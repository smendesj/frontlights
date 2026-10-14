"""Runner paralelo da suíte com fila serial, prazo por módulo e erro de infraestrutura (issue 27, S1 e S2).

Seams: a linha de comando de `tests/suite.py` (`--tests-dir`, `--serial`, `--workers`, `--module-timeout`, `--list`),
observada por subprocess sobre uma pasta temporária de módulos falsos que o próprio teste escreve: o que sai no
stdout (cabeçalho, uma linha por módulo, saída completa dos que falharam, total no formato do unittest), o código
de saída, os instantes gravados pelos módulos marcadores (fila serial e limite de trabalhadores) e a variável
`FRONTLIGHTS_SUITE` repassada aos filhos. S2: o prazo por módulo (`--module-timeout`) com a árvore morta e a saída
parcial, os erros de infraestrutura (módulo que não importa, filho sem a linha `Ran`, crash) com saída 2, e o
Ctrl+Break que mata os filhos (PIDs gravados pelos módulos falsos, conferidos depois). S3: o relatório JSON de
`--report <arquivo>` (topo, módulos, totais, prazo estourado, pasta inexistente, interrupção) e os manifestos de
texto (README, protocolo, referência da etapa 6, `docs/acceptance.md` e o workflow da CI). Nada aqui roda a suíte
real: sobre a pasta `tests/` só se usa `--list`.
"""
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime
from pathlib import Path

ROOT =Path(__file__).resolve().parents[1]
SUITE = ROOT / 'tests' / 'suite.py'
VARIABLE = 'FRONTLIGHTS_SUITE'
SERIAL_REAL = ('test_serve_ports', 'test_checks_integration', 'test_serve', 'test_browser_app_example', 'test_checks')

PASSES = """
import unittest


class Passa(unittest.TestCase):
    def test_um(self):
        self.assertTrue(True)

    def test_dois(self):
        self.assertEqual(1 + 1, 2)
"""

FAILS = """
import unittest


class Falha(unittest.TestCase):
    def test_que_falha(self):
        self.assertEqual(1, 2, 'falha de proposito do modulo falso')
"""

SKIPS = """
import unittest


class Pula(unittest.TestCase):
    @unittest.skip('pulo de proposito do modulo falso')
    def test_pulado(self):
        pass
"""

# Grava, num arquivo JSON ao lado do módulo, o instante de início e de fim e o valor da variável no ambiente.
MARKER = """
import json
import os
import time
import unittest
from pathlib import Path


class Marca(unittest.TestCase):
    def test_marca(self):
        started = time.time()
        time.sleep(0.4)
        record = {'start': started, 'end': time.time(), 'suite': os.environ.get('FRONTLIGHTS_SUITE')}
        Path(__file__).with_suffix('.json').write_text(json.dumps(record), encoding='utf-8')
"""

# Imprime, com flush, e dorme bem mais do que o prazo que o teste dá ao runner.
SLEEPS = """
import time
import unittest


class Dorme(unittest.TestCase):
    def test_dorme(self):
        print('antes de dormir', flush=True)
        time.sleep(10)
"""

BROKEN_IMPORT = """
import unittest
import no_such_module_xyz


class Quebrado(unittest.TestCase):
    def test_nunca_roda(self):
        pass
"""

BROKEN_SYNTAX = """
import unittest


class Quebrado(unittest.TestCase)
    def test_nunca_roda(self):
        pass
"""

EMPTY_CLASS = """
import unittest


class SemTestes(unittest.TestCase):
    def ajuda(self):
        pass
"""

CRASH = """
import os
import unittest


class Cai(unittest.TestCase):
    def test_cai(self):
        os._exit(3)
"""

EMPTY_EXIT0 = """
import os
os._exit(0)
"""

# Sobe um neto que dorme 60 s (grupo próprio, sem janela), grava os dois PIDs num JSON ao lado e dorme 30 s.
SPAWNS_GRANDCHILD = """
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path


class Neto(unittest.TestCase):
    def test_sobe_neto_e_dorme(self):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        neto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], creationflags=flags)
        record = {'child': os.getpid(), 'grandchild': neto.pid}
        Path(__file__).with_suffix('.json').write_text(json.dumps(record), encoding='utf-8')
        time.sleep(30)
"""

# Nomeia os módulos que `unittest.TestLoader().discover` carrega de uma pasta, sem rodar nada.
DISCOVERED_MODULES = r"""
import json, sys, unittest
modules = set()
def walk(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            walk(item)
        else:
            modules.add(item.id().split('.')[0])
walk(unittest.TestLoader().discover(sys.argv[1]))
print(json.dumps(sorted(modules)))
"""


def pid_alive(pid):
    """Como serve.pid_alive: OpenProcess + GetExitCodeProcess == STILL_ACTIVE (259). Só Windows."""
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


def kill_pids(pids):
    """Limpeza dos testes: mata cada PID com a árvore, sem confiar na saída do taskkill."""
    for pid in pids:
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, timeout=60)


def environment(value):
    env = {key: val for key, val in os.environ.items() if key != VARIABLE}
    if value is not None:
        env[VARIABLE] = value
    return env


def run(args, value=None):
    return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=environment(value),
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)


def suite(args, value=None):
    return run([str(SUITE), *args], value)


class FakeFolderTests(unittest.TestCase):
    """Base: uma pasta temporária com os módulos falsos pedidos, e o runner rodado sobre ela."""

    def folder(self, modules):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)
        for name, source in modules.items():
            (path / f'{name}.py').write_text(textwrap.dedent(source).lstrip(), encoding='utf-8')
        return path

    def run_suite(self, path, serial, workers=2, extra=(), value=None):
        return suite(['--tests-dir', str(path), '--serial', ','.join(serial), '--workers', str(workers), *extra],
                     value)

    def record(self, path, name):
        return json.loads((path / f'{name}.json').read_text(encoding='utf-8'))

    def markers(self, path, names):
        return {name: self.record(path, name) for name in names}


class TotalsAndExitCodeTests(FakeFolderTests):
    """Seam: a linha de total, o resultado somado e o código de saída."""

    def test_passing_and_skipping_modules_add_up_to_ok_with_skipped_and_exit_zero(self):
        path = self.folder({'test_passa': PASSES, 'test_pula': SKIPS})
        completed = self.run_suite(path, [])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertRegex(completed.stdout, r'\nRan 3 tests in \d+\.\d{3}s\n\nOK \(skipped=1\)\n')

    def test_a_failing_module_makes_the_total_failed_and_exit_one(self):
        path = self.folder({'test_passa': PASSES, 'test_falha': FAILS, 'test_pula': SKIPS})
        completed = self.run_suite(path, [])
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertRegex(completed.stdout, r'\nRan 4 tests in \d+\.\d{3}s\n\nFAILED \(failures=1, skipped=1\)\n')

    def test_each_module_gets_one_line_with_wall_time_count_and_verdict(self):
        path = self.folder({'test_passa': PASSES, 'test_falha': FAILS, 'test_pula': SKIPS})
        completed = self.run_suite(path, ['test_pula'])
        lines = completed.stdout.splitlines()
        self.assertTrue(any(re.search(r'test_passa\b.*\b\d+\.\ds\b.*\bRan 2\b.*\bOK\b', line)
                            and 'pool' in line for line in lines), completed.stdout)
        self.assertTrue(any(re.search(r'test_falha\b.*\b\d+\.\ds\b.*\bRan 1\b.*FAILED \(failures=1\)', line)
                            and 'pool' in line for line in lines), completed.stdout)
        self.assertTrue(any(re.search(r'test_pula\b.*\b\d+\.\ds\b.*\bRan 1\b.*OK \(skipped=1\)', line)
                            and 'serial' in line for line in lines), completed.stdout)

    def test_only_the_failing_module_output_is_repeated_at_the_end_with_how_to_rerun_it(self):
        path = self.folder({'test_passa': PASSES, 'test_falha': FAILS})
        completed = self.run_suite(path, [])
        self.assertIn('falha de proposito do modulo falso', completed.stdout)
        self.assertIn('AssertionError', completed.stdout)
        self.assertIn(f'Rode sozinho: python -m unittest discover -s {path} -p test_falha.py', completed.stdout)
        self.assertNotIn('-p test_passa.py', completed.stdout)
        self.assertNotIn('test_um', completed.stdout)
        self.assertNotIn('test_dois', completed.stdout)


class SerialQueueTests(FakeFolderTests):
    """Seam: os instantes gravados pelos marcadores."""

    def test_serial_modules_run_one_at_a_time_in_the_given_order_and_the_first_one_alone(self):
        names = ('test_marca_c', 'test_marca_a', 'test_marca_b', 'test_marca_p1', 'test_marca_p2')
        path = self.folder({name: MARKER for name in names})
        completed = self.run_suite(path, ['test_marca_c', 'test_marca_a', 'test_marca_b'], workers=2)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        marks = self.markers(path, names)
        self.assertLessEqual(marks['test_marca_c']['end'], marks['test_marca_a']['start'], marks)
        self.assertLessEqual(marks['test_marca_a']['end'], marks['test_marca_b']['start'], marks)
        for pool in ('test_marca_p1', 'test_marca_p2'):
            self.assertGreaterEqual(marks[pool]['start'], marks['test_marca_c']['end'], marks)

    def test_the_pool_never_runs_more_modules_than_workers_at_once(self):
        names = ('test_marca_p1', 'test_marca_p2', 'test_marca_p3')
        path = self.folder({name: MARKER for name in names})
        completed = self.run_suite(path, [], workers=2)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        marks = self.markers(path, names)
        for name, mark in marks.items():
            overlapping = [other for other, mark2 in marks.items()
                           if mark2['start'] < mark['end'] and mark['start'] < mark2['end']]
            self.assertLessEqual(len(overlapping), 2, (name, marks))
        self.assertIn('Trabalhadores: 2', completed.stdout)

    def test_without_the_workers_option_the_pool_has_four_workers_whatever_the_cores(self):
        path = self.folder({'test_passa': PASSES})
        completed = suite(['--tests-dir', str(path), '--serial', ''])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('Trabalhadores: 4\n', completed.stdout)


class EnvironmentTests(FakeFolderTests):
    """Seam: o cabeçalho e a variável repassada aos filhos."""

    def test_the_header_names_the_variable_and_the_children_receive_it(self):
        path = self.folder({'test_marca_v': MARKER})
        completed = self.run_suite(path, [], value='rapida')
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f'{VARIABLE}=rapida', completed.stdout)
        self.assertIn(str(path), completed.stdout)
        self.assertEqual(self.record(path, 'test_marca_v')['suite'], 'rapida')

    def test_the_header_says_when_the_variable_is_absent(self):
        path = self.folder({'test_marca_v': MARKER})
        completed = self.run_suite(path, [], value=None)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('(sem variável)', completed.stdout)
        self.assertIsNone(self.record(path, 'test_marca_v')['suite'])


class ValidationTests(FakeFolderTests):
    """Seam: saída 2 antes de qualquer processo."""

    def test_a_serial_module_that_does_not_exist_stops_everything_with_exit_two(self):
        path = self.folder({'test_marca_v': MARKER})
        completed = self.run_suite(path, ['nao_existe'])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn('nao_existe', completed.stdout + completed.stderr)
        self.assertFalse((path / 'test_marca_v.json').exists(), 'nenhum módulo pode rodar antes da validação')

    def test_argparse_rejects_zero_workers_zero_timeout_and_a_missing_folder(self):
        path = self.folder({'test_marca_v': MARKER})
        for extra in (['--workers', '0'], ['--module-timeout', '0'], ['--tests-dir', str(path / 'nao_existe')]):
            with self.subTest(extra=extra):
                completed = suite(['--tests-dir', str(path), '--serial', '', *extra])
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn('usage', completed.stderr)
        self.assertFalse((path / 'test_marca_v.json').exists(), 'nenhum módulo pode rodar antes da validação')

    def test_outside_windows_the_runner_refuses_with_exit_two(self):
        fake = f"import sys; sys.platform = 'linux'; import runpy; runpy.run_path(r'{SUITE}', run_name='__main__')"
        completed = run(['-c', fake, '--list'])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn('Windows', completed.stderr)
        self.assertIn('linux', completed.stderr)


class ListTests(unittest.TestCase):
    """Seam: `--list` sobre a pasta real `tests/`, sem rodar nada."""

    def test_list_names_exactly_the_modules_unittest_discovers_and_marks_the_serial_ones(self):
        completed = suite(['--list'])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        entries = re.findall(r'^\s*(\d+)\s+(serial|pool)\s+(test_\w+)\s*$', completed.stdout, re.MULTILINE)
        self.assertTrue(entries, completed.stdout)
        self.assertEqual([int(order) for order, _, _ in entries], list(range(1, len(entries) + 1)))
        discovered = run(['-c', DISCOVERED_MODULES, 'tests'])
        self.assertEqual(discovered.returncode, 0, discovered.stderr)
        self.assertEqual(sorted(name for _, _, name in entries), json.loads(discovered.stdout))
        serial = [name for _, kind, name in entries if kind == 'serial']
        self.assertEqual(serial, list(SERIAL_REAL))
        self.assertNotIn('Ran ', completed.stdout)


class SleepersTests(FakeFolderTests):
    """Base: pastas com dorminhocos; a limpeza mata os PIDs gravados (e o runner), para nunca deixar neto vivo."""

    def recorded_pids(self, path, names):
        pids = []
        for name in names:
            record_file = path / f'{name}.json'
            if record_file.exists():
                record = json.loads(record_file.read_text(encoding='utf-8'))
                pids.extend([record['child'], record['grandchild']])
        return pids

    def folder_with_cleanup(self, modules):
        path = self.folder(modules)
        self.addCleanup(lambda: kill_pids(self.recorded_pids(path, modules)))
        return path

    def module_lines(self, stdout, name):
        return [line for line in stdout.splitlines() if line.startswith('[') and f' {name} ' in line]


class ModuleTimeoutTests(SleepersTests):
    """Seam: `--module-timeout` com um módulo que dorme além do prazo."""

    def test_a_module_past_the_timeout_is_killed_and_its_partial_output_is_shown_with_exit_two(self):
        path = self.folder_with_cleanup({'test_sleeps': SLEEPS, 'test_passa': PASSES})
        started = time.monotonic()
        completed = self.run_suite(path, [], extra=['--module-timeout', '1'])
        wall = time.monotonic() - started
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertLess(wall, 8, f'o runner levou {wall:.1f} s para matar um módulo com prazo de 1 s')
        self.assertIn('antes de dormir', completed.stdout)
        self.assertIn(f'Rode sozinho: python -m unittest discover -s {path} -p test_sleeps.py', completed.stdout)
        self.assertNotIn('-p test_passa.py', completed.stdout)
        lines = self.module_lines(completed.stdout, 'test_sleeps')
        self.assertEqual(len(lines), 1, completed.stdout)
        self.assertIn('prazo de 1.0 s estourado', lines[0])
        self.assertNotIn('Ran ?', lines[0])

    def test_the_whole_process_tree_of_a_timed_out_module_is_dead_after_the_runner_ends(self):
        path = self.folder_with_cleanup({'test_neto': SPAWNS_GRANDCHILD})
        completed = self.run_suite(path, [], extra=['--module-timeout', '2'])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        pids = self.recorded_pids(path, ['test_neto'])
        self.assertEqual(len(pids), 2, 'o módulo falso não chegou a gravar os PIDs')
        time.sleep(0.5)
        alive = [pid for pid in pids if pid_alive(pid)]
        self.assertEqual(alive, [], f'processos vivos depois do runner: {alive} (filho, neto) = {pids}')


class InfrastructureErrorTests(FakeFolderTests):
    """Seam: saída 2 quando o filho não importa, não deixa a linha `Ran` ou cai; `Ran 0 tests` é aceito."""

    def test_a_module_that_does_not_import_is_an_infrastructure_error_with_its_traceback_at_the_end(self):
        for name, source in (('test_broken_import', BROKEN_IMPORT), ('test_broken_syntax', BROKEN_SYNTAX)):
            with self.subTest(module=name):
                path = self.folder({name: source, 'test_passa': PASSES})
                completed = self.run_suite(path, [])
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn('Failed to import test module', completed.stdout)
                self.assertIn('Traceback', completed.stdout)
                self.assertIn(f'Rode sozinho: python -m unittest discover -s {path} -p {name}.py', completed.stdout)
                self.assertNotIn('-p test_passa.py', completed.stdout)

    def test_a_child_without_the_ran_line_is_an_infrastructure_error_whatever_its_exit_code(self):
        for name, source in (('test_crash', CRASH), ('test_empty_exit0', EMPTY_EXIT0)):
            with self.subTest(module=name):
                path = self.folder({name: source, 'test_passa': PASSES})
                completed = self.run_suite(path, [])
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn(f'-p {name}.py', completed.stdout)
                self.assertNotIn('-p test_passa.py', completed.stdout)

    def test_a_module_with_zero_tests_counts_zero_and_is_not_an_error(self):
        path = self.folder({'test_vazio': EMPTY_CLASS, 'test_passa': PASSES})
        completed = self.run_suite(path, [])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertRegex(completed.stdout, r'\nRan 2 tests in \d+\.\d{3}s\n\nOK\n')
        lines = [line for line in completed.stdout.splitlines() if line.startswith('[') and ' test_vazio ' in line]
        self.assertEqual(len(lines), 1, completed.stdout)
        self.assertIn('Ran 0', lines[0])

    def test_infrastructure_wins_over_a_product_failure_without_hiding_it(self):
        path = self.folder({'test_falha': FAILS, 'test_broken_import': BROKEN_IMPORT})
        completed = self.run_suite(path, [])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn('falha de proposito do modulo falso', completed.stdout)
        self.assertIn('Failed to import test module', completed.stdout)
        self.assertIn('-p test_falha.py', completed.stdout)
        self.assertIn('-p test_broken_import.py', completed.stdout)
        self.assertRegex(completed.stdout, r'\nFAILED \(failures=1, infraestrutura=1\)\n')


@unittest.skipUnless(os.name == 'nt', 'CTRL_BREAK_EVENT e grupos de processos só existem no Windows')
class InterruptTests(SleepersTests):
    """Seam: Ctrl+Break no runner mata os filhos e os netos antes de sair com 130."""

    def test_ctrl_break_kills_every_child_and_grandchild_and_exits_with_130(self):
        names = ('test_neto_a', 'test_neto_b')
        path = self.folder_with_cleanup({name: SPAWNS_GRANDCHILD for name in names})
        runner = subprocess.Popen([sys.executable, str(SUITE), '--tests-dir', str(path), '--serial', '',
                                   '--workers', '2', '--module-timeout', '60'],
                                  cwd=str(ROOT), env=environment(None), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.addCleanup(lambda: kill_pids([runner.pid]))
        deadline = time.monotonic() + 15
        while len(self.recorded_pids(path, names)) < 4 and time.monotonic() < deadline:
            time.sleep(0.1)
        pids = self.recorded_pids(path, names)
        self.assertEqual(len(pids), 4, f'os módulos falsos não gravaram os 4 PIDs em 15 s: {pids}')
        try:
            os.kill(runner.pid, signal.CTRL_BREAK_EVENT)
        except OSError as error:
            kill_pids([runner.pid])
            self.skipTest(f'sem console para o CTRL_BREAK_EVENT ({error}); a issue prevê demonstração manual')
        try:
            raw, _ = runner.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            kill_pids([runner.pid])
            self.fail('o runner não terminou em 15 s depois do Ctrl+Break')
        output = raw.decode('utf-8', errors='replace')
        time.sleep(0.5)
        alive = [pid for pid in pids if pid_alive(pid)]
        self.assertEqual(alive, [], f'processos vivos depois do Ctrl+Break: {alive} de {pids}\n{output}')
        self.assertNotEqual(runner.returncode, 3221225786, 'o runner morreu pelo CTRL_BREAK sem tratar\n' + output)
        self.assertEqual(runner.returncode, 130, output)
        self.assertIn('Interrompido', output)


def git_head():
    completed = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                               timeout=45)
    return completed.stdout.strip() if completed.returncode == 0 else None


TOP_KEYS = ('version', 'started_at', 'finished_at', 'seconds', 'head', 'variable', 'workers', 'module_timeout',
            'tests_dir', 'modules', 'totals', 'result', 'exit_code')
MODULE_KEYS = ('name', 'queue', 'seconds', 'tests_run', 'skipped', 'failures', 'errors', 'result', 'exit_code',
               'problem', 'command')
TOTAL_KEYS = ('modules', 'tests_run', 'skipped', 'failures', 'errors', 'infrastructure')


class ParallelSuiteReportTests(SleepersTests):
    """Seam: o JSON que `--report <arquivo>` grava, lido depois da rodada sobre os módulos falsos."""

    def report_file(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / 'rodada.json'

    def load(self, report):
        self.assertTrue(report.exists(), 'o runner não gravou o relatório')
        return json.loads(report.read_text(encoding='utf-8'))

    def by_name(self, data):
        return {module['name']: module for module in data['modules']}

    def test_the_report_has_the_run_the_modules_and_the_totals(self):
        path = self.folder({'test_passa': PASSES, 'test_falha': FAILS, 'test_pula': SKIPS})
        report = self.report_file()
        completed = self.run_suite(path, ['test_passa'], workers=2, extra=['--report', str(report)], value='rapida')
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        data = self.load(report)
        self.assertEqual(list(data), list(TOP_KEYS))
        self.assertEqual(data['version'], 1)
        started = datetime.fromisoformat(data['started_at'])
        finished = datetime.fromisoformat(data['finished_at'])
        self.assertIsNotNone(started.tzinfo, data['started_at'])
        self.assertIsNotNone(finished.tzinfo, data['finished_at'])
        self.assertLessEqual(started, finished)
        self.assertGreaterEqual(data['seconds'], 0)
        self.assertEqual(data['head'], git_head())
        self.assertEqual(data['variable'], 'rapida')
        self.assertEqual(data['workers'], 2)
        self.assertEqual(data['module_timeout'], 900)
        self.assertEqual(Path(data['tests_dir']).resolve(), path.resolve())
        self.assertEqual([module['name'] for module in data['modules']], ['test_passa', 'test_falha', 'test_pula'])
        for module in data['modules']:
            with self.subTest(module=module['name']):
                self.assertEqual(list(module), list(MODULE_KEYS))
                self.assertGreaterEqual(module['seconds'], 0)
                self.assertIsNone(module['problem'])
                self.assertIn(f'-p {module["name"]}.py', module['command'])
        modules = self.by_name(data)
        self.assertEqual(modules['test_passa']['queue'], 'serial')
        self.assertEqual(modules['test_falha']['queue'], 'pool')
        self.assertEqual(modules['test_pula']['queue'], 'pool')
        self.assertEqual((modules['test_passa']['result'], modules['test_passa']['exit_code'],
                          modules['test_passa']['tests_run']), ('ok', 0, 2))
        self.assertEqual((modules['test_falha']['result'], modules['test_falha']['exit_code'],
                          modules['test_falha']['tests_run'], modules['test_falha']['failures']), ('failed', 1, 1, 1))
        self.assertEqual((modules['test_pula']['result'], modules['test_pula']['tests_run'],
                          modules['test_pula']['skipped']), ('ok', 1, 1))
        self.assertEqual(list(data['totals']), list(TOTAL_KEYS))
        for key in ('tests_run', 'skipped', 'failures', 'errors'):
            with self.subTest(total=key):
                self.assertEqual(data['totals'][key], sum(module[key] for module in data['modules']))
        self.assertEqual(data['totals']['modules'], 3)
        self.assertEqual(data['totals']['infrastructure'], 0)
        self.assertEqual((data['result'], data['exit_code']), ('failed', 1))

    def test_without_the_variable_the_report_says_null_and_a_green_run_is_ok(self):
        path = self.folder({'test_passa': PASSES})
        report = self.report_file()
        completed = self.run_suite(path, [], extra=['--report', str(report)])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        data = self.load(report)
        self.assertIsNone(data['variable'])
        self.assertEqual((data['result'], data['exit_code']), ('ok', 0))

    def test_a_timed_out_module_is_infrastructure_with_no_exit_code_and_the_run_exits_two(self):
        path = self.folder_with_cleanup({'test_sleeps': SLEEPS, 'test_passa': PASSES})
        report = self.report_file()
        completed = self.run_suite(path, [], extra=['--module-timeout', '1', '--report', str(report)])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        data = self.load(report)
        sleeps = self.by_name(data)['test_sleeps']
        self.assertEqual((sleeps['result'], sleeps['exit_code']), ('infrastructure', None))
        self.assertIn('prazo de 1.0 s estourado', sleeps['problem'])
        self.assertEqual(data['module_timeout'], 1)
        self.assertEqual(data['totals']['infrastructure'], 1)
        self.assertEqual(data['totals']['tests_run'], 2, 'o módulo de infraestrutura não entra nos totais')
        self.assertEqual((data['result'], data['exit_code']), ('infrastructure', 2))

    def test_a_report_in_a_missing_folder_is_refused_with_exit_two_before_anything_runs(self):
        path = self.folder({'test_marca_v': MARKER})
        report = path / 'nao_existe' / 'rodada.json'
        completed = self.run_suite(path, [], extra=['--report', str(report)])
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn('usage', completed.stderr)
        self.assertIn('a pasta do relatório não existe', completed.stderr)
        self.assertFalse((path / 'test_marca_v.json').exists(), 'nenhum módulo pode rodar antes da validação')
        self.assertFalse(report.exists())

    @unittest.skipUnless(os.name == 'nt', 'CTRL_BREAK_EVENT e grupos de processos só existem no Windows')
    def test_an_interrupted_run_writes_the_report_with_the_modules_that_finished(self):
        path = self.folder_with_cleanup({'test_passa': PASSES, 'test_neto': SPAWNS_GRANDCHILD})
        report = self.report_file()
        runner = subprocess.Popen([sys.executable, str(SUITE), '--tests-dir', str(path), '--serial', 'test_passa',
                                   '--workers', '2', '--module-timeout', '60', '--report', str(report)],
                                  cwd=str(ROOT), env=environment(None), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.addCleanup(lambda: kill_pids([runner.pid]))
        deadline = time.monotonic() + 15
        while len(self.recorded_pids(path, ['test_neto'])) < 2 and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(len(self.recorded_pids(path, ['test_neto'])), 2, 'o módulo falso não gravou os PIDs')
        try:
            os.kill(runner.pid, signal.CTRL_BREAK_EVENT)
        except OSError as error:
            kill_pids([runner.pid])
            self.skipTest(f'sem console para o CTRL_BREAK_EVENT ({error})')
        try:
            raw, _ = runner.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            kill_pids([runner.pid])
            self.fail('o runner não terminou em 15 s depois do Ctrl+Break')
        output = raw.decode('utf-8', errors='replace')
        self.assertEqual(runner.returncode, 130, output)
        data = self.load(report)
        self.assertEqual((data['result'], data['exit_code']), ('interrupted', 130))
        self.assertEqual([module['name'] for module in data['modules']], ['test_passa'], output)
        self.assertEqual(data['totals']['tests_run'], 2)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def section(text, heading, next_heading):
    return ' '.join(text.split(heading)[1].split(next_heading)[0].split())


class ParallelSuiteTextTests(unittest.TestCase):
    """Seam: os manifestos de texto. As frases da issue 25 continuam guardadas por test_suite_rapida.py."""

    def test_the_readme_runs_the_fast_suite_by_the_runner_and_the_whole_one_by_discover(self):
        text = flat('README.md')
        for phrase in ('A suíte rápida roda por `python tests/suite.py`', 'numa fila serial',
                       '`--report <arquivo>` grava um JSON',
                       'vale igual para o `discover` e para o runner',
                       'pelo `python -m unittest discover -s tests -v`',
                       'o runner não encurta a suíte inteira',
                       'roda o mesmo `discover`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn('python -m unittest discover -s tests -v\npython tests/suite.py\n', read('README.md'))

    def test_the_protocol_says_the_same(self):
        text = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('roda por `python tests/suite.py` com `FRONTLIGHTS_SUITE=rapida`', 'numa fila serial',
                       '`--report <arquivo>` grava o JSON da rodada',
                       'pelo `python -m unittest discover -s tests -v`',
                       'roda o mesmo `discover` e não define a variável'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_stage_six_reference_says_the_same_inside_its_section(self):
        text = section(read('skills', 'frontlights', 'references', 'development.md'),
                       '## Slices in order', '## Dispatch and ownership')
        for phrase in ('the fast suite runs through `python tests/suite.py`', 'in a serial queue',
                       '`--report <file>` writes the JSON of the run',
                       'through `python -m unittest discover -s tests -v`',
                       'the runner does not make the whole suite shorter',
                       'runs the same `discover` and never sets the variable'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_acceptance_record_names_the_runner_and_the_discover(self):
        text = flat('docs', 'acceptance.md')
        for phrase in ('A suíte rápida roda por `python tests/suite.py`', 'É a suíte inteira e o comando da CI',
                       'pelo `discover`, continua obrigatória antes da revisão independente e do PR',
                       '`python -m compileall -q skills/frontlights/scripts tests`', 'issue 27'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('`python -m compileall -q scripts tests`', text)

    def test_the_acceptance_record_counts_every_test_module(self):
        match = re.search(r'\*\*(\d+) testes em (\d+) módulos', flat('docs', 'acceptance.md'))
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(2)), len(list((ROOT / 'tests').glob('test_*.py'))))

    def test_the_ci_keeps_the_discover_and_never_calls_the_runner(self):
        workflow = read('.github', 'workflows', 'tests.yml')
        self.assertIn('python -m unittest discover -s tests -v', workflow)
        self.assertNotIn('tests/suite.py', workflow)


if __name__ == '__main__':
    unittest.main()
