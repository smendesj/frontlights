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
from unittest import mock

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
        # the preview runs on fixed ports (its tab is only reloaded): one free port reserved per test, also used by
        # preview.baseUrl
        self.preview_port = free_port()
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

    def preview_process(self, name='web', secret=PASSWORD, port=None, **extra):
        port = port or self.preview_port
        entry = {'name': name, 'argv': [sys.executable, str(self.script), str(port), MARKER] + ([secret] if secret else []),
                 'port': port, 'health': f'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}
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
            preview = {'worktree': worktree, 'branch': 'previa', 'baseUrl': f'http://127.0.0.1:{self.preview_port}/',
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
        self.assertEqual(result['baseUrl'], f'http://127.0.0.1:{self.preview_port}/')
        self.assertEqual(result['processes'][0]['port'], self.preview_port)
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
                         ('.claude/worktrees/previa', 'previa', f'http://127.0.0.1:{self.preview_port}/'))
        process = result['processes'][0]
        self.assertEqual(process['pid'], started['processes'][0]['pid'])
        self.assertTrue(process['alive'])
        self.assertEqual(process['log'], '.frontlights/preview/log/web.log')
        self.assertTrue(any(line.startswith(MARKER) for line in process['tail']), process['tail'])
        self.assertIn(f'senha={MASK}', process['tail'][-1])
        self.assertNotIn(PASSWORD, done_text(done))


class PreviewStopTest(PreviewTestCase):
    def test_stop_kills_the_processes_and_their_relays_and_removes_the_registry(self):
        self.write_config()
        started = self.start_preview()
        record = json.loads(self.registry().read_text(encoding='utf-8'))
        pid, relay_pid = record['processes'][0]['pid'], record['processes'][0]['relayPid']
        # fixed ports (3rd review of issue 34): the preview reserves no port, so its stop releases none
        self.assertEqual(started['processes'][0]['port'], self.preview_port)
        self.assertFalse((serve.ports_dir(self.root) / f'{self.preview_port}.json').exists())
        done = self.serve('preview', 'stop')
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertTrue(result['ok'])
        self.assertTrue(all(item['stopped'] for item in result['processes']), result)
        self.assertNotIn('reservas_liberadas', result)
        self.assertFalse(self.registry().exists())
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
    def test_stop_of_an_issue_does_not_kill_the_preview_nor_its_registry(self):
        self.write_config()
        preview = self.start_preview()
        issue = self.serve('start', issue=9)
        self.assertEqual(issue.returncode, 0, done_text(issue))
        issue_url = self.payload(issue)['processes'][0]['url']
        done = self.serve('stop', issue=9)
        self.assertEqual(done.returncode, 0, done_text(done))
        self.assertTrue(wait_until(lambda: not reachable(issue_url)), 'o stop da issue não derrubou a issue')
        self.assertFalse(self.issue_registry().exists())
        self.assertTrue(self.registry().is_file(), 'o stop da issue apagou o registro da prévia')
        self.assertTrue(reachable(preview['processes'][0]['url']), 'o stop da issue derrubou a prévia')
        status = self.payload(self.serve('preview', 'status'))
        self.assertTrue(status['running'])
        self.assertEqual(status['processes'][0]['pid'], preview['processes'][0]['pid'])

    def test_stop_of_an_issue_without_its_registry_leaves_the_preview_alone(self):
        self.write_config()
        preview = self.start_preview()
        done = self.serve('stop', issue=9)
        self.assertEqual(done.returncode, 1, done_text(done))
        self.assertEqual(self.payload(done)['reservas_liberadas'], [])
        self.assertTrue(self.registry().is_file())
        self.assertTrue(reachable(preview['processes'][0]['url']), 'o stop da issue derrubou a prévia')


class PreviewUsageTest(PreviewTestCase):
    def test_without_the_preview_block_start_and_refresh_are_refused_as_usage(self):
        self.write_config(preview=None)
        for action in ('start', 'refresh'):
            with self.subTest(action=action):
                done = self.serve('preview', action)
                self.assertEqual(done.returncode, 1, done_text(done))
                result = self.payload(done)
                self.assertEqual(result['category'], 'uso')
                self.assertIn('bloco preview', result['error'])
        self.assertFalse(self.registry().exists())

    def test_without_the_preview_block_nor_a_registry_status_and_stop_say_there_is_no_registry(self):
        self.write_config(preview=None)
        for action in ('status', 'stop'):
            with self.subTest(action=action):
                done = self.serve('preview', action)
                self.assertEqual(done.returncode, 1, done_text(done))
                self.assertIn('Não há registro da prévia', self.payload(done)['error'])
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
        self.assertIn('[{start,refresh,status,stop}]', done.stdout)
        for flag in ('--config', '--root', '--issue', '--log', '--branch', '--base'):
            self.assertIn(flag, done.stdout)


# Broken builds of the fake server: one exits at once, the other never listens (its health never answers).
EXITING_SERVER = r"""import sys
print('ERRO-DE-BUILD: app.py linha 3: SyntaxError', flush=True)
sys.exit(1)
"""
SILENT_SERVER = r"""import sys
import time
print('ERRO-DE-BUILD: o servidor nao abriu a porta', flush=True)
time.sleep(600)
"""


class RefreshTestCase(PreviewTestCase):
    """A real Git repository in the temporary folder: `main` with the fake server, issue branches beside it, and
    `preview.worktree` inside the repository (as the worktrees of `.claude/worktrees`). The preview worktree does
    not exist at first: `preview refresh` creates it."""

    def setUp(self):
        super().setUp()
        self.worktree.rmdir()
        self.git('init', '-q', '-b', 'main')
        for key, value in (('user.name', 'Teste'), ('user.email', 'teste@exemplo.test'),
                           ('commit.gpgsign', 'false'), ('core.autocrlf', 'false')):
            self.git('config', key, value)
        (self.root / '.gitignore').write_text('.claude/\n.frontlights/\n', encoding='utf-8')
        (self.root / 'preview_server.py').write_text(PREVIEW_SERVER, encoding='utf-8')
        (self.root / 'feature.txt').write_text('base\n', encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'inicio')
        self.branch('issue-1', {'issue1.txt': 'da issue 1\n'})
        self.write_config(preview=self.refresh_block())

    def git(self, *args, cwd=None):
        done = subprocess.run(['git', *args], cwd=cwd or self.root, capture_output=True, text=True,
                              encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def branch(self, name, files):
        """A branch cut from main with one commit that writes `files`; the main worktree goes back to main."""
        self.git('checkout', '-q', '-b', name, 'main')
        for path, text in files.items():
            (self.root / path).write_text(text, encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', f'commit de {name}')
        self.git('checkout', '-q', 'main')

    def refresh_block(self, **extra):
        port = self.preview_port
        process = {'name': 'web', 'argv': [sys.executable, 'preview_server.py', str(port), MARKER, PASSWORD],
                   'port': port, 'health': f'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}
        process.update(extra)
        return {'worktree': '.claude/worktrees/previa', 'branch': 'previa', 'baseUrl': f'http://127.0.0.1:{port}/',
                'processes': [process]}

    def refresh(self, *branches):
        argv = ['preview', 'refresh']
        for name in branches:
            argv += ['--branch', name]
        return self.serve(*argv)

    def rev(self, ref):
        return self.git('rev-parse', ref)


class PreviewRefreshTest(RefreshTestCase):
    def test_refresh_without_the_worktree_creates_it_merges_the_branch_and_brings_the_preview_up(self):
        done = self.refresh('issue-1')
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertTrue(result['ok'])
        self.assertEqual((result['worktree'], result['branch'], result['base']),
                         ('.claude/worktrees/previa', 'previa', 'main'))
        self.assertEqual(result['baseCommit'], self.rev('main'))
        self.assertEqual(result['merged'], [{'branch': 'issue-1', 'commit': self.rev('issue-1')}])
        self.assertEqual((self.worktree / 'issue1.txt').read_text(encoding='utf-8'), 'da issue 1\n')
        self.assertEqual(self.git('symbolic-ref', '--short', 'HEAD', cwd=self.worktree), 'previa')
        self.assertTrue(reachable(result['processes'][0]['url']))
        record = json.loads(self.registry().read_text(encoding='utf-8'))
        self.assertEqual(record['merged'], [{'branch': 'issue-1', 'commit': self.rev('issue-1')}])
        self.assertEqual((record['base'], record['baseCommit']), ('main', self.rev('main')))
        status = self.payload(self.serve('preview', 'status'))
        self.assertTrue(status['running'])
        self.assertEqual(status['merged'], record['merged'])

    def test_refresh_of_a_live_preview_brings_it_down_and_up_again_with_new_processes(self):
        first = self.payload(self.refresh('issue-1'))
        old = json.loads(self.registry().read_text(encoding='utf-8'))['processes'][0]
        self.branch('issue-2', {'issue2.txt': 'da issue 2\n'})
        done = self.refresh('issue-1', 'issue-2')
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertNotEqual(result['processes'][0]['pid'], old['pid'])
        self.assertTrue(all(item['stopped'] for item in result['stopped']), result['stopped'])
        self.assertEqual(sorted(item['pid'] for item in result['stopped']), sorted([old['pid'], old['relayPid']]))
        self.assertTrue(wait_until(lambda: not serve.pid_alive(old['pid'])), 'o processo antigo continuou vivo')
        self.assertTrue(wait_until(lambda: not serve.pid_alive(old['relayPid'])), 'o relé antigo continuou vivo')
        self.assertTrue(reachable(result['processes'][0]['url']))
        self.assertEqual([item['branch'] for item in result['merged']], ['issue-1', 'issue-2'])
        self.assertTrue((self.worktree / 'issue2.txt').is_file())
        status = self.payload(self.serve('preview', 'status'))
        self.assertTrue(status['running'])
        self.assertEqual(status['processes'][0]['pid'], result['processes'][0]['pid'])
        self.assertNotEqual(first['processes'][0]['pid'], status['processes'][0]['pid'])

    def test_refresh_merges_the_branch_even_when_a_tag_has_the_same_name(self):
        self.git('tag', 'issue-1', 'main')  # `git merge issue-1` would take the tag (main) before the branch
        done = self.refresh('issue-1')
        self.assertEqual(done.returncode, 0, done_text(done))
        self.assertTrue((self.worktree / 'issue1.txt').is_file(), 'o refresh mesclou a tag, não a branch')
        self.assertEqual(self.rev('previa^2'), self.rev('refs/heads/issue-1'))
        self.assertEqual(self.git('log', '-1', '--format=%s', 'previa'), "Merge branch 'issue-1' into previa")

    def test_refresh_leaves_the_local_main_and_the_issue_branch_where_they_were(self):
        main, issue = self.rev('main'), self.rev('issue-1')
        self.assertEqual(self.refresh('issue-1').returncode, 0, done_text(self.last))
        self.assertEqual(self.refresh('issue-1').returncode, 0, done_text(self.last))
        self.assertEqual((self.rev('main'), self.rev('issue-1')), (main, issue))
        self.assertEqual(self.git('symbolic-ref', '--short', 'HEAD'), 'main')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=no'), '')
        self.assertNotEqual(self.rev('previa'), main)  # the merge commit lives only on the preview branch
        self.assertEqual(self.git('rev-parse', 'previa^1'), main)
        self.assertEqual(self.git('rev-parse', 'previa^2'), issue)


    def test_after_a_stop_and_the_worktree_removed_the_refresh_redoes_the_branch_its_marker_names(self):
        """2nd review of issue 34 (B2): the stop deletes the record, not the marker of the preview branch."""
        marker = self.root / '.frontlights' / 'preview' / 'branch.json'
        self.assertEqual(self.refresh('issue-1').returncode, 0, done_text(self.last))
        self.assertEqual(json.loads(marker.read_text(encoding='utf-8')), {'branch': 'previa'})
        self.assertTrue(self.payload(self.serve('preview', 'stop'))['ok'], done_text(self.last))
        self.assertFalse(self.registry().exists())
        self.assertTrue(marker.is_file(), 'o stop apagou o marcador da branch da prévia')
        self.git('worktree', 'remove', '--force', str(self.worktree))
        done = self.refresh('issue-1')
        self.assertEqual(done.returncode, 0, done_text(done))
        self.assertEqual((self.rev('previa^1'), self.rev('previa^2')), (self.rev('main'), self.rev('issue-1')))
        self.assertEqual(json.loads(marker.read_text(encoding='utf-8')), {'branch': 'previa'})


    def test_a_start_over_a_record_with_everything_dead_keeps_the_merges_the_worktree_holds(self):
        """2nd review of issue 34 (B5): the processes die without `preview stop`; `preview start` brings the same
        worktree up again, so the record keeps base, baseCommit and merged."""
        first = self.payload(self.refresh('issue-1'))
        self.assertTrue(first['ok'], first)
        for entry in json.loads(self.registry().read_text(encoding='utf-8'))['processes']:
            for pid in (entry['pid'], entry['relayPid']):
                serve.kill_tree(pid)
                self.assertTrue(wait_until(lambda: not serve.pid_alive(pid)), f'o pid {pid} continuou vivo')
        self.assertEqual(self.serve('preview', 'start').returncode, 0, done_text(self.last))
        status = self.payload(self.serve('preview', 'status'))
        self.assertTrue(status['running'], status)
        self.assertEqual((status.get('base'), status.get('baseCommit'), status.get('merged')),
                         (first['base'], first['baseCommit'], first['merged']))


class PreviewRefreshBrokenBuildTest(RefreshTestCase):
    def assert_broken_build(self, done):
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertFalse(result['ok'])
        self.assertEqual(result['category'], 'infraestrutura')
        self.assertEqual(result['build'], 'quebrado')
        self.assertEqual(result['failedProcess'], 'web')
        self.assertEqual(result['log'], '.frontlights/preview/log/web.log')
        self.assertTrue(result['tail'], result)
        self.assertTrue(result['tail'][-1].startswith('ERRO-DE-BUILD:'), result['tail'])
        self.assertNotIn('left', result)
        self.assertFalse(self.registry().exists(), 'o registro ficou com processos de um build quebrado')
        reservations = [json.loads(path.read_text(encoding='utf-8'))
                        for path in serve.ports_dir(self.root).glob('*.json')]
        self.assertEqual([item for item in reservations if item.get('issue') == 'preview'], [])
        return result

    def test_a_process_that_exits_before_its_health_fails_the_refresh_with_the_log_and_its_last_lines(self):
        live = self.payload(self.refresh('issue-1'))['processes'][0]  # an earlier, healthy run fills the log first
        self.branch('quebrada', {'preview_server.py': EXITING_SERVER})
        result = self.assert_broken_build(self.refresh('issue-1', 'quebrada'))
        self.assertIn('terminou antes de ficar saudável', result['error'])
        self.assertFalse(any(MARKER in line for line in result['tail']), 'o tail trouxe linhas da execução anterior')
        self.assertTrue(wait_until(lambda: not reachable(live['url'])))

    def test_a_health_that_never_answers_fails_the_refresh_and_kills_the_process(self):
        self.write_config(preview=self.refresh_block(timeoutSeconds=3))
        self.branch('sem-health', {'preview_server.py': SILENT_SERVER})
        result = self.assert_broken_build(self.refresh('sem-health'))
        self.assertIn('não ficou saudável', result['error'])


class PreviewRefreshRefusalTest(RefreshTestCase):
    def test_two_branches_that_conflict_are_aborted_with_the_files_and_leave_the_worktree_clean(self):
        self.branch('conflito-a', {'feature.txt': 'versao A\n'})
        self.branch('conflito-b', {'feature.txt': 'versao B\n'})
        main, a, b = self.rev('main'), self.rev('conflito-a'), self.rev('conflito-b')
        done = self.refresh('conflito-a', 'conflito-b')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'infraestrutura')
        self.assertIs(result['conflict'], True)
        self.assertEqual(result['branch'], 'conflito-b')
        self.assertEqual(result['files'], ['feature.txt'])
        self.assertEqual(result['merged'], [{'branch': 'conflito-a', 'commit': a}])
        self.assertEqual(self.git('status', '--porcelain', cwd=self.worktree), '')
        merging = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', 'MERGE_HEAD'], cwd=self.worktree,
                                 capture_output=True, text=True, timeout=60)
        self.assertNotEqual(merging.returncode, 0, 'ficou um merge em andamento na worktree da prévia')
        self.assertEqual((self.rev('previa^1'), self.rev('previa^2')), (main, a))  # the merge before the conflict

        self.assertFalse(self.registry().exists(), 'um conflito subiu a prévia')
        self.assertEqual((self.rev('main'), self.rev('conflito-a'), self.rev('conflito-b')), (main, a, b))

    def test_a_branch_that_does_not_exist_is_refused_as_usage_and_touches_nothing(self):
        done = self.refresh('issue-1', 'nao-existe')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso')
        self.assertIn('nao-existe', result['error'])
        self.assertFalse(self.worktree.exists(), 'uma recusa de uso criou a worktree da prévia')
        self.assertFalse(self.registry().exists())

    def test_a_preview_worktree_with_tracked_changes_is_refused_as_usage_and_the_preview_stays_up(self):
        live = self.payload(self.refresh('issue-1'))['processes'][0]
        (self.worktree / 'feature.txt').write_text('editado na previa\n', encoding='utf-8')
        done = self.refresh('issue-1')
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso')
        self.assertIn('nada se edita nela', result['error'])
        self.assertEqual((self.worktree / 'feature.txt').read_text(encoding='utf-8'), 'editado na previa\n')
        self.assertTrue(reachable(live['url']), 'uma recusa de uso derrubou a prévia')

    def test_branch_and_base_are_refused_outside_preview_refresh(self):
        for argv in (('preview', 'start', '--branch', 'issue-1'), ('preview', 'status', '--base', 'main'),
                     ('start', '--branch', 'issue-1')):
            with self.subTest(argv=argv):
                done = self.serve(*argv)
                self.assertEqual(done.returncode, 1, done_text(done))
                self.assertEqual(self.payload(done)['category'], 'uso')
                self.assertIn('preview refresh', self.payload(done)['error'])
        self.assertFalse(self.worktree.exists())


class FakeRecordMixin:
    """Fake records of the preview pointing at Python processes that only sleep (no server comes up), and a spy of
    the records `launch_preview` writes, to learn every pid a launch started."""

    def sleeper(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        identity = serve.process_identity(child.pid)
        self.assertIsNotNone(identity)
        return {'pid': child.pid, 'identity': identity, 'child': child}

    def dead(self):
        """A pid that is no longer alive, with the identity it had (a reused pid then is not the same process)."""
        item = self.sleeper()
        item['child'].kill()
        item['child'].wait()
        return item

    def fake_registry(self, process, relay, branch='previa'):
        entry = {'name': 'web', 'pid': process['pid'], 'identity': process['identity'], 'port': 1,
                 'url': 'http://127.0.0.1:1/', 'startedAt': serve.now_iso(), 'log': '.frontlights/preview/log/web.log',
                 'relayPid': relay['pid'], 'relayIdentity': relay['identity']}
        path = self.registry()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'root': str(self.root.resolve()), 'worktree': '.claude/worktrees/previa',
                                    'branch': branch, 'baseUrl': 'http://127.0.0.1:1/', 'startedAt': serve.now_iso(),
                                    'processes': [entry]}), encoding='utf-8')
        # runs before kill_leftovers: a fake record must never make the safety net kill a reused pid
        self.addCleanup(path.unlink, missing_ok=True)
        return path.read_text(encoding='utf-8')

    def recording(self):
        """(list of the entries of every record written, patch that records them)."""
        seen, real = [], serve.write_preview_registry

        def record(root, block, entries, started_at, contents=None):
            seen.append(json.loads(json.dumps(entries)))
            return real(root, block, entries, started_at, contents)
        return seen, mock.patch.object(serve, 'write_preview_registry', record)

    def preview_reservations(self):
        folder = serve.ports_dir(self.root)
        return [path for path in folder.glob('*.json')
                if json.loads(path.read_text(encoding='utf-8')).get('issue') == 'preview'] if folder.is_dir() else []


class PreviewConfigRefusalTest(PreviewTestCase):
    """Refusals of the `preview` block (category `uso`), read in process: nothing is created and nothing comes up."""

    def block(self, **changes):
        block = {'worktree': '.claude/worktrees/previa', 'branch': 'previa',
                 'baseUrl': f'http://127.0.0.1:{self.preview_port}/', 'processes': [self.preview_process()]}
        block.update(changes)
        return block

    def refused(self, block, needle):
        self.write_config(preview=block)
        with self.assertRaises(serve.Refusal) as caught:
            serve.load_preview_block(self.config, self.root)
        self.assertEqual(caught.exception.category, 'uso', str(caught.exception))
        self.assertIn(needle, str(caught.exception))
        self.assertFalse((self.root / '.frontlights' / 'preview').exists(), 'uma recusa de config criou algo')
        return caught.exception

    def accepted(self, block):
        self.write_config(preview=block)
        return serve.load_preview_block(self.config, self.root)

    def test_a_preview_worktree_with_dots_absolute_with_a_drive_outside_or_equal_to_the_root_is_refused(self):
        outside = Path(self.tmp.name) / 'fora'
        (outside / 'previa').mkdir(parents=True)
        link = self.root / 'atalho'  # a junction (or symlink) inside the root that leads out of it
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(link))
        else:
            link.symlink_to(outside, target_is_directory=True)
        relative_only, inside = 'sem ".." e sem unidade ou raiz', 'dentro do --root'
        values = [('', 'texto não vazio'), ('../fora', relative_only), ('.claude/../../fora', relative_only),
                  (str(outside), relative_only), ('/fora', relative_only), ('\\fora', relative_only),
                  ('atalho/previa', inside), ('.', inside), ('./', inside)]
        if os.name == 'nt':
            values += [('C:fora', relative_only), ('C:\\fora', relative_only)]
        for value, needle in values:
            with self.subTest(worktree=value):
                self.assertIn('preview.worktree', str(self.refused(self.block(worktree=value), needle)))
        self.assertEqual([path.name for path in outside.iterdir()], ['previa'])

    def test_a_preview_branch_named_main_or_master_in_any_case_is_refused(self):
        for value in ('main', 'master', 'Main', 'MASTER'):
            with self.subTest(branch=value):
                self.refused(self.block(branch=value), 'protegida')

    def test_a_preview_branch_with_an_invalid_name_is_refused(self):
        for value in ('', '-x', 'a b', 'a..b', 'nome.lock', 'a/b.lock', 'a/', 'a//b', 'a/.b', 'a.', 7):
            with self.subTest(branch=value):
                self.refused(self.block(branch=value), 'preview.branch')

    def test_a_preview_branch_that_matches_protected_branches_of_an_authorization_is_refused(self):
        folder = self.root / '.frontlights'
        folder.mkdir()
        (folder / 'authorization.json').write_text(json.dumps({'protected_branches': ['release', 'hotfix/*', 'Prod*']}),
                                                   encoding='utf-8')
        (folder / 'authorization-ilegivel.json').write_text('{ ilegivel', encoding='utf-8')
        (folder / 'authorization-lista.json').write_text(json.dumps({'protected_branches': 'release-x'}),
                                                         encoding='utf-8')
        (folder / 'authorization-pasta.json').mkdir()
        for value in ('release', 'RELEASE', 'release/x', 'hotfix/a', 'hotfix/a/b', 'producao'):
            with self.subTest(branch=value):
                self.refused(self.block(branch=value), 'protegida')
        for value in ('previa', 'releases', 'hotfix', 'release-x'):  # unreadable files are skipped, never fatal
            with self.subTest(branch=value):
                self.assertEqual(self.accepted(self.block(branch=value))['branch'], value)

    def write_hostile_authorizations(self):
        """2nd review of issue 34 (B3): one record nested too deep for json, one past the size limit; both name
        protected branches that would refuse the block if they were read."""
        folder = self.root / '.frontlights'
        folder.mkdir(exist_ok=True)
        (folder / 'authorization-fundo.json').write_text('[' * 100000, encoding='utf-8')
        padding = 'x' * (2 * 1024 * 1024 + 1)  # the limit: 2 MiB per record
        (folder / 'authorization-grande.json').write_text(
            json.dumps({'protected_branches': ['grande*'], 'padding': padding}), encoding='utf-8')

    def test_an_authorization_nested_too_deep_or_too_large_is_skipped(self):
        self.write_hostile_authorizations()
        self.assertEqual(self.accepted(self.block(branch='grande-previa'))['branch'], 'grande-previa')
        self.assertEqual(serve.protected_patterns(self.root), list(serve.PROTECTED_BRANCHES))

    def test_the_cli_answers_json_with_hostile_authorizations(self):
        self.write_hostile_authorizations()
        self.write_config(preview=self.block(branch='grande-previa'))
        for args in (('preview', 'start'), ('preview', 'refresh')):
            with self.subTest(args=args):
                done = self.serve(*args)
                self.assertNotIn('Traceback', done.stderr)
                result = self.payload(done)  # JSON, never a traceback
                self.assertIn('ok', result)
        self.assertTrue(self.payload(self.serve('preview', 'stop'))['ok'])

    def test_a_process_health_outside_the_local_host_is_refused_naming_the_process(self):
        port, other = self.preview_port, free_port()
        for host in ('example.test', '10.0.0.5', '0.0.0.0'):
            with self.subTest(host=host):
                error = self.refused(self.block(processes=[self.preview_process(), self.preview_process(
                    'api', port=other, health=f'http://{host}:{other}/')]), 'api')
                self.assertEqual(error.process, 'api')
        for health in (f'http://localhost:{port}/', f'http://[::1]:{port}/'):
            with self.subTest(health=health):
                self.accepted(self.block(processes=[self.preview_process(health=health)]))

    def fixed(self, name, port, with_port=True):
        """A preview process on a fixed port: the integer `port`, or (with_port=False) only the port of the health."""
        item = {'name': name, 'argv': [sys.executable, str(self.script), str(port), MARKER],
                'health': f'http://127.0.0.1:{port}/'}
        if with_port:
            item['port'] = port
        return item

    def test_a_port_placeholder_in_the_base_url_is_refused(self):
        """3rd review of issue 34 (M): the preview opens once in a tab and is only reloaded, so its port is fixed."""
        port = free_port()
        for value in ('http://127.0.0.1:{port}/', 'http://localhost:{port}/app'):
            with self.subTest(baseUrl=value):
                error = self.refused(self.block(baseUrl=value, processes=[self.fixed('web', port)]), 'preview.baseUrl')
                self.assertIn('{port}', str(error))

    def test_a_process_with_an_automatic_port_is_refused_naming_it(self):
        port = free_port()
        auto = {'name': 'api', 'argv': [sys.executable, str(self.script), '{port}', MARKER], 'port': 'auto',
                'health': 'http://127.0.0.1:{port}/'}
        error = self.refused(self.block(baseUrl=f'http://127.0.0.1:{port}/', processes=[self.fixed('web', port), auto]),
                             'preview.processes')
        self.assertEqual(error.process, 'api')
        self.assertIn('"auto"', str(error))

    def test_a_base_url_on_a_port_that_no_process_uses_is_refused(self):
        port = free_port()
        other = port + 1 if port < 65535 else port - 1
        cases = {f'http://127.0.0.1:{other}/': other, 'http://127.0.0.1/': 80, 'https://localhost/app': 443}
        for value, expected in cases.items():
            with self.subTest(baseUrl=value):
                error = self.refused(self.block(baseUrl=value, processes=[self.fixed('web', port)]), 'preview.baseUrl')
                self.assertIn(str(expected), str(error))
                self.assertIn('preview.processes', str(error))

    def test_a_base_url_on_the_fixed_port_of_a_process_is_accepted(self):
        port, other = free_port(), free_port()
        cases = {'port inteiro': ([self.fixed('web', port)], f'http://127.0.0.1:{port}/'),
                 'porta do health': ([self.fixed('api', other), self.fixed('web', port, with_port=False)],
                                     f'http://localhost:{port}/app'),
                 'porta do esquema': ([self.fixed('web', 80)], 'http://127.0.0.1/')}
        for case, (processes, base_url) in cases.items():
            with self.subTest(case=case):
                self.assertEqual(self.accepted(self.block(baseUrl=base_url, processes=processes))['baseUrl'], base_url)

    def test_two_processes_whose_names_give_the_same_log_file_are_refused(self):
        for first, second in (('web api', 'web_api'), ('Web', 'web')):
            with self.subTest(names=(first, second)):
                port = free_port()
                processes = [self.preview_process(name, port=port + index) for index, name in enumerate((first, second))]
                error = self.refused(self.block(processes=processes), 'mesmo arquivo de log')
                self.assertEqual(error.process, second)


class PreviewStartRecordTest(FakeRecordMixin, PreviewTestCase):
    """`preview start` with an old record: any live pid of it (process or relay) refuses; nothing alive goes on."""

    def start(self):
        with mock.patch.object(serve, 'launch_preview', return_value={'ok': True}) as launch:
            try:
                return launch, serve.preview_start(self.config, self.root), None
            except serve.Refusal as refusal:
                return launch, None, refusal

    def test_a_live_relay_of_the_old_record_refuses_the_start(self):
        self.write_config()
        before = self.fake_registry(self.dead(), self.sleeper())
        launch, _, refusal = self.start()
        self.assertIsNotNone(refusal, 'o start seguiu com o relé antigo vivo')
        self.assertEqual(refusal.category, 'uso')
        self.assertIn('refresh', str(refusal))
        launch.assert_not_called()
        self.assertEqual(self.registry().read_text(encoding='utf-8'), before)

    def test_a_live_process_of_the_old_record_refuses_the_start(self):
        self.write_config()
        before = self.fake_registry(self.sleeper(), self.dead())
        launch, _, refusal = self.start()
        self.assertIsNotNone(refusal)
        self.assertEqual(refusal.category, 'uso')
        launch.assert_not_called()
        self.assertEqual(self.registry().read_text(encoding='utf-8'), before)

    def test_an_old_record_with_nothing_alive_lets_the_start_go_on(self):
        self.write_config()
        self.fake_registry(self.dead(), self.dead())
        launch, result, refusal = self.start()
        self.assertIsNone(refusal)
        self.assertEqual(result, {'ok': True})
        launch.assert_called_once()


class PreviewStatusRecordTest(FakeRecordMixin, PreviewTestCase):
    def test_status_reports_the_relay_and_running_needs_the_process_and_its_relay(self):
        self.write_config()
        process, relay = self.sleeper(), self.sleeper()
        self.fake_registry(process, relay)
        result = serve.preview_status(self.config, self.root)
        self.assertTrue(result['running'])
        self.assertEqual((result['processes'][0]['alive'], result['processes'][0]['relayAlive']), (True, True))
        relay['child'].kill()
        relay['child'].wait()
        result = serve.preview_status(self.config, self.root)
        self.assertEqual((result['processes'][0]['alive'], result['processes'][0]['relayAlive']), (True, False))
        self.assertFalse(result['running'], 'a prévia sem relé (sem log) foi dada como no ar')

    def test_status_and_stop_work_without_the_preview_block_when_there_is_a_registry(self):
        self.write_config(preview=None)
        process, relay = self.sleeper(), self.sleeper()
        self.fake_registry(process, relay)
        self.log().parent.mkdir(parents=True, exist_ok=True)
        self.log().write_text(f'linha com {PASSWORD} e {LOGIN}\n', encoding='utf-8')
        done = self.serve('preview', 'status')
        self.assertEqual(done.returncode, 0, done_text(done))
        result = self.payload(done)
        self.assertTrue(result['running'])
        self.assertEqual(result['processes'][0]['tail'], [f'linha com {MASK} e {MASK}'])
        self.assertNotIn(PASSWORD, done_text(done))
        done = self.serve('preview', 'stop')
        self.assertEqual(done.returncode, 0, done_text(done))
        self.assertTrue(all(item['stopped'] for item in self.payload(done)['processes']), done_text(done))
        self.assertFalse(self.registry().exists())
        self.assertTrue(wait_until(lambda: not serve.pid_alive(process['pid'])))
        self.assertTrue(wait_until(lambda: not serve.pid_alive(relay['pid'])))


# A process that never prints and never listens: alive until killed, its health never answers.
QUIET_SERVER = r"""import time
time.sleep(600)
"""


class PreviewLaunchFailureTest(FakeRecordMixin, PreviewTestCase):
    """A failed launch with two processes, and a relay that dies, both in process (the pids come from the spy)."""

    def config_with(self, second):
        self.write_config(preview={'worktree': '.claude/worktrees/previa', 'branch': 'previa',
                                   'baseUrl': f'http://127.0.0.1:{self.preview_port}/',
                                   'processes': [self.preview_process(), second]})

    def exiting(self):
        script = Path(self.tmp.name) / 'exiting_server.py'
        script.write_text(EXITING_SERVER, encoding='utf-8')
        port = free_port()
        return {'name': 'quebra', 'argv': [sys.executable, str(script)], 'port': port,
                'health': f'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}

    def pids(self, seen):
        return {pid for entries in seen for entry in entries for pid in (entry['pid'], entry.get('relayPid')) if pid}

    def test_when_the_second_process_fails_the_first_and_its_relay_are_torn_down(self):
        self.config_with(self.exiting())
        seen, spy = self.recording()
        with spy, self.assertRaises(serve.Refusal) as caught:
            serve.preview_start(self.config, self.root)
        failure = caught.exception
        self.assertEqual((failure.process, failure.category, failure.extra.get('build')),
                         ('quebra', 'infraestrutura', 'quebrado'))
        self.assertNotIn('left', failure.extra)
        pids = self.pids(seen)
        self.assertEqual(len(pids), 4, seen)
        for pid in pids:
            self.assertTrue(wait_until(lambda: not serve.pid_alive(pid), 5), f'o pid {pid} ficou vivo')
        self.assertFalse(self.registry().exists(), 'o registro ficou depois de derrubar tudo')
        self.assertEqual(self.preview_reservations(), [])

    def test_relays_that_do_not_stop_at_the_end_of_their_process_are_torn_down_too(self):
        self.config_with(self.exiting())
        seen, spy = self.recording()
        stubborn = mock.patch.object(serve, 'relay_argv',  # a relay that never reads stdin, so never sees EOF
                                     lambda config, log: [sys.executable, '-c', 'import time; time.sleep(60)'])
        with spy, stubborn, self.assertRaises(serve.Refusal) as caught:
            serve.preview_start(self.config, self.root)
        self.assertEqual(caught.exception.process, 'quebra')
        relays = {entry['relayPid'] for entries in seen for entry in entries if entry.get('relayPid')}
        self.assertEqual(len(relays), 2, seen)
        for pid in relays:
            self.assertTrue(wait_until(lambda: not serve.pid_alive(pid), 5), f'o relé {pid} ficou vivo')
        self.assertFalse(self.registry().exists())

    def test_what_cannot_be_torn_down_is_all_the_registry_keeps(self):
        self.config_with(self.exiting())
        seen, spy = self.recording()
        real_kill = serve.kill_tree

        def stubborn(pid):  # the first process "survives" the teardown
            return False if pid == seen[0][0]['pid'] else real_kill(pid)
        with spy, mock.patch.object(serve, 'kill_tree', stubborn), self.assertRaises(serve.Refusal) as caught:
            serve.preview_start(self.config, self.root)
        first = seen[0][0]['pid']
        self.assertEqual(caught.exception.extra['left'], [{'name': 'web', 'pid': first}])
        record = json.loads(self.registry().read_text(encoding='utf-8'))
        self.assertEqual([(entry['name'], entry['pid']) for entry in record['processes']], [('web', first)])
        self.assertTrue(serve.pid_alive(first))
        for pid in self.pids(seen) - {first}:
            self.assertTrue(wait_until(lambda: not serve.pid_alive(pid), 5), f'o pid {pid} ficou vivo')
        self.assertEqual(record['processes'][0]['port'], self.preview_port)
        self.assertEqual(self.preview_reservations(), [], 'a prévia, de portas fixas, reservou uma porta')

    def test_a_relay_that_dies_before_the_health_is_infrastructure_not_a_broken_build(self):
        script = Path(self.tmp.name) / 'quiet_server.py'
        script.write_text(QUIET_SERVER, encoding='utf-8')
        port = self.preview_port
        self.write_config(preview={'worktree': '.claude/worktrees/previa', 'branch': 'previa',
                                   'baseUrl': f'http://127.0.0.1:{port}/',
                                   'processes': [{'name': 'web', 'argv': [sys.executable, str(script)], 'port': port,
                                                  'health': f'http://127.0.0.1:{port}/', 'timeoutSeconds': 20}]})
        seen, spy = self.recording()
        dying = mock.patch.object(serve, 'relay_argv',
                                  lambda config, log: [sys.executable, '-c', 'raise SystemExit(3)'])
        with spy, dying, self.assertRaises(serve.Refusal) as caught:
            serve.preview_start(self.config, self.root)
        failure = caught.exception
        self.assertEqual((failure.process, failure.category), ('web', 'infraestrutura'))
        self.assertIn('relé', str(failure))
        self.assertNotIn('build', failure.extra, 'a morte do relé foi dada como build quebrado')
        for pid in self.pids(seen):
            self.assertTrue(wait_until(lambda: not serve.pid_alive(pid), 5), f'o pid {pid} ficou vivo')
        self.assertFalse(self.registry().exists())
        self.assertEqual(self.preview_reservations(), [])


class TailLinesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'web.log'

    def test_tail_reads_only_the_end_of_the_file_and_drops_the_line_cut_by_the_window(self):
        lines = [f'linha-{number:05d}-{"x" * 88}\n'.encode() for number in range(3000)]  # 101 bytes each
        self.path.write_bytes(b''.join(lines))
        handles, real_open = [], open

        class Spy:
            def __init__(self, handle):
                self.handle, self.read_bytes = handle, 0
                handles.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *error):
                self.handle.close()

            def read(self, *size):
                data = self.handle.read(*size)
                self.read_bytes += len(data)
                return data

            def __getattr__(self, name):
                return getattr(self.handle, name)

        with mock.patch.object(serve, 'open', create=True, side_effect=lambda *a, **k: Spy(real_open(*a, **k))):
            tail = serve.tail_lines(self.path, count=10000)
        self.assertEqual(len(handles), 1)
        self.assertLessEqual(handles[0].read_bytes, 64 * 1024 + 1, 'o tail leu o arquivo inteiro')
        self.assertLessEqual(len(tail), 64 * 1024 // 101)
        self.assertEqual(tail, [line.decode().rstrip('\n') for line in lines[-len(tail):]])

    def test_a_window_that_starts_on_a_line_boundary_keeps_that_line(self):
        lines = [f'{number:063d}\n'.encode() for number in range(2000)]  # 64 bytes: the window is 1024 whole lines
        self.path.write_bytes(b''.join(lines))
        tail = serve.tail_lines(self.path, count=5000)
        self.assertEqual(len(tail), 1024)
        self.assertEqual(tail[0], f'{976:063d}')

    def test_the_offset_of_this_run_still_limits_the_tail(self):
        for before in (b'antes\n' * 100, b'antes\n' * 40000):  # inside and before the 64 KB window
            with self.subTest(size=len(before)):
                self.path.write_bytes(before + b'depois 1\ndepois 2\n')
                self.assertEqual(serve.tail_lines(self.path, offset=len(before)), ['depois 1', 'depois 2'])
        self.assertEqual(serve.tail_lines(Path(self.tmp.name) / 'nao-existe.log'), [])


class PreviewMergeCommitTest(RefreshTestCase):
    def test_the_merge_uses_the_commit_read_by_the_check_not_the_branch_read_again(self):
        old = self.rev('issue-1')
        self.git('worktree', 'add', '-q', '-b', 'previa', str(self.worktree), 'main')
        self.git('checkout', '-q', 'issue-1')  # the branch moves after the check read it
        (self.root / 'issue1.txt').write_text('mudou depois do check\n', encoding='utf-8')
        self.git('commit', '-q', '-am', 'depois do check')
        self.git('checkout', '-q', 'main')
        self.assertNotEqual(self.rev('issue-1'), old)
        block = serve.load_preview_block(self.config, self.root)
        merged = serve.merge_branches(block, self.worktree, ['issue-1'], {'issue-1': old})
        self.assertEqual(merged, [{'branch': 'issue-1', 'commit': old}])
        self.assertEqual(self.rev('previa^2'), old)
        self.assertEqual(self.git('log', '-1', '--format=%s', 'previa'), "Merge branch 'issue-1' into previa")


class PreviewRefreshGuardTest(FakeRecordMixin, RefreshTestCase):
    """Refusals of `preview refresh` before anything is stopped: a fake live preview (sleeping processes) proves
    nothing was torn down, and neither the preview worktree nor any branch moves."""

    def live(self, branch='previa'):
        self.process, self.relay = self.sleeper(), self.sleeper()
        self.before = self.fake_registry(self.process, self.relay, branch)
        self.refs = self.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads')

    def assert_refused(self, done, needle):
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso', result)
        self.assertIn(needle, result['error'])
        self.assertEqual(self.registry().read_text(encoding='utf-8'), self.before)
        self.assertTrue(serve.pid_alive(self.process['pid']) and serve.pid_alive(self.relay['pid']),
                        'uma recusa de uso derrubou a prévia')
        self.assertEqual(self.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads'), self.refs)
        self.assertFalse(serve.preview_log_dir(self.root).exists())
        return result

    def test_a_dangerous_branch_name_is_refused(self):
        self.live()
        for value in ('-x', 'a..b', 'nome.lock', 'com espaço', 'a/', 'a//b'):
            with self.subTest(branch=value):
                self.assert_refused(self.serve('preview', 'refresh', f'--branch={value}'),
                                    'não é um nome simples')
        self.assertFalse(self.worktree.exists())

    def test_a_base_that_is_the_preview_branch_or_a_dangerous_name_is_refused(self):
        self.live()
        for value, needle in (('previa', 'própria branch da prévia'), ('-x', '--base precisa'),
                              ('a..b', '--base precisa')):
            with self.subTest(base=value):
                self.assert_refused(self.serve('preview', 'refresh', f'--base={value}'), needle)
        self.assertFalse(self.worktree.exists())

    def test_a_preview_worktree_that_is_not_a_worktree_of_this_repository_is_refused(self):
        self.live()
        self.worktree.mkdir(parents=True)
        (self.worktree / 'meu.txt').write_text('nao e da previa\n', encoding='utf-8')
        self.assert_refused(self.refresh('issue-1'), 'não é uma worktree deste repositório')
        self.git('init', '-q', '-b', 'outro', cwd=self.worktree)  # another repository in its place
        self.assert_refused(self.refresh('issue-1'), 'não é uma worktree deste repositório')
        self.assertEqual((self.worktree / 'meu.txt').read_text(encoding='utf-8'), 'nao e da previa\n')

    def test_a_preview_worktree_on_another_branch_is_refused(self):
        self.git('worktree', 'add', '-q', '-b', 'outra', str(self.worktree), 'main')
        self.live()
        self.assert_refused(self.refresh('issue-1'), 'não está na branch previa')
        self.assertEqual(self.git('symbolic-ref', '--short', 'HEAD', cwd=self.worktree), 'outra')

    def test_a_preview_branch_in_use_in_another_worktree_is_refused(self):
        self.git('worktree', 'add', '-q', '-b', 'previa', str(Path(self.tmp.name) / 'outra'), 'main')
        self.live()
        self.assert_refused(self.refresh('issue-1'), 'em uso em outra worktree')
        self.assertFalse(self.worktree.exists())

    def test_an_existing_branch_that_is_not_the_previews_is_never_moved_by_the_first_refresh(self):
        self.branch('previa', {'proprio.txt': 'commit proprio\n'})
        own = self.rev('previa')
        done = self.refresh('issue-1')  # no record at all
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso')
        self.assertIn('já existe', result['error'])
        self.assertIn('git worktree prune', result['error'])
        self.assertEqual(self.rev('previa'), own, 'o refresh moveu uma branch que não era da prévia')
        self.assertFalse(self.worktree.exists())
        self.live(branch='antiga')  # a record that names another branch does not vouch for this one
        self.assert_refused(self.refresh('issue-1'), 'já existe')
        self.assertEqual(self.rev('previa'), own)
        self.assertFalse(self.worktree.exists())

    def charter(self, path, branch='issue-1'):
        """2nd review of issue 34 (B1): a fictitious authorization record whose `worktrees` names the worktree of
        issue 1; entries out of the format beside it are skipped."""
        folder = self.root / '.frontlights'
        folder.mkdir(exist_ok=True)
        (folder / 'authorization-teste.json').write_text(json.dumps({
            'repository': 'OWNER/REPOSITORY', 'issue_ids': [1],
            'worktrees': ['texto', {'issue': 2}, {'issue': 1, 'path': path, 'branch': branch}]}), encoding='utf-8')

    def preview_on(self, worktree, branch):
        self.write_config(preview=dict(self.refresh_block(), worktree=worktree, branch=branch))

    def assert_refused_without_record(self, needle):
        refs = self.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads')
        done = self.refresh()
        self.assertEqual(done.returncode, 1, done_text(done))
        result = self.payload(done)
        self.assertEqual(result['category'], 'uso', result)
        self.assertIn(needle, result['error'])
        self.assertEqual(self.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads'), refs)
        self.assertFalse(serve.preview_log_dir(self.root).exists())

    def test_a_preview_on_the_worktree_and_the_branch_of_an_issue_is_refused_with_or_without_a_record(self):
        issue = self.root / '.claude' / 'worktrees' / 'issue-1'
        self.git('worktree', 'add', '-q', str(issue), 'issue-1')
        self.charter(str(issue))  # absolute, as the session records it
        self.preview_on('.claude/worktrees/issue-1', 'issue-1')
        own = self.rev('issue-1')
        self.assert_refused_without_record('worktree de issue')
        self.live(branch='issue-1')
        self.assert_refused(self.refresh(), 'worktree de issue')
        self.assertEqual(self.rev('issue-1'), own, 'o refresh moveu a branch da issue')
        self.assertEqual(self.git('symbolic-ref', '--short', 'HEAD', cwd=issue), 'issue-1')
        self.assertTrue((issue / 'issue1.txt').is_file())

    def test_a_preview_branch_named_by_an_issue_worktree_is_refused_even_when_the_record_names_it(self):
        self.charter('.claude/worktrees/issue-1')
        self.preview_on('.claude/worktrees/previa', 'issue-1')
        own = self.rev('issue-1')
        self.assert_refused_without_record('worktree de issue')
        self.live(branch='issue-1')  # the record would vouch for the branch: the charter still wins
        self.assert_refused(self.refresh(), 'worktree de issue')
        self.assertEqual(self.rev('issue-1'), own)
        self.assertFalse(self.worktree.exists())

    def test_a_preview_worktree_named_by_an_issue_worktree_is_refused(self):
        issue = self.root / '.claude' / 'worktrees' / 'issue-1'
        self.git('worktree', 'add', '-q', '-b', 'previa', str(issue), 'main')
        self.charter('.claude/worktrees/issue-1')
        self.preview_on('.claude/worktrees/issue-1', 'previa')
        self.assert_refused_without_record('worktree de issue')
        self.live()
        self.assert_refused(self.refresh(), 'worktree de issue')

    def test_the_first_refresh_redoes_the_branch_the_registry_names(self):
        self.branch('previa', {'proprio.txt': 'commit proprio\n'})
        self.fake_registry(self.dead(), self.dead(), 'previa')
        with mock.patch.object(serve, 'launch_preview', return_value={'ok': True}) as launch:
            result = serve.preview_refresh(self.config, self.root, ['issue-1'], 'main')
        launch.assert_called_once()
        self.assertEqual(result['merged'], [{'branch': 'issue-1', 'commit': self.rev('issue-1')}])
        self.assertEqual((self.rev('previa^1'), self.rev('previa^2')), (self.rev('main'), self.rev('issue-1')))


def done_text(done):
    return done.stdout + done.stderr


if __name__ == '__main__':
    unittest.main()
