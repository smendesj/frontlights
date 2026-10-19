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
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import cleanup
import roads as rs

SCRIPT = Path(cleanup.__file__)
REPO = 'OWNER/REPOSITORY'
EARLY = '2026-10-06T12:00:00Z'
LATE = '2026-10-06T13:00:00Z'


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

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / self.root_name
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.root / 'app.txt').write_text('one\n')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'first')
        self.git('remote', 'add', 'origin', f'https://github.com/{REPO}.git')
        (self.root / '.frontlights').mkdir()
        with open(self.root / '.git' / 'info' / 'exclude', 'a', encoding='utf-8') as exclude:
            exclude.write('/.frontlights/\n')
        self.config = self.root / '.frontlights' / 'config.json'
        self.config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')
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
        self.git('worktree', 'add', '-q', '-b', branch, str(path), *([start] if start else []))
        if commit:
            (path / f'{name}.txt').write_text(name)
            self.git('add', '.', cwd=path)
            self.git('commit', '-q', '-m', name, cwd=path)
        if record:
            self.entries.append({'issue': issue, 'path': str(path), 'branch': branch, 'ownership': ['src']})
            self.authorize()
        return path, branch, self.git('rev-parse', 'HEAD', cwd=path)

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
        self.assertEqual((entry['issue'], entry['cautions'], entry['deleteRemoteBranch'], entry['pullRequests']),
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
        self.assertTrue(result['ask'])
        self.assertEqual((entry['issue'], entry['branch'], entry['tip'], entry['pullRequests']), (12, branch, tip, [7]))
        self.assertEqual((entry['removeWorktree'], entry['deleteRemoteBranch'], entry['cautions']), (True, True, []))
        argvs = [c['argv'] for c in entry['commands']]
        self.assertEqual([a[:2] for a in argvs], [['git', '-C']] * 3)
        self.assertEqual({cleanup.norm(a[2]) for a in argvs}, {cleanup.norm(self.root)})   # always from the main worktree
        self.assertEqual(argvs[0][3:5], ['worktree', 'remove'])
        self.assertEqual(cleanup.norm(argvs[0][5]), cleanup.norm(path))
        self.assertEqual(argvs[1][3:], ['branch', '-D', branch])
        self.assertEqual(argvs[2][3:], ['push', 'origin', '--delete', branch])
        self.assertTrue(all(c['argv'][0] == 'git' for c in entry['commands']))

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
        for command in entry['commands'][:2]:   # the remote branch lives only on GitHub in this fixture
            subprocess.run(command['argv'], check=True, capture_output=True)
        after = cleanup.run('verify', self.config, self.root, None, None, [str(path)], [branch], FakeGh())
        self.assertTrue(after['ok'], after)
        self.assertEqual([e['gone'] for e in after['entries']], [True, True])
        self.assertEqual((after['entries'][1]['localGone'], after['entries'][1]['remoteGone']), (True, True))

    def test_a_remote_branch_that_is_gone_or_has_moved_is_not_deleted_and_is_said(self):
        path, branch, tip = self.worktree('wt12')
        for remote, caution in ((None, 'remote_branch_gone'), ('a' * 40, 'remote_branch_moved')):
            with self.subTest(remote=remote):
                entry = self.only(self.plan({branch: merged(tip, remote=remote)})[0])
                self.assertEqual((entry['deleteRemoteBranch'], entry['cautions']), (False, [caution]))
                self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])

    def test_records_kept_inside_the_worktree_are_a_caution_that_does_not_block(self):
        path, branch, tip = self.worktree('wt12')
        (path / '.frontlights').mkdir()
        (path / '.frontlights' / 'note.txt').write_text('evidence')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(entry['cautions'], ['frontlights_records'])

    def test_a_squash_merged_branch_is_removable_because_its_tip_is_the_head_of_the_merged_pull_request(self):
        path, branch, tip = self.worktree('wt12')
        entry = self.only(self.plan({branch: merged(tip, merged_at=LATE)})[0])
        self.assertIn('-D', entry['commands'][1]['argv'])   # Git calls it unmerged; GitHub says its head was merged

    def test_a_branch_whose_worktree_is_already_gone_is_deleted_alone(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'remove', str(path))
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual((entry['removeWorktree'], entry['path'], [c['kind'] for c in entry['commands']]),
                         (False, None, ['delete_branch', 'delete_remote_branch']))

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

    def test_ignored_files_go_away_with_the_worktree_so_they_are_named_in_a_caution_that_does_not_block(self):
        self.ignore('*.env', 'node_modules/')
        path, branch, tip = self.worktree('wt12')
        (path / 'secret.env').write_text('TOKEN=1')
        (path / 'node_modules').mkdir()
        (path / 'node_modules' / 'x.js').write_text('x')
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual(entry['cautions'], ['ignored_files'])
        self.assertEqual((entry['ignoredCount'], sorted(entry['ignored'])), (2, ['node_modules/', 'secret.env']))
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

    def test_the_remote_branch_is_deleted_only_when_origin_is_the_configured_repository(self):
        path, branch, tip = self.worktree('wt12')
        for url, deletes in ((f'git@github.com:{REPO}.git', True), (f'https://github.com/{REPO.lower()}', True),
                             ('https://github.com/OTHER/REPOSITORY.git', False), ('not a url', False)):
            with self.subTest(url=url):
                self.git('remote', 'set-url', 'origin', url)
                entry = self.only(self.plan({branch: merged(tip)})[0])
                self.assertEqual(entry['deleteRemoteBranch'], deletes)
                self.assertEqual([c['kind'] for c in entry['commands']].count('delete_remote_branch'), int(deletes))
                self.assertEqual(entry['cautions'], [] if deletes else ['origin_is_not_the_repository'])

    def test_the_push_url_is_the_one_that_counts(self):
        path, branch, tip = self.worktree('wt12')
        self.git('config', 'remote.origin.pushurl', 'https://github.com/OTHER/REPOSITORY.git')   # fetch URL still ours
        entry = self.only(self.plan({branch: merged(tip)})[0])
        self.assertEqual((entry['deleteRemoteBranch'], entry['cautions']), (False, ['origin_is_not_the_repository']))

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
        self.assertEqual((last['issue'], last['branch'], last['cautions'], last['deleteRemoteBranch']),
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

    def test_verify_says_a_remote_branch_that_is_still_there_is_not_gone(self):
        path, branch, tip = self.worktree('wt12')
        self.git('worktree', 'remove', str(path))
        self.git('branch', '-D', branch)
        there = cleanup.run('verify', self.config, self.root, None, None, (), [branch], FakeGh({branch: {'remote': tip}}))
        self.assertEqual((there['ok'], there['entries'][0]['localGone'], there['entries'][0]['remoteGone']), (False, True, False))
        gone = cleanup.run('verify', self.config, self.root, None, None, (), [branch], FakeGh({}))
        self.assertEqual((gone['ok'], gone['entries'][0]['gone']), (True, True))


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
        self.assertEqual((entry['cautions'], entry['deleteRemoteBranch']), (['contained_in_base_without_pull_request'], False))
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])
        self.assertFalse(any('push' in c['argv'] for c in entry['commands']))

    def test_a_branch_pushed_under_the_old_flow_and_delivered_without_a_pull_request_still_reports_its_remote(self):
        path, branch, tip = self.delivered()
        entry = self.only(self.plan({branch: {'heads': [], 'remote': 'a' * 40}})[0])
        self.assertEqual((entry['cautions'], entry['deleteRemoteBranch']),
                         (['contained_in_base_without_pull_request', 'remote_branch_moved'], False))
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch'])
        entry = self.only(self.plan({branch: {'heads': [], 'remote': tip}})[0])
        self.assertEqual((entry['cautions'], entry['deleteRemoteBranch']), (['contained_in_base_without_pull_request'], True))
        self.assertEqual([c['kind'] for c in entry['commands']], ['remove_worktree', 'delete_branch', 'delete_remote_branch'])

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


if __name__ == '__main__':
    unittest.main()
