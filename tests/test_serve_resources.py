"""Recursos por sessão (retro do GeoCloud #1123/#1124, 23/10/2026): `{port:<nome>}`, `{issue}`,
`browserTest.runtimeConfig`, `browserTest.setup`/`teardown` e o rascunho do teste livre sem linha repetida.

Seam: `serve.py start|stop` por subprocesso numa worktree temporária, com um servidor falso que devolve o que recebeu
(argv e variáveis), e `serve.free_test_start`/`free_test_add` chamados direto.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
SCRIPT = SCRIPTS / 'serve.py'
sys.path.insert(0, str(SCRIPTS))
import serve  # noqa: E402

MOTIVO_SUITE_RAPIDA = ('FRONTLIGHTS_SUITE=rapida pula tests.test_serve_resources: o módulo sobe processos e portas de '
                       'verdade. Rode a suíte sem a variável antes da revisão independente e do PR.')


def load_tests(loader, tests, pattern):
    """Suíte rápida (issue 25): com FRONTLIGHTS_SUITE=rapida o módulo vira um teste pulado, com o motivo."""
    if os.environ.get('FRONTLIGHTS_SUITE') != 'rapida':
        return tests
    pulado = type('ModuloPulado', (unittest.TestCase,),
                  {'test_serve_resources': unittest.skip(MOTIVO_SUITE_RAPIDA)(lambda self: None)})
    return unittest.TestSuite([pulado('test_serve_resources')])


PASSWORD = 'senha-ficticia-9'
LOGIN = 'usuario1@exemplo.test'

# The port comes from argv[1]; the body is what the process received: argv and the FRONTLIGHTS_PORT_* variables.
ECHO_SERVER = r"""import http.server, json, os, sys
port = int(sys.argv[1])
body = json.dumps({'argv': sys.argv[1:], 'PORT': os.environ.get('PORT'),
                   'env': {k: v for k, v in os.environ.items() if k.startswith('FRONTLIGHTS_PORT_')}}).encode()
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()
"""
# A hook: appends its argv (and whether the runtime config exists) to hooks.log in the cwd; exits with argv[1].
HOOK = r"""import json, sys
from pathlib import Path
with open('hooks.log', 'a', encoding='utf-8') as log:
    log.write(json.dumps({'argv': sys.argv[2:], 'runtime': Path('runtime.json').exists()}) + '\n')
if sys.argv[1] != '0':
    print('falhou com ' + sys.argv[2] if len(sys.argv) > 2 else 'falhou')
sys.exit(int(sys.argv[1]))
"""


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as answer:
        return json.loads(answer.read().decode())


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ResourcesCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'worktree'
        self.root.mkdir()
        self.server = self.base / 'echo.py'
        self.server.write_text(ECHO_SERVER, encoding='utf-8')
        self.hook = self.base / 'hook.py'
        self.hook.write_text(HOOK, encoding='utf-8')
        self.config = self.base / 'config.json'
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if (self.root / '.frontlights' / 'serve' / '11.json').exists():
            subprocess.run([sys.executable, str(SCRIPT), 'stop', '--config', str(self.config), '--root',
                            str(self.root), '--issue', '11'], capture_output=True, timeout=120)

    def write_config(self, processes, **extra):
        block = {'processes': processes, 'baseUrl': 'http://127.0.0.1:1',
                 'users': [{'login': LOGIN, 'password': PASSWORD}], **extra}
        self.config.write_text(json.dumps({'repository': 'OWNER/REPOSITORY', 'roads': None, 'browserTest': block}),
                               encoding='utf-8')

    def auto(self, name, *argv):
        return {'name': name, 'argv': [sys.executable, str(self.server), '{port}', *argv], 'port': 'auto',
                'health': 'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}

    def hook_argv(self, code, *argv):
        return [sys.executable, str(self.hook), str(code), *argv]

    def serve(self, operation, config=True):
        command = [sys.executable, str(SCRIPT), operation, '--root', str(self.root), '--issue', '11']
        if config:
            command[3:3] = ['--config', str(self.config)]
        done = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=180)
        return done.returncode, json.loads(done.stdout), done.stdout + done.stderr

    def hooks(self):
        log = self.root / 'hooks.log'
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]

    def reservations(self):
        return sorted((self.root / '.frontlights' / 'serve' / 'ports').glob('*.json'))


class NamedPortTests(ResourcesCase):
    def test_a_process_reads_another_auto_port_by_argv_and_every_process_gets_every_variable(self):
        fixed = free_port()
        web = {'name': 'web', 'argv': [sys.executable, str(self.server), str(fixed), '--api=http://127.0.0.1:{port:api}',
                                       'issue-{issue}'],
               'port': fixed, 'health': f'http://127.0.0.1:{fixed}/', 'timeoutSeconds': 20}
        self.write_config([self.auto('api'), self.auto('smtp'), web])
        code, out, text = self.serve('start')
        self.assertEqual(code, 0, text)
        ports = {item['name']: item['port'] for item in out['processes']}
        self.assertEqual(out['ports'], {'api': ports['api'], 'smtp': ports['smtp']})
        seen = fetch(f'http://127.0.0.1:{fixed}/')
        self.assertEqual(seen['argv'][1:], [f'--api=http://127.0.0.1:{ports["api"]}', 'issue-11'])
        self.assertEqual(seen['env'], {'FRONTLIGHTS_PORT_API': str(ports['api']),
                                       'FRONTLIGHTS_PORT_SMTP': str(ports['smtp'])})
        self.assertIsNone(seen['PORT'], 'PORT é só a porta própria de um processo auto')
        api = fetch(f'http://127.0.0.1:{ports["api"]}/')
        self.assertEqual((api['PORT'], api['env']['FRONTLIGHTS_PORT_SMTP']), (str(ports['api']), str(ports['smtp'])))

    def test_a_health_may_name_the_port_of_another_process(self):
        probe = {'name': 'probe', 'argv': [sys.executable, '-c', 'import time; time.sleep(60)'],
                 'health': 'http://127.0.0.1:{port:api}/', 'timeoutSeconds': 20}
        self.write_config([self.auto('api'), probe])
        code, out, text = self.serve('start')
        self.assertEqual(code, 0, text)
        by_name = {item['name']: item for item in out['processes']}
        self.assertEqual(by_name['probe']['port'], by_name['api']['port'])

    def test_an_unknown_or_fixed_name_is_a_usage_refusal_before_anything_runs(self):
        fixed = free_port()
        fixed_process = {'name': 'fixo', 'argv': [sys.executable, str(self.server), str(fixed)], 'port': fixed,
                         'health': f'http://127.0.0.1:{fixed}/'}
        for where in ('{port:nada}', '{port:fixo}'):
            with self.subTest(where=where):
                self.write_config([self.auto('api', where), fixed_process], setup=[self.hook_argv(0, 'x')])
                code, out, _ = self.serve('start')
                self.assertEqual((code, out['category']), (1, 'uso'))
                self.assertIn(where, out['error'])
                self.assertEqual((self.reservations(), self.hooks()), ([], []))
                self.assertFalse((self.root / '.frontlights' / 'serve' / '11.json').exists())

    def test_a_list_without_auto_processes_refuses_a_named_port(self):
        with self.assertRaises(serve.Refusal) as caught:
            serve.validate_processes([{'name': 'web', 'argv': ['x', '{port:web}'], 'health': 'http://127.0.0.1:4200/'}],
                                     'preview.processes')
        self.assertEqual(caught.exception.category, 'uso')
        self.assertIn('nenhum declarado', str(caught.exception))


class RuntimeConfigTests(ResourcesCase):
    def test_it_is_written_before_the_first_spawn_with_the_ports_and_removed_on_stop(self):
        self.write_config([self.auto('api')], runtimeConfig={
            'path': 'runtime.json',
            'content': {'apiUrl': 'http://127.0.0.1:{port:api}', 'nested': [{'db': 'banco_issue_{issue}'}], 'n': 3}},
            setup=[self.hook_argv(0, 'antes')])
        code, out, text = self.serve('start')
        self.assertEqual(code, 0, text)
        port = out['processes'][0]['port']
        target = self.root / 'runtime.json'
        self.assertEqual(out['runtimeConfig'], 'runtime.json')
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')),
                         {'apiUrl': f'http://127.0.0.1:{port}', 'nested': [{'db': 'banco_issue_11'}], 'n': 3})
        self.assertEqual(self.hooks(), [{'argv': ['antes'], 'runtime': False}], 'o setup roda antes do runtimeConfig')
        code, out, text = self.serve('stop')
        self.assertEqual(code, 0, text)
        self.assertTrue(out['runtimeConfigRemovido'])
        self.assertFalse(target.exists())

    def test_a_path_outside_the_worktree_or_a_bad_shape_is_refused(self):
        for spec in ({'path': '../fora.json', 'content': {}}, {'path': 'C:/fora.json', 'content': {}},
                     {'path': 'pasta-que-nao-existe/x.json', 'content': {}}, {'path': 'x.json', 'content': []},
                     {'path': 'x.json', 'content': {'u': '{port}'}}, {'path': 'x.json', 'content': {'u': '{port:web}'}}):
            with self.subTest(spec=spec):
                self.write_config([self.auto('api')], runtimeConfig=spec)
                code, out, _ = self.serve('start')
                self.assertEqual((code, out['category']), (1, 'uso'), out)
                self.assertEqual(self.reservations(), [])

    def test_a_failed_start_removes_it_and_runs_the_teardown(self):
        dying = {'name': 'web', 'argv': [sys.executable, '-c', 'raise SystemExit(3)'], 'port': 'auto',
                 'health': 'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}
        self.write_config([self.auto('api'), dying], runtimeConfig={'path': 'runtime.json', 'content': {'a': 'b'}},
                          setup=[self.hook_argv(0, 'clona', 'db_issue_{issue}')],
                          teardown=[self.hook_argv(0, 'descarta', 'db_issue_{issue}')])
        code, out, text = self.serve('start')
        self.assertEqual((code, out['category'], out['failedProcess']), (1, 'infraestrutura', 'web'), text)
        self.assertFalse((self.root / 'runtime.json').exists())
        self.assertEqual([entry['argv'] for entry in self.hooks()],
                         [['clona', 'db_issue_11'], ['descarta', 'db_issue_11']])
        self.assertEqual(self.reservations(), [])


class SetupTeardownTests(ResourcesCase):
    def test_setup_runs_before_and_teardown_after_stop_even_without_config_on_the_stop(self):
        self.write_config([self.auto('api')], setup=[self.hook_argv(0, 'clona', 'db_issue_{issue}')],
                          teardown=[self.hook_argv(0, 'descarta', 'db_issue_{issue}')])
        code, out, text = self.serve('start')
        self.assertEqual(code, 0, text)
        self.assertEqual(out['setup'][0][-2:], ['clona', 'db_issue_11'])
        code, out, text = self.serve('stop', config=False)   # the registry remembers the start's config
        self.assertEqual(code, 0, text)
        self.assertEqual([entry['argv'] for entry in self.hooks()],
                         [['clona', 'db_issue_11'], ['descarta', 'db_issue_11']])

    def test_a_failed_setup_spawns_nothing_and_releases_the_ports_with_its_output_masked(self):
        self.write_config([self.auto('api')], setup=[self.hook_argv(5, PASSWORD)])
        code, out, text = self.serve('start')
        self.assertEqual((code, out['category'], out['failedProcess']), (1, 'infraestrutura', 'browserTest.setup[0]'))
        self.assertIn('código 5', out['error'])
        self.assertTrue(out['tail'])
        self.assertNotIn(PASSWORD, text)
        self.assertEqual(self.reservations(), [])
        self.assertFalse((self.root / '.frontlights' / 'serve' / '11.json').exists())

    def test_hooks_take_only_issue_and_must_be_argv_lists(self):
        for hooks in ('npm run db', [['x', '{port:api}']], [[]], [['x', '{port}']]):
            with self.subTest(hooks=hooks):
                self.write_config([self.auto('api')], teardown=hooks)
                code, out, _ = self.serve('start')
                self.assertEqual((code, out['category']), (1, 'uso'))


class FreeTestDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'browserTest': {'baseUrl': 'http://127.0.0.1:4200/', 'users': []}}),
                               encoding='utf-8')
        self.draft = self.root / '.frontlights' / 'issues' / '12' / 'teste-livre-cas.md'

    def boxes(self):
        return [line for line in self.draft.read_text(encoding='utf-8').splitlines() if line.startswith('- [')]

    def test_add_appends_once_and_a_second_start_keeps_the_draft_without_repeats(self):
        serve.free_test_start(str(self.config), str(self.root), 12)
        first = serve.free_test_add(str(self.config), str(self.root), 12, ['P1 menu some', 'P2 botão volta'])
        self.assertEqual((first['added'], first['alreadyThere']), (['- [ ] P1 menu some', '- [ ] P2 botão volta'], 0))
        again = serve.free_test_add(str(self.config), str(self.root), 12, ['P1  menu some', '- [x] P2 botão volta'])
        self.assertEqual((again['added'], again['alreadyThere']), ([], 2))
        with self.draft.open('a', encoding='utf-8') as handle:   # a session that appended by hand, twice
            handle.write('- [ ] P1 menu some\n- [x] P2 botão volta\n')
        started = serve.free_test_start(str(self.config), str(self.root), 12)
        self.assertEqual(started['repetidasRemovidas'], 2)
        self.assertEqual(self.boxes(), ['- [ ] P1 menu some', '- [ ] P2 botão volta'])

    def test_add_needs_the_draft_and_a_box(self):
        with self.assertRaises(serve.Refusal):
            serve.free_test_add(str(self.config), str(self.root), 12, ['P1'])
        serve.free_test_start(str(self.config), str(self.root), 12)
        for boxes in ([], ['  '], ['duas\nlinhas']):
            with self.subTest(boxes=boxes), self.assertRaises(serve.Refusal):
                serve.free_test_add(str(self.config), str(self.root), 12, boxes)


if __name__ == '__main__':
    unittest.main()
