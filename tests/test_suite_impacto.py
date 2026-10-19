"""Suíte por impacto: `tests/suite.py --impact <base>` (issue 52, S4).

Seam: a linha de comando do runner, chamada por subprocess sobre a pasta `tests/` de um repositório Git temporário
com módulos falsos. Os três pesados falsos (`test_serve_ports`, `test_checks_integration`, `test_serve_preview`)
imitam o `load_tests` da suíte rápida (com `FRONTLIGHTS_SUITE=rapida`, um teste pulado) e, quando rodam de verdade,
gravam num JSON ao lado o valor da variável que receberam. O que se observa: o código de saída, os JSONs gravados
pelos pesados, o `--list` e o relatório de `--report`. Nada aqui roda a suíte real.
"""
import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from test_suite_paralela import PASSES, suite

HEAVY = ('test_serve_ports', 'test_checks_integration', 'test_serve_preview')

# Um pesado falso: pula com a variável, como os reais; sem ela, roda e grava o que recebeu. IMPORTS vira a linha de
# import do módulo (o `alvo` é um script da pasta `scripts/` do repositório falso).
HEAVY_SOURCE = """
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
IMPORTS


def load_tests(loader, tests, pattern):
    if os.environ.get('FRONTLIGHTS_SUITE') != 'rapida':
        return tests
    pulado = type('ModuloPulado', (unittest.TestCase,),
                  {'test_pulado': unittest.skip('FRONTLIGHTS_SUITE=rapida pula o pesado falso')(lambda self: None)})
    return unittest.TestSuite([pulado('test_pulado')])


class Pesado(unittest.TestCase):
    def test_roda_de_verdade(self):
        record = {'suite': os.environ.get('FRONTLIGHTS_SUITE')}
        Path(__file__).with_suffix('.json').write_text(json.dumps(record), encoding='utf-8')
"""


def heavy(imports=''):
    return HEAVY_SOURCE.replace('IMPORTS', imports)


class ImpactTests(unittest.TestCase):
    """Base: um repositório temporário com `scripts/alvo.py`, os três pesados (só `test_serve_ports` importa o
    `alvo`), um módulo leve e um `tests/suite.py` de mentira, num commit que serve de base."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.tests = self.repo / 'tests'
        files = {
            'scripts/alvo.py': 'VALOR = 1\n',
            'notas.md': 'Notas do repositório falso.\n',
            'tests/suite.py': '# runner de mentira\n',
            'tests/test_leve.py': PASSES,
            'tests/test_serve_ports.py': heavy('import alvo'),
            'tests/test_checks_integration.py': heavy(),
            'tests/test_serve_preview.py': heavy(),
        }
        for relative, text in files.items():
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text).lstrip(), encoding='utf-8')
        self.git('init', '-q')
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git('config', key, value)
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        done = subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def change(self, relative, message=None):
        """Muda um arquivo e, com `message`, commita a mudança; sem ela, a mudança fica na árvore de trabalho."""
        path = self.repo / relative
        path.write_text(path.read_text(encoding='utf-8') + '# mudança\n', encoding='utf-8')
        if message:
            self.commit(message)

    def run_impact(self, base=None, extra=()):
        report = self.repo.parent / f'{self.repo.name}-rodada.json'
        self.addCleanup(lambda: report.unlink(missing_ok=True))
        completed = suite(['--tests-dir', str(self.tests), '--serial', ','.join(HEAVY), '--workers', '2',
                           '--impact', base or self.base, '--report', str(report), *extra])
        data = json.loads(report.read_text(encoding='utf-8')) if report.exists() else None
        return completed, data

    def ran_without_variable(self):
        """Os pesados que rodaram de verdade, com o valor da variável que cada um recebeu."""
        found = {}
        for name in HEAVY:
            marker = self.tests / f'{name}.json'
            if marker.exists():
                found[name] = json.loads(marker.read_text(encoding='utf-8'))['suite']
        return found

    def selection(self, data):
        return {item['name']: item for item in data['impact']}


class ImpactSelectionTests(ImpactTests):
    """Seam: quais pesados rodam sem a variável, conforme o diff."""

    def test_a_committed_change_to_a_script_a_heavy_module_imports_runs_that_module_without_the_variable(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.ran_without_variable(), {'test_serve_ports': None}, output)
        self.assertRegex(completed.stdout, r'(?m)^\[impacto\] test_serve_ports\b.*\bRan 1\b +OK$', output)

    def test_an_uncommitted_change_counts_too(self):
        self.change('scripts/alvo.py')
        completed, _ = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(self.ran_without_variable(), {'test_serve_ports': None}, completed.stdout)

    def test_a_diff_that_touches_nothing_heavy_leaves_the_heavy_modules_out_but_reports_them(self):
        self.change('notas.md', 'muda as notas')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.ran_without_variable(), {}, output)
        self.assertNotIn('[impacto]', completed.stdout)
        self.assertEqual({name: item['selected'] for name, item in self.selection(data).items()},
                         {name: False for name in HEAVY}, data)
        for name in HEAVY:
            self.assertIn(name, completed.stdout)

    def test_a_change_to_the_runner_selects_every_heavy_module(self):
        self.change('tests/suite.py', 'muda o runner')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.ran_without_variable(), {name: None for name in HEAVY}, output)
        for name, item in self.selection(data).items():
            self.assertTrue(item['selected'], data)
            self.assertIn('runner', item['reason'])

    def test_list_shows_which_heavy_modules_would_run_without_running_anything(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed = suite(['--tests-dir', str(self.tests), '--serial', ','.join(HEAVY), '--impact', self.base,
                           '--list'])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertRegex(completed.stdout, r'(?m)^\s*\d+\s+impacto\s+test_serve_ports\s*$')
        self.assertNotRegex(completed.stdout, r'(?m)^\s*\d+\s+impacto\s+test_serve_preview\s*$')
        self.assertEqual(self.ran_without_variable(), {})
        self.assertNotIn('Ran ', completed.stdout)


class ImpactValidationTests(ImpactTests):
    """Seam: a base que o Git não resolve."""

    def test_a_base_git_cannot_resolve_exits_two_before_anything_runs(self):
        completed, data = self.run_impact(base='nao-existe-essa-base')
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn("o Git não resolve a base 'nao-existe-essa-base'", completed.stderr)
        self.assertNotIn('usage', completed.stderr, 'é erro da base, não da linha de comando')
        self.assertNotIn('Ran ', completed.stdout)
        self.assertIsNone(data, 'nada roda, então nenhum relatório')
        self.assertEqual(self.ran_without_variable(), {})


class ImpactReportTests(ImpactTests):
    """Seam: o JSON de `--report` numa rodada por impacto."""

    def test_the_report_records_the_mode_the_base_and_why_each_heavy_module_ran_or_not(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(data['mode'], 'impact')
        self.assertEqual(data['base'], self.base)
        self.assertEqual(data['variable'], 'rapida')
        selection = self.selection(data)
        self.assertEqual(list(selection), list(HEAVY))
        self.assertTrue(selection['test_serve_ports']['selected'])
        self.assertIn('alvo.py', selection['test_serve_ports']['reason'])
        for name in ('test_checks_integration', 'test_serve_preview'):
            self.assertFalse(selection[name]['selected'])
            self.assertTrue(selection[name]['reason'])
        impact = [module for module in data['modules'] if module['queue'] == 'impacto']
        self.assertEqual([(module['name'], module['tests_run'], module['skipped'], module['result'])
                          for module in impact], [('test_serve_ports', 1, 0, 'ok')], data['modules'])
        fast = {module['name']: module for module in data['modules'] if module['queue'] != 'impacto'}
        self.assertEqual(sorted(fast), sorted([*HEAVY, 'test_leve']))
        for name in HEAVY:
            self.assertEqual(fast[name]['skipped'], 1, fast[name])


if __name__ == '__main__':
    unittest.main()
