"""`roads.py`: o bloco `roadmapSync`, a credencial, a aprovação e o transporte. O `gaps` e a leitura do
`roadmap-state` saíram na issue 65.

Seams: `roads.run('status' | 'approve', ...)`, a linha de comando, `roads.request` com o transporte HTTP simulado, e
`roads.http_default` contra um servidor local. Os testes usam transporte simulado: não homologam a RoadS real.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import roads as rs

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts' / 'roads.py'
SECRET = 'fixture-secret-value'


class Transport:
    """Records every request and answers from a queue of (status, body); an exception in the
    queue is raised instead, as the real transport does for a network error."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append({'method': method, 'url': url, 'headers': headers, 'body': body})
        answer = self.answers.pop(0) if self.answers else (200, '{}')
        if isinstance(answer, Exception):
            raise answer
        status, body_out = answer
        return status, body_out if isinstance(body_out, str) else json.dumps(body_out)


class RoadsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.project = base / 'project'
        self.scrum = base / 'scrum'
        (self.project / '.frontlights').mkdir(parents=True)
        self.scrum.mkdir()
        self.write_config()
        env = patch.dict(os.environ, {'FRONTLIGHTS_API_SECRET': SECRET})
        env.start()
        self.addCleanup(env.stop)
        user_env = patch.object(rs, 'windows_user_env', return_value=None)
        user_env.start()
        self.addCleanup(user_env.stop)
        rs._SECRETS.clear()

    def write_config(self, **overrides):
        sync = {'enabled': True, 'endpoint': 'https://roads.example.test/api/frontlights',
                'secretEnvVar': 'FRONTLIGHTS_API_SECRET', 'scrumRoot': str(self.scrum),
                'weekFolderPattern': '{yyyy}/{dd_MM}'}
        sync.update(overrides)
        config = {'repository': 'OWNER/REPOSITORY', 'project': None, 'roads': None, 'roadmapSync': sync}
        (self.project / '.frontlights' / 'config.json').write_text(json.dumps(config), encoding='utf-8')

    def run_op(self, operation):
        return rs.run(operation, str(self.project))

    def get(self, *answers):
        """GET <endpoint>/progress-report through `request`, the transport every RoadS call of the skill uses."""
        self.assertTrue(self.run_op('approve')['ok'])
        transport = Transport(*answers)
        ctx = rs.Context(str(self.project))
        return rs.request(ctx, transport, 'GET', rs.endpoint_url(ctx.endpoint, 'progress-report')), transport


class ConfigurationTests(RoadsTestCase):
    def test_status_without_configuration_is_not_an_error(self):
        (self.project / '.frontlights' / 'config.json').unlink()
        result = self.run_op('status')
        self.assertTrue(result['ok'])
        self.assertFalse(result['configured'])
        self.assertFalse(result['ready'])

    def test_status_reports_secret_and_approval_and_never_touches_the_network(self):
        with patch.object(rs, 'http_default', side_effect=AssertionError('network')) as network:
            result = self.run_op('status')
        self.assertTrue(result['configured'])
        self.assertEqual((result['secret'], result['approval']), ('present', 'unapproved'))
        self.assertFalse(result['ready'])
        self.assertEqual(result['obsoleteKeys'], [])
        self.assertFalse(network.called)
        self.run_op('approve')
        self.assertTrue(self.run_op('status')['ready'])

    def test_status_names_the_keys_of_the_retired_roadmap_sync_and_ignores_them(self):
        self.write_config(roadmapFile='{yyyy}/ROADMAP.md', sprintFilePattern='SPRINT_{dd_MM}_a_{dd_MM}.md',
                          maxSprintItems='not checked any more', markCompleted='nor this',
                          issueTargets={'Example Product': {'repository': 'OWNER/REPOSITORY'}})
        result = self.run_op('status')
        self.assertTrue(result['configured'], result['message'])
        self.assertEqual(result['obsoleteKeys'],
                         ['roadmapFile', 'sprintFilePattern', 'maxSprintItems', 'markCompleted', 'issueTargets'])
        self.assertIn('retired roadmap sync', result['message'])

    def test_the_operations_of_the_retired_roadmap_sync_are_gone(self):
        for operation in ('fetch', 'apply', 'ack', 'rotate-markers'):
            with self.subTest(operation=operation):
                result = self.run_op(operation)
                self.assertFalse(result['ok'])
                self.assertIn('Unknown operation', result['message'])

    def test_the_gaps_operation_left_frontlights_with_the_roadmap_state_reader(self):
        # issue 65: completing the issues RoadS shows is no longer a Frontlights step
        result = self.run_op('gaps')
        self.assertFalse(result['ok'])
        self.assertIn('Unknown operation', result['message'])
        for name in ('op_gaps', 'issue_gaps', 'read_state', 'normalise_state', 'read_issues', 'board_layout'):
            with self.subTest(name=name):
                self.assertFalse(hasattr(rs, name))
        done = subprocess.run([sys.executable, str(SCRIPT), 'gaps', '--root', str(self.project)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("invalid choice: 'gaps'", done.stderr)
        self.assertEqual(done.stdout, '')

    def test_an_enabled_block_that_does_not_validate_is_reported_not_hidden(self):
        self.write_config(endpoint='http://roads.example.test/api')
        result = self.run_op('status')
        self.assertEqual((result['configured'], result['enabled']), (False, True))
        self.assertIn('https', result['message'])
        self.write_config(enabled=False)
        self.assertEqual((self.run_op('status')['configured'], self.run_op('status')['enabled']), (False, False))
        (self.project / '.frontlights' / 'config.json').unlink()
        self.assertFalse(self.run_op('status')['enabled'])

    def test_secret_variable_must_carry_the_frontlights_prefix(self):
        self.write_config(secretEnvVar='GUARDIANS_API_SECRET')
        result = self.run_op('status')
        self.assertFalse(result['configured'])
        self.assertIn('^FRONTLIGHTS_', result['message'])

    def test_endpoint_must_be_https_without_credentials(self):
        for endpoint in ('http://roads.example.test/api', 'https://user:pw@roads.example.test/api',
                         'https://roads.example.test/api?x=1'):
            with self.subTest(endpoint=endpoint):
                self.write_config(endpoint=endpoint)
                self.assertFalse(self.run_op('status')['configured'])
        self.write_config(endpoint='http://localhost:3000/api/frontlights')
        self.assertTrue(self.run_op('status')['configured'])

    def test_approval_covers_the_full_url_and_the_variable(self):
        self.run_op('approve')
        self.assertEqual(self.run_op('status')['approval'], 'approved')
        self.write_config(endpoint='https://roads.example.test/api/other-tenant')
        self.assertEqual(self.run_op('status')['approval'], 'changed')

    def test_an_approval_recorded_by_the_retired_roadmap_sync_still_holds(self):
        record = {'schemaVersion': 1, 'endpoint': 'https://roads.example.test/api/frontlights',
                  'secretEnvVar': 'FRONTLIGHTS_API_SECRET', 'approvedAt': '2026-10-01T10:00:00-03:00'}
        path = self.project / '.frontlights' / 'roadmap-sync' / 'approval.json'
        path.parent.mkdir()
        path.write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(self.run_op('status')['approval'], 'approved')


class TransportTests(RoadsTestCase):
    def test_the_bearer_goes_only_to_the_approved_endpoint(self):
        text, transport = self.get((200, {'window': None}))
        self.assertEqual([(c['method'], c['url']) for c in transport.calls],
                         [('GET', 'https://roads.example.test/api/frontlights/progress-report')])
        self.assertEqual(transport.calls[0]['headers'], {'Authorization': f'Bearer {SECRET}'})
        self.assertEqual(json.loads(text), {'window': None})

    def test_redirect_and_rejected_credential_are_refused_without_leaking_the_secret(self):
        for status, fragment in ((302, 'redirect'), (401, 'rejected the credential'), (500, 'HTTP 500')):
            with self.subTest(status=status):
                with self.assertRaises(rs.Refusal) as caught:
                    self.get((status, ''))
                self.assertIn(fragment, str(caught.exception))
                self.assertNotIn(SECRET, rs.protect(str(caught.exception)))

    def test_protect_redacts_the_secret_once_it_was_read(self):
        rs.read_secret('FRONTLIGHTS_API_SECRET')
        self.assertEqual(rs.protect(f'token {SECRET} here'), 'token [redacted] here')

    def test_the_real_transport_sends_the_versioned_user_agent(self):
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get('User-Agent'))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{}')

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        status, _ = rs.http_default('GET', f'http://127.0.0.1:{server.server_address[1]}/x', {}, None)
        self.assertEqual(status, 200)
        self.assertEqual(seen, [rs.user_agent()])
        self.assertRegex(seen[0], r'^frontlights-roadmap-sync/[0-9a-f]{12}$')

    def test_the_user_agent_names_the_skill_and_its_commit(self):
        head = subprocess.run(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', '--short=12', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(rs.user_agent(), f'frontlights-roadmap-sync/{head}')


class PathTests(RoadsTestCase):
    """The checks every path under scrumRoot gets; progress_report.py saves the prints of the summary there."""

    def test_pattern_expansion_uses_start_then_end(self):
        import datetime as dt
        start, end = dt.date(2026, 9, 28), dt.date(2026, 10, 2)
        self.assertEqual(rs.expand_pattern('{yyyy}/{dd_MM}', start, end), '2026/28_09')
        self.assertEqual(rs.expand_pattern('X_{dd_MM}_a_{dd_MM}', start, end), 'X_28_09_a_02_10')

    def test_unsafe_relative_paths_are_refused(self):
        for relative in ('../fora', '2026/pasta.', '2026/ /x', 'a:b'):
            with self.subTest(relative=relative):
                with self.assertRaises(rs.Refusal):
                    rs.safe_folder(str(self.scrum), relative, create=True)

    def test_relative_scrum_root_is_refused(self):
        with self.assertRaises(rs.Refusal):
            rs.contained_path('scrum', '2026/28_09')

    @unittest.skipUnless(sys.platform.startswith('win'), 'drive roots are a Windows concept')
    def test_drive_root_is_refused(self):
        with self.assertRaises(rs.Refusal):
            rs.contained_path('C:\\', '2026/28_09')

    def test_a_folder_is_created_inside_the_scrum_root(self):
        folder = rs.safe_folder(str(self.scrum), '2026/28_09', create=True)
        self.assertEqual(Path(folder), self.scrum / '2026' / '28_09')
        self.assertTrue(Path(folder).is_dir())

    def test_cloud_reparse_tags_are_storage_not_redirection(self):
        self.assertTrue(rs.cloud_tag(0x9000001A))
        self.assertTrue(rs.cloud_tag(0x9000601A))
        self.assertFalse(rs.cloud_tag(0xA0000003))  # mount point / junction
        self.assertFalse(rs.cloud_tag(0xA000000C))  # symbolic link


if __name__ == '__main__':
    unittest.main()
