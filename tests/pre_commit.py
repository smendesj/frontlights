"""Verificação de antes do commit no repositório do Frontlights (ferramenta de quem desenvolve; fora da skill).

Roda em segundos o que pega um commit vermelho por erro de script ou de texto, sem substituir a suíte inteira:

1. os arquivos mudados em relação ao HEAD: no índice, fora dele e não rastreados (`git status --porcelain -z
   --untracked-files=all`; um renomeado conta pelo nome novo);
2. `python -m compileall -q skills/frontlights/scripts tests`;
3. os módulos `tests/test_*.py` que estão entre os mudados (inteiros) e os que citam o nome de um arquivo mudado
   ou importam um script mudado (`import roadmap_sync`): desses, só as classes de teste que citam ou importam
   (`-k '*.<Classe>.*'`), ou o módulo inteiro quando isso está fora de uma classe com métodos `test*` (um import
   no topo, uma constante, um helper, uma classe base sem testes);
4. cada um como no `tests/suite.py` (o `run_module` dele: `python -m unittest discover -s tests -p <módulo>.py`,
   que respeita o `load_tests` da suíte rápida), com `FRONTLIGHTS_SUITE=rapida`, do menor arquivo para o maior,
   num pool de `--workers`, sob um prazo TOTAL (`--timeout`, 20 s): no prazo, o que está rodando morre com a
   árvore de processos e o que não começou fica de fora; os dois ficam para a suíte inteira, sem contar como falha.

Nenhum hook o roda: o `CLAUDE.md` manda rodá-lo antes de cada commit. Ele confere a árvore de trabalho, não o
índice, e não substitui a suíte inteira, obrigatória antes da revisão independente e do merge na main local.
Limite conhecido: uma classe que herda os testes de uma classe base que cita o arquivo não é escolhida pelo `-k`
da base. Código 0: verde, inclusive com o que ficou para a suíte; 1: o compileall ou um módulo falhou (ou não
importou); 2: erro de uso ou do Git; 130: interrompido (Ctrl+C). Só biblioteca padrão; só Windows, como o
`tests/suite.py`.

Uso: python tests/pre_commit.py [--timeout S] [--workers N] [--root PASTA]
"""
import argparse
import ast
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from types import SimpleNamespace

import suite

DEFAULT_TIMEOUT = 20
DEFAULT_WORKERS = 4
COMPILED = ('skills/frontlights/scripts', 'tests')
LEFT = 'fica para a suíte inteira'


def parse(argv):
    parser = argparse.ArgumentParser(description='Verificação de antes do commit: compileall e os testes que as '
                                                 'mudanças tocam ou citam, sob um prazo total.')
    parser.add_argument('--timeout', type=suite.positive_float, default=DEFAULT_TIMEOUT,
                        help=f'prazo total dos módulos, em segundos (padrão: {DEFAULT_TIMEOUT})')
    parser.add_argument('--workers', type=suite.positive_int, default=DEFAULT_WORKERS,
                        help=f'módulos ao mesmo tempo (padrão: {DEFAULT_WORKERS})')
    parser.add_argument('--root', type=suite.existing_dir, default=Path(__file__).resolve().parents[1],
                        help='o repositório (padrão: o deste script)')
    return parser.parse_args(argv)


class GitError(Exception):
    pass


def git(root, *args):
    done = subprocess.run(['git', '-C', str(root), *args], capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    if done.returncode != 0:
        raise GitError(suite.decode(done.stderr).strip() or f'git {" ".join(args)} saiu com {done.returncode}')
    return suite.decode(done.stdout)


def changed_files(root):
    """Os caminhos mudados em relação ao HEAD, relativos à raiz, com `/`. No `-z`, um renomeado ou copiado traz o
    nome novo e, no campo seguinte, o antigo, que fica de fora."""
    fields = git(root, 'status', '--porcelain', '-z', '--untracked-files=all').split('\0')
    paths = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4:
            continue
        status, path = field[:2], field[3:]
        paths.append(path)
        if 'R' in status or 'C' in status:
            index += 1
    return paths


def uses(node, stems):
    """Se o nó importa um script mudado pelo nome do módulo (`import roadmap_sync`, `from closeout import x`) ou o
    carrega por uma string igual a ele (`importlib.import_module('serve')`): a forma como os testes de unidade
    chegam aos scripts sem escrever o nome do arquivo."""
    for item in ast.walk(node):
        if isinstance(item, ast.Import) and any(alias.name.split('.')[0] in stems for alias in item.names):
            return True
        if isinstance(item, ast.ImportFrom):
            if item.module and item.module.split('.')[0] in stems:
                return True
            if not item.module and any(alias.name in stems for alias in item.names):
                return True
        if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value in stems:
            return True
    return False


def citing_classes(source, names, stems):
    """As classes de teste (com métodos `test*`) que citam um dos nomes ou importam um dos scripts mudados, ou None
    quando o módulo inteiro tem de rodar: a citação ou o import aparece fora delas (o docstring do módulo não conta)
    ou o arquivo não é Python válido. Lista vazia: nada no módulo cita nem importa."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    classes = []
    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, 'value', None), ast.Constant):
            continue  # o docstring do módulo descreve, não lê
        segment = ast.get_source_segment(source, node) or ''
        if not (any(name in segment for name in names) or uses(node, stems)):
            continue
        has_tests = isinstance(node, ast.ClassDef) and any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith('test')
            for item in node.body)
        if not has_tests:
            return None
        classes.append(node.name)
    return classes


def selected(tests_dir, changed):
    """[(módulo, classes ou None)], do menor arquivo para o maior: o tamanho é a estimativa barata do tempo (os de
    texto são pequenos e levam 1-2 s; os que sobem processos e repositórios são grandes), e assim os pesados não
    ocupam o pool enquanto os leves esperam. Um módulo mudado roda inteiro; um que cita ou importa roda as classes
    que citam ou importam (ou inteiro, quando é fora delas); um que não cita nem importa fica de fora."""
    names = {Path(path).name for path in changed}
    stems = {Path(path).stem for path in changed if path.endswith('.py')}
    chosen = []
    for path in tests_dir.glob('test_*.py'):
        source = path.read_text(encoding='utf-8', errors='replace')
        if path.name in names:
            chosen.append((path.stat().st_size, path.stem, None))
        elif any(word in source for word in names | stems):
            classes = citing_classes(source, names, stems)
            if classes != []:
                chosen.append((path.stat().st_size, path.stem, classes))
    return [(name, classes) for _, name, classes in sorted(chosen)]


def command(tests_dir, name, classes):
    argv = suite.command_for(tests_dir, name)
    for cls in classes or ():
        argv += ['-k', f'*.{cls}.*']  # com `*`, o unittest casa o id inteiro, não um pedaço do nome
    return argv


def compile_all(root):
    """O compileall dos scripts e dos testes; devolve (passou, saída)."""
    targets = [target for target in COMPILED if (root / target).is_dir()]
    done = subprocess.run([sys.executable, '-m', 'compileall', '-q', *targets], cwd=str(root), capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=300)
    return done.returncode == 0, suite.decode(done.stdout + done.stderr).strip()


class Round:
    """Os módulos sob um relógio só: cada um começa com o que resta do prazo total e, depois dele, nenhum começa."""

    def __init__(self, root, chosen, timeout, workers):
        self.root = root
        self.current = SimpleNamespace(tests_dir=root / 'tests')
        self.chosen = chosen
        self.workers = workers
        self.deadline = time.monotonic() + timeout
        self.live = suite.Live()
        self.stopping = threading.Event()
        self.results = {}  # só os que começaram; None é o que a interrupção cortou
        self.printing = threading.Lock()

    def one(self, name, classes):
        started = time.monotonic()
        remaining = self.deadline - started
        if remaining <= 0 or self.stopping.is_set():
            return
        try:
            outcome = suite.run_module(self.current, name, 'commit', self.root, remaining, self.live, self.stopping,
                                       command=command(self.current.tests_dir, name, classes))
        except Exception as error:  # um erro aqui é vermelho, nunca um módulo que "não começou"
            outcome = suite.Outcome(name, 'commit', time.monotonic() - started, None, '',
                                    problem=f'erro interno: {type(error).__name__}: {error}')
        self.results[name] = outcome
        self.say(line_for(name, classes, outcome))

    def say(self, text):
        with self.printing:
            print(text, flush=True)

    def execute(self):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            pending = {pool.submit(self.one, name, classes) for name, classes in self.chosen}
            try:
                while pending:  # a thread principal nunca bloqueia sem prazo: é assim que o Ctrl+C chega a ela
                    _, pending = wait(pending, timeout=suite.POLL_SECONDS)
                    if self.stopping.is_set():  # o Ctrl+Break pode ligar `stopping` na thread de trabalho primeiro
                        raise KeyboardInterrupt
            except KeyboardInterrupt:
                self.stopping.set()
                self.live.kill_all()
                raise
        for name, classes in self.chosen:
            if name not in self.results:
                self.say(f'[commit] {name:<34}       -   não começou no prazo; {LEFT}{suffix(classes)}')
        return [(name, classes, self.results.get(name)) for name, classes in self.chosen]


def suffix(classes):
    return f'  ({", ".join(classes)})' if classes else ''


def line_for(name, classes, outcome):
    if outcome is None:
        return f'[commit] {name:<34} interrompido{suffix(classes)}'
    if outcome.timed_out is not None:
        extra = f' ({outcome.problem})' if 'matar' in (outcome.problem or '') else ''
        return (f'[commit] {name:<34} {outcome.wall:7.1f}s  prazo total esgotado, árvore morta; {LEFT}{extra}'
                f'{suffix(classes)}')
    return suite.module_line(outcome) + suffix(classes)


def failed(outcome):
    return outcome is not None and outcome.timed_out is None and not outcome.passed


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if sys.platform != 'win32':
        print(f'tests/pre_commit.py só roda no Windows (sys.platform={sys.platform}), como o tests/suite.py.',
              file=sys.stderr)
        return 2
    options = parse(sys.argv[1:] if argv is None else argv)
    try:
        root = Path(git(options.root, 'rev-parse', '--show-toplevel').strip()).resolve()
        changed = changed_files(root)
    except (GitError, OSError, subprocess.SubprocessError) as error:
        print(f'Git: {error}', file=sys.stderr)
        return 2
    if not changed:
        print('Nenhum arquivo mudado em relação ao HEAD: nada a conferir.')
        return 0
    print(f'Mudados ({len(changed)}): {", ".join(changed)}')
    started = time.monotonic()
    compiled, compile_output = compile_all(root)
    print('compileall: ' + ('ok' if compiled else 'FALHOU'), flush=True)
    if not compiled:
        print(compile_output)
    chosen = selected(root / 'tests', changed)
    results = []
    if not chosen:
        print('Nenhum teste é tocado pelas mudanças.')
    else:
        print(f'Módulos ({len(chosen)}), com FRONTLIGHTS_SUITE=rapida e prazo total de {options.timeout:g} s:',
              flush=True)
        os.environ[suite.VARIABLE] = 'rapida'  # o run_module repassa o ambiente deste processo aos filhos
        current = Round(root, chosen, options.timeout, options.workers)
        suite.install_interrupt_handlers(current.stopping)
        try:
            results = current.execute()
        except KeyboardInterrupt:
            print('\nInterrompido: os módulos vivos foram mortos com as árvores de processos.', flush=True)
            return suite.INTERRUPTED
    red = [(name, classes, outcome) for name, classes, outcome in results if failed(outcome)]
    for name, classes, outcome in red:
        print('=' * 70)
        print(f'{name}{suffix(classes)}: ' + (f'infraestrutura: {outcome.problem}' if outcome.problem
                                                else f'código de saída {outcome.returncode}'))
        print('-' * 70)
        print(outcome.output.rstrip('\n'))
        print(f'Rode sozinho: {subprocess.list2cmdline(["python", *command(root / "tests", name, classes)[1:]])}')
    left = sum(1 for _, _, outcome in results if outcome is None or outcome.timed_out is not None)
    verdict = 'FALHOU' if red or not compiled else 'ok'
    print(f'Verificação de antes do commit: {verdict} em {time.monotonic() - started:.1f} s; '
          f'{len(results) - left - len(red)} módulo(s) verde(s), {len(red)} vermelho(s), {left} para a suíte '
          'inteira.')
    return 1 if red or not compiled else 0


if __name__ == '__main__':
    sys.exit(main())
