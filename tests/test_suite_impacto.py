"""Suíte por impacto: `tests/suite.py --impact <base>` (issue 52, S4; issue 57, S1).

Seam: a linha de comando do runner, chamada por subprocess sobre a pasta `tests/` de um repositório Git temporário
com módulos falsos. Cada classe de teste falsa, quando roda, grava em `tests/marcas/<módulo>.<Classe>.json` o valor
da variável que recebeu. Os três pesados falsos (`test_serve_ports`, `test_checks_integration`, `test_serve_preview`)
imitam o `load_tests` da suíte rápida (com `FRONTLIGHTS_SUITE=rapida`, um teste pulado, sem marca). O que se observa:
o código de saída, as marcas gravadas (quais módulos e classes rodaram de fato), o `--list` e o relatório de
`--report`. Nada aqui roda a suíte real.
"""
import json
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from test_suite_paralela import suite

HEAVY = ('test_serve_ports', 'test_checks_integration', 'test_serve_preview')

# O começo de todo módulo falso: o caminho dos scripts do repositório falso e a função que grava a marca da classe.
HEAD = """
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def marca(test):
    folder = Path(__file__).resolve().parent / 'marcas'
    folder.mkdir(exist_ok=True)
    name = f'{Path(__file__).stem}.{type(test).__name__}'
    record = {'suite': os.environ.get('FRONTLIGHTS_SUITE')}
    (folder / f'{name}.json').write_text(json.dumps(record), encoding='utf-8')
"""

# O `load_tests` dos pesados falsos, como o dos reais: com a variável, o módulo vira um único teste pulado.
SKIP_FAST = """

def load_tests(loader, tests, pattern):
    if os.environ.get('FRONTLIGHTS_SUITE') != 'rapida':
        return tests
    pulado = type('ModuloPulado', (unittest.TestCase,),
                  {'test_pulado': unittest.skip('FRONTLIGHTS_SUITE=rapida pula o pesado falso')(lambda self: None)})
    return unittest.TestSuite([pulado('test_pulado')])
"""


def marked_class(name, body=''):
    """Uma classe de teste falsa que grava a marca; `body` entra no método (para citar um arquivo, por exemplo)."""
    return f"""

class {name}(unittest.TestCase):
    def test_marca(self):
        {body or 'pass'}
        marca(self)
"""


def module(*classes, top='', heavy=False):
    return HEAD + top + (SKIP_FAST if heavy else '') + ''.join(classes)


CITES = "self.assertTrue('alvo.py')"  # cita o nome do arquivo mudado dentro da classe

FILES = {
    'scripts/alvo.py': 'VALOR = 1\n',
    'notas.md': 'Notas do repositório falso.\n',
    'tests/suite.py': '# runner de mentira\n',
    # não cita nem importa o alvo: só roda quando ele mesmo muda
    'tests/test_leve.py': module(marked_class('Leve')),
    # importa o alvo no topo: escolhido inteiro
    'tests/test_topo.py': module(marked_class('Topo'), top='import alvo\n'),
    # só uma classe cita o alvo: escolhido só nela
    'tests/test_classes.py': module(marked_class('CitaAlvo', CITES), marked_class('NaoCita')),
    # o teste de fonte única: roda sempre, inteiro
    'tests/test_single_source.py': module(marked_class('FonteUnica'), marked_class('OutraRegra')),
    # pesado que importa o alvo no topo: inteiro, sem a variável
    'tests/test_serve_ports.py': module(marked_class('Pesado'), top='import alvo\n', heavy=True),
    # pesado em que só uma classe cita o alvo: só ela, sem a variável
    'tests/test_checks_integration.py': module(marked_class('CitaAlvo', CITES), marked_class('Outra'), heavy=True),
    # pesado que não cita nem importa o alvo: fica de fora
    'tests/test_serve_preview.py': module(marked_class('Pesado'), heavy=True),
}

EVERY_CLASS = {'test_leve.Leve', 'test_topo.Topo', 'test_classes.CitaAlvo', 'test_classes.NaoCita',
               'test_single_source.FonteUnica', 'test_single_source.OutraRegra', 'test_serve_ports.Pesado',
               'test_checks_integration.CitaAlvo', 'test_checks_integration.Outra', 'test_serve_preview.Pesado'}
EVERY_MODULE = sorted({name.split('.')[0] for name in EVERY_CLASS})


class ImpactTests(unittest.TestCase):
    """Base: um repositório temporário com `scripts/alvo.py`, os módulos falsos de FILES e um `tests/suite.py` de
    mentira, num commit que serve de base."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.tests = self.repo / 'tests'
        for relative, text in FILES.items():
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

    def list_impact(self):
        return suite(['--tests-dir', str(self.tests), '--serial', ','.join(HEAVY), '--impact', self.base, '--list'])

    def marks(self):
        """As classes que rodaram de verdade (`<módulo>.<Classe>`), com o valor da variável que cada uma recebeu."""
        folder = self.tests / 'marcas'
        if not folder.is_dir():
            return {}
        return {path.stem: json.loads(path.read_text(encoding='utf-8'))['suite'] for path in folder.glob('*.json')}

    def selection(self, data):
        return {item['name']: item for item in data['impact']}


class ImpactSelectionTests(ImpactTests):
    """Seam: o que roda, em todos os módulos, conforme o diff: inteiro, só algumas classes ou nada."""

    def test_a_change_to_a_script_runs_only_what_the_pre_commit_selection_chooses_whole_or_by_class(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, _ = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.marks(), {
            'test_topo.Topo': 'rapida',
            'test_classes.CitaAlvo': 'rapida',
            'test_single_source.FonteUnica': 'rapida',
            'test_single_source.OutraRegra': 'rapida',
            'test_serve_ports.Pesado': None,
            'test_checks_integration.CitaAlvo': None,
        }, output)

    def test_the_chosen_heavy_modules_run_without_the_variable_in_the_serial_queue(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        queues = {module['name']: module['queue'] for module in data['modules']}
        self.assertEqual(queues, {'test_serve_ports': 'impacto', 'test_checks_integration': 'impacto',
                                  'test_topo': 'pool', 'test_classes': 'pool', 'test_single_source': 'pool'},
                         data['modules'])
        order = [module['name'] for module in data['modules'] if module['queue'] == 'impacto']
        self.assertEqual(order, ['test_serve_ports', 'test_checks_integration'], 'a ordem da lista serial')
        self.assertRegex(completed.stdout, r'(?m)^\[impacto\] test_serve_ports\b.*\bRan 1\b +OK$', output)

    def test_an_uncommitted_change_counts_too(self):
        self.change('scripts/alvo.py')
        completed, _ = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('test_topo.Topo', self.marks(), completed.stdout)
        self.assertIn('test_serve_ports.Pesado', self.marks(), completed.stdout)

    def test_a_diff_that_touches_no_test_runs_only_the_single_source_test(self):
        self.change('notas.md', 'muda as notas')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.marks(), {'test_single_source.FonteUnica': 'rapida',
                                        'test_single_source.OutraRegra': 'rapida'}, output)
        self.assertNotIn('[impacto]', completed.stdout)
        self.assertEqual([module['name'] for module in data['modules']], ['test_single_source'], data['modules'])
        self.assertEqual({name for name, item in self.selection(data).items() if item['selected']},
                         {'test_single_source'}, data['impact'])

    def test_a_changed_test_module_runs_whole_and_alone_besides_the_single_source_test(self):
        self.change('tests/test_classes.py', 'muda um teste')
        completed, _ = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(set(self.marks()), {'test_classes.CitaAlvo', 'test_classes.NaoCita',
                                             'test_single_source.FonteUnica', 'test_single_source.OutraRegra'},
                         output)

    def test_a_change_to_the_runner_runs_every_module_whole_with_the_heavy_ones_without_the_variable(self):
        self.change('tests/suite.py', 'muda o runner')
        completed, data = self.run_impact()
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        marks = self.marks()
        self.assertEqual(set(marks), EVERY_CLASS, output)
        self.assertEqual({name for name, value in marks.items() if value is None},
                         {name for name in EVERY_CLASS if name.split('.')[0] in HEAVY}, output)
        for name, item in self.selection(data).items():
            self.assertTrue(item['selected'], data['impact'])
            self.assertIn('runner', item['reason'])

    def test_list_shows_each_chosen_module_whole_or_by_class_and_why_without_running_anything(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed = self.list_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        entries = re.findall(r'(?m)^\s*\d+\s+(serial|impacto|pool)\s+(test_\w+)(?:\s+\(([^)]*)\))?\s*$',
                             completed.stdout)
        self.assertEqual({name: (kind, classes) for kind, name, classes in entries}, {
            'test_serve_ports': ('impacto', ''),
            'test_checks_integration': ('impacto', 'CitaAlvo'),
            'test_classes': ('pool', 'CitaAlvo'),
            'test_single_source': ('pool', ''),
            'test_topo': ('pool', ''),
        }, completed.stdout)
        reasons = {line.split(':')[0].strip(): line for line in completed.stdout.splitlines()
                   if line.startswith('  test_')}
        self.assertIn('alvo.py', reasons['test_topo'], completed.stdout)
        self.assertIn('alvo.py', reasons['test_checks_integration'], completed.stdout)
        self.assertIn('fica de fora', reasons['test_leve'], completed.stdout)
        self.assertIn('fica de fora', reasons['test_serve_preview'], completed.stdout)
        self.assertNotIn('fica de fora', reasons['test_single_source'], completed.stdout)
        self.assertEqual(self.marks(), {})
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
        self.assertEqual(self.marks(), {})


class ImpactReportTests(ImpactTests):
    """Seam: o JSON de `--report` numa rodada por impacto."""

    def test_the_report_records_the_mode_the_base_and_why_each_module_ran_or_not(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(data['mode'], 'impact')
        self.assertEqual(data['base'], self.base)
        self.assertEqual(data['base_commit'], self.base)
        self.assertEqual(data['changed'], ['scripts/alvo.py'])
        self.assertEqual(data['variable'], 'rapida')
        for key in ('version', 'started_at', 'finished_at', 'head', 'workers', 'module_timeout', 'tests_dir',
                    'modules', 'totals', 'result', 'exit_code'):
            self.assertIn(key, data)
        selection = self.selection(data)
        self.assertEqual(sorted(selection), EVERY_MODULE)
        self.assertEqual({name for name, item in selection.items() if item['selected']},
                         {'test_topo', 'test_classes', 'test_single_source', 'test_serve_ports',
                          'test_checks_integration'}, data['impact'])
        self.assertIn('alvo.py', selection['test_serve_ports']['reason'])
        for name in ('test_leve', 'test_serve_preview'):
            self.assertFalse(selection[name]['selected'])
            self.assertTrue(selection[name]['reason'])
        heavy = {module['name']: (module['tests_run'], module['skipped'], module['result'])
                 for module in data['modules'] if module['queue'] == 'impacto'}
        self.assertEqual(heavy, {'test_serve_ports': (1, 0, 'ok'), 'test_checks_integration': (1, 0, 'ok')})

    def test_the_report_lists_what_ran_by_module_or_class_and_which_modules_ran_whole(self):
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(sorted(data['ran']), ['test_checks_integration.CitaAlvo', 'test_classes.CitaAlvo',
                                               'test_serve_ports', 'test_single_source', 'test_topo'], data)
        self.assertEqual(sorted(data['complete']), ['test_serve_ports', 'test_single_source', 'test_topo'], data)

    def test_after_a_runner_change_every_module_ran_whole(self):
        self.change('tests/suite.py', 'muda o runner')
        completed, data = self.run_impact()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(sorted(data['ran']), EVERY_MODULE)
        self.assertEqual(sorted(data['complete']), EVERY_MODULE)

    def test_a_failing_class_run_alone_fails_the_round_and_names_the_class_in_the_rerun_command(self):
        path = self.tests / 'test_classes.py'
        path.write_text(path.read_text(encoding='utf-8').replace(CITES, CITES + '; self.fail("de propósito")'),
                        encoding='utf-8')
        self.commit('a classe que cita falha')
        self.base = self.git('rev-parse', 'HEAD').strip()  # a falha já está na base: o teste não está no diff
        self.change('scripts/alvo.py', 'muda o alvo')
        completed, data = self.run_impact()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        failed = [module for module in data['modules'] if module['result'] == 'failed']
        self.assertEqual([module['name'] for module in failed], ['test_classes'], data['modules'])
        self.assertIn('*.CitaAlvo.*', failed[0]['command'])
        self.assertNotIn('test_classes.NaoCita', self.marks())


if __name__ == '__main__':
    unittest.main()
