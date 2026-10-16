"""Prévia de longa duração do serve (issue 34, CA S1): `serve.py preview start|status|stop`.

Processos falsos (um servidor HTTP em Python que imprime um marcador e, quando pedido, a senha fictícia no
stdout), config temporário com o bloco `preview` e contas fictícias em `browserTest.users` para provar a
máscara do log. Cada chamada ao serve é um processo novo (uma "sessão" nova), como no uso real.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import serve  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts' / 'serve.py'
MOTIVO_SUITE_RAPIDA = ('FRONTLIGHTS_SUITE=rapida pula tests.test_serve_preview: o módulo sobe processos e portas de '
                       'verdade. Rode a suíte sem a variável antes da revisão independente e do PR.')
PASSWORD = 'senha-fake'
LOGIN = 'usuario1@exemplo.test'
MARKER = 'MARCADOR-DA-PREVIA'
MASK = '[redacted]'


def load_tests(loader, tests, pattern):
    """Marcação da suíte rápida (issue 25): com FRONTLIGHTS_SUITE=rapida o módulo inteiro vira um único teste
    pulado, com o motivo; qualquer outro valor, ou a ausência da variável, carrega tudo como sempre."""
    if os.environ.get('FRONTLIGHTS_SUITE') != 'rapida':
        return tests
    pulado = type('ModuloPulado', (unittest.TestCase,),
                  {'test_serve_preview': unittest.skip(MOTIVO_SUITE_RAPIDA)(lambda self: None)})
    return unittest.TestSuite([pulado('test_serve_preview')])


# Fake server of the preview: port from argv[1]; prints one line with the marker and, when given, the secret.
PREVIEW_SERVER = r"""import http.server
import sys

port = int(sys.argv[1])
secret = sys.argv[3] if len(sys.argv) > 3 else ''
print(sys.argv[2] + ' ouvindo na porta ' + str(port) + ' senha=' + secret, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *args):
        pass


http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def reachable(url):
    try:
        urllib.request.urlopen(url, timeout=2).close()
        return True
    except OSError:
        return False


def wait_until(condition, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


class PreviewTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'main'
        self.root.mkdir()
        self.worktree = self.root / '.claude' / 'worktrees' / 'previa'
        self.worktree.mkdir(parents=True)
        self.script = Path(self.tmp.name) / 'preview_server.py'
        self.script.write_text(PREVIEW_SERVER, encoding='utf-8')
        self.config = Path(self.tmp.name) / 'config.json'
        self.addCleanup(self.kill_leftovers)  # safety net, so a refused stop never leaves a fake server behind
        self.addCleanup(self.serve, 'preview', 'stop')
        self.addCleanup(self.serve, 'stop', issue=9)

    def kill_leftovers(self):
        for path in (self.registry(), self.issue_registry()):
            if path.is_file():
                for entry in json.loads(path.read_text(encoding='utf-8')).get('processes', []):
                    for key in ('pid', 'relayPid'):
                        if serve.valid_pid(entry.get(key)):
                            serve.kill_tree(entry[key])
        time.sleep(0.2)

    def preview_process(self, name='web', secret=PASSWORD, **extra):
        entry = {'name': name, 'argv': [sys.executable, str(self.script), '{port}', MARKER] + ([secret] if secret else []),
                 'port': 'auto', 'health': 'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}
        entry.update(extra)
        return entry

    def issue_process(self, name='web'):
        port = free_port()
        return {'name': name, 'argv': [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
                'port': port, 'health': f'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}

    def write_config(self, preview='default', issue_processes=None, worktree='.claude/worktrees/previa'):
        config = {'repository': 'OWNER/REPOSITORY', 'roads': None,
                  'browserTest': {'baseUrl': 'http://127.0.0.1:1', 'users': [{'login': LOGIN, 'password': PASSWORD}],
                                  'processes': issue_processes or [self.issue_process()]}}
        if preview == 'default':
            preview = {'worktree': worktree, 'branch': 'previa', 'baseUrl': 'http://127.0.0.1:1/',
                       'processes': [self.preview_process()]}
        if preview is not None:
            config['preview'] = preview
        self.config.write_text(json.dumps(config), encoding='utf-8')

    def serve(self, *args, issue=None):
        argv = [sys.executable, str(SCRIPT), *args, '--config', str(self.config), '--root', str(self.root)]
        if issue is not None:
            argv += ['--issue', str(issue)]
        done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.last = done
        return done

    def payload(self, done):
        return json.loads(done.stdout)

    def registry(self):
        return self.root / '.frontlights' / 'preview' / 'registry.json'

    def issue_registry(self, issue=9):
        return self.root / '.frontlights' / 'serve' / f'{issue}.json'

    def log(self, name='web'):
        return self.root / '.frontlights' / 'preview' / 'log' / f'{name}.log'

    def start_preview(self):
        done = self.serve('preview', 'start')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return self.payload(done)


class PreviewStartTest(PreviewTestCase):
    def test_start_brings_the_preview_up_records_it_and_saves_a_masked_log(self):
        self.write_config()
        result = self.start_preview()
        self.assertTrue(result['ok'])
        self.assertEqual(result['worktree'], '.claude/worktrees/previa')
        self.assertEqual(result['branch'], 'previa')
        self.assertEqual(result['baseUrl'], 'http://127.0.0.1:1/')
        process = result['processes'][0]
        self.assertEqual(process['name'], 'web')
        self.assertIsInstance(process['pid'], int)
        self.assertIsInstance(process['port'], int)
        self.assertTrue(reachable(process['url']))
        self.assertTrue(self.registry().is_file())
        record = json.loads(self.registry().read_text(encoding='utf-8'))
        self.assertEqual(record['worktree'], '.claude/worktrees/previa')
        self.assertEqual(record['branch'], 'previa')
        self.assertEqual(record['processes'][0]['pid'], process['pid'])
        self.assertTrue(serve.pid_alive(record['processes'][0]['relayPid']))
        self.assertTrue(wait_until(lambda: self.log().is_file() and MARKER in self.log().read_text(encoding='utf-8')),
                        'o log da prévia não recebeu a linha do marcador')
        text = self.log().read_text(encoding='utf-8')
        self.assertIn(f'{MARKER} ouvindo na porta {process["port"]} senha={MASK}', text)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn(PASSWORD, done_text(self.last))
        self.assertNotIn(LOGIN, done_text(self.last))


class PreviewStatusTest(PreviewTestCase):
    def test_status_from_a_new_session_finds_the_processes_by_the_registry_and_returns_the_masked_tail(self):
        self.write_config()
        started = self.start_preview()
        self.assertTrue(wait_until(lambda: self.log().is_file() and MARKER in self.log().read_text(encoding='utf-8')))
        done = self.serve('preview', 'status')  # a new serve process: nothing but the registry links it to the start
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertTrue(result['ok'])
        self.assertTrue(result['running'])
        self.assertEqual((result['worktree'], result['branch'], result['baseUrl']),
                         ('.claude/worktrees/previa', 'previa', 'http://127.0.0.1:1/'))
        process = result['processes'][0]
        self.assertEqual(process['pid'], started['processes'][0]['pid'])
        self.assertTrue(process['alive'])
        self.assertEqual(process['log'], '.frontlights/preview/log/web.log')
        self.assertTrue(any(line.startswith(MARKER) for line in process['tail']), process['tail'])
        self.assertIn(f'senha={MASK}', process['tail'][-1])
        self.assertNotIn(PASSWORD, done_text(done))


class PreviewStopTest(PreviewTestCase):
    def test_stop_kills_the_processes_and_their_relays_removes_the_registry_and_releases_the_ports(self):
        self.write_config()
        started = self.start_preview()
        record = json.loads(self.registry().read_text(encoding='utf-8'))
        pid, relay_pid, port = record['processes'][0]['pid'], record['processes'][0]['relayPid'], started['processes'][0]['port']
        reservation = serve.ports_dir(self.root) / f'{port}.json'
        self.assertTrue(reservation.is_file())
        done = self.serve('preview', 'stop')
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertTrue(result['ok'])
        self.assertTrue(all(item['stopped'] for item in result['processes']), result)
        self.assertEqual(result['reservas_liberadas'], [port])
        self.assertFalse(self.registry().exists())
        self.assertFalse(reservation.exists())
        self.assertTrue(wait_until(lambda: not serve.pid_alive(pid)), 'o processo da prévia continuou vivo')
        self.assertTrue(wait_until(lambda: not serve.pid_alive(relay_pid)), 'o relé do log continuou vivo')
        self.assertTrue(wait_until(lambda: not reachable(started['processes'][0]['url'])))

    def test_stop_without_a_registry_is_refused(self):
        self.write_config()
        done = self.serve('preview', 'stop')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertFalse(result['ok'])
        self.assertIn('registro da prévia', result['error'])


class DuplicatePreviewStartTest(PreviewTestCase):
    def test_a_second_start_with_the_preview_alive_is_refused_as_usage_and_asks_for_refresh(self):
        self.write_config()
        first = self.start_preview()
        before = self.registry().read_text(encoding='utf-8')
        done = self.serve('preview', 'start')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertFalse(result['ok'])
        self.assertEqual(result['category'], 'uso')
        self.assertIn('refresh', result['error'])
        self.assertEqual(self.registry().read_text(encoding='utf-8'), before)
        self.assertTrue(reachable(first['processes'][0]['url']))
        self.assertEqual(self.payload(self.serve('preview', 'status'))['processes'][0]['pid'],
                         first['processes'][0]['pid'])


class IssueStopKeepsThePreviewTest(PreviewTestCase):
    def test_stop_of_an_issue_does_not_kill_the_preview_nor_its_registry_nor_its_reservation(self):
        self.write_config()
        preview = self.start_preview()
        port = preview['processes'][0]['port']
        reservation = serve.ports_dir(self.root) / f'{port}.json'
        self.assertEqual(json.loads(reservation.read_text(encoding='utf-8'))['issue'], 'preview')
        issue = self.serve('start', issue=9)
        self.assertEqual(issue.returncode, 0, done_text(issue))
        issue_url = self.payload(issue)['processes'][0]['url']
        done = self.serve('stop', issue=9)
        self.assertEqual(done.returncode, 0, done_text(done))
        self.assertTrue(wait_until(lambda: not reachable(issue_url)), 'o stop da issue não derrubou a issue')
        self.assertFalse(self.issue_registry().exists())
        self.assertTrue(self.registry().is_file(), 'o stop da issue apagou o registro da prévia')
        self.assertTrue(reservation.is_file(), 'o stop da issue liberou a porta da prévia')
        self.assertTrue(reachable(preview['processes'][0]['url']), 'o stop da issue derrubou a prévia')
        status = self.payload(self.serve('preview', 'status'))
        self.assertTrue(status['running'])
        self.assertEqual(status['processes'][0]['pid'], preview['processes'][0]['pid'])

    def test_stop_of_an_issue_without_its_registry_leaves_the_preview_reservation_alone(self):
        self.write_config()
        preview = self.start_preview()
        reservation = serve.ports_dir(self.root) / f'{preview["processes"][0]["port"]}.json'
        done = self.serve('stop', issue=9)
        self.assertEqual(done.returncode, 1, done_text(done))
        self.assertEqual(self.payload(done)['reservas_liberadas'], [])
        self.assertTrue(reservation.is_file())
        self.assertTrue(self.registry().is_file())


class PreviewUsageTest(PreviewTestCase):
    def test_without_the_preview_block_every_preview_action_is_refused_as_usage(self):
        self.write_config(preview=None)
        for action in ('start', 'status', 'stop'):
            with self.subTest(action=action):
                done = self.serve('preview', action)
                self.assertEqual(done.returncode, 1, done_text(done))
                result = self.payload(done)
                self.assertEqual(result['category'], 'uso')
                self.assertIn('bloco preview', result['error'])
        self.assertFalse(self.registry().exists())

    def test_start_without_the_preview_worktree_is_refused_as_usage_and_points_to_refresh(self):
        self.write_config(worktree='.claude/worktrees/inexistente')
        done = self.serve('preview', 'start')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso')
        self.assertIn('não existe', result['error'])
        self.assertIn('refresh', result['error'])
        self.assertFalse(self.registry().exists())

    def test_an_issue_operation_without_issue_is_refused_as_usage(self):
        self.write_config()
        for operation in ('start', 'status', 'stop'):
            with self.subTest(operation=operation):
                done = self.serve(operation)
                self.assertEqual(done.returncode, 1, done_text(done))
                result = self.payload(done)
                self.assertEqual(result['category'], 'uso')
                self.assertIn('--issue', result['error'])
        self.assertFalse((self.root / '.frontlights' / 'serve').exists(), 'um start sem issue subiu algo')

    def test_the_help_lists_preview_and_relay_and_their_flags(self):
        done = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
        self.assertEqual(done.returncode, 0)
        self.assertIn('{start,stop,status,preview,relay}', done.stdout)
        self.assertIn('[{start,status,stop}]', done.stdout)
        for flag in ('--config', '--root', '--issue', '--log'):
            self.assertIn(flag, done.stdout)


def done_text(done):
    return done.stdout + done.stderr


if __name__ == '__main__':
    unittest.main()
