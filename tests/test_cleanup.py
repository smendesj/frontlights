"""`cleanup.py`: descobre, só leitura, quais worktrees e branches já podem ser removidos depois do merge.

Seams: `cleanup.run` (`plan` e `verify`) e `cleanup.main`, com repositórios Git reais em pastas temporárias e um
`gh` simulado que só aceita leituras (`api graphql` sem mutation). Os testes usam GitHub simulado: não homologam o
GitHub real. Marcadores genéricos (OWNER/REPOSITORY): o vocabulário de um projeto vive fora daqui.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import cleanup
import roads as rs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture

SCRIPT = Path(cleanup.__file__)
REPO = 'OWNER/REPOSITORY'
EARLY = '2026-10-06T12:00:00Z'
LATE = '2026-10-06T13:00:00Z'
PREMADE = ('wt12', 'issue-12', 'wt-a', 'wt-b', 'wt-c', 'parent')   # the names `worktree` is called with


def pull(number, state='MERGED', base='main', oid=None, merged_at=EARLY):
    return {'number': number, 'state': state, 'merged': state == 'MERGED', 'mergedAt': merged_at if state == 'MERGED' else None,
            'baseRefName': base, 'headRefOid': oid}


def merged(tip, number=7, remote='same', **kw):
    """What GitHub says of a branch whose pull request was merged: `remote='same'` keeps the remote branch at `tip`."""
    return {'heads': [pull(number, oid=tip, **kw)], 'remote': tip if remote == 'same' else remote}


class FakeGh:
    """Answers the two reads the helper makes from canned data and records every argv. A mutation fails."""

    def __init__(self, branches=None, default='main'):
        self.branches, self.default = dict(branches or {}), default
        self.calls, self.violations = [], []

    def queries(self):
        return [a for call in self.calls for a in call if a.startswith('query=')]

    def __call__(self, argv):
        self.calls.append(list(argv))
        query = next((a for a in argv if a.startswith('query=')), '')
        if argv[:2] != ['api', 'graphql'] or not query or re.search(r'\bmutation\b', query):
            self.violations.append(list(argv))
            raise AssertionError(f'not a read: {argv}')
        repo = {}
        if 'defaultBranchRef' in query:
            repo['defaultBranchRef'] = {'name': self.default} if self.default else None
        for i, branch in re.findall(r'h(\d+): pullRequests\(headRefName: "([^"]+)"', query):
            info = self.branches.get(branch, {})
            heads = info.get('heads', [])
            repo[f'h{i}'] = {'totalCount': info.get('total', len(heads)), 'nodes': heads}
            repo[f'd{i}'] = {'totalCount': info.get('dependents', 0)}
            repo[f'r{i}'] = {'target': {'oid': info['remote']}} if info.get('remote') else None
        return {'data': {'repository': repo}}


class CleanupCase(unittest.TestCase):
    root_name = 'proj'

    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, cls.build)

    @classmethod
    def build(cls, folder):
        """The base repository, once per class (and per `root_name`): one commit, a GitHub origin, `.frontlights/`
        ignored and its config. Each test copies it; the copy keeps the file mtimes, and worktrees come after."""
        root = folder / cls.root_name
        root.mkdir()
        git = lambda *args: subprocess.run(['git', '-c', 'commit.gpgsign=false', '-C', str(root), *args], check=True,
                                           capture_output=True, text=True, encoding='utf-8')
        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        (root / 'app.txt').write_text('one\n')
        git('add', '.')
        git('commit', '-q', '-m', 'first')
        git('remote', 'add', 'origin', f'https://github.com/{REPO}.git')
        (root / '.frontlights').mkdir()
        with open(root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('/.frontlights/\n')
        (root / '.frontlights' / 'config.json').write_text(json.dumps({'repository': REPO}), encoding='utf-8')
        # The commit `worktree(name)` makes, made ahead in one process: refs/fixture/<name> on top of main. Nothing
        # of the product reads that namespace; the branch claude/<name> only appears when the test asks for it.
        stamp, lines = int(time.time()), []
        for i, name in enumerate(PREMADE, 1):
            lines += [f'commit refs/fixture/{name}', f'mark :{i}',
                      f'committer Fixture <fixture@example.invalid> {stamp} +0000', f'data {len(name) + 1}', name,
                      'from refs/heads/main', f'M 100644 inline {name}.txt', f'data {len(name)}', name, '']
        marks = folder / 'marks'
        subprocess.run(['git', '-C', str(root), 'fast-import', '--quiet', f'--export-marks={marks}'], check=True,
                       capture_output=True, input='\n'.join(lines).encode('utf-8'))
        tips = dict(line.split() for line in marks.read_text(encoding='utf-8').splitlines() if line)
        cls.premade = {name: tips[f':{i}'] for i, name in enumerate(PREMADE, 1)}
        marks.unlink()
        cls.main_tip = (root / '.git' / 'refs' / 'heads' / 'main').read_text(encoding='utf-8').strip()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        gitfixture.copy(self.template, self.base, exist_ok=True)
        self.root = self.base / self.root_name
        self.config = self.root / '.frontlights' / 'config.json'
        self.entries, self.protected = [], []
        self.tick = 0

    def git(self, *args, cwd=None):
        done = subprocess.run(['git', '-c', 'commit.gpgsign=false', '-C', str(cwd or self.root), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8')
        return done.stdout.strip()

    def authorize(self):
        data = {'issue_ids': sorted({e['issue'] for e in self.entries}), 'worktrees': self.entries,
                'protected_branches': self.protected}
        (self.root / '.frontlights' / 'authorization.json').write_text(json.dumps(data), encoding='utf-8')

    def worktree(self, name, issue=12, commit=True, start=None, record=True):
        """A worktree on a new branch `claude/<name>` with one commit of its own; returns (path, branch, tip)."""
        path, branch = self.base / name, f'claude/{name}'
        if start is None and (name in self.premade or not commit) and self.on_template_main():  # made ahead
            tip = self.premade[name] if commit else self.main_tip
            self.git('worktree', 'add', '-q', '-b', branch, str(path), tip)
        else:
            self.git('worktree', 'add', '-q', '-b', branch, str(path), *([start] if start else []))
            if commit:
                (path / f'{name}.txt').write_text(name)
                self.git('add', '.', cwd=path)
                self.git('commit', '-q', '-m', name, cwd=path)
            tip = self.git('rev-parse', 'HEAD', cwd=path)
        if record:
            self.entries.append({'issue': issue, 'path': str(path), 'branch': branch, 'ownership': ['src']})
            self.authorize()
        return path, branch, tip

    def on_template_main(self):
        """The main checkout still on main, at the template's commit (read from the files, without a Git process)."""
        dot = self.root / '.git'
        try:
            head = (dot / 'HEAD').read_text(encoding='utf-8').strip()
            ref = (dot / 'refs' / 'heads' / 'main').read_text(encoding='utf-8').strip()
        except OSError:
            return False
        return head == 'ref: refs/heads/main' and ref == self.main_tip

    def plan(self, branches=None, issues='12', base=None, worktrees=(), gh=None, default='main', integrations=()):
        gh = gh or FakeGh(branches, default)
        result = cleanup.run('plan', self.config, self.root, issues, base, worktrees, (), gh, integrations=integrations)
        self.assertEqual(gh.violations, [])
        return result, gh

    def only(self, result):
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual((len(result['candidates']), len(result['excluded'])), (1, 0), result)
        return result['candidates'][0]

    def reasons(self, result):
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(result['candidates'], [], result['candidates'])
        return [e['reasons'] for e in result['excluded']]


class SliceWorktreeTests(CleanupCase):
    """Issue 31, S3: a worktree de uma CA (entrada com `slice` na autorização) pode ir embora sem PR, quando a branch
    dela já está na branch da issue, não foi enviada e não tem PR; antes disso, fica."""

    def slice_worktree(self, name, slice_id, start, commit=True):
        path, branch = self.base / name, f'claude/{name}'
        self.git('worktree', 'add', '-q', '-b', branch, str(path), start)
        if commit:
            (path / f'{name}.txt').write_text(name)
            self.git('add', '.', cwd=path)
            self.git('commit', '-q', '-m', name, cwd=path)
        self.entries.append({'issue': 12, 'path': str(path), 'branch': branch, 'slice': slice_id, 'ownership': ['src']})
        self.authorize()
        return path, branch, self.git('rev-parse', 'HEAD', cwd=path)

    def test_a_slice_freshly_cut_with_nothing_of_its_own_is_not_offered_as_merged(self):
        _, issue_branch, _ = self.worktree('issue-12')
        _, s1_branch, _ = self.slice_worktree('issue-12-s1', 'S1', issue_branch, commit=False)
        result, _ = self.plan({issue_branch: {'heads': []}, s1_branch: {'heads': []}})
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}[s1_branch], ['slice_not_in_issue_branch'])

    def test_an_entry_with_slice_that_points_at_the_issue_branch_is_never_offered(self):
        issue_path, issue_branch, _ = self.worktree('issue-12', record=False)
        self.entries.append({'issue': 12, 'path': str(issue_path), 'branch': issue_branch, 'slice': 'S9', 'ownership': ['src']})
        self.entries.append({'issue': 12, 'path': str(issue_path), 'branch': issue_branch, 'ownership': ['src']})
        self.authorize()
        result, _ = self.plan({issue_branch: {'heads': []}})
        self.assertEqual(result['candidates'], [])
        self.assertEqual([e['reasons'] for e in result['excluded']], [['slice_is_issue_branch']])

    def test_when_the_issue_branch_is_gone_the_slice_is_judged_against_the_base(self):
        issue_path, issue_branch, _ = self.worktree('issue-12')
        s1_path, s1_branch, s1_tip = self.slice_worktree('issue-12-s1', 'S1', issue_branch)
        self.git('merge', '-q', '--no-ff', '-m', 's1', s1_branch, cwd=issue_path)
        self.git('worktree', 'remove', str(issue_path))
        self.git('branch', '-D', issue_branch)
        result, _ = self.plan({s1_branch: {'heads': []}})
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}, {s1_branch: ['slice_issue_branch_unknown']})
        self.git('merge', '-q', '--no-ff', '-m', 'issue', s1_tip)   # the base (main, checked out in the root) now holds the slice
        result, _ = self.plan({s1_branch: {'heads': []}})
        entry = self.only(result)
        self.assertEqual((entry['branch'], entry['cautions']), (s1_branch, ['slice_merged_into_issue_branch']))

    def test_the_slices_of_an_issue_come_before_the_issue_in_the_candidates(self):
        issue_path, issue_branch, _ = self.worktree('issue-12')
        _, s1_branch, _ = self.slice_worktree('issue-12-s1', 'S1', issue_branch)
        self.git('merge', '-q', '--no-ff', '-m', 's1', s1_branch, cwd=issue_path)
        issue_tip = self.git('rev-parse', 'HEAD', cwd=issue_path)
        result, _ = self.plan({issue_branch: merged(issue_tip), s1_branch: {'heads': []}})
        self.assertEqual([(c['branch'], c['slice']) for c in result['candidates']], [(s1_branch, 'S1'), (issue_branch, None)])

    def test_a_slice_branch_merged_into_the_issue_branch_can_go_without_a_pull_request(self):
        issue_path, issue_branch, _ = self.worktree('issue-12')
        _, s1_branch, _ = self.slice_worktree('issue-12-s1', 'S1', issue_branch)
        self.git('merge', '-q', '--no-ff', '-m', 's1', s1_branch, cwd=issue_path)
        result, _ = self.plan({issue_branch: {'heads': []}, s1_branch: {'heads': []}})
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}, {issue_branch: ['no_merged_pr']})
        entry = {c['branch']: c for c in result['candidates']}[s1_branch]
        self.assertEqual((entry['issue'], entry['cautions'], entry['ask'], entry['pullRequests']),
                         (12, ['slice_merged_into_issue_branch'], False, []))
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])

    def test_a_slice_still_outside_the_issue_branch_pushed_or_with_a_pull_request_stays(self):
        issue_path, issue_branch, _ = self.worktree('issue-12')
        _, s1_branch, s1_tip = self.slice_worktree('issue-12-s1', 'S1', issue_branch)
        result, _ = self.plan({issue_branch: {'heads': []}, s1_branch: {'heads': []}})
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}[s1_branch], ['slice_not_in_issue_branch'])
        self.git('merge', '-q', '--no-ff', '-m', 's1', s1_branch, cwd=issue_path)
        for info, reason in (({'heads': [pull(9, oid=s1_tip)]}, 'slice_has_pull_request'),
                             ({'heads': [], 'remote': s1_tip}, 'slice_pushed')):
            with self.subTest(reason=reason):
                result, _ = self.plan({issue_branch: {'heads': []}, s1_branch: info})
                self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}[s1_branch], [reason])

    def test_a_slice_whose_issue_worktree_is_not_in_the_authorization_cannot_be_judged(self):
        self.git('branch', 'claude/issue-12')
        _, s1_branch, _ = self.slice_worktree('issue-12-s1', 'S1', 'claude/issue-12')
        result, _ = self.plan({s1_branch: {'heads': []}})
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}[s1_branch], ['slice_issue_branch_unknown'])


class RemovableTests(CleanupCase):
    def test_a_merged_clean_worktree_comes_with_the_commands_in_the_order_to_run_them(self):
        path, branch, tip = self.worktree('wt12')
        result, _ = self.plan({branch: merged(tip)})
        entry = self.only(result)
        self.assertFalse(result['ask'])   # the cleanup of merged work asks nothing
        self.assertEqual((entry['issue'], entry['branch'], entry['tip'], entry['pullRequests']), (12, branch, tip, [7]))
        self.assertEqual((entry['removeWorktree'], entry['ask'], entry['cautions']), (True, False, []))
        argvs = [c['argv'] for c in entry['commands']]
        self.assertEqual([a[:2] for a in argvs], [['git', '-C']] * 2)
        self.assertEqual({cleanup.norm(a[2]) for a in argvs}, {cleanup.norm(self.root)})   # always from the main worktree
        self.assertEqual(argvs[0][3:5], ['worktree', 'remove'])
        self.assertEqual(cleanup.norm(argvs[0][5]), cleanup.norm(path))
        self.assertEqual(argvs[1][3:], ['branch', '-D', branch])
        prune = {'kind': 'fetch_prune', 'item': None, 'argv': ['git', '-C', argvs[0][2], 'fetch', '--prune', 'origin']}
        self.assertEqual(result['commands'], [prune] + entry['commands'])

    def test_nothing_is_ever_removed_by_the_plan_and_no_command_forces_anything(self):
        path, branch, tip = self.worktree('wt12')
        result, gh = self.plan({branch: merged(tip)})
        self.assertTrue(path.is_dir())
        self.assertIn(branch, self.git('branch', '--list', branch))
        for command in self.only(result)['commands']:
            self.assertNotIn('--force', command['argv'])
            self.assertNotIn('-f', command['argv'])
        self.assertTrue(all(call[:2] == ['api', 'graphql'] for call in gh.calls))

    def test_the_commands_really_work_and_verify_then_sees_everything_gone(self):
        path, branch, tip = self.worktree('wt12')
        result, _ = self.plan({branch: merged(tip)})
        entry = self.only(result)
        before = cleanup.run('verify', self.config, self.root, None, None, [str(path)], [branch], FakeGh({branch: merged(tip)}))
        self.assertFalse(before['ok'])
        self.assertEqual(before['exitCode'], 1)
        self.assertEqual([e['gone'] for e in before['entries']], [False, False])
        for command in entry['commands']:
            subprocess.run(command['argv'], check=True, capture_output=True)
        after = cleanup.run('verify', self.config, self.root, None, None, [str(path)], [branch], FakeGh())
        self.assertTrue(after['ok'], after)
        self.assertEqual([e['gone'] for e in after['entries']], [True, True])

    def test_the_remote_branch_is_never_touched_whatever_github_says_of_it(self):
        path, branch, tip = self.worktree('wt12')
        for remote in (None, tip, 'a' * 40):
            with self.subTest(remote=remote):
                result, _ = self.plan({branch: merged(tip, remote=remote)})
                entry = self.only(result)
                self.assertEqual(entry['cautions'], [])
                self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])
                self.assertNotIn('push', [a for c in result['commands'] for a in c['argv']])

    def test_records_kept_inside_the_worktree_are_copied_to_the_main_before_it_is_removed(self):
        path, branch, tip = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('evidence')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual((entry['cautions'], entry['ask']), (['frontlights_records'], False))
        self.assertEqual([c['kind'] for c in entry['commands']], ['copy_records', 'remove_worktree', 'delete_branch'])
        self.assertEqual(cleanup.norm(entry['recordsTo']),
                         cleanup.norm(self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / f'wt12-{tip[:7]}'))

    def test_a_squash_merged_branch_is_removable_because_its_tip_is_the_head_of_the_merged_pull_request(self):
        path, branch, tip = self.worktree('wt12')
        entry = self.only(self.plan({branch: merged(tip, merged_at=LATE)})[0])
        self.assertIn('-D', entry['commands'][1]['argv'])   # Git calls it unmerged; GitHub says its head was merged

    def test_a_branch_whose_worktree_is_already_gone_is_deleted_alone(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'remove', str(path))
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual((entry['removeWorktree'], entry['path'], [c['kind'] for c in entry['commands']]),
                         (False, None, ['delete_branch']))

    def test_what_is_already_gone_is_counted_and_asks_nothing(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'remove', str(path))
        self.git('branch', '-D', branch)
        result, _ = self.plan({})
        self.assertEqual((result['alreadyClean'], result['candidates'], result['excluded'], result['ask']), (1, [], [], False))

    def test_several_issues_are_ordered_by_number_and_a_hand_named_worktree_comes_last(self):
        a, branch_a, tip_a = self.worktree('wt-a', issue=13)
        b, branch_b, tip_b = self.worktree('wt-b', issue=12)
        c, branch_c, tip_c = self.worktree('wt-c', record=False)
        result, _ = self.plan({branch_a: merged(tip_a), branch_b: merged(tip_b), branch_c: merged(tip_c)},
                              issues='12,13', worktrees=[str(c)])
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual([(e['issue'], e['branch']) for e in result['candidates']],
                         [(12, branch_b), (13, branch_a), (None, branch_c)])

    def test_only_the_worktrees_of_the_named_issues_are_looked_at(self):
        path, branch, tip = self.worktree('wt12', issue=12)
        result, _ = self.plan({branch: merged(tip)}, issues='99')
        self.assertEqual((result['candidates'], result['excluded'], result['ask']), ([], [], False))
        self.assertIn('nothing to clean', result['message'])


class IgnoredAndOriginTests(CleanupCase):
    def ignore(self, *patterns):
        with open(self.root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('\n'.join(patterns) + '\n')

    def test_ignored_files_go_away_with_the_worktree_so_they_are_named_and_a_secret_among_them_asks(self):
        self.ignore('*.env', 'node_modules/')
        path, branch, tip = self.worktree('wt12')
        (path / 'secret.env').write_text('TOKEN=1')
        (path / 'node_modules').mkdir()
        (path / 'node_modules' / 'x.js').write_text('x')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(entry['cautions'], ['ignored_files'])
        self.assertEqual((entry['ignoredCount'], sorted(entry['ignored'])), (2, ['node_modules/', 'secret.env']))
        self.assertEqual((entry['ask'], entry['askIgnored']), (True, ['secret.env']))
        self.assertEqual([c['kind'] for c in entry['commands']][0], 'remove_worktree')

    def test_the_frontlights_folder_has_its_own_caution_and_is_not_listed_as_an_ignored_file(self):
        path, branch, tip = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('evidence')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(entry['cautions'], ['frontlights_records'])
        self.assertNotIn('ignored', entry)

    def test_a_worktree_with_nothing_ignored_has_no_such_caution(self):
        path, branch, tip = self.worktree('wt12')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertNotIn('ignored_files', entry['cautions'])
        self.assertNotIn('ignoredCount', entry)

    def test_without_an_origin_there_is_nothing_to_prune(self):
        path, branch, tip = self.worktree('wt12')
        self.git('remote', 'remove', 'origin')
        result, _ = self.plan({branch: merged(tip)})
        self.assertEqual([c['kind'] for c in result['commands']], ['remove_worktree', 'delete_branch'])

    def test_ignored_names_come_unquoted_even_with_spaces_and_accents(self):
        self.ignore('*.sqlite')
        path, branch, tip = self.worktree('wt12')
        (path / 'dir with space').mkdir()
        (path / 'dir with space' / 'a.sqlite').write_text('x')
        (path / 'a\u00e7\u00e3o.sqlite').write_text('x')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(sorted(entry['ignored']), sorted(['dir with space/a.sqlite', 'a\u00e7\u00e3o.sqlite']))

    def test_the_plan_does_not_refresh_the_index_of_a_worktree(self):
        path, branch, tip = self.worktree('wt12')
        index = Path(self.git('rev-parse', '--path-format=absolute', '--git-path', 'index', cwd=path))

        def touch():
            later = index.stat().st_mtime + 50
            os.utime(path / 'wt12.txt', (later, later))      # same content, newer stamp: git would refresh the index
        touch()
        before = index.stat().st_mtime_ns
        self.git('status', '--porcelain', cwd=path)
        if index.stat().st_mtime_ns == before:
            self.skipTest('this git does not rewrite the index on status, so there is nothing to guard against')
        touch()
        before = index.stat().st_mtime_ns
        self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(index.stat().st_mtime_ns, before)

    def test_the_questions_asked_of_github_are_the_ones_the_rules_need(self):
        path, branch, tip = self.worktree('wt12')
        _, gh = self.plan({branch: merged(tip)})
        asked = ' '.join(gh.queries())
        self.assertIn(f'pullRequests(headRefName: "{branch}", first: 20, states: [OPEN, MERGED, CLOSED])', asked)
        self.assertIn(f'pullRequests(baseRefName: "{branch}", first: 1, states: OPEN)', asked)
        self.assertIn(f'ref(qualifiedName: "refs/heads/{branch}")', asked)


class IntegrationTests(CleanupCase):
    """The local-only worktree where a family was integrated before its pull requests."""

    def family(self):
        a_path, a, a_tip = self.worktree('wt-a', issue=12)
        b_path, b, b_tip = self.worktree('wt-b', issue=13)
        integ = self.base / 'integ'
        self.git('worktree', 'add', '-q', '-b', 'claude/integ', str(integ), 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'a', a, cwd=integ)
        self.git('merge', '-q', '--no-ff', '-m', 'b', b, cwd=integ)
        info = {a: merged(a_tip, number=7), b: merged(b_tip, number=8), 'claude/integ': {'heads': []}}
        return integ, info, (a_tip, b_tip)

    def test_an_integration_worktree_that_only_merged_delivered_branches_can_go_last(self):
        integ, info, _ = self.family()
        result, _ = self.plan(info, issues='12,13', integrations=[str(integ)])
        self.assertEqual(len(result['candidates']), 3, result)
        last = result['candidates'][-1]
        self.assertEqual((last['issue'], last['branch'], last['cautions'], last['ask']),
                         (None, 'claude/integ', ['local_only_integration'], False))
        self.assertEqual([c['kind'] for c in last['commands']], ['remove_worktree', 'delete_branch'])

    def test_named_as_an_ordinary_worktree_it_needs_a_pull_request_like_any_other(self):
        integ, info, _ = self.family()
        result, _ = self.plan(info, issues='12,13', worktrees=[str(integ)])
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}['claude/integ'], ['no_merged_pr'])

    def test_a_commit_of_its_own_a_member_that_never_merged_a_push_or_a_pull_request_keep_it(self):
        integ, info, (a_tip, b_tip) = self.family()
        (integ / 'extra.txt').write_text('a fix made in the wrong place')
        self.git('add', '.', cwd=integ)
        self.git('commit', '-q', '-m', 'extra', cwd=integ)
        result, _ = self.plan(info, issues='12,13', integrations=[str(integ)])
        self.assertEqual([e['reasons'] for e in result['excluded']], [['integration_has_unique_commits']])
        self.git('reset', '-q', '--hard', 'HEAD~1', cwd=integ)
        undelivered = dict(info)
        undelivered['claude/wt-b'] = {'heads': [pull(8, 'OPEN', oid=b_tip)], 'remote': b_tip}
        result, _ = self.plan(undelivered, issues='12,13', integrations=[str(integ)])
        reasons = {e['branch']: e['reasons'] for e in result['excluded']}
        self.assertEqual(reasons['claude/wt-b'], ['open_pr', 'no_merged_pr'])
        self.assertEqual(reasons['claude/integ'], ['integration_has_unique_commits'])
        for change, reason in (({'heads': [pull(9, oid='1' * 40)]}, 'integration_has_pull_request'),
                               ({'heads': [], 'remote': 'e' * 40}, 'integration_pushed'),
                               ({'heads': [], 'dependents': 1}, 'open_dependents')):
            with self.subTest(reason=reason):
                result, _ = self.plan({**info, 'claude/integ': change}, issues='12,13', integrations=[str(integ)])
                self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}['claude/integ'], [reason])

    def test_a_clean_merge_of_two_members_that_touch_different_hunks_of_one_file_stays_offered(self):
        (self.root / 'shared.txt').write_text(''.join(f'line {n}\n' for n in range(1, 31)))
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'shared')
        a_path, a, _ = self.worktree('wt-a', issue=12)
        b_path, b, _ = self.worktree('wt-b', issue=13)
        for path, number in ((a_path, 2), (b_path, 29)):
            lines = (path / 'shared.txt').read_text().splitlines(keepends=True)
            lines[number - 1] = f'edited {number}\n'
            (path / 'shared.txt').write_text(''.join(lines))
            self.git('add', '.', cwd=path)
            self.git('commit', '-q', '-m', f'edit {number}', cwd=path)
        a_tip, b_tip = (self.git('rev-parse', 'HEAD', cwd=p) for p in (a_path, b_path))
        integ = self.base / 'integ'
        self.git('worktree', 'add', '-q', '-b', 'claude/integ', str(integ), 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'a', a, cwd=integ)
        self.git('merge', '-q', '--no-ff', '-m', 'b', b, cwd=integ)
        info = {a: merged(a_tip, number=7), b: merged(b_tip, number=8), 'claude/integ': {'heads': []}}
        result, _ = self.plan(info, issues='12,13', integrations=[str(integ)])
        self.assertEqual([c['branch'] for c in result['candidates']], [a, b, 'claude/integ'])

    def test_a_diff_setting_of_the_user_cannot_hide_what_an_evil_merge_changed(self):
        (self.root / '.gitattributes').write_text('*.doc diff=hide\n')
        (self.root / 'x.doc').write_text('v0')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'attributes and a document')
        self.git('config', 'diff.hide.textconv', 'echo same #')   # every version of a .doc prints the same text; the shell drops the file name
        integ, info, _ = self.family()
        (integ / 'x.doc').write_text('v2, changed inside the merge')
        self.git('add', '.', cwd=integ)
        self.git('commit', '-q', '--amend', '--no-edit', cwd=integ)
        self.stays_for_its_own_content(integ, info)

    def stays_for_its_own_content(self, integ, info):
        result, _ = self.plan(info, issues='12,13', integrations=[str(integ)])
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}, {'claude/integ': ['integration_has_unique_commits']})

    def test_a_merge_amended_with_a_file_is_content_of_its_own(self):
        integ, info, _ = self.family()
        (integ / 'resolved.txt').write_text('slipped into the last merge')
        self.git('add', '.', cwd=integ)
        self.git('commit', '-q', '--amend', '--no-edit', cwd=integ)
        self.stays_for_its_own_content(integ, info)

    def test_a_conflict_resolved_by_hand_in_the_integration_merge_is_content_of_its_own(self):
        a_path, a, _ = self.worktree('wt-a', issue=12)
        b_path, b, _ = self.worktree('wt-b', issue=13)
        for path, text in ((a_path, 'from a\n'), (b_path, 'from b\n')):
            (path / 'shared.txt').write_text(text)
            self.git('add', '.', cwd=path)
            self.git('commit', '-q', '-m', 'shared', cwd=path)
        a_tip, b_tip = (self.git('rev-parse', 'HEAD', cwd=p) for p in (a_path, b_path))
        integ = self.base / 'integ'
        self.git('worktree', 'add', '-q', '-b', 'claude/integ', str(integ), 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'a', a, cwd=integ)
        subprocess.run(['git', '-C', str(integ), 'merge', '--no-ff', '-m', 'b', b], capture_output=True)   # conflicts on purpose
        (integ / 'shared.txt').write_text('from a and b, resolved by hand\n')
        self.git('add', '.', cwd=integ)
        self.git('commit', '-q', '-m', 'resolved', cwd=integ)
        self.stays_for_its_own_content(integ, {a: merged(a_tip, number=7), b: merged(b_tip, number=8), 'claude/integ': {'heads': []}})

    def test_a_failing_log_is_not_read_as_nothing_of_its_own(self):
        integ, info, _ = self.family()
        tip = self.git('rev-parse', 'HEAD', cwd=integ)
        ctx = {'root': str(self.root), 'base': 'main', 'delivered': set()}
        real = cleanup.git

        def failing(root, *args):
            return (128, '') if args[:1] == ('log',) else real(root, *args)
        with patch.object(cleanup, 'git', failing):
            self.assertIsNone(cleanup.unique_commits(ctx, tip))
        self.assertTrue(cleanup.unique_commits(ctx, tip))   # nothing delivered here, so the members' commits are its own

    def test_naming_an_authorized_path_as_the_integration_worktree_judges_it_as_one(self):
        integ, info, _ = self.family()
        self.entries.append({'issue': 14, 'path': str(integ), 'branch': 'claude/integ'})
        self.authorize()
        result, _ = self.plan(info, issues='12,13,14', integrations=[str(integ)])
        mine = [c for c in result['candidates'] if c['branch'] == 'claude/integ']
        self.assertEqual((len(mine), mine[0]['issue'], mine[0]['cautions']), (1, 14, ['local_only_integration']))

    def test_without_any_delivered_branch_its_commits_are_not_covered(self):
        integ, _, _ = self.family()
        result, _ = self.plan({'claude/integ': {'heads': []}}, issues='99', integrations=[str(integ)])
        self.assertEqual([e['reasons'] for e in result['excluded']], [['integration_has_unique_commits']])

    def test_an_integration_worktree_with_uncommitted_changes_stays_like_any_other(self):
        integ, info, _ = self.family()
        (integ / 'scratch.txt').write_text('x')
        result, _ = self.plan(info, issues='12,13', integrations=[str(integ)])
        self.assertEqual({e['branch']: e['reasons'] for e in result['excluded']}['claude/integ'], ['uncommitted_changes'])


class MoreStayTests(CleanupCase):
    def test_a_name_below_a_protected_one_is_protected_too(self):
        path, branch, tip = self.worktree('wt12')
        self.protected = ['claude']
        self.authorize()
        self.assertEqual(self.reasons(self.plan({branch: merged(tip)})[0]), [['protected_branch']])

    def test_a_subfolder_of_the_worktree_is_still_the_folder_the_session_stands_in(self):
        path, branch, tip = self.worktree('wt12')
        (path / 'sub').mkdir()
        before = os.getcwd()
        os.chdir(path / 'sub')
        try:
            result, _ = self.plan({branch: merged(tip)})
        finally:
            os.chdir(before)
        self.assertEqual(self.reasons(result), [['current_directory']])

    def test_a_locked_worktree_and_a_branch_checked_out_elsewhere_stay(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'lock', str(path))
        self.assertEqual(self.reasons(self.plan({branch: merged(tip)})[0]), [['locked_worktree']])
        self.git('worktree', 'unlock', str(path))
        other, other_branch, other_tip = self.worktree('wt-b', issue=13, record=False)
        self.entries.append({'issue': 13, 'path': str(self.base / 'ghost'), 'branch': other_branch})   # its folder is gone
        self.authorize()
        result, _ = self.plan({other_branch: merged(other_tip)}, issues='13')
        self.assertEqual(self.reasons(result), [['checked_out_elsewhere']])

    def test_a_hand_named_path_that_exists_nowhere_is_a_mistake_not_a_clean_project(self):
        result, _ = self.plan({}, issues='99', worktrees=[str(self.base / 'tpyo')])
        self.assertEqual((result['alreadyClean'], result['excluded'][0]['reasons']), (0, ['not_found']))

    def test_a_registered_worktree_whose_folder_was_deleted_by_hand_stays_and_is_not_gone(self):
        path, branch, tip = self.worktree('wt12')
        shutil.rmtree(path)
        reasons = self.reasons(self.plan({branch: merged(tip)})[0])
        self.assertEqual(reasons, [['path_missing', 'unreadable_status']])   # nothing to run `git status` in
        verify = cleanup.run('verify', self.config, self.root, None, None, [str(path)], (), FakeGh())
        self.assertEqual((verify['ok'], verify['entries'][0]['gone']), (False, False))

    def test_the_authorized_branch_name_is_only_a_hint_the_real_branch_wins(self):
        path, branch, tip = self.worktree('wt12')
        self.entries[0]['branch'] = 'claude/old-name'
        self.authorize()
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual((entry['branch'], entry['cautions']), (branch, ['branch_differs_from_authorization']))

    def test_verify_reads_only_the_local_branch_the_remote_one_is_githubs(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'remove', str(path))
        self.git('branch', '-D', branch)
        gh = FakeGh({branch: {'remote': tip}})
        result = cleanup.run('verify', self.config, self.root, None, None, (), [branch], gh)
        self.assertEqual((result['ok'], result['entries'][0]['gone'], gh.calls), (True, True, []))


class ChainTests(CleanupCase):
    """How far a stacked branch is followed on its way to the approved base."""

    def chain(self, branch, tip, length, last_base='main', cycle=False, bad_oid=False):
        info = {branch: {'heads': [pull(50, base='claude/p1', oid=tip, merged_at='2026-10-06T12:00:00Z')], 'remote': tip}}
        for i in range(1, length + 1):
            base = f'claude/p{i + 1}' if i < length else last_base
            if cycle and i == length:
                base = 'claude/p1'
            info[f'claude/p{i}'] = {'heads': [pull(50 + i, base=base, oid='zzz' if bad_oid else tip, merged_at=f'2026-10-06T12:{i:02d}:00Z')]}
        return info

    def test_a_short_chain_reaches_the_base(self):
        path, branch, tip = self.worktree('wt12')
        self.assertEqual(self.only(self.plan(self.chain(branch, tip, 3))[0])['issue'], 12)

    def test_a_chain_longer_than_the_cap_a_cycle_and_a_parent_that_never_reached_the_base_stay(self):
        path, branch, tip = self.worktree('wt12')
        for name, kwargs in (('too long', dict(length=cleanup.MAX_CHAIN + 3)), ('cycle', dict(length=3, cycle=True)),
                             ('never reached', dict(length=2, last_base='claude/nowhere')),
                             ('a head that is no commit id', dict(length=2, bad_oid=True))):
            with self.subTest(case=name):
                self.assertEqual(self.reasons(self.plan(self.chain(branch, tip, **kwargs))[0]), [['merged_into_other_branch']])


class StayTests(CleanupCase):
    def test_uncommitted_changes_of_any_kind_keep_the_worktree(self):
        path, branch, tip = self.worktree('wt12')
        info = {branch: merged(tip)}
        (path / 'wt12.txt').write_text('edited')
        self.assertEqual(self.reasons(self.plan(info)[0]), [['uncommitted_changes']])
        self.git('checkout', '-q', '--', 'wt12.txt', cwd=path)
        (path / 'new.txt').write_text('untracked')
        self.assertEqual(self.reasons(self.plan(info)[0]), [['uncommitted_changes']])

    def test_a_commit_the_merged_pull_request_does_not_have_keeps_it(self):
        path, branch, tip = self.worktree('wt12')
        (path / 'later.txt').write_text('after the merge')
        self.git('add', '.', cwd=path)
        self.git('commit', '-q', '-m', 'later', cwd=path)
        self.assertEqual(self.reasons(self.plan({branch: merged(tip)})[0]), [['newer_than_merged_pr']])

    def test_an_open_pull_request_a_missing_one_or_a_closed_one_keep_it(self):
        path, branch, tip = self.worktree('wt12')
        cases = {'open': ({'heads': [pull(7, 'OPEN', oid=tip)], 'remote': tip}, 'open_pr'),
                 'none': ({'heads': [], 'remote': tip}, 'no_merged_pr'),
                 'closed': ({'heads': [pull(7, 'CLOSED', oid=tip)], 'remote': tip}, 'no_merged_pr')}
        for name, (info, reason) in cases.items():
            with self.subTest(case=name):
                self.assertIn(reason, self.reasons(self.plan({branch: info})[0])[0])

    def test_a_pull_request_open_on_top_of_the_branch_keeps_it(self):
        path, branch, tip = self.worktree('wt12')
        info = merged(tip)
        info['dependents'] = 1
        self.assertEqual(self.reasons(self.plan({branch: info})[0]), [['open_dependents']])

    def test_more_pull_requests_than_one_page_cannot_be_judged(self):
        path, branch, tip = self.worktree('wt12')
        info = merged(tip)
        info['total'] = 30
        self.assertEqual(self.reasons(self.plan({branch: info})[0]), [['pull_requests_unreadable']])

    def test_merged_into_another_branch_does_not_count_until_that_branch_reached_the_base(self):
        path, branch, tip = self.worktree('wt12')
        info = merged(tip, base='claude/other')
        self.assertEqual(self.reasons(self.plan({branch: info, 'claude/other': {'heads': []}})[0]), [['merged_into_other_branch']])

    def test_the_main_worktree_and_protected_branches_are_never_offered(self):
        self.entries.append({'issue': 12, 'path': str(self.root), 'branch': 'main'})
        self.authorize()
        self.assertEqual(self.reasons(self.plan({})[0]), [['main_worktree']])
        self.entries.clear()
        path, branch, tip = self.worktree('wt12')
        self.protected = ['claude/*']
        self.authorize()
        self.assertEqual(self.reasons(self.plan({branch: merged(tip)})[0]), [['protected_branch']])

    def test_a_release_branch_named_as_the_base_is_protected_too(self):
        path, _, _ = self.worktree('wt12', start='main')
        self.git('checkout', '-q', '-b', 'release/1.0', cwd=path)
        self.entries[0]['branch'] = 'release/1.0'
        self.authorize()
        result, _ = self.plan({}, base='release/1.0')
        self.assertEqual(self.reasons(result), [['protected_branch']])

    def test_the_folder_the_session_stands_in_is_never_removed_under_its_feet(self):
        path, branch, tip = self.worktree('wt12')
        before = os.getcwd()
        os.chdir(path)
        try:
            result, _ = self.plan({branch: merged(tip)})
        finally:
            os.chdir(before)
        self.assertEqual(self.reasons(result), [['current_directory']])

    def test_a_detached_worktree_and_a_folder_git_does_not_know_stay(self):
        detached = self.base / 'detached'
        self.git('worktree', 'add', '-q', '--detach', str(detached))
        stray = self.base / 'stray'
        stray.mkdir()
        result, _ = self.plan({}, worktrees=[str(detached), str(stray)], issues='12')
        self.assertEqual(sorted(sum(self.reasons(result), [])), ['detached_head', 'not_a_worktree'])

    def test_a_path_a_command_line_cannot_carry_is_never_typed(self):
        odd = self.base / 'wt$odd'
        self.git('worktree', 'add', '-q', '-b', 'claude/odd', str(odd))
        (odd / 'odd.txt').write_text('x')
        self.git('add', '.', cwd=odd)
        self.git('commit', '-q', '-m', 'odd', cwd=odd)
        tip = self.git('rev-parse', 'HEAD', cwd=odd)
        result, _ = self.plan({'claude/odd': merged(tip)}, worktrees=[str(odd)], issues='99')
        self.assertEqual(self.reasons(result), [['unsafe_path']])

    def test_a_branch_name_outside_the_plain_rule_is_never_put_in_a_query_or_a_command(self):
        path = self.base / 'weird'
        self.git('worktree', 'add', '-q', '-b', 'claude/we+ird', str(path))
        result, gh = self.plan({}, worktrees=[str(path)], issues='99')
        self.assertEqual(self.reasons(result), [['unsafe_branch']])
        self.assertFalse(any('we+ird' in argument for call in gh.calls for argument in call))

    def test_a_pull_request_that_cannot_be_read_keeps_the_worktree(self):
        path, branch, tip = self.worktree('wt12')

        class Broken:
            violations = []

            def __call__(self, argv):
                raise rs.Refusal('gh refused the GitHub read')
        result = cleanup.run('plan', self.config, self.root, '12', None, (), (), Broken())
        self.assertEqual((result['ok'], result['exitCode']), (False, 1))
        self.assertTrue(path.is_dir())


class UnsafeRootTests(CleanupCase):
    root_name = 'pro$j'

    def test_a_project_folder_a_command_line_cannot_carry_makes_every_command_unsafe(self):
        path, branch, tip = self.worktree('wt12')
        result, _ = self.plan({branch: merged(tip)})
        self.assertEqual(self.reasons(result), [['unsafe_path']])


class StackedTests(CleanupCase):
    """A child branch whose pull request went into its parent's branch, not into the base."""

    def stack(self):
        parent_path, parent, _ = self.worktree('parent', issue=10)
        child_path = self.base / 'child'
        self.git('worktree', 'add', '-q', '-b', 'claude/child', str(child_path), parent)
        (child_path / 'child.txt').write_text('child')
        self.git('add', '.', cwd=child_path)
        self.git('commit', '-q', '-m', 'child', cwd=child_path)
        child_tip = self.git('rev-parse', 'HEAD', cwd=child_path)
        self.entries.append({'issue': 11, 'path': str(child_path), 'branch': 'claude/child'})
        self.authorize()
        self.git('merge', '-q', '--no-ff', '-m', 'merge child', 'claude/child', cwd=parent_path)
        return parent, self.git('rev-parse', 'HEAD', cwd=parent_path), child_tip

    def child_info(self, child_tip, merged_at=EARLY):
        return {'heads': [pull(21, base='claude/parent', oid=child_tip, merged_at=merged_at)], 'remote': child_tip}

    def test_the_child_goes_once_its_parent_reached_the_base_after_it_and_contains_it(self):
        parent, parent_head, child_tip = self.stack()
        info = {'claude/child': self.child_info(child_tip),
                parent: {'heads': [pull(20, base='main', oid=parent_head, merged_at=LATE)], 'remote': parent_head}}
        result, _ = self.plan(info, issues='11')
        self.assertEqual(self.only(result)['branch'], 'claude/child')

    def test_a_parent_merged_before_the_child_did_not_carry_it(self):
        parent, parent_head, child_tip = self.stack()
        info = {'claude/child': self.child_info(child_tip, merged_at=LATE),
                parent: {'heads': [pull(20, base='main', oid=parent_head, merged_at=EARLY)]}}
        self.assertEqual(self.reasons(self.plan(info, issues='11')[0]), [['merged_into_other_branch']])

    def test_a_parent_head_that_does_not_contain_the_child_did_not_carry_it(self):
        parent, parent_head, child_tip = self.stack()
        first = self.git('rev-parse', 'main')
        info = {'claude/child': self.child_info(child_tip),
                parent: {'heads': [pull(20, base='main', oid=first, merged_at=LATE)]}}
        self.assertEqual(self.reasons(self.plan(info, issues='11')[0]), [['merged_into_other_branch']])

    def test_a_parent_head_this_clone_does_not_have_cannot_be_checked(self):
        parent, parent_head, child_tip = self.stack()
        info = {'claude/child': self.child_info(child_tip),
                parent: {'heads': [pull(20, base='main', oid='f' * 40, merged_at=LATE)]}}
        self.assertEqual(self.reasons(self.plan(info, issues='11')[0]), [['ancestry_unverifiable']])

    def test_a_parent_that_is_itself_stacked_on_a_branch_that_never_merged_stays(self):
        parent, parent_head, child_tip = self.stack()
        info = {'claude/child': self.child_info(child_tip),
                parent: {'heads': [pull(20, base='claude/grand', oid=parent_head, merged_at=LATE)]},
                'claude/grand': {'heads': []}}
        self.assertEqual(self.reasons(self.plan(info, issues='11')[0]), [['merged_into_other_branch']])


class RefusalTests(CleanupCase):
    def test_the_issues_are_required_and_must_be_numbers(self):
        for issues in (None, '', [], 'a', '0', '12,,13'):
            with self.subTest(issues=issues):
                result, gh = self.plan({}, issues=issues)
                self.assertFalse(result['ok'])
                self.assertEqual(gh.calls, [])

    def test_a_base_that_is_not_a_plain_branch_name_is_refused_before_any_read(self):
        for base in ('main; rm', 'a..b', '-x', '$HOME', 'a b'):
            with self.subTest(base=base):
                result, gh = self.plan({}, base=base)
                self.assertFalse(result['ok'])
                self.assertEqual(gh.calls, [])

    def test_the_base_is_the_default_branch_unless_named_and_must_be_known(self):
        path, branch, tip = self.worktree('wt12')
        result, _ = self.plan({branch: merged(tip)})
        self.assertEqual((result['expectedBase'], result['baseSource']), ('main', 'default_branch'))
        result, _ = self.plan({branch: merged(tip, base='release')}, base='release')
        self.assertEqual((result['expectedBase'], result['baseSource'], len(result['candidates'])), ('release', 'argument', 1))
        result, _ = self.plan({}, default=None)
        self.assertFalse(result['ok'])
        self.assertIn('--base', result['message'])

    def test_a_project_without_a_repository_or_outside_git_is_a_refusal(self):
        self.config.write_text(json.dumps({'repository': None}), encoding='utf-8')
        result, gh = self.plan({})
        self.assertFalse(result['ok'])
        self.assertEqual(gh.calls, [])
        self.config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')
        with tempfile.TemporaryDirectory() as outside:
            result = cleanup.run('plan', self.config, outside, '12', None, (), (), FakeGh())
        self.assertEqual((result['ok'], result['exitCode']), (False, 1))
        self.assertIn('Git repository', result['message'])

    def test_verify_needs_something_to_check_and_a_plain_branch(self):
        for worktrees, branches in (((), ()), ((), ('a b',))):
            with self.subTest(branches=branches):
                result = cleanup.run('verify', self.config, self.root, None, None, worktrees, branches, FakeGh())
                self.assertFalse(result['ok'])

    def test_an_unknown_operation_is_a_refusal(self):
        result = cleanup.run('frobnicate', self.config, self.root)
        self.assertEqual((result['ok'], result['exitCode']), (False, 1))


class CliTests(CleanupCase):
    def main(self, *argv, branches=None):
        gh = FakeGh(branches)
        out = io.StringIO()
        with patch.object(rs, 'gh_default', gh), contextlib.redirect_stdout(out):
            code = cleanup.main(list(argv))
        self.assertEqual(gh.violations, [])
        return code, out.getvalue(), gh

    def test_plan_prints_the_json_the_session_reads(self):
        path, branch, tip = self.worktree('wt12')
        code, out, _ = self.main('plan', '--config', str(self.config), '--root', str(self.root), '--issues', '12',
                                 branches={branch: merged(tip)})
        result = json.loads(out)
        self.assertEqual((code, result['ok'], len(result['candidates'])), (0, True, 1))
        self.assertTrue(out.isascii())
        self.assertTrue(out.startswith('{\n  "'))

    def test_verify_exits_1_while_something_is_still_there(self):
        path, branch, tip = self.worktree('wt12')
        code, out, _ = self.main('verify', '--config', str(self.config), '--root', str(self.root), '--worktree', str(path),
                                 '--branch', branch)
        self.assertEqual((code, json.loads(out)['ok']), (1, False))

    def archive(self, source, target):
        code, out, _ = self.main('archive', '--from', str(source), '--to', str(target))
        return code, json.loads(out)

    def records(self, folder):
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob('*')) if p.is_file()}

    def test_archive_again_after_the_removal_failed_is_ok_and_keeps_the_records(self):
        """Review r2 of issue 63 (R2-1): a round copies the records and `git worktree remove` fails; the next round
        offers the same worktree, tip and `recordsTo`. The second archive finds the same files and says so (exit 0),
        so the removal goes on; a copy that stopped half-way is completed."""
        path, _, _ = self.worktree('wt12')
        source = path / '.frontlights'
        (source / 'sub').mkdir(parents=True)
        (source / 'note.txt').write_text('evidence')
        (source / 'sub' / 'a.txt').write_text('slice')
        target = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / 'wt12-abc1234'
        code, first = self.archive(source, target)
        self.assertEqual((code, first['ok'], first['files']), (0, True, 2))
        code, second = self.archive(source, target)
        self.assertEqual((code, second['ok'], second['exitCode'], second['files']), (0, True, 0, 2))
        self.assertIn('already', second['message'])
        self.assertEqual(self.records(target), self.records(source))
        (target / 'sub' / 'a.txt').unlink()   # a copy that failed half-way
        code, third = self.archive(source, target)
        self.assertEqual((code, third['ok'], third['files']), (0, True, 2))
        self.assertEqual(self.records(target), self.records(source))

    def test_archive_refuses_a_destination_with_a_differing_or_extra_file_and_leaves_it(self):
        """Review r2 of issue 63 (R2-1): any file of the destination that differs from the source, or that the source
        does not have, is refused (exit 1), nothing copied, the destination untouched."""
        path, _, _ = self.worktree('wt12')
        source = path / '.frontlights'
        source.mkdir()
        (source / 'note.txt').write_text('evidence')
        (source / 'more.txt').write_text('more')
        for name, files in (('differs', {'note.txt': 'other'}), ('extra', {'note.txt': 'evidence', 'old.txt': 'old'})):
            with self.subTest(name):
                target = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / f'wt12-{name}'
                target.mkdir(parents=True)
                for file, text in files.items():
                    (target / file).write_text(text)
                before = self.records(target)
                code, result = self.archive(source, target)
                self.assertEqual((code, result['ok'], result['exitCode']), (1, False, 1))
                self.assertEqual(self.records(target), before)

    def junction(self, link, to):
        if os.name != 'nt':
            self.skipTest('junctions exist only on Windows')
        done = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(to)], capture_output=True, timeout=30)
        if done.returncode != 0:
            self.skipTest('mklink /J failed here')

    def test_archive_refuses_a_junction_in_the_destination_or_the_source_and_writes_nothing_outside(self):
        """Review r3 of issue 63 (R3-1): on Windows a junction is not a symlink, so a junction planted in the
        destination (or one of its parents, or the source) would let the copy write, or read, outside `.frontlights`.
        Each case is refused (exit 1) and the folder outside stays as it was."""
        path, _, _ = self.worktree('wt12')
        source = path / '.frontlights'
        (source / 'sub').mkdir(parents=True)
        (source / 'note.txt').write_text('evidence')
        (source / 'sub' / 'a.txt').write_text('slice')
        outside = Path(tempfile.mkdtemp(prefix='outside-'))
        self.addCleanup(shutil.rmtree, outside, True)
        worktrees = self.root / '.frontlights' / 'issues' / '12' / 'worktrees'
        worktrees.mkdir(parents=True)
        # inside the destination: `sub` leads outside, empty
        inner = worktrees / 'wt12-inner'
        inner.mkdir()
        self.junction(inner / 'sub', outside)
        code, result = self.archive(source, inner)
        self.assertEqual((code, result['ok'], result['exitCode']), (1, False, 1))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((inner / 'note.txt').exists())
        # inside the destination, with the same files as the source's `sub`
        (outside / 'a.txt').write_text('slice')
        code, result = self.archive(source, inner)
        self.assertEqual((code, result['ok']), (1, False))
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ['a.txt'])
        os.rmdir(inner / 'sub')
        (outside / 'a.txt').unlink()
        # the destination itself is a junction
        self.junction(worktrees / 'wt12-self', outside)
        code, result = self.archive(source, worktrees / 'wt12-self')
        self.assertEqual((code, result['ok']), (1, False))
        self.assertEqual(list(outside.iterdir()), [])
        # a parent of the destination is a junction
        self.junction(worktrees / 'parent', outside)
        code, result = self.archive(source, worktrees / 'parent' / 'wt12-x')
        self.assertEqual((code, result['ok']), (1, False))
        self.assertEqual(list(outside.iterdir()), [])
        # a junction in the source is refused rather than copied through
        (outside / 'secret.txt').write_text('not records')
        self.junction(source / 'link', outside)
        target = worktrees / 'wt12-source'
        code, result = self.archive(source, target)
        self.assertEqual((code, result['ok']), (1, False))
        self.assertFalse((target / 'link' / 'secret.txt').exists())

    def test_archive_completes_after_a_copy_interrupted_on_a_temporary_file(self):
        """Review r3 of issue 63 (R3-2): each file is copied to a temporary name and renamed into place, so a final
        file is never incomplete; a temporary file left by an interrupted run is removed and the next archive is ok."""
        path, _, _ = self.worktree('wt12')
        source = path / '.frontlights'
        (source / 'sub').mkdir(parents=True)
        (source / 'note.txt').write_text('evidence')
        (source / 'sub' / 'a.txt').write_text('slice, the whole of it')
        target = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / 'wt12-abc1234'
        (target / 'sub').mkdir(parents=True)
        (target / 'note.txt').write_text('evidence')
        (target / 'sub' / cleanup.archive_temp_name('a.txt')).write_text('slice, the')   # interrupted, truncated
        code, result = self.archive(source, target)
        self.assertEqual((code, result['ok'], result['files']), (0, True, 2))
        self.assertEqual(self.records(target), self.records(source))
        copied = []
        real_replace = os.replace

        def replace(src, dst):
            copied.append((Path(src).name, Path(dst).name))
            return real_replace(src, dst)
        fresh = target.parent / 'wt12-fresh'
        with patch.object(cleanup.os, 'replace', replace):
            code, result = self.archive(source, fresh)
        self.assertEqual((code, result['ok'], result['files']), (0, True, 2))
        self.assertIn((cleanup.archive_temp_name('a.txt'), 'a.txt'), copied)
        self.assertEqual(self.records(fresh), self.records(source))

    def test_archive_refuses_a_source_entry_named_like_the_temporary_file_and_copies_nothing(self):
        """Review r4 of issue 63 (R4-1, criterion P1): the source holds `a.txt` and `.a.txt.frontlights-archive-tmp`.
        Copied as they come, the second would be taken for the temporary file of the first and one record lost (or,
        were it a link leading outside, written through). It is refused (exit 1), nothing copied, the destination
        untouched; and the temporary file is created exclusively, so one already there is never written through."""
        path, _, _ = self.worktree('wt12')
        source = path / '.frontlights'
        source.mkdir()
        (source / 'a.txt').write_text('slice')
        (source / cleanup.archive_temp_name('a.txt')).write_text('another record')
        worktrees = self.root / '.frontlights' / 'issues' / '12' / 'worktrees'
        target = worktrees / 'wt12-abc1234'
        code, result = self.archive(source, target)
        self.assertEqual((code, result['ok'], result['exitCode']), (1, False, 1))
        self.assertFalse(target.exists())
        earlier = worktrees / 'wt12-earlier'
        earlier.mkdir(parents=True)
        (earlier / 'kept.txt').write_text('kept')
        (source / 'kept.txt').write_text('kept')
        code, result = self.archive(source, earlier)
        self.assertEqual((code, result['ok']), (1, False))
        self.assertEqual(self.records(earlier), {'kept.txt': b'kept'})
        # the temporary file is created exclusively: one already there (here a planted file) is not overwritten
        (source / cleanup.archive_temp_name('a.txt')).unlink()
        (source / 'kept.txt').unlink()
        destination = worktrees / 'wt12-busy'
        destination.mkdir()
        planted = destination / cleanup.archive_temp_name('a.txt')
        with self.assertRaises(FileExistsError):
            planted.write_text('planted')
            cleanup.copy_whole(str(source / 'a.txt'), str(destination / 'a.txt'))
        self.assertEqual(planted.read_text(), 'planted')
        self.assertFalse((destination / 'a.txt').exists())

    def test_usage_mistakes_are_json_refusals_too(self):
        for argv in ([], ['plan'], ['frobnicate', '--config', 'x'], ['plan', '--config', 'x', '--bogus'], ['verify', '--config']):
            with self.subTest(argv=argv):
                code, out, _ = self.main(*argv)
                result = json.loads(out)
                self.assertEqual((code, result['ok'], result['exitCode']), (1, False, 1))
                self.assertTrue(result['message'])

    def test_a_real_process_has_no_traceback_and_no_stderr(self):
        for argv in (['plan', '--config', str(self.config), '--root', str(self.root)], ['nonsense'],
                     ['verify', '--config', str(self.root / 'missing.json'), '--branch', 'x']):
            with self.subTest(argv=argv):
                done = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, encoding='utf-8',
                                      cwd=self.root, timeout=60)
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertEqual(done.stderr, '')
                self.assertEqual(json.loads(done.stdout)['exitCode'], 1)
                self.assertNotIn('Traceback', done.stdout)


class DeliveredWithoutPullRequestTests(CleanupCase):
    """Issue 32, S4: a branch da issue entra na main local por merge, sem PR própria. Sem nenhuma PR, ela pode ir
    embora quando a base aprovada (`origin/<base>` quando a ref remota existe, senão a local) já contém a ponta;
    fora da base, ou com uma PR fechada sem merge, continua `no_merged_pr`."""

    def delivered(self):
        """An issue worktree whose branch was merged into the base (main, checked out in the root)."""
        path, branch, tip = self.worktree('issue-12')
        self.git('merge', '-q', '--no-ff', '-m', 'issue 12', branch)
        return path, branch, tip

    def test_an_issue_branch_merged_into_the_base_goes_without_a_pull_request(self):
        path, branch, tip = self.delivered()
        result, _ = self.plan({branch: {'heads': []}})
        entry = self.only(result)
        self.assertEqual((entry['issue'], entry['branch'], entry['tip'], entry['pullRequests']), (12, branch, tip, []))
        self.assertEqual((entry['cautions'], entry['ask']), (['contained_in_base_without_pull_request'], False))
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])
        self.assertFalse(any('push' in c['argv'] for c in entry['commands']))

    def test_a_branch_pushed_under_the_old_flow_and_delivered_without_a_pull_request_leaves_its_remote_alone(self):
        path, branch, tip = self.delivered()
        for remote in ('a' * 40, tip):
            with self.subTest(remote=remote):
                entry = self.only(self.plan({branch: {'heads': [], 'remote': remote}})[0])
                self.assertEqual(entry['cautions'], ['contained_in_base_without_pull_request'])
                self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])

    def test_an_issue_branch_outside_the_base_still_needs_a_pull_request(self):
        path, branch, tip = self.worktree('issue-12')
        self.assertEqual(self.reasons(self.plan({branch: {'heads': []}})[0]), [['no_merged_pr']])

    def test_the_remote_tracking_base_is_the_one_that_counts_when_it_exists(self):
        before = self.git('rev-parse', 'main')
        path, branch, tip = self.delivered()
        self.git('update-ref', 'refs/remotes/origin/main', before)   # origin/main as of the last fetch: before the merge
        self.assertEqual(self.reasons(self.plan({branch: {'heads': []}})[0]), [['no_merged_pr']])
        self.git('update-ref', 'refs/remotes/origin/main', self.git('rev-parse', 'main'))
        entry = self.only(self.plan({branch: {'heads': []}})[0])
        self.assertEqual((entry['branch'], entry['cautions']), (branch, ['contained_in_base_without_pull_request']))

    def test_a_closed_pull_request_or_an_open_dependent_still_keeps_it(self):
        path, branch, tip = self.delivered()
        for name, info, reason in (('closed', {'heads': [pull(7, 'CLOSED', oid=tip)]}, 'no_merged_pr'),
                                   ('dependent', {'heads': [], 'dependents': 1}, 'open_dependents')):
            with self.subTest(case=name):
                self.assertEqual(self.reasons(self.plan({branch: info})[0]), [[reason]])

    def test_an_ancestry_git_cannot_tell_keeps_it(self):
        path, branch, tip = self.delivered()
        with patch.object(cleanup, 'is_ancestor', lambda *args: None):
            result, _ = self.plan({branch: {'heads': []}})
        self.assertEqual(self.reasons(result), [['ancestry_unverifiable']])


class MergedWorkTests(CleanupCase):
    """Issue 63, S1: a limpeza do trabalho mesclado roda sozinha e sem branch remota. Depois do merge da release, o
    plano traz `git fetch --prune`, a cópia dos registros de cada worktree para `.frontlights/issues/<n>/` antes de
    removê-la, a remoção das worktrees e das branches locais da issue, das slices e da release mesclada, e nenhum
    `git push origin --delete`; só pergunta quem tem arquivo ignorado fora de dependência ou build. O `origin` é um
    repositório nu local que faz o papel do GitHub (merge e exclusão automática da branch da release)."""

    RELEASE = 'claude/release-2026-10-20'

    def released(self):
        """An issue worktree with a slice merged into it, the issue merged into the local main, the release branch cut
        from main, pushed, merged on the origin and deleted there (GitHub's automatic deletion), and main pulled."""
        bare = self.base / 'origin.git'
        self.git('clone', '-q', '--bare', str(self.root), str(bare))
        self.git('remote', 'set-url', 'origin', str(bare))
        self.git('fetch', '-q', 'origin')
        issue_path, issue_branch, _ = self.worktree('issue-12')
        s1_path = self.base / 'issue-12-s1'
        s1_branch = 'claude/issue-12-s1'
        self.git('worktree', 'add', '-q', '-b', s1_branch, str(s1_path), issue_branch)
        (s1_path / 's1.txt').write_text('s1')
        self.git('add', '.', cwd=s1_path)
        self.git('commit', '-q', '-m', 's1', cwd=s1_path)
        self.entries.append({'issue': 12, 'path': str(s1_path), 'branch': s1_branch, 'slice': 'S1', 'ownership': ['src']})
        self.authorize()
        self.git('merge', '-q', '--no-ff', '-m', 's1', s1_branch, cwd=issue_path)
        for path, name in ((issue_path, 'review.json'), (s1_path, 'progress.json')):
            (path / '.frontlights' / 'issues' / '12').mkdir(parents=True)
            (path / '.frontlights' / 'issues' / '12' / name).write_text('{"evidence": true}', encoding='utf-8')
        self.git('merge', '-q', '--no-ff', '-m', 'issue 12', issue_branch)
        self.git('branch', self.RELEASE, 'main')
        self.git('push', '-q', '-u', 'origin', self.RELEASE)
        release_tip = self.git('rev-parse', self.RELEASE)
        self.git('update-ref', 'refs/heads/main', release_tip, cwd=bare)          # the merge of the release on GitHub
        self.git('update-ref', '-d', f'refs/heads/{self.RELEASE}', cwd=bare)      # its automatic deletion
        self.git('pull', '-q', '--ff-only', 'origin', 'main')
        info = {issue_branch: {'heads': []}, s1_branch: {'heads': []},
                self.RELEASE: {'heads': [pull(70, oid=release_tip)]}}
        return (issue_path, issue_branch), (s1_path, s1_branch), info

    def test_after_the_release_merge_the_plan_brings_the_whole_cleanup_in_order_and_verify_sees_it_done(self):
        (issue_path, issue_branch), (s1_path, s1_branch), info = self.released()
        result, _ = self.plan(info)
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(result['excluded'], [])
        self.assertFalse(result['ask'])
        main = cleanup.norm(self.root)
        kinds = [c['kind'] for c in result['commands']]
        self.assertEqual(kinds, ['fetch_prune', 'copy_records', 'remove_worktree', 'delete_branch',
                                 'copy_records', 'remove_worktree', 'delete_branch', 'delete_branch'])
        self.assertEqual(result['commands'][0]['argv'][3:], ['fetch', '--prune', 'origin'])
        branches = [c['argv'][-1] for c in result['commands'] if c['kind'] == 'delete_branch']
        self.assertEqual(branches, [s1_branch, issue_branch, self.RELEASE])
        removed = [cleanup.norm(c['argv'][-1]) for c in result['commands'] if c['kind'] == 'remove_worktree']
        self.assertEqual(removed, [cleanup.norm(s1_path), cleanup.norm(issue_path)])
        release = result['candidates'][-1]
        self.assertEqual((release['branch'], release['release'], release['removeWorktree'], release['cautions']),
                         (self.RELEASE, True, False, ['merged_release_branch']))
        flat_argv = [a for c in result['commands'] for a in c['argv']]
        self.assertNotIn('push', flat_argv)
        self.assertNotIn('--force', flat_argv)
        self.assertNotIn('-f', flat_argv)
        for command in result['commands']:
            if command['argv'][0] == 'git':
                self.assertEqual(cleanup.norm(command['argv'][2]), main)
            subprocess.run(command['argv'], check=True, capture_output=True)
        archive = self.root / '.frontlights' / 'issues' / '12' / 'worktrees'
        tips = {c['branch']: c['tip'] for c in result['candidates']}
        issue_records = archive / f"issue-12-{tips[issue_branch][:7]}"
        s1_records = archive / f"issue-12-s1-{tips[s1_branch][:7]}"
        self.assertEqual(json.loads((issue_records / 'issues' / '12' / 'review.json').read_text(encoding='utf-8')),
                         {'evidence': True})
        self.assertTrue((s1_records / 'issues' / '12' / 'progress.json').is_file())
        self.assertEqual(self.git('branch', '--list', '-r', f'origin/{self.RELEASE}'), '')   # pruned by the fetch
        after = cleanup.run('verify', self.config, self.root, None, None, [str(issue_path), str(s1_path)],
                            [issue_branch, s1_branch, self.RELEASE], FakeGh(),
                            records=[str(issue_records), str(s1_records)])
        self.assertTrue(after['ok'], after)
        self.assertEqual([e['kind'] for e in after['entries']], ['worktree'] * 2 + ['branch'] * 3 + ['records'] * 2)

    def test_each_command_names_the_item_it_belongs_to(self):
        """Review r1 of issue 63 (R1-3): every command of `commands` carries the branch of its candidate in `item`
        (null only for the fetch, which belongs to no item), so a failure skips the rest of that item."""
        _, _, info = self.released()
        result, _ = self.plan(info)
        self.assertEqual(result['commands'][0]['kind'], 'fetch_prune')
        self.assertIsNone(result['commands'][0]['item'])
        expected = [c['branch'] for c in result['candidates'] for _ in c['commands']]
        self.assertEqual([c['item'] for c in result['commands'][1:]], expected)
        for candidate in result['candidates']:
            with self.subTest(branch=candidate['branch']):
                self.assertEqual({c['item'] for c in candidate['commands']}, {candidate['branch']})

    def test_the_records_of_each_worktree_go_to_a_folder_of_their_own_tip(self):
        """Review r1 of issue 63 (R1-2): `recordsTo` carries the short tip of the worktree, so a later worktree of the
        same folder name never lands on records archived before."""
        (issue_path, issue_branch), _, info = self.released()
        result, _ = self.plan(info)
        entry = next(c for c in result['candidates'] if c['branch'] == issue_branch)
        expected = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / f"issue-12-{entry['tip'][:7]}"
        self.assertEqual(cleanup.norm(entry['recordsTo']), cleanup.norm(expected))
        copy = next(c for c in entry['commands'] if c['kind'] == 'copy_records')
        self.assertEqual(copy['argv'][-1], entry['recordsTo'])

    def test_archive_refuses_a_destination_that_already_holds_records(self):
        """Review r1 of issue 63 (R1-2): a destination that exists and is not empty is refused, nothing copied."""
        path, _, _ = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('new')
        target = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / 'wt12-abc1234'
        target.mkdir(parents=True)
        (target / 'note.txt').write_text('old')
        result = cleanup.run('archive', None, source=str(path / '.frontlights'), destination=str(target))
        self.assertEqual((result['ok'], result['exitCode']), (False, 1))
        self.assertEqual(((target / 'note.txt').read_text(), sorted(p.name for p in target.iterdir())), ('old', ['note.txt']))
        empty = target.parent / 'wt12-def5678'
        empty.mkdir()
        result = cleanup.run('archive', None, source=str(path / '.frontlights'), destination=str(empty))
        self.assertEqual((result['ok'], (empty / 'note.txt').read_text()), (True, 'new'))

    def test_archive_refuses_a_frontlights_folder_outside_the_main_worktree(self):
        """Review r1 of issue 63 (R1-6): the destination lies under the main worktree's `.frontlights`, the main
        worktree read from Git for the worktree of --from; a `.frontlights` elsewhere is refused."""
        path, _, _ = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('evidence')
        for target in (self.base / 'other' / '.frontlights' / 'issues' / '12', path / 'sub' / '.frontlights' / 'x',
                       self.root / 'sub' / '.frontlights' / 'x'):
            with self.subTest(target=str(target)):
                result = cleanup.run('archive', None, source=str(path / '.frontlights'), destination=str(target))
                self.assertEqual((result['ok'], result['exitCode']), (False, 1))
                self.assertFalse(target.exists())

    def test_archive_copies_only_a_frontlights_folder_into_a_frontlights_folder(self):
        path, _, _ = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('evidence')
        inside = self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / 'wt12'
        for source, target in ((path, inside), (path / '.frontlights', self.base / 'elsewhere'),
                               (path / '.frontlights', path / '.frontlights' / 'x')):
            with self.subTest(source=source.name, target=target.name):
                result = cleanup.run('archive', None, source=str(source), destination=str(target))
                self.assertEqual((result['ok'], result['exitCode']), (False, 1))
                self.assertFalse(inside.exists())
        result = cleanup.run('archive', None, source=str(path / '.frontlights'), destination=str(inside))
        self.assertEqual((result['ok'], result['files'], (inside / 'note.txt').read_text()), (True, 1, 'evidence'))

    def test_verify_says_records_that_were_not_copied(self):
        result = cleanup.run('verify', self.config, self.root, None, None, (), (), FakeGh(),
                             records=[str(self.root / '.frontlights' / 'issues' / '12' / 'worktrees' / 'nada')])
        self.assertEqual((result['ok'], result['exitCode'], result['entries'][0]['copied']), (False, 1, False))

    def test_only_ignored_files_besides_dependency_or_build_folders_make_a_candidate_ask(self):
        with open(self.root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('node_modules/\n__pycache__/\ndist/\n*.env\n')
        path, branch, tip = self.worktree('wt12')
        for folder in ('node_modules', '__pycache__', 'dist'):
            (path / folder).mkdir()
            (path / folder / 'x').write_text('x')
        result, _ = self.plan({branch: merged(tip)})
        entry = self.only(result)
        self.assertEqual((entry['ask'], result['ask']), (False, False))
        self.assertIn('remove_worktree', [c['kind'] for c in result['commands']])
        (path / 'secret.env').write_text('TOKEN=1')
        result, _ = self.plan({branch: merged(tip)})
        entry = self.only(result)
        self.assertEqual((entry['ask'], entry['askReason'], entry['askIgnored'], result['ask']),
                         (True, 'ignored_files_besides_dependencies', ['secret.env'], True))
        self.assertEqual([c['kind'] for c in result['commands']], ['fetch_prune'])   # asked first, run after a yes
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])

    def test_a_release_branch_not_yet_merged_or_checked_out_is_left_alone(self):
        self.git('branch', self.RELEASE, 'main')
        stray = self.base / 'rel'
        self.git('worktree', 'add', '-q', '-b', 'claude/release-2026-10-21', str(stray))
        (stray / 'r.txt').write_text('r')
        self.git('add', '.', cwd=stray)
        self.git('commit', '-q', '-m', 'r', cwd=stray)
        result, _ = self.plan({self.RELEASE: {'heads': [pull(70, 'OPEN', oid=self.main_tip)]}})
        self.assertEqual([c['branch'] for c in result['candidates']], [])
        self.assertNotIn('claude/release-2026-10-21', [e['branch'] for e in result['excluded']])


if __name__ == '__main__':
    unittest.main()
