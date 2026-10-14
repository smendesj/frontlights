"""Runner paralelo da suíte com fila serial (issue 27, S1).

Seams: a linha de comando de `tests/suite.py` (`--tests-dir`, `--serial`, `--workers`, `--module-timeout`, `--list`),
observada por subprocess sobre uma pasta temporária de módulos falsos que o próprio teste escreve: o que sai no
stdout (cabeçalho, uma linha por módulo, saída completa dos que falharam, total no formato do unittest), o código
de saída, os instantes gravados pelos módulos marcadores (fila serial e limite de trabalhadores) e a variável
`FRONTLIGHTS_SUITE` repassada aos filhos. Nada aqui roda a suíte real: sobre a pasta `tests/` só se usa `--list`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == '__main__':
    unittest.main()
