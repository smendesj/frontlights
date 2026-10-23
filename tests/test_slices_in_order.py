"""A etapa 6 trabalha as slices de uma issue em ordem, numa branch por issue, criada no GitHub a partir da `origin/<base>`: cada slice é um ciclo de
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

sys.path.insert(0, str(ROOT / 'tests'))
import skilltext  # noqa: E402

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

    def test_each_slice_worktree_keeps_its_own_checkpoint(self):
        """Issue 31, S2: uma worktree por CA, um checkpoint por worktree; o de uma CA não retoma na outra
        (caracterização: a recusa "different worktree" já existia na base; a regra nova é o checkpoint por worktree)."""
        other = Path(self.tmp.name) / 'repo-s2'
        other.mkdir()
        for args in (('init', '-b', 'claude/fixture-s2'), ('config', 'user.email', 'fixture@example.invalid'),
                     ('config', 'user.name', 'Fixture')):
            subprocess.run(['git', '-C', str(other), *args], check=True, capture_output=True)
        (other / 'b.txt').write_text('two', encoding='utf-8')
        subprocess.run(['git', '-C', str(other), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(other), 'commit', '-m', 'fixture'], check=True, capture_output=True)
        s1 = frontlights.checkpoint(self.root, self.issue, self.handoff, 'next', slice_id='S1')
        s2 = frontlights.checkpoint(other, self.issue, self.handoff, 'next', slice_id='S2')
        self.assertEqual(frontlights.resume(self.root, s1, self.issue, self.handoff)['slice'], 'S1')
        self.assertEqual(frontlights.resume(other, s2, self.issue, self.handoff)['slice'], 'S2')
        with self.assertRaisesRegex(ValueError, 'different worktree'):
            frontlights.resume(self.root, s2, self.issue, self.handoff)

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
    def test_stage_6_works_the_slices_in_order_on_one_branch_merged_into_the_local_main(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        # redesenho, issue 3: a etapa 6 é um item da lista numerada e aponta para a seção por nome
        body = flat(skilltext.stage(6))
        for phrase in ('slices in order, one issue branch, one worktree per slice', '`frontlights.py slice open`',
                       '("Slices in order";'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        development = flat(read('skills', 'frontlights', 'references', 'development.md'))
        # redesenho, issue 3: "created on GitHub from `origin/<base>`" vive em development.md, "Slices in order"
        slices = flat(section(read('skills', 'frontlights', 'references', 'development.md'), 'Slices in order') or '')
        for phrase in ('One issue branch, one worktree per slice, one merge into the local main per issue.',
                       'created on GitHub when its work starts', '(`origin/<base>`, never the local main)'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, slices)
        for phrase in ('gets its own worktree and branch', 'the slices are worked in dependency order',
                       'a family that already exists', 'the order of the slices'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        self.assertNotIn('Choose the highest safe parallelism; when a sub-issue', body)
        self.assertNotIn('one branch, one worktree and one PR', body)

    def test_the_reference_defines_the_loop_the_checkpoint_and_the_tick_of_each_slice(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = flat(section(text, 'Slices in order') or '')
        self.assertNotEqual(body, '')
        for phrase in ('one issue branch', 'delivered by one merge into the local main', 'its own worktree and branch',
                       'in dependency order: independent slices run at once',
                       'one TDD loop', '`checkpoint --slice <id>`', 'first open box', 'tick of its box',
                       '`closeout.py tick-check` before and after the write', 'one per issue, when the last slice',
                       'it is the only gate of the merge into the local main',
                       'a broader suite and an independent review run only when the user asks for them',
                       'a family that already exists'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertNotIn('one per issue, of the whole diff, before the merge into the local main', body)
        self.assertLess(text.index('## Slices in order'), text.index('## Dispatch and ownership'))

    def test_independent_slices_run_at_once_and_a_dependent_one_is_stacked(self):
        """Issue 31, S3: CAs sem `Depende de` entre si e sem arquivo em comum rodam juntas, cada uma na própria
        worktree; a CA que depende de outra ainda aberta é empilhada na branch dela (`base` no charter, `--stacked`
        no browser-gate); o cleanup oferece a branch de CA já na branch da issue; o teste assistido é um por issue."""
        # redesenho, issue 3: a etapa 6 diz "one per issue, DEPOIS only, the only gate"; o momento (a última slice que
        # muda a tela) vive em development.md, "Slices in order"
        skill = flat(skilltext.stage(6))
        self.assertIn('the watched run, one per issue, DEPOIS only, the only gate', skill)
        self.assertIn('one per issue, when the last slice that changes the screen closes its loop',
                      flat(section(read('skills', 'frontlights', 'references', 'development.md'), 'Slices in order') or ''))
        self.assertIn('There is one watched run per issue, never one per slice',
                      flat(read('skills', 'frontlights', 'references', 'browser-testing.md')))
        body = flat(section(read('skills', 'frontlights', 'references', 'development.md'), 'Slices in order') or '')
        for phrase in ('no `Depende de` between them and no file in common', '`"base": "<slice-branch>"`', '`--stacked`',
                       "is cut from that slice's branch instead (stacked",
                       'merged into the branch of the issue after the slice it depends on'):
            with self.subTest(where='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        self.assertIn('slice_merged_into_issue_branch', flat(read('skills', 'frontlights', 'references', 'closeout.md')))
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        self.assertIn('O teste é um por issue', security)
        self.assertIn('uma vez por issue e antes da revisão independente', flat(read('skills', 'frontlights', 'docs', 'protocol.md')))
        self.assertIn('**Um teste por issue, o único portão.**', flat(read('README.md')))

    def test_each_slice_has_its_own_worktree_cut_from_the_issue_branch(self):
        """Issue 31, S2: a worktree e a branch de cada CA, o `slice` no charter, um checkpoint por worktree e o
        merge da CA pronta na branch da issue entre os merges cobertos, nos quatro documentos, no handoff e no
        exemplo de autorização."""
        # redesenho, issue 3: a etapa 6 cita o comando entregue (`slice merge`); a frase "merged into the branch of the
        # issue when its loop closes" segue fixada em development.md, logo abaixo
        skill = flat(skilltext.stage(6))
        for phrase in ('`frontlights.py slice merge`', 'TDD by default, never a gate'):
            with self.subTest(where='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        development = read('skills', 'frontlights', 'references', 'development.md')
        body = flat(section(development, 'Slices in order') or '')
        for phrase in ('`<branch_prefix>issue-<n>-s<k>`', 'cut from the branch of the issue', '`slice`',
                       '`checkpoint-<id>.json`', 'merged into the branch of the issue'):
            with self.subTest(where='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        self.assertIn("a slice's branch into the branch of its own issue when its loop closes", flat(development))
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        for phrase in ('uma worktree por slice', '`checkpoint-<id>.json`'):
            with self.subTest(where='protocol.md', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertIn('cada CA na própria worktree', flat(read('README.md')))
        charter = json.loads(read('skills', 'frontlights', 'examples', 'authorization.json'))
        sliced = [w for w in charter['worktrees'] if 'slice' in w]
        self.assertEqual([w['slice'] for w in sliced], ['S2'])
        self.assertTrue(sliced[0]['branch'].endswith('-s2'))

    def test_the_handoff_names_the_slice_in_progress(self):
        handoff = read('skills', 'frontlights', 'templates', 'handoff.md')
        self.assertRegex(handoff, r'(?m)^- Slice em andamento')
        self.assertIn('worktree', re.search(r'(?m)^- Slice em andamento[^\n]*', handoff).group(0))

    def test_the_browser_reference_says_what_a_slice_and_a_root_are(self):
        text = flat(read('skills', 'frontlights', 'references', 'browser-testing.md'))
        self.assertIn('a slice is a box', text)
        self.assertIn("each `--root` is the worktree of an issue or of one of its slices", text)
        self.assertNotIn("each `--root` is an issue's worktree", text)

    def test_the_protocol_the_readme_and_the_runbook_follow(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        readme = flat(read('README.md'))
        for text, name in ((protocol, 'protocol'), (readme, 'README')):
            for phrase in ('slices de cada issue em ordem', 'uma branch por issue, criada no GitHub a partir da', 'família que já existe'):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)
        runbook = flat(read('evals', 'runbook.md'))
        for phrase in ('the order of the slices', 'first open box', '`checkpoint --slice`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, runbook)


if __name__ == '__main__':
    unittest.main()
