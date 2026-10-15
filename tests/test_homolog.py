"""Homologação na main local (issue 32): a branch da issue é cortada da main local, fica só local e entra nela
por merge com três portões verdes; nada vai ao GitHub até a release.

Seams: `frontlights.py authorize` (S1); o texto de `SKILL.md`, `references/development.md`, `docs/protocol.md`,
`docs/security.md`, `templates/handoff.md`, `examples/authorization.json`, `README.md`, `docs/acceptance.md` e
`evals/runbook.md` (S1).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import frontlights

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def stage(number):
    text = read('skills', 'frontlights', 'SKILL.md')
    return ' '.join(text.split(f'## {number}.')[1].split(f'## {number + 1}.')[0].split())


GREEN = {'full_suite': 'green', 'review_gate': 'current', 'browser_gate': 'answered'}


class LocalMainMergeAuthorizeTests(unittest.TestCase):
    """S1: `authorize` aceita o merge da branch da issue na main local só com os três portões verdes; a main
    remota (`origin/main`) nunca é alvo; uma branch de CA não entra na main local."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.issue = self.root / 'issue-1'
        self.slice = self.root / 'issue-1-s2'
        for folder in (self.issue, self.slice):
            (folder / 'src').mkdir(parents=True)
        self.c = dict(repository='example/project', issue_ids=[1], concurrency=1,
                      approved_by='usuário (autorização permanente)',
                      approval_reference='autorização permanente (docs/security.md)',
                      expires_at='2099-01-01T00:00:00+00:00',
                      monitoring={'mode': 'local', 'confirmed_by': 'usuário (autorização permanente)'},
                      base={'branch': 'main', 'commit': 'abc1234'},
                      protected_branches=['main', 'master'],
                      operations=['edit', 'test', 'checkpoint', 'merge_into_local_main'],
                      worktrees=[{'issue': 1, 'path': str(self.issue), 'branch': 'claude/issue-1', 'ownership': ['src']},
                                 {'issue': 1, 'path': str(self.slice), 'branch': 'claude/issue-1-s2', 'slice': 'S2',
                                  'ownership': ['src']}],
                      verification_commands=[['python', '-m', 'unittest']],
                      stop_conditions=['Decisão nova de produto'])
        self.op = dict(repository='example/project', issue=1, kind='merge_into_local_main',
                       worktree=str(self.issue), branch='claude/issue-1', target='main', gates=dict(GREEN))

    def test_the_merge_into_the_local_main_passes_with_the_three_gates_green(self):
        result = frontlights.authorize(self.c, self.op)
        self.assertEqual(result['scope_check'], 'pass')
        self.assertFalse(result['permission_granted'])

    def test_a_browser_gate_that_was_not_needed_is_green_too(self):
        op = dict(self.op, gates=dict(GREEN, browser_gate='not_needed'))
        self.assertEqual(frontlights.authorize(self.c, op)['scope_check'], 'pass')

    def test_a_missing_or_red_gate_refuses_and_names_the_gate(self):
        reds = {'full_suite': ('red', 'skipped', True, None), 'review_gate': ('stale', 'current ', None),
                'browser_gate': ('pending', 'stale', 'contradiction', 'dispensado', None)}
        for gate, values in reds.items():
            for value in values:
                gates = dict(GREEN)
                if value is None:
                    del gates[gate]
                else:
                    gates[gate] = value
                with self.subTest(gate=gate, value=value), self.assertRaisesRegex(ValueError, gate):
                    frontlights.authorize(self.c, dict(self.op, gates=gates))
        with self.assertRaisesRegex(ValueError, 'gates'):
            frontlights.authorize(self.c, {k: v for k, v in self.op.items() if k != 'gates'})

    def test_the_remote_main_is_never_the_target(self):
        for target in ('origin/main', 'refs/remotes/origin/main', 'upstream/main'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'remote'):
                frontlights.authorize(self.c, dict(self.op, target=target))

    def test_the_target_is_the_base_branch_of_the_charter_and_nothing_else(self):
        for target in ('develop', 'master', 'claude/issue-1', '', None):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'target'):
                frontlights.authorize(self.c, dict(self.op, target=target))
        without_base = {k: v for k, v in self.c.items() if k != 'base'}
        with self.assertRaisesRegex(ValueError, 'base'):
            frontlights.authorize(without_base, self.op)

    def test_a_slice_branch_does_not_enter_the_local_main(self):
        op = dict(self.op, worktree=str(self.slice), branch='claude/issue-1-s2', slice='S2')
        with self.assertRaisesRegex(ValueError, 'slice'):
            frontlights.authorize(self.c, op)

    def test_the_kind_must_be_covered_by_the_charter(self):
        c = dict(self.c, operations=['edit', 'test', 'checkpoint'])
        with self.assertRaisesRegex(ValueError, 'outside bounded authorization'):
            frontlights.authorize(c, self.op)

    def test_the_local_main_is_still_never_the_branch_of_an_edit(self):
        op = dict(repository='example/project', issue=1, kind='edit', worktree=str(self.issue), branch='main',
                  path=str(self.issue / 'src' / 'app.py'))
        with self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
            frontlights.authorize(self.c, op)
        c = dict(self.c, worktrees=[dict(self.c['worktrees'][0], branch='main')])
        with self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
            frontlights.authorize(c, op)


class LocalMainTextTests(unittest.TestCase):
    """S1: os quatro documentos, o handoff e o exemplo de autorização dizem que a branch da issue é cortada da
    main local, fica só local e entra nela com os três portões, e distinguem a main local da remota."""

    def test_stage_six_cuts_the_branch_from_the_local_main_and_keeps_it_local(self):
        text = stage(6)
        for phrase in ('cut from the local main', 'never from `origin/main`', 'stays local and is never pushed',
                       'the merge of the branch of the issue into the local main with its three gates green',
                       'Nothing of an issue goes to GitHub before the release',
                       'writing the remote main (`origin/main`, the base branch on GitHub)',
                       'the local main is written only by the covered merge below',
                       'the full suite green at the tip of the branch of the issue, `review-gate` `current` for it and '
                       '`browser-gate` `answered` (or `not_needed`)',
                       '`merge_into_local_main`', 'a red gate is a question to the user, never a merge'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for gone in ('pushing the work branches', 'one issue branch and one PR', 'write the base branch'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_development_reference_has_the_gates_section_after_the_review(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertEqual(text.count('## Into the local main: the three gates'), 1)
        self.assertLess(text.index('## Review, checkpoints and renewal'), text.index('## Into the local main'))
        self.assertLess(text.index('## Into the local main'), text.index('## After the pull request'))
        body = ' '.join(text.split('## Into the local main: the three gates')[1].split('## After the pull request')[0].split())
        for phrase in ('homologation bench', 'refused as the remote main', '**Bring the local main in first.**',
                       '`git merge main`', '**Gate 1, the full suite.**', 'never the fast suite',
                       '**Gate 2, the review.**', '`stale` means a review again, never the merge',
                       '**Gate 3, the watched run.**', '**The check and the merge.**', '`merge_into_local_main`',
                       '`examples/operation-merge-local-main.json`', '`git merge --no-ff <branch_prefix>issue-<n>`',
                       'it never edits the gates to make them pass', '**Record it.**', '"Merge na main local"',
                       'a preflight, not a barrier', 'it reads no Git'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        whole = ' '.join(text.split())
        for phrase in ('one merge into the local main per issue', 'delivered by one merge into the local main',
                       'the branches of the issue and of its slices are never pushed',
                       'writing the remote main (`origin/main`, the base branch on GitHub)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, whole)
        for gone in ('pushing the work branches', 'Draft PRs are covered', 'delivered in one PR'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, whole)

    def test_the_protocol_and_the_security_notes_tell_the_local_main_from_the_remote(self):
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('cortada da main local', 'fica só local, nunca é enviada e entra na main local',
                       'três portões verdes', 'conferidos pelo `authorize` como `merge_into_local_main`',
                       'Nada da issue vai ao GitHub antes da release',
                       'escrever na main remota (`origin/main`, a branch base no GitHub)',
                       'a main local só recebe o merge coberto', 'a saída do `authorize` do merge na main local'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Main local e main remota.**', 'cortada da main local e fica só local',
                       'escrever na main remota (`origin/main`)',
                       '`merge_into_local_main` só com `target` igual a `base.branch`', 'são recusados como main remota',
                       'nunca de uma slice',
                       '`full_suite: green`, `review_gate: current` e `browser_gate: answered` ou `not_needed`',
                       'conferência prévia, não barreira', 'não lê o Git',
                       'confere `edit`, `test`, `checkpoint` e `merge_into_local_main`',
                       'e o merge da branch da issue na main local com os três portões verdes). Esses são os únicos merges permitidos'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        for name, text in (('protocol', protocol), ('security', security)):
            with self.subTest(file=name):
                self.assertNotIn('enviar as branches de trabalho', text)
                self.assertNotIn('escrever na branch base ou protegida', text)

    def test_the_readme_the_handoff_and_the_examples_follow(self):
        readme = flat('README.md')
        for phrase in ('cortadas da main local do projeto (a homologação) e ficam só locais até a release',
                       'numa branch por issue, cortada da main local',
                       'mesclar a branch da issue na main local com os três portões verdes',
                       'escrever na main remota (`origin/main`)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertNotIn('enviar as branches, abrir PRs rascunho', readme)
        handoff = read('skills', 'frontlights', 'templates', 'handoff.md')
        self.assertIn('- Merge na main local (', handoff)
        self.assertIn('`merge_into_local_main`', handoff)
        charter = json.loads(read('skills', 'frontlights', 'examples', 'authorization.json'))
        self.assertIn('merge_into_local_main', charter['operations'])
        self.assertEqual(charter['base']['branch'], 'main')
        op = json.loads(read('skills', 'frontlights', 'examples', 'operation-merge-local-main.json'))
        self.assertEqual((op['kind'], op['target']), ('merge_into_local_main', 'main'))
        self.assertEqual(set(op['gates']), {'full_suite', 'review_gate', 'browser_gate'})
        # the example operation passes `authorize` against the example charter once the placeholders are filled
        with tempfile.TemporaryDirectory() as temp:
            charter = dict(charter, approved_by='usuário', approval_reference='autorização permanente',
                           expires_at='2099-01-01T00:00:00+00:00',
                           monitoring=dict(charter['monitoring'], confirmed_by='usuário'),
                           worktrees=[dict(charter['worktrees'][0], path=temp)])
            self.assertEqual(frontlights.authorize(charter, dict(op, worktree=temp))['scope_check'], 'pass')

    def test_the_acceptance_record_and_the_runbook_track_it(self):
        self.assertIn('| 27. Homologação na main local: merge com portões e release por PR única (issue 32) | Pendente |',
                      flat('docs', 'acceptance.md'))
        self.assertIn('27. Local main as homologation (issue 32).', flat('evals', 'runbook.md'))


if __name__ == '__main__':
    unittest.main()
