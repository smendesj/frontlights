"""Etapa 6 por comando (redesenho, issue 4): `slice open` e `slice merge` (S2), a guarda do `closeout.py tick` (S2)
e `homolog merge` (S3), em gitfixture com origin bare e `gh` simulado.

Seams: `frontlights.slice_cli`, `closeout.run('tick')` e `homolog.run('merge')`.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import closeout  # noqa: E402
import frontlights  # noqa: E402
import homolog  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture  # noqa: E402
from test_charter import REPO, build  # noqa: E402
from test_closeout import FakeIssueGh, TICK_BODY  # noqa: E402

GREEN = [sys.executable, '-c', 'raise SystemExit(0)']
RED = [sys.executable, '-c', 'raise SystemExit(1)']


def git(root, *args):
    return gitfixture.git(root, *args).stdout.strip()


class Stage6Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.folder = gitfixture.copy(self.template, self.tmp / 'f')
        self.root = self.folder / 'project'
        self.wt = self.folder / 'wt'
        (self.root / '.frontlights').mkdir()
        self.config = self.root / '.frontlights' / 'config.json'
        self.config.write_text(json.dumps({'repository': REPO, 'branchPrefix': 'PREFIX/'}), encoding='utf-8')
        result = frontlights.charter_cli('new', str(self.root), str(self.config), issues=['12'],
                                         ownership=['src', 'tests'], approved_by='OWNER-LOGIN', verify=[json.dumps(GREEN)])
        self.assertTrue(result['ok'], result)

    def charter(self):
        return json.loads((self.root / '.frontlights' / 'authorization.json').read_text(encoding='utf-8'))

    def open(self, *slices, **options):
        options.setdefault('directory', str(self.wt))
        return frontlights.slice_cli('open', str(self.root), str(self.config), '12', list(slices), **options)

    def merge(self, label='S1', **options):
        return frontlights.slice_cli('merge', str(self.root), str(self.config), '12', [label], **options)

    def commit(self, tree, name='src/feature.py', text='x = 1\n', message='slice'):
        path = Path(tree) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        git(tree, 'add', name)
        git(tree, 'commit', '-q', '-m', message)


class SliceOpenTests(Stage6Case):
    def test_open_cuts_the_issue_branch_from_the_remote_base_and_one_worktree_per_slice(self):
        result = self.open('S1', 'S2', ownership=['S1=src/a', 'S2=src/b'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(git(self.root, 'rev-parse', 'PREFIX/issue-12'), git(self.root, 'rev-parse', 'origin/main'))
        self.assertEqual(result['commands'], [['gh', 'issue', 'develop', '12', '--repo', REPO, '--base', 'main',
                                               '--name', 'PREFIX/issue-12']])
        entries = self.charter()['worktrees']
        self.assertEqual([(e['branch'], e.get('slice')) for e in entries],
                         [('PREFIX/issue-12', None), ('PREFIX/issue-12-s1', 'S1'), ('PREFIX/issue-12-s2', 'S2')])
        self.assertEqual(entries[1]['ownership'], ['src/a'])
        for entry in entries:
            self.assertTrue(Path(entry['path']).is_dir())
        op = {'repository': REPO, 'issue': 12, 'slice': 'S1', 'kind': 'edit', 'worktree': entries[1]['path'],
              'branch': 'PREFIX/issue-12-s1', 'path': 'src/a/x.py'}
        self.assertEqual(frontlights.authorize(self.charter(), op)['scope_check'], 'pass')
        with self.assertRaises(ValueError):
            frontlights.authorize(self.charter(), dict(op, path='src/b/x.py'))

    def test_a_stacked_slice_is_cut_from_the_slice_it_depends_on(self):
        self.open('S1')
        s1 = self.charter()['worktrees'][1]['path']
        self.commit(s1)
        result = self.open('S2', stacked_on='S1')
        self.assertTrue(result['ok'], result)
        entry = self.charter()['worktrees'][2]
        self.assertEqual(entry['base'], 'PREFIX/issue-12-s1')
        self.assertEqual(git(self.root, 'rev-parse', 'PREFIX/issue-12-s2'), git(self.root, 'rev-parse', 'PREFIX/issue-12-s1'))

    def test_opening_again_reports_the_slice_already_open(self):
        self.open('S1')
        result = self.open('S1')
        self.assertTrue(result['slices'][0]['already'])
        self.assertEqual(len(self.charter()['worktrees']), 2)

    def test_overlapping_ownership_is_a_warning(self):
        result = self.open('S1', 'S2')
        self.assertTrue(any('posse em comum' in w for w in result['warnings']))

    def test_an_issue_outside_the_charter_is_refused(self):
        result = frontlights.slice_cli('open', str(self.root), str(self.config), '99', ['S1'], directory=str(self.wt))
        self.assertEqual((result['ok'], result['reason']), (False, 'unapproved_issue'))


class SliceMergeTests(Stage6Case):
    def setUp(self):
        super().setUp()
        self.open('S1')
        entries = self.charter()['worktrees']
        self.issue_wt, self.s1 = entries[0]['path'], entries[1]['path']
        self.commit(self.s1)

    def test_a_green_slice_is_merged_no_ff_and_the_push_comes_as_argv(self):
        result = self.merge(comment_file='nota.md')
        self.assertTrue(result['ok'], result)
        parents = git(self.issue_wt, 'rev-list', '--parents', '-n', '1', 'HEAD').split()
        self.assertEqual(len(parents), 3)   # a merge commit, never a fast-forward
        self.assertEqual(result['commands'], [['git', '-C', self.issue_wt, 'push', 'origin', 'PREFIX/issue-12']])
        self.assertEqual(result['tests']['ran'][0]['exitCode'], 0)
        self.assertIn('--comment-file', result['next']['tick'])
        self.assertEqual(result['preview'], {'skipped': 'sem bloco preview no config: nada de prévia'})
        self.assertEqual(git(self.root, 'ls-remote', 'origin', 'PREFIX/issue-12'), '')   # nothing was pushed

    def test_a_dirty_worktree_is_refused(self):
        (Path(self.s1) / 'solto.txt').write_text('x', encoding='utf-8')
        result = self.merge()
        self.assertEqual((result['ok'], result['reason'], result['exitCode']), (False, 'dirty', 1))
        self.assertIn('solto.txt', result['files'])

    def test_a_red_test_is_refused_and_nothing_is_merged(self):
        before = git(self.root, 'rev-parse', 'PREFIX/issue-12')
        result = self.merge(tests=[json.dumps(RED)])
        self.assertEqual((result['ok'], result['reason']), (False, 'red'))
        self.assertEqual(git(self.root, 'rev-parse', 'PREFIX/issue-12'), before)
        self.assertTrue(Path(result['tests']['log']).is_file())

    def test_without_any_test_the_merge_is_refused_unless_watched_only(self):
        record = self.charter()
        record['verification_commands'] = []
        (self.root / '.frontlights' / 'authorization.json').write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(self.merge()['reason'], 'no_tests')
        result = self.merge(watched_only=True)
        self.assertTrue(result['ok'], result)
        self.assertIn('skipped', result['tests'])

    def test_a_suite_record_counts_only_on_the_same_tree(self):
        record = self.tmp / 'suite.json'
        record.write_text(json.dumps({'exitCode': 0, 'head': git(self.s1, 'rev-parse', 'HEAD~1')}), encoding='utf-8')
        self.assertEqual(self.merge(source=str(record))['reason'], 'suite_other_tree')
        record.write_text(json.dumps({'exitCode': 0, 'head': git(self.s1, 'rev-parse', 'HEAD')}), encoding='utf-8')
        self.assertTrue(self.merge(source=str(record))['ok'])

    def test_a_commit_only_of_the_local_main_is_exit_3(self):
        self.commit(self.root, 'src/main_only.py', message='só na main local')
        git(self.issue_wt, 'merge', '-q', '--no-edit', 'main')
        result = self.merge()
        self.assertEqual((result['ok'], result['reason'], result['exitCode']), (False, 'local_main_commit', 3))
        self.assertEqual(result['commits'][0], git(self.root, 'rev-parse', 'main'))

    def test_a_conflict_is_exit_2_with_the_files_and_the_rerun_goes_on(self):
        self.commit(self.issue_wt, 'src/feature.py', 'x = 2\n', 'na issue')
        result = self.merge()
        self.assertEqual((result['ok'], result['reason'], result['exitCode']), (False, 'conflict', 2))
        self.assertEqual(result['files'], ['src/feature.py'])
        self.assertEqual(git(self.issue_wt, 'status', '--porcelain'), '')
        subprocess.run(['git', '-C', self.issue_wt, 'merge', '--no-ff', 'PREFIX/issue-12-s1'], capture_output=True)
        (Path(self.issue_wt) / 'src' / 'feature.py').write_text('x = 3\n', encoding='utf-8')
        git(self.issue_wt, 'commit', '-q', '-am', 'resolvido')
        again = self.merge()
        self.assertTrue(again['ok'], again)
        self.assertTrue(again['alreadyMerged'])


class TickGuardTests(unittest.TestCase):
    """`closeout.py tick` marca uma caixa de slice só com o teste assistido aprovado ou o roteiro sem tela no
    formato; a caixa de pendência e o critério sem rótulo seguem como antes."""

    WALK = ('# Roteiro S2 da issue #12\n\nPersona: sem tela. Base abc1234, commit def5678.\n\n## Antes\n\n```\nsaída '
            'antiga\n```\n\n## Depois\n\n```\nsaída nova\n```\n')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.records = self.root / '.frontlights' / 'issues' / '12'
        self.records.mkdir(parents=True)
        self.config = self.root / '.frontlights' / 'config.json'
        self.config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')

    def tick(self, **options):
        gh = FakeIssueGh()
        options.setdefault('box', 'S2')
        result = closeout.run('tick', str(self.config), str(self.root), gh=gh, edit=gh.edit, issue='12',
                              line=options.pop('line', None), **options)
        return result, gh

    def test_without_evidence_the_box_is_refused_before_any_read(self):
        result, gh = self.tick()
        self.assertEqual((result['ok'], result['reason'], result['written']), (False, 'no_evidence', False))
        self.assertEqual(gh.reads, [])
        self.assertIn('walkthroughs/S<k>.md', result['hint'])

    def test_the_watched_run_approved_ticks_and_pode_prosseguir_does_not(self):
        browser = self.records / 'browser'
        browser.mkdir()
        (browser / 'result.json').write_text(json.dumps({'situacao': 'prosseguir'}), encoding='utf-8')
        self.assertEqual(self.tick()[0]['reason'], 'no_evidence')
        (browser / 'result.json').write_text(json.dumps({'situacao': 'aprovado'}), encoding='utf-8')
        result, _ = self.tick()
        self.assertTrue(result['verified'], result)
        self.assertEqual(result['evidence']['kind'], 'teste assistido')

    def test_a_walkthrough_in_its_format_ticks_and_one_out_of_it_is_refused(self):
        folder = self.records / 'walkthroughs'
        folder.mkdir()
        (folder / 'S2.md').write_text('## Antes\n\nsem bloco\n\n## Depois\n', encoding='utf-8')
        result, _ = self.tick()
        self.assertEqual(result['reason'], 'no_evidence')
        self.assertIn('fora do formato', result['message'])
        (folder / 'S2.md').write_text(self.WALK, encoding='utf-8')
        result, _ = self.tick()
        self.assertTrue(result['verified'], result)
        self.assertEqual(result['evidence']['kind'], 'roteiro sem tela')

    def test_a_line_on_a_slice_box_is_guarded_and_a_line_on_another_criterion_is_not(self):
        result, _ = self.tick(box=None, line='7')
        self.assertEqual(result['reason'], 'no_evidence')
        result, _ = self.tick(box=None, line='9')
        self.assertTrue(result['verified'], result)

    def test_the_comment_goes_with_the_tick(self):
        (self.records / 'walkthroughs').mkdir()
        (self.records / 'walkthroughs' / 'S2.md').write_text(self.WALK, encoding='utf-8')
        note = self.root / 'nota.md'
        note.write_text('S2 entregue no commit abc1234; `python -m unittest` verde.', encoding='utf-8')
        gh = FakeIssueGh()
        calls = []

        def edit(argv):
            calls.append(argv)
            if argv[0] == 'issue' and argv[1] == 'edit':
                gh.edit(argv)
        result = closeout.run('tick', str(self.config), str(self.root), gh=gh, edit=edit, issue='12', box='S2',
                              line=None, comment_file=str(note))
        self.assertTrue(result['commented'], result)
        self.assertEqual(calls[-1], ['issue', 'comment', '12', '--repo', REPO, '--body-file', str(note)])
        self.assertIn('- [x] S2.', gh.body)


if __name__ == '__main__':
    unittest.main()
