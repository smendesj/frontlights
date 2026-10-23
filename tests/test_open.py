"""`frontlights.py open` (issue 2 do redesenho): as leituras da abertura num comando só.

Seams: `frontlights.open_session` e o `--help` do `frontlights.py`, com um repositório Git real (origin nu local,
então o `fetch --prune` roda sem rede) e um `gh` simulado que só aceita leituras (`api graphql` sem mutation),
composto dos simulados de `test_cleanup` (branches e PRs) e de `test_closeout` (issues). Os testes usam GitHub
simulado: não homologam o GitHub real. Marcadores genéricos (OWNER/REPOSITORY).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skills' / 'frontlights' / 'scripts'))
sys.path.insert(0, str(HERE))
import frontlights  # noqa: E402
import gitfixture  # noqa: E402
import test_cleanup  # noqa: E402
import test_closeout  # noqa: E402

SCRIPT = HERE.parent / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
REPO = 'OWNER/REPOSITORY'


class ComposedGh:
    """The issue reads go to the closeout fake, the branch reads to the cleanup fake; both refuse any write."""

    def __init__(self, branches=None, nodes=None, fail_issues=False):
        self.cleanup = test_cleanup.FakeGh(branches)
        self.closeout = test_closeout.FakeGh(nodes, fail_issues=fail_issues)

    def __call__(self, argv):
        query = next((a for a in argv if a.startswith('query=')), '')
        return (self.closeout if 'issue(number' in query else self.cleanup)(argv)

    @property
    def violations(self):
        return self.cleanup.violations + self.closeout.violations


class OpenCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, cls.build)

    @classmethod
    def build(cls, folder):
        origin = folder / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True, capture_output=True)
        root = gitfixture.init(folder / 'proj')
        (root / 'app.txt').write_text('one\n')
        gitfixture.git(root, 'add', '.')
        gitfixture.git(root, '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'first')
        gitfixture.git(root, 'remote', 'add', 'origin', str(origin))
        gitfixture.git(root, 'push', '-q', 'origin', 'main')
        (root / '.frontlights').mkdir()
        with open(root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('/.frontlights/\n')
        (root / '.frontlights' / 'config.json').write_text(json.dumps({'repository': REPO}), encoding='utf-8')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        gitfixture.copy(self.template, self.base, exist_ok=True)
        self.root = self.base / 'proj'
        self.config = self.root / '.frontlights' / 'config.json'

    def git(self, *args, cwd=None):
        return gitfixture.git(cwd or self.root, '-c', 'commit.gpgsign=false', *args).stdout.strip()

    def worktree(self, name, issue=12, push=True):
        """A worktree on `PREFIX/<name>` with one commit; with `push`, the commit reaches origin/main (released)."""
        path, branch = self.base / name, f'PREFIX/{name}'
        self.git('worktree', 'add', '-q', '-b', branch, str(path))
        (path / f'{name}.txt').write_text(name)
        self.git('add', '.', cwd=path)
        self.git('commit', '-q', '-m', name, cwd=path)
        if push:
            self.git('push', '-q', 'origin', f'{branch}:main')
        return path, branch

    def authorize(self, entries, ids=None):
        data = {'issue_ids': ids if ids is not None else sorted({e['issue'] for e in entries}), 'base': {'branch': 'main'},
                'branch_prefix': 'PREFIX/', 'worktrees': entries}
        (self.root / '.frontlights' / 'authorization.json').write_text(json.dumps(data), encoding='utf-8')

    def open(self, gh, fetch=True):
        result = frontlights.open_session(self.config, self.root, gh=gh, fetch=fetch)
        self.assertEqual(gh.violations, [])
        return result


class OpenTests(OpenCase):
    def test_one_command_fetches_plans_the_cleanup_and_finds_the_closeout_and_removes_nothing(self):
        path, branch = self.worktree('issue-12')
        self.authorize([{'issue': 12, 'path': str(path), 'branch': branch}])
        gh = ComposedGh(nodes={12: test_closeout.node(12)})
        result = self.open(gh)
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['fetched'])
        kinds = [c['kind'] for c in result['cleanup']['commands']]
        self.assertEqual(kinds, ['fetch_prune', 'remove_worktree', 'delete_branch'])
        self.assertEqual((result['cleanup']['ask'], result['cleanup']['excluded'], result['cleanup']['alreadyClean']),
                         ([], [], 0))
        self.assertEqual(result['cleanup']['issues'], [12])
        self.assertEqual((result['closeout']['ask'], result['closeout']['count']), (True, 1))
        self.assertEqual(result['closeout']['issues'][0]['number'], 12)
        self.assertEqual(result['closeout']['question'], 'Fechar as issues que já têm todos os critérios marcados?')
        self.assertTrue(path.is_dir(), 'open never removes')
        self.assertIn(branch, self.git('branch', '--list', branch))
        self.assertIn('Nada foi removido nem fechado', result['message'])

    def test_the_base_comes_from_the_authorization_record(self):
        path, branch = self.worktree('issue-12')
        self.authorize([{'issue': 12, 'path': str(path), 'branch': branch}])
        result = self.open(ComposedGh(nodes={12: test_closeout.node(12)}))
        self.assertEqual(result['cleanup']['expectedBase'], 'main')

    def test_a_candidate_with_ignored_files_is_listed_in_ask(self):
        path, branch = self.worktree('issue-12')
        with open(self.root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('*.env\n')
        (path / 'local.env').write_text('X=1')
        self.authorize([{'issue': 12, 'path': str(path), 'branch': branch}])
        result = self.open(ComposedGh(nodes={12: test_closeout.node(12)}))
        self.assertEqual([a['branch'] for a in result['cleanup']['ask']], [branch])
        self.assertEqual(result['cleanup']['ask'][0]['askIgnored'], ['local.env'])
        self.assertEqual([c['kind'] for c in result['cleanup']['commands']], ['fetch_prune'])

    def test_an_issue_whose_branch_is_not_released_waits_and_its_worktree_stays(self):
        path, branch = self.worktree('issue-12', push=False)
        self.authorize([{'issue': 12, 'path': str(path), 'branch': branch}])
        result = self.open(ComposedGh(nodes={12: test_closeout.node(12)}))
        self.assertEqual(result['closeout']['awaiting_release'], [12])
        self.assertFalse(result['closeout']['ask'])
        self.assertEqual([e['reasons'] for e in result['cleanup']['excluded']], [['no_merged_pr']])
        self.assertIn('esperam a release: #12', result['message'])

    def test_without_authorization_records_nothing_is_cleaned(self):
        result = self.open(ComposedGh())
        self.assertEqual(result['cleanup']['commands'], [])
        self.assertEqual(result['cleanup']['issues'], [])
        self.assertFalse(result['closeout']['ask'])

    def test_a_part_that_fails_is_a_warning_and_the_other_part_still_runs(self):
        path, branch = self.worktree('issue-12')
        self.authorize([{'issue': 12, 'path': str(path), 'branch': branch}])
        result = self.open(ComposedGh(fail_issues=True))
        self.assertIsNone(result['closeout'])
        self.assertTrue(any(w.startswith('closeout_failed:') for w in result['warnings']), result['warnings'])
        self.assertEqual(len(result['cleanup']['commands']), 3)

    def test_without_fetch_nothing_is_fetched(self):
        result = self.open(ComposedGh(), fetch=False)
        self.assertFalse(result['fetched'])

    def test_the_command_line_lists_open(self):
        done = subprocess.run([sys.executable, str(SCRIPT), 'open', '--help'], capture_output=True, text=True,
                              encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        for flag in ('--config', '--root', '--no-fetch', '--full'):
            with self.subTest(flag=flag):
                self.assertIn(flag, done.stdout)


if __name__ == '__main__':
    unittest.main()
