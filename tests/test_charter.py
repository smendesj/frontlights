"""Etapa 6 por comando, S1 (redesenho, issue 4): `frontlights.py charter new|renew|add` grava todos os campos que o
`authorize` lê, com a posse (ownership) obrigatória, o prefixo pela cadeia, o charter anterior guardado, o anúncio
em português e o dry-run do `authorize` antes de gravar.

Seams: `frontlights.charter_cli` e a entrada `frontlights.py charter`.
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import frontlights  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture  # noqa: E402

REPO = 'OWNER/REPOSITORY'


def build(folder):
    """A bare origin with one commit on main, and the project that pushed it (no worktree in the template)."""
    origin = folder / 'origin.git'
    subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True)
    project = gitfixture.init(folder / 'project')
    (project / 'src').mkdir()
    (project / 'src' / 'app.py').write_text('print(1)\n', encoding='utf-8')
    (project / '.gitignore').write_text('.frontlights/\n__pycache__/\n', encoding='utf-8')
    gitfixture.git(project, 'add', '.')
    gitfixture.git(project, 'commit', '-q', '-m', 'base')
    gitfixture.git(project, 'remote', 'add', 'origin', str(origin))
    gitfixture.git(project, 'push', '-q', '-u', 'origin', 'main')


class CharterCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = gitfixture.copy(self.template, Path(tmp.name) / 'f')
        self.root = self.folder / 'project'
        (self.root / '.frontlights').mkdir()
        self.config = self.root / '.frontlights' / 'config.json'
        self.write_config()

    def write_config(self, **extra):
        data = {'repository': REPO, 'branchPrefix': 'PREFIX/'}
        data.update(extra)
        self.config.write_text(json.dumps(data), encoding='utf-8')

    def charter(self, action='new', **options):
        options.setdefault('issues', ['12'])
        options.setdefault('ownership', ['src/app.py', 'tests'])
        options.setdefault('approved_by', 'OWNER-LOGIN')
        return frontlights.charter_cli(action, str(self.root), str(self.config), **options)

    def record(self):
        return json.loads((self.root / '.frontlights' / 'authorization.json').read_text(encoding='utf-8'))


class CharterNewTests(CharterCase):
    def test_new_writes_every_field_authorize_reads(self):
        result = self.charter()
        self.assertTrue(result['ok'], result)
        record = self.record()
        for key in ('repository', 'issue_ids', 'operations', 'protected_branches', 'stop_conditions', 'base',
                    'issued_at', 'expires_at', 'monitoring', 'approved_by', 'confirmed_by', 'approval_reference',
                    'concurrency', 'branch_prefix', 'worktrees', 'verification_commands', 'ownership'):
            self.assertIn(key, record)
        self.assertEqual(record['repository'], REPO)
        self.assertEqual(record['issue_ids'], [12])
        self.assertEqual(record['branch_prefix'], 'PREFIX/')
        self.assertEqual(record['monitoring']['mode'], 'local')
        self.assertEqual(record['monitoring']['confirmed_by'], 'OWNER-LOGIN')
        self.assertEqual(record['approval_reference'], 'autorização permanente (docs/security.md)')
        self.assertEqual(record['base']['branch'], 'main')
        self.assertEqual(record['base']['issues']['from'], 'origin/main')
        self.assertRegex(record['base']['issues']['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(record['ownership'], {'12': ['src/app.py', 'tests']})
        issued = dt.datetime.fromisoformat(record['issued_at'])
        expires = dt.datetime.fromisoformat(record['expires_at'])
        self.assertIsNotNone(issued.tzinfo)
        self.assertLessEqual(expires - issued, dt.timedelta(hours=24))
        self.assertEqual(result['dryRun'][0]['scope_check'], 'pass')

    def test_an_entry_with_the_ownership_passes_authorize_for_an_owned_edit(self):
        self.charter()
        record = self.record()
        record['worktrees'].append({'issue': 12, 'path': str(self.root), 'branch': 'PREFIX/issue-12',
                                    'ownership': record['ownership']['12']})
        op = {'repository': REPO, 'issue': 12, 'kind': 'edit', 'worktree': str(self.root),
              'branch': 'PREFIX/issue-12', 'path': 'src/app.py'}
        self.assertEqual(frontlights.authorize(record, op)['scope_check'], 'pass')

    def test_the_ownership_is_required_and_never_star_alone(self):
        for ownership in ([], ['*']):
            with self.subTest(ownership=ownership):
                result = self.charter(ownership=ownership)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], 'ownership_required')
                self.assertFalse((self.root / '.frontlights' / 'authorization.json').exists())

    def test_ownership_by_issue_for_a_batch(self):
        result = self.charter(issues=['12', '13'], ownership=['12=src/app.py', '13=docs,tests'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.record()['ownership'], {'12': ['src/app.py'], '13': ['docs', 'tests']})
        result = self.charter(issues=['12', '13'], ownership=['12=src/app.py'])
        self.assertEqual((result['ok'], result['reason']), (False, 'ownership_required'))

    def test_the_prefix_follows_the_chain(self):
        self.charter(prefix='OTHER/')
        self.assertEqual(self.record()['branch_prefix'], 'OTHER/')
        self.write_config()
        result = self.charter()
        self.assertEqual((self.record()['branch_prefix'], result['prefixSource']), ('PREFIX/', 'config'))
        self.config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')
        result = self.charter()
        self.assertEqual((result['ok'], result['reason']), (False, 'no_prefix'))

    def test_a_config_with_the_snake_case_key_names_the_prefix(self):
        self.config.write_text(json.dumps({'repository': REPO, 'branch_prefix': 'PREFIX/'}), encoding='utf-8')
        result = self.charter()
        self.assertTrue(result['ok'], result)
        self.assertEqual((self.record()['branch_prefix'], result['prefixSource']), ('PREFIX/', 'config:branch_prefix'))
        self.assertNotIn('warnings', result)
        self.write_config(branch_prefix='OTHER/')
        result = self.charter()
        self.assertEqual((self.record()['branch_prefix'], result['prefixSource']), ('PREFIX/', 'config'))
        self.assertTrue(any(w.startswith('branch_prefix_conflict') for w in result['warnings']), result)

    def test_the_previous_charter_is_kept_never_deleted(self):
        self.charter()
        first = (self.root / '.frontlights' / 'authorization.json').read_text(encoding='utf-8')
        result = self.charter(issues=['13'])
        self.assertTrue(result['ok'], result)
        kept = sorted((self.root / '.frontlights').glob('authorization-*-issue-12*.json'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding='utf-8'), first)
        self.assertEqual(result['kept'], str(kept[0]))
        self.assertEqual(self.record()['issue_ids'], [13])
        self.charter(issues=['14'])
        self.assertEqual(len(list((self.root / '.frontlights').glob('authorization-*.json'))), 2)

    def test_the_announcement_is_in_portuguese(self):
        result = self.charter()
        text = result['announcement']
        for part in ('autorização permanente', '#12', REPO, 'PREFIX/', 'origin/main', 'src/app.py', 'São Paulo'):
            self.assertIn(part, text)

    def test_a_refused_dry_run_writes_nothing(self):
        result = self.charter(protect=['PREFIX/*'])
        self.assertEqual((result['ok'], result['reason']), (False, 'authorize_refused'))
        self.assertIn('branch_prefix', result['message'])
        self.assertFalse((self.root / '.frontlights' / 'authorization.json').exists())

    def test_more_than_24_hours_is_refused(self):
        result = self.charter(hours=25)
        self.assertEqual((result['ok'], result['reason']), (False, 'hours'))

    def test_direct_work_has_the_local_main_as_base(self):
        result = self.charter(issues=[], directs=['melhoria-x'], ownership=['src'])
        self.assertTrue(result['ok'], result)
        record = self.record()
        self.assertEqual((record['issue_ids'], record['direct_ids']), ([], ['melhoria-x']))
        self.assertEqual(record['base']['direct']['from'], 'main')
        self.assertNotIn('issues', record['base'])


class CharterRenewAddTests(CharterCase):
    def test_renew_extends_expires_at_and_keeps_the_rest(self):
        self.charter()
        record = self.record()
        record['expires_at'] = '2000-01-01T00:00:00+00:00'
        record['worktrees'] = [{'issue': 12, 'path': 'x', 'branch': 'PREFIX/issue-12', 'ownership': ['src']}]
        (self.root / '.frontlights' / 'authorization.json').write_text(json.dumps(record), encoding='utf-8')
        result = frontlights.charter_cli('renew', str(self.root), str(self.config))
        self.assertTrue(result['ok'], result)
        renewed = self.record()
        self.assertGreater(dt.datetime.fromisoformat(renewed['expires_at']), dt.datetime.now(dt.timezone.utc))
        self.assertEqual(renewed['worktrees'], record['worktrees'])
        self.assertEqual(list((self.root / '.frontlights').glob('authorization-*.json')), [])

    def test_renew_without_a_charter_is_refused(self):
        result = frontlights.charter_cli('renew', str(self.root), str(self.config))
        self.assertEqual((result['ok'], result['reason']), (False, 'no_charter'))

    def test_add_puts_an_issue_with_its_ownership_in_the_charter(self):
        self.charter()
        result = self.charter('add', issues=['13'], ownership=['docs'])
        self.assertTrue(result['ok'], result)
        record = self.record()
        self.assertEqual(record['issue_ids'], [12, 13])
        self.assertEqual(record['ownership']['13'], ['docs'])
        again = self.charter('add', issues=['13'], ownership=['docs'])
        self.assertEqual((again['ok'], again['reason']), (False, 'already_in_charter'))


    def test_add_announces_the_base_origin_has_now_not_the_one_of_new(self):
        """Teste real (23/10/2026): o `charter add` anunciou a base com um commit velho de origin/main."""
        self.charter()
        other = self.folder / 'outro'
        subprocess.run(['git', 'clone', '-q', str(self.folder / 'origin.git'), str(other)], check=True)
        for key, value in (('user.email', 'x@example.invalid'), ('user.name', 'X')):
            gitfixture.git(other, 'config', key, value)
        (other / 'novo.txt').write_text('x', encoding='utf-8')
        gitfixture.git(other, 'add', '.')
        gitfixture.git(other, 'commit', '-q', '-m', 'novo na origin')
        gitfixture.git(other, 'push', '-q', 'origin', 'main')
        fresh = gitfixture.git(other, 'rev-parse', 'HEAD').stdout.strip()
        result = self.charter('add', issues=['13'], ownership=['docs'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.record()['base']['issues']['commit'], fresh)
        self.assertIn(f'origin/main ({fresh[:7]})', result['announcement'])


class CharterCommandLineTests(CharterCase):
    def test_the_command_line_writes_the_charter_from_the_project(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'frontlights.py'), 'charter', 'new', '--issue', '12',
                               '--ownership', 'src', '--approved-by', 'OWNER-LOGIN'],
                              cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        result = json.loads(done.stdout)
        self.assertTrue(result['ok'])
        self.assertEqual(self.record()['issue_ids'], [12])

    def test_without_ownership_the_command_line_names_the_flag(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'frontlights.py'), 'charter', 'new', '--issue', '12',
                               '--approved-by', 'OWNER-LOGIN'],
                              cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 1)
        self.assertIn('--ownership', json.loads(done.stdout)['hint'])


if __name__ == '__main__':
    unittest.main()
