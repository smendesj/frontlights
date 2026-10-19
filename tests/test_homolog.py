"""Homologação na main local (issue 32): a branch da issue é cortada da main local, fica só local e entra nela
por merge com três portões verdes; nada vai ao GitHub até a release.

Seams: `frontlights.py authorize` (S1); o texto de `SKILL.md`, `references/development.md`, `docs/protocol.md`,
`docs/security.md`, `templates/handoff.md`, `examples/authorization.json`, `README.md`, `docs/acceptance.md` e
`evals/runbook.md` (S1); `scripts/homolog.py` (`hook` e `sync`) e a entrada `frontlights.py homolog` (S2);
`scripts/homolog.py` (`bundle` e `backup_dir`) e a validação de `homolog.backupDir` no `inspect` (S3);
`scripts/homolog.py` (`release-plan`) e a entrada `frontlights.py homolog release-plan` (S4; a regra do
`cleanup.py plan` para a branch entregue sem PR está em `test_cleanup.py`).
"""
import json
import os
import subprocess
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


GREEN = {'suite_gate': 'current', 'review_gate': 'current', 'browser_gate': 'answered'}


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

    def test_an_operation_that_still_carries_full_suite_is_refused_naming_suite_gate(self):
        """Issue 52, S2: o portão da suíte inteira saiu; a chave antiga é recusada antes dos portões, com ou sem
        `suite_gate`, e a recusa nomeia `suite_gate`."""
        without = {k: v for k, v in GREEN.items() if k != 'suite_gate'}
        for gates in (dict(GREEN, full_suite='green'), dict(without, full_suite='green')):
            with self.subTest(gates=gates), self.assertRaisesRegex(ValueError, r'full_suite is gone.*suite_gate'):
                frontlights.authorize(self.c, dict(self.op, gates=gates))

    def test_a_missing_or_red_gate_refuses_and_names_the_gate(self):
        reds = {'suite_gate': ('green', 'stale', 'unconfigured', 'red', 'missing', True, None),
                'review_gate': ('stale', 'current ', None),
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
    main local, fica só local e entra nela com os três portões, e distinguem a main local da remota."""

    def test_stage_six_cuts_the_branch_from_the_local_main_and_keeps_it_local(self):
        text = stage(6)
        for phrase in ('one issue branch, cut from the local main and kept local',
                       'the merge of the branch of the issue once its three gates are green, then the bundle',
                       '(development.md, "Into the local main")', '**Denied operations are asked one at a time.**'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('never `origin/main`', 'stays local and is never pushed',
                       'Nothing of an issue goes to GitHub before the release',
                       'writing the remote main (`origin/main`, the base branch on GitHub)',
                       'the local main is written only by the covered merge',
                       '`{"suite_gate": "current", "review_gate": "current", "browser_gate": "answered"}`',
                       '`merge_into_local_main`', 'the session asks the user with `AskUserQuestion` instead of merging'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        for gone in ('pushing the work branches', 'one issue branch and one PR', 'write the base branch'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, text)

    def test_the_development_reference_has_the_gates_section_after_the_review(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertEqual(text.count('## Into the local main: the three gates'), 1)
        self.assertLess(text.index('## Review, checkpoints and renewal'), text.index('## Into the local main'))
        self.assertLess(text.index('## Into the local main'), text.index('## The release'))
        body = ' '.join(text.split('## Into the local main: the three gates')[1].split('## The release')[0].split())
        for phrase in ('homologation bench', 'refused as the remote main', '**Bring the local main in first.**',
                       '`git merge main`', '**Gate 1, the impact suite.**', 'never the fast suite',
                       'the three gates run at the same time on that tip',
                       'with a screen the review waits for the watched run',
                       '`homolog suite-gate --root <issue-worktree> --config .frontlights/config.json --issue <n> --base <base>`',
                       'The whole suite waits for the release.',
                       'an operation that still carries `full_suite` is refused, naming `suite_gate`',
                       '**Gate 2, the review.**', '`stale` means a review again, never the merge',
                       '**Gate 3, the watched run.**', '**The check and the merge.**', '`merge_into_local_main`',
                       '`examples/operation-merge-local-main.json`', '`git merge --no-ff <branch_prefix>issue-<n>`',
                       'it never edits the gates to make them pass', '**Record it.**', '"Merge na main local"',
                       'a preflight, not a barrier', 'it reads no Git'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        whole = ' '.join(text.split())
        for phrase in ('one merge into the local main per issue', 'delivered by one merge into the local main',
                       'the branches of the issue and of its slices stay local',
                       'writing the remote main (`origin/main`, the base branch on GitHub)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, whole)
        for gone in ('pushing the work branches', 'Draft PRs are covered', 'delivered in one PR'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, whole)

    def test_a_stale_review_reruns_the_impact_suite_beside_the_new_round(self):
        """Revisão da issue 52, M1: depois de uma revisão vencida, a suíte de impacto roda de novo ao lado da nova
        rodada de revisão, nunca numa fila antes dela; o `suite-gate` volta a `current` antes do merge."""
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = ' '.join(text.split('## Review, checkpoints and renewal')[1].split('## Into the local main')[0].split())
        self.assertIn('with the impact suite rerun on the new tip beside that review round, not before it '
                      '("Into the local main"); `homolog suite-gate` must answer `current` again before the merge',
                      body)
        self.assertNotIn('rerun the impact suite until', body)

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
        for phrase in ('cortada da main local e nunca enviada, entra na main local por merge só com os três portões verdes',
                       '"Standing authorization and the denied operations"', 'em "Into the local main"',
                       'a saída do `authorize` do merge na main local'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Main local e main remota.**',
                       '`merge_into_local_main` só com `target` igual a `base.branch`', 'são recusados como main remota',
                       'nunca de uma slice',
                       'com os três `gates` de "Into the local main" (`references/development.md`)',
                       'ou a chave antiga `full_suite`, nomeia o portão na recusa', 'não prova que a suíte rodou',
                       'conferência prévia, não barreira', 'não lê o Git',
                       'confere `edit`, `test`, `checkpoint` e `merge_into_local_main`',
                       'os merges cobertos de `references/development.md` ("Standing authorization and the denied operations"), os únicos permitidos'):
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
                       'o da branch da issue na main local com os três portões verdes',
                       'nada da issue vai ao GitHub antes da release'):
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
        self.assertEqual(set(op['gates']), {'suite_gate', 'review_gate', 'browser_gate'})
        # the example operation passes `authorize` against the example charter once the placeholders are filled
        with tempfile.TemporaryDirectory() as temp:
            charter = dict(charter, approved_by='usuário', approval_reference='autorização permanente',
                           expires_at='2099-01-01T00:00:00+00:00',
                           monitoring=dict(charter['monitoring'], confirmed_by='usuário'),
                           worktrees=[dict(charter['worktrees'][0], path=temp)])
            self.assertEqual(frontlights.authorize(charter, dict(op, worktree=temp))['scope_check'], 'pass')

    def test_the_hook_and_the_sync_open_stage_six(self):
        """S2: a skill, a referência, o protocolo, a segurança e o README dizem quando o hook e o sync rodam, o que
        perguntam, e declaram as três escritas da skill dentro de `.git/`."""
        skill = stage(6)
        for phrase in ('1. **Hook and sync** (development.md, "The start of stage 6"): `homolog hook`, then `homolog sync` '
                       'brings `origin/<base>` into the local main',):
            with self.subTest(file='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        heading = '## The start of stage 6: the pre-push hook and the sync of the local main'
        self.assertLess(text.index(heading), text.index('## Slices in order'))
        body = ' '.join(text.split(heading)[1].split('## Slices in order')[0].split())
        for phrase in ('"Instalar o hook `pre-push` que recusa enviar a main local?"', '"Sim, instalar"',
                       'it is never overwritten', 'It is the only hook the skill installs',
                       '`homolog sync --root <main worktree> --base <base>', 'never pushes',
                       '"Resolver o conflito agora na worktree principal"', 'gets neither',
                       '`scripts/homolog.py`', 'exit code 0 done, 1 refused or failed, 2 a question for the user',
                       '**The hook.**', '`installed`, `ours`, `foreign`, `path` and `script`', '`foreign: true`',
                       'refuses with exit code 1', 'a guard and not a barrier', '`--no-verify`',
                       '**The sync.**', 'no tracked change pending and no merge in progress',
                       '`git fetch <remote>` and `git merge --no-edit <remote>/<base>`', '`git merge --abort`',
                       'never uses `--force`, `reset` or `rebase`', 'runs again before the release'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('instala um único hook', 'Esse `pre-push` é o único hook que o Frontlights instala',
                       'nunca sobrescreve um hook de outra origem',
                       'É uma guarda, não uma barreira', 'As escritas da skill dentro de `.git/` são três',
                       '`.git/info/exclude`', '`frontlights-serve/ports/`',
                       '**Sincronização da main local (`homolog sync`).**', 'Nunca envia, nunca usa `--force`, `reset` nem `rebase`',
                       'é merge coberto (`references/development.md`, "Standing authorization and the denied operations")'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('o hook `pre-push`, a sincronização da main local e a prévia, em "The start of stage 6"',):
            with self.subTest(file='protocol.md', phrase=phrase):
                self.assertIn(phrase, protocol)
        readme = flat('README.md')
        for phrase in ('instala só o hook `pre-push` da homologação', 'O único hook que a skill instala',
                       'traz `origin/main` para a main local (`homolog sync`'):
            with self.subTest(file='README.md', phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertNotIn('skill não instala hooks, então', readme)
        self.assertIn('S2: `homolog hook` confere', flat('docs', 'acceptance.md'))
        self.assertIn('confirm `homolog hook` exits 2', flat('evals', 'runbook.md'))

    def test_the_bundle_follows_each_merge_into_the_local_main(self):
        """S3: a skill, a referência, o protocolo, a segurança, o README e o exemplo de config dizem quando o bundle
        é gravado, onde, e que sem a chave nada é gravado."""
        self.assertIn('once its three gates are green, then the bundle', stage(6))
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = ' '.join(text.split('## Into the local main: the three gates')[1].split('## The release')[0].split())
        for phrase in ('6. **Back it up.**', 'homolog bundle --root <main worktree> --config',
                       'the only write the run makes outside the project, and only into that folder',
                       '`homolog.backupDir`', '`git bundle verify`', 'old bundles are never deleted',
                       '`configured: false`', 'name the key, ask nothing and go on', '7. **Record it.**',
                       '"sem backup configurado"'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Backup da main local (`homolog bundle`).**', 'a única gravação da execução fora do projeto',
                       'o utilitário nunca a cria', 'nunca se sobrescreve nem se apaga um bundle', 'não há rede',
                       'nunca entra neste repositório', 'A chave só diz onde gravar'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn('os três portões do merge na main local e o bundle depois dele, em "Into the local main"',
                      flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('a chave `homolog.backupDir` aponta uma pasta sua, por caminho absoluto', flat('README.md'))
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
        self.assertIn('das branches de trabalho de todo prefixo dos registros de autorização', flat('README.md'))

    def test_the_release_name_follows_the_newest_record(self):
        """Issue 44, S2: o nome da release usa o prefixo do registro de autorização mais recente, sem `--prefix`."""
        release = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ("the prefix of the newest authorization record by `issued_at` (without `issued_at`, the last "
                       "record by file name; `claude/` when there is none; `--prefix` names it alone", '`prefix` and `prefixSource` say which'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, release)
        self.assertIn('without `issued_at`, the last record by file name', release)
        self.assertIn('say in one line how many records `skipped` counts', release)
        for file in (('skills', 'frontlights', 'docs', 'protocol.md'), ('README.md',)):
            with self.subTest(file=file[-1]):
                text = flat(*file)
                self.assertIn('o prefixo do registro de autorização mais recente', text)
                self.assertIn('sem `issued_at`, o último registro pelo nome do arquivo', text)
        self.assertIn('das branches de trabalho de todo `branch_prefix` dos registros de autorização',
                      flat('skills', 'frontlights', 'docs', 'security.md'))

    def test_the_release_replaces_the_pull_request_per_issue(self):
        """S4: a release é oferecida ao fim de cada issue homologada e substitui a espera do merge por issue; os
        textos que diziam "antes do PR" dizem "antes do merge na main local"."""
        skill = stage(6)
        for phrase in ('7. **The release** (development.md, "The release"), offered at the end of each homologated issue',
                       "the session then waits for the user's merge"):
            with self.subTest(file='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        self.assertIn('before such an issue is merged into the local main, and before a PR is opened or updated',
                      flat('skills', 'frontlights', 'references', 'browser-testing.md'))
        self.assertNotIn("After a PR is opened, wait for the user's merge by default", skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.assertNotIn('## After the pull request', text)
        self.assertIn('## The release: from the local main to GitHub', text)
        self.assertIn('## Integrating a family before the local main', text)
        body = ' '.join(text.split('## The release: from the local main to GitHub')[1].split())
        for phrase in ('**Plan it.**', 'homolog release-plan --root <main worktree> --base <base>', '**Offer it.**',
                       '"Lançar a release com as issues #a, #b agora?"', '"Sim, lançar" first and "Agora não" second',
                       '`gh pr create --base <base> --head <release branch>', 'The body follows `templates/pr.md`',
                       '**Branch and pull request (covered).**', '`git push -u origin <release branch>`',
                       '**No closing keyword.**', '**Wait for the merge.**', '**Offer the merge when the PR is ready.**',
                       '**What wakes the session.**', '**What counts as merged.**', '**At the merge.**',
                       '`git pull --ff-only origin <base>`', '**Other work goes on.**',
                       '**Run the whole suite on the local main.**',
                       'homolog suite --release --mode full --base <base> --root <main worktree> --config .frontlights/config.json',
                       '`fullSuite` must be `current`',
                       'the whole suite of the release is green at the tip the release branch was cut from',
                       '(`python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog suite-gate --release --head '
                       '<head of the pull request> --base <base> --root <main worktree> --config '
                       '.frontlights/config.json` answers `current`, from the per-tip record `release/suite-<sha>.json` '
                       "in the main worktree's `.frontlights/release/`)",
                       'on a clean tree (a change not committed outside `.frontlights/`, tracked or untracked, is '
                       'refused and nothing runs: commit or discard it first)',
                       'Another issue entering the local main, or the suite run for a later release, does not make '
                       'the pull request unready',
                       'and `--timeout-seconds <N>` sized to that suite (3600 s without it)'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        order = [body.index(title) for title in ('**Plan it.**', '**Run the whole suite on the local main.**',
                                                 '**Offer it.**') if title in body]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('(`fullSuite: current`)', body)
        self.assertNotIn('recordedHead', body.split('**Offer the merge when the PR is ready.**')[1].split('**What wakes')[0])
        self.assertIn('run the impact suite and the type checks', ' '.join(text.split()))
        self.assertNotIn('run the full relevant suite', ' '.join(text.split()))
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('| Release |', 'A release é oferecida ao fim de cada issue homologada',
                       '"Agora não" deixa a issue homologada na main local',
                       'a suíte inteira na main local (`homolog suite --release --mode full`) e o `release-plan` de novo',
                       'release/suite.json', 'release/suite-full-<data-hora>.log',
                       'release/suite-<sha>.json cópia do mesmo registro por ponta (o sha completo do head), que a '
                       'execução numa ponta seguinte não sobrescreve; `homolog suite-gate --release --head <sha>` a '
                       'julga, e a PR da release fica pronta por ela'):
            with self.subTest(file='protocol.md', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertNotIn('| Espera do merge |', protocol)
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        for phrase in ('when the release of stage 6', 'the issue closes with the release that carries it',
                       '`contained_in_base_without_pull_request`'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)
        readme = flat('README.md')
        for phrase in ('#### Homologar na main local, lançar a release, fechar e limpar', '`homolog release-plan`',
                       'cujo tip já está em `origin/main`', 'oferta da release (branch de release e PR única)',
                       'a release só fica pronta com a suíte inteira verde na ponta da main local'):
            with self.subTest(file='README.md', phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertIn('- Release (a saída do `release-plan`', read('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertIn('o `fullSuite` do `release-plan`', flat('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertIn('S4: `homolog release-plan` (só leitura)', flat('docs', 'acceptance.md'))
        self.assertIn('# Release from the local main, closing, parent tick and cleanup', read('evals', 'merge-wait-and-cleanup.md'))

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
        self.assertIn('when an issue is excluded as `awaiting_release`', stage(1))
        self.assertIn('fica fora como `awaiting_release` até a release que a leva ser mesclada',
                      flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('senão `awaiting_release`; as únicas leituras de Git são `rev-parse` e `merge-base`',
                      flat('skills', 'frontlights', 'docs', 'security.md'))
        self.assertIn('fica fora como `awaiting_release`, e o Frontlights só avisa', flat('README.md'))
        self.assertIn('S5: `closeout.py candidates` exclui como `awaiting_release`', flat('docs', 'acceptance.md'))
        self.assertIn('the issue waits for the release (`awaiting_release`)', flat('evals', 'runbook.md'))

    def test_the_acceptance_record_and_the_runbook_track_it(self):
        self.assertIn('| 27. Homologação na main local: merge com portões e release por PR única (issue 32) | Pendente |',
                      flat('docs', 'acceptance.md'))
        self.assertIn('27. Local main as homologation (issue 32).', flat('evals', 'runbook.md'))


HOMOLOG = SKILL / 'scripts' / 'homolog.py'
FRONTLIGHTS = SKILL / 'scripts' / 'frontlights.py'
MARKER = '# frontlights pre-push hook v1 (homolog hook)'


class HomologHookAndSyncTests(unittest.TestCase):
    """S2: `homolog hook` instala e confere o pre-push que recusa enviar a main local; `homolog sync` traz
    `origin/main` para a main local e relata conflito deixando a worktree limpa. Só repositórios temporários: o
    remoto é um repositório bare no mesmo disco, e a configuração Git da máquina fica fora da fixture."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(base / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0')
        (base / 'gitconfig').write_text('', encoding='utf-8')
        self.origin = base / 'origin.git'
        self.work = base / 'work'
        self.other = base / 'other'
        self.git(None, 'init', '-q', '--bare', '-b', 'main', str(self.origin))
        self.git(None, 'init', '-q', '-b', 'main', str(self.work))
        self.configure(self.work)
        self.commit(self.work, 'README.md', 'first\n', 'first')
        self.git(self.work, 'remote', 'add', 'origin', str(self.origin))
        self.git(self.work, 'push', '-q', '-u', 'origin', 'main')
        self.git(None, 'clone', '-q', str(self.origin), str(self.other))
        self.configure(self.other)

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

    def cli(self, *args, script=HOMOLOG):
        done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL, timeout=180)
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError:
            self.fail(f'sem JSON no stdout (saída {done.returncode}): {done.stdout!r} {done.stderr!r}')
        self.assertEqual(result['exitCode'], done.returncode)
        return done.returncode, result

    def hook(self, *flags):
        return self.cli('hook', '--root', str(self.work), *flags)

    def sync(self):
        return self.cli('sync', '--root', str(self.work))

    def test_check_on_a_fresh_repository_asks_for_the_install(self):
        code, result = self.hook('--check')
        self.assertEqual(code, 2, result)
        self.assertEqual((result['installed'], result['ours'], result['foreign'], result['base']),
                         (False, False, False, 'main'))
        self.assertIn(MARKER, result['script'])
        self.assertIn('refs/heads/main', result['script'])
        self.assertTrue(result['script'].startswith('#!/bin/sh\n'))
        self.assertNotIn('\r', result['script'])
        self.assertFalse(Path(result['path']).exists())

    def test_install_is_idempotent_and_check_then_passes(self):
        code, first = self.hook('--install')
        self.assertEqual((code, first['written'], first['installed'], first['ours']), (0, True, True, True))
        path = Path(first['path'])
        self.assertEqual(path.read_bytes(), first['script'].encode('utf-8'))
        code, again = self.hook('--install')
        self.assertEqual((code, again['written']), (0, True))
        code, check = self.hook('--check')
        self.assertEqual((code, check['installed'], check['ours'], check['foreign'], check['current']),
                         (0, True, True, False, True))
        self.assertEqual((first['current'], again['current'], check['outsideRepository']), (True, True, False))
        self.assertEqual(path.read_bytes(), first['script'].encode('utf-8'))

    def test_a_hook_of_another_base_is_ours_but_not_current_and_install_rewrites_it(self):
        code, master = self.hook('--install', '--base', 'master')
        self.assertEqual((code, master['written'], master['current']), (0, True, True))
        path = Path(master['path'])
        self.assertIn('refs/heads/master', path.read_text(encoding='utf-8'))
        code, check = self.hook('--check', '--base', 'main')
        self.assertEqual((code, check['installed'], check['ours'], check['foreign'], check['current']),
                         (2, True, True, False, False))
        self.assertIn('--install', check['message'])
        self.assertIn('difere', check['message'])
        self.assertIn('refs/heads/master', path.read_text(encoding='utf-8'))   # --check wrote nothing
        code, main = self.hook('--install', '--base', 'main')
        self.assertEqual((code, main['written'], main['ours'], main['current']), (0, True, True, True))
        self.assertEqual(path.read_bytes(), main['script'].encode('utf-8'))
        self.assertIn('refs/heads/main', path.read_text(encoding='utf-8'))
        code, check = self.hook('--check')
        self.assertEqual((code, check['current']), (0, True))

    def test_a_tampered_hook_that_keeps_the_marker_is_not_current(self):
        _, installed = self.hook('--install')
        path = Path(installed['path'])
        path.write_bytes(installed['script'].replace('exit 1', 'exit 0').encode('utf-8'))
        code, check = self.hook('--check')
        self.assertEqual((code, check['installed'], check['ours'], check['foreign'], check['current']),
                         (2, True, True, False, False))
        self.assertIn('difere', check['message'])
        # a CRLF copy of the expected script is still current: only the line endings differ
        path.write_bytes(installed['script'].replace('\n', '\r\n').encode('utf-8'))
        code, check = self.hook('--check')
        self.assertEqual((code, check['current']), (0, True))

    def test_a_hooks_folder_outside_the_repository_is_refused_and_nothing_is_written(self):
        elsewhere = Path(self.temp.name) / 'hooks-elsewhere'
        elsewhere.mkdir()
        self.git(self.work, 'config', 'core.hooksPath', str(elsewhere))
        code, install = self.hook('--install')
        self.assertEqual((code, install['ok'], install['written'], install['outsideRepository']), (1, False, False, True))
        self.assertIn('core.hooksPath', install['message'])
        self.assertEqual(list(elsewhere.iterdir()), [])
        code, check = self.hook('--check')
        self.assertEqual((code, check['ok'], check['outsideRepository'], check['installed']), (2, False, True, False))
        self.assertEqual(Path(check['path']).parent, elsewhere.resolve())
        self.assertIn('core.hooksPath', check['message'])
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.assertFalse((self.work / '.git' / 'hooks' / 'pre-push').exists())
        # the user installed our hook there by hand: the check reads it as installed and current, and still writes nothing
        (elsewhere / 'pre-push').write_bytes(check['script'].encode('utf-8'))
        code, check = self.hook('--check')
        self.assertEqual((code, check['ok'], check['installed'], check['current'], check['outsideRepository']),
                         (0, True, True, True, True))
        code, install = self.hook('--install')
        self.assertEqual((code, install['written']), (1, False))
        self.assertEqual((elsewhere / 'pre-push').read_bytes(), check['script'].encode('utf-8'))

    def test_the_hook_refuses_pushing_the_local_main_and_lets_other_branches_through(self):
        self.hook('--install')
        remote_main = self.sha(self.origin, 'main')
        self.commit(self.work, 'local.txt', 'local\n', 'local work on main')
        refused = self.git(self.work, 'push', 'origin', 'main', check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('frontlights', refused.stderr)
        self.assertEqual(self.sha(self.origin, 'main'), remote_main)
        self.git(self.work, 'switch', '-q', '-c', 'claude/x')
        self.commit(self.work, 'x.txt', 'x\n', 'branch work')
        allowed = self.git(self.work, 'push', 'origin', 'claude/x', check=False)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(self.sha(self.origin, 'claude/x'), self.sha(self.work))
        disguised = self.git(self.work, 'push', 'origin', 'claude/x:main', check=False)
        self.assertNotEqual(disguised.returncode, 0)
        self.assertIn('frontlights', disguised.stderr)
        self.assertEqual(self.sha(self.origin, 'main'), remote_main)

    def test_a_foreign_hook_is_reported_and_never_overwritten(self):
        _, fresh = self.hook('--check')
        path = Path(fresh['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        foreign = b'#!/bin/sh\nexit 0\n'
        path.write_bytes(foreign)
        code, check = self.hook('--check')
        self.assertEqual((code, check['installed'], check['ours'], check['foreign']), (2, True, False, True))
        code, install = self.hook('--install')
        self.assertEqual((code, install['written'], install['ok']), (1, False, False))
        self.assertIn('frontlights', install['message'].lower())
        self.assertEqual(path.read_bytes(), foreign)

    def test_sync_advances_the_local_main_when_the_remote_moved(self):
        before = self.sha(self.work)
        tip = self.commit(self.other, 'remote.txt', 'remote\n', 'remote work')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        code, result = self.sync()
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
        code, direct = self.hook('--check')
        routed_code, routed = self.cli('homolog', 'hook', '--check', '--root', str(self.work), script=FRONTLIGHTS)
        self.assertEqual(routed_code, code)
        self.assertEqual(routed, direct)


class HomologBundleTests(unittest.TestCase):
    """S3: `homolog bundle` grava um bundle Git da main local e das branches de trabalho na pasta de
    `homolog.backupDir`; sem a chave diz que não há pasta e não grava; `inspect` recusa a chave inválida e não
    muda a saída sem ela. Só repositórios e pastas temporários; a configuração Git da máquina fica fora."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.base / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0')
        (self.base / 'gitconfig').write_text('', encoding='utf-8')
        self.work = self.base / 'work'
        self.backup = self.base / 'backup'
        self.backup.mkdir()
        self.git(None, 'init', '-q', '-b', 'main', str(self.work))
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git(self.work, 'config', key, value)
        self.commit('README.md', 'first\n', 'first')
        self.git(self.work, 'switch', '-q', '-c', 'claude/issue-1')
        self.commit('one.txt', 'one\n', 'issue 1')
        self.git(self.work, 'switch', '-q', '-c', 'claude/issue-1-s2')
        self.commit('two.txt', 'two\n', 'slice 2')
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'switch', '-q', '-c', 'other')
        self.commit('other.txt', 'other\n', 'outside the prefix')
        self.git(self.work, 'switch', '-q', 'main')

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

    def cli(self, *args, script=HOMOLOG):
        done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL, timeout=180)
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError:
            self.fail(f'sem JSON no stdout (saída {done.returncode}): {done.stdout!r} {done.stderr!r}')
        self.assertEqual(result['exitCode'], done.returncode)
        return done.returncode, result

    def bundle(self, config, *flags):
        return self.cli('bundle', '--root', str(self.work), '--config', str(config), *flags)

    def written_files(self):
        return sorted(path.name for path in self.backup.iterdir())

    def test_bundle_writes_a_verifiable_file_with_the_base_and_the_work_branches(self):
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
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
        self.assertEqual((result['prefixes'], result['prefixSource']), (['equipe/'], 'records'))

    def test_two_records_bring_both_prefixes(self):
        """Issue 44, S1: a união dos prefixos; um registro sem `branch_prefix` vale `claude/`."""
        self.team_branches()
        self.record('authorization-1.json', issued_at='2026-01-01T10:00:00+00:00')
        self.record('authorization-2.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+00:00')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']),
                         {'main', 'claude/issue-1', 'claude/issue-1-s2', 'equipe/issue-2', 'equipe/issue-2-s1'})
        self.assertEqual((result['prefixes'], result['prefixSource']), (['claude/', 'equipe/'], 'records'))

    def test_without_a_valid_record_it_keeps_the_default(self):
        """Issue 44, S1: sem registro válido, `claude/`, como antes; um registro malformado é ignorado."""
        self.team_branches()
        config = self.config(homolog={'backupDir': str(self.backup)})
        code, result = self.bundle(config)
        self.assertEqual(code, 0, result)
        self.assertEqual(set(result['refs']), {'main', 'claude/issue-1', 'claude/issue-1-s2'})
        self.assertEqual((result['prefixes'], result['prefixSource']), (['claude/'], 'default'))
        self.assertEqual(result['skipped'], 0)
        self.record('authorization-bad.json', branch_prefix='x$/')
        (self.work / '.frontlights' / 'authorization-broken.json').write_text('[1, 2]', encoding='utf-8')
        code, result = self.bundle(config)
        self.assertEqual(code, 0, result)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), (['claude/'], 'default', 2))
        self.record('authorization-new.json', branch_prefix='equipe/')
        code, result = self.bundle(config)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), (['equipe/'], 'records', 2))

    def test_a_record_with_malformed_worktrees_is_left_out_and_counted(self):
        """Issue 44, 2ª revisão: o registro com `worktrees` que não é lista fica fora dos prefixos e entra em
        `skipped`, como na leitura das branches das issues."""
        self.team_branches()
        self.record('authorization-1.json', branch_prefix='claude/')
        self.record('authorization-2.json', branch_prefix='equipe/', worktrees='x')
        code, result = self.bundle(self.config(homolog={'backupDir': str(self.backup)}))
        self.assertEqual(code, 0, result)
        self.assertEqual((result['prefixes'], result['prefixSource'], result['skipped']), (['claude/'], 'records', 1))

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
        self.assertEqual((result['prefixes'], result['prefixSource']), (['equipe/'], 'records'))
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


class HomologReleasePlanTests(unittest.TestCase):
    """S4: `homolog release-plan` lista as issues que estão na main local e ainda não em `origin/main`, conta os
    commits à frente e atrás e nomeia a branch da release sem criar nada: só lê o Git e os registros. Só
    repositórios temporários: o remoto é um repositório bare no mesmo disco, e a configuração Git da máquina fica
    fora da fixture."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.base / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0')
        (self.base / 'gitconfig').write_text('', encoding='utf-8')
        self.origin = self.base / 'origin.git'
        self.work = self.base / 'work'
        self.other = self.base / 'other'
        self.git(None, 'init', '-q', '--bare', '-b', 'main', str(self.origin))
        self.git(None, 'init', '-q', '-b', 'main', str(self.work))
        self.configure(self.work)
        self.commit(self.work, 'README.md', 'first\n', 'first')
        self.git(self.work, 'remote', 'add', 'origin', str(self.origin))
        self.git(self.work, 'push', '-q', '-u', 'origin', 'main')
        self.git(None, 'clone', '-q', str(self.origin), str(self.other))
        self.configure(self.other)
        (self.work / '.frontlights').mkdir()
        self.record({'issue': 1, 'branch': 'claude/issue-1'}, {'issue': 2, 'branch': 'claude/issue-2'},
                    {'issue': 1, 'branch': 'claude/issue-1-s2', 'slice': 'S2'})

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

    def cli(self, *args, script=HOMOLOG):
        done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL, timeout=180)
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError:
            self.fail(f'sem JSON no stdout (saída {done.returncode}): {done.stdout!r} {done.stderr!r}')
        self.assertEqual(result['exitCode'], done.returncode)
        return done.returncode, result

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

    def plan(self, *flags, script=HOMOLOG):
        return self.cli('release-plan', '--root', str(self.work), *flags, script=script)

    def deliver_direct(self, slug):
        """A branch of work without an issue, cut from the local main with one commit, merged back with --no-ff."""
        branch = f'claude/{slug}'
        self.git(self.work, 'switch', '-q', '-c', branch)
        self.commit(self.work, f'{slug}.txt', f'{slug}\n', f'work {slug}')
        self.git(self.work, 'switch', '-q', 'main')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', f'merge of {slug} into the local main', branch)
        return branch

    def full_suite(self, fail=False, root=None):
        """S3: the whole suite of the release recorded in the main worktree, on the local main, by `homolog suite
        --release --mode full` with a fake argv (green, or red with `fail`); the config lives outside the repo."""
        fake = self.base / 'fake_suite.py'
        fake.write_text('import sys\nsys.exit(1 if "--falha" in sys.argv else 0)\n', encoding='utf-8')
        config = self.base / 'config.json'
        config.write_text(json.dumps({'repository': None, 'homolog': {'backupDir': None}}), encoding='utf-8')
        argv = [sys.executable, str(fake), *(['--falha'] if fail else [])]
        code, result = self.cli('suite', '--root', str(root or self.work), '--config', str(config), '--release',
                                '--mode', 'full', '--argv', json.dumps(argv))
        self.assertEqual(code, 1 if fail else 0, result)
        return result

    def test_without_the_whole_suite_of_the_tip_the_release_is_not_ready(self):
        """S3: sem o registro da suíte inteira na ponta da main local, a release não fica pronta (exit 2)."""
        self.deliver(1)
        code, result = self.plan()
        self.assertEqual((code, result['ready']), (2, False), result)
        self.assertEqual(result['release'], [1])
        self.assertEqual(result['fullSuite']['status'], 'missing')
        self.assertIn('homolog suite --release --mode full', result['message'])
        self.assertIn(self.sha(self.work)[:7], result['message'])

    def test_the_message_names_the_base_of_the_project_in_the_command(self):
        """Revisão da issue 52, M2: num projeto cuja base não é main, o comando da suíte inteira que a mensagem
        manda rodar leva `--base <a base>`; sem ele, a release rodaria (e julgaria) a ponta da main."""
        self.git(self.work, 'switch', '-q', '-c', 'develop')
        self.git(self.work, 'push', '-q', 'origin', 'develop')
        self.git(self.work, 'switch', '-q', '-c', 'claude/issue-1')
        self.commit(self.work, 'issue-1.txt', '1\n', 'issue 1')
        self.git(self.work, 'switch', '-q', 'develop')
        self.git(self.work, 'merge', '-q', '--no-ff', '-m', 'merge of issue 1 into the local develop', 'claude/issue-1')
        code, result = self.plan('--base', 'develop')
        self.assertEqual((code, result['release'], result['fullSuite']['status']), (2, [1], 'missing'), result)
        self.assertIn('`homolog suite --release --mode full --base develop`', result['message'])

    def test_the_whole_suite_green_at_the_tip_makes_the_release_ready(self):
        self.deliver(1)
        self.full_suite()
        code, result = self.plan()
        self.assertEqual((code, result['ready']), (0, True), result)
        full = result['fullSuite']
        self.assertEqual((full['status'], full['recordedHead']), ('current', self.sha(self.work)))
        self.assertTrue(os.path.samefile(full['recordPath'], self.work / '.frontlights' / 'release' / 'suite.json'))
        self.assertIn('Release pronta', result['message'])

    def test_a_whole_suite_adopted_from_an_issue_of_the_same_tree_makes_the_release_ready(self):
        """Issue 54, S1: a issue roda a suíte inteira na ponta dela e entra na main local por `--no-ff` sem mudar
        arquivo; a adoção (`suite --release --mode full --from`) deixa o `release-plan` pronto sem rodar a suíte."""
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

    def test_a_red_whole_suite_keeps_the_release_back(self):
        self.deliver(1)
        self.full_suite(fail=True)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (2, False, 'red'), result)
        self.assertIn('homolog suite --release --mode full', result['message'])

    def test_a_delivery_after_the_whole_suite_makes_it_stale(self):
        self.deliver(1)
        self.full_suite()
        self.deliver(2)
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (2, False, 'stale'), result)
        self.assertIn('head', result['fullSuite']['changed'])
        self.assertIn(self.sha(self.work)[:7], result['message'])

    def test_an_uncommitted_edit_after_the_whole_suite_makes_it_stale(self):
        self.deliver(1)
        self.full_suite()
        (self.work / 'README.md').write_text('edited\n', encoding='utf-8')
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (2, False, 'stale'), result)
        self.assertEqual(result['fullSuite']['files_changed'], ['README.md'])

    def test_a_main_worktree_off_the_local_main_is_elsewhere(self):
        self.deliver(1)
        self.full_suite()
        self.git(self.work, 'switch', '-q', 'claude/issue-1')
        code, result = self.plan()
        self.assertEqual((code, result['ready'], result['fullSuite']['status']), (2, False, 'elsewhere'), result)
        self.assertIn('claude/issue-1', result['message'])
        self.assertIn('homolog suite --release --mode full', result['message'])

    def test_behind_and_nothing_to_release_still_come_before_the_whole_suite(self):
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
        self.assertEqual((result['prefix'], result['prefixSource']), ('equipe/', 'records'))

    def test_instants_are_compared_across_offsets_and_an_invalid_one_ranks_last(self):
        """Issue 44, S2: `Z` e fusos diferentes valem pelo instante; `issued_at` inválido fica atrás, mesmo com o
        maior nome de arquivo; sem `issued_at` em nenhum, vale o último registro pelo nome do arquivo."""
        (self.work / '.frontlights' / 'authorization.json').unlink()
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-01-02T10:00:00+05:00')
        self.record(name='authorization-b.json', branch_prefix='antigo/', issued_at='2026-01-02T06:00:00Z')
        self.record(name='authorization-z.json', branch_prefix='outro/', issued_at='ontem')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource']), ('antigo/', 'records'))
        for name in ('authorization-a.json', 'authorization-b.json', 'authorization-z.json'):
            (self.work / '.frontlights' / name).unlink()
        self.record(name='authorization-1.json', branch_prefix='primeiro/')
        self.record(name='authorization-2.json', branch_prefix='segundo/')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource']), ('segundo/', 'records'))

    def test_a_record_with_malformed_worktrees_never_names_the_release(self):
        """Issue 44, 2ª revisão: o registro que a leitura das branches ignora também não nomeia a release."""
        self.record(name='authorization-a.json', branch_prefix='equipe/', issued_at='2026-02-01T10:00:00+00:00',
                    worktrees='x')
        code, result = self.plan()
        self.assertEqual((result['prefix'], result['prefixSource'], result['skipped']), ('claude/', 'records', 1))

    def test_without_a_valid_record_the_release_keeps_the_default(self):
        """Issue 44, S2: sem registro válido, `claude/`, como antes."""
        (self.work / '.frontlights' / 'authorization.json').unlink()
        code, result = self.plan()
        self.assertRegex(result['releaseBranch'], r'^claude/release-\d{4}-\d{2}-\d{2}$')
        self.assertEqual((result['prefix'], result['prefixSource']), ('claude/', 'default'))

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

    def test_a_name_used_by_a_merged_pull_request_is_never_suggested_again(self):
        """O nome da release pula também os nomes citados em 'Merge pull request #N from dono/<nome>' no histórico
        de `origin/main`, mesmo com a branch já apagada nos dois lados; outro formato de assunto não pesa."""
        self.deliver(1)
        _, first = self.plan()
        name = first['releaseBranch']
        for number, merged in ((45, name), (46, f'{name}-2')):
            self.git(self.other, 'switch', '-q', '-c', 'feature')
            self.commit(self.other, f'pr-{number}.txt', f'{number}\n', f'pull request {number}')
            self.git(self.other, 'switch', '-q', 'main')
            self.git(self.other, 'merge', '-q', '--no-ff', '-m', f'Merge pull request #{number} from OWNER/{merged}', 'feature')
            self.git(self.other, 'branch', '-q', '-D', 'feature')
        self.git(self.other, 'switch', '-q', '-c', 'side')
        self.commit(self.other, 'side.txt', 'side\n', 'side')
        self.git(self.other, 'switch', '-q', 'main')
        self.git(self.other, 'merge', '-q', '--no-ff', '-m', f"Merge branch '{name}-3'", 'side')
        self.git(self.other, 'push', '-q', 'origin', 'main')
        self.git(self.work, 'fetch', '-q', 'origin')
        _, result = self.plan()
        self.assertEqual(result['releaseBranch'], f'{name}-3')

    def test_the_help_texts_name_the_four_operations(self):
        for text in (read('skills', 'frontlights', 'scripts', 'homolog.py').split('"""')[1],
                     read('skills', 'frontlights', 'scripts', 'frontlights.py')):
            for operation in ('`hook`', '`sync`', '`bundle`', '`release-plan`'):
                self.assertIn(operation, text)
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


if __name__ == '__main__':
    unittest.main()
