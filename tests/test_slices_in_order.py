"""A etapa 6 trabalha as slices de uma issue em ordem, numa branch e um PR por issue: cada slice é um ciclo de
TDD, um ponto de retomada e uma caixa marcada com evidência; uma sessão nova retoma pela primeira caixa aberta.

Seams: `frontlights.checkpoint`/`resume` com `--slice`, e os manifestos de texto da skill, da referência da etapa
6, da referência do navegador, do modelo de handoff, do protocolo, do README e do roteiro.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(SKILL / 'scripts'))
import frontlights

SCRIPT = SKILL / 'scripts' / 'frontlights.py'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return None
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


class SliceCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        for args in (('init', '-b', 'claude/fixture'), ('config', 'user.email', 'fixture@example.invalid'),
                     ('config', 'user.name', 'Fixture')):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        (self.root / 'a.txt').write_text('one', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'commit', '-m', 'fixture'], check=True, capture_output=True)
        self.handoff = Path(self.tmp.name) / 'handoff.md'
        self.handoff.write_text('state', encoding='utf-8')
        self.issue = {'number': 1, 'title': 't', 'body': 'b', 'state': 'open', 'source': 'local', 'labels': [],
                      'assignees': [], 'updated_at': 'x'}

    def test_a_checkpoint_carries_the_slice_in_progress_and_resume_echoes_it(self):
        saved = frontlights.checkpoint(self.root, self.issue, self.handoff, 'next', slice_id='S2')
        self.assertEqual(saved['slice'], 'S2')
        resumed = frontlights.resume(self.root, saved, self.issue, self.handoff)
        self.assertEqual((resumed['state'], resumed['slice']), ('unchanged', 'S2'))

    def test_without_a_slice_the_checkpoint_and_an_old_one_resume_with_none(self):
        saved = frontlights.checkpoint(self.root, self.issue, self.handoff, 'next')
        self.assertIsNone(saved['slice'])
        saved.pop('slice')
        self.assertIsNone(frontlights.resume(self.root, saved, self.issue, self.handoff)['slice'])

    def test_a_slice_id_is_a_short_label_without_spaces(self):
        for bad in ('S 2', '', 'x' * 20, 'S2\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                frontlights.checkpoint(self.root, self.issue, self.handoff, 'next', slice_id=bad)

    def test_the_cli_takes_and_echoes_the_slice(self):
        issue_file = Path(self.tmp.name) / 'issue.json'
        issue_file.write_text(json.dumps(self.issue), encoding='utf-8')
        saved = subprocess.run([sys.executable, str(SCRIPT), 'checkpoint', '--root', str(self.root), '--issue',
                                str(issue_file), '--handoff', str(self.handoff), '--next-step', 'S3', '--slice', 'S3'],
                               capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(json.loads(saved.stdout)['slice'], 'S3')
        checkpoint_file = Path(self.tmp.name) / 'checkpoint.json'
        checkpoint_file.write_text(saved.stdout, encoding='utf-8')
        resumed = subprocess.run([sys.executable, str(SCRIPT), 'resume', '--root', str(self.root), '--issue',
                                  str(issue_file), '--handoff', str(self.handoff), '--checkpoint', str(checkpoint_file)],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(json.loads(resumed.stdout)['slice'], 'S3')


class SlicesInOrderTextTests(unittest.TestCase):
    def test_stage_6_works_the_slices_in_order_on_one_branch_and_one_pr_per_issue(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        body = flat(section(skill, '6. Bounded development') or '')
        for phrase in ('one branch, one worktree and one PR', 'its slices are worked in order',
                       'parallelism only between issues', 'a family that already exists', 'the order of the slices'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertNotIn('Choose the highest safe parallelism; when a sub-issue', body)

    def test_the_reference_defines_the_loop_the_checkpoint_and_the_tick_of_each_slice(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = flat(section(text, 'Slices in order') or '')
        self.assertNotEqual(body, '')
        for phrase in ('one branch, in one worktree, and delivered in one PR', 'in dependency order, one at a time',
                       'one TDD loop', '`checkpoint --slice <id>`', 'first open box', 'tick of its box',
                       '`closeout.py tick-check` before and after the write', 'one per batch',
                       'one per issue, of the whole diff, before the PR', 'a family that already exists'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertLess(text.index('## Slices in order'), text.index('## Dispatch and ownership'))

    def test_the_handoff_names_the_slice_in_progress(self):
        self.assertRegex(read('skills', 'frontlights', 'templates', 'handoff.md'), r'(?m)^- Slice em andamento')

    def test_the_browser_reference_says_what_a_slice_and_a_root_are(self):
        text = flat(read('skills', 'frontlights', 'references', 'browser-testing.md'))
        self.assertIn('a slice is a box', text)
        self.assertIn("each `--root` is an issue's worktree", text)
        self.assertNotIn("each `--root` is a slice's worktree", text)

    def test_the_protocol_the_readme_and_the_runbook_follow(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        readme = flat(read('README.md'))
        for text, name in ((protocol, 'protocol'), (readme, 'README')):
            for phrase in ('slices de cada issue em ordem', 'uma branch e um PR por issue', 'família que já existe'):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)
        runbook = flat(read('evals', 'runbook.md'))
        for phrase in ('the order of the slices', 'first open box', '`checkpoint --slice`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, runbook)


if __name__ == '__main__':
    unittest.main()
