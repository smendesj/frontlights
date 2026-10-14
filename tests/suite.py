"""Runner paralelo da suíte de testes do Frontlights (issue 27).

Roda cada módulo `test_*.py` da pasta como um processo filho (`python -m unittest discover -s <pasta> -p <arquivo>`,
o mesmo modo da suíte inteira, que respeita o `load_tests` da suíte rápida): os módulos sensíveis da lista SERIAL
vão numa fila serial, um por vez e na ordem da lista; os demais, num pool de processos. O primeiro serial roda
sozinho; quando termina, o pool e o resto da fila seguem ao mesmo tempo. Só biblioteca padrão; só Windows.

Uso: python tests/suite.py [--tests-dir PASTA] [--serial a,b,c] [--workers N] [--module-timeout S] [--list]
"""
import argparse
import locale
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VARIABLE = 'FRONTLIGHTS_SUITE'

# Fila serial, nesta ordem (nome do módulo, motivo). Tudo o que não está aqui vai para o pool.
SERIAL = (
    ('test_serve_ports', 'cerca de 48 processos simultâneos, 19 asserções de tempo, PIDs mortos, portas '
                         'pré-escolhidas'),
    ('test_checks_integration', 'portas pré-escolhidas e PIDs mortos'),
    ('test_serve', 'portas pré-escolhidas, servidores reais'),
    ('test_browser_app_example', 'Chromium quando o Playwright existe'),
    ('test_checks', 'asserções de 14 s e 20 s com prazos reais de 1 s; por último, para não disputar CPU'),
)

RAN_LINE = re.compile(r'^Ran (\d+) tests? in [\d.]+s$', re.MULTILINE)
VERDICT_LINE = re.compile(r'^(OK|FAILED)(?: \((.*)\))?$')
COUNT_KEYS = ('failures', 'errors', 'skipped', 'expected failures', 'unexpected successes')


# --- linha de comando ---------------------------------------------------------------------------------------

def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f'{text!r}: precisa ser um inteiro maior ou igual a 1')
    return value


def positive_float(text):
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f'{text!r}: precisa ser um número maior que 0')
    return value


def existing_dir(text):
    path = Path(text)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f'{text!r}: a pasta não existe')
    return path


def default_workers():
    return max(1, (os.cpu_count() or 1) - 2)


def parse(argv):
    parser = argparse.ArgumentParser(description='Roda os módulos de teste em paralelo, com uma fila serial '
                                                 'para os módulos sensíveis.')
    parser.add_argument('--tests-dir', type=existing_dir, default=None,
                        help='pasta dos módulos test_*.py (padrão: a pasta deste script)')
    parser.add_argument('--serial', default=None,
                        help='lista de módulos seriais separados por vírgula, no lugar da lista SERIAL '
                             '(vazia = nenhum serial)')
    parser.add_argument('--workers', type=positive_int, default=default_workers(),
                        help='trabalhadores do pool (padrão: max(1, cpu_count - 2))')
    parser.add_argument('--module-timeout', type=positive_float, default=900,
                        help='prazo por módulo, em segundos (padrão: 900; ainda sem efeito nesta versão)')
    parser.add_argument('--list', action='store_true', help='só lista os módulos e a ordem, sem rodar nada')
    return parser.parse_args(argv)


# --- plano --------------------------------------------------------------------------------------------------

class Plan:
    """Os módulos que rodariam: a fila serial na ordem dada e o pool em ordem alfabética."""

    def __init__(self, tests_dir, shown_dir, serial, pool, workers):
        self.tests_dir = tests_dir
        self.shown_dir = shown_dir
        self.serial = serial
        self.pool = pool
        self.workers = workers

    def entries(self):
        return [(name, 'serial') for name in self.serial] + [(name, 'pool') for name in self.pool]


def serial_names(text):
    if text is None:
        return [name for name, _ in SERIAL]
    names = []
    for item in text.split(','):
        item = item.strip()
        if item.endswith('.py'):
            item = item[:-3]
        if item:
            names.append(item)
    return names


def plan(options):
    tests_dir = options.tests_dir
    shown_dir = str(tests_dir) if tests_dir is not None else 'tests'
    tests_dir = (tests_dir if tests_dir is not None else Path(__file__).parent).resolve()
    found = sorted(path.stem for path in tests_dir.glob('test_*.py') if path.is_file())
    if not found:
        raise SystemExit(f'Nenhum módulo test_*.py em {tests_dir}.')
    serial = serial_names(options.serial)
    missing = [name for name in serial if name not in found]
    if missing:
        raise SystemExit(f'Módulo serial inexistente em {tests_dir}: {", ".join(missing)}. Nada foi rodado.')
    repeated = sorted({name for name in serial if serial.count(name) > 1})
    if repeated:
        raise SystemExit(f'Módulo repetido na lista serial: {", ".join(repeated)}. Nada foi rodado.')
    pool = [name for name in found if name not in serial]
    return Plan(tests_dir, shown_dir, serial, pool, options.workers)


def print_list(current):
    for order, (name, kind) in enumerate(current.entries(), start=1):
        print(f'{order:>3}  {kind:<6}  {name}')


# --- um módulo por processo filho ---------------------------------------------------------------------------

class Outcome:
    """O que um módulo deixou: tempo de parede, código de saída, saída completa e as contagens lidas dela."""

    def __init__(self, name, kind, wall, returncode, output):
        self.name = name
        self.kind = kind
        self.wall = wall
        self.returncode = returncode
        self.output = output
        ran = RAN_LINE.search(output)
        self.ran = int(ran.group(1)) if ran else None
        self.verdict, self.counts = read_verdict(output)
        # Sem a linha `Ran` ou sem veredito reconhecido, o módulo conta como falha. S2: isso vira erro de
        # infraestrutura (saída 2), junto com o prazo por módulo.
        self.passed = returncode == 0 and self.ran is not None and self.verdict is not None \
            and self.verdict.startswith('OK')


def read_verdict(output):
    """A última linha não vazia da saída do unittest: `OK`, `OK (skipped=1)`, `FAILED (failures=1, errors=2)`."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    match = VERDICT_LINE.match(lines[-1]) if lines else None
    if not match:
        return None, {}
    counts = {}
    for item in (match.group(2) or '').split(','):
        key, _, value = item.strip().partition('=')
        if key in COUNT_KEYS and value.isdigit():
            counts[key] = int(value)
    return lines[-1], counts


def decode(raw):
    """UTF-8 quando a saída é UTF-8; senão a codificação local do console, com substituição. Quebras `\\r\\n`
    viram `\\n`, para o regex de linha e para não dobrar as linhas em branco ao reimprimir."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode(locale.getpreferredencoding(False), errors='replace')
    return text.replace('\r\n', '\n')


def command_for(tests_dir, name):
    return [sys.executable, '-m', 'unittest', 'discover', '-s', str(tests_dir), '-p', f'{name}.py']


def run_module(current, name, kind, root):
    """Roda um módulo como processo filho e devolve o Outcome. S2 acrescenta aqui o prazo e o kill."""
    started = time.monotonic()
    process = subprocess.Popen(command_for(current.tests_dir, name), cwd=str(root), env=dict(os.environ),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw, _ = process.communicate()
    return Outcome(name, kind, time.monotonic() - started, process.returncode, decode(raw))


# --- escalonamento ------------------------------------------------------------------------------------------

class Run:
    """Roda o plano: o primeiro serial sozinho; depois o pool e o resto da fila serial ao mesmo tempo."""

    def __init__(self, current, root):
        self.current = current
        self.root = root
        self.lock = threading.Lock()
        self.outcomes = {}

    def one(self, name, kind):
        outcome = run_module(self.current, name, kind, self.root)
        with self.lock:
            self.outcomes[name] = outcome
            print(module_line(outcome), flush=True)
        return outcome

    def serial_rest(self, names):
        for name in names:
            self.one(name, 'serial')

    def execute(self):
        serial = list(self.current.serial)
        if serial:
            self.one(serial[0], 'serial')
        rest = threading.Thread(target=self.serial_rest, args=(serial[1:],), name='fila-serial')
        rest.start()
        with ThreadPoolExecutor(max_workers=self.current.workers, thread_name_prefix='pool') as pool:
            for future in [pool.submit(self.one, name, 'pool') for name in self.current.pool]:
                future.result()
        rest.join()
        return [self.outcomes[name] for name, _ in self.current.entries()]


# --- saída --------------------------------------------------------------------------------------------------

def print_header(current):
    value = os.environ.get(VARIABLE)
    print('Suíte do Frontlights em paralelo')
    resolved = f' ({current.tests_dir})' if str(current.tests_dir) != current.shown_dir else ''
    print(f'Pasta: {current.shown_dir}{resolved}')
    print(f'{VARIABLE}={value}' if value is not None else f'{VARIABLE} (sem variável)')
    print(f'Trabalhadores: {current.workers}')
    print(f'Fila serial: {", ".join(current.serial) if current.serial else "(nenhuma)"}')
    print(f'Módulos: {len(current.serial) + len(current.pool)} ({len(current.serial)} seriais, '
          f'{len(current.pool)} no pool)')
    print(flush=True)


def module_line(outcome):
    ran = f'Ran {outcome.ran}' if outcome.ran is not None else 'Ran ?'
    verdict = outcome.verdict if outcome.verdict is not None else f'(sem veredito; saída {outcome.returncode})'
    return f'[{outcome.kind:<6}] {outcome.name:<34} {outcome.wall:7.1f}s  {ran:<9} {verdict}'


def summary_line(outcomes):
    """O resultado somado, no formato do unittest: os zeros ficam de fora."""
    totals = {key: sum(outcome.counts.get(key, 0) for outcome in outcomes) for key in COUNT_KEYS}
    failed = any(not outcome.passed for outcome in outcomes)
    infos = []
    if failed:
        if totals['failures']:
            infos.append(f'failures={totals["failures"]}')
        if totals['errors']:
            infos.append(f'errors={totals["errors"]}')
    for key in ('skipped', 'expected failures', 'unexpected successes'):
        if totals[key]:
            infos.append(f'{key}={totals[key]}')
    verdict = 'FAILED' if failed else 'OK'
    return verdict + (f' ({", ".join(infos)})' if infos else '')


def print_failures(current, outcomes):
    for outcome in outcomes:
        if outcome.passed:
            continue
        print('=' * 70)
        print(f'{outcome.name} ({outcome.kind}): saída completa, código de saída {outcome.returncode}')
        print('-' * 70)
        print(outcome.output.rstrip('\n'))
        print(f'Rode sozinho: python -m unittest discover -s {current.shown_dir} -p {outcome.name}.py')
        print()


def print_total(outcomes, wall):
    ran = sum(outcome.ran or 0 for outcome in outcomes)
    print('-' * 70)
    print(f'Ran {ran} test{"" if ran == 1 else "s"} in {wall:.3f}s')
    print()
    print(summary_line(outcomes), flush=True)


# --- principal ----------------------------------------------------------------------------------------------

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if sys.platform != 'win32':
        print(f'tests/suite.py só roda no Windows (sys.platform={sys.platform}). Em outro sistema, rode '
              'python -m unittest discover -s tests -v.', file=sys.stderr)
        return 2
    options = parse(sys.argv[1:] if argv is None else argv)
    try:
        current = plan(options)
    except SystemExit as error:
        print(error, file=sys.stderr)
        return 2
    if options.list:
        print_list(current)
        return 0
    root = Path(__file__).resolve().parents[1]
    print_header(current)
    started = time.monotonic()
    outcomes = Run(current, root).execute()
    wall = time.monotonic() - started
    print()
    print_failures(current, outcomes)
    print_total(outcomes, wall)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == '__main__':
    sys.exit(main())
