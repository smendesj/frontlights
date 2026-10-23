"""Homologação na main local (issue 32): a branch da issue é cortada da main local, fica só local e entra nela
por merge com o teste assistido respondido ou dispensável (o único portão, decisão de 20/10/2026); nada vai ao
GitHub até a release.

Seams: `frontlights.py authorize` (S1); o texto de `SKILL.md`, `references/development.md`, `docs/protocol.md`,
`docs/security.md`, `templates/handoff.md`, `examples/authorization.json`, `README.md`, `docs/acceptance.md` e
`evals/runbook.md` (S1); `scripts/homolog.py` (`sync`) e a entrada `frontlights.py homolog` (S2);
`scripts/homolog.py` (`bundle` e `backup_dir`) e a validação de `homolog.backupDir` no `inspect` (S3);
`scripts/homolog.py` (`release-plan`) e a entrada `frontlights.py homolog release-plan` (S4; a regra do
`cleanup.py plan` para a branch entregue sem PR está em `test_cleanup.py`).
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import frontlights
import homolog
import roads as rs
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture
import skilltext
from test_closeout import DONE_ALL, DONE_PARTIAL, FakeGh, node

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def stage(number):
    return skilltext.flat(skilltext.stage(number))


# redesenho, issue 3: os títulos de development.md ficaram curtos.
LOCAL_MAIN = '\n## Into the local main\n'
RELEASE = '\n## The release\n'


GREEN = {'browser_gate': 'answered'}


class LocalMainMergeAuthorizeTests(unittest.TestCase):
    """S1: `authorize` aceita o merge da branch da issue na main local só com o teste assistido respondido ou
    dispensável (`browser_gate`, o único portão; `suite_gate` e `review_gate` são opcionais); a main remota (`origin/main`) nunca é alvo; uma branch de CA não entra na main local."""

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

    def test_the_merge_into_the_local_main_passes_with_the_watched_run_answered(self):
        result = frontlights.authorize(self.c, self.op)
        self.assertEqual(result['scope_check'], 'pass')
        self.assertFalse(result['permission_granted'])

    def test_the_merge_comes_from_the_integration_branch_of_the_issue(self):
        """Issue 70, S2: a main local entra pela branch local de integração `<prefix>issue-<n>-integra`, cortada da
        branch da issue e listada como entrada própria do charter (sem `slice`); o `authorize` aceita o merge dela."""
        integra = self.root / 'issue-1-integra'
        (integra / 'src').mkdir(parents=True)
        c = dict(self.c, worktrees=self.c['worktrees'] + [
            {'issue': 1, 'path': str(integra), 'branch': 'claude/issue-1-integra', 'ownership': ['src']}])
        op = dict(self.op, worktree=str(integra), branch='claude/issue-1-integra')
        result = frontlights.authorize(c, op)
        self.assertEqual(result['scope_check'], 'pass')
        self.assertFalse(result['permission_granted'])

    def test_a_browser_gate_that_was_not_needed_is_green_too(self):
        op = dict(self.op, gates=dict(GREEN, browser_gate='not_needed'))
        self.assertEqual(frontlights.authorize(self.c, op)['scope_check'], 'pass')

    def test_the_suite_and_the_review_gates_are_optional_with_any_value(self):
        """Decisão de 20/10/2026: `suite_gate` e `review_gate` são aceitos em `gates` com qualquer valor, nunca
        exigidos nem recusados."""
        for extra in ({}, {'suite_gate': 'current', 'review_gate': 'current'}, {'suite_gate': 'stale'},
                      {'review_gate': 'stale'}, {'suite_gate': 'red', 'review_gate': None}):
            with self.subTest(extra=extra):
                op = dict(self.op, gates=dict(GREEN, **extra))
                self.assertEqual(frontlights.authorize(self.c, op)['scope_check'], 'pass')

    def test_a_missing_or_red_watched_run_refuses_and_names_the_gate(self):
        for value in ('pending', 'stale', 'contradiction', 'dispensado', 'unconfigured', True, None):
            gates = dict(GREEN, suite_gate='current', review_gate='current')
            if value is None:
                del gates['browser_gate']
            else:
                gates['browser_gate'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'browser_gate'):
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

    def test_a_base_branch_with_a_slash_is_accepted_and_its_remote_tracking_name_is_not(self):
        c = dict(self.c, base={'branch': 'release/main', 'commit': 'abc1234'})
        result = frontlights.authorize(c, dict(self.op, target='release/main'))
        self.assertEqual(result['scope_check'], 'pass')
        with self.assertRaisesRegex(ValueError, 'remote'):
            frontlights.authorize(c, dict(self.op, target='origin/release/main'))
        with self.assertRaisesRegex(ValueError, 'not the base branch'):
            frontlights.authorize(c, dict(self.op, target='main'))
        for remote in ('origin/main', 'refs/remotes/origin/main', 'remotes/origin/main'):
            bad = dict(self.c, base={'branch': remote, 'commit': 'abc1234'})
            with self.subTest(base=remote), self.assertRaisesRegex(ValueError, 'remote-tracking'):
                frontlights.authorize(bad, dict(self.op, target=remote))

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
    main local, fica só local e entra nela com o teste assistido, e distinguem a main local da remota."""

    def test_stage_six_cuts_the_branch_from_the_local_main_and_keeps_it_local(self):
        text = stage(6)
        # redesenho, issue 3: a etapa 6 cita os comandos e aponta as seções; `gh issue develop`, o push depois de
        # cada slice e os passos do merge na main local (portão, passeios sem tela, `authorize`, merge, bundle) vivem
        # em development.md, fixados abaixo e em test_the_development_reference_has_the_watched_run_section_after_the_review.
        for phrase in ('slices in order, one issue branch, one worktree per slice: `frontlights.py slice open`',
                       '`homolog.py merge`, the local main entering the integration branch, never the issue branch '
                       '("Into the local main")',
                       'A denied operation runs only after the "Sim" of its own question naming the exact command.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('**Denied operations are asked one at a time.**', text)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('`gh issue develop <n> --repo <repo> --base <base> --name <branch_prefix>issue-<n>`',
                       '`git fetch origin <branch_prefix>issue-<n>`',
                       '`git worktree add <path> <branch_prefix>issue-<n>`',
                       'links it to the Development field of the issue',
                       '`git push origin <branch_prefix>issue-<n>`',
                       'the branches of the slices, the preview branch and the local main stay local and are never pushed',
                       'never a commit that is only in the local main',
                       'the local main never enters a pushed branch',
                       'writing the remote main (`origin/main`, the base branch on GitHub)',
                       'the local main is written only by the covered merge',
                       '`gates` `{"browser_gate": "answered"}` (or `not_needed`), the only gate',
                       '`merge_into_local_main`', 'the session asks the user with `AskUserQuestion` instead of merging'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        for gone in ('pushing the work branches', 'one issue branch and one PR', 'write the base branch',
                     'cut from the local main and kept local'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)
        for gone in ('stays local and is never pushed', 'Nothing of an issue goes to GitHub before the release',
                     '`git branch <branch_prefix>issue-<n> main`', 'the branches of the issue and of its slices stay local',
                     'the branch of the issue stays local, never pushed'):
            with self.subTest(file='development.md', gone=gone):
                self.assertNotIn(gone, development)

    def test_the_local_main_enters_through_a_local_integration_branch(self):
        """Issue 70, S2: a main local entra por uma branch local de integração, e a branch remota da issue nunca a
        recebe; os merges cobertos, o teste livre, a skill, a segurança, o README, o handoff, o exemplo e a limpeza
        dizem isso."""
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ("a base into an issue's own branch or into its local integration branch "
                       "(`<branch_prefix>issue-<n>-integra`",
                       'the branch of the issue into its local integration branch',
                       'the local integration branch of the issue into the local main',
                       'brings the branch of the issue and the local main into its integration branch',
                       'Work without an issue has no integration branch'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        for gone in ('by steps 1, 4 and 5 of "Into the local main"',
                     'the branch of the issue into the local main once its watched run'):
            with self.subTest(file='development.md', gone=gone):
                self.assertNotIn(gone, development)
        skill = stage(6)
        # redesenho, issue 3: a mesma regra em palavras novas.
        self.assertIn('the local main entering the integration branch, never the issue branch', skill)
        self.assertNotIn('the local main brought into the branch of the issue,', skill)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        self.assertIn('só da worktree de integração da issue (`<prefixo>issue-<n>-integra`, cortada da branch da issue', security)
        self.assertNotIn('a main local é trazida para a branch da issue', flat('README.md'))  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        handoff = read('skills', 'frontlights', 'templates', 'handoff.md')
        self.assertIn('a main local trazida para a branch local de integração', handoff)
        self.assertNotIn('a main local trazida para a branch da issue;', handoff)
        op = json.loads(read('skills', 'frontlights', 'examples', 'operation-merge-local-main.json'))
        self.assertEqual((op['branch'], op['worktree']), ('claude/issue-1-integra', 'REPLACE_WITH_ABSOLUTE_INTEGRATION_WORKTREE_PATH'))
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        self.assertIn('the local integration worktree of each issue (`<branch_prefix>issue-<n>-integra`)', closeout)

    def test_the_direct_path_keeps_a_local_branch(self):
        """Issue 70, S1: o trabalho sem issue não tem issue a que ligar a branch, então a branch dele fica local."""
        development = flat('skills', 'frontlights', 'references', 'development.md')
        self.assertIn('Its branch has no issue to link: it is cut from the local main and stays local, never pushed',
                      development)

    def test_the_first_watched_run_compares_the_remote_base_with_the_branch_of_the_issue(self):
        """Issue 70, S1: ANTES na base do GitHub (`origin/<base>`), DEPOIS na branch da issue, no banco local."""
        browser = flat('skills', 'frontlights', 'references', 'browser-testing.md')
        for phrase in ('ANTES runs the `Fluxo:` on the remote base of the batch (`origin/<base>`, the base the branch '
                       'of the issue was created from)',
                       'a detached-HEAD worktree made with `git worktree add` at `origin/<base>`',
                       '"ANTES: origin/main"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, browser)
        self.assertNotIn('"ANTES: main" on the main', browser)

    def test_the_development_reference_has_the_watched_run_section_after_the_review(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertEqual(text.count(LOCAL_MAIN), 1)
        self.assertLess(text.index('## Review, checkpoints and renewal'), text.index('## Into the local main'))
        self.assertLess(text.index('## Into the local main'), text.index('## The release'))
        body = ' '.join(text.split(LOCAL_MAIN)[1].split(RELEASE)[0].split())
        for phrase in ('homologation bench', 'refused as the remote main',
                       '**Bring the local main in, on a local integration branch.**',
                       '`git worktree add -b <branch_prefix>issue-<n>-integra <path> <branch_prefix>issue-<n>`',
                       '`{issue: n, path, branch: <branch_prefix>issue-<n>-integra}`', 'local and never pushed',
                       'The branch of the issue never receives the local main',
                       '`git merge main`', 'The watched run is the only gate of stage 6: no impact suite and no '
                       'review is required.', '**The gate, the watched run.**', '**The check and the merge.**',
                       '`merge_into_local_main`',
                       '`examples/operation-merge-local-main.json`', '`git merge --no-ff <branch_prefix>issue-<n>-integra`',
                       'it never edits the gates to make them pass', '**Record it.**', '"Merge na main local"',
                       '**Without a screen, the walkthroughs.**', 'running the walkthrough of each box',
                       'a preflight, not a barrier', 'it reads no Git'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        for gone in ('**Gate 1, the impact suite.**', '**Gate 2, the review.**', 'The whole suite waits for the release.',
                     '`full_suite`', '**Bring the local main in first.**', 'the branch of the issue holds the local main',
                     'is not pushed after step 1', "In the issue's worktree, `git merge main`"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, body)
        whole = ' '.join(text.split())
        for phrase in ('one merge into the local main per issue', 'delivered by one merge into the local main',
                       'the branches of the slices, the preview branch and the local main stay local',
                       'writing the remote main (`origin/main`, the base branch on GitHub)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, whole)
        for gone in ('pushing the work branches', 'Draft PRs are covered', 'delivered in one PR'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, whole)

    def test_the_review_runs_only_on_request_and_is_no_gate(self):
        """Decisão de 20/10/2026: a revisão independente roda só a pedido e não é portão do merge na main local
        nem da release; uma revisão vencida não chama a suíte de impacto."""
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = ' '.join(text.split('## Review, checkpoints and renewal')[1].split('## Into the local main')[0].split())
        self.assertIn('The independent review runs only when the user asks for one: it is not dispatched by default '
                      'and is not a gate of the merge into the local main nor of the release.', body)
        self.assertIn("whether to review again is the user's call", body)
        self.assertNotIn('impact suite rerun on the new tip', body)

    def test_the_security_notes_cover_the_homolog_suites(self):
        """Revisão da issue 52, B2: o `inspect` aceita `suites` dentro de `homolog`, e o `homolog suite` está entre
        os comandos lidos do config, com o filtro de shell do `checks`, sem shell e com a árvore morta no prazo."""
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('dentro de `homolog`, qualquer chave além de `backupDir` e `suites`',
                       'as suítes da homologação (`homolog suite`)',
                       'blocos `browserTest`, `checks` e `homolog.suites`; no `homolog suite`, também o `--argv` que a '
                       'sessão passa',
                       'O `homolog suite` aplica ao argv de `homolog.suites` e ao `--argv` o mesmo filtro de shell do '
                       '`checks`, roda sem shell e, no prazo, mata a árvore inteira de processos.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn('qualquer outra chave dentro de `homolog`', security)

    def test_the_protocol_and_the_security_notes_tell_the_local_main_from_the_remote(self):
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('criada no GitHub a partir da `origin/<base>` por `gh issue develop`, ligada à issue e enviada a '
                       'cada fatia mesclada, entra na main local por merge só com o teste assistido respondido ou '
                       'dispensável, o único portão',
                       '"Standing authorization and the denied operations"', 'em "Into the local main"',
                       'a saída do `authorize` do merge na main local'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Main local e main remota.**',
                       '`merge_into_local_main` só com `target` igual a `base.branch`', 'são recusados como main remota',
                       'nunca de uma slice',
                       'e com o `gates` de "Into the local main" (`references/development.md`), só o `browser_gate`, '
                       'o único portão',
                       'um `browser_gate` fora de `answered` ou `not_needed` é recusado nomeando o portão',
                       'e `suite_gate` e `review_gate`, quando vêm, são aceitos sem exigência',
                       'não prova que o teste assistido foi respondido',
                       'conferência prévia, não barreira', 'não lê o Git',
                       'confere `edit`, `test`, `checkpoint` e `merge_into_local_main`',
                       'os merges cobertos de `references/development.md` ("Standing authorization and the denied operations"), os únicos permitidos'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        for name, text in (('protocol', protocol), ('security', security)):
            with self.subTest(file=name):
                self.assertNotIn('enviar as branches de trabalho', text)
                self.assertNotIn('escrever na branch base ou protegida', text)
                self.assertNotIn('cortada da main local e nunca enviada', text)
        self.assertIn('A branch da issue é a única branch de trabalho enviada antes da release', security)

    def test_the_readme_the_handoff_and_the_examples_follow(self):
        readme = flat('README.md')
        for phrase in ('empurra a branch da issue', 'O trabalho aprovado entra na sua `main` local, nunca na remota'):  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        for gone in ('cortadas da main local do projeto (a homologação) e ficam só locais até a release',
                     'nada da issue vai ao GitHub antes da release', 'numa branch por issue, cortada da main local'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, readme)
        self.assertNotIn('a branch da issue é cortada da main local e nunca enviada',
                         read('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertNotIn('enviar as branches, abrir PRs rascunho', readme)
        handoff = read('skills', 'frontlights', 'templates', 'handoff.md')
        self.assertIn('- Merge na main local (', handoff)
        self.assertIn('`merge_into_local_main`', handoff)
        charter = json.loads(read('skills', 'frontlights', 'examples', 'authorization.json'))
        self.assertIn('merge_into_local_main', charter['operations'])
        self.assertEqual(charter['base']['branch'], 'main')
        op = json.loads(read('skills', 'frontlights', 'examples', 'operation-merge-local-main.json'))
        self.assertEqual((op['kind'], op['target']), ('merge_into_local_main', 'main'))
        self.assertEqual(op['gates'], {'browser_gate': 'answered'})
        # the example operation passes `authorize` against the example charter once the placeholders are filled
        with tempfile.TemporaryDirectory() as temp:
            charter = dict(charter, approved_by='usuário', approval_reference='autorização permanente',
                           expires_at='2099-01-01T00:00:00+00:00',
                           monitoring=dict(charter['monitoring'], confirmed_by='usuário'),
                           worktrees=[dict(next(w for w in charter['worktrees'] if w['branch'] == op['branch']),
                                           path=temp)])
            self.assertEqual(frontlights.authorize(charter, dict(op, worktree=temp))['scope_check'], 'pass')

    def test_the_sync_opens_stage_six(self):
        """S2 e a decisão de 20/10/2026: a skill, a referência, o protocolo, a segurança e o README dizem quando o
        sync roda e o que pergunta, que nenhum hook é instalado, e declaram as duas escritas da skill dentro de
        `.git/`."""
        skill = stage(6)
        # redesenho, issue 3: o passo "Sync" virou oração com o ponteiro; o que o sync faz vive em development.md.
        self.assertIn('`homolog sync` and the preview ("The start of stage 6")', skill)
        self.assertNotIn('homolog hook', skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        heading = '\n## The start of stage 6\n'
        self.assertLess(text.index(heading), text.index('## Slices in order'))
        body = ' '.join(text.split(heading)[1].split('## Slices in order')[0].split())
        for phrase in ('`homolog sync --root <main worktree> --base <base>', 'never pushes',
                       '"Resolver o conflito agora na worktree principal"', '"Seguir sem sincronizar"',
                       '`scripts/homolog.py`', 'exit code 0 done, 1 refused or failed, 2 a question for the user',
                       'The local main is never pushed to the remote main: its content leaves only under the release '
                       'branch name, by the refspec push of the release ("The release", below), and `origin/<base>` '
                       'stays a denied write.',
                       '**The sync.**', 'is the covered merge of `origin/<base>` into the local main',
                       'no tracked change pending and no merge in progress',
                       '`git fetch <remote>` and `git merge --no-edit <remote>/<base>`', '`git merge --abort`',
                       'never uses `--force`, `reset` or `rebase`', 'runs again before the release'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        for gone in ('**The hook.**', 'pre-push', '"Sim, instalar"', '`--no-verify`'):
            with self.subTest(file='development.md', gone=gone):
                self.assertNotIn(gone, ' '.join(text.split()))
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('O Frontlights não instala hook nenhum.',
                       'A regra de que a main local do projeto, a homologação, nunca é enviada à main remota (o conteúdo dela só '
                       'sai para o nome da branch da release, pelo push da release) é regra da skill, não barreira.', 'As escritas da skill dentro de `.git/` são duas',
                       '`.git/info/exclude`', '`frontlights-serve/ports/`',
                       '**Sincronização da main local (`homolog sync`).**', 'Nunca envia, nunca usa `--force`, `reset` nem `rebase`',
                       'é merge coberto (`references/development.md`, "Standing authorization and the denied operations")'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn('Esse `pre-push` é o único hook que o Frontlights instala', security)
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('a sincronização da main local e a prévia, em "The start of stage 6"', protocol)
        readme = flat('README.md')
        self.assertIn('Nenhum hook bloqueia nada: a skill não instala hook', readme)  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        self.assertNotIn('instala só o hook `pre-push` da homologação', readme)
        self.assertIn('confirm that no hook is installed or asked about', flat('evals', 'runbook.md'))

    def test_the_bundle_follows_each_merge_into_the_local_main(self):
        """S3: a skill, a referência, o protocolo, a segurança, o README e o exemplo de config dizem quando o bundle
        é gravado, onde, e que sem a chave nada é gravado."""
        # redesenho, issue 3: "o merge, depois o bundle" saiu da etapa 6; a ordem vive nos passos de development.md.
        self.assertIn('("Into the local main")', stage(6))
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = ' '.join(text.split(LOCAL_MAIN)[1].split(RELEASE)[0].split())
        self.assertLess(body.index('4. **The check and the merge.**'), body.index('5. **Back it up.**'))
        for phrase in ('5. **Back it up.**', 'homolog bundle --root <main worktree> --config',
                       'the only write the run makes outside the project, and only into that folder',
                       '`homolog.backupDir`', '`git bundle verify`', 'old bundles are never deleted',
                       '`configured: false`', 'name the key, ask nothing and go on', '6. **Record it.**',
                       '"sem backup configurado"'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Backup da main local (`homolog bundle`).**', 'a única gravação da execução fora do projeto',
                       'o utilitário nunca a cria', 'nunca se sobrescreve nem se apaga um bundle', 'não há rede',
                       'nunca entra neste repositório', 'A chave só diz onde gravar'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn('o portão do merge na main local (o teste assistido) e o bundle depois dele, em "Into the local main"',
                      flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('backup da homologação', flat('README.md'))  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        example = json.loads(read('skills', 'frontlights', 'examples', 'config.json'))
        self.assertIsNone(example['homolog']['backupDir'])
        self.assertIn('S3: `homolog bundle` grava', flat('docs', 'acceptance.md'))
        self.assertIn('one `.bundle` file there which `git bundle verify` accepts', flat('evals', 'runbook.md'))

    def test_the_bundle_follows_the_prefixes_of_the_records(self):
        """Issue 44, S1: o backup leva as branches de todo `branch_prefix` dos registros, sem `--prefix` na chamada."""
        step = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('the local main and the work branches of every `branch_prefix` in the authorization records '
                       '(`.frontlights/authorization*.json`; `claude/` when there is none',
                       '`--prefix` names one prefix alone', '`prefixes`, `prefixSource` and `skipped`'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, step)
        self.assertNotIn('the local main and every branch under the `branch_prefix`', step)

    def test_the_release_name_follows_the_newest_record(self):
        """Issue 44, S2: o nome da release usa o prefixo do registro de autorização mais recente, sem `--prefix`."""
        release = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ("the prefix of the newest authorization record by `issued_at` (records without a valid `issued_at` "
                       "rank below those with one, and ties go to the last file name; `claude/` when there is none; "
                       "`--prefix` names it alone", '`prefix` and `prefixSource` say which'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, release)
        self.assertIn('records without a valid `issued_at` rank below those with one', release)
        self.assertIn('say in one line how many records `skipped` counts', release)
        for file in (('skills', 'frontlights', 'docs', 'protocol.md'),):  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
            with self.subTest(file=file[-1]):
                text = flat(*file)
                self.assertIn('o prefixo do registro de autorização mais recente', text)
                self.assertIn('os registros sem `issued_at` válido ficam abaixo dos que têm, e o empate vai para o', text)
        self.assertIn('das branches de trabalho de todo `branch_prefix` dos registros de autorização',
                      flat('skills', 'frontlights', 'docs', 'security.md'))

    def test_the_release_replaces_the_pull_request_per_issue(self):
        """S4: a release é oferecida ao fim de cada issue homologada e substitui a espera do merge por issue; os
        textos que diziam "antes do PR" dizem "antes do merge na main local"."""
        skill = stage(6)
        # redesenho, issue 3: o passo 8 virou os comandos da release com o ponteiro; "oferecida ao fim de cada issue
        # homologada" vive em development.md, "The release" (fixado em
        # test_the_free_test_sits_between_the_local_main_and_the_release).
        self.assertIn('`homolog.py release plan`, `release go`, `release status` until the user merges, `release landed` '
                      '("The release")', skill)
        self.assertIn('before such an issue is merged into the local main, and before a PR is opened or updated',
                      flat('skills', 'frontlights', 'references', 'browser-testing.md'))
        self.assertNotIn("After a PR is opened, wait for the user's merge by default", skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertNotIn('## After the pull request', text)
        self.assertIn(RELEASE + '\nFrom the local main to GitHub.', text)
        self.assertIn('## Integrating a family before the local main', text)
        body = ' '.join(text.split(RELEASE)[1].split())
        for phrase in ('**Plan it.**', 'homolog release-plan --root <main worktree> --base <base>', '**Offer it.**',
                       '"Lançar a release com as issues #a, #b agora?"', '"Sim, lançar" first and "Agora não" second',
                       '`gh pr create --base <base> --head <release branch>', 'The body follows `templates/pr.md`',
                       '**Branch and pull request (covered).**', '`git push origin main:refs/heads/<release branch>`',
                       'never to the remote main, and no local release branch is created',
                       '**When the host refuses the refspec push.**',
                       'the old path: `git branch <release branch> <base>` and `git push -u origin <release branch>`',
                       'the cleanup removes that local branch once it is merged (`references/closeout.md`, step 5)',
                       '**`Closes #n` only from `closes`.**', '**Wait for the merge.**', '**Offer the merge when the PR is ready.**',
                       '**What wakes the session.**', '**What counts as merged.**', '**At the merge.**',
                       '`git pull --ff-only origin <base>`', '**Other work goes on.**',
                       'No suite is required for the release (no whole check is: the watched run of each issue is its '
                       'evidence)',
                       'the whole suite on the local main (`homolog suite --release --mode full`, judged by `homolog '
                       'suite-gate --release`) runs only when the user asks for it, and a red one is then a finding '
                       'with a destination by the ladder',
                       "The release's pull request is ready when the watched run of every issue in it is recorded "
                       '(answered or not needed), the pull request has no conflict with the base and no finding lacks '
                       'a destination.',
                       'Another issue entering the local main does not make the pull request unready.'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        self.assertLess(body.index('**Plan it.**'), body.index('**Offer it.**'))
        self.assertLess(body.index('`git push origin main:refs/heads/<release branch>`'),
                        body.index('**When the host refuses the refspec push.**'))
        self.assertLess(body.index('**When the host refuses the refspec push.**'),
                        body.index('`git push -u origin <release branch>`'))
        whole = ' '.join(text.split())
        for never in ('main:main', 'main:refs/heads/main', 'git push origin main`', 'git push origin <base>',
                      'git push origin HEAD', 'git push -u origin main', 'git push origin origin/'):
            with self.subTest(never=never):
                self.assertNotIn(never, whole)
        start = whole.find('git push origin main')
        self.assertNotEqual(start, -1)
        while start != -1:
            with self.subTest(at=start):
                self.assertTrue(whole.startswith('git push origin main:refs/heads/<release branch>', start),
                                whole[start:start + 60])
            start = whole.find('git push origin main', start + 1)
        for gone in ('**Run the whole suite on the local main.**', '`fullSuite` must be `current`',
                     'the whole suite of the release is green at the tip the release branch was cut from'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, body)
        self.assertNotIn('recordedHead', body.split('**Offer the merge when the PR is ready.**')[1].split('**What wakes')[0])
        self.assertNotIn('run the full relevant suite', ' '.join(text.split()))
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('| Release |', 'A release é oferecida ao fim de cada issue homologada',
                       '"Agora não" deixa a issue homologada na main local',
                       'sem suíte obrigatória (a suíte inteira só a pedido do usuário)',
                       'release/suite.json a suíte inteira da release (`homolog suite --release`, só a pedido do usuário)',
                       'release/suite-full-<data-hora>.log',
                       'release/suite-<sha>.json cópia do mesmo registro por ponta (o sha completo do head), que a '
                       'execução numa ponta seguinte não sobrescreve; `homolog suite-gate --release --head <sha>` a '
                       'julga'):
            with self.subTest(file='protocol.md', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertNotIn('| Espera do merge |', protocol)
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        # redesenho, issue 3: closeout.md abre dizendo de onde a release a entrega, em palavras novas.
        for phrase in ('The release of stage 6 (`development.md`, "The release") hands over here', 'the issue closes with the release that carries it',
                       '`contained_in_base_without_pull_request`'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)
        self.assertIn('`homolog.py release`', flat('README.md'))  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        self.assertIn('- Release (a saída do `release-plan`', read('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertIn('a suíte inteira na ponta da main local só quando o usuário a pediu',
                      flat('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertIn('S4: `homolog release-plan` (só leitura)', flat('docs', 'acceptance.md'))
        self.assertIn('# Release from the local main, closing, parent tick and cleanup', read('evals', 'merge-wait-and-cleanup.md'))

    def test_the_free_test_sits_between_the_local_main_and_the_release(self):
        """Issue 69, S3: numa issue com tela, o teste livre abre sem pergunta depois do merge na main local e do
        bundle, e a pergunta da release só vem quando o usuário fecha a janela."""
        text = read('skills', 'frontlights', 'references', 'development.md')
        local, free, release = (LOCAL_MAIN, '## The free test on the local main', RELEASE)
        for heading in (local, free, release):
            with self.subTest(heading=heading):
                self.assertEqual(text.count(heading), 1)
        self.assertLess(text.index(local), text.index(free))
        self.assertLess(text.index(free), text.index(release))
        body = ' '.join(text.split(free)[1].split(release)[0].split())
        for phrase in ('In an issue whose `browser-gate` was `answered`', 'without a question',
                       'the window, the login, the strip and the holder are in `references/browser-testing.md`, '
                       '"The free test window"',
                       'served from the main worktree, on the local main, on the local development database',
                       'The user leads', 'One free test per homologated issue',
                       "the next issue's free test covers everything accumulated in the local main",
                       'Closing the window right away is how the user skips it',
                       'stops what it started for the free test (`serve stop` on the main worktree, "The free test window")',
                       'the release question comes only after the window is closed'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        offer = ' '.join(text.split(release)[1].split('- **Plan it.**')[0].split())
        self.assertIn('offered by the session at the end of each homologated issue, once the window of its free test '
                      'is closed ("The free test on the local main", above)', offer)
        self.assertNotIn('right after the merge into the local main and the bundle', offer)
        skill = stage(6)
        # redesenho, issue 3: os passos 6 a 8 viraram orações com o comando e o ponteiro, na mesma ordem.
        six = '`homolog.py merge`'
        seven = '`serve.py free-test start` ("The free test on the local main")'
        eight = '`homolog.py release plan`'
        for item in (six, seven, eight):
            with self.subTest(file='SKILL.md', item=item):
                self.assertIn(item, skill)
        self.assertLess(skill.index(six), skill.index(seven))
        self.assertLess(skill.index(seven), skill.index(eight))
        self.assertNotIn('7. **The release**', skill)
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('o teste livre na main local, em "The free test on the local main"',
                       'Ao fim de cada issue homologada, depois de fechada a janela do teste livre'):
            with self.subTest(file='protocol.md', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertIn('M --> L["Teste livre<br/>na main local"]', flat('README.md'))  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill

    def test_a_fix_in_the_free_test_is_made_at_once_and_its_criteria_go_in_one_batch(self):
        """Issue 69, S4: uma correção pedida no teste livre é feita na hora na branch da issue e mesclada de novo na
        main local; cada correção vira um CA novo no rascunho local; ao fechar a janela, um lote aprovado por link e
        carimbo é escrito só por acréscimo, e só então vem a release; sem correção, a release vem direto."""
        text = read('skills', 'frontlights', 'references', 'development.md')
        free, release = '## The free test on the local main', RELEASE
        body = ' '.join(text.split(free)[1].split(release)[0].split())
        fix = body.split('- **A fix asked in the free test.**')[1].split('- **Window closed, next step.**')[0]
        for phrase in ('fixes it at once on the branch of the issue',
                       'or in a new slice worktree of that issue ("Slices in order", above)',
                       'TDD by default ("Which tests run when", above)',
                       'pushes the branch of the issue again (covered)',
                       'merges that branch into the local main again by steps 4 and 5 of "Into the local main"',
                       'the `authorize` check included',
                       'the free test itself is the evidence of the fix, and the watched run is not rerun',
                       'the user reloads the page', 'the window stays open',
                       '`.frontlights/issues/<n>/teste-livre-cas.md`', 'one box per fix',
                       'ticked (`- [x]`) only when the user checked the fix in the free test',
                       'open (`- [ ]`) otherwise',
                       'leftover boxes (`references/issues.md`, "A leftover as an acceptance criterion")'):
            with self.subTest(part='fix', phrase=phrase):
                self.assertIn(phrase, fix)
        closed = body.split('- **Window closed, next step.**')[1]
        for phrase in ('With fixes, the batch before the release',
                       'by link and stamp (`SKILL.md`, "Show before approval")',
                       'one approval for the whole file',
                       'the write rule of the leftover (body captured, append only, difference checked, reread)',
                       'Without fixes, the release comes directly',
                       'the release question comes only after the window is closed'):
            with self.subTest(part='closed', phrase=phrase):
                self.assertIn(phrase, closed)
        self.assertLess(closed.index('With fixes, the batch before the release'),
                        closed.index('Only then it goes on to "The release"'))
        self.assertEqual(' '.join(text.split()).count('teste-livre-cas.md'), 1)
        self.assertNotIn('Lançar a release', body)

    def test_without_a_screen_the_free_test_is_in_the_terminal(self):
        """Issue 69, S5: num projeto sem tela (`browser-gate` `not_needed`), o teste livre acontece no terminal: os
        comandos para usar a main local e a pergunta de fim do teste antes da release; só o "Sim, terminei" leva à
        release, e uma correção pedida ali segue a regra da S4."""
        question = 'Terminou de testar a main local?'
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertEqual(text.count(question), 1)
        skill_dir = ROOT / 'skills' / 'frontlights'
        for path in sorted((skill_dir / 'references').glob('*.md')) + [skill_dir / 'SKILL.md']:
            if path.name == 'development.md':
                continue
            with self.subTest(file=path.name):
                self.assertNotIn(question, ' '.join(path.read_text(encoding='utf-8').split()))
        free, release = '## The free test on the local main', RELEASE
        body = ' '.join(text.split(free)[1].split(release)[0].split())
        terminal = body.split('- **Without a screen, in the terminal.**')[1].split('- **')[0]
        for phrase in ('In an issue whose `browser-gate` said `not_needed`', 'no window opens and no product is served',
                       'right after the merge into the local main and the bundle',
                       "in one line, in the user's language, that the local main is ready for the user to try",
                       'each in its own code block', "the charter's `verification_commands` or what `inspect` reports",
                       'never a secret', f'asks with `AskUserQuestion` "{question}"',
                       '"Sim, terminei" first', '"Ainda testando" leaves the question pending',
                       'asks it again when the user comes back', 'never answers it for the user',
                       'Only after "Sim, terminei"', 'follows "A fix asked in the free test", below'):
            with self.subTest(part='terminal', phrase=phrase):
                self.assertIn(phrase, terminal)
        self.assertLess(body.index('- **Without a screen, in the terminal.**'),
                        body.index('- **A fix asked in the free test.**'))
        closed = body.split('- **Window closed, next step.**')[1]
        for phrase in ("without a screen, the user's \"Sim, terminei\" in its place",
                       'without a screen, only after "Sim, terminei"'):
            with self.subTest(part='closed', phrase=phrase):
                self.assertIn(phrase, closed)
        # redesenho, issue 3: o teste livre sem tela saiu da etapa 6; vive em development.md (fixado acima), para
        # onde a etapa aponta.
        self.assertIn('`serve.py free-test start` ("The free test on the local main")', stage(6))
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('sem tela, o teste livre acontece no terminal: os comandos para usar a main local e a pergunta '
                      'de fim do teste, e só o "Sim, terminei" leva à release', protocol)

    def test_the_closeout_waits_for_the_release(self):
        """S5: o fechamento documenta `awaiting_release` na referência, na etapa 1 da skill, no protocolo, na
        segurança e no README."""
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        for phrase in ('`awaiting_release` with the branch, its tip, the base and the remote',
                       'keeps such an issue out as `awaiting_release` until `origin/<base>` holds its branch',
                       'never excludes on a doubt', '`releaseCheck` says `checked`, `skipped` or `unavailable`',
                       'An `awaiting_release` is said to the user in one line'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)
        # redesenho, issue 3: a etapa 1 diz em palavras novas; a regra inteira vive em closeout.md.
        self.assertIn('`awaiting_release` in one line', stage(1))
        self.assertIn('An `awaiting_release` is said to the user in one line, never proposed', closeout)
        self.assertIn('fica fora como `awaiting_release` até a release que a leva ser mesclada',
                      flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('senão `awaiting_release`; as únicas leituras de Git são `rev-parse` e `merge-base`',
                      flat('skills', 'frontlights', 'docs', 'security.md'))
        self.assertIn('S5: `closeout.py candidates` exclui como `awaiting_release`', flat('docs', 'acceptance.md'))
        self.assertIn('the issue waits for the release (`awaiting_release`)', flat('evals', 'runbook.md'))

    def test_the_acceptance_record_and_the_runbook_track_it(self):
        self.assertIn('| 27. Homologação na main local: merge com portões e release por PR única (issue 32) | Pendente |',
                      flat('docs', 'acceptance.md'))
        self.assertIn('27. Local main as homologation (issue 32).', flat('evals', 'runbook.md'))


HOMOLOG = SKILL / 'scripts' / 'homolog.py'
FRONTLIGHTS = SKILL / 'scripts' / 'frontlights.py'
CONFIG = (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'), ('commit.gpgsign', 'false'))


def isolated(base):
    """The Git environment of a fixture: the empty `gitconfig` of `base` as the global one, no system one."""
    return dict(os.environ, GIT_CONFIG_GLOBAL=str(Path(base) / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                GIT_TERMINAL_PROMPT='0')


def build_git(env, cwd, *args):
    """A checked Git command of the class template, under the isolated environment."""
    prefix = ['git', '-C', str(cwd)] if cwd else ['git']
    done = subprocess.run([*prefix, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                          env=env, stdin=subprocess.DEVNULL, timeout=60)
    if done.returncode != 0:
        raise AssertionError(f'git {" ".join(args)}: {done.stderr}')


def build_commit(env, repo, name, content, message):
    (repo / name).write_text(content, encoding='utf-8')
    build_git(env, repo, 'add', name)
    build_git(env, repo, 'commit', '-q', '-m', message)


def build_trio(folder):
    """The template of the sync and release-plan tests: `origin.git` (bare), `work` pushed to it and `other`
    cloned from it, all inside `folder`; `gitfixture.copy` points the remotes of a copy at its own `origin.git`."""
    (folder / 'gitconfig').write_text('', encoding='utf-8')
    env = isolated(folder)
    origin, work, other = folder / 'origin.git', folder / 'work', folder / 'other'
    build_git(env, None, 'init', '-q', '--bare', '-b', 'main', str(origin))
    build_git(env, None, 'init', '-q', '-b', 'main', str(work))
    for key, value in CONFIG:
        build_git(env, work, 'config', key, value)
    build_commit(env, work, 'README.md', 'first\n', 'first')
    build_git(env, work, 'remote', 'add', 'origin', str(origin))
    build_git(env, work, 'push', '-q', '-u', 'origin', 'main')
    build_git(env, None, 'clone', '-q', str(origin), str(other))
    for key, value in CONFIG:
        build_git(env, other, 'config', key, value)


class HomologCli:
    """The `homolog` command line of the tests. By default `homolog.main` runs in this process with the argument
    list, the stdout captured and the isolated Git environment applied only during the call (the Git that homolog
    runs inherits it); `real=True`, and every call through `frontlights.py`, starts a real process."""

    def cli(self, *args, script=HOMOLOG, real=False):
        if real or script != HOMOLOG:
            done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL,
                                  timeout=180)
            code, stdout, stderr = done.returncode, done.stdout, done.stderr
        else:
            out = io.StringIO()
            with mock.patch.dict(os.environ, self.env, clear=True), contextlib.redirect_stdout(out):
                code = homolog.main(list(args))
            stdout, stderr = out.getvalue(), ''
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError:
            self.fail(f'sem JSON no stdout (saída {code}): {stdout!r} {stderr!r}')
        self.assertEqual(result['exitCode'], code)
        return code, result


class HomologSyncTests(HomologCli, unittest.TestCase):
    """S2: `homolog sync` traz `origin/main` para a main local e relata conflito deixando a worktree limpa; o
    `homolog hook` saiu (decisão de 20/10/2026) e é uma operação desconhecida. Só repositórios temporários: o
    remoto é um repositório bare no mesmo disco, e a configuração Git da máquina fica fora da fixture. O trio
    (origin, work, other) é montado uma vez por classe e copiado para cada teste (issue #59)."""

    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build_trio)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = gitfixture.copy(self.template, Path(self.temp.name), exist_ok=True)
        self.env = isolated(base)
        self.origin = base / 'origin.git'
        self.work = base / 'work'
        self.other = base / 'other'

    def git(self, cwd, *args, check=True):
        prefix = ['git', '-C', str(cwd)] if cwd else ['git']
        done = subprocess.run([*prefix, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=self.env, stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(done.returncode, 0, f'git {" ".join(args)}: {done.stderr}')
        return done

    def configure(self, repo):
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git(repo, 'config', key, value)

    def commit(self, repo, name, content, message):
        (repo / name).write_text(content, encoding='utf-8')
        self.git(repo, 'add', name)
        self.git(repo, 'commit', '-q', '-m', message)
        return self.sha(repo)

    def sha(self, repo, ref='HEAD'):
        return self.git(repo, 'rev-parse', ref).stdout.strip()

    def sync(self, real=False):
        return self.cli('sync', '--root', str(self.work), real=real)

    def test_sync_advances_the_local_main_when_the_remote_moved(self):
        before = self.sha(self.work)
        tip = self.commit(self.other, 'remote.txt', 'remote\n', 'remote work')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        code, result = self.sync(real=True)   # the real `homolog.py sync` process
        self.assertEqual(code, 0, result)
        self.assertEqual((result['before'], result['after'], result['advanced'], result['fastForward'],
                          result['remoteTip']), (before, tip, True, True, tip))
        self.assertEqual(self.sha(self.work), tip)
        self.assertIn('remote work', self.git(self.work, 'log', '-1', '--format=%s').stdout)
        self.assertEqual(self.git(self.work, 'status', '--porcelain').stdout, '')

    def test_sync_with_nothing_new_changes_nothing(self):
        before = self.sha(self.work)
        code, result = self.sync()
        self.assertEqual(code, 0, result)
        self.assertEqual((result['before'], result['after'], result['advanced']), (before, before, False))
        self.assertEqual(self.sha(self.work), before)

    def test_sync_reports_a_conflict_and_leaves_the_worktree_clean(self):
        before = self.commit(self.work, 'README.md', 'local line\n', 'local change')
        self.commit(self.other, 'README.md', 'remote line\n', 'remote change')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        code, result = self.sync()
        self.assertEqual(code, 2, result)
        self.assertEqual((result['conflict'], result['files'], result['before']), (True, ['README.md'], before))
        self.assertEqual(result['remoteTip'], self.sha(self.other))
        self.assertIn('README.md', result['message'])
        self.assertEqual(self.git(self.work, 'status', '--porcelain').stdout, '')
        merging = self.git(self.work, 'rev-parse', '--verify', '--quiet', 'MERGE_HEAD', check=False)
        self.assertNotEqual(merging.returncode, 0)
        self.assertEqual(self.sha(self.work), before)

    def test_sync_needs_a_clean_worktree_on_the_base_branch(self):
        (self.work / 'README.md').write_text('dirty\n', encoding='utf-8')
        code, result = self.sync()
        self.assertEqual(code, 1, result)
        self.assertIn('não commitadas', result['message'])
        self.git(self.work, 'checkout', '-q', '--', 'README.md')
        self.git(self.work, 'switch', '-q', '-c', 'feature')
        code, result = self.sync()
        self.assertEqual(code, 1, result)
        self.assertIn('feature', result['message'])
        self.assertIn('main', result['message'])

    def test_the_frontlights_entry_gives_the_same_report_as_the_module(self):
        code, direct = self.sync()
        routed_code, routed = self.cli('homolog', 'sync', '--root', str(self.work), script=FRONTLIGHTS)
        self.assertEqual(routed_code, code)
        self.assertEqual(routed, direct)

    def test_the_hook_operation_is_gone(self):
        code, result = self.cli('hook', '--root', str(self.work), '--check')
        self.assertEqual((code, result['ok']), (1, False), result)
        self.assertFalse((self.work / '.git' / 'hooks' / 'pre-push').exists())


class HomologBundleTests(HomologCli, unittest.TestCase):
    """S3: `homolog bundle` grava um bundle Git da main local e das branches de trabalho na pasta de
    `homolog.backupDir`; sem a chave diz que não há pasta e não grava; `inspect` recusa a chave inválida e não
    muda a saída sem ela. Só repositórios e pastas temporários; a configuração Git da máquina fica fora. O
    repositório `work` (o nome dá o do bundle) e a pasta `backup` vazia são montados uma vez por classe e copiados
    para cada teste (issue #59)."""

    @staticmethod
    def build(folder):
        (folder / 'gitconfig').write_text('', encoding='utf-8')
        env = isolated(folder)
        work = folder / 'work'
        (folder / 'backup').mkdir()
        build_git(env, None, 'init', '-q', '-b', 'main', str(work))
        for key, value in CONFIG:
            build_git(env, work, 'config', key, value)
        build_commit(env, work, 'README.md', 'first\n', 'first')
        build_git(env, work, 'switch', '-q', '-c', 'claude/issue-1')
        build_commit(env, work, 'one.txt', 'one\n', 'issue 1')
        build_git(env, work, 'switch', '-q', '-c', 'claude/issue-1-s2')
        build_commit(env, work, 'two.txt', 'two\n', 'slice 2')
        build_git(env, work, 'switch', '-q', 'main')
        build_git(env, work, 'switch', '-q', '-c', 'other')
        build_commit(env, work, 'other.txt', 'other\n', 'outside the prefix')
        build_git(env, work, 'switch', '-q', 'main')

    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, cls.build)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = gitfixture.copy(self.template, Path(self.temp.name), exist_ok=True)
        self.env = isolated(self.base)
        self.work = self.base / 'work'
        self.backup = self.base / 'backup'

    def git(self, cwd, *args, check=True):
        prefix = ['git', '-C', str(cwd)] if cwd else ['git']
        done = subprocess.run([*prefix, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=self.env, stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(done.returncode, 0, f'git {" ".join(args)}: {done.stderr}')
        return done

    def commit(self, name, content, message):
        (self.work / name).write_text(content, encoding='utf-8')
        self.git(self.work, 'add', name)
        self.git(self.work, 'commit', '-q', '-m', message)

    def config(self, **extra):
        """Writes a config file outside the repository and returns its path."""
        path = self.base / 'config.json'
        path.write_text(json.dumps({'repository': None, **extra}), encoding='utf-8')
        return path

    def bundle(self, config, *flags, real=False):
        return self.cli('bundle', '--root', str(self.work), '--config', str(config), *flags, real=real)

    def written_files(self):
        return sorted(path.name for path in self.backup.iterdir())

    def test_bundle_writes_a_verifiable_file_with_the_base_and_the_work_branches(self):
        # the real `homolog.py bundle` process
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}, branchPrefix='claude/'), real=True)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['configured'], result['written'], result['verified']), (True, True, True))
        path = Path(result['path'])
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.parent, self.backup)
        self.assertEqual(path.suffix, '.bundle')
        self.assertTrue(path.stem.startswith('work-'))
        self.assertEqual(result['bytes'], path.stat().st_size)
        self.assertGreater(result['bytes'], 0)
        self.assertEqual(set(result['refs']), {'main', 'claude/issue-1', 'claude/issue-1-s2'})
        self.assertEqual(self.written_files(), [path.name])
        self.assertIn(path.name, result['message'])
        verify = self.git(self.work, 'bundle', 'verify', str(path), check=False)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        restored = self.base / 'restored'
        clone = self.git(None, 'clone', '-q', str(path), str(restored), check=False)
        self.assertEqual(clone.returncode, 0, clone.stderr)
        heads = self.git(restored, 'for-each-ref', '--format=%(refname:short)', 'refs/remotes/origin/').stdout.split()
        self.assertTrue({'origin/main', 'origin/claude/issue-1', 'origin/claude/issue-1-s2'} <= set(heads), heads)
        self.assertNotIn('origin/other', heads)
        self.assertEqual(self.git(restored, 'rev-parse', 'origin/claude/issue-1-s2').stdout,
                         self.git(self.work, 'rev-parse', 'claude/issue-1-s2').stdout)
        self.assertEqual(self.git(self.work, 'status', '--porcelain').stdout, '')

    def test_without_the_key_it_says_there_is_no_folder_and_writes_nothing(self):
        for extra in ({}, {'homolog': None}, {'homolog': {'backupDir': None}}, {'homolog': {}}):
            with self.subTest(extra=extra):
                code, result = self.bundle(self.config(**extra))
                self.assertEqual(code, 1, result)
                self.assertEqual((result['configured'], result['written'], result['ok']), (False, False, False))
                self.assertIn('homolog.backupDir', result['message'])
                self.assertEqual(self.written_files(), [])

    def test_a_folder_that_does_not_exist_is_refused_and_never_created(self):
        missing = self.base / 'missing'
        code, result = self.bundle(self.config(homolog={'backupDir': str(missing)}))
        self.assertEqual(code, 1, result)
        self.assertEqual((result['configured'], result['written']), (True, False))
        self.assertIn('não existe', result['message'])
        self.assertFalse(missing.exists())
        self.assertEqual(self.written_files(), [])
        (self.base / 'file.txt').write_text('x', encoding='utf-8')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.base / 'file.txt')}))
        self.assertEqual((code, result['configured'], result['written']), (1, True, False))

    def test_an_invalid_key_is_refused_before_anything_is_written(self):
        for value in ('relative/dir', '~/dir', 'C:/a/../b', '', 5):
            with self.subTest(value=value):
                code, result = self.bundle(self.config(homolog={'backupDir': value}))
                self.assertEqual(code, 1, result)
                self.assertIn('homolog.backupDir', result['message'])
                self.assertEqual(self.written_files(), [])
        code, result = self.bundle(self.config(homolog={'backupdir': str(self.backup)}))
        self.assertEqual(code, 1, result)
        self.assertIn('backupdir', result['message'])
        self.assertEqual(self.written_files(), [])

    def test_two_bundles_never_overwrite_each_other(self):
        config = self.config(homolog={'backupDir': str(self.backup)})
        code, first = self.bundle(config)
        self.assertEqual(code, 0, first)
        code, second = self.bundle(config)
        self.assertEqual(code, 0, second)
        self.assertNotEqual(first['path'], second['path'])
        self.assertTrue(Path(first['path']).is_file() and Path(second['path']).is_file())
        self.assertEqual(len(self.written_files()), 2)
        self.assertEqual(set(second['refs']), set(first['refs']))

    def test_the_prefix_and_the_base_are_checked(self):
        config = self.config(homolog={'backupDir': str(self.backup)})
        for prefix in ('claude', 'cl aude/', '../x/', 'x$/', ''):
            with self.subTest(prefix=prefix):
                code, result = self.bundle(config, '--prefix', prefix)
                self.assertEqual(code, 1, result)
                self.assertIn('prefixo', result['message'])
        code, result = self.bundle(config, '--prefix', '-x/')   # argparse reads it as an option: a usage refusal
        self.assertEqual(code, 1, result)
        code, result = self.bundle(config, '--base', 'nope')
        self.assertEqual(code, 1, result)
        self.assertIn('nope', result['message'])
        self.assertEqual(self.written_files(), [])
        code, result = self.bundle(config, '--prefix', 'other/')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['refs'], ['main'])

    def record(self, name, **data):
        """An authorization record in the `.frontlights` of the repository (issue 44)."""
        folder = self.work / '.frontlights'
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(json.dumps({'repository': 'OWNER/REPOSITORY', 'worktrees': [], **data}),
                                   encoding='utf-8')

    def team_branches(self):
        """Two work branches under a prefix other than `claude/`, cut from the base (issue 44)."""
        self.git(self.work, 'switch', '-q', '-c', 'equipe/issue-2')
        self.commit('three.txt', 'three\n', 'issue 2')
        self.git(self.work, 'switch', '-q', '-c', 'equipe/issue-2-s1')
        self.commit('four.txt', 'four\n', 'issue 2, slice 1')
        self.git(self.work, 'switch', '-q', 'main')

    def test_without_prefix_the_records_name_the_branches(self):
        """Issue 44, S1: sem `--prefix`, o bundle leva as branches do `branch_prefix` dos registros."""
        self.team_branches()
        self.record('authorization-2.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+00:00')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']), {'main', 'equipe/issue-2', 'equipe/issue-2-s1'})
        self.assertEqual((result['prefixes'], result['prefixSource']), (['equipe/'], 'authorization'))

    def test_two_records_bring_both_prefixes(self):
        """Issue 44, S1: a união dos prefixos; um registro sem `branch_prefix` vale `claude/`."""
        self.team_branches()
        self.record('authorization-1.json', issued_at='2026-01-01T10:00:00+00:00')
        self.record('authorization-2.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+00:00')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']),
                         {'main', 'claude/issue-1', 'claude/issue-1-s2', 'equipe/issue-2', 'equipe/issue-2-s1'})
        self.assertEqual((result['prefixes'], result['prefixSource']), (['claude/', 'equipe/'], 'authorization'))

    def test_without_a_valid_record_it_keeps_the_default(self):
        """Issue 44, S1; redesenho, issue 1, S3: sem registro válido nem `branchPrefix`, nenhum prefixo padrão: só a
        base entra no bundle; um registro malformado é ignorado."""
        self.team_branches()
        config = self.config(homolog={'backupDir': str(self.backup)})
        code, result = self.bundle(config)
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']), {'main'})
        self.assertEqual((result['prefixes'], result['prefixSource']), ([], None))
        self.assertEqual(result['skipped'], 0)
        self.record('authorization-bad.json', branch_prefix='x$/')
        (self.work / '.frontlights' / 'authorization-broken.json').write_text('[1, 2]', encoding='utf-8')
        code, result = self.bundle(config)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), ([], None, 2))
        self.record('authorization-new.json', branch_prefix='equipe/')
        code, result = self.bundle(config)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), (['equipe/'], 'authorization', 2))

    def test_a_record_with_malformed_worktrees_is_left_out_and_counted(self):
        """Issue 44, 2ª revisão: o registro com `worktrees` que não é lista fica fora dos prefixos e entra em
        `skipped`, como na leitura das branches das issues."""
        self.team_branches()
        self.record('authorization-1.json', branch_prefix='claude/')
        self.record('authorization-2.json', branch_prefix='equipe/', worktrees='x')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
        self.assertEqual(code, 0, result)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), (['claude/'], 'authorization', 1))

    def test_an_explicit_prefix_still_wins(self):
        """Issue 44, S1: `--prefix` explícito vale sozinho, com registros de outro prefixo."""
        self.team_branches()
        self.record('authorization-1.json', branch_prefix='claude/')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}), '--prefix', 'equipe/')
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']), {'main', 'equipe/issue-2', 'equipe/issue-2-s1'})
        self.assertEqual((result['prefixes'], result['prefixSource']), (['equipe/'], 'argument'))

    def test_records_elsewhere_are_read_with_records(self):
        """Issue 44, S1: `--records` aponta a pasta dos registros, como no release-plan."""
        self.team_branches()
        elsewhere = self.base / 'elsewhere'
        (elsewhere / '.frontlights').mkdir(parents=True)
        (elsewhere / '.frontlights' / 'authorization.json').write_text(
            json.dumps({'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'equipe/', 'worktrees': []}), encoding='utf-8')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}), '--records', str(elsewhere))
        self.assertEqual(code, 0, result)
        self.assertEqual((result['prefixes'], result['prefixSource']), (['equipe/'], 'authorization'))
        self.assertEqual(set(result['refs']), {'main', 'equipe/issue-2', 'equipe/issue-2-s1'})

    def test_an_unreadable_config_is_a_refusal_in_json(self):
        code, result = self.bundle(self.base / 'absent.json')
        self.assertEqual((code, result['ok']), (1, False))
        broken = self.base / 'broken.json'
        broken.write_text('[1, 2]', encoding='utf-8')
        code, result = self.bundle(broken)
        self.assertEqual((code, result['ok']), (1, False))
        self.assertEqual(self.written_files(), [])

    def test_the_frontlights_entry_routes_bundle(self):
        config = self.config(homolog={'backupDir': str(self.backup)})
        code, result = self.cli('homolog', 'bundle', '--root', str(self.work), '--config', str(config), script=FRONTLIGHTS)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['operation'], result['written']), ('bundle', True))
        self.assertEqual(self.written_files(), [Path(result['path']).name])

    def inspect(self, config):
        path = self.config(**config)
        return frontlights.inspect(json.loads(path.read_text(encoding='utf-8')), str(self.work), path)

    def test_inspect_does_not_change_without_the_key_and_accepts_a_valid_one(self):
        plain = self.inspect({})
        for config in ({'homolog': None}, {'homolog': {'backupDir': None}},
                       {'homolog': {'backupDir': str(self.backup)}}, {'homolog': {'backupDir': str(self.base / 'missing')}}):
            with self.subTest(config=config):
                result = self.inspect(config)
                self.assertEqual(sorted(result), sorted(plain))
                self.assertNotIn('homolog', result)
                self.assertNotIn('warnings', result)
        self.assertFalse((self.base / 'missing').exists())

    def test_inspect_refuses_an_invalid_key_and_never_echoes_the_value(self):
        invalid = ({'homolog': 'x'}, {'homolog': ['x']}, {'homolog': {'backupDir': 5}},
                   {'homolog': {'backupDir': 'relative/dir'}}, {'homolog': {'backupDir': '~/dir'}},
                   {'homolog': {'backupDir': 'C:/a/../b'}}, {'homolog': {'backupDir': ''}},
                   {'homolog': {'backupDir': 'C:/x{port}'}}, {'homolog': {'backupDir': 'C:/x\x00y'}},
                   {'homolog': {'backupdir': 'C:/x'}}, {'homolog': {'backupDir': 'C:/x', 'extra': 1}})
        for config in invalid:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, 'homolog') as caught:
                self.inspect(config)
            message = str(caught.exception)
            value = config['homolog'].get('backupDir') if isinstance(config['homolog'], dict) else None
            if isinstance(value, str) and value:
                self.assertNotIn(value, message)
        with self.assertRaisesRegex(ValueError, 'extra'):
            self.inspect({'homolog': {'backupDir': 'C:/x', 'extra': 1}})

    def test_the_inspect_cli_reports_the_refusal_as_json(self):
        path = self.config(homolog={'backupDir': 'relative/dir'})
        done = subprocess.run([sys.executable, str(FRONTLIGHTS), 'inspect', '--config', str(path), '--root', str(self.work)],
                              capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=120)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, '')
        self.assertNotIn('Traceback', done.stderr)
        self.assertIn('homolog.backupDir', json.loads(done.stderr)['error'])
        path = self.config(homolog={'backupDir': str(self.backup)})
        done = subprocess.run([sys.executable, str(FRONTLIGHTS), 'inspect', '--config', str(path), '--root', str(self.work)],
                              capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('homolog', json.loads(done.stdout))


class HomologReleasePlanTests(HomologCli, unittest.TestCase):
    """S4: `homolog release-plan` lista as issues que estão na main local e ainda não em `origin/main`, conta os
    commits à frente e atrás e nomeia a branch da release sem criar nada: só lê o Git e os registros. Só
    repositórios temporários: o remoto é um repositório bare no mesmo disco, e a configuração Git da máquina fica
    fora da fixture. O trio (origin, work, other) e o registro de autorização são montados uma vez por classe e
    copiados para cada teste (issue #59)."""

    @staticmethod
    def build(folder):
        build_trio(folder)
        (folder / 'work' / '.frontlights').mkdir()
        entries = [{'issue': 1, 'branch': 'claude/issue-1'}, {'issue': 2, 'branch': 'claude/issue-2'},
                   {'issue': 1, 'branch': 'claude/issue-1-s2', 'slice': 'S2'}]
        data = {'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'claude/', 'worktrees': entries}
        (folder / 'work' / '.frontlights' / 'authorization.json').write_text(json.dumps(data), encoding='utf-8')

    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, cls.build)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = gitfixture.copy(self.template, Path(self.temp.name), exist_ok=True)
        self.env = isolated(self.base)
        self.origin = self.base / 'origin.git'
        self.work = self.base / 'work'
        self.other = self.base / 'other'

    def git(self, cwd, *args, check=True):
        prefix = ['git', '-C', str(cwd)] if cwd else ['git']
        done = subprocess.run([*prefix, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=self.env, stdin=subprocess.DEVNULL, timeout=60)
        if check:
            self.assertEqual(done.returncode, 0, f'git {" ".join(args)}: {done.stderr}')
        return done

    def configure(self, repo):
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git(repo, 'config', key, value)

    def commit(self, repo, name, content, message):
        (repo / name).write_text(content, encoding='utf-8')
        self.git(repo, 'add', name)
        self.git(repo, 'commit', '-q', '-m', message)
        return self.sha(repo)

    def sha(self, repo, ref='HEAD'):
        return self.git(repo, 'rev-parse', ref).stdout.strip()

    def record(self, *entries, name='authorization.json', **extra):
        """An authorization record in the `.frontlights` of the main worktree with the given `worktrees` entries."""
        data = {'repository': 'OWNER/REPOSITORY', 'branch_prefix': 'claude/', 'worktrees': list(entries), **extra}
        (self.work / '.frontlights' / name).write_text(json.dumps(data), encoding='utf-8')

    def deliver(self, number):
        """An issue branch cut from the local main with one commit, merged back into it with --no-ff."""
        branch = f'claude/issue-{number}'
        self.git(self.work, 'switch', '-q', '-c', branch)
        self.commit(self.work, f'issue-{number}.txt', f'{number}\n', f'issue {number}')
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', f'merge of issue {number} into the local main', branch)
        return branch

    def plan(self, *flags, script=HOMOLOG, real=False):
        return self.cli('release-plan', '--root', str(self.work), *flags, script=script, real=real)

    def deliver_direct(self, slug):
        """A branch of work without an issue, cut from the local main with one commit, merged back with --no-ff."""
        branch = f'claude/{slug}'
        self.git(self.work, 'switch', '-q', '-c', branch)
        self.commit(self.work, f'{slug}.txt', f'{slug}\n', f'work {slug}')
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', f'merge of {slug} into the local main', branch)
        return branch

    def full_suite(self, fail=False, root=None, real=False):
        """S3: the whole suite of the release recorded in the main worktree, on the local main, by `homolog suite
        --release --mode full` with a fake argv (green, or red with `fail`); the config lives outside the repo."""
        fake = self.base / 'fake_suite.py'
        fake.write_text('import sys\nsys.exit(1 if "--falha" in sys.argv else 0)\n', encoding='utf-8')
        config = self.base / 'config.json'
        config.write_text(json.dumps({'repository': None, 'homolog': {'backupDir': None}}), encoding='utf-8')
        argv = [sys.executable, str(fake), *(['--falha'] if fail else [])]
        code, result = self.cli('suite', '--root', str(root or self.work), '--config', str(config), '--release',
                                '--mode', 'full', '--argv', json.dumps(argv), real=real)
        self.assertEqual(code, 1 if fail else 0, result)
        return result

    def test_without_the_whole_suite_the_release_is_still_ready(self):
        """Decisão de 20/10/2026: a suíte inteira não é exigida pela release; sem o registro dela, a release fica
        pronta (exit 0) e `fullSuite` diz `missing`, só como informação."""
        self.deliver(1)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['release']), (0, True, [1]), result)
        self.assertEqual(result['fullSuite']['status'], 'missing')
        self.assertIn('Release pronta', result['message'])
        self.assertIn('Suíte inteira (opcional, não exigida pela release): missing.', result['message'])
        self.assertNotIn('homolog suite --release --mode full', result['message'])

    def test_the_whole_suite_green_at_the_tip_makes_the_release_ready(self):
        self.deliver(1)
        self.full_suite(real=True)   # the real `homolog.py suite` process
        code, result = self.plan(real=True)   # the real `homolog.py release-plan` process
        self.assertEqual((code, result['ready']), (0, True), result)
        full = result['fullSuite']
        self.assertEqual((full['status'], full['recordedHead']), ('current', self.sha(self.work)))
        self.assertTrue(os.path.samefile(full['recordPath'], self.work / '.frontlights' / 'release' / 'suite.json'))
        self.assertIn('Release pronta', result['message'])

    def test_a_whole_suite_adopted_from_an_issue_of_the_same_tree_is_current(self):
        """Issue 54, S1: a issue roda a suíte inteira na ponta dela e entra na main local por `--no-ff` sem mudar
        arquivo; a adoção (`suite --release --mode full --from`) deixa o `fullSuite` do `release-plan` em `current`
        sem rodar a suíte."""
        fake = self.base / 'fake_suite.py'
        fake.write_text('import sys\nsys.exit(1 if "--falha" in sys.argv else 0)\n', encoding='utf-8')
        config = self.base / 'config.json'
        config.write_text(json.dumps({'repository': None, 'homolog': {'backupDir': None, 'suites': {
            'full': {'argv': [sys.executable, str(fake), '--falha'], 'timeoutSeconds': 60}}}}), encoding='utf-8')
        self.git(self.work, 'switch', '-q', '-c', 'claude/issue-1')
        self.commit(self.work, 'issue-1.txt', '1\n', 'issue 1')
        code, ran = self.cli('suite', '--root', str(self.work), '--config', str(config), '--issue', '1', '--mode',
                             'full', '--argv', json.dumps([sys.executable, str(fake)]))
        self.assertEqual(code, 0, ran)
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', 'merge of issue 1 into the local main', 'claude/issue-1')
        code, adopted = self.cli('suite', '--root', str(self.work), '--config', str(config), '--release', '--mode',
                                 'full', '--from', ran['recordPath'])
        self.assertEqual((code, adopted.get('state')), (0, 'adopted'), adopted)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['release']), (0, True, [1]), result)
        self.assertEqual((result['fullSuite']['status'], result['fullSuite']['recordedHead']),
                         ('current', self.sha(self.work)))
        issue_head = self.sha(self.work, 'claude/issue-1')
        self.assertEqual(result['fullSuite']['adoptedFrom']['head'], issue_head)
        self.assertIn(f'adotada da ponta {issue_head[:7]}', result['fullSuite']['message'])

    def test_a_red_whole_suite_is_reported_and_does_not_hold_the_release(self):
        self.deliver(1)
        self.full_suite(fail=True)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (0, True, 'red'), result)
        self.assertIn('Suíte inteira (opcional, não exigida pela release): red.', result['message'])

    def test_a_delivery_after_the_whole_suite_makes_it_stale(self):
        self.deliver(1)
        self.full_suite()
        self.deliver(2)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (0, True, 'stale'), result)
        self.assertIn('head', result['fullSuite']['changed'])

    def test_an_uncommitted_edit_after_the_whole_suite_makes_it_stale(self):
        self.deliver(1)
        self.full_suite()
        (self.work / 'README.md').write_text('edited\n', encoding='utf-8')
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (0, True, 'stale'), result)
        self.assertEqual(result['fullSuite']['files_changed'], ['README.md'])

    def test_a_main_worktree_off_the_local_main_is_elsewhere(self):
        self.deliver(1)
        self.full_suite()
        self.git(self.work, 'switch', '-q', 'claude/issue-1')
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (0, True, 'elsewhere'), result)
        self.assertIn('claude/issue-1', result['fullSuite']['message'])

    def test_behind_and_nothing_to_release_say_nothing_of_the_whole_suite(self):
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertIn('nada a liberar', result['message'])
        self.assertEqual(result['fullSuite']['status'], 'missing')
        self.deliver(1)
        self.commit(self.other, 'remote.txt', 'remote\n', 'remote work')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        self.git(self.work, 'fetch', '-q', 'origin')
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertIn('sync', result['message'])
        self.assertNotIn('suíte inteira', result['message'])

    def test_work_without_an_issue_makes_a_release_of_its_own(self):
        """Trabalho sem issue: a entrada com `direct` entra na release como `releaseDirect`, com a branch nomeada,
        e a lista das issues não muda."""
        self.record({'issue': 1, 'branch': 'claude/issue-1'}, {'direct': 'melhoria-x', 'branch': 'claude/melhoria-x'},
                    {'direct': 'melhoria-x', 'branch': 'claude/melhoria-x-s1', 'slice': 'S1'})
        self.deliver_direct('melhoria-x')
        self.full_suite()
        code, result = self.plan()
        self.assertEqual(code, 0, result)
        self.assertEqual((result['ready'], result['release'], result['releaseDirect'], result['skipped']),
                         (True, [], ['melhoria-x'], 0))
        self.assertEqual(result['directs'], [{'direct': 'melhoria-x', 'branch': 'claude/melhoria-x',
                                              'tip': self.sha(self.work, 'claude/melhoria-x'), 'present': True,
                                              'inLocalMain': True, 'inRemoteMain': False}])
        self.assertEqual([i['issue'] for i in result['issues']], [1])
        self.assertIn('melhoria-x', result['message'])
        self.assertIn(result['releaseBranch'], result['message'])

    def test_issues_and_work_without_an_issue_go_together(self):
        self.record({'issue': 2, 'branch': 'claude/issue-2'}, {'direct': 'melhoria-x', 'branch': 'claude/melhoria-x'},
                    {'direct': 'melhoria-y', 'branch': 'claude/melhoria-y'})
        self.deliver_direct('melhoria-y')
        self.git(self.work, 'push', '-q', 'origin', 'main')   # melhoria-y is already in the remote main
        self.deliver(2)
        self.deliver_direct('melhoria-x')
        self.full_suite()
        code, result = self.plan()
        self.assertEqual(code, 0, result)
        self.assertEqual((result['release'], result['releaseDirect']), ([2], ['melhoria-x']))
        self.assertEqual({d['direct']: d['inRemoteMain'] for d in result['directs']},
                         {'melhoria-x': False, 'melhoria-y': True})
        self.assertIn('#2', result['message'])
        self.assertIn('melhoria-x', result['message'])
        self.assertNotIn('melhoria-y', result['message'])

    def test_a_malformed_direct_entry_is_counted_and_an_old_entry_without_a_key_still_is(self):
        self.record({'issue': 1, 'branch': 'claude/issue-1'}, {'direct': 'Melhoria X', 'branch': 'claude/melhoria-x'},
                    {'direct': 'melhoria-z', 'branch': 'outro/melhoria-z'},
                    {'issue': 3, 'direct': 'melhoria-w', 'branch': 'claude/melhoria-w'},
                    {'branch': 'claude/sem-chave'}, {'issue': None, 'branch': 'claude/issue-nula'})
        code, result = self.plan()
        self.assertEqual((result['directs'], result['releaseDirect']), ([], []))
        self.assertEqual([i['issue'] for i in result['issues']], [1])
        self.assertEqual(result['skipped'], 5)

    def test_without_issue_nor_direct_in_the_main_the_question_is_the_same(self):
        self.record({'direct': 'melhoria-x', 'branch': 'claude/melhoria-x'})
        self.commit(self.work, 'solto.txt', 'x\n', 'commit sem branch registrada')
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertEqual((result['ready'], result['release'], result['releaseDirect']), (False, [], []))
        self.assertEqual([(d['direct'], d['present']) for d in result['directs']], [('melhoria-x', False)])
        self.assertIn('nenhuma branch de issue', result['message'])

    def test_without_prefix_the_newest_record_names_the_release(self):
        """Issue 44, S2: sem `--prefix`, o nome da release usa o `branch_prefix` do registro de `issued_at` mais novo,
        nunca o do nome de arquivo; um registro sem `issued_at` fica atrás dos que têm."""
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+00:00')
        self.record(name='authorization-b.json', branch_prefix='antigo/', issued_at='2026-01-01T10:00:00+00:00')
        code, result = self.plan()
        self.assertRegex(result['releaseBranch'], r'^equipe/release-\d{4}-\d{2}-\d{2}$')
        self.assertEqual((result['prefix'], result['prefixSource']), ('equipe/', 'authorization'))

    def test_instants_are_compared_across_offsets_and_an_invalid_one_ranks_last(self):
        """Issue 44, S2: `Z` e fusos diferentes valem pelo instante; `issued_at` inválido fica atrás, mesmo com o
        maior nome de arquivo; sem `issued_at` em nenhum, vale o último registro pelo nome do arquivo."""
        (self.work / '.frontlights' / 'authorization.json').unlink()
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+05:00')
        self.record(name='authorization-b.json', branch_prefix='antigo/', issued_at='2026-01-02T06:00:00Z')
        self.record(name='authorization-z.json', branch_prefix='outro/', issued_at='ontem')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource']), ('antigo/', 'authorization'))
        for name in ('authorization-a.json', 'authorization-b.json', 'authorization-z.json'):
            (self.work / '.frontlights' / name).unlink()
        self.record(name='authorization-1.json', branch_prefix='primeiro/')
        self.record(name='authorization-2.json', branch_prefix='segundo/')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource']), ('segundo/', 'authorization'))

    def test_a_record_with_malformed_worktrees_never_names_the_release(self):
        """Issue 44, 2ª revisão: o registro que a leitura das branches ignora também não nomeia a release."""
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-02-01T10:00:00+00:00',
                    worktrees='x')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource'], result['skipped']), ('claude/', 'authorization', 1))

    def test_without_a_valid_record_the_release_keeps_the_default(self):
        """Issue 44, S2; redesenho, issue 1, S3: sem registro válido nem `branchPrefix`, a release não tem nome (nenhum
        prefixo padrão); com `branchPrefix` no config, ele nomeia a release."""
        (self.work / '.frontlights' / 'authorization.json').unlink()
        code, result = self.plan()
        self.assertIsNone(result['releaseBranch'])
        self.assertEqual((result['prefix'], result['prefixSource']), (None, None))
        (self.work / '.frontlights' / 'config.json').write_text(json.dumps({'repository': None, 'branchPrefix': 'dev/'}),
                                                               encoding='utf-8')
        code, result = self.plan()
        self.assertRegex(result['releaseBranch'], r'^dev/release-\d{4}-\d{2}-\d{2}$')
        self.assertEqual((result['prefix'], result['prefixSource']), ('dev/', 'config'))

    def test_an_explicit_prefix_still_names_the_release(self):
        """Issue 44, S2: `--prefix` explícito vale sozinho."""
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+00:00')
        code, result = self.plan('--prefix', 'rel/')
        self.assertRegex(result['releaseBranch'], r'^rel/release-\d{4}-\d{2}-\d{2}$')
        self.assertEqual((result['prefix'], result['prefixSource']), ('rel/', 'argument'))

    def test_the_release_lists_only_the_issues_still_outside_the_remote_main(self):
        self.deliver(1)
        self.git(self.work, 'push', '-q', 'origin', 'main')
        remote_main = self.sha(self.origin, 'main')
        self.deliver(2)
        self.full_suite()
        code, result = self.plan()
        self.assertEqual(code, 0, result)
        self.assertEqual((result['ok'], result['ready'], result['release'], result['ahead'], result['behind'], result['skipped']),
                         (True, True, [2], 2, 0, 0))
        self.assertEqual((result['base'], result['remote'], result['localMain'], result['remoteMain']),
                         ('main', 'origin', self.sha(self.work), remote_main))
        self.assertEqual([i['issue'] for i in result['issues']], [1, 2])
        one, two = result['issues']
        self.assertEqual((one['branch'], one['present'], one['inLocalMain'], one['inRemoteMain']),
                         ('claude/issue-1', True, True, True))
        self.assertEqual((two['branch'], two['tip'], two['present'], two['inLocalMain'], two['inRemoteMain']),
                         ('claude/issue-2', self.sha(self.work, 'claude/issue-2'), True, True, False))
        self.assertRegex(result['releaseBranch'], r'^claude/release-\d{4}-\d{2}-\d{2}$')
        self.assertIn('#2', result['message'])
        self.assertIn(result['releaseBranch'], result['message'])
        # it only reads: the release branch was not created, nothing was pushed, the worktree is untouched
        missing = self.git(self.work, 'rev-parse', '--verify', '--quiet', f"refs/heads/{result['releaseBranch']}", check=False)
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(self.sha(self.origin, 'main'), remote_main)
        self.assertEqual(self.git(self.work, 'status', '--porcelain', '--untracked-files=no').stdout, '')

    def test_nothing_ahead_is_a_question_not_a_release(self):
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertEqual((result['ok'], result['ready'], result['ahead'], result['behind'], result['release']),
                         (False, False, 0, 0, []))
        self.assertIn('nada a liberar', result['message'])
        self.assertEqual([(i['issue'], i['present']) for i in result['issues']], [(1, False), (2, False)])

    def test_a_local_main_behind_the_remote_asks_for_the_sync_first(self):
        self.deliver(1)
        self.commit(self.other, 'remote.txt', 'remote\n', 'remote work')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        self.git(self.work, 'fetch', '-q', 'origin')
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertEqual((result['ready'], result['ahead'], result['behind'], result['release']), (False, 2, 1, [1]))
        self.assertIn('sync', result['message'])
        self.assertEqual(result['remoteMain'], self.sha(self.other))

    def test_without_the_remote_ref_it_refuses_and_names_the_sync(self):
        self.deliver(1)
        self.git(self.work, 'update-ref', '-d', 'refs/remotes/origin/main')
        code, result = self.plan()
        self.assertEqual(code, 1, result)
        self.assertEqual((result['ok'], result['ready'], result['ahead'], result['behind'], result['remoteMain'], result['release']),
                         (False, False, None, None, None, []))
        self.assertIn('sync', result['message'])
        self.assertEqual({i['issue']: (i['inLocalMain'], i['inRemoteMain']) for i in result['issues']},
                         {1: (True, None), 2: (None, None)})

    def test_a_slice_entry_is_ignored_a_gone_branch_is_absent_and_malformed_entries_are_counted(self):
        self.record({'issue': 1, 'branch': 'claude/issue-1'}, {'issue': 1, 'branch': 'claude/issue-1-s2', 'slice': 'S2'},
                    {'issue': 'x', 'branch': 'claude/x'}, {'issue': 3, 'branch': 'bad name'},
                    {'issue': 4, 'branch': 'other/issue-4'}, {'issue': 0, 'branch': 'claude/issue-0'}, 'not an entry')
        (self.work / '.frontlights' / 'authorization-2.json').write_text('[1, 2]', encoding='utf-8')
        (self.work / '.frontlights' / 'authorization-3.json').write_text('{broken', encoding='utf-8')
        self.git(self.work, 'branch', 'claude/issue-1-s2')   # the slice branch exists; the issue branch does not
        code, result = self.plan()
        self.assertEqual(code, 2, result)
        self.assertEqual([i['issue'] for i in result['issues']], [1])
        entry = result['issues'][0]
        self.assertEqual((entry['branch'], entry['present'], entry['tip'], entry['inLocalMain'], entry['inRemoteMain']),
                         ('claude/issue-1', False, None, None, None))
        self.assertEqual(result['skipped'], 7)   # five entries and two files

    def test_an_existing_release_branch_of_the_day_is_never_reused(self):
        self.deliver(1)
        self.full_suite()
        code, first = self.plan()
        self.assertEqual(code, 0, first)
        name = first['releaseBranch']
        self.git(self.work, 'branch', name)
        _, second = self.plan()
        self.assertEqual(second['releaseBranch'], f'{name}-2')
        self.git(self.work, 'branch', f'{name}-2')
        _, third = self.plan()
        self.assertEqual(third['releaseBranch'], f'{name}-3')
        code, result = self.plan('--prefix', 'rel/')
        self.assertEqual(code, 0, result)
        self.assertRegex(result['releaseBranch'], r'^rel/release-\d{4}-\d{2}-\d{2}$')
        for prefix in ('claude', '../x/', 'cl aude/'):
            with self.subTest(prefix=prefix):
                code, result = self.plan('--prefix', prefix)
                self.assertEqual(code, 1, result)
                self.assertIn('prefixo', result['message'])

    def test_a_remote_tracking_release_branch_of_the_day_is_skipped_too(self):
        self.deliver(1)
        self.full_suite()
        code, first = self.plan()
        self.assertEqual(code, 0, first)
        name = first['releaseBranch']
        self.git(self.work, 'update-ref', f'refs/remotes/origin/{name}', 'HEAD')
        _, second = self.plan()
        self.assertEqual(second['releaseBranch'], f'{name}-2')
        _, elsewhere = self.plan('--remote', 'upstream')   # another remote does not hold the name
        self.assertEqual(elsewhere['releaseBranch'], name)

    def test_a_name_only_in_the_subject_of_a_merged_pull_request_is_free_again(self):
        """O GitHub apaga a branch de cabeça da PR mesclada e aceita o nome de novo: o nome que só aparece num
        'Merge pull request #N from dono/<nome>' de `origin/main`, sem branch local nem remote-tracking, volta a ser
        sugerido."""
        self.deliver(1)
        _, first = self.plan()
        name = first['releaseBranch']
        self.git(self.other, 'switch', '-q', '-c', 'feature')
        self.commit(self.other, 'pr-45.txt', '45\n', 'pull request 45')
        self.git(self.other, 'switch', '-q', 'main')
        self.git(self.other, 'merge', '-q', '--no-ff', '-m', f'Merge pull request #45 from OWNER/{name}', 'feature')
        self.git(self.other, 'branch', '-q', '-D', 'feature')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        self.git(self.work, 'fetch', '-q', 'origin')
        _, result = self.plan()
        self.assertEqual(result['releaseBranch'], name)

    def test_the_help_texts_name_the_operations_and_no_hook(self):
        for text in (read('skills', 'frontlights', 'scripts', 'homolog.py').split('"""')[1],
                     read('skills', 'frontlights', 'scripts', 'frontlights.py')):
            for operation in ('`sync`', '`bundle`', '`release-plan`'):
                self.assertIn(operation, text)
            self.assertNotIn('`hook`', text)
        self.assertNotIn('Later slices add', read('skills', 'frontlights', 'scripts', 'homolog.py'))
        self.assertNotIn('`hook` and `sync` of the local main', read('skills', 'frontlights', 'scripts', 'frontlights.py'))

    def test_records_without_an_authorization_map_no_issue_and_ask(self):
        self.deliver(1)
        self.full_suite()
        empty = self.base / 'elsewhere'
        (empty / '.frontlights').mkdir(parents=True)
        for folder in (empty, self.base / 'absent'):
            with self.subTest(folder=folder.name):
                code, result = self.plan('--records', str(folder))
                self.assertEqual(code, 2, result)
                self.assertEqual((result['issues'], result['release'], result['ready'], result['ahead'], result['skipped']),
                                 ([], [], False, 2, 0))
                self.assertIn('nenhuma branch de issue', result['message'])
        code, same = self.plan('--records', str(self.work))
        self.assertEqual((code, same['release']), (0, [1]))

    def test_the_frontlights_entry_gives_the_same_plan_as_the_module(self):
        self.deliver(1)
        code, direct = self.plan()
        self.assertEqual(direct['operation'], 'release-plan')
        routed_code, routed = self.cli('homolog', 'release-plan', '--root', str(self.work), script=FRONTLIGHTS)
        self.assertEqual((routed_code, routed), (code, direct))


class HomologReleaseClosesTests(HomologCli, unittest.TestCase):
    """Issue 63, S3: o `release-plan` lê o GitHub (só leitura) e devolve `closes`, as issues de topo da release
    prontas (todas as caixas marcadas, nenhuma filha aberta, nenhuma pendência fora dos critérios), que a PR da
    release leva como `Closes #n`; sem leitura do GitHub a lista sai vazia com a razão e o plano não muda. Git real
    (o trio da classe-mãe), gh falso (`FakeGh` de test_closeout): nenhuma chamada real ao gh."""

    LEFTOVER = DONE_ALL + '\n## Pendências conhecidas\n\n- [ ] sobra\n'

    # the fixture and the helpers of the release-plan tests, without running those tests again
    build = staticmethod(HomologReleasePlanTests.build)
    setUpClass = HomologReleasePlanTests.__dict__['setUpClass']
    git, commit, sha = HomologReleasePlanTests.git, HomologReleasePlanTests.commit, HomologReleasePlanTests.sha
    record, deliver = HomologReleasePlanTests.record, HomologReleasePlanTests.deliver
    full_suite = HomologReleasePlanTests.full_suite

    def setUp(self):
        HomologReleasePlanTests.setUp(self)
        self.config = self.work / '.frontlights' / 'config.json'

    def deliver_five(self):
        self.record(*({'issue': n, 'branch': f'claude/issue-{n}'} for n in range(1, 6)))
        for number in range(1, 6):
            self.deliver(number)

    def write_config(self, repository='OWNER/REPOSITORY', path=None):
        path = path or self.config
        path.write_text(json.dumps({'repository': repository}), encoding='utf-8')
        return path

    def five(self):
        return FakeGh({1: node(1), 2: node(2, parent=9), 3: node(3, text=DONE_PARTIAL),
                       4: node(4, children=[(8, 'OPEN')]), 5: node(5, text=self.LEFTOVER)})

    def routed(self, gh, *flags):
        """`frontlights.py homolog release-plan` neste processo, com o gh falso no lugar do `gh_default`."""
        out = io.StringIO()
        argv = ['frontlights.py', 'homolog', 'release-plan', '--root', str(self.work), '--full', *flags]
        with mock.patch.object(rs, 'gh_default', gh), mock.patch.object(sys, 'argv', argv), \
                mock.patch.dict(os.environ, self.env, clear=True), contextlib.redirect_stdout(out):
            code = frontlights.main()
        self.assertEqual(gh.violations, [])
        result = json.loads(out.getvalue())
        self.assertEqual(result['exitCode'], code)
        return code, result

    def test_closes_lists_only_the_ready_top_level_issues(self):
        self.deliver_five()
        self.write_config()
        self.full_suite()
        gh = self.five()
        code, result = self.routed(gh)
        self.assertEqual((code, result['ready'], result['release']), (0, True, [1, 2, 3, 4, 5]), result)
        self.assertEqual((result['closes'], result['closesReason']), ([1], None), result)
        self.assertIn('Closes #1', result['closesMessage'])
        by = {entry['issue']: entry for entry in result['issues']}
        self.assertEqual({n: by[n]['closing'] for n in by},
                         {1: True, 2: 'sub_issue', 3: 'unchecked_criteria', 4: 'open_children', 5: 'pending_outside'})
        self.assertEqual((by[1]['state'], by[1]['level'], by[1]['parent'], by[1]['criteria']),
                         ('OPEN', 'top', None, {'checked': 2, 'total': 2}))
        self.assertEqual((by[2]['level'], by[2]['parent']), ('sub', 9))
        self.assertEqual(by[3]['criteria'], {'checked': 1, 'total': 2})
        self.assertEqual(by[4]['openChildren'], [8])
        self.assertEqual((by[5]['pendingOutside'], by[1]['pendingOutside']), (1, 0))

    def test_closed_missing_or_criterionless_issues_never_close(self):
        self.deliver_five()
        self.write_config()
        gh = FakeGh({1: node(1, state='CLOSED'), 2: node(2, text='sem critérios'), 3: node(3),
                     4: node(4, totals={'children': 150})})
        code, result = self.routed(gh)
        self.assertEqual((code, result['ready']), (0, True), result)   # `closes` never changes `ready`
        by = {entry['issue']: entry['closing'] for entry in result['issues']}
        self.assertEqual(by, {1: 'not_open', 2: 'no_criteria', 3: True, 4: 'truncated', 5: 'not_found'})
        self.assertEqual(result['closes'], [3])

    def test_without_a_config_nothing_is_read_and_closes_is_empty(self):
        self.deliver(1)
        gh = self.five()
        code, result = self.routed(gh)
        self.assertEqual(gh.calls, [])
        self.assertEqual((result['closes'], result['closesReason']), ([], 'no_config'), result)
        self.assertEqual((code, result['ready']), (0, True))
        self.assertIn('sem `Closes #n`', result['closesMessage'])
        self.assertNotIn('closing', result['issues'][0])

    def test_a_config_without_repository_reads_nothing(self):
        self.deliver(1)
        self.write_config(repository=None)
        gh = self.five()
        _, result = self.routed(gh)
        self.assertEqual(gh.calls, [])
        self.assertEqual((result['closes'], result['closesReason']), ([], 'no_repository'), result)

    def test_a_failed_read_keeps_the_plan_and_empties_closes(self):
        self.deliver(1)
        self.write_config()
        self.full_suite()
        gh = FakeGh({1: node(1)}, fail_issues=True)
        code, result = self.routed(gh)
        self.assertEqual((code, result['ready'], result['release']), (0, True, [1]), result)
        self.assertEqual((result['closes'], result['closesReason']), ([], 'github_unavailable'), result)
        self.assertIn('Release pronta', result['message'])

    def test_a_base_that_is_not_the_default_branch_closes_nothing(self):
        self.deliver(1)
        self.write_config()
        gh = FakeGh({1: node(1)}, default_branch='develop')
        _, result = self.routed(gh)
        self.assertEqual((result['closes'], result['closesReason']), ([], 'base_not_default'), result)
        self.assertIn('develop', result['closesMessage'])
        self.assertFalse([q for q in gh.queries() if 'issue(number' in q])

    def test_nothing_to_release_reads_nothing(self):
        self.write_config()
        gh = self.five()
        _, result = self.routed(gh)
        self.assertEqual(gh.calls, [])
        self.assertEqual((result['closes'], result['closesReason']), ([], 'nothing_to_release'), result)

    def test_config_names_a_file_outside_the_root(self):
        self.deliver(1)
        outside = self.write_config(path=self.base / 'config.json')
        _, result = self.routed(FakeGh({1: node(1)}), '--config', str(outside))
        self.assertEqual((result['closes'], result['closesReason']), ([1], None), result)


if __name__ == '__main__':
    unittest.main()
