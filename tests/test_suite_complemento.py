"""Complemento da suíte: `tests/suite.py --skip-covered <arquivo>` (issue 57, S2).

Seam: a linha de comando do runner, chamada por subprocess sobre uma pasta temporária de módulos falsos (os
auxiliares de `test_suite_paralela`). Cada módulo marcador grava, ao lado dele, o valor da variável que recebeu; o
pesado falso imita o `load_tests` da suíte rápida (com `FRONTLIGHTS_SUITE=rapida`, não roda nada e não grava a
marca). O arquivo `{"complete": [...]}` lista os módulos já cobertos. O que se observa: o código de saída, as marcas
gravadas (quais módulos rodaram, e com ou sem a variável), o `--list` e o relatório de `--report`. Nada aqui roda a
suíte real.
"""
import json
import re
import unittest

from test_suite_paralela import FAILS, MARKER, FakeFolderTests

# O pesado falso: só roda (e grava a marca) sem a variável, como os pesados reais com o `load_tests` da rápida.
HEAVY_MARKER = MARKER + """

def load_tests(loader, tests, pattern):
    if os.environ.get('FRONTLIGHTS_SUITE') == 'rapida':
        return unittest.TestSuite()
    return tests
"""

SERIAL = ['test_pesado', 'test_serial_coberto', 'test_serial_livre']
MODULES = {
    'test_pesado': HEAVY_MARKER,
    'test_serial_coberto': MARKER,
    'test_serial_livre': MARKER,
    'test_coberto': MARKER,
    'test_livre': MARKER,
    'test_outro_livre': MARKER,
}
COVERED = ['test_serial_coberto', 'test_coberto', 'test_nao_existe']
RUNS = ['test_pesado', 'test_serial_livre', 'test_livre', 'test_outro_livre']


class ComplementTests(FakeFolderTests):
    """Base: a pasta dos módulos falsos e o arquivo dos cobertos fora dela."""

    def setUp(self):
        self.path = self.folder(MODULES)
        self.covered = self.path.parent / f'{self.path.name}-cobertos.json'
        self.report = self.path.parent / f'{self.path.name}-rodada.json'
        for item in (self.covered, self.report):
            self.addCleanup(lambda item=item: item.unlink(missing_ok=True))

    def write_covered(self, data=None, raw=None):
        self.covered.write_bytes(raw if raw is not None else json.dumps({'complete': data}).encode('utf-8'))

    def complement(self, extra=(), value='rapida'):
        completed = self.run_suite(self.path, SERIAL, extra=['--skip-covered', str(self.covered),
                                                              '--report', str(self.report), *extra], value=value)
        data = json.loads(self.report.read_text(encoding='utf-8')) if self.report.exists() else None
        return completed, data

    def marks(self):
        """{módulo: valor da variável} dos módulos que rodaram de verdade."""
        return {name: self.record(self.path, name)['suite'] for name in MODULES
                if (self.path / f'{name}.json').exists()}


class ComplementRunTests(ComplementTests):
    """Seam: o que roda no complemento, com que variável e em que fila."""

    def test_every_module_runs_whole_and_without_the_variable_except_the_covered_ones(self):
        self.write_covered(COVERED)
        completed, _ = self.complement(value='rapida')
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, output)
        self.assertEqual(self.marks(), {name: None for name in RUNS}, output)
        self.assertIn('(sem variável)', completed.stdout)

    def test_the_serial_ones_run_in_the_serial_queue_in_order_and_the_rest_in_the_pool(self):
        self.write_covered(COVERED)
        completed, data = self.complement()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        queues = [(module['name'], module['queue']) for module in data['modules']]
        self.assertEqual([item for item in queues if item[1] == 'serial'],
                         [('test_pesado', 'serial'), ('test_serial_livre', 'serial')], queues)
        self.assertEqual(sorted(name for name, queue in queues if queue == 'pool'),
                         ['test_livre', 'test_outro_livre'], queues)

    def test_a_covered_failing_module_does_not_run_and_an_uncovered_one_fails_the_round(self):
        path = self.path / 'test_coberto.py'
        path.write_text(FAILS.lstrip(), encoding='utf-8')
        self.write_covered(COVERED)
        completed, _ = self.complement()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.write_covered(['test_serial_coberto'])
        completed, data = self.complement()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertEqual([module['name'] for module in data['modules'] if module['result'] == 'failed'],
                         ['test_coberto'], data['modules'])

    def test_the_file_may_start_with_a_utf8_bom(self):
        self.write_covered(raw=b'\xef\xbb\xbf' + json.dumps({'complete': COVERED}).encode('utf-8'))
        completed, _ = self.complement()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(set(self.marks()), set(RUNS))


class ComplementReportTests(ComplementTests):
    """Seam: o JSON de `--report` numa rodada de complemento."""

    def test_the_report_keeps_its_keys_and_adds_the_mode_the_skipped_and_the_unknown_ids(self):
        self.write_covered(COVERED)
        completed, data = self.complement()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        for key in ('version', 'started_at', 'finished_at', 'seconds', 'head', 'variable', 'workers',
                    'module_timeout', 'tests_dir', 'modules', 'totals', 'result', 'exit_code'):
            self.assertIn(key, data)
        self.assertEqual(data['mode'], 'complement')
        self.assertEqual(data['skipped_covered'], ['test_coberto', 'test_serial_coberto'])
        self.assertEqual(data['unknown_covered'], ['test_nao_existe'])
        self.assertIsNone(data['variable'])
        self.assertEqual(sorted(module['name'] for module in data['modules']), sorted(RUNS))
        self.assertEqual((data['result'], data['exit_code']), ('ok', 0))


class ComplementListTests(ComplementTests):
    """Seam: o `--list` mostra o plano do complemento sem rodar nada."""

    def test_list_shows_the_modules_that_run_and_the_ones_skipped_as_covered(self):
        self.write_covered(COVERED)
        completed, data = self.complement(extra=['--list'])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        entries = re.findall(r'(?m)^\s*\d+\s+(serial|pool)\s+(test_\w+)\s*$', completed.stdout)
        self.assertEqual([name for _, name in entries], ['test_pesado', 'test_serial_livre', 'test_livre',
                                                          'test_outro_livre'], completed.stdout)
        skipped = re.search(r'(?m)^Pulados por cobertos: (.*)$', completed.stdout)
        self.assertIsNotNone(skipped, completed.stdout)
        self.assertEqual(skipped.group(1), 'test_coberto, test_serial_coberto')
        self.assertRegex(completed.stdout, r'(?m)^Ids desconhecidos: test_nao_existe$')
        self.assertEqual(self.marks(), {})
        self.assertNotIn('Ran ', completed.stdout)
        self.assertIsNone(data)


class ComplementValidationTests(ComplementTests):
    """Seam: arquivo ausente, ilegível ou inválido, e a combinação com `--impact`: saída 2, nada roda."""

    def assert_refused(self, completed, data, text):
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2, output)
        self.assertIn(text, completed.stderr, output)
        self.assertIn('Nada foi rodado', completed.stderr, output)
        self.assertNotIn('usage', completed.stderr, output)
        self.assertNotIn('Ran ', completed.stdout)
        self.assertIsNone(data, 'nada roda, então nenhum relatório')
        self.assertEqual(self.marks(), {})

    def test_a_missing_file_exits_two_before_anything_runs(self):
        completed, data = self.complement()
        self.assert_refused(completed, data, '--skip-covered')

    def test_an_invalid_file_exits_two_before_anything_runs(self):
        cases = {
            'não é JSON': b'{"complete": [',
            'não é UTF-8': b'{"complete": ["test_\xff"]}',
            'é uma lista': b'["test_coberto"]',
            'sem a chave': b'{}',
            'chave a mais': b'{"complete": [], "outra": []}',
            'chave repetida': b'{"complete": [], "complete": []}',
            'complete não é lista': b'{"complete": "test_coberto"}',
            'item não é texto': b'{"complete": [1]}',
            'item vazio': b'{"complete": [""]}',
            'item com NUL': b'{"complete": ["test_\\u0000x"]}',
            'item repetido': b'{"complete": ["test_coberto", "test_coberto"]}',
            'grande demais': json.dumps({'complete': [f'test_{index:07d}' for index in range(30000)]}).encode(),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                self.write_covered(raw=raw)
                completed, data = self.complement()
                self.assert_refused(completed, data, '--skip-covered')

    def test_together_with_impact_it_is_refused_with_exit_two(self):
        self.write_covered(COVERED)
        completed, data = self.complement(extra=['--impact', 'HEAD'])
        self.assert_refused(completed, data, '--impact')


if __name__ == '__main__':
    unittest.main()
