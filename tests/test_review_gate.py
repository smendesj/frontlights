"""O portão da revisão: depois de qualquer mudança no diff, no HEAD ou nos arquivos, a revisão independente
anterior deixa de valer. `review-gate` compara a evidência salva na hora da revisão com a atual.

Seam: a CLI `frontlights.py review-gate` (saída JSON e código de saída) e `frontlights.review_gate`.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import frontlights

SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'


class ReviewGateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-b', 'claude/fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.root / 'app.txt').write_text('one', encoding='utf-8')
        (self.root / 'other.txt').write_text('fixed', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        self.review = Path(self.tmp.name) / 'review.json'

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True)

    def reviewed(self, wrap=None):
        """The evidence the reviewer was bound to, saved as the coordinator does."""
        evidence = frontlights.git_evidence(self.root)
        self.review.write_text(json.dumps(evidence if wrap is None else {wrap: evidence}), encoding='utf-8')

    def gate(self):
        return frontlights.review_gate(json.loads(self.review.read_text(encoding='utf-8')), frontlights.git_evidence(self.root))

    def cli(self):
        return subprocess.run([sys.executable, str(SCRIPT), 'review-gate', '--root', str(self.root),
                               '--review', str(self.review)], capture_output=True, text=True, encoding='utf-8')


class GateDecisionTests(ReviewGateTestCase):
    def test_nothing_changed_since_the_review(self):
        self.reviewed()
        result = self.gate()
        self.assertEqual(result['status'], 'current')
        self.assertEqual((result['changed'], result['files_changed']), ([], []))

    def test_an_edit_after_the_review_makes_it_stale_and_names_the_file(self):
        self.reviewed()
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        result = self.gate()
        self.assertEqual(result['status'], 'stale')
        self.assertIn('diff_sha256', result['changed'])
        self.assertIn('files_sha256', result['changed'])
        self.assertEqual(result['files_changed'], ['app.txt'])

    def test_a_new_untracked_file_makes_it_stale(self):
        self.reviewed()
        (self.root / 'new.txt').write_text('x', encoding='utf-8')
        result = self.gate()
        self.assertEqual((result['status'], result['files_changed']), ('stale', ['new.txt']))

    def test_a_removed_file_makes_it_stale(self):
        self.reviewed()
        (self.root / 'other.txt').unlink()
        result = self.gate()
        self.assertEqual((result['status'], result['files_changed']), ('stale', ['other.txt']))

    def test_a_new_commit_with_the_same_content_still_makes_it_stale(self):
        self.reviewed()
        self.git('commit', '--allow-empty', '-m', 'amend only the history')
        result = self.gate()
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['changed'], ['head'])
        self.assertEqual(result['files_changed'], [])

    def test_another_branch_makes_it_stale(self):
        self.reviewed()
        self.git('checkout', '-b', 'claude/other')
        result = self.gate()
        self.assertEqual((result['status'], result['changed']), ('stale', ['branch']))

    def test_the_control_folder_is_not_part_of_the_evidence(self):
        self.reviewed()
        (self.root / '.frontlights').mkdir()
        (self.root / '.frontlights' / 'handoff.md').write_text('notes', encoding='utf-8')
        self.assertEqual(self.gate()['status'], 'current')

    def test_the_evidence_may_come_wrapped_as_in_a_checkpoint(self):
        for wrap in ('evidence', 'git'):
            with self.subTest(wrap=wrap):
                self.reviewed(wrap)
                self.assertEqual(self.gate()['status'], 'current')

    def test_a_detached_head_has_an_empty_branch_and_still_compares(self):
        self.git('checkout', '--detach')
        self.reviewed()
        self.assertEqual(self.gate()['status'], 'current')
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.assertEqual(self.gate()['status'], 'stale')

    def test_a_review_without_evidence_is_refused(self):
        for saved in ({}, {'head': 'abc'}, {'evidence': {'head': 1}}, [], 'text'):
            with self.subTest(saved=saved), self.assertRaises(ValueError):
                frontlights.review_gate(saved, frontlights.git_evidence(self.root))


class GateCommandTests(ReviewGateTestCase):
    def test_current_exits_zero_and_stale_exits_two(self):
        self.reviewed()
        current = self.cli()
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(json.loads(current.stdout)['status'], 'current')
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        stale = self.cli()
        self.assertEqual(stale.returncode, 2)
        self.assertEqual(json.loads(stale.stdout)['status'], 'stale')
        self.assertEqual(stale.stderr, '')

    def test_an_unreadable_review_file_exits_one_without_a_traceback(self):
        self.review.write_text('not json', encoding='utf-8')
        failed = self.cli()
        self.assertEqual(failed.returncode, 1)
        self.assertNotIn('Traceback', failed.stderr)
        self.assertIn('error', json.loads(failed.stderr))


class GateDocumentationTests(unittest.TestCase):
    def test_the_rule_is_in_the_development_reference_and_the_handoff(self):
        development = ' '.join((ROOT / 'skills' / 'frontlights' / 'references' / 'development.md')
                               .read_text(encoding='utf-8').split())
        for phrase in ('review-gate', 'exit code 2', 'before reporting an issue as reviewed',
                       'Any commit, edit or new file after the review',
                       'The independent review runs only when the user asks for one',
                       'is not a gate of the merge into the local main nor of the release'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)
        self.assertNotIn('before opening or updating a PR', development)
        handoff = (ROOT / 'skills' / 'frontlights' / 'templates' / 'handoff.md').read_text(encoding='utf-8')
        self.assertIn('review-gate', handoff)


if __name__ == '__main__':
    unittest.main()
