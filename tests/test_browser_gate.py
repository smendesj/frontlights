"""O portão do teste assistido: o diff (não o texto do plano) diz se algo visível mudou, um lote tem uma decisão só
(não uma por branch) e a decisão deixa de valer quando muda código que não é teste nem documento.

Seam: a CLI `frontlights.py browser-gate` (saída JSON e código de saída) e `browser_gate.gate`; para a pendência
que atravessa janelas, `checkpoint`, `resume` e `context`. Só marcadores genéricos (repositório público).
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import browser_gate
import frontlights

SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
EXAMPLE = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))

SCREEN = 'web/src/app/pages/items/items.component.ts'
SCREEN_SPEC = 'web/src/app/pages/items/items.component.spec.ts'
TEMPLATE = 'web/src/app/pages/items/items.component.html'
SERVICE = 'web/src/app/services/items.service.ts'
API = 'api/src/ItemController.cs'
API_TEST = 'api/tests/ItemControllerTests.cs'
NOTES = 'docs/notes.md'


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.main = base / 'main'
        self.main.mkdir()
        self.git(self.main, 'init', '-b', 'main')
        self.git(self.main, 'config', 'user.email', 'fixture@example.invalid')
        self.git(self.main, 'config', 'user.name', 'Fixture')
        for name in (SCREEN, SCREEN_SPEC, TEMPLATE, SERVICE, API, API_TEST, NOTES):
            self.write(self.main, name, 'base\n')
        self.git(self.main, 'add', '.')
        self.git(self.main, 'commit', '-m', 'base')
        self.record = base / 'result.json'
        self.config = copy.deepcopy(EXAMPLE)
        self.config.update(repository=None, project=None, roads=None)
        self.config['browserTest'].pop('frontPaths')      # the baseline is the default guess; one test sets the globs

    def git(self, root, *args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)

    def write(self, root, name, text):
        path = Path(root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def slice(self, name, **files):
        """A worktree on its own branch, with the given files committed (`path` -> text, `__`-free)."""
        root = Path(self.tmp.name) / name
        self.git(self.main, 'worktree', 'add', '-b', name, str(root), 'main')
        for path, text in files.items():
            self.write(root, path, text)
        if files:
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-m', name)
        return root

    def edit(self, root, path, text='changed\n'):
        self.write(root, path, text)

    def decide(self, report, situacao='aprovado', **extra):
        record = {'situacao': situacao, 'lote': {'roots': report['roots']}, **extra}
        self.record.write_text(json.dumps(record), encoding='utf-8')
        return record

    def gate(self, roots, toca='sim', config='default', **kwargs):
        config = self.config if config == 'default' else config
        record = json.loads(self.record.read_text(encoding='utf-8')) if self.record.is_file() else None
        return browser_gate.gate([str(r) for r in roots], 'main', config, toca, record, **kwargs)

    def cli(self, roots, *extra):
        args = [sys.executable, str(SCRIPT), 'browser-gate', '--base', 'main']
        for root in roots:
            args += ['--root', str(root)]
        return subprocess.run(args + list(extra), capture_output=True, text=True, encoding='utf-8')


class DetectionTests(GateTestCase):
    def test_nothing_changed_and_a_plan_that_says_no_needs_no_test(self):
        a = self.slice('slice-a')
        result = self.gate([a], toca='nao')
        self.assertEqual((result['status'], result['front_files']), ('not_needed', []))

    def test_an_api_only_change_needs_no_test_unless_the_plan_turns_it_on(self):
        a = self.slice('slice-a', **{API: 'new\n'})
        self.assertEqual(self.gate([a], toca='nao')['status'], 'not_needed')
        self.assertEqual(self.gate([a], toca='ausente')['status'], 'not_needed')
        turned_on = self.gate([a], toca='sim')
        self.assertEqual((turned_on['status'], turned_on['reason'], turned_on['action']), ('pending', 'sem-registro', 'ask'))

    def test_a_visible_change_is_found_in_the_diff_whatever_the_plan_says(self):
        a = self.slice('slice-a', **{SCREEN: 'new\n', API: 'new\n'})
        result = self.gate([a], toca='sim')
        self.assertEqual((result['status'], result['front_files']), ('pending', [SCREEN]))
        self.assertEqual(list(result['roots']), ['slice-a'])

    def test_a_visible_change_the_plan_does_not_declare_is_a_contradiction(self):
        a = self.slice('slice-a', **{TEMPLATE: 'new\n'})
        for toca in ('nao', 'ausente'):
            result = self.gate([a], toca=toca)
            with self.subTest(toca=toca):
                self.assertEqual((result['status'], result['action']), ('contradiction', 'ask-plan'))

    def test_tests_and_documents_are_never_a_visible_change(self):
        a = self.slice('slice-a', **{SCREEN_SPEC: 'new\n', NOTES: 'new\n', 'README.md': 'x\n', API_TEST: 'new\n'})
        result = self.gate([a], toca='nao')
        self.assertEqual((result['status'], result['front_files']), ('not_needed', []))

    def test_uncommitted_staged_untracked_and_deleted_files_count(self):
        a = self.slice('slice-a')
        self.edit(a, SCREEN)
        self.assertEqual(self.gate([a], toca='nao')['front_files'], [SCREEN])
        self.git(a, 'checkout', '--', SCREEN)
        self.write(a, 'web/src/app/new.component.html', '<p>x</p>')
        self.assertEqual(self.gate([a], toca='nao')['front_files'], ['web/src/app/new.component.html'])
        (a / 'web/src/app/new.component.html').unlink()
        (a / TEMPLATE).unlink()
        self.assertEqual(self.gate([a], toca='nao')['front_files'], [TEMPLATE])

    def test_the_control_folder_is_never_counted(self):
        a = self.slice('slice-a')
        self.write(a, '.frontlights/issues/1/browser/shot.html', 'x')
        self.assertEqual(self.gate([a], toca='nao')['status'], 'not_needed')

    def test_front_paths_in_the_config_replace_the_default_guess(self):
        a = self.slice('slice-a', **{SERVICE: 'new\n', API: 'new\n', SCREEN_SPEC: 'new\n'})
        self.assertEqual(self.gate([a], toca='nao')['front_files'], [])      # a service is not a screen file by default
        self.config['browserTest']['frontPaths'] = ['web/src/**']
        result = self.gate([a], toca='nao')
        self.assertEqual((result['status'], result['front_files']), ('contradiction', [SERVICE]))   # the spec is still a test

    def test_images_count_only_in_asset_folders(self):
        a = self.slice('slice-a', **{'web/src/assets/logo.svg': '<svg/>', 'api/src/diagram.svg': '<svg/>'})
        self.assertEqual(self.gate([a], toca='nao')['front_files'], ['web/src/assets/logo.svg'])

    def test_the_glob_rules(self):
        match = lambda pattern, path: browser_gate.compile_glob(pattern).match(path)
        self.assertTrue(match('web/**', 'web/src/a.ts'))
        self.assertTrue(match('web/src/**/*.ts', 'web/src/a.ts'))          # `**/` may cross no folder at all
        self.assertTrue(match('web/src/**/*.ts', 'web/src/a/b/c.ts'))
        self.assertFalse(match('web/src/*.ts', 'web/src/a/b.ts'))          # `*` stays inside one folder
        self.assertTrue(match('WEB/SRC/*.TS', 'web/src/a.ts'))
        self.assertFalse(match('web/src/a.ts', 'web/src/a.tsx'))
        self.assertFalse(match('a?b', 'a/b'))                               # `?` stays inside one folder
        self.assertTrue(match('a?b', 'axb'))
        self.assertTrue(match('a**b', 'a/x/b'))                             # `**` crosses folders without a slash too
        self.assertFalse(match('a*b', 'a/x/b'))
        self.assertTrue(match('web/**/app', 'web/app'))
        self.assertTrue(match('web/**/app', 'web/x/y/app/z.ts'))            # a folder name covers its content
        self.assertFalse(match('web/**/app', 'web/x/application.ts'))
        self.assertTrue(match('*.html', 'a.html'))
        self.assertFalse(match('*.html', 'web/a.html'))                     # `*` does not cross folders: say `**/*.html`
        self.assertTrue(match('**/*.html', 'web/src/a.html'))
        self.assertTrue(match('web/src/a.ts', 'WEB/SRC/A.TS'))              # the case of the path does not matter either
        self.assertFalse(match('a/**a', 'a/'))
        self.assertFalse(match('**a', 'b'))


class BatchTests(GateTestCase):
    def setUp(self):
        super().setUp()
        self.parent = self.slice('slice-parent', **{SCREEN: 'parent\n', API: 'parent\n'})
        self.child = self.slice('slice-child', **{API_TEST: 'child\n', 'api/src/Other.cs': 'child\n'})
        self.second = self.slice('slice-second', **{TEMPLATE: 'second\n'})

    def test_one_decision_covers_every_visible_slice_of_the_batch(self):
        result = self.gate([self.parent, self.child, self.second])
        self.assertEqual(result['front_files'], sorted([SCREEN, TEMPLATE]))
        self.assertEqual(sorted(result['roots']), ['slice-parent', 'slice-second'])
        self.assertEqual(result['other_roots'], ['slice-child'])
        self.assertEqual(result['status'], 'pending')

    def test_the_decision_is_recorded_once_and_covers_the_whole_batch(self):
        roots = [self.parent, self.child, self.second]
        self.decide(self.gate(roots))
        self.assertEqual(self.gate(roots)['status'], 'answered')

    def test_a_slice_without_a_visible_change_never_makes_the_record_stale(self):
        roots = [self.parent, self.child, self.second]
        self.decide(self.gate(roots))
        self.edit(self.child, 'api/src/Other.cs', 'later\n')
        self.assertEqual(self.gate(roots)['status'], 'answered')

    def test_a_label_that_appears_twice_is_refused(self):
        with self.assertRaises(ValueError):
            self.gate([self.parent, self.parent])


class DecisionTests(GateTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.slice('slice-a', **{SCREEN: 'new\n', API: 'new\n'})

    def test_a_decision_to_watch_run_or_go_on_answers(self):
        for situacao in ('aprovado', 'prosseguir', 'sem-assistir'):
            self.decide(self.gate([self.a]), situacao)
            with self.subTest(situacao):
                self.assertEqual(self.gate([self.a])['status'], 'answered')

    def test_not_yet_and_a_change_request_stay_pending(self):
        for situacao, reason in (('ainda-nao', 'ainda-nao'), ('alteracao', 'alteracao'), ('pendente', 'pendente')):
            self.decide(self.gate([self.a]), situacao)
            result = self.gate([self.a])
            with self.subTest(situacao):
                self.assertEqual((result['status'], result['reason'], result['action']), ('pending', reason, 'ask'))

    def test_a_record_from_before_situacao_is_read_through_aprovacao(self):
        report = self.gate([self.a])
        self.record.write_text(json.dumps({'aprovacao': 'aprovado', 'lote': {'roots': report['roots']}}), encoding='utf-8')
        self.assertEqual(self.gate([self.a])['status'], 'answered')
        self.record.write_text(json.dumps({'assistido': True, 'lote': {'roots': report['roots']}}), encoding='utf-8')
        self.assertEqual(self.gate([self.a])['status'], 'pending')

    def test_code_that_is_not_a_test_or_a_document_makes_it_stale_and_names_the_root(self):
        self.decide(self.gate([self.a]))
        self.edit(self.a, API)
        result = self.gate([self.a])
        self.assertEqual((result['status'], result['reason'], result['changed_roots']), ('stale', 'codigo-mudou', ['slice-a']))
        self.assertEqual(result['action'], 'ask-again')

    def test_a_visible_file_edit_after_the_decision_makes_it_stale(self):
        self.decide(self.gate([self.a]))
        self.edit(self.a, SCREEN)
        self.assertEqual(self.gate([self.a])['status'], 'stale')

    def test_tests_and_documents_changed_after_the_decision_keep_it(self):
        self.decide(self.gate([self.a]))
        self.edit(self.a, SCREEN_SPEC)
        self.edit(self.a, API_TEST)
        self.edit(self.a, NOTES)
        self.assertEqual(self.gate([self.a])['status'], 'answered')

    def test_a_commit_with_the_same_content_keeps_it(self):
        self.decide(self.gate([self.a]))
        self.git(self.a, 'commit', '--allow-empty', '-m', 'history only')
        self.assertEqual(self.gate([self.a])['status'], 'answered')

    def test_a_new_visible_slice_after_the_decision_makes_it_stale(self):
        self.decide(self.gate([self.a]))
        b = self.slice('slice-b', **{TEMPLATE: 'b\n'})
        result = self.gate([self.a, b])
        self.assertEqual((result['status'], result['changed_roots']), ('stale', ['slice-b']))

    def test_a_record_without_the_binding_cannot_be_trusted(self):
        self.record.write_text(json.dumps({'situacao': 'aprovado'}), encoding='utf-8')
        result = self.gate([self.a])
        self.assertEqual((result['status'], result['reason']), ('stale', 'sem-vinculo'))

    def test_a_decision_with_a_plan_that_says_no_is_answered_with_a_warning(self):
        self.decide(self.gate([self.a]))
        result = self.gate([self.a], toca='nao')
        self.assertEqual(result['status'], 'answered')
        self.assertTrue(any('Toca o frontend' in warning for warning in result['warnings']))

    def test_a_plan_that_turns_it_on_with_no_visible_diff_binds_to_the_changed_code(self):
        a = self.slice('slice-api', **{API: 'only api\n'})
        report = self.gate([a], toca='sim')
        self.assertEqual(report['status'], 'pending')
        self.decide(report)
        self.assertEqual(self.gate([a], toca='sim')['status'], 'answered')
        self.edit(a, API)
        self.assertEqual(self.gate([a], toca='sim')['status'], 'stale')

    def test_a_project_without_browser_test_cannot_run_it_and_the_session_asks_how(self):
        config = {'repository': None}
        result = self.gate([self.a], toca='sim', config=config)
        self.assertEqual((result['status'], result['action']), ('unconfigured', 'ask-how'))
        self.assertEqual(self.gate([self.a], toca='sim', config=None)['status'], 'pending')   # no config given: no verdict

    def test_a_missing_base_or_no_roots_is_an_error(self):
        with self.assertRaises(ValueError):
            browser_gate.gate([], 'main')
        with self.assertRaises(ValueError):
            browser_gate.gate([str(self.a)], '')
        with self.assertRaises(ValueError):
            browser_gate.gate([str(self.a)], 'no-such-branch')
        with self.assertRaises(ValueError):
            browser_gate.gate([str(self.a)], 'main', None, 'maybe')


class ClassificationTests(unittest.TestCase):
    """A screen file is never taken for a document or a test because of its name or folder; the config can name more."""

    def front(self, path, patterns=None):
        compiled = [browser_gate.compile_glob(item) for item in patterns] if patterns else None
        return browser_gate.is_front(path, compiled)

    def test_screens_with_the_name_or_the_folder_of_a_document_or_a_test_still_count(self):
        screens = ['web/src/app/changelog/changelog.component.html', 'web/src/app/license/license.component.ts',
                   'web/src/app/license/license.component.scss', 'web/src/app/notice/notice.component.html',
                   'web/src/app/docs/docs.component.html', 'web/src/app/test/page.component.html',
                   'web/src/app/spec/x.component.html', 'web/src/app/fixtures/y.html', 'web/src/assets/license.svg',
                   'web/src/app/Tests/z.component.ts', 'src/Licenses/License.cshtml']
        for path in screens:
            for patterns in (None, ['web/**', 'src/**']):
                with self.subTest(path=path, patterns=patterns):
                    self.assertTrue(self.front(path, patterns))
                    self.assertFalse(browser_gate.is_test_or_doc(path) and not browser_gate.looks_screen(path))

    def test_documents_and_tests_never_count_even_when_the_config_names_their_folder(self):
        for path in ('README', 'LICENSE', 'CHANGELOG.md', 'NOTICE', 'web/readme.txt', 'guide.mdx', 'notes.rst',
                     'web/src/app/items.component.spec.ts', 'web/src/app/items.test.tsx', 'web/e2e/items.e2e.ts'):
            with self.subTest(path=path):
                self.assertTrue(browser_gate.is_test_or_doc(path))
                self.assertFalse(self.front(path, ['web/**']))

    def test_a_file_that_is_not_a_screen_file_inside_a_test_or_doc_folder_is_excluded(self):
        for folder in ('tests', 'test', '__tests__', '__mocks__', 'e2e', 'cypress', 'fixtures', 'spec', 'specs', 'docs', 'doc',
                       'Tests', 'DOCS'):
            with self.subTest(folder=folder):
                self.assertTrue(browser_gate.is_test_or_doc(f'web/src/{folder}/helper.ts'))
                self.assertFalse(self.front(f'web/src/{folder}/helper.ts', ['web/**']))

    def test_the_default_guess_looks_at_the_screen_suffixes_and_asset_images(self):
        for path in ('a/b.html', 'a/b.htm', 'a/b.css', 'a/b.scss', 'a/b.sass', 'a/b.less', 'a/b.vue', 'a/b.svelte', 'a/b.tsx',
                     'a/b.jsx', 'a/b.component.ts', 'a/b.component.js', 'web/assets/x.png', 'web/public/x.ico', 'web/static/x.webp'):
            with self.subTest(path=path):
                self.assertTrue(self.front(path))
        for path in ('api/src/Item.cs', 'web/src/app/items.service.ts', 'api/src/diagram.svg', 'a/b.json'):
            with self.subTest(path=path):
                self.assertFalse(self.front(path))

    def test_patterns_are_normalized_and_a_folder_name_covers_what_is_inside(self):
        path = 'web/src/app/items.service.ts'
        for pattern in ('web/src/**', './web/src/**', 'web/src/', 'web/src', 'web\\src\\**', 'WEB/SRC', 'web/*/app/*.ts', 'web/src/app/items.service.t?'):
            with self.subTest(pattern=pattern):
                self.assertTrue(self.front(path, [pattern]))
        self.assertFalse(self.front(path, ['web/s']))
        self.assertFalse(self.front(path, ['api/**']))

    def test_the_pattern_list_is_validated(self):
        for bad in ([], 'web/**', ['/web'], ['\\web'], ['~/web'], ['C:/web'], ['a/../b'], [''], [1], ['x'] * 51, ['{a,b}/**'],
                    ['web/[ab].ts'], ['a' * 201], ['a\x00b'], ['.'], ['./'], [' '], ['//'], ['web/**', '.'],
                    ['*a' * 9 + 'b'], ['a/./b'], ['src/.'], ['.. '], [' ../x']):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                browser_gate.validate_front_paths(bad)
        self.assertEqual(browser_gate.validate_front_paths(['web/**', 'a/*/*.ts']), ['web/**', 'a/*/*.ts'])
        self.assertEqual(browser_gate.validate_front_paths(['*' * 40 + 'b', '*a' * 8 + 'b']), ['*' * 40 + 'b', '*a' * 8 + 'b'])
        self.assertEqual(browser_gate.normalize_pattern('  .//web\\\\src//**/  '), 'web/src/**')
        self.assertEqual(browser_gate.normalize_pattern('a****b'), 'a**b')
        with self.assertRaises(ValueError):
            browser_gate.front_patterns({'browserTest': {'frontPaths': ['{a,b}']}})
        with self.assertRaises(ValueError):
            browser_gate.front_patterns([])

    def test_a_pathological_pattern_cannot_stall_the_gate(self):
        import time
        patterns = ['*' * 40 + 'b', '*' * 199 + 'b', '*a' * 8 + 'b', '**a' * 8 + 'b', '?' * 100 + 'x', '**/' * 8 + 'b']
        paths = ['a' * 1000, 'a/' * 300, ('a' * 20 + '/') * 40 + 'c']
        for pattern in browser_gate.validate_front_paths(patterns):
            glob = browser_gate.compile_glob(pattern)
            for path in paths:
                started = time.monotonic()
                glob.match(path)
                with self.subTest(pattern=pattern[:20], path=path[:20]):
                    self.assertLess(time.monotonic() - started, 0.5)

    def test_the_whole_pattern_list_stays_cheap_over_many_adversarial_files(self):
        import time
        patterns = browser_gate.validate_front_paths(['*a' * 8 + 'b'] * 50)
        globs = [browser_gate.compile_glob(item) for item in patterns]
        files = ['a' * 150 + '.ts'] * 60
        started = time.monotonic()
        for name in files:
            self.assertFalse(any(glob.match(name) for glob in globs))
        self.assertLess(time.monotonic() - started, 5)

    def test_every_screen_suffix_and_the_test_name_forms_are_recognised(self):
        for path in ('a/b.astro', 'a/b.ejs', 'a/b.hbs', 'a/b.cshtml', 'a/b.razor'):
            with self.subTest(path=path):
                self.assertTrue(self.front(path))
        for path in ('web/src/app/items.e2e.ts', 'web/src/app/items.test.js', 'web/src/app/items.spec.tsx'):
            with self.subTest(path=path):
                self.assertTrue(browser_gate.is_test_or_doc(path))
                self.assertFalse(self.front(path))


class MoreGateCases(GateTestCase):
    def test_a_screen_in_a_documentation_or_test_folder_is_found_in_a_real_diff(self):
        a = self.slice('slice-a', **{'web/src/app/docs/docs.component.html': 'x\n', 'web/src/app/test/page.component.html': 'x\n',
                                      'web/src/app/license/license.component.ts': 'x\n'})
        for config in (self.config, {**self.config, 'browserTest': {**self.config['browserTest'], 'frontPaths': ['web/src/**']}}):
            result = self.gate([a], toca='nao', config=config)
            with self.subTest(frontPaths=config['browserTest'].get('frontPaths')):
                self.assertEqual(result['status'], 'contradiction')
                self.assertEqual(len(result['front_files']), 3)

    def test_each_root_lists_its_own_visible_files(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        b = self.slice('slice-b', **{API: 'b\n'})
        result = self.gate([a, b])
        self.assertEqual(result['by_root'], {'slice-a': [SCREEN], 'slice-b': []})

    def test_the_users_explicit_dispensation_answers_even_without_browser_test(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        report = self.gate([a], config={'repository': None})
        self.assertEqual((report['status'], report['reason']), ('unconfigured', 'sem-browsertest'))
        self.decide(report, 'dispensado', pergunta={'resposta': 'Verificar à mão e dispensar'})
        self.assertEqual(self.gate([a], config={'repository': None})['status'], 'answered')
        self.assertEqual(self.gate([a])['status'], 'answered')
        self.edit(a, SCREEN)                                                 # visible code: asks again
        self.assertEqual(self.gate([a])['status'], 'stale')

    def test_dispensation_is_not_inferred_from_not_yet(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        self.decide(self.gate([a]), 'ainda-nao')
        self.assertEqual(self.gate([a], config={'repository': None})['status'], 'unconfigured')

    def test_a_root_inside_a_subfolder_gives_the_same_answer_as_the_top_of_the_repository(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        inside = a / 'web'
        top = self.gate([a])
        self.assertEqual(self.gate([inside])['front_files'], top['front_files'])
        self.decide(self.gate([inside]))
        self.assertEqual(self.gate([inside])['status'], 'answered')
        self.edit(a, SCREEN)
        self.assertEqual(self.gate([inside])['status'], 'stale')
        self.assertEqual(self.gate([a])['status'], 'stale')

    def test_a_base_that_moved_on_after_the_slice_was_cut_adds_nothing(self):
        a = self.slice('slice-a', **{API: 'a\n'})
        self.write(self.main, SCREEN, 'main moved\n')
        self.git(self.main, 'commit', '-am', 'main changes a screen')
        result = self.gate([a], toca='nao')
        self.assertEqual((result['status'], result['front_files']), ('not_needed', []))

    def test_files_the_repository_ignores_never_count(self):
        a = self.slice('slice-a', **{'.gitignore': '*.generated.html\n'})
        self.write(a, 'web/src/app/x.generated.html', 'ignored')
        self.assertEqual(self.gate([a], toca='nao')['status'], 'not_needed')
        self.write(a, 'web/src/app/x.html', 'counted')
        self.assertEqual(self.gate([a], toca='nao')['front_files'], ['web/src/app/x.html'])

    def test_a_renamed_screen_counts_for_the_old_and_the_new_path(self):
        a = self.slice('slice-a')
        self.git(a, 'mv', TEMPLATE, 'web/src/app/pages/items/list.component.html')
        result = self.gate([a], toca='nao')
        self.assertEqual(sorted(result['front_files']), sorted([TEMPLATE, 'web/src/app/pages/items/list.component.html']))

    def test_a_detached_head_is_labelled_by_its_commit_and_compared_like_a_branch(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        self.git(a, 'checkout', '--detach')
        report = self.gate([a])
        label = next(iter(report['roots']))
        self.assertEqual(label, 'detached:slice-a')            # the worktree folder: it does not change with each commit
        self.decide(report)
        self.assertEqual(self.gate([a])['status'], 'answered')
        self.write(a, NOTES, 'a note\n')
        self.git(a, 'add', '.')
        self.git(a, 'commit', '-m', 'only a document')
        self.assertEqual(self.gate([a])['status'], 'answered')   # a document commit does not invalidate the decision
        with self.assertRaises(ValueError):
            self.gate([a, a])

    def test_a_record_with_an_invalid_legacy_approval_is_pending(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        report = self.gate([a])
        self.record.write_text(json.dumps({'aprovacao': 'bogus', 'lote': {'roots': report['roots']}}), encoding='utf-8')
        self.assertEqual(self.gate([a])['status'], 'pending')

    def test_a_record_saved_with_a_byte_order_mark_is_read(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        config_file = Path(self.tmp.name) / 'config.json'
        config_file.write_text(json.dumps(self.config), encoding='utf-8-sig')
        report = self.gate([a])
        self.record.write_text(json.dumps({'situacao': 'aprovado', 'lote': {'roots': report['roots']}}), encoding='utf-8-sig')
        done = self.cli([a], '--config', str(config_file), '--toca', 'sim', '--record', str(self.record))
        self.assertEqual((done.returncode, json.loads(done.stdout)['status']), (0, 'answered'))

    def test_the_control_folder_of_a_project_inside_a_subfolder_is_never_counted(self):
        a = self.slice('slice-a', **{'proj/web/x.html': 'x\n'})
        inside = a / 'proj'
        self.decide(self.gate([inside]))
        self.write(a, 'proj/.frontlights/issues/1/browser/result.json', '{}')
        self.assertEqual(self.gate([inside])['status'], 'answered')

    def test_an_explicit_decision_that_is_not_valid_is_pending_whatever_the_legacy_field_says(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        report = self.gate([a])
        self.record.write_text(json.dumps({'situacao': 'talvez', 'aprovacao': 'aprovado', 'lote': {'roots': report['roots']}}),
                               encoding='utf-8')
        self.assertEqual(self.gate([a])['status'], 'pending')

    def test_an_exhausted_matching_budget_is_an_error_not_a_pass(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n', TEMPLATE: 'b\n'})
        original = browser_gate.MATCH_BUDGET_SECONDS
        browser_gate.MATCH_BUDGET_SECONDS = -1
        self.addCleanup(setattr, browser_gate, 'MATCH_BUDGET_SECONDS', original)
        with self.assertRaises(ValueError):
            self.gate([a])

    def test_an_explicit_null_decision_reads_the_legacy_field(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        report = self.gate([a])
        self.record.write_text(json.dumps({'situacao': None, 'aprovacao': 'aprovado', 'lote': {'roots': report['roots']}}),
                               encoding='utf-8')
        self.assertEqual(self.gate([a])['status'], 'answered')

    def test_a_big_file_is_hashed_whole(self):
        a = self.slice('slice-a')
        big = a / 'web/src/app/big.component.ts'
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_bytes(b'x' * (3 * 1024 * 1024))
        self.decide(self.gate([a]))
        with open(big, 'r+b') as handle:
            handle.seek(-1, 2)
            handle.write(b'y')
        self.assertEqual(self.gate([a])['status'], 'stale')

    def test_a_config_that_is_not_an_object_is_an_error_not_a_traceback(self):
        a = self.slice('slice-a', **{SCREEN: 'a\n'})
        bad = Path(self.tmp.name) / 'bad.json'
        bad.write_text('[]', encoding='utf-8')
        done = self.cli([a], '--config', str(bad))
        self.assertEqual(done.returncode, 1)
        self.assertNotIn('Traceback', done.stderr)
        self.assertIn('error', json.loads(done.stderr))
        missing = self.cli([a], '--config', str(Path(self.tmp.name) / 'none.json'))
        self.assertEqual(missing.returncode, 1)


class StackedSliceTests(GateTestCase):
    """A slice named with `stacked` is measured from what it shares with the branch its PR targets: only its own changes."""

    def stacked_slice(self, name, parent, **files):
        root = Path(self.tmp.name) / name
        self.git(self.main, 'worktree', 'add', '-b', name, str(root), parent)
        for path, text in files.items():
            self.write(root, path, text)
        if files:
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-m', name)
        return root

    def setUp(self):
        super().setUp()
        self.parent = self.slice('slice-parent', **{SCREEN: 'parent\n', API: 'parent\n'})
        self.child1 = self.stacked_slice('slice-child1', 'slice-parent', **{'api/src/Other1.cs': 'c1\n'})
        self.child2 = self.stacked_slice('slice-child2', 'slice-parent', **{API_TEST: 'c2\n', 'api/src/Other2.cs': 'c2\n'})
        self.roots = [self.parent, self.child1, self.child2]
        self.stack = {'slice-child1': 'slice-parent', 'slice-child2': 'slice-parent'}

    def test_without_stacked_every_root_is_measured_from_the_base(self):
        result = self.gate(self.roots)
        self.assertEqual(result['by_root']['slice-child1'], [SCREEN])        # the parent's change is in the child's history
        self.assertEqual(result['stacked_on'], {})

    def test_api_only_children_stacked_on_a_screen_parent_are_not_visible_roots(self):
        result = self.gate(self.roots, stacked=self.stack)
        self.assertEqual(result['by_root'], {'slice-parent': [SCREEN], 'slice-child1': [], 'slice-child2': []})
        self.assertEqual(list(result['roots']), ['slice-parent'])
        self.assertEqual(sorted(result['other_roots']), ['slice-child1', 'slice-child2'])
        self.assertEqual(result['stacked_on'], self.stack)

    def test_one_decision_holds_while_the_children_keep_working(self):
        self.decide(self.gate(self.roots, stacked=self.stack))
        self.edit(self.child1, 'api/src/Other1.cs')
        self.git(self.child1, 'commit', '-am', 'more api')
        self.assertEqual(self.gate(self.roots, stacked=self.stack)['status'], 'answered')

    def test_a_new_commit_on_the_parent_makes_only_the_parent_stale(self):
        self.decide(self.gate(self.roots, stacked=self.stack))
        self.write(self.parent, SCREEN, 'parent again\n')
        self.git(self.parent, 'commit', '-am', 'parent fix')
        result = self.gate(self.roots, stacked=self.stack)
        self.assertEqual((result['status'], result['changed_roots']), ('stale', ['slice-parent']))
        self.assertEqual(result['by_root']['slice-child2'], [])             # the child was cut before the fix: its own work is unchanged

    def test_a_child_that_merged_the_new_parent_keeps_measuring_only_its_own_work(self):
        self.write(self.parent, SCREEN, 'parent again\n')
        self.git(self.parent, 'commit', '-am', 'parent fix')
        self.git(self.child1, 'merge', '--no-edit', 'slice-parent')
        result = self.gate(self.roots, stacked=self.stack)
        self.assertEqual(result['by_root']['slice-child1'], [])
        self.assertEqual(list(result['roots']), ['slice-parent'])

    def test_a_stacked_child_that_changes_the_screen_itself_is_visible_with_only_its_own_file(self):
        child = self.stacked_slice('slice-child3', 'slice-parent', **{TEMPLATE: 'child\n'})
        result = self.gate([self.parent, child], stacked={'slice-child3': 'slice-parent'})
        self.assertEqual(result['by_root'], {'slice-parent': [SCREEN], 'slice-child3': [TEMPLATE]})
        self.assertEqual(sorted(result['roots']), ['slice-child3', 'slice-parent'])

    def test_a_slice_not_named_stays_measured_from_the_base(self):
        other = self.slice('slice-other', **{TEMPLATE: 'other\n'})
        result = self.gate([self.parent, other], stacked={})
        self.assertEqual(result['by_root'], {'slice-parent': [SCREEN], 'slice-other': [TEMPLATE]})

    def test_the_target_may_be_a_branch_outside_the_batch(self):
        result = self.gate([self.child1, self.child2], toca='nao', stacked=self.stack)
        self.assertEqual((result['status'], result['front_files']), ('not_needed', []))

    def test_the_entries_must_name_a_root_and_an_existing_branch(self):
        with self.assertRaises(ValueError):
            self.gate(self.roots, stacked={'slice-nobody': 'slice-parent'})
        with self.assertRaises(ValueError):
            self.gate(self.roots, stacked={'slice-child1': 'no-such-branch'})
        for bad in ('child1', '=x', 'x=', ''):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                browser_gate.parse_stacked([bad])
        self.assertEqual(browser_gate.parse_stacked(['a=b', ' c = d ']), {'a': 'b', 'c': 'd'})

    def test_the_command_line_takes_repeated_stacked_entries(self):
        args = ['--stacked', 'slice-child1=slice-parent', '--stacked', 'slice-child2=slice-parent', '--toca', 'sim']
        done = self.cli(self.roots, *args)
        result = json.loads(done.stdout)
        self.assertEqual((done.returncode, result['status'], list(result['roots'])), (2, 'pending', ['slice-parent']))
        bad = self.cli(self.roots, '--stacked', 'child1')
        self.assertEqual(bad.returncode, 1)
        self.assertIn('error', json.loads(bad.stderr))


class CommandTests(GateTestCase):
    def setUp(self):
        super().setUp()
        self.config_file = Path(self.tmp.name) / 'config.json'
        self.config_file.write_text(json.dumps(self.config), encoding='utf-8')

    def test_exit_zero_when_nothing_is_owed_and_two_when_something_is(self):
        quiet = self.slice('slice-quiet', **{API: 'x\n'})
        done = self.cli([quiet], '--config', str(self.config_file), '--toca', 'não')
        self.assertEqual((done.returncode, json.loads(done.stdout)['status'], done.stderr), (0, 'not_needed', ''))
        loud = self.slice('slice-loud', **{SCREEN: 'x\n'})
        owed = self.cli([loud], '--config', str(self.config_file), '--toca', 'sim', '--record', str(self.record))
        self.assertEqual((owed.returncode, json.loads(owed.stdout)['status']), (2, 'pending'))
        self.decide(json.loads(owed.stdout))
        answered = self.cli([loud], '--config', str(self.config_file), '--toca', 'sim', '--record', str(self.record))
        self.assertEqual((answered.returncode, json.loads(answered.stdout)['status']), (0, 'answered'))
        self.edit(loud, SCREEN)
        stale = self.cli([loud], '--config', str(self.config_file), '--toca', 'sim', '--record', str(self.record))
        self.assertEqual((stale.returncode, json.loads(stale.stdout)['status']), (2, 'stale'))

    def test_a_contradiction_exits_two(self):
        loud = self.slice('slice-loud', **{TEMPLATE: 'x\n'})
        done = self.cli([loud], '--config', str(self.config_file))
        self.assertEqual((done.returncode, json.loads(done.stdout)['status']), (2, 'contradiction'))

    def test_an_unreadable_record_or_base_exits_one_without_a_traceback(self):
        a = self.slice('slice-a', **{SCREEN: 'x\n'})
        self.record.write_text('not json', encoding='utf-8')
        failed = self.cli([a], '--record', str(self.record))
        self.assertEqual(failed.returncode, 1)
        self.assertNotIn('Traceback', failed.stderr)
        self.assertIn('error', json.loads(failed.stderr))
        bad = subprocess.run([sys.executable, str(SCRIPT), 'browser-gate', '--base', 'nope', '--root', str(a)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(bad.returncode, 1)
        self.assertIn('error', json.loads(bad.stderr))


class CarriedPendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        for args in (('init', '-b', 'claude/fixture'), ('config', 'user.email', 'fixture@example.invalid'),
                     ('config', 'user.name', 'Fixture')):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        (self.root / 'a.txt').write_text('one', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'commit', '-m', 'fixture'], check=True, capture_output=True)
        self.handoff = Path(self.tmp.name) / 'handoff.md'
        self.handoff.write_text('state', encoding='utf-8')
        self.issue = {'number': 1, 'title': 't', 'body': 'b', 'state': 'open', 'source': 'local', 'labels': [],
                      'assignees': [], 'updated_at': 'x'}

    def test_a_checkpoint_carries_the_open_obligations_and_resume_lists_them(self):
        saved = frontlights.checkpoint(self.root, self.issue, self.handoff, 'next', ['teste_assistido', 'teste_assistido'])
        self.assertEqual(saved['pending'], ['teste_assistido'])
        resumed = frontlights.resume(self.root, saved, self.issue, self.handoff)
        self.assertEqual((resumed['state'], resumed['pending']), ('unchanged', ['teste_assistido']))

    def test_a_checkpoint_without_obligations_and_an_old_one_resume_with_an_empty_list(self):
        saved = frontlights.checkpoint(self.root, self.issue, self.handoff, 'next')
        self.assertEqual(saved['pending'], [])
        saved.pop('pending')
        self.assertEqual(frontlights.resume(self.root, saved, self.issue, self.handoff)['pending'], [])

    def test_a_pending_name_is_a_short_lowercase_word(self):
        for bad in ('Teste Assistido', '', 'x' * 41, '1abc', None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                frontlights.pending_names([bad])

    def run_context(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), 'context', *args], capture_output=True, text=True, encoding='utf-8')
        return done.returncode, json.loads(done.stdout) if done.stdout else done.stderr

    def test_the_context_command_asks_for_the_pending_watched_run_before_the_window_closes(self):
        self.assertEqual(self.run_context('--used', '50000', '--reserve', '5000'), (0, {'action': 'continue'}))
        code, result = self.run_context('--used', '50000', '--reserve', '5000', '--pending', 'teste_assistido')
        self.assertEqual((code, result), (0, {'action': 'continue', 'pending': ['teste_assistido']}))
        for used, action in (('99000', 'handoff'), ('160000', 'stop')):
            code, result = self.run_context('--used', used, '--reserve', '5000', '--pending', 'teste_assistido')
            with self.subTest(action=action):
                self.assertEqual((result['action'], result['ask_before_continuing']), (action, ['teste_assistido']))
        code, result = self.run_context('--used', '99000', '--reserve', '5000', '--pending', 'outra_coisa')
        self.assertNotIn('ask_before_continuing', result)

    def test_unknown_usage_still_stops_and_still_carries_the_pending(self):
        done = subprocess.run([sys.executable, str(SCRIPT), 'context', '--reserve', '5000', '--pending', 'teste_assistido'],
                              capture_output=True, text=True, encoding='utf-8')
        result = json.loads(done.stdout)
        self.assertEqual((result['action'], result['ask_before_continuing']), ('stop', ['teste_assistido']))


class FrontPathsConfigTests(unittest.TestCase):
    def check(self, front):
        config = {'repository': None, 'browserTest': {'users': [{'login': 'usuario@exemplo.test', 'password': 'senha-ficticia-longa'}],
                                                      'frontPaths': front}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            return frontlights.inspect(config, folder, path)

    def test_relative_globs_are_accepted(self):
        self.assertIn('sources', self.check(['web/src/**', 'app/*.html']))

    def test_anything_else_is_refused(self):
        for bad in ([], '/abs/path', ['/abs/path'], ['..\\x'], ['a/../b'], ['~/x'], ['C:/x'], [''], [1], ['x'] * 51):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.check(bad)

    def test_the_example_config_names_generic_front_paths(self):
        self.assertEqual(EXAMPLE['browserTest']['frontPaths'], ['web/src/**'])


class GateDocumentationTests(unittest.TestCase):
    def flat(self, *parts):
        return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())

    def test_the_rule_is_in_the_browser_reference_the_skill_and_the_development_reference(self):
        browser = self.flat('skills', 'frontlights', 'references', 'browser-testing.md')
        for phrase in ('browser-gate', 'one watched run per batch', 'before the independent review', 'lote.roots',
                       'situacao', 'ainda-nao', 'never one per branch or worktree', 'teste_assistido'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, browser)
        development = self.flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('browser-gate', 'before the independent review', 'teste_assistido'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)
        skill = self.flat('skills', 'frontlights', 'SKILL.md')
        for phrase in ('browser-gate', 'teste_assistido'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)
        self.assertIn('browser-gate', self.flat('skills', 'frontlights', 'templates', 'handoff.md'))

    def test_the_eval_the_runbook_and_the_record_cover_the_case(self):
        self.assertIn('browser-gate', self.flat('evals', 'batch-watched-run.md'))
        for name in (('skills', 'frontlights', 'references', 'browser-testing.md'), ('skills', 'frontlights', 'docs', 'security.md'), ('README.md',),
                     ('evals', 'batch-watched-run.md'), ('evals', 'runbook.md')):
            with self.subTest(doc=name[-1]):
                self.assertIn('dispensado', self.flat(*name))
        self.assertIn('19. One watched run per batch (`evals/batch-watched-run.md`)', self.flat('evals', 'runbook.md'))
        self.assertIn('| 19. Teste assistido por lote, antes da revisão | Pendente |', self.flat('docs', 'acceptance.md'))


if __name__ == '__main__':
    unittest.main()
