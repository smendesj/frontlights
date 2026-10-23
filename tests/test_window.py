"""Issue 8: `serve.py window`, a janela visível do teste assistido entregue por script.

Seam: `_window.main([...])` (o que `serve.py window` chama) e o próprio `serve.py window` por subprocesso. O Chrome é
um processo Python que imita a porta de depuração (escreve `DevToolsActivePort` no perfil e responde
`/json/version`); o Playwright é simulado trocando `_window.find_playwright` e `_window.run_driver`. Nada é
instalado: os testes conferem que nenhum argv chamado tem `install`.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import _window  # noqa: E402
import serve  # noqa: E402

FAKE_CHROME = r"""import http.server, sys, threading
profile = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--user-data-dir='))
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"Browser": "Chrome/fake"}')
    def log_message(self, *a):
        pass
server = http.server.HTTPServer(('127.0.0.1', 0), H)
open(profile + '/DevToolsActivePort', 'w').write(str(server.server_address[1]) + '\n/devtools/browser/x\n')
server.serve_forever()
"""
PLAYWRIGHT = ('node', '/simulado/node_modules/playwright', 'node_modules')
CONFIG = {'repository': 'OWNER/REPOSITORY',
          'browserTest': {'baseUrl': 'http://127.0.0.1:4200/',
                          'users': [{'login': 'usuario1@exemplo.test', 'password': 'senha-ficticia'},
                                    {'login': 'usuario2@exemplo.test', 'password': 'senha-ficticia'}],
                          'processes': [{'name': 'web', 'argv': ['npm', 'start'], 'health': 'http://127.0.0.1:4200/'}],
                          'login': {'user': '#login', 'password': '#senha', 'submit': 'button[type=submit]'}}}


class FakeDriver:
    """The Node driver, simulated: records each call and answers like window_driver.cjs."""

    def __init__(self, fits=True, hold=None):
        self.calls = []
        self.fits = fits
        self.hold = hold

    def __call__(self, playwright, command, payload, env=None, timeout=None):
        self.calls.append((command, payload, dict(env or {})))
        if command == 'open':
            Path(payload['check']).write_bytes(b'png')
            return {'ok': True, 'fits': self.fits, 'checkShot': payload['check'], 'login': 'script'}
        if command == 'shot':
            Path(payload['path']).write_bytes(b'\x89PNG')
            return {'ok': True, 'path': payload['path']}
        if command == 'hold':
            return self.hold(payload)
        return {'ok': False, 'error': 'inesperado'}


class WindowCase(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / 'fake_chrome.py'
        self.fake.write_text(FAKE_CHROME, encoding='utf-8')
        self.write_config(CONFIG)
        self.driver = FakeDriver()
        self.patches = [mock.patch.object(_window, 'find_chrome', lambda playwright=None: [sys.executable, str(self.fake)]),
                        mock.patch.object(_window, 'find_playwright', lambda config, tree, root: PLAYWRIGHT),
                        mock.patch.object(_window, 'run_driver', self.driver),
                        mock.patch.object(_window.shutil, 'which', self.which)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.close_all)

    @staticmethod
    def which(name):
        return 'node' if name == 'node' else None

    def write_config(self, config):
        (self.root / '.frontlights').mkdir(exist_ok=True)
        (self.root / '.frontlights' / 'config.json').write_text(json.dumps(config), encoding='utf-8')

    def window(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = _window.main([*args, '--root', str(self.root), '--tree', str(self.root), '--full'])
        return code, json.loads(out.getvalue())

    def close_all(self):
        for state in self.root.glob('.frontlights/**/window.json'):
            data = json.loads(state.read_text(encoding='utf-8'))
            if serve.pid_alive(data.get('pid')):
                serve.kill_tree(data['pid'])
            _window.remove_profile(data.get('profileDir'))


class OpenAndCloseTests(WindowCase):

    def test_open_records_cdp_url_pid_and_profile_and_close_stops_only_what_it_started(self):
        code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        self.assertEqual(code, 0, out)
        state = json.loads((self.root / '.frontlights/issues/12/browser/window.json').read_text(encoding='utf-8'))
        for key in ('cdpUrl', 'pid', 'profileDir'):
            self.assertEqual(state[key], out[key])
        self.assertTrue(state['cdpUrl'].startswith('http://127.0.0.1:'))
        self.assertTrue(serve.pid_alive(out['pid']))
        self.assertTrue(out['fits'])
        self.assertTrue(out['checkShot'].startswith(out['profileDir']), 'a conferência não é guardada')
        self.assertEqual(out['driver'], 'playwright')
        self.assertIn('preparo:', out['message'])
        self.assertIsInstance(out['preparoSegundos'], float)
        opened = self.driver.calls[0]
        self.assertEqual(opened[1]['strip'], 'ANTES: origin/main')
        self.assertEqual(opened[2]['FRONTLIGHTS_WINDOW_USER'], 'usuario1@exemplo.test')
        self.assertNotIn('senha-ficticia', json.dumps(opened[1]), 'a senha vai só por variável de ambiente')
        self.assertNotIn('senha-ficticia', json.dumps(out))
        code, closed = self.window('close', '--issue', '12')
        self.assertEqual(code, 0, closed)
        self.assertTrue(closed['closed'])
        self.assertIn('só o Chrome que este script abriu', closed['message'])
        self.assertFalse(serve.pid_alive(out['pid']))
        self.assertFalse(Path(out['profileDir']).exists())

    def test_close_never_stops_a_pid_that_is_not_the_chrome_it_started(self):
        code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        path = self.root / '.frontlights/issues/12/browser/window.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        state['identity'] = 'outro-processo'
        path.write_text(json.dumps(state), encoding='utf-8')
        code, closed = self.window('close', '--issue', '12')
        self.assertFalse(closed['closed'])
        self.assertIn('nada foi parado', closed['message'])
        self.assertTrue(serve.pid_alive(out['pid']))
        serve.kill_tree(out['pid'])

    def test_a_second_open_is_refused_while_the_window_lives(self):
        self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        self.assertEqual(code, 1)
        self.assertIn('window attach', out['error'])

    def test_without_playwright_chrome_opens_with_the_cdp_port_and_nothing_is_installed(self):
        calls = []
        real_run = subprocess.run

        def spy(argv, *args, **kwargs):
            calls.append(list(argv))
            return real_run(argv, *args, **kwargs)

        with mock.patch.object(_window, 'find_playwright', lambda config, tree, root: None), \
                mock.patch.object(_window.subprocess, 'run', spy):
            code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        self.assertEqual(code, 0, out)
        self.assertEqual(out['driver'], 'cdp')
        self.assertIsNone(out['fits'])
        self.assertIn('Nada foi instalado', out['message'])
        self.assertFalse([argv for argv in calls if 'install' in ' '.join(map(str, argv))])
        self.assertEqual(self.driver.calls, [])

    def test_without_chrome_the_open_is_an_infrastructure_refusal(self):
        with mock.patch.object(_window, 'find_chrome', lambda playwright=None: None):
            code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        self.assertEqual(code, 1)
        self.assertEqual(out['category'], 'infraestrutura')
        self.assertIn('Nada foi instalado', out['error'])

    def test_the_strip_carries_no_login_nor_local_path(self):
        for strip in ('ANTES: usuario1@exemplo.test', 'ANTES: C:\\Users\\alguem', 'qualquer coisa',
                      'DEPOIS: branch x /home/alguem'):
            with self.subTest(strip=strip):
                code, out = self.window('open', '--issue', '12', '--strip', strip)
                self.assertEqual((code, out['category']), (1, 'uso'))
        code, out = self.window('open', '--issue', '12', '--strip', 'DEPOIS: branch PREFIX/issue-12')
        self.assertEqual(code, 0, out)

    def test_only_a_local_base_url_is_opened(self):
        code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main',
                                '--base-url', 'https://staging.example.com/')
        self.assertEqual((code, out['category']), (1, 'uso'))

    def test_a_project_without_processes_is_the_users_environment(self):
        config = json.loads(json.dumps(CONFIG))
        del config['browserTest']['processes']
        self.write_config(config)
        code, out = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        self.assertEqual(out['ambiente'], 'ambiente_do_usuario')
        self.assertIn('de pé na branch', out['question'])

    def test_the_cli_routes_window_to_its_own_parser(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'serve.py'), 'window', '--help'], capture_output=True,
                              text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0)
        for op in ('open', 'attach', 'hold', 'shot', 'close'):
            self.assertIn(op, done.stdout)
        done = subprocess.run([sys.executable, str(SCRIPTS / 'serve.py'), 'window', 'voar'], capture_output=True,
                              text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)['category'], 'uso')


class AttachTests(WindowCase):

    def test_attach_reuses_a_live_window(self):
        _, opened = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        code, out = self.window('attach', '--issue', '12')
        self.assertEqual(code, 0, out)
        self.assertFalse(out['reopened'])
        self.assertEqual(out['pid'], opened['pid'])

    def test_attach_reopens_a_dead_window_on_the_same_base_without_a_question(self):
        _, opened = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        serve.kill_tree(opened['pid'])
        code, out = self.window('attach', '--issue', '12')
        self.assertEqual(code, 0, out)
        self.assertTrue(out['reopened'])
        self.assertNotEqual(out['pid'], opened['pid'])
        self.assertEqual(out['strip'], 'ANTES: origin/main')
        self.assertNotIn('question', out)
        self.assertFalse(Path(opened['profileDir']).exists())


class ShotTests(WindowCase):

    def test_a_shot_is_named_by_pass_cover_and_criterion_in_the_evidence_dir(self):
        self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        code, out = self.window('shot', '--issue', '12', '--pass', 'antes', '--criterion', 'S2')
        self.assertEqual(code, 0, out)
        self.assertEqual(out['file'], 'antes-12-S2.png')
        self.assertTrue(Path(out['path']).is_file())
        self.assertEqual(Path(out['path']).parent, self.root / '.frontlights/issues/12/browser')

    def test_the_shot_writes_the_print_into_result_json_with_the_schema_of_the_gate(self):
        """Esquema único: `window shot` e `browser-gate record` gravam os campos de protocol.md."""
        import browser_gate
        self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        code, out = self.window('shot', '--issue', '12', '--pass', 'antes', '--criterion', 'S2')
        record = json.loads((self.root / '.frontlights/issues/12/browser/result.json').read_text(encoding='utf-8'))
        self.assertEqual(record['passadas']['antes']['criterios']['S2']['print'], 'antes-12-S2.png')
        self.assertEqual(record['pastaDosPrints'], out['evidenceDir'])
        self.assertLessEqual(set(record), set(browser_gate.RECORD_FIELDS))
        self.assertLessEqual(set(record['passadas']['antes']), set(browser_gate.PASS_FIELDS))
        self.assertLessEqual(set(record['passadas']['antes']['criterios']['S2']), set(browser_gate.CRITERION_FIELDS))

    def test_a_shot_goes_to_the_sprint_folder_when_the_config_names_it(self):
        scrum = self.root / 'SCRUM'
        scrum.mkdir()
        config = dict(CONFIG, roadmapSync={'enabled': False, 'scrumRoot': str(scrum),
                                            'weekFolderPattern': '{yyyy}/{dd_MM}'})
        self.write_config(config)
        self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        code, out = self.window('shot', '--issue', '12', '--pass', 'depois', '--criterion', 'S1', '--cover', '10')
        self.assertEqual(code, 0, out)
        self.assertEqual(out['file'], 'depois-10-S1.png')
        relative = Path(out['path']).relative_to(scrum).as_posix()
        self.assertRegex(relative, r'^\d{4}/\d{2}_\d{2}/evidencias/REPOSITORY/12/depois-10-S1\.png$')

    def test_shots_before_the_number_wait_in_the_pending_folder_and_move_when_it_comes(self):
        code, out = self.window('open', '--strip', 'ANTES: origin/main')
        self.assertEqual(code, 0, out)
        self.assertIsNone(out['issue'])
        self.assertTrue((self.root / '.frontlights/evidencias-pendentes/window.json').is_file())
        code, shot = self.window('shot', '--pass', 'antes', '--name', 'tela-1')
        self.assertEqual(shot['file'], 'antes-pendente-tela-1.png')
        self.assertEqual(Path(shot['path']).parent, self.root / '.frontlights/evidencias-pendentes')
        code, attached = self.window('attach', '--issue', '31')
        self.assertEqual(code, 0, attached)
        self.assertEqual(sorted(attached['pendentesMovidos']), ['antes-31-tela-1.png', 'window.json'])
        self.assertTrue((self.root / '.frontlights/issues/31/browser/antes-31-tela-1.png').is_file())
        self.assertFalse(list((self.root / '.frontlights/evidencias-pendentes').glob('*.png')))

    def test_one_print_per_criterion_or_one_label(self):
        self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        for extra in ((), ('--criterion', 'S2', '--name', 'tela'), ('--criterion', 'passo-3')):
            with self.subTest(extra=extra):
                code, out = self.window('shot', '--issue', '12', '--pass', 'antes', *extra)
                self.assertEqual((code, out['category']), (1, 'uso'))


class HoldTests(WindowCase):

    def test_the_holder_reports_the_user_closing_the_window(self):
        def hold(payload):
            state = json.loads((self.root / '.frontlights/issues/12/browser/window.json').read_text(encoding='utf-8'))
            serve.kill_tree(state['pid'])
            return {'ok': True, 'ended_by': 'disconnected'}

        self.driver.hold = hold
        self.window('open', '--issue', '12', '--strip', 'DEPOIS: branch PREFIX/issue-12')
        code, out = self.window('hold', '--issue', '12', '--minutes', '5')
        self.assertEqual(code, 0, out)
        self.assertEqual(out['ended_by'], 'disconnected')
        self.assertIn('Nenhum dos dois é resposta', out['message'])
        self.assertEqual(self.driver.calls[-1][1]['minutes'], 5)
        state = json.loads((self.root / '.frontlights/issues/12/browser/window.json').read_text(encoding='utf-8'))
        self.assertEqual(state['endedBy'], 'disconnected')

    def test_at_the_deadline_the_holder_closes_the_window_itself(self):
        self.driver.hold = lambda payload: {'ok': True, 'ended_by': 'prazo'}
        _, opened = self.window('open', '--issue', '12', '--strip', 'DEPOIS: branch PREFIX/issue-12')
        code, out = self.window('hold', '--issue', '12', '--minutes', '5')
        self.assertEqual(out['ended_by'], 'prazo')
        self.assertTrue(out['closedByHolder'])
        self.assertFalse(serve.pid_alive(opened['pid']))

    def test_without_a_driver_the_holder_watches_the_window_itself_with_no_time_limit(self):
        with mock.patch.object(_window, 'find_playwright', lambda config, tree, root: None):
            _, opened = self.window('open', '--issue', '12', '--strip', 'ANTES: origin/main')
        threading.Timer(1.0, serve.kill_tree, [opened['pid']]).start()
        started = time.monotonic()
        code, out = self.window('hold', '--issue', '12', '--minutes', 'none')
        self.assertEqual(out['ended_by'], 'disconnected')
        self.assertLess(time.monotonic() - started, 30)


class BriefTests(WindowCase):
    """Issue 8, S3: `window brief` preenche references/browser-conductor.md; o coordenador não o lê."""

    REFERENCE = ROOT / 'skills' / 'frontlights' / 'references' / 'browser-conductor.md'

    def test_every_placeholder_is_filled_and_the_brief_is_written_beside_the_record(self):
        _, opened = self.window('open', '--issue', '12', '--strip', 'DEPOIS: branch PREFIX/issue-12')
        code, out = self.window('brief', '--issue', '12', '--pass', 'depois', '--criteria', 'S1,S2')
        self.assertEqual(code, 0, out)
        brief = Path(out['brief'])
        self.assertEqual(brief, self.root / '.frontlights/issues/12/browser/brief-depois.md')
        text = brief.read_text(encoding='utf-8')
        self.assertNotIn('{{', text)
        self.assertIn('DEPOIS: branch PREFIX/issue-12', text)
        self.assertIn('S1, S2', text)
        self.assertIn(opened['cdpUrl'], text)
        self.assertIn('--minutes 5', text)
        self.assertIn('Do not return your report before the holder exits', text)
        self.assertNotIn('senha-ficticia', text)
        self.assertEqual(out['window'], 'aberta')

    def test_the_antes_brief_holds_without_a_time_limit_and_works_before_the_window_opens(self):
        code, out = self.window('brief', '--issue', '12', '--pass', 'antes', '--criteria', 'S1')
        self.assertEqual(code, 0, out)
        text = Path(out['brief']).read_text(encoding='utf-8')
        self.assertIn('--minutes none', text)
        self.assertIn('ANTES: origin/main', text)
        self.assertIn('not open: step 1 opens it', text)
        self.assertEqual(out['window'], 'fechada')

    def test_criteria_are_required(self):
        code, out = self.window('brief', '--issue', '12', '--pass', 'antes')
        self.assertEqual((code, out['category']), (1, 'uso'))

    def test_the_reference_is_english_with_the_portuguese_anchor_and_no_verdict(self):
        text = ' '.join(self.REFERENCE.read_text(encoding='utf-8').split())
        self.assertIn('**Portuguese.** Everything the user reads', text)
        self.assertIn('You never decide whether the pass passed', text)
        self.assertIn("Chrome driven by Playwright, visible, disposable profile, never Claude's built-in browser nor "
                      'Claude in Chrome', text)
        self.assertIn('Closing the window or the 5 minutes ending is never an answer', text)
        self.assertLessEqual(len(text.split()), 990)


class PlaywrightResolutionTests(unittest.TestCase):
    """The order: browserTest.playwright, PLAYWRIGHT_PATH, node_modules, the npx cache; nothing without Node."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tree = Path(temp.name)
        for name in ('declared', 'env', 'node_modules/playwright'):
            (self.tree / name).mkdir(parents=True)
            (self.tree / name / 'package.json').write_text('{}', encoding='utf-8')

    def find(self, config, env, node='node'):
        with mock.patch.object(_window.shutil, 'which', lambda name: node if name == 'node' else None), \
                mock.patch.dict(os.environ, env, clear=False), mock.patch.object(_window, 'npx_caches', lambda: []):
            if 'PLAYWRIGHT_PATH' not in env:
                os.environ.pop('PLAYWRIGHT_PATH', None)
            return _window.find_playwright(config, self.tree, self.tree)

    def test_the_order(self):
        declared = {'browserTest': {'playwright': 'declared'}}
        env = {'PLAYWRIGHT_PATH': str(self.tree / 'env')}
        self.assertEqual(self.find(declared, env)[2], 'browserTest.playwright')
        self.assertEqual(self.find({}, env)[2], 'PLAYWRIGHT_PATH')
        self.assertEqual(self.find({}, {})[2], 'node_modules')
        self.assertIsNone(self.find({}, {}, node=None))

    def test_nothing_is_installed_by_the_window(self):
        for path in (SCRIPTS / '_window.py', SCRIPTS / 'window_driver.cjs'):
            text = path.read_text(encoding='utf-8')
            for word in ('npm install', 'npx playwright install', 'pip install', "'install'"):
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, text)


if __name__ == '__main__':
    unittest.main()
