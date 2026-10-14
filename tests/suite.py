"""Runner paralelo da suíte de testes do Frontlights (issue 27, S1, S2 e S3).

Roda cada módulo `test_*.py` da pasta como um processo filho (`python -m unittest discover -s <pasta> -p <arquivo>`,
o mesmo modo da suíte inteira, que respeita o `load_tests` da suíte rápida): os módulos sensíveis da lista SERIAL
vão numa fila serial, um por vez e na ordem da lista; os demais, num pool de processos. O primeiro serial roda
sozinho; quando termina, o pool e o resto da fila seguem ao mesmo tempo. Só biblioteca padrão; só Windows.

Cada módulo tem um prazo (`--module-timeout`): estourado, a árvore inteira do filho é morta e a saída parcial fica
registrada. Prazo estourado, módulo que não importa e filho que termina sem a linha `Ran N tests` são erros de
infraestrutura: a suíte sai com 2, que prevalece sobre o 1 das falhas de produto sem escondê-las. `Ran 0 tests`
é aceito e conta zero. Ctrl+C ou Ctrl+Break mata todos os filhos vivos antes de sair com 130.

`--report <arquivo>` grava a rodada em JSON (UTF-8), como evidência: início e fim com fuso, HEAD do repositório,
variável, trabalhadores e, por módulo, fila, tempo, contagens, resultado e o comando para rodá-lo sozinho. Numa
interrupção, o relatório sai com `result: "interrupted"` e só os módulos que terminaram antes dela.

Uso: python tests/suite.py [--tests-dir PASTA] [--serial a,b,c] [--workers N] [--module-timeout S]
                           [--report ARQUIVO] [--list]
"""
import argparse
import json
import locale
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

VARIABLE = 'FRONTLIGHTS_SUITE'
INTERRUPTED = 130
POLL_SECONDS = 0.2  # a thread principal nunca bloqueia sem prazo: é assim que o Ctrl+C/Ctrl+Break chega a ela
KILL_WAIT_SECONDS = 5
IMPORT_FAILURE = re.compile(r'unittest\.loader\._FailedTest|Failed to import test module')

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
VERDICT_LINE = re.compile(r'^(OK|FAILED|NO TESTS RAN)(?: \((.*)\))?$')  # NO TESTS RAN: 3.12+ com zero testes
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


def report_path(text):
    path = Path(text)
    if not path.parent.is_dir():
        raise argparse.ArgumentTypeError(f'{text!r}: a pasta do relatório não existe')
    return path


DEFAULT_WORKERS = 4  # o mais rápido medido na issue 27 (revisão r2): mais trabalhadores atrasam a fila serial


def default_workers():
    return DEFAULT_WORKERS


def parse(argv):
    parser = argparse.ArgumentParser(description='Roda os módulos de teste em paralelo, com uma fila serial '
                                                 'para os módulos sensíveis.')
    parser.add_argument('--tests-dir', type=existing_dir, default=None,
                        help='pasta dos módulos test_*.py (padrão: a pasta deste script)')
    parser.add_argument('--serial', default=None,
                        help='lista de módulos seriais separados por vírgula, no lugar da lista SERIAL '
                             '(vazia = nenhum serial)')
    parser.add_argument('--workers', type=positive_int, default=default_workers(),
                        help=f'trabalhadores do pool (padrão: {DEFAULT_WORKERS})')
    parser.add_argument('--module-timeout', type=positive_float, default=900,
                        help='prazo por módulo, em segundos; estourado, a árvore do filho é morta e a suíte sai '
                             'com 2 (padrão: 900)')
    parser.add_argument('--report', type=report_path, default=None,
                        help='grava a rodada em JSON neste arquivo, como evidência (a pasta precisa existir)')
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
    """O que um módulo deixou: tempo de parede, código de saída, saída (completa ou parcial) e as contagens lidas
    dela. `problem` é o erro de infraestrutura, quando há; `passed` só vale sem problema e com veredito OK."""

    def __init__(self, name, kind, wall, returncode, output, timed_out=None):
        self.name = name
        self.kind = kind
        self.wall = wall
        self.returncode = returncode
        self.output = output
        self.timed_out = timed_out  # o prazo, em segundos, quando ele estourou
        ran = RAN_LINE.search(output)
        self.ran = int(ran.group(1)) if ran else None
        self.verdict, self.counts = read_verdict(output)
        self.problem = self.infrastructure_problem()
        if self.problem is not None:
            self.passed = False
        elif self.ran == 0:
            self.passed = returncode in (0, 5)  # 3.11: rc 0 e `OK`; 3.12+: rc 5 e `NO TESTS RAN`
        else:
            self.passed = returncode == 0 and self.verdict.startswith('OK')

    def infrastructure_problem(self):
        """O motivo pelo qual o módulo não chegou a dar um veredito de produto, ou None."""
        if self.timed_out is not None:
            return f'prazo de {self.timed_out:.1f} s estourado'
        if IMPORT_FAILURE.search(self.output):
            return 'o módulo não importou'
        if self.ran is None:
            return f'sem a linha "Ran N tests" (código de saída {self.returncode})'
        if self.verdict is None:
            return f'sem veredito do unittest (código de saída {self.returncode})'
        return None


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


def pid_alive(pid):
    """OpenProcess + GetExitCodeProcess == STILL_ACTIVE (259), como serve.pid_alive: o código de saída do taskkill
    não é prova de morte."""
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        return bool(ok) and code.value == 259
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def kill_tree(process):
    """Mata o filho com a árvore inteira (`taskkill /T /F`) e confirma a morte do filho pela API. Devolve True
    quando ele morreu. Limite conhecido: um neto cujo pai já morreu fica fora do `/T` (sem Job Object aqui);
    a leitora daemon garante que ele não prende o runner, só a saída parcial."""
    try:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass
    deadline = time.monotonic() + KILL_WAIT_SECONDS
    while pid_alive(process.pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not pid_alive(process.pid)


class Reader(threading.Thread):
    """Lê o pipe do filho num buffer: o que o filho já imprimiu está lá mesmo se um neto segurar o pipe aberto."""

    def __init__(self, stream):
        super().__init__(name='leitora', daemon=True)
        self.stream = stream
        self.buffer = bytearray()

    def run(self):
        try:
            while True:
                chunk = self.stream.read1(65536)
                if not chunk:
                    break
                self.buffer += chunk
        except (OSError, ValueError):
            pass


def run_module(current, name, kind, root, timeout, live, stopping):
    """Roda um módulo como processo filho, em grupo próprio (o Ctrl+Break do console não chega nele: quem o mata é
    o runner), e devolve o Outcome. Passado o prazo, mata a árvore e guarda a saída parcial. `live` é o registro
    dos filhos vivos, para o abort; `stopping` encerra a espera quando a suíte foi interrompida."""
    started = time.monotonic()
    process = subprocess.Popen(command_for(current.tests_dir, name), cwd=str(root), env=dict(os.environ),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    reader = Reader(process.stdout)
    reader.start()
    live.add(name, process)
    timed_out = None
    try:
        deadline = started + timeout
        while True:
            try:
                process.wait(timeout=max(0.0, min(POLL_SECONDS, deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if stopping.is_set():
                    if process.poll() is None:
                        kill_tree(process)
                    process.wait()
                    break
                if time.monotonic() >= deadline:
                    timed_out = timeout
                    kill_tree(process)
                    process.wait()
                    break
    finally:
        live.remove(name)
    reader.join(KILL_WAIT_SECONDS)
    output = decode(bytes(reader.buffer))
    return Outcome(name, kind, time.monotonic() - started, process.returncode, output, timed_out)


class Live:
    """Os filhos vivos, por nome, sob trava: o abort mata cada um com a árvore."""

    def __init__(self):
        self.lock = threading.Lock()
        self.processes = {}

    def add(self, name, process):
        with self.lock:
            self.processes[name] = process

    def remove(self, name):
        with self.lock:
            self.processes.pop(name, None)

    def kill_all(self):
        with self.lock:
            processes = list(self.processes.values())
        killed = 0
        for process in processes:
            try:
                kill_tree(process)
            finally:
                killed += 1
        return killed


# --- escalonamento ------------------------------------------------------------------------------------------

class Run:
    """Roda o plano: o primeiro serial sozinho; depois o pool e o resto da fila serial ao mesmo tempo. Os filhos
    rodam em threads; a thread principal só espera com prazo (POLL_SECONDS), para o Ctrl+C/Ctrl+Break chegar."""

    def __init__(self, current, root, timeout):
        self.current = current
        self.root = root
        self.timeout = timeout
        self.lock = threading.Lock()
        self.outcomes = {}
        self.live = Live()
        self.stopping = threading.Event()
        self.executor = None

    def one(self, name, kind):
        if self.stopping.is_set():
            return None
        outcome = run_module(self.current, name, kind, self.root, self.timeout, self.live, self.stopping)
        with self.lock:
            self.outcomes[name] = outcome
            if not self.stopping.is_set():
                print(module_line(outcome), flush=True)
        return outcome

    def serial_queue(self, names, first_done):
        try:
            for name in names:
                if self.stopping.is_set():
                    break
                self.one(name, 'serial')
                first_done.set()
        finally:
            first_done.set()

    def execute(self):
        first_done = threading.Event()
        queue = threading.Thread(target=self.serial_queue, args=(list(self.current.serial), first_done),
                                 name='fila-serial')
        queue.start()
        while not first_done.wait(POLL_SECONDS):
            pass
        self.executor = ThreadPoolExecutor(max_workers=self.current.workers, thread_name_prefix='pool')
        futures = [self.executor.submit(self.one, name, 'pool') for name in self.current.pool]
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=POLL_SECONDS)
        while queue.is_alive():
            queue.join(POLL_SECONDS)
        self.executor.shutdown(wait=False)
        for future in futures:
            future.result()  # relança um erro inesperado da thread, em vez de um KeyError adiante
        return [self.outcomes[name] for name, _ in self.current.entries()]

    def abort(self):
        """Interrupção: nada mais começa, todo filho vivo morre com a árvore. Devolve quantos foram mortos."""
        self.stopping.set()
        try:
            return self.live.kill_all()
        finally:
            if self.executor is not None:
                self.executor.shutdown(wait=False, cancel_futures=True)


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
    head = f'[{outcome.kind:<6}] {outcome.name:<34} {outcome.wall:7.1f}s  '
    if outcome.problem is not None:
        return head + f'infraestrutura: {outcome.problem}'
    return head + f'{f"Ran {outcome.ran}":<9} {outcome.verdict}'


def counted(outcomes):
    """Os módulos cujas contagens entram no total: um erro de infraestrutura não rodou de verdade (o `Ran 1` e o
    `errors=1` de um módulo que não importou são do carregador, não do produto)."""
    return [outcome for outcome in outcomes if outcome.problem is None]


def summary_line(outcomes):
    """O resultado somado, no formato do unittest, mais `infraestrutura=N` (módulos): os zeros ficam de fora."""
    totals = {key: sum(outcome.counts.get(key, 0) for outcome in counted(outcomes)) for key in COUNT_KEYS}
    problems = sum(1 for outcome in outcomes if outcome.problem is not None)
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
    if problems:
        infos.append(f'infraestrutura={problems}')
    verdict = 'FAILED' if failed else 'OK'
    return verdict + (f' ({", ".join(infos)})' if infos else '')


def print_failures(current, outcomes):
    for outcome in outcomes:
        if outcome.passed:
            continue
        print('=' * 70)
        if outcome.timed_out is not None:
            print(f'{outcome.name} ({outcome.kind}): infraestrutura: {outcome.problem}, árvore de processos morta; '
                  'saída parcial')
        elif outcome.problem is not None:
            print(f'{outcome.name} ({outcome.kind}): infraestrutura: {outcome.problem}; saída completa')
        else:
            print(f'{outcome.name} ({outcome.kind}): saída completa, código de saída {outcome.returncode}')
        print('-' * 70)
        print(outcome.output.rstrip('\n'))
        print(f'Rode sozinho: {rerun_command(current, outcome.name)}')
        print()


def rerun_command(current, name):
    return f'python -m unittest discover -s {current.shown_dir} -p {name}.py'


def print_total(outcomes, wall):
    ran = sum(outcome.ran or 0 for outcome in counted(outcomes))
    print('-' * 70)
    print(f'Ran {ran} test{"" if ran == 1 else "s"} in {wall:.3f}s')
    print()
    problems = [outcome for outcome in outcomes if outcome.problem is not None]
    if problems:
        print('Infraestrutura: ' + '; '.join(f'{outcome.name} ({outcome.problem})' for outcome in problems))
    print(summary_line(outcomes), flush=True)


def exit_code(outcomes):
    """2 (infraestrutura) prevalece sobre 1 (falha de produto); 0 só com tudo verde."""
    if any(outcome.problem is not None for outcome in outcomes):
        return 2
    return 0 if all(outcome.passed for outcome in outcomes) else 1


# --- relatório JSON (--report) ------------------------------------------------------------------------------

RESULTS = {0: 'ok', 1: 'failed', 2: 'infrastructure', INTERRUPTED: 'interrupted'}


def git_head(root):
    """O commit do repositório onde este script está, ou None fora de um repositório ou em erro do git."""
    try:
        completed = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                   timeout=45)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def module_record(current, outcome):
    if outcome.problem is not None:
        result = 'infrastructure'
    else:
        result = 'ok' if outcome.passed else 'failed'
    return {
        'name': outcome.name,
        'queue': outcome.kind,
        'seconds': round(outcome.wall, 3),
        'tests_run': outcome.ran,
        'skipped': outcome.counts.get('skipped', 0),
        'failures': outcome.counts.get('failures', 0),
        'errors': outcome.counts.get('errors', 0),
        'result': result,
        'exit_code': None if outcome.timed_out is not None else outcome.returncode,
        'problem': outcome.problem,
        'command': rerun_command(current, outcome.name),
    }


def report_data(current, options, head, started_at, wall, outcomes, code):
    """O JSON da rodada. Os totais somam só os módulos sem erro de infraestrutura, como a linha de total."""
    good = counted(outcomes)
    return {
        'version': 1,
        'started_at': started_at.isoformat(timespec='milliseconds'),
        'finished_at': datetime.now().astimezone().isoformat(timespec='milliseconds'),
        'seconds': round(wall, 3),
        'head': head,
        'variable': os.environ.get(VARIABLE),
        'workers': current.workers,
        'module_timeout': options.module_timeout,
        'tests_dir': str(current.tests_dir),
        'modules': [module_record(current, outcome) for outcome in outcomes],
        'totals': {
            'modules': len(outcomes),
            'tests_run': sum(outcome.ran or 0 for outcome in good),
            'skipped': sum(outcome.counts.get('skipped', 0) for outcome in good),
            'failures': sum(outcome.counts.get('failures', 0) for outcome in good),
            'errors': sum(outcome.counts.get('errors', 0) for outcome in good),
            'infrastructure': len(outcomes) - len(good),
        },
        'result': RESULTS[code],
        'exit_code': code,
    }


def write_report(path, data):
    """Grava o relatório; devolve False (com o motivo no stderr) quando não consegue."""
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError as error:
        print(f'Relatório não gravado em {path}: {error}', file=sys.stderr)
        return False
    print(f'Relatório: {path}', flush=True)
    return True


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
    head = git_head(root) if options.report is not None else None
    install_break_handler()
    print_header(current)
    started_at = datetime.now().astimezone()
    started = time.monotonic()
    run = Run(current, root, options.module_timeout)
    try:
        outcomes = run.execute()
    except KeyboardInterrupt:
        with run.lock:  # os que terminaram antes da interrupção; os mortos por ela ficam de fora
            finished = [run.outcomes[name] for name, _ in current.entries() if name in run.outcomes]
        killed = run.abort()
        print(f'\nInterrompido: {killed} módulo{"" if killed == 1 else "s"} morto{"" if killed == 1 else "s"} '
              f'(com as árvores de processos); nada foi somado.', flush=True)
        if options.report is not None:
            write_report(options.report, report_data(current, options, head, started_at,
                                                     time.monotonic() - started, finished, INTERRUPTED))
        return INTERRUPTED
    wall = time.monotonic() - started
    print()
    print_failures(current, outcomes)
    print_total(outcomes, wall)
    code = exit_code(outcomes)
    if options.report is not None:
        if not write_report(options.report, report_data(current, options, head, started_at, wall, outcomes, code)):
            return max(code, 2)  # sem a evidência pedida, a rodada é um erro de infraestrutura
    return code


def install_break_handler():
    """Ctrl+Break (SIGBREAK, só Windows) vira KeyboardInterrupt na thread principal, como o Ctrl+C."""
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)


if __name__ == '__main__':
    sys.exit(main())
