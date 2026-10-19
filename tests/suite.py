"""Runner paralelo da suíte de testes do Frontlights (issue 27, S1, S2 e S3; `--impact` das issues 52, S4, e 57, S1;
`--skip-covered` da issue 57, S2).

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

`--impact <base>` é a suíte por impacto (issue 52, S4; issue 57, S1): roda, em todos os módulos, só o que o diff
toca. Os mudados são o diff commitado `<base>...HEAD` MAIS a árvore de trabalho (no índice, fora dele e não
rastreados), para que uma edição sem commit não fique de fora. "Toca" é a seleção do `tests/pre_commit.py`
(`selected`): o módulo mudou (roda inteiro), cita o nome de um arquivo mudado ou importa um script mudado (roda só
as classes que citam ou importam, com `-k '*.<Classe>.*'`, ou inteiro quando isso está fora de uma classe). O
`test_single_source` roda sempre, inteiro. Uma mudança no `tests/suite.py` ou no `tests/pre_commit.py` escolhe todos
os módulos inteiros. O que não foi escolhido não roda. Os escolhidos rodam com `FRONTLIGHTS_SUITE=rapida`, menos os
pesados da lista HEAVY, que rodam SEM a variável na fila serial (fila `impacto`), na ordem da lista SERIAL. O
relatório ganha `mode: "impact"`, `base`, `base_commit`, `changed`, `impact` (por módulo: `name`, `selected`,
`reason`, `classes`), `ran` (o que rodou: o nome de cada módulo inteiro e `<módulo>.<Classe>` de cada classe) e
`complete` (os módulos que rodaram inteiros), depois das chaves de sempre; o `--list` mostra o plano: os módulos,
inteiros ou com as classes, e por quê. Base que o Git não resolve: sai com 2 sem rodar nada.

`--skip-covered <arquivo>` é o complemento da suíte (issue 57, S2): roda todos os módulos da pasta, inteiros e SEM
a variável (a semântica da suíte inteira, com os pesados de verdade), menos os listados em `complete` do arquivo, o
mesmo `complete` que o relatório do `--impact` grava. Os seriais vão na fila serial, na ordem da lista SERIAL; os
demais, no pool. O arquivo é `{"complete": [ids]}`: um objeto JSON só com a chave `complete`, uma lista de textos
não vazios, sem NUL e sem repetição, em UTF-8 (com ou sem BOM) e de até COVERED_LIMIT bytes. Um id é o nome de um
módulo (`test_x`); o que não nomeia módulo da pasta sai como desconhecido e não muda mais nada. Arquivo ausente,
ilegível ou inválido, e o `--skip-covered` junto do `--impact`, saem com 2 sem rodar nada. O relatório ganha
`mode: "complement"`, `skipped_covered` (os pulados, em ordem) e `unknown_covered`; o `--list` mostra os que rodam
e os pulados por cobertos.

Uso: python tests/suite.py [--tests-dir PASTA] [--serial a,b,c] [--workers N] [--module-timeout S]
                           [--report ARQUIVO] [--list] [--impact BASE | --skip-covered ARQUIVO]
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

# Os módulos pesados: os que o `load_tests` pula com FRONTLIGHTS_SUITE=rapida. No `--impact`, cada um que o diff
# toca roda sem a variável, na fila serial.
HEAVY = ('test_serve_ports', 'test_checks_integration', 'test_serve_preview')
# Os arquivos da pasta dos testes cuja mudança escolhe todos os módulos inteiros no `--impact`: o runner e a seleção.
RUNNER_FILES = ('suite.py', 'pre_commit.py')
SINGLE_SOURCE = 'test_single_source'  # o teste de fonte única: no `--impact`, roda sempre, inteiro
IMPACT = 'impacto'  # a fila dos pesados que rodam sem a variável no `--impact`
COVERED_LIMIT = 256 * 1024  # o tamanho máximo, em bytes, do arquivo do `--skip-covered`

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
    parser.add_argument('--impact', metavar='BASE', default=None,
                        help='suíte por impacto: só os módulos e as classes que o diff BASE...HEAD mais a árvore de '
                             'trabalho toca, mais o test_single_source; os pesados sem a variável')
    parser.add_argument('--skip-covered', metavar='ARQUIVO', type=Path, default=None,
                        help='complemento da suíte: todos os módulos inteiros e sem a variável, menos os listados '
                             'em "complete" do arquivo JSON')
    return parser.parse_args(argv)


# --- plano --------------------------------------------------------------------------------------------------

class Plan:
    """Os módulos que rodariam: a fila serial na ordem dada e o pool em ordem alfabética. No `--impact`, `impact`
    traz a escolha de cada módulo (Impact) e só os escolhidos rodam: os seriais na fila serial, na ordem dela, com
    os pesados sem a variável (fila `impacto`); os demais no pool. O primeiro da fila roda sozinho, como na suíte
    inteira. Um pesado escolhido fora da lista serial vai para o fim da fila. No `--skip-covered`, `covered` traz
    os cobertos (Covered), que ficam de fora das duas filas."""

    def __init__(self, tests_dir, shown_dir, serial, pool, workers, impact=None, covered=None):
        self.tests_dir = tests_dir
        self.shown_dir = shown_dir
        self.serial = serial
        self.pool = pool
        self.workers = workers
        self.impact = impact
        self.covered = covered

    def skipped(self):
        return set(self.covered.skipped) if self.covered is not None else set()

    def chosen(self):
        """{módulo: classes, ou None para o módulo inteiro} dos escolhidos no `--impact`; None fora dele."""
        if self.impact is None:
            return None
        return {item['name']: item['classes'] for item in self.impact.records if item['selected']}

    def classes(self, name):
        """As classes que o módulo roda, ou None quando ele roda inteiro."""
        return (self.chosen() or {}).get(name)

    def queue(self):
        chosen = self.chosen()
        if chosen is None:
            return [(name, 'serial') for name in self.serial if name not in self.skipped()]
        entries = [(name, IMPACT if name in HEAVY else 'serial') for name in self.serial if name in chosen]
        return entries + [(name, IMPACT) for name in chosen if name in HEAVY and name not in self.serial]

    def pool_names(self):
        chosen = self.chosen()
        if chosen is None:
            return [name for name in self.pool if name not in self.skipped()]
        return [name for name in self.pool if name in chosen and name not in HEAVY]

    def entries(self):
        return self.queue() + [(name, 'pool') for name in self.pool_names()]

    def command(self, name):
        """O comando do filho: o módulo inteiro, ou só as classes escolhidas (o `-k` do `tests/pre_commit.py`)."""
        classes = self.classes(name)
        if not classes:
            return command_for(self.tests_dir, name)
        import pre_commit  # tardio: o pre_commit importa este módulo
        return pre_commit.command(self.tests_dir, name, classes)


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


def classes_suffix(classes):
    return f'  ({", ".join(classes)})' if classes else ''


def print_list(current):
    for order, (name, kind) in enumerate(current.entries(), start=1):
        print(f'{order:>3}  {kind:<7}  {name}{classes_suffix(current.classes(name))}')
    if current.impact is not None:
        print()
        print_impact(current.impact)
    if current.covered is not None:
        print()
        print_covered(current.covered)


# --- suíte por impacto (--impact) ---------------------------------------------------------------------------

class ImpactError(Exception):
    pass


class Impact:
    """A escolha do `--impact`: a base pedida e o commit dela, os arquivos mudados e, por módulo da pasta, se roda,
    inteiro ou em quais classes, e por quê."""

    def __init__(self, base, base_commit, changed, records):
        self.base = base
        self.base_commit = base_commit
        self.changed = changed
        self.records = records


def impact_selection(tests_dir, base):
    """O que o diff toca, em todos os módulos da pasta. Mudados: o diff commitado `git diff --name-only --no-renames
    <base>...HEAD` (desde o ponto em que o HEAD saiu da base) MAIS a árvore de trabalho (no índice, fora dele e não
    rastreados, como o `tests/pre_commit.py` lista), para que uma edição ainda sem commit não fique de fora. "Toca" é
    a seleção do `tests/pre_commit.py` (`selected`): o módulo mudou (inteiro), ou cita o nome de um arquivo mudado ou
    importa um script mudado (as classes que citam ou importam, ou inteiro quando é fora delas). O SINGLE_SOURCE roda
    sempre, inteiro. Uma mudança no runner ou na seleção (RUNNER_FILES, na pasta dos testes) escolhe todos os
    módulos inteiros. Levanta ImpactError quando o Git não resolve a base ou falha."""
    import pre_commit  # tardio: o pre_commit importa este módulo
    failures = (pre_commit.GitError, OSError, subprocess.SubprocessError)
    try:
        root = Path(pre_commit.git(tests_dir, 'rev-parse', '--show-toplevel').strip()).resolve()
    except failures as error:
        raise ImpactError(f'--impact: a pasta {tests_dir} não está num repositório Git ({error}). '
                          'Nada foi rodado.') from error
    try:
        base_commit = pre_commit.git(root, 'rev-parse', '--verify', '--quiet', f'{base}^{{commit}}').strip()
    except failures as error:
        raise ImpactError(f'--impact: o Git não resolve a base {base!r} em {root}. Nada foi rodado.') from error
    try:
        committed = [path for path in pre_commit.git(root, 'diff', '--name-only', '--no-renames', '-z',
                                                     f'{base_commit}...HEAD').split('\0') if path]
        working = pre_commit.changed_files(root)
    except failures as error:
        raise ImpactError(f'--impact: o Git falhou ao comparar {base!r} com o HEAD ({error}). '
                          'Nada foi rodado.') from error
    changed = sorted(set(committed) | set(working))
    chosen = dict(pre_commit.selected(tests_dir, changed))
    runner = {(tests_dir / name).resolve() for name in RUNNER_FILES}
    runner_changed = [path for path in changed if (root / path).resolve() in runner]
    names = {Path(path).name for path in changed}
    always = 'o teste de fonte única roda sempre, inteiro'
    records = []
    for module in sorted(path for path in tests_dir.glob('test_*.py') if path.is_file()):
        name, classes = module.stem, None
        if runner_changed:
            selected, reason = True, f'o runner ou a seleção mudou ({", ".join(runner_changed)})'
        elif name in chosen:
            selected, classes = True, chosen[name]
            if module.name in names:
                reason = 'o módulo mudou'
            else:
                source = module.read_text(encoding='utf-8', errors='replace')
                cited = [path for path in changed
                         if Path(path).name in source or (path.endswith('.py') and Path(path).stem in source)]
                where = 'as classes citam ou importam' if classes else 'fora de uma classe, cita ou importa'
                reason = f'{where} um arquivo mudado ({", ".join(cited)})'
            if name == SINGLE_SOURCE and classes:
                classes, reason = None, f'{reason}; {always}'
        elif name == SINGLE_SOURCE:
            selected, reason = True, always
        else:
            selected, reason = False, 'o diff não toca o que ele testa'
        records.append({'name': name, 'selected': selected, 'reason': reason, 'classes': classes})
    return Impact(base, base_commit, changed, records)


def print_impact(impact):
    chosen = sum(1 for item in impact.records if item['selected'])
    print(f'Impacto: base {impact.base} ({impact.base_commit[:12]}), {len(impact.changed)} arquivo(s) mudado(s); '
          f'{chosen} de {len(impact.records)} módulo(s) escolhido(s)')
    for item in impact.records:
        if not item['selected']:
            verdict = 'fica de fora'
        else:
            verdict = f'classes {", ".join(item["classes"])}' if item['classes'] else 'inteiro'
            if item['name'] in HEAVY:
                verdict += ', sem a variável'
        print(f'  {item["name"]}: {verdict} ({item["reason"]})')


# --- complemento da suíte (--skip-covered) ------------------------------------------------------------------

class CoveredError(Exception):
    pass


class Covered:
    """Os cobertos do `--skip-covered`: os módulos da pasta que ficam de fora e os ids que não nomeiam módulo
    nenhum dela, ambos em ordem."""

    def __init__(self, skipped, unknown):
        self.skipped = skipped
        self.unknown = unknown


def unique_keys(pairs):
    """O `object_pairs_hook` do arquivo dos cobertos: uma chave repetida é arquivo inválido, não a última vence."""
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise ValueError(f'chave repetida: {", ".join(repeated)}')
    return dict(pairs)


def covered_selection(tests_dir, path):
    """Lê o arquivo `{"complete": [ids]}` (UTF-8 com ou sem BOM, até COVERED_LIMIT bytes) e devolve o Covered.
    Levanta CoveredError quando o arquivo falta, não se lê ou não tem exatamente esse formato."""
    def refuse(why):
        return CoveredError(f'--skip-covered: o arquivo {path} {why}. Nada foi rodado.')
    try:
        with open(path, 'rb') as stream:
            raw = stream.read(COVERED_LIMIT + 1)
    except OSError as error:
        raise refuse(f'não pôde ser lido ({error})') from error
    if len(raw) > COVERED_LIMIT:
        raise refuse(f'passa de {COVERED_LIMIT} bytes')
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_keys)
    except UnicodeDecodeError as error:
        raise refuse(f'não está em UTF-8 ({error})') from error
    except ValueError as error:
        raise refuse(f'não é um JSON válido ({error})') from error
    if not isinstance(data, dict) or set(data) != {'complete'}:
        raise refuse('precisa ser um objeto JSON só com a chave "complete"')
    ids = data['complete']
    if not isinstance(ids, list):
        raise refuse('precisa ter em "complete" uma lista')
    for item in ids:
        if not isinstance(item, str) or not item or '\0' in item:
            raise refuse(f'tem em "complete" um id que não é um texto não vazio e sem NUL ({item!r})')
    repeated = sorted({item for item in ids if ids.count(item) > 1})
    if repeated:
        raise refuse(f'repete em "complete" o id {", ".join(repeated)}')
    found = {module.stem for module in tests_dir.glob('test_*.py') if module.is_file()}
    return Covered(sorted(set(ids) & found), sorted(set(ids) - found))


def print_covered(covered):
    print(f'Pulados por cobertos: {", ".join(covered.skipped) if covered.skipped else "(nenhum)"}')
    if covered.unknown:
        print(f'Ids desconhecidos: {", ".join(covered.unknown)}')


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


def run_module(current, name, kind, root, timeout, live, stopping, command=None, env=None):
    """Roda um módulo como processo filho e devolve o Outcome, ou None quando a rodada foi interrompida. O filho
    roda em grupo próprio, que o livra só do Ctrl+C do console: o Ctrl+Break do teclado chega a todos os processos
    do console, e o filho morre com 0xC000013A (STATUS_CONTROL_C_EXIT) antes de a thread principal reagir; esse
    código liga `stopping` e conta como interrupção, não como erro do módulo. Passado o prazo, mata a árvore e
    guarda a saída parcial; se a árvore não morrer, é erro de infraestrutura. `live` é o registro dos filhos vivos,
    para o abort; `stopping` encerra a espera quando a suíte foi interrompida. `command` troca o comando padrão
    (`command_for`), como o `tests/pre_commit.py` faz para rodar só algumas classes com `-k`; `env` troca o
    ambiente dos filhos (o padrão é o deste processo), como o `--impact` faz para rodar os pesados sem a variável."""
    started = time.monotonic()
    process = subprocess.Popen(command or command_for(current.tests_dir, name), cwd=str(root),
                               env=dict(os.environ) if env is None else env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    reader = Reader(process.stdout)
    reader.start()
    live.add((name, kind), process)
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
        live.remove((name, kind))
    if interrupted or process.returncode == STATUS_CONTROL_C_EXIT:
        stopping.set()
        return None
    reader.join(KILL_WAIT_SECONDS)
    output = decode(bytes(reader.buffer))
    return Outcome(name, kind, time.monotonic() - started, process.returncode, output, timed_out, problem)


class Live:
    """Os filhos vivos, por (nome, fila), sob trava: o abort mata cada um com a árvore."""

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
        """Mata a árvore de cada filho ainda vivo; devolve as chaves (nome, fila) dos que ela matou."""
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
        self.outcomes = {}  # por (nome, fila)
        self.interrupted = set()  # (nome, fila) dos que a interrupção matou (pelo runner ou pelo próprio evento)
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
        env = without_variable() if kind == IMPACT else None
        try:
            outcome = run_module(self.current, name, kind, self.root, self.timeout, self.live, self.stopping,
                                 command=self.current.command(name), env=env)
        except Exception as error:
            outcome = Outcome(name, kind, time.monotonic() - started, None, traceback.format_exc(),
                              problem=f'erro interno do runner ({type(error).__name__}: {error})')
        with self.lock:
            if outcome is None:
                self.interrupted.add((name, kind))
            elif not self.stopping.is_set():
                self.outcomes[(name, kind)] = outcome
                print(module_line(outcome) + classes_suffix(self.current.classes(name)), flush=True)

    def serial_queue(self, entries, first_done):
        try:
            for name, kind in entries:
                if self.stopping.is_set():
                    break
                self.one(name, kind)
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
        self.queue = threading.Thread(target=self.serial_queue, args=(self.current.queue(), first_done),
                                      name='fila-serial')
        self.queue.start()
        while not first_done.wait(POLL_SECONDS):
            self.check_stop()
        self.check_stop()
        self.executor = ThreadPoolExecutor(max_workers=self.current.workers, thread_name_prefix='pool')
        self.futures = [self.executor.submit(self.one, name, 'pool') for name in self.current.pool_names()]
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
        return [self.outcomes[key] for key in self.current.entries() if key in self.outcomes]

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

def without_variable():
    """O ambiente deste processo sem a variável: o dos pesados que o `--impact` roda de verdade."""
    return {key: value for key, value in os.environ.items() if key != VARIABLE}


def print_header(current):
    value = os.environ.get(VARIABLE)
    print('Suíte do Frontlights em paralelo')
    resolved = f' ({current.tests_dir})' if str(current.tests_dir) != current.shown_dir else ''
    print(f'Pasta: {current.shown_dir}{resolved}')
    print(f'{VARIABLE}={value}' if value is not None else f'{VARIABLE} (sem variável)')
    print(f'Trabalhadores: {current.workers}')
    queue = [name for name, _ in current.queue()]
    pool = current.pool_names()
    print(f'Fila serial: {", ".join(queue) if queue else "(nenhuma)"}')
    print(f'Módulos: {len(queue) + len(pool)} ({len(queue)} seriais, {len(pool)} no pool)')
    if current.impact is not None:
        print_impact(current.impact)
    if current.covered is not None:
        print_covered(current.covered)
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
    """O comando para rodar o módulo sozinho (no `--impact`, só as classes escolhidas), com o caminho absoluto da
    pasta (os filhos rodam da raiz do repositório; um caminho relativo só valeria de lá)."""
    return subprocess.list2cmdline(['python', *current.command(name)[1:]])


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
    data = {
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
    if current.impact is not None:  # chaves só do `--impact`, depois das de sempre
        data['mode'] = 'impact'
        data['base'] = current.impact.base
        data['base_commit'] = current.impact.base_commit
        data['changed'] = current.impact.changed
        data['impact'] = [dict(item) for item in current.impact.records]
        data['ran'], data['complete'] = ran_ids(current, outcomes)
    if current.covered is not None:  # chaves só do `--skip-covered`, depois das de sempre
        data['mode'] = 'complement'
        data['skipped_covered'] = list(current.covered.skipped)
        data['unknown_covered'] = list(current.covered.unknown)
    return data


def ran_ids(current, outcomes):
    """O que rodou no `--impact`: em `ran`, o nome de cada módulo que rodou inteiro e `<módulo>.<Classe>` de cada
    classe que rodou sem o resto do módulo; em `complete`, só os módulos inteiros. Um erro de infraestrutura (prazo
    estourado, módulo que não importou) não rodou de verdade e fica de fora dos dois."""
    ran, complete = [], []
    for outcome in counted(outcomes):
        classes = current.classes(outcome.name)
        if classes:
            ran += [f'{outcome.name}.{cls}' for cls in classes]
        else:
            ran.append(outcome.name)
            complete.append(outcome.name)
    return ran, complete


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
    if options.impact is not None and options.skip_covered is not None:
        print('--skip-covered não combina com --impact: o complemento roda o que o impacto não rodou inteiro. '
              'Nada foi rodado.', file=sys.stderr)
        return 2
    try:
        current = plan(options)
        if options.impact is not None:
            current.impact = impact_selection(current.tests_dir, options.impact)
        if options.skip_covered is not None:
            current.covered = covered_selection(current.tests_dir, options.skip_covered)
    except (SystemExit, ImpactError, CoveredError) as error:
        print(error, file=sys.stderr)
        return 2
    if options.list:
        print_list(current)
        return 0
    if current.impact is not None:
        os.environ[VARIABLE] = 'rapida'  # os escolhidos rodam com ela; os pesados escolhidos, sem ela
    if current.covered is not None:
        os.environ.pop(VARIABLE, None)  # o complemento é a suíte inteira: todos sem a variável
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
        finished = [run.outcomes[key] for key in current.entries() if key in run.outcomes]
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
