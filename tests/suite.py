"""Runner paralelo da suíte de testes do Frontlights (issue 27, S1, S2 e S3).

Roda cada módulo `test_*.py` da pasta como um processo filho (`python -m unittest discover -s <pasta> -p <arquivo>`,
o mesmo modo da suíte inteira, que respeita o `load_tests` da suíte rápida): os módulos sensíveis da lista SERIAL
vão numa fila serial, um por vez e na ordem da lista; os demais, num pool de processos. O primeiro serial roda
sozinho; quando termina, o pool e o resto da fila seguem ao mesmo tempo. Só biblioteca padrão; só Windows.

Cada módulo tem um prazo (`--module-timeout`): estourado, a árvore inteira do filho é morta e a saída parcial fica
registrada. Prazo estourado, módulo que não importa, filho que termina sem a linha `Ran N tests` e erro interno do
runner são erros de infraestrutura: a suíte sai com 2, que prevalece sobre o 1 das falhas de produto sem
escondê-las. `Ran 0 tests` é aceito e conta zero. A contagem e o veredito vêm do bloco final do unittest (a última
linha `Ran N tests` em coluna 0 e o veredito depois dela, sem as cores ANSI); a falha de import, do cabeçalho de
erro do unittest para aquele módulo.

Ctrl+C ou Ctrl+Break interrompe a rodada: nada mais começa, todos os filhos vivos morrem com a árvore e a suíte
sai com 130. O Ctrl+Break do teclado chega também aos filhos (o grupo próprio só os livra do Ctrl+C), que morrem
com 0xC000013A antes de a thread principal reagir: esse código conta como interrupção, não como erro do módulo.

`--report <arquivo>` grava a rodada em JSON (UTF-8), como evidência: início e fim com fuso, HEAD do repositório,
variável, trabalhadores e, por módulo, fila, tempo, contagens, resultado e o comando para rodá-lo sozinho. Numa
interrupção, o relatório sai com `result: "interrupted"` e só os módulos que terminaram antes dela.

Uso: python tests/suite.py [--tests-dir PASTA] [--serial a,b,c] [--workers N] [--module-timeout S]
                           [--report ARQUIVO] [--list]
"""
import argparse
import json
import locale
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

VARIABLE = 'FRONTLIGHTS_SUITE'
INTERRUPTED = 130
POLL_SECONDS = 0.2  # a thread principal nunca bloqueia sem prazo: é assim que o Ctrl+C/Ctrl+Break chega a ela
KILL_WAIT_SECONDS = 5
STATUS_CONTROL_C_EXIT = 0xC000013A  # 3221225786: o código de quem morre pelo Ctrl+C/Ctrl+Break do console

# Fila serial, nesta ordem (nome do módulo, motivo). Tudo o que não está aqui vai para o pool.
SERIAL = (
    ('test_serve_ports', 'cerca de 48 processos simultâneos, 19 asserções de tempo, PIDs mortos, portas '
                         'pré-escolhidas'),
    ('test_checks_integration', 'portas pré-escolhidas e PIDs mortos'),
    ('test_serve', 'portas pré-escolhidas, servidores reais'),
    ('test_serve_preview', 'servidores reais da prévia, relés de log e reservas de porta'),
    ('test_browser_app_example', 'Chromium quando o Playwright existe'),
    ('test_checks', 'asserções de 14 s e 20 s com prazos reais de 1 s; por último, para não disputar CPU'),
)

ANSI = re.compile(r'\x1b\[[0-9;]*m')  # 3.13+ colore a saída do unittest com FORCE_COLOR ou PYTHON_COLORS
RAN_LINE = re.compile(r'^Ran (\d+) tests? in [\d.]+s$')
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
    if not math.isfinite(value) or value <= 0:  # nan e inf passariam pelo `<= 0` e dariam um JSON inválido
        raise argparse.ArgumentTypeError(f'{text!r}: precisa ser um número finito maior que 0')
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


def parse(argv):
    parser = argparse.ArgumentParser(description='Roda os módulos de teste em paralelo, com uma fila serial '
                                                 'para os módulos sensíveis.')
    parser.add_argument('--tests-dir', type=existing_dir, default=None,
                        help='pasta dos módulos test_*.py (padrão: a pasta deste script)')
    parser.add_argument('--serial', default=None,
                        help='lista de módulos seriais separados por vírgula, no lugar da lista SERIAL '
                             '(vazia = nenhum serial)')
    parser.add_argument('--workers', type=positive_int, default=DEFAULT_WORKERS,
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
    dela. `problem` é o erro de infraestrutura, quando há (dado de fora, ou lido da saída); `passed` só vale sem
    problema e com veredito OK."""

    def __init__(self, name, kind, wall, returncode, output, timed_out=None, problem=None):
        self.name = name
        self.kind = kind
        self.wall = wall
        self.returncode = returncode
        self.output = output
        self.timed_out = timed_out  # o prazo, em segundos, quando ele estourou
        lines = plain_lines(output)
        self.ran, self.verdict, self.counts = read_final_block(lines)
        self.import_failed = import_failed(lines, name)
        self.problem = problem if problem is not None else self.infrastructure_problem()
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
        if self.import_failed:
            return 'o módulo não importou'
        if self.ran is None:
            return f'sem a linha "Ran N tests" (código de saída {self.returncode})'
        if self.verdict is None:
            return f'sem veredito do unittest (código de saída {self.returncode})'
        return None


def plain_lines(output):
    """As linhas da saída sem as sequências de cor ANSI e sem o espaço à direita."""
    return [ANSI.sub('', line).rstrip() for line in output.splitlines()]


def read_final_block(lines):
    """O bloco final do unittest: a ÚLTIMA linha `Ran N tests in X s` em coluna 0 e o veredito (`OK`,
    `OK (skipped=1)`, `FAILED (failures=1, errors=2)`) na primeira linha depois dela que casa com VERDICT_LINE.
    Texto que chega ao pipe depois do resumo (print sem flush, atexit, um neto) e um runner aninhado numa mensagem
    de falha, que vem antes do resumo, não mudam a leitura. Devolve (quantos rodaram, veredito, contagens), com
    None no que faltar."""
    last = None
    for index, line in enumerate(lines):
        if RAN_LINE.match(line):
            last = index
    if last is None:
        return None, None, {}
    ran = int(RAN_LINE.match(lines[last]).group(1))
    for line in lines[last + 1:]:
        match = VERDICT_LINE.match(line)
        if match:
            counts = {}
            for item in (match.group(2) or '').split(','):
                key, _, value = item.strip().partition('=')
                if key in COUNT_KEYS and value.isdigit():
                    counts[key] = int(value)
            return ran, line, counts
    return ran, None, {}


def import_failed(lines, name):
    """Se o unittest relatou que ESTE módulo não importou: o cabeçalho de erro dele, em coluna 0,
    `ERROR: <nome> (unittest.loader._FailedTest.<nome>)` (até o 3.10, sem o `.<nome>` final). O mesmo texto
    dentro de uma mensagem de falha, ou de outro módulo, não conta."""
    escaped = re.escape(name)
    header = re.compile(rf'^ERROR: {escaped} \(unittest\.loader\._FailedTest(?:\.{escaped})?\)$')
    return any(header.match(line) for line in lines)


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


def kill_tree(process):
    """Mata o filho com a árvore inteira (`taskkill /T /F`) e, de reserva, pelo handle (`process.kill()`). Só age
    enquanto `poll()` é None: o Popen segura o handle do filho, então o PID ainda é dele (nunca um PID reusado).
    Limite conhecido: um neto cujo pai já morreu fica fora do `/T` (sem Job Object aqui); a leitora daemon garante
    que ele não prende o runner, só a saída parcial."""
    if process.poll() is not None:
        return
    try:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


def stop_tree(process):
    """Mata a árvore e espera o filho com prazo (KILL_WAIT_SECONDS), sem travar a thread. False quando ele não
    morreu: quem chama registra isso como erro de infraestrutura."""
    kill_tree(process)
    try:
        process.wait(timeout=KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return True


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
    """Roda um módulo como processo filho e devolve o Outcome, ou None quando a rodada foi interrompida. O filho
    roda em grupo próprio, que o livra só do Ctrl+C do console: o Ctrl+Break do teclado chega a todos os processos
    do console, e o filho morre com 0xC000013A (STATUS_CONTROL_C_EXIT) antes de a thread principal reagir; esse
    código liga `stopping` e conta como interrupção, não como erro do módulo. Passado o prazo, mata a árvore e
    guarda a saída parcial; se a árvore não morrer, é erro de infraestrutura. `live` é o registro dos filhos vivos,
    para o abort; `stopping` encerra a espera quando a suíte foi interrompida."""
    started = time.monotonic()
    process = subprocess.Popen(command_for(current.tests_dir, name), cwd=str(root), env=dict(os.environ),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    reader = Reader(process.stdout)
    reader.start()
    live.add(name, process)
    timed_out = None
    problem = None
    interrupted = False
    try:
        deadline = started + timeout
        while True:
            try:
                process.wait(timeout=max(0.0, min(POLL_SECONDS, deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if stopping.is_set():
                    interrupted = True
                    stop_tree(process)
                    break
                if time.monotonic() >= deadline:
                    timed_out = timeout
                    if not stop_tree(process):
                        problem = (f'prazo de {timeout:.1f} s estourado; não foi possível matar a árvore de '
                                   'processos')
                    break
    except BaseException:
        stop_tree(process)  # um erro aqui não deixa filho vivo
        raise
    finally:
        live.remove(name)
    if interrupted or process.returncode == STATUS_CONTROL_C_EXIT:
        stopping.set()
        return None
    reader.join(KILL_WAIT_SECONDS)
    output = decode(bytes(reader.buffer))
    return Outcome(name, kind, time.monotonic() - started, process.returncode, output, timed_out, problem)


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
        """Mata a árvore de cada filho ainda vivo; devolve os nomes dos que ela matou."""
        with self.lock:
            processes = list(self.processes.items())
        killed = set()
        for name, process in processes:
            if process.poll() is None:
                kill_tree(process)
                killed.add(name)
        return killed


# --- escalonamento ------------------------------------------------------------------------------------------

class Run:
    """Roda o plano: o primeiro serial sozinho; depois o pool e o resto da fila serial ao mesmo tempo. Os filhos
    rodam em threads; a thread principal só espera com prazo (POLL_SECONDS), para o Ctrl+C/Ctrl+Break chegar, e
    confere `stopping` a cada volta: um filho morto pelo evento do console liga `stopping` sem que a thread
    principal receba sinal nenhum. Com `stopping` ligado, nenhuma fila começa módulo novo."""

    def __init__(self, current, root, timeout):
        self.current = current
        self.root = root
        self.timeout = timeout
        self.lock = threading.Lock()
        self.outcomes = {}
        self.interrupted = set()  # os módulos que a interrupção matou (pelo runner ou pelo próprio evento)
        self.errors = []  # (onde, traceback) dos erros das threads fora de um módulo
        self.live = Live()
        self.stopping = threading.Event()
        self.executor = None
        self.queue = None
        self.futures = []

    def one(self, name, kind):
        """Um módulo. Um erro inesperado vira um Outcome de infraestrutura com o traceback, em vez de sumir na
        thread; um módulo que termina com a rodada já interrompida não entra nos resultados."""
        if self.stopping.is_set():
            return
        started = time.monotonic()
        try:
            outcome = run_module(self.current, name, kind, self.root, self.timeout, self.live, self.stopping)
        except Exception as error:
            outcome = Outcome(name, kind, time.monotonic() - started, None, traceback.format_exc(),
                              problem=f'erro interno do runner ({type(error).__name__}: {error})')
        with self.lock:
            if outcome is None:
                self.interrupted.add(name)
            elif not self.stopping.is_set():
                self.outcomes[name] = outcome
                print(module_line(outcome), flush=True)

    def serial_queue(self, names, first_done):
        try:
            for name in names:
                if self.stopping.is_set():
                    break
                self.one(name, 'serial')
                first_done.set()
        except Exception:
            with self.lock:
                self.errors.append(('fila serial', traceback.format_exc()))
        finally:
            first_done.set()

    def check_stop(self):
        if self.stopping.is_set():
            raise KeyboardInterrupt

    def execute(self):
        first_done = threading.Event()
        self.queue = threading.Thread(target=self.serial_queue, args=(list(self.current.serial), first_done),
                                      name='fila-serial')
        self.queue.start()
        while not first_done.wait(POLL_SECONDS):
            self.check_stop()
        self.check_stop()
        self.executor = ThreadPoolExecutor(max_workers=self.current.workers, thread_name_prefix='pool')
        self.futures = [self.executor.submit(self.one, name, 'pool') for name in self.current.pool]
        pending = set(self.futures)
        while pending:
            _, pending = wait(pending, timeout=POLL_SECONDS)
            self.check_stop()
        while self.queue.is_alive():
            self.queue.join(POLL_SECONDS)
            self.check_stop()
        self.executor.shutdown(wait=False)
        for future in self.futures:
            error = future.exception()
            if error is not None:
                self.errors.append(('pool', ''.join(traceback.format_exception(error))))
        self.check_stop()
        return [self.outcomes[name] for name, _ in self.current.entries() if name in self.outcomes]

    def abort(self):
        """Interrupção: nada mais começa, todo filho vivo morre com a árvore e as threads têm um prazo para
        terminar. Um KeyboardInterrupt no meio não deixa filho vivo: a matança recomeça até acabar. Devolve quantos
        módulos a interrupção matou, pelo runner ou pelo próprio evento do console."""
        self.stopping.set()
        killed = set()
        while True:
            try:
                if self.executor is not None:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                killed |= self.live.kill_all()
                self.join_threads()
                break
            except KeyboardInterrupt:
                continue
        with self.lock:
            return len(killed | self.interrupted)

    def join_threads(self):
        deadline = time.monotonic() + 2 * KILL_WAIT_SECONDS + 5
        wait(self.futures, timeout=max(0.0, deadline - time.monotonic()))
        if self.queue is not None:
            self.queue.join(max(0.0, deadline - time.monotonic()))


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
    """O comando para rodar o módulo sozinho, com o caminho absoluto da pasta (os filhos rodam da raiz do
    repositório; um caminho relativo só valeria de lá)."""
    return subprocess.list2cmdline(['python', '-m', 'unittest', 'discover', '-s', str(current.tests_dir),
                                    '-p', f'{name}.py'])


def print_total(outcomes, wall):
    ran = sum(outcome.ran or 0 for outcome in counted(outcomes))
    print('-' * 70)
    print(f'Ran {ran} test{"" if ran == 1 else "s"} in {wall:.3f}s')
    print()
    problems = [outcome for outcome in outcomes if outcome.problem is not None]
    if problems:
        print('Infraestrutura: ' + '; '.join(f'{outcome.name} ({outcome.problem})' for outcome in problems))
    print(summary_line(outcomes), flush=True)


def print_internal_errors(errors):
    for where, text in errors:
        print('=' * 70)
        print(f'Erro interno do runner ({where}): infraestrutura; traceback')
        print('-' * 70)
        print(text.rstrip('\n'))
        print()


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
    run = Run(current, root, options.module_timeout)
    install_interrupt_handlers(run.stopping)
    started_at = datetime.now().astimezone()
    started = time.monotonic()
    try:  # do cabeçalho ao relatório: um Ctrl+C em qualquer ponto passa pela interrupção tratada
        print_header(current)
        outcomes = run.execute()
        wall = time.monotonic() - started
        print()
        print_failures(current, outcomes)
        print_internal_errors(run.errors)
        print_total(outcomes, wall)
        code = 2 if run.errors else exit_code(outcomes)
        if options.report is not None:
            data = report_data(current, options, head, started_at, wall, outcomes, code)
            if not write_report(options.report, data):
                return max(code, 2)  # sem a evidência pedida, a rodada é um erro de infraestrutura
        return code
    except KeyboardInterrupt:
        return interrupted(run, current, options, head, started_at, started)


def interrupted(run, current, options, head, started_at, started):
    """Mata o que está vivo e relata só os módulos que terminaram antes da interrupção; sai com 130."""
    killed = run.abort()
    with run.lock:
        finished = [run.outcomes[name] for name, _ in current.entries() if name in run.outcomes]
    print(f'\nInterrompido: {killed} módulo{"" if killed == 1 else "s"} morto{"" if killed == 1 else "s"} '
          f'(com as árvores de processos); nada foi somado.', flush=True)
    if options.report is not None:
        write_report(options.report, report_data(current, options, head, started_at, time.monotonic() - started,
                                                 finished, INTERRUPTED))
    return INTERRUPTED


def install_interrupt_handlers(stopping):
    """Ctrl+C (SIGINT) e Ctrl+Break (SIGBREAK, só Windows) ligam `stopping` antes de virar KeyboardInterrupt na
    thread principal: as threads param de começar módulos na hora. Com a interrupção já em curso, um novo sinal é
    ignorado, para não cortar a limpeza nem a mensagem final no meio."""
    def interrupt(signum, frame):
        if stopping.is_set():
            return
        stopping.set()
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, interrupt)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, interrupt)


if __name__ == '__main__':
    sys.exit(main())
