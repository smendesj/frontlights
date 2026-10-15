"""Homologação na main local (issue 32): a branch da issue é cortada da main local, fica só local e entra nela
por merge com três portões verdes; nada vai ao GitHub até a release.

Seams: `frontlights.py authorize` (S1); o texto de `SKILL.md`, `references/development.md`, `docs/protocol.md`,
`docs/security.md`, `templates/handoff.md`, `examples/authorization.json`, `README.md`, `docs/acceptance.md` e
`evals/runbook.md` (S1); `scripts/homolog.py` (`hook` e `sync`) e a entrada `frontlights.py homolog` (S2);
`scripts/homolog.py` (`bundle` e `backup_dir`) e a validação de `homolog.backupDir` no `inspect` (S3).
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

    def test_the_hook_and_the_sync_open_stage_six(self):
        """S2: a skill, a referência, o protocolo, a segurança e o README dizem quando o hook e o sync rodam, o que
        perguntam, e declaram as três escritas da skill dentro de `.git/`."""
        skill = stage(6)
        for phrase in ('**Hook and sync, at the start of every stage 6.**',
                       '"Instalar o hook `pre-push` que recusa enviar a main local?"', '"Sim, instalar"',
                       'never overwrite it', 'the only hook the skill installs',
                       '`homolog sync --root <main worktree> --base <base>`', 'never a push, a reset or a rebase',
                       '"Resolver o conflito agora na worktree principal"', 'gets neither the hook nor the sync'):
            with self.subTest(file='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        heading = '## The start of stage 6: the pre-push hook and the sync of the local main'
        self.assertLess(text.index(heading), text.index('## Slices in order'))
        body = ' '.join(text.split(heading)[1].split('## Slices in order')[0].split())
        for phrase in ('`scripts/homolog.py`', 'exit code 0 done, 1 refused or failed, 2 a question for the user',
                       '**The hook.**', '`installed`, `ours`, `foreign`, `path` and `script`', '`foreign: true`',
                       'refuses with exit code 1', 'a guard and not a barrier', '`--no-verify`',
                       '**The sync.**', 'no tracked change pending and no merge in progress',
                       '`git fetch <remote>` and `git merge --no-edit <remote>/<base>`', '`git merge --abort`',
                       'never uses `--force`, `reset` or `rebase`', 'runs again before the release'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('instala um único hook', 'não instala hooks', 'nunca sobrescreve um hook de outra origem',
                       'É uma guarda, não uma barreira', 'As escritas da skill dentro de `.git/` são três',
                       '`.git/info/exclude`', '`frontlights-serve/ports/`',
                       '**Sincronização da main local (`homolog sync`).**', 'Nunca envia, nunca usa `--force`, `reset` nem `rebase`',
                       'o merge de `origin/main` na main local pelo `homolog sync`'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        protocol = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in ('`origin/main` na main local pelo `homolog sync`', 'o hook `pre-push` de `homolog hook`',
                       'nunca por cima de um hook de outra origem'):
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
        skill = stage(6)
        for phrase in ('`homolog bundle --root <main worktree> --config <config>`', '`homolog.backupDir`',
                       'the only write the run makes outside the project', 'without the key it writes nothing'):
            with self.subTest(file='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        text = read('skills', 'frontlights', 'references', 'development.md')
        body = ' '.join(text.split('## Into the local main: the three gates')[1].split('## After the pull request')[0].split())
        for phrase in ('6. **Back it up.**', '`homolog.backupDir`', '`git bundle verify`', 'old bundles are never deleted',
                       '`configured: false`', 'name the key, ask nothing and go on', '7. **Record it.**',
                       '"sem backup configurado"'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, body)
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Backup da main local (`homolog bundle`).**', 'a única gravação da execução fora do projeto',
                       'o utilitário nunca a cria', 'nunca se sobrescreve nem se apaga um bundle', 'não há rede',
                       'nunca entra neste repositório', 'A chave nunca liga nem amplia a autorização'):
            with self.subTest(file='security.md', phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn('`homolog.backupDir` do config (`homolog bundle`; sem a chave, nada é gravado e a sessão avisa)',
                      flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('a chave `homolog.backupDir` aponta uma pasta sua, por caminho absoluto', flat('README.md'))
        example = json.loads(read('skills', 'frontlights', 'examples', 'config.json'))
        self.assertEqual(example['homolog'], {'backupDir': None})
        self.assertIn('S3: `homolog bundle` grava', flat('docs', 'acceptance.md'))
        self.assertIn('one `.bundle` file there which `git bundle verify` accepts', flat('evals', 'runbook.md'))

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
        self.assertEqual((code, check['installed'], check['ours'], check['foreign']), (0, True, True, False))
        self.assertEqual(path.read_bytes(), first['script'].encode('utf-8'))

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


if __name__ == '__main__':
    unittest.main()
