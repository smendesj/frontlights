"""A suíte roda pelo Frontlights e o portão diz se ela cobre a ponta (issue 52, S1).

`homolog suite` roda o argv de `homolog.suites.<modo>` do config (impacto ou completa) na worktree, grava a saída
num log e o registro `.frontlights/issues/<n>/suite.json` com o HEAD e a evidência da árvore; `homolog suite-gate`
compara esse registro com a ponta de agora: `current`, `stale`, `red`, `missing` ou `unconfigured`.

Seams: as linhas de comando `homolog suite` e `homolog suite-gate` (saída JSON e código de saída), chamadas como
subprocesso num repositório Git temporário, com um argv falso (um script Python mínimo que sai 0 ou 1, ou dorme).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOMOLOG = ROOT / 'skills' / 'frontlights' / 'scripts' / 'homolog.py'
FRONTLIGHTS = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'

# O argv falso: imprime os próprios argumentos e sai com o código pedido, ou dorme além do prazo.
FAKE = '''import sys, time
print('argumentos:', ' '.join(sys.argv[1:]))
if '--dorme' in sys.argv:
    time.sleep(30)
sys.exit(1 if '--falha' in sys.argv else 0)
'''

# O argv falso do relatório (issue 57, S3): `--copia <arquivo> <caminho>` copia os bytes do arquivo para o caminho
# que o `{report}` virou; sem `--copia`, não grava relatório nenhum.
REPORTER = '''import shutil, sys
if '--copia' in sys.argv:
    at = sys.argv.index('--copia')
    shutil.copyfile(sys.argv[at + 1], sys.argv[at + 2])
sys.exit(1 if '--falha' in sys.argv else 0)
'''


class SuiteTestCase(unittest.TestCase):
    """Um repositório temporário com um commit, um config fora dele e o argv falso fora dele."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.base / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0')
        (self.base / 'gitconfig').write_text('', encoding='utf-8')
        self.fake = self.base / 'fake_suite.py'
        self.fake.write_text(FAKE, encoding='utf-8')
        self.work = self.base / 'work'
        self.git(None, 'init', '-q', '-b', 'main', str(self.work))
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git(self.work, 'config', key, value)
        self.commit('app.txt', 'one\n', 'first')
        self.git(self.work, 'switch', '-q', '-c', 'claude/issue-7')
        self.commit('app.txt', 'two\n', 'issue 7')

    def git(self, cwd, *args):
        prefix = ['git', '-C', str(cwd)] if cwd else ['git']
        done = subprocess.run([*prefix, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=self.env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(done.returncode, 0, f'git {" ".join(args)}: {done.stderr}')
        return done

    def commit(self, name, content, message):
        (self.work / name).write_text(content, encoding='utf-8')
        self.git(self.work, 'add', name)
        self.git(self.work, 'commit', '-q', '-m', message)

    def argv(self, *flags):
        return [sys.executable, str(self.fake), *flags]

    def config(self, suites=None, timeout=60):
        """Writes the config outside the repository; `suites` maps a mode to the flags of the fake argv."""
        homolog = {'backupDir': None}
        if suites is not None:
            homolog['suites'] = {mode: {'argv': self.argv(*flags), 'timeoutSeconds': timeout}
                                 for mode, flags in suites.items()}
        path = self.base / 'config.json'
        path.write_text(json.dumps({'repository': None, 'homolog': homolog}), encoding='utf-8')
        return path

    def cli(self, *args, script=HOMOLOG):
        done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL, timeout=120)
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError:
            self.fail(f'sem JSON no stdout (saída {done.returncode}): {done.stdout!r} {done.stderr!r}')
        self.assertEqual(result['exitCode'], done.returncode)
        self.assertNotIn('Traceback', done.stderr)
        return done.returncode, result

    def suite(self, config, mode, *flags):
        return self.cli('suite', '--root', str(self.work), '--config', str(config), '--issue', '7',
                        '--mode', mode, *flags)

    def gate(self, config, *flags):
        return self.cli('suite-gate', '--root', str(self.work), '--config', str(config), '--issue', '7', *flags)

    @property
    def record(self):
        return self.work / '.frontlights' / 'issues' / '7' / 'suite.json'


class SuiteRunTests(SuiteTestCase):
    def test_without_the_mode_configured_nothing_runs_and_the_key_is_named(self):
        for suites in (None, {'full': ()}):
            with self.subTest(suites=suites):
                code, result = self.suite(self.config(suites), 'impact')
                self.assertEqual(code, 2)
                self.assertEqual(result['state'], 'unconfigured')
                self.assertIn('homolog.suites.impact', result['message'])
                self.assertFalse(self.record.exists())

    def test_impact_replaces_the_base_and_writes_the_record_with_the_tree_evidence(self):
        code, result = self.suite(self.config({'impact': ('--impacto', '{base}')}), 'impact', '--base', 'main')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['state'], 'green')
        saved = json.loads(self.record.read_text(encoding='utf-8'))
        self.assertEqual(saved, result['record'])
        self.assertEqual((saved['mode'], saved['base'], saved['exitCode'], saved['source']),
                         ('impact', 'main', 0, 'config'))
        self.assertEqual(saved['argv'], self.argv('--impacto', 'main'))
        head = self.git(self.work, 'rev-parse', 'HEAD').stdout.strip()
        self.assertEqual((saved['head'], saved['evidence']['head']), (head, head))
        for key in ('branch', 'diff_sha256', 'files_sha256'):
            self.assertIn(key, saved['evidence'])
        self.assertFalse(saved['concurrent'])
        self.assertIsInstance(saved['seconds'], (int, float))
        for key in ('startedAt', 'finishedAt'):
            self.assertRegex(saved[key], r'[+-]\d\d:\d\d$')
        log = Path(saved['output'])
        self.assertTrue(os.path.samefile(log.parent, self.record.parent))
        self.assertIn('argumentos: --impacto main', log.read_text(encoding='utf-8'))

    def test_the_base_defaults_to_main(self):
        code, result = self.suite(self.config({'impact': ('{base}',)}), 'impact')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['record']['argv'][-1], 'main')

    def test_a_failing_suite_is_red_and_exits_one(self):
        code, result = self.suite(self.config({'full': ('--falha',)}), 'full')
        self.assertEqual((code, result.get('state')), (1, 'red'))
        self.assertEqual(json.loads(self.record.read_text(encoding='utf-8'))['exitCode'], 1)

    def test_concurrent_is_recorded(self):
        code, result = self.suite(self.config({'full': ()}), 'full', '--concurrent')
        self.assertEqual(code, 0, result)
        self.assertTrue(json.loads(self.record.read_text(encoding='utf-8'))['concurrent'])

    def test_a_timeout_kills_the_suite_and_exits_one(self):
        code, result = self.suite(self.config({'full': ('--dorme',)}, timeout=1), 'full')
        self.assertEqual((code, result.get('state')), (1, 'red'))
        saved = json.loads(self.record.read_text(encoding='utf-8'))
        self.assertTrue(saved['timedOut'])
        self.assertIsNone(saved['exitCode'])
        self.assertLess(saved['seconds'], 20)

    def test_timeout_seconds_overrides_the_timeout_of_the_config(self):
        """Revisão da issue 52, M4: `--timeout-seconds` vale no lugar do `timeoutSeconds` do config: menor que a
        duração da suíte, ela é interrompida; o config dava 60 s, que bastariam."""
        code, result = self.suite(self.config({'full': ('--dorme',)}, timeout=60), 'full', '--timeout-seconds', '1')
        self.assertEqual((code, result.get('state')), (1, 'red'), result)
        saved = json.loads(self.record.read_text(encoding='utf-8'))
        self.assertTrue(saved['timedOut'])
        self.assertLess(saved['seconds'], 20)
        self.assertIn('1 s', result['message'])

    def test_a_timeout_keeps_the_partial_output_in_the_log(self):
        """Revisão da issue 52, B1: interrompida no prazo, a suíte deixa no log o que já tinha impresso, seguido da
        frase do prazo, como a saída parcial do `tests/suite.py`."""
        partial = self.base / 'partial_suite.py'
        partial.write_text("import time\nprint('linha antes do prazo', flush=True)\ntime.sleep(30)\n",
                           encoding='utf-8')
        given = json.dumps([sys.executable, str(partial)])
        code, result = self.suite(self.config(), 'full', '--argv', given, '--timeout-seconds', '3')
        self.assertEqual((code, result.get('state')), (1, 'red'), result)
        log = Path(json.loads(self.record.read_text(encoding='utf-8'))['output']).read_text(encoding='utf-8')
        self.assertIn('linha antes do prazo', log)
        self.assertIn('A suíte passou de 3 s e foi interrompida.', log)
        self.assertLess(log.index('linha antes do prazo'), log.index('A suíte passou de 3 s'))

    def test_timeout_seconds_larger_than_the_suite_lets_it_pass_even_with_an_argv(self):
        """M4: com `--argv` e o config dando 1 s, `--timeout-seconds 60` deixa terminar uma suíte de 3 s."""
        slow = self.base / 'slow_suite.py'
        slow.write_text('import time\ntime.sleep(3)\n', encoding='utf-8')
        given = json.dumps([sys.executable, str(slow)])
        config = self.config({'full': ('--dorme',)}, timeout=1)
        code, result = self.suite(config, 'full', '--argv', given, '--timeout-seconds', '60')
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertFalse(json.loads(self.record.read_text(encoding='utf-8'))['timedOut'])

    def test_the_full_suite_without_a_configured_timeout_gets_an_hour(self):
        """M4: a suíte inteira sem `timeoutSeconds` no config (pelo `--argv`, ou declarada sem prazo) tem 3600 s,
        não os 600 s de `checks`, que mataram a suíte inteira real; a de impacto mantém o padrão de `checks`."""
        sys.path.insert(0, str(HOMOLOG.parent))
        self.addCleanup(sys.path.remove, str(HOMOLOG.parent))
        import checks
        import homolog
        argv = json.dumps(self.argv())
        bare = {'repository': None, 'homolog': {'backupDir': None}}
        declared = {'repository': None, 'homolog': {'suites': {'full': {'argv': self.argv()},
                                                               'impact': {'argv': self.argv()}}}}
        self.assertEqual(homolog.suite_run_settings(bare, 'full', argv)[0]['timeout'], 3600)
        self.assertEqual(homolog.suite_run_settings(declared, 'full', None)[0]['timeout'], 3600)
        self.assertEqual(homolog.suite_run_settings(declared, 'full', argv)[0]['timeout'], 3600)
        self.assertEqual(homolog.suite_run_settings(declared, 'impact', None)[0]['timeout'], checks.DEFAULT_TIMEOUT)
        self.assertEqual(homolog.suite_run_settings(bare, 'full', argv, '120')[0]['timeout'], 120)

    def test_a_non_positive_timeout_seconds_is_refused_and_nothing_runs(self):
        for value in ('0', '-5', 'dez', '1.5'):
            with self.subTest(value=value):
                code, result = self.suite(self.config({'full': ()}), 'full', f'--timeout-seconds={value}')
                self.assertEqual(code, 1, result)
                self.assertIn('--timeout-seconds precisa ser um inteiro positivo', result['message'])
                self.assertFalse(self.record.exists())

    def test_a_full_argv_given_once_runs_without_the_config_and_is_recorded_as_argument(self):
        given = json.dumps(self.argv('--uma-vez'))
        code, result = self.suite(self.config(), 'full', '--argv', given)
        self.assertEqual(code, 0, result)
        saved = json.loads(self.record.read_text(encoding='utf-8'))
        self.assertEqual((saved['source'], saved['argv']), ('argument', self.argv('--uma-vez')))
        gate_code, gate = self.gate(self.config())
        self.assertEqual((gate_code, gate.get('status')), (0, 'current'))

    def test_an_argv_with_impact_is_refused_and_nothing_runs(self):
        code, result = self.suite(self.config({'impact': ()}), 'impact', '--argv', json.dumps(self.argv()))
        self.assertEqual(code, 1)
        self.assertIn('--argv', result['message'])
        self.assertFalse(self.record.exists())

    def test_a_malformed_suite_in_the_config_is_refused(self):
        path = self.base / 'config.json'
        for suites in ({'impact': {'argv': 'python -m unittest'}}, {'impact': {'argv': ['cmd', '/c', 'x']}},
                       {'full': {'argv': ['python'], 'timeoutSeconds': 0}}, {'outra': {'argv': ['python']}},
                       {'full': {'argv': ['python'], 'extra': 1}}, ['python']):
            with self.subTest(suites=suites):
                path.write_text(json.dumps({'repository': None, 'homolog': {'suites': suites}}), encoding='utf-8')
                code, result = self.suite(path, 'full')
                self.assertEqual(code, 1)
                self.assertIn('homolog.suites', result['message'])
                self.assertFalse(self.record.exists())

    def test_the_route_through_frontlights_gives_the_same_answer(self):
        config = self.config()
        direct = self.suite(config, 'full')
        routed = self.cli('homolog', 'suite', '--root', str(self.work), '--config', str(config), '--issue', '7',
                          '--mode', 'full', script=FRONTLIGHTS)
        self.assertEqual(direct[0], 2)
        self.assertEqual(direct[1].get('state'), 'unconfigured')
        self.assertEqual(routed, direct)


class SuiteReportTests(SuiteTestCase):
    """Issue 57, S3: com `{report}` no argv de `homolog.suites.impact`, a suíte grava num arquivo novo da pasta da
    issue a lista do que rodou (`ran`) e do que rodou por inteiro (`complete`), e o `suite.json` a guarda."""

    TODAY = {'mode', 'source', 'base', 'argv', 'head', 'evidence', 'exitCode', 'timedOut', 'seconds', 'output',
             'concurrent', 'startedAt', 'finishedAt'}
    VALID = {'ran': ['tests.test_a', 'tests.test_b.Classe.test_um'], 'complete': ['tests.test_a']}

    def setUp(self):
        super().setUp()
        self.reporter = self.base / 'report_suite.py'
        self.reporter.write_text(REPORTER, encoding='utf-8')

    def payload(self, content):
        """A file outside the repository with `content` (bytes as is, anything else as JSON) for the fake to copy."""
        path = self.base / f'payload-{len(list(self.base.glob("payload-*")))}.json'
        path.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode('utf-8'))
        return path

    def report_config(self, *flags, mode='impact'):
        path = self.base / 'config.json'
        suites = {mode: {'argv': [sys.executable, str(self.reporter), *flags], 'timeoutSeconds': 60}}
        path.write_text(json.dumps({'repository': None, 'homolog': {'suites': suites}}), encoding='utf-8')
        return path

    def run_with(self, content, *flags):
        copy = ('--copia', str(self.payload(content)), '{report}') if content is not None else ('{report}',)
        return self.suite(self.report_config(*flags, *copy, '--base', '{base}'), 'impact')

    def saved(self):
        return json.loads(self.record.read_text(encoding='utf-8'))

    def test_a_valid_report_gives_ran_and_complete_in_the_record(self):
        for name, content in (('utf-8', self.VALID),
                              ('utf-8-sig', b'\xef\xbb\xbf' + json.dumps(self.VALID).encode('utf-8'))):
            with self.subTest(encoding=name):
                code, result = self.run_with(content)
                self.assertEqual((code, result.get('state')), (0, 'green'), result)
                saved = self.saved()
                self.assertEqual(saved, result['record'])
                self.assertEqual((saved['ran'], saved['complete']), (self.VALID['ran'], self.VALID['complete']))
                report = Path(saved['report'])
                self.assertTrue(report.is_absolute())
                self.assertTrue(os.path.samefile(report.parent, self.record.parent))
                self.assertRegex(report.name, r'^suite-report-\d{8}-\d{6}(-\d+)?\.json$')
                self.assertEqual(saved['argv'][-3:], [str(report), '--base', 'main'])
                self.assertNotIn('warnings', saved)
                gate_code, gate = self.gate(self.report_config('{report}'))
                self.assertEqual((gate_code, gate.get('status')), (0, 'current'), gate)

    def test_a_report_with_the_usual_keys_of_the_runner_still_gives_ran_and_complete(self):
        """Revisão da issue 57, rodada 1, S1: o `--report` do `tests/suite.py --impact` grava `ran` e `complete`
        junto das chaves de sempre (version, modules, totals, mode, impact...); o registro pega `ran` e `complete` e
        ignora o resto."""
        content = dict(self.VALID, version=1, started_at='2026-10-19T10:00:00.000-03:00',
                       finished_at='2026-10-19T10:00:01.000-03:00', seconds=1.0, head='0' * 40, variable=None,
                       workers=4, module_timeout=900, tests_dir='tests', modules=[{'name': 'tests.test_a'}],
                       totals={'modules': 1, 'tests_run': 3, 'skipped': 0, 'failures': 0, 'errors': 0,
                               'infrastructure': 0},
                       result='ok', exit_code=0, mode='impact', base='main', base_commit='1' * 40,
                       changed=['app.txt'], impact=[{'name': 'tests.test_a', 'selected': True, 'reason': 'mudou',
                                                     'classes': None}])
        code, result = self.run_with(content)
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        saved = self.saved()
        self.assertEqual((saved.get('ran'), saved.get('complete')), (self.VALID['ran'], self.VALID['complete']),
                         saved.get('warnings'))
        self.assertNotIn('warnings', saved)
        for key in ('version', 'modules', 'totals', 'impact', 'changed', 'base_commit'):
            with self.subTest(key=key):
                self.assertNotIn(key, saved)

    @unittest.skipUnless(os.name == 'nt', 'o runner tests/suite.py só roda no Windows')
    def test_the_real_runner_with_impact_and_report_gives_ran_and_complete_in_the_record(self):
        """Revisão da issue 57, rodada 1, S1: o argv do config real (`python tests/suite.py --impact {base}
        --report {report}`), sobre uma pasta `tests/` mínima do repositório temporário, deixa `ran` e `complete` no
        `suite.json`: o módulo que a issue mudou rodou inteiro, o que ela não toca ficou de fora."""
        tests = self.work / 'tests'
        tests.mkdir()
        case = 'import unittest\n\n\nclass Caso(unittest.TestCase):\n    def test_ok(self):\n        pass\n'
        self.git(self.work, 'switch', '-q', 'main')
        (tests / 'test_parado.py').write_text(case, encoding='utf-8')
        self.git(self.work, 'add', 'tests')
        self.git(self.work, 'commit', '-q', '-m', 'test_parado na main')
        self.git(self.work, 'switch', '-q', 'claude/issue-7')
        self.git(self.work, 'merge', '-q', '--no-edit', 'main')
        self.commit('tests/test_mudado.py', case, 'test_mudado na issue')
        path = self.base / 'config.json'
        argv = [sys.executable, str(ROOT / 'tests' / 'suite.py'), '--tests-dir', str(tests), '--serial=',
                '--workers', '1', '--impact', '{base}', '--report', '{report}']
        path.write_text(json.dumps({'repository': None, 'homolog': {
            'suites': {'impact': {'argv': argv, 'timeoutSeconds': 120}}}}), encoding='utf-8')
        code, result = self.suite(path, 'impact', '--base', 'main')
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        saved = self.saved()
        self.assertEqual((saved.get('ran'), saved.get('complete')), (['test_mudado'], ['test_mudado']),
                         saved.get('warnings'))
        self.assertNotIn('warnings', saved)

    def test_a_failed_run_keeps_its_exit_code_and_still_records_the_report(self):
        code, result = self.run_with(self.VALID, '--falha')
        self.assertEqual((code, result.get('state')), (1, 'red'), result)
        saved = self.saved()
        self.assertEqual((saved['exitCode'], saved['ran']), (1, self.VALID['ran']))

    def test_a_missing_oversized_or_invalid_report_is_a_warning_without_the_lists(self):
        cases = {
            'ausente': None,
            'grande': b' ' * (2 * 1024 * 1024 + 1),
            'não JSON': b'{"ran": [',
            'utf-16': json.dumps(self.VALID).encode('utf-16'),
            'lista': ['tests.test_a'],
            'sem complete': {'ran': ['tests.test_a']},
            'sem ran, com outras chaves': {'complete': [], 'version': 1, 'mode': 'impact'},
            'complete não lista': {'ran': ['tests.test_a'], 'complete': 'tests.test_a'},
            'ran não lista': {'ran': 'tests.test_a', 'complete': []},
            'id vazio': {'ran': [''], 'complete': []},
            'id não texto': {'ran': [7], 'complete': []},
            'NUL': {'ran': ['tests.test_a\0'], 'complete': []},
            'duplicado em ran': {'ran': ['tests.test_a', 'tests.test_a'], 'complete': []},
            'duplicado em complete': {'ran': ['tests.test_a'], 'complete': ['tests.test_a', 'tests.test_a']},
            'complete fora de ran': {'ran': ['tests.test_a'], 'complete': ['tests.test_b']},
        }
        for name, content in cases.items():
            with self.subTest(report=name):
                code, result = self.run_with(content)
                self.assertEqual((code, result.get('state')), (0, 'green'), result)
                saved = self.saved()
                self.assertNotIn('ran', saved)
                self.assertNotIn('complete', saved)
                self.assertTrue(os.path.samefile(Path(saved['report']).parent, self.record.parent))
                self.assertTrue(any('relatório' in warning and saved['report'] in warning
                                    for warning in saved.get('warnings', [])), saved.get('warnings'))
                gate_code, gate = self.gate(self.report_config('{report}'))
                self.assertEqual((gate_code, gate.get('status')), (0, 'current'), gate)

    def test_without_the_marker_the_record_is_the_one_of_today(self):
        code, result = self.suite(self.report_config('--base', '{base}'), 'impact')
        self.assertEqual(code, 0, result)
        self.assertEqual(set(self.saved()), self.TODAY)
        self.assertEqual(list(self.record.parent.glob('suite-report-*')), [])

    def test_the_marker_out_of_its_place_in_the_config_is_refused_and_nothing_runs(self):
        for name, flags, mode in (('na suíte inteira', ('{report}',), 'full'),
                                  ('dentro de um argumento', ('--saida={report}',), 'impact'),
                                  ('duas vezes', ('{report}', '{report}'), 'impact')):
            with self.subTest(case=name):
                code, result = self.suite(self.report_config(*flags, mode=mode), mode)
                self.assertEqual(code, 1, result)
                self.assertIn('{report}', result['message'])
                self.assertIn(f'homolog.suites.{mode}.argv', result['message'])
                self.assertFalse(self.record.exists())

    def test_the_marker_in_a_given_argv_is_refused(self):
        given = json.dumps([sys.executable, str(self.reporter), '{report}'])
        code, result = self.suite(self.config(), 'full', '--argv', given)
        self.assertEqual(code, 1, result)
        self.assertIn('{report}', result['message'])
        self.assertIn('--argv', result['message'])
        self.assertFalse(self.record.exists())


class SuiteInspectTests(SuiteTestCase):
    def inspect(self, config):
        return subprocess.run([sys.executable, str(FRONTLIGHTS), 'inspect', '--config', str(config), '--root',
                               str(self.work)], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=self.env, stdin=subprocess.DEVNULL, timeout=120)

    def test_inspect_accepts_the_suites_and_refuses_a_malformed_one(self):
        accepted = self.inspect(self.config({'impact': ('{base}',), 'full': ()}))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        path = self.base / 'config.json'
        path.write_text(json.dumps({'repository': None, 'homolog': {'suites': {'full': {'argv': 'python x.py'}}}}),
                        encoding='utf-8')
        refused = self.inspect(path)
        self.assertEqual(refused.returncode, 1)
        self.assertNotIn('Traceback', refused.stderr)
        self.assertIn('homolog.suites.full.argv', json.loads(refused.stderr)['error'])

    def test_inspect_accepts_the_report_marker_only_in_the_impact_suite(self):
        """Issue 57, S3: `{report}` vale como argumento inteiro de `homolog.suites.impact.argv`; na suíte inteira,
        o inspect recusa o config."""
        accepted = self.inspect(self.config({'impact': ('{report}', '{base}'), 'full': ()}))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        refused = self.inspect(self.config({'impact': (), 'full': ('{report}',)}))
        self.assertEqual(refused.returncode, 1)
        self.assertNotIn('Traceback', refused.stderr)
        error = json.loads(refused.stderr)['error']
        self.assertIn('homolog.suites.full.argv', error)
        self.assertIn('{report}', error)

    def test_the_example_config_gives_the_suites_room_for_their_measured_duration(self):
        """Revisão da issue 52, M3: a suíte inteira levou 934 s com a máquina quieta e 28 min carregada; os prazos
        do config de exemplo cobrem isso (impacto 2400 s). A inteira passou de 3600 s sob carga numa release de
        19/10/2026, então o exemplo dá 5400 s."""
        example = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))
        suites = example['homolog']['suites']
        self.assertEqual((suites['impact']['timeoutSeconds'], suites['full']['timeoutSeconds']), (2400, 5400))


class SuiteGateTests(SuiteTestCase):
    def ran(self, mode='impact', *flags):
        config = self.config({mode: flags})
        code, result = self.suite(config, mode)
        self.assertEqual(code, 1 if '--falha' in flags else 0, result)
        return config

    def test_a_green_record_of_the_tip_is_current(self):
        config = self.ran()
        code, result = self.gate(config)
        self.assertEqual((code, result.get('status')), (0, 'current'))
        self.assertEqual(result['mode'], 'impact')

    def test_a_commit_after_the_run_makes_it_stale(self):
        config = self.ran()
        self.commit('app.txt', 'three\n', 'after the suite')
        code, result = self.gate(config)
        self.assertEqual((code, result.get('status')), (2, 'stale'))
        self.assertIn('head', result['changed'])

    def test_an_uncommitted_edit_after_the_run_makes_it_stale(self):
        config = self.ran()
        (self.work / 'app.txt').write_text('edited\n', encoding='utf-8')
        code, result = self.gate(config)
        self.assertEqual((code, result.get('status')), (2, 'stale'))
        self.assertNotIn('head', result['changed'])
        self.assertEqual(result['files_changed'], ['app.txt'])

    def test_a_failed_suite_of_the_tip_is_red(self):
        config = self.ran('full', '--falha')
        code, result = self.gate(config)
        self.assertEqual((code, result.get('status')), (2, 'red'))

    def test_without_a_record_it_is_missing(self):
        code, result = self.gate(self.config({'impact': ()}))
        self.assertEqual((code, result.get('status')), (2, 'missing'))

    def test_without_a_record_and_without_suites_it_is_unconfigured(self):
        code, result = self.gate(self.config())
        self.assertEqual((code, result.get('status')), (2, 'unconfigured'))

    def test_require_full_does_not_take_an_impact_record(self):
        config = self.ran()
        code, result = self.gate(config, '--require', 'full')
        self.assertEqual(code, 2)
        self.assertNotEqual(result['status'], 'current')
        self.assertEqual(result['mode'], 'impact')
        full = self.ran('full')
        code, result = self.gate(full, '--require', 'full')
        self.assertEqual((code, result.get('status')), (0, 'current'))


class SuiteReleaseTests(SuiteTestCase):
    """S3: a suíte inteira da release roda na worktree principal, na main local, e grava
    `.frontlights/release/suite.json`; só a suíte completa, só na ponta da base."""

    def setUp(self):
        super().setUp()
        self.git(self.work, 'switch', '-q', 'main')

    def release(self, config, *flags):
        return self.cli('suite', '--root', str(self.work), '--config', str(config), '--release', *flags)

    def release_gate(self, config, *flags):
        return self.cli('suite-gate', '--root', str(self.work), '--config', str(config), '--release', *flags)

    @property
    def release_record(self):
        return self.work / '.frontlights' / 'release' / 'suite.json'

    def test_release_writes_the_record_of_the_release_folder(self):
        code, result = self.release(self.config({'full': ()}), '--mode', 'full')
        self.assertEqual(code, 0, result)
        saved = json.loads(self.release_record.read_text(encoding='utf-8'))
        self.assertEqual((saved['mode'], saved['head']), ('full', self.git(self.work, 'rev-parse', 'main').stdout.strip()))
        self.assertTrue(os.path.samefile(Path(saved['output']).parent, self.release_record.parent))
        self.assertFalse(self.record.exists())

    def test_release_refuses_the_impact_suite_and_runs_nothing(self):
        code, result = self.release(self.config({'impact': (), 'full': ()}), '--mode', 'impact')
        self.assertEqual(code, 1, result)
        self.assertIn('--mode full', result['message'])
        self.assertFalse(self.release_record.exists())

    def test_release_off_the_base_branch_is_refused_and_runs_nothing(self):
        config = self.config({'full': ()})
        for target in ('claude/issue-7', '--detach main'):
            with self.subTest(target=target):
                self.git(self.work, 'switch', '-q', *target.split())
                code, result = self.release(config, '--mode', 'full')
                self.assertEqual(code, 1, result)
                self.assertIn('main', result['message'])
                self.assertFalse(self.release_record.exists())
        self.git(self.work, 'switch', '-q', 'main')
        code, result = self.release(config, '--mode', 'full', '--base', 'claude/issue-7')
        self.assertEqual(code, 1, result)
        self.assertFalse(self.release_record.exists())

    def test_issue_and_release_together_are_refused(self):
        config = self.config({'full': ()})
        for operation, flags in (('suite', ('--mode', 'full')), ('suite-gate', ())):
            with self.subTest(operation=operation):
                code, result = self.cli(operation, '--root', str(self.work), '--config', str(config), '--issue', '7',
                                        '--release', *flags)
                self.assertEqual(code, 1, result)
                self.assertIn('--release', result['message'])
                self.assertFalse(self.release_record.exists())
                self.assertFalse(self.record.exists())

    def test_the_gate_of_the_release_reads_the_release_record(self):
        config = self.config({'full': ()})
        code, result = self.release(config, '--mode', 'full')
        self.assertEqual(code, 0, result)
        code, gate = self.release_gate(config)
        self.assertEqual((code, gate.get('status'), gate.get('mode')), (0, 'current', 'full'), gate)
        self.assertTrue(os.path.samefile(gate['recordPath'], self.release_record))
        self.commit('app.txt', 'three\n', 'after the release suite')
        code, gate = self.release_gate(config)
        self.assertEqual((code, gate.get('status')), (2, 'stale'), gate)

    def tip_record(self, head):
        return self.work / '.frontlights' / 'release' / f'suite-{head}.json'

    def test_two_release_runs_at_two_tips_keep_both_per_tip_records(self):
        """Revisão da issue 52, rodada 2: a suíte da release guarda também uma cópia por ponta,
        `release/suite-<sha>.json`, que a rodada numa ponta seguinte não sobrescreve; `suite.json` fica a última."""
        config = self.config({'full': ()})
        first = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.assertEqual(self.release(config, '--mode', 'full')[0], 0)
        self.commit('app.txt', 'three\n', 'another issue in the local main')
        second = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.assertEqual(self.release(config, '--mode', 'full')[0], 0)
        for head in (first, second):
            with self.subTest(head=head):
                saved = json.loads(self.tip_record(head).read_text(encoding='utf-8'))
                self.assertEqual((saved['mode'], saved['head'], saved['exitCode']), ('full', head, 0))
        self.assertEqual(json.loads(self.release_record.read_text(encoding='utf-8'))['head'], second)

    def test_the_gate_of_a_given_tip_stays_current_after_the_local_main_moves_on(self):
        """Rodada 2: a PR da release A espera; outra issue entra na main local e a suíte roda de novo para a próxima
        release. `suite-gate --release --head <ponta de A>` segue `current`, mesmo com a worktree principal noutra
        ponta; sem `--head`, o último registro é julgado como antes."""
        config = self.config({'full': ()})
        first = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.assertEqual(self.release(config, '--mode', 'full')[0], 0)
        self.commit('app.txt', 'three\n', 'another issue in the local main')
        self.assertEqual(self.release(config, '--mode', 'full')[0], 0)
        self.commit('app.txt', 'four\n', 'yet another issue')
        self.git(self.work, 'switch', '-q', 'claude/issue-7')
        code, gate = self.release_gate(config, '--head', first)
        self.assertEqual((code, gate.get('status'), gate.get('head')), (0, 'current', first), gate)
        self.assertTrue(os.path.samefile(gate['recordPath'], self.tip_record(first)))
        code, latest = self.release_gate(config)
        self.assertEqual(code, 1, latest)

    def test_the_gate_of_an_unknown_tip_is_missing_and_a_failed_one_is_red(self):
        config = self.config({'full': ()})
        unknown = 'a' * 40
        code, gate = self.release_gate(config, '--head', unknown)
        self.assertEqual((code, gate.get('status'), gate.get('head')), (2, 'missing', unknown), gate)
        failing = self.config({'full': ('--falha',)})
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.assertEqual(self.release(failing, '--mode', 'full')[0], 1)
        code, gate = self.release_gate(config, '--head', head)
        self.assertEqual((code, gate.get('status')), (2, 'red'), gate)

    def test_release_with_a_tracked_uncommitted_edit_is_refused_and_runs_nothing(self):
        """Revisão da issue 52, rodada 3: a suíte da release roda só numa árvore limpa; uma edição não commitada
        num arquivo versionado (staged ou não) é recusada, nada roda e nenhum registro da ponta é gravado."""
        config = self.config({'full': ()})
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        for staged in (False, True):
            with self.subTest(staged=staged):
                (self.work / 'app.txt').write_text('edição não commitada\n', encoding='utf-8')
                if staged:
                    self.git(self.work, 'add', 'app.txt')
                code, result = self.release(config, '--mode', 'full')
                self.assertEqual(code, 1, result)
                self.assertIn('app.txt', result['message'])
                self.assertFalse(self.release_record.exists())
                self.assertFalse(self.tip_record(head).exists())
                self.git(self.work, 'reset', '-q', '--hard')

    def test_release_with_an_untracked_file_outside_frontlights_is_refused(self):
        config = self.config({'full': ()})
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        (self.work / 'pasta').mkdir()
        (self.work / 'pasta' / 'novo.txt').write_text('não versionado\n', encoding='utf-8')
        code, result = self.release(config, '--mode', 'full')
        self.assertEqual(code, 1, result)
        self.assertIn('pasta/novo.txt', result['message'])
        self.assertFalse(self.release_record.exists())
        self.assertFalse(self.tip_record(head).exists())

    def test_a_file_under_frontlights_does_not_block_the_release_suite(self):
        config = self.config({'full': ()})
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        (self.work / '.frontlights').mkdir()
        (self.work / '.frontlights' / 'notas.txt').write_text('registro local\n', encoding='utf-8')
        code, result = self.release(config, '--mode', 'full')
        self.assertEqual(code, 0, result)
        self.assertTrue(self.tip_record(head).exists())

    def test_the_gate_of_a_tip_whose_record_carries_uncommitted_changes_is_missing(self):
        """Defesa em profundidade: um registro por ponta cuja evidência mostra diff não vazio, ou um arquivo fora do
        commit, não vale pela ponta; `suite-gate --release --head` responde missing."""
        import hashlib
        config = self.config({'full': ()})
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.assertEqual(self.release(config, '--mode', 'full')[0], 0)
        clean = json.loads(self.tip_record(head).read_text(encoding='utf-8'))
        dirty_diff = json.loads(json.dumps(clean))
        dirty_diff['evidence']['diff_sha256'] = hashlib.sha256(b'diff --git a/app.txt b/app.txt\n').hexdigest()
        untracked = json.loads(json.dumps(clean))
        untracked['evidence']['files']['solto.txt'] = hashlib.sha256(b'solto\n').hexdigest()
        for name, record in (('diff', dirty_diff), ('untracked', untracked)):
            with self.subTest(record=name):
                self.tip_record(head).write_text(json.dumps(record), encoding='utf-8')
                code, gate = self.release_gate(config, '--head', head)
                self.assertEqual((code, gate.get('status')), (2, 'missing'), gate)
                self.assertIn('não commitad', gate['message'])

    def test_head_needs_the_release_and_a_full_sha(self):
        config = self.config({'full': ()})
        code, result = self.cli('suite-gate', '--root', str(self.work), '--config', str(config), '--issue', '7',
                                '--head', 'a' * 40)
        self.assertEqual(code, 1, result)
        self.assertIn('--head só vale com --release', result['message'])
        for head in ('abc1234', 'z' * 40, '../' + 'a' * 37):
            with self.subTest(head=head):
                code, result = self.release_gate(config, '--head', head)
                self.assertEqual(code, 1, result)
                self.assertIn('sha completo', result['message'])


class AdoptionTestCase(SuiteTestCase):
    """Issue 54: a release adota, sem rodar nada, a suíte inteira verde que uma issue rodou numa árvore limpa cuja
    árvore de commit é a mesma da ponta da main local (`homolog suite --release --mode full --from <registro>`).

    A issue 7 roda a suíte inteira na ponta dela e entra na main local por `--no-ff`, sem mudar arquivo; o config da
    release declara uma suíte que falharia, de modo que uma execução de verdade daria vermelho."""

    def setUp(self):
        super().setUp()
        code, result = self.suite(self.config({'full': ()}), 'full')
        self.assertEqual(code, 0, result)
        self.source = self.record
        self.issue_head = self.git(self.work, 'rev-parse', 'HEAD').stdout.strip()
        self.issue_tree = self.git(self.work, 'rev-parse', 'HEAD^{tree}').stdout.strip()
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', 'merge of issue 7 into the local main', 'claude/issue-7')
        self.main_head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        self.failing = self.config({'full': ('--falha',)})

    @property
    def release_folder(self):
        return self.work / '.frontlights' / 'release'

    def adopt(self, *flags, source=None, config=None):
        return self.cli('suite', '--root', str(self.work), '--config', str(config or self.failing), '--release',
                        '--mode', 'full', '--from', str(source or self.source), *flags)

    def release_gate(self, *flags):
        return self.cli('suite-gate', '--root', str(self.work), '--config', str(self.failing), '--release', *flags)



class SuiteAdoptionTests(AdoptionTestCase):
    def test_a_green_full_record_of_the_same_tree_is_adopted_without_running(self):
        """S1: os dois registros da release são gravados com a evidência da main local e `adoptedFrom`, nada roda
        (nenhum log na pasta da release), e os dois juízes da release respondem `current`."""
        self.assertNotEqual(self.main_head, self.issue_head)
        code, result = self.adopt()
        self.assertEqual((code, result.get('state')), (0, 'adopted'), result)
        for path in (self.release_folder / 'suite.json', self.release_folder / f'suite-{self.main_head}.json'):
            with self.subTest(record=path.name):
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual((saved['mode'], saved['head'], saved['exitCode'], saved['timedOut']),
                                 ('full', self.main_head, 0, False))
                self.assertEqual((saved['evidence']['head'], saved['evidence']['branch']), (self.main_head, 'main'))
                adopted = saved['adoptedFrom']
                self.assertTrue(os.path.samefile(adopted['path'], self.source))
                self.assertEqual((adopted['head'], adopted['tree']), (self.issue_head, self.issue_tree))
        self.assertEqual(list(self.release_folder.glob('*.log')), [])
        code, gate = self.release_gate()
        self.assertEqual((code, gate.get('status')), (0, 'current'), gate)
        code, gate = self.release_gate('--head', self.main_head)
        self.assertEqual((code, gate.get('status')), (0, 'current'), gate)

    def test_the_gate_of_the_adopted_tip_names_the_origin(self):
        """S3: `suite-gate --release --head` repassa `adoptedFrom` e diz de qual ponta a suíte foi adotada."""
        self.assertEqual(self.adopt()[0], 0)
        code, gate = self.release_gate('--head', self.main_head)
        self.assertEqual((code, gate.get('status')), (0, 'current'), gate)
        self.assertEqual((gate['adoptedFrom']['head'], gate['adoptedFrom']['tree']), (self.issue_head, self.issue_tree))
        self.assertTrue(os.path.samefile(gate['adoptedFrom']['path'], self.source))
        self.assertIn(f'adotada da ponta {self.issue_head[:7]}', gate['message'])


class SuiteAdoptionRefusalTests(AdoptionTestCase):
    """S2: `--from` recusa, sem gravar nada, o registro que não vale pela ponta da main local."""

    def forged(self, evidence=None, **changes):
        """A copy of the issue's green record, outside the repository, with `changes` (and `evidence` keys)."""
        record = json.loads(self.source.read_text(encoding='utf-8'))
        record.update(changes)
        record['evidence'].update(evidence or {})
        path = self.base / f'origem-{len(list(self.base.glob("origem-*.json")))}.json'
        path.write_text(json.dumps(record), encoding='utf-8')
        return path

    def assert_refused_without_writing(self, needle, *flags, source=None):
        code, result = self.adopt(*flags, source=source)
        self.assertEqual(code, 1, result)
        self.assertIn(needle, result['message'])
        self.assertIn('nada foi gravado', result['message'])
        self.assertFalse((self.release_folder / 'suite.json').exists())
        self.assertFalse((self.release_folder / f'suite-{self.main_head}.json').exists())

    def test_a_record_of_the_impact_suite_is_refused(self):
        self.assert_refused_without_writing('suíte por impacto', source=self.forged(mode='impact'))

    def test_a_red_a_timed_out_or_a_failed_to_start_record_is_refused(self):
        for name, changes in (('red', {'exitCode': 1}), ('timeout', {'exitCode': None, 'timedOut': True}),
                              ('error', {'exitCode': None, 'error': 'executable_missing'})):
            with self.subTest(record=name):
                self.assert_refused_without_writing('não passou', source=self.forged(**changes))

    def test_a_record_run_with_a_diff_or_a_file_outside_the_commit_is_refused(self):
        import hashlib
        files = dict(json.loads(self.source.read_text(encoding='utf-8'))['evidence']['files'],
                     **{'solto.txt': hashlib.sha256(b'solto\n').hexdigest()})
        diff = hashlib.sha256(b'diff --git a/app.txt b/app.txt\n').hexdigest()
        for name, evidence in (('diff', {'diff_sha256': diff}), ('untracked', {'files': files})):
            with self.subTest(record=name):
                self.assert_refused_without_writing('não commitad', source=self.forged(evidence))

    def test_a_record_whose_head_the_repository_does_not_know_is_refused(self):
        for head in ('a' * 40, 'main'):
            with self.subTest(head=head):
                self.assert_refused_without_writing('não conhece', source=self.forged({'head': head}, head=head))

    def test_a_record_of_another_commit_tree_is_refused(self):
        """A suíte rodou no primeiro commit da main, cuja árvore não é a da ponta da main local."""
        first = self.git(self.work, 'rev-parse', 'main~1').stdout.strip()
        self.assert_refused_without_writing('outra árvore', source=self.forged({'head': first}, head=first))

    def test_a_record_whose_file_hashes_differ_is_refused_and_the_release_records_stay_as_they_were(self):
        """Mesma árvore de commit, mas o hash dos arquivos da evidência não é o da main local agora: recusado, e os
        registros que uma adoção anterior gravou ficam byte a byte como estavam."""
        self.assertEqual(self.adopt()[0], 0)
        records = (self.release_folder / 'suite.json', self.release_folder / f'suite-{self.main_head}.json')
        before = [path.read_bytes() for path in records]
        code, result = self.adopt(source=self.forged({'files_sha256': 'b' * 64}))
        self.assertEqual(code, 1, result)
        self.assertIn('hash dos arquivos', result['message'])
        self.assertIn('nada foi gravado', result['message'])
        self.assertEqual([path.read_bytes() for path in records], before)

    def test_from_with_argv_or_timeout_seconds_is_refused(self):
        for flags in (('--argv', json.dumps(self.argv())), ('--timeout-seconds', '30')):
            with self.subTest(flag=flags[0]):
                self.assert_refused_without_writing(flags[0], *flags)

    def test_from_without_the_release_is_refused(self):
        code, result = self.cli('suite', '--root', str(self.work), '--config', str(self.failing), '--issue', '7',
                                '--mode', 'full', '--from', str(self.source))
        self.assertEqual(code, 1, result)
        self.assertIn('--from só vale com --release', result['message'])
        self.assertEqual(json.loads(self.source.read_text(encoding='utf-8'))['head'], self.issue_head)

    def test_a_path_without_a_suite_record_is_refused(self):
        missing = self.base / 'nao-existe.json'
        self.assert_refused_without_writing('não há registro de suíte', source=missing)

    def test_off_the_tip_or_with_the_local_main_dirty_the_refusals_of_today_hold(self):
        self.git(self.work, 'switch', '-q', 'claude/issue-7')
        code, result = self.adopt()
        self.assertEqual(code, 1, result)
        self.assertIn('não na main local', result['message'])
        self.git(self.work, 'switch', '-q', 'main')
        (self.work / 'app.txt').write_text('edição não commitada\n', encoding='utf-8')
        code, result = self.adopt()
        self.assertEqual(code, 1, result)
        self.assertIn('app.txt', result['message'])
        self.assertFalse((self.release_folder / 'suite.json').exists())
        self.assertFalse((self.release_folder / f'suite-{self.main_head}.json').exists())


class CoveredTestCase(SuiteTestCase):
    """Issue 57, S4: com `{covered}` no argv de `homolog.suites.full`, a release passa à suíte inteira um arquivo
    `{"complete": [ids]}` com o que o impacto das issues da release rodou inteiro e verde na mesma árvore da ponta,
    e grava no registro da release o que foi pulado e de onde veio.

    A main local tem um remoto bare; cada issue tem a própria worktree (`git worktree add`), cortada da main local,
    um commit e a suíte rodada ali pelo `homolog suite`; o registro de autorização da worktree principal a nomeia. A
    suíte falsa é o REPORTER: no impacto copia o relatório para o `{report}`, na inteira copia o arquivo do
    `{covered}` para `recebido.json`, fora do repositório."""

    def setUp(self):
        super().setUp()
        self.git(self.work, 'switch', '-q', 'main')
        self.reporter = self.base / 'report_suite.py'
        self.reporter.write_text(REPORTER, encoding='utf-8')
        origin = self.base / 'origin.git'
        self.git(None, 'init', '-q', '--bare', '-b', 'main', str(origin))
        self.git(self.work, 'remote', 'add', 'origin', str(origin))
        self.git(self.work, 'push', '-q', 'origin', 'main')
        self.received = self.base / 'recebido.json'
        self.marked = ('--copia', '{covered}', str(self.received))
        self.entries = []

    def write_config(self, impact=('{report}',), full=None):
        path = self.base / 'config.json'
        suites = {'impact': {'argv': [sys.executable, str(self.reporter), *impact], 'timeoutSeconds': 60},
                  'full': {'argv': [sys.executable, str(self.reporter), *(self.marked if full is None else full)],
                           'timeoutSeconds': 60}}
        path.write_text(json.dumps({'repository': None, 'homolog': {'suites': suites}}), encoding='utf-8')
        return path

    def issue(self, number, complete=('tests.test_a',), mode='impact', flags=(), report=True, loose=False):
        """The worktree of issue `number`, cut from the local main now, with one commit; its suite run there (the
        impact one with a report whose `complete` is `complete`, unless `report` is false); `loose` leaves an
        untracked file in it during the run. The authorization record of the main worktree names it."""
        path, branch = self.base / f'wt-{number}', f'claude/issue-{number}'
        self.git(self.work, 'worktree', 'add', '-q', '-b', branch, str(path), 'main')
        (path / f'issue-{number}.txt').write_text(f'{number}\n', encoding='utf-8')
        self.git(path, 'add', '.')
        self.git(path, 'commit', '-q', '-m', f'issue {number}')
        if loose:
            (path / 'solto.txt').write_text('solto\n', encoding='utf-8')
        payload = self.base / f'payload-{number}.json'
        payload.write_text(json.dumps({'ran': [*complete, 'tests.test_z.Classe'], 'complete': list(complete)}),
                           encoding='utf-8')
        config = self.write_config(impact=(*flags, *(('--copia', str(payload), '{report}') if report else ())))
        code, result = self.cli('suite', '--root', str(path), '--config', str(config), '--issue', str(number),
                                '--mode', mode)
        self.assertEqual(code, 1 if '--falha' in flags else 0, result)
        self.entries.append({'issue': number, 'branch': branch, 'path': str(path)})
        (self.work / '.frontlights').mkdir(exist_ok=True)
        (self.work / '.frontlights' / 'authorization.json').write_text(json.dumps(
            {'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'claude/', 'worktrees': self.entries}),
            encoding='utf-8')
        return path

    def deliver(self, number):
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', f'merge of issue {number} into the local main',
                 f'claude/issue-{number}')

    def release(self, config=None, *flags):
        return self.cli('suite', '--root', str(self.work), '--config', str(config or self.write_config()),
                        '--release', '--mode', 'full', *flags)

    @property
    def release_folder(self):
        return self.work / '.frontlights' / 'release'

    def saved(self, name='suite.json'):
        return json.loads((self.release_folder / name).read_text(encoding='utf-8'))


class ReleaseCoveredTests(CoveredTestCase):
    def test_the_release_skips_what_the_impact_of_an_issue_of_the_same_tree_ran_whole(self):
        """O arquivo do `{covered}` traz o `complete` do impacto da issue; os dois registros da release gravam o
        que foi pulado e de onde veio; o portão da release (com e sem `--head`) e o `release-plan` o aceitam como a
        suíte inteira da ponta e dizem quantos módulos foram pulados."""
        worktree = self.issue(1, complete=('tests.test_a', 'tests.test_b'))
        self.deliver(1)
        head = self.git(self.work, 'rev-parse', 'main').stdout.strip()
        issue_head = self.git(self.work, 'rev-parse', 'claude/issue-1').stdout.strip()
        tree = self.git(self.work, 'rev-parse', 'claude/issue-1^{tree}').stdout.strip()
        code, result = self.release()
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')),
                         {'complete': ['tests.test_a', 'tests.test_b']})
        self.assertIn('2 módulo', result['message'])
        for name in ('suite.json', f'suite-{head}.json'):
            with self.subTest(record=name):
                saved = self.saved(name)
                covered = saved['covered']
                self.assertEqual((covered['complete'], covered['refused']), (['tests.test_a', 'tests.test_b'], []))
                self.assertEqual([(item['issue'], item['head'], item['tree']) for item in covered['from']],
                                 [(1, issue_head, tree)])
                self.assertTrue(os.path.samefile(covered['from'][0]['path'],
                                                 worktree / '.frontlights' / 'issues' / '1' / 'suite.json'))
                self.assertTrue(os.path.samefile(Path(covered['file']).parent, self.release_folder))
                self.assertIn(covered['file'], saved['argv'])
        config = self.write_config()
        for flags in ((), ('--head', head)):
            with self.subTest(gate=flags):
                code, gate = self.cli('suite-gate', '--root', str(self.work), '--config', str(config), '--release',
                                      *flags)
                self.assertEqual((code, gate.get('status')), (0, 'current'), gate)
                self.assertEqual(gate['covered'], self.saved()['covered'])
                self.assertIn('2 módulo', gate['message'])
        code, plan = self.cli('release-plan', '--root', str(self.work))
        self.assertEqual((code, plan['ready'], plan['release'], plan['fullSuite']['status']),
                         (0, True, [1], 'current'), plan)
        self.assertEqual(plan['fullSuite']['covered'], self.saved()['covered'])
        self.assertIn('2 módulo', plan['message'])

    def test_a_later_fix_worktree_of_the_issue_does_not_hide_the_record_of_the_branch_of_the_issue(self):
        """Uma correção de revisão ganha a própria worktree e uma entrada da mesma issue, depois da entrada da issue,
        no registro de autorização; o registro da suíte continua na worktree da branch da issue, e é ele que conta."""
        worktree = self.issue(1)
        fix = self.base / 'wt-1-fix1'
        self.git(self.work, 'worktree', 'add', '-q', '-b', 'claude/issue-1-fix1', str(fix), 'claude/issue-1')
        self.entries.append({'issue': 1, 'branch': 'claude/issue-1-fix1', 'path': str(fix)})
        (self.work / '.frontlights' / 'authorization.json').write_text(json.dumps(
            {'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'claude/', 'worktrees': self.entries}),
            encoding='utf-8')
        self.deliver(1)
        code, result = self.release()
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')), {'complete': ['tests.test_a']})
        covered = self.saved()['covered']
        self.assertEqual(covered['refused'], [])
        self.assertTrue(os.path.samefile(covered['from'][0]['path'],
                                         worktree / '.frontlights' / 'issues' / '1' / 'suite.json'))

    def test_a_later_fix_branch_not_in_the_local_main_does_not_take_the_issue_out_of_the_release(self):
        """A branch de uma correção posterior da mesma issue, ainda fora da main local, não decide se a issue é da
        release: vale a branch da issue, que está na main local; o plano a lista e a release pula o que ela cobriu."""
        self.issue(1)
        fix = self.base / 'wt-1-fix1'
        self.git(self.work, 'worktree', 'add', '-q', '-b', 'claude/issue-1-fix1', str(fix), 'claude/issue-1')
        (fix / 'correcao.txt').write_text('correção ainda fora da main\n', encoding='utf-8')
        self.git(fix, 'add', '.')
        self.git(fix, 'commit', '-q', '-m', 'correção em andamento')
        self.entries.append({'issue': 1, 'branch': 'claude/issue-1-fix1', 'path': str(fix)})
        (self.work / '.frontlights' / 'authorization.json').write_text(json.dumps(
            {'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'claude/', 'worktrees': self.entries}),
            encoding='utf-8')
        self.deliver(1)
        code, result = self.release()
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')), {'complete': ['tests.test_a']})
        code, plan = self.cli('release-plan', '--root', str(self.work))
        self.assertEqual((code, plan['release']), (0, [1]), plan)

    def test_a_record_that_does_not_count_contributes_nothing_and_its_reason_is_recorded(self):
        """Cada issue entra na main local logo depois do próprio registro; só a última tem a árvore da ponta."""
        self.issue(1)                                       # verde, mas a ponta andou depois dela
        self.deliver(1)
        self.issue(2, flags=('--falha',))                   # vermelho
        self.deliver(2)
        self.issue(3, report=False)                         # impacto sem o {report}: sem complete
        self.deliver(3)
        self.issue(4, mode='full')                          # registro da suíte inteira
        self.deliver(4)
        self.issue(5, loose=True)                           # rodou com um arquivo fora do commit
        self.deliver(5)
        removed = self.issue(6)                             # a worktree saiu antes da release
        self.deliver(6)
        self.git(self.work, 'worktree', 'remove', '--force', str(removed))
        self.issue(8, complete=('tests.test_c',))           # a árvore da ponta
        self.deliver(8)
        code, result = self.release()
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')), {'complete': ['tests.test_c']})
        covered = self.saved()['covered']
        self.assertEqual(covered['complete'], ['tests.test_c'])
        self.assertEqual([item['issue'] for item in covered['from']], [8])
        reasons = {item['issue']: item['reason'] for item in covered['refused']}
        for number, needle in ((1, 'outra árvore'), (2, 'não passou'), (3, 'complete'), (4, 'suíte inteira'),
                               (5, 'não commitad'), (6, 'não existe')):
            with self.subTest(issue=number):
                self.assertIn(needle, reasons.get(number, ''), covered['refused'])
        self.assertEqual(sorted(reasons), [1, 2, 3, 4, 5, 6])
        self.assertTrue(all('path' in item for item in covered['refused']))

    def assert_nothing_skipped_with_the_reason(self, needle):
        code, result = self.release()
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')), {'complete': []})
        covered = self.saved()['covered']
        self.assertEqual((covered['complete'], covered['from']), ([], []))
        self.assertTrue(any(needle in warning for warning in covered.get('warnings') or []), covered)
        self.assertIn(needle, result['message'])

    def test_without_the_remote_ref_of_the_base_nothing_is_skipped_and_the_reason_is_recorded(self):
        """Revisão da issue 57, rodada 1, B4: sem `refs/remotes/origin/<base>` a lista das issues da release não sai;
        nada é pulado, e o `covered` do registro da release nomeia o ref que faltou."""
        self.issue(1)
        self.deliver(1)
        self.git(self.work, 'update-ref', '-d', 'refs/remotes/origin/main')
        self.assert_nothing_skipped_with_the_reason('refs/remotes/origin/main')

    def test_without_an_authorization_record_of_the_issues_nothing_is_skipped_and_the_reason_is_recorded(self):
        """B4: sem registro de autorização que nomeie uma issue da release, o `covered` diz por que nada foi pulado."""
        self.issue(1)
        self.deliver(1)
        (self.work / '.frontlights' / 'authorization.json').unlink()
        self.assert_nothing_skipped_with_the_reason('autorização')

    def test_without_the_marker_the_release_record_is_the_one_of_today(self):
        self.issue(1)
        self.deliver(1)
        code, result = self.release(self.write_config(full=()))
        self.assertEqual((code, result.get('state')), (0, 'green'), result)
        self.assertEqual(set(self.saved()), SuiteReportTests.TODAY)
        self.assertEqual(list(self.release_folder.glob('suite-covered-*')), [])
        self.assertFalse(self.received.exists())

    def test_the_marker_out_of_its_place_is_refused_and_nothing_runs(self):
        for name, impact, full, mode in (('na suíte de impacto', ('{covered}',), (), 'impact'),
                                         ('dentro de um argumento', (), ('--cobertos={covered}',), 'full'),
                                         ('duas vezes', (), ('{covered}', '{covered}'), 'full')):
            with self.subTest(case=name):
                code, result = self.release(self.write_config(impact=impact, full=full))
                self.assertEqual(code, 1, result)
                self.assertIn('{covered}', result['message'])
                self.assertIn(f'homolog.suites.{mode}.argv', result['message'])
                self.assertFalse((self.release_folder / 'suite.json').exists())
        given = json.dumps([sys.executable, str(self.reporter), '{covered}'])
        code, result = self.release(self.write_config(), '--argv', given)
        self.assertEqual(code, 1, result)
        self.assertIn('{covered}', result['message'])
        self.assertIn('--argv', result['message'])
        self.assertFalse((self.release_folder / 'suite.json').exists())

    def test_the_whole_suite_of_an_issue_skips_nothing(self):
        """Fora da release não há issue que cubra nada: o arquivo do `{covered}` vem vazio e a suíte roda tudo."""
        self.issue(1, mode='full')
        self.assertEqual(json.loads(self.received.read_text(encoding='utf-8')), {'complete': []})


if __name__ == '__main__':
    unittest.main()
