"""A release (da main local ao GitHub), a espera do merge dela, fechar, marcar no pai e limpar worktrees e branches:
o texto da skill, das referências, dos modelos, dos docs e do eval diz o mesmo que os scripts `closeout.py` e
`cleanup.py` fazem.

Seams: o texto de `SKILL.md`, `references/development.md`, `references/closeout.md`, `templates/handoff.md`,
`docs/`, `README.md` e `evals/`; os scripts têm os próprios testes (`test_closeout.py`, `test_cleanup.py`). A espera
é uma regra da skill (o Frontlights não a impõe), então ela só se prova pelo texto e pela revisão manual de
`evals/merge-wait-and-cleanup.md`.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def section(text, heading, marks='##'):
    match = re.search(rf'^{marks} {re.escape(heading)}\n(.*?)(?=^#{{1,{len(marks)}}} |\Z)', text, re.M | re.S)
    return match.group(1) if match else ''


class WaitTests(unittest.TestCase):
    def setUp(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        self.wait = ' '.join(section(text, 'The release: from the local main to GitHub').split())

    def test_the_wait_is_the_default_and_the_user_can_end_it(self):
        for phrase in ("By default, as soon as the release's pull request is open, the session waits for the user's merge",
                       '"não aguardar"', 'the closeout question of the next session picks the work up',
                       '"Lançar a release com as issues #a, #b agora?"', '"Sim, lançar" first and "Agora não" second',
                       'the release branch and the branch of each issue are the only branches of the flow that are pushed'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_it_is_said_to_the_user_and_recorded_in_the_handoff(self):
        for phrase in ('One line to the user, in their language', 'the `Release` line', 'head and base branch',
                       'the approved base'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_only_the_closes_of_the_release_plan_carry_a_closing_keyword(self):
        """Issue 63, S3: `Closes #n` só para as issues do `closes` do `release-plan`; as outras sem palavra."""
        for phrase in ('one `Closes #n` line per issue of the `closes` of the last `release-plan`, copied from that list, '
                       'never counted by hand',
                       'is cited by number without a closing keyword (`Closes`, `Fixes`, `Resolves` or a variant of them), '
                       'in the body and in the commits, and follows the closing question of stage 7',
                       'The merge itself stays a denied operation'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_notification_is_only_a_trigger_and_merge_status_decides(self):
        for phrase in ('Either is only a trigger', 'run `merge-status` and act only on its answer, never on the notification',
                       'may not report a merge at all, so the monitor is the dependable trigger',
                       'prints one short line only when the set of `ready` or `settled` PRs changes',
                       '`${CLAUDE_SKILL_DIR}` may be unset in a background shell', 'The user can also say "mesclei"',
                       'closeout.py" merge-status --config <config> --prs <n> --base <approved base>',
                       'the same GitHub account as the session\'s `gh`',
                       'When the host offers neither, say so in the handoff and stop waiting'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_only_a_merge_into_the_approved_base_counts(self):
        for phrase in ('`ready` lists the PRs merged into the approved base',
                       'A PR merged into another branch, closed without a merge, or not found is never ready',
                       '`git pull --ff-only origin <base>`', 'if it does not fast-forward, stop and ask instead of merging or resetting',
                       '`contained_in_base_without_pull_request`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_merge_leads_to_the_cleanup_first_then_the_closing_approval_and_independent_work_goes_on(self):
        for phrase in ('first the cleanup of the merged work (step 5), without approval and before any closing question',
                       '`git fetch --prune`, the records of each worktree copied to the main worktree, the worktrees and the local branches of the issues, the slices and the merged release removed',
                       'then `closeout.py verify --issues <closes>` only confirms the issues of `closes` (closed by the '
                       'merge), and the closing of the rest (with the tick in a parent, for a sub-issue) has its own approval',
                       'An issue whose criteria are not all ticked is not offered: say which are left, and tick only what the evidence supports',
                       'The wait never blocks independent issues'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_stacking_rule_points_to_the_wait_and_the_skill_states_it_in_stage_six(self):
        self.assertIn('the family enters the local main as one', flat('skills', 'frontlights', 'references', 'development.md'))
        stage6 = ' '.join(read('skills', 'frontlights', 'SKILL.md').split('## 6.')[1].split('## 7.')[0].split())
        self.assertIn('8. **The release** (development.md, "The release"), offered at the end of each homologated issue',
                      stage6)
        release = ' '.join(read('skills', 'frontlights', 'references', 'development.md')
                           .split('## The release: from the local main to GitHub')[1].split())
        for phrase in ('"Lançar a release com as issues #a, #b agora?"', '**`Closes #n` only from `closes`.**',
                       '"Mesclar a PR #<n> em <base>?"', '`git pull --ff-only origin <base>`',
                       'A PR merged into another branch, closed without a merge, or not found is never ready',
                       'offers the release again with everything accumulated'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, release)


class FreeTestHandoffTests(unittest.TestCase):
    """Issue 69, S3: o handoff ganha a linha do teste livre logo depois da linha do merge na main local."""

    def test_the_handoff_has_the_free_test_line_after_the_local_main_merge(self):
        lines = read('skills', 'frontlights', 'templates', 'handoff.md').splitlines()
        merge = [i for i, line in enumerate(lines) if line.startswith('- Merge na main local')]
        free = [i for i, line in enumerate(lines) if line.startswith('- Teste livre na main local')]
        self.assertEqual(len(merge), 1)
        self.assertEqual(len(free), 1)
        self.assertEqual(free[0], merge[0] + 1)
        for phrase in ('janela fechada', '`serve stop`', 'pulado'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, lines[free[0]])

    def test_the_free_test_line_records_the_fixes_and_their_batch(self):
        """Issue 69, S4: a linha do teste livre registra as correções, os commits, o arquivo do lote, o carimbo e a
        resposta literal."""
        line = [line for line in read('skills', 'frontlights', 'templates', 'handoff.md').splitlines()
                if line.startswith('- Teste livre na main local')][0]
        for phrase in ('cada correção pedida', 'o commit dela', '`.frontlights/issues/<n>/teste-livre-cas.md`',
                       'o carimbo', 'a resposta literal', 'a escrita só por acréscimo'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_the_free_test_line_records_the_terminal_variant(self):
        """Issue 69, S5: sem tela, a linha do teste livre registra os comandos dados e a resposta literal."""
        line = [line for line in read('skills', 'frontlights', 'templates', 'handoff.md').splitlines()
                if line.startswith('- Teste livre na main local')][0]
        self.assertIn('sem tela, no terminal: os comandos dados e a resposta literal da pergunta de fim do teste',
                      line)

    def test_the_release_is_offered_once_the_free_test_window_is_closed(self):
        self.assertIn('once the window of its free test is closed', ' '.join(read(
            'skills', 'frontlights', 'references', 'development.md').split()))


class CloseoutReferenceTests(unittest.TestCase):
    """Issue 2 do redesenho: a mecânica da limpeza e do fechamento foi para `cleanup.py run` e `closeout.py
    run`/`apply` (e as razões para o `--help`); a referência guarda as regras que a sessão decide."""

    def setUp(self):
        self.text = read('skills', 'frontlights', 'references', 'closeout.md')
        self.flat = ' '.join(self.text.split())

    def test_a_merge_is_one_of_the_ways_into_the_closeout(self):
        for phrase in ('when the release of stage 6', 'finds its pull request merged into the approved base',
                       'pass `--issues` with the rest of what `release-plan` listed',
                       'they skip the question', 'A merge into the local main closes nothing',
                       '`unchecked_criteria` and `no_criteria` with the counts (say which criteria are left'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_parent_ticks_are_line_numbers_only_and_shared_items_are_never_ticked(self):
        for phrase in ('A sub-issue carries `parentTicks`', '`lines` of its open parent that cite it alone',
                       '`shared`, never ticked', 'Without `parentTicks` it is only closed'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_table_and_the_question_carry_the_ticks(self):
        for phrase in ('"marcar no corpo de #P as linhas L"', '"não marcadas: citam outras issues"',
                       '"Fechar estas <N> issues e marcar os itens dos pais?"',
                       '"Só fechar, sem marcar" (only with ticks)', '"Só fechar, sem marcar" skips it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_tick_is_written_by_apply_checked_before_and_after_and_only_after_the_close(self):
        step3 = ' '.join(section(self.text, '3. Write what was approved').split())
        for phrase in ('**The tick in a parent.**', 'After a sub-issue closes, and before its parent does',
                       "`apply` ticks the parent's `lines` in one write",
                       'capture, check, `tick-check`, `gh issue edit --body-file`, reread, `tick-check`',
                       '`.frontlights/issues/<parent>/`', 'a child that fails holds its parent back',
                       'Retry only what is in `failed`', 'Then `run` again: a parent now complete gets the same question'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step3)
        self.assertIn('with the `tick-check` result of each parent', ' '.join(section(self.text, '4. Verify').split()))

    def test_the_cleanup_of_merged_work_runs_first_without_a_question(self):
        step5 = ' '.join(section(self.text, '5. Clean up the merged work (first, without a question)').split())
        for phrase in ('right after `git pull --ff-only origin <base>`, with `--issues` from `release-plan`',
                       'at stage 1, right after `frontlights.py open`, when the authorization records list issue ids',
                       'It is the written exception to "deleting anything" of the denied operations',
                       '**without a question**, whatever the closing answer',
                       'cleanup.py" run --from-authorizations [--issues 12,13] [--integration <worktree>]',
                       '`run` fetches, plans again and runs only that fresh plan, item by item',
                       "archive of the worktree's `.frontlights`, its junctions undone, `git worktree remove`, `git branch -D`",
                       'A failed command stops its item, never retried and never with `--force`',
                       'GitHub deletes merged head branches; the released issue branch is the exception',
                       "`run` leaves its `git push origin --delete` and the local delete after it in `sessionCommands`, for the session, in order",
                       '`contained_in_base_without_pull_request`', '`slice_merged_into_issue_branch`',
                       'saved outputs older than 30 days', 'on "Sim", `run` again with `--yes <key>`',
                       '`excluded` (`in_use` included) is said in one line',
                       'reasons and cautions are in `cleanup.py --help`',
                       'The `verify` and `.frontlights/cleanup-<…>.json` go to the handoff'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step5)

    def test_an_issue_of_closes_still_open_after_the_merge_joins_the_closing_question(self):
        """Review r1 of issue 63 (R1-5): an issue of `closes` that the verify still shows open after the merge is
        read once more and, still open, joins the closing question of step 2 with the reason in one line."""
        step1 = ' '.join(section(self.text, '1. Find the candidates (read only)').split())
        for phrase in ('First run `closeout.py verify --issues <closes>`',
                       'one still open is read once more a few seconds later',
                       'joins the question of step 2 with the reason in one line'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step1)
        step4 = ' '.join(section(self.text, '4. Verify').split())
        self.assertIn("at a release's merge verify the `closes` too", step4)

    def test_the_question_of_a_candidate_that_asks_fits_the_five_word_limit(self):
        step5 = ' '.join(section(self.text, '5. Clean up the merged work (first, without a question)').split())
        asking = step5.split('ignorados <nomes>?"', 1)[1].split('; on "Sim"')[0]
        labels = list(dict.fromkeys(x for x in __import__('re').findall(r'"([^"]+)"', asking)))
        self.assertEqual(labels, ['Sim, remover', 'Não, manter'])
        self.assertTrue(all(len(label.split()) <= 5 for label in labels))

    def test_the_sync_offer_is_step_six_and_the_never_list_names_the_limits(self):
        self.assertTrue(section(self.text, '6. Let RoadS see it'))
        never = ' '.join(section(self.text, 'Never').split())
        self.assertIn('Step 5 (the cleanup, without a question) runs first', self.flat)
        for phrase in ('the one body edit is the approved tick of the item of a parent that cites a sub-issue closed in the same list',
                       'on the strength of the merge alone', 'from a list not approved with its stamp',
                       'Remove what `cleanup.py run` did not offer, an `ask: true` without its yes, a remote branch other '
                       "than the released issue's; use `--force`",
                       'Merge a pull request, deploy or release: the closeout never does'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, never)

    def test_every_status_merge_status_produces_is_documented_where_the_wait_reads_it(self):
        source = read('skills', 'frontlights', 'scripts', 'closeout.py')
        wait = flat('skills', 'frontlights', 'references', 'development.md')
        for code in ('merged_into_base', 'merged_elsewhere', 'closed_unmerged', 'not_found', 'unknown', 'open'):
            self.assertIn(f"'{code}'", source)
        for phrase in ('`ready`', 'merged into another branch', 'closed without a merge', 'not found'):
            self.assertIn(phrase, wait)


class StageSevenAndTemplatesTests(unittest.TestCase):
    def test_stage_seven_names_the_wake_the_tick_and_the_cleanup(self):
        stage7 = ' '.join(read('skills', 'frontlights', 'SKILL.md').split('## 7.')[1].split())
        for phrase in ("when the wait of stage 6 finds the release's pull request merged into the approved base",
                       'the cleanup of the merged work (closeout.md, step 5) runs first, without a question',
                       "and of remote branches only the released issue's (GitHub deletes the others)",
                       'Closing (with the tick in a parent, in the same approval) waits for its own'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage7)
        closeout = ' '.join(read('skills', 'frontlights', 'references', 'closeout.md').split())
        for phrase in ('**The tick in a parent.**', 'scripts/cleanup.py" run', 'with **its own approval**'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)

    def test_the_handoff_template_has_the_wait_and_the_closing_and_cleanup_lines(self):
        text = flat('skills', 'frontlights', 'templates', 'handoff.md')
        for phrase in ('Release (a saída do `release-plan`', 'Aguardando o merge da PR única', 'ou "não aguardar" com a resposta literal do usuário',
                       'Fechamento e limpeza (a lista aprovada do fechamento e a resposta literal; da limpeza, que roda antes e sem pergunta',
                       '`closeout.py verify`, `tick-check` e `cleanup.py verify`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class DocsAndEvalsTests(unittest.TestCase):
    def test_the_documents_carry_the_rules(self):
        cases = {
            ('README.md',): ('#### Homologar na main local, lançar a release, fechar e limpar', 'aguarda o seu merge por padrão',
                             'pergunta se lança a release com elas agora', 'a branch `<prefixo>release-<data>`',
                             'A PR leva `Closes #n` só para as issues do `closes` do `release-plan`',
                             'só vale o merge **na branch base aprovada**',
                             '`closeout.py tick-check` antes e depois', 'Sem item citando a filha, ela só fecha',
                             '`cleanup.py plan`', 'Nunca usa `--force`', 'A limpeza não depende da resposta ao fechamento',
                             'logo depois do `git pull --ff-only` e sem pergunta', 'Primeiro `git fetch --prune`',
                             '`.frontlights/issues/<n>/worktrees/<pasta>-<tip curto>/` da worktree principal (`cleanup.py archive`)',
                             'também no início de toda sessão nova cujos registros de autorização listam issues, depois de um `git fetch --prune origin`',
                             'se o `verify` ainda a vê aberta depois de relê-la uma vez, ela entra na pergunta de fechamento, com a razão numa linha',
                             'Das branches remotas, a limpeza só apaga a da issue (`git push origin --delete`)',
                             'nunca a de uma slice, da integração, da release ou uma protegida',
                             'a branch local da release mesclada',
                             'A espera é regra da skill, não barreira do Frontlights',
                             '`python scripts/closeout.py candidates|verify|merge-status|tick-check ...`',
                             '`python scripts/cleanup.py plan|verify ...`',
                             'Os arquivos que o Git ignora (um `.env`, `node_modules`) vão embora com a worktree',
                             'só pergunta antes a worktree que tem arquivo ignorado fora de pastas de dependência ou build',
                             'A worktree de integração local da família (nunca enviada, sem PR)'),
            ('skills', 'frontlights', 'docs', 'protocol.md'): ('| Release |', '| Limpeza |', 'só `merged_into_base` vale',
                                      'a família entra na main local pela branch do pai, com as filhas dentro',
                                      'a issue não é relatada como revisada com ela; o portão do merge na main local (o teste assistido)',
                                      '(`parentTicks`', '`closeout.py tick-check` confere antes e depois',
                                      '`scripts/cleanup.py plan|verify`', 'nunca com `--force`',
                                      'roda antes do fechamento, logo depois do `git pull --ff-only`, sem pergunta',
                                      'o único `git push origin --delete` é o da branch da issue, quando `origin/<base>` já contém a ponta dela no GitHub',
                                      'worktrees/<pasta>-<tip curto>/ cópia do `.frontlights` de cada worktree da issue'),
            ('skills', 'frontlights', 'templates', 'handoff.md'): ('Aguardando o merge',),
            ('skills', 'frontlights', 'references', 'closeout.md'): ('`contained_in_base_without_pull_request`',
                                                                    'parentTicks', 'Only line numbers'),
            ('skills', 'frontlights', 'docs', 'security.md'): ('A limpeza de worktrees e branches (`scripts/cleanup.py`) só lê, exceto o `archive`, o `unlink` e o `run`:',
                                      'A abertura (`frontlights.py open`) só lê',
                                      'nunca roda `git push`: o `git push origin --delete` da branch da issue lançada e o `branch -D` dela ficam em `sessionCommands`',
                                      'desfeitos com `os.rmdir` (só o link; nunca o alvo, nunca dentro de `.frontlights`)',
                                      'fica em `excluded` como `in_use`', '(`junction_unverifiable`)',
                                      'grava `.frontlights/cleanup-<data>.json` como evidência',
                                      'o `unlink` apaga', 'cópia byte a byte do mesmo caminho na worktree principal',
                                      'O `apply` (`--expect <carimbo> --answer "<resposta literal>" [--only n…]`)',
                                      'recusa (`lista mudou: …`, nada escrito)',
                                      'recusa um `--only` que deixe um pai escolhido sem a filha da lista',
                                      'grava `.frontlights/closeout-<data>.result.json`',
                                      'a sessão age só sobre a resposta do `merge-status`, e o gatilho do ambiente (inscrição na PR ou monitor) só a acorda',
                                      'um item que cita outras issues junto nunca é marcado', 'nunca com `--force`',
                                      'cujo tip é a cabeça de uma PR mesclada que chegou à base aprovada',
                                      'ou, sem PR nenhuma, cujo tip já está contido em `origin/<base>`',
                                      'das branches remotas, só a da issue (a entrada da issue sem `slice`, nunca a `-integra`, a da release ou uma protegida) entra',
                                      'nenhuma outra branch remota entra: o GitHub apaga a branch de cabeça da PR mesclada',
                                      'o `archive` copia o `.frontlights` de uma worktree (nunca a pasta `out/`)',
                                      'recusa um destino com arquivo diferente ou a mais (nada é copiado, nada é sobrescrito)',
                                      'e destino fora do `.frontlights` da worktree principal daquele repositório (lida do Git)',
                                      'a limpeza do trabalho mesclado roda sem pergunta (a exceção escrita a "apagar qualquer coisa" das operações negadas)',
                                      'usa `git --no-optional-locks` sem shell', 'o aviso `ignored_files` lista os nomes',
                                      'a worktree de integração local (`--integration`) só entra sem PR'),
        }
        for name, phrases in cases.items():
            text = flat(*name)
            for phrase in phrases:
                with self.subTest(doc=name[-1], phrase=phrase):
                    self.assertIn(phrase, text)

    def test_the_eval_the_runbook_and_the_record_cover_the_case(self):
        text = flat('evals', 'merge-wait-and-cleanup.md')
        for phrase in ('the session says in one line that it waits for the merge', 'the notification alone is never taken as proof',
                       '"Lançar a release com as issues #a, #b agora?"', 'pushes only that branch',
                       '`git push origin main:refs/heads/<release branch>`', '`git pull --ff-only`',
                       '`contained_in_base_without_pull_request`', 'marcar no corpo de #P a linha L', 'the item that cites two issues is listed as not ticked',
                       'exactly the listed line with `[ ]` turned into `[x]`', '`tick-check` answers `ok` before the write and on the reread',
                       'before any closing question and without asking, the cleanup of the merged work', 'with no `--force`',
                       'no other command is `git push origin --delete`', 'right before its local `git branch -D`',
                       'before `git worktree remove`',
                       '"Não agora" to the closing leaves the cleanup done already',
                       'the next `/frontlights` start runs `git fetch --prune origin` and then `cleanup.py plan` for the issue ids of the '
                       'authorization records, without a question, and then asks the closeout question',
                       '`.frontlights/issues/<n>/worktrees/<folder>-<short tip>/`',
                       'Reject:', 'it is a rule of the skill', 'Cleanup details (same case)', 'Reject (cleanup):',
                       'removing a worktree without naming the ignored files that go with it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        runbook = flat('evals', 'runbook.md')
        self.assertIn('17. Merge wait, closing, parent tick and cleanup (`evals/merge-wait-and-cleanup.md`)', runbook)
        self.assertNotIn('runs the cleanup of the merged work it finds', runbook)
        self.assertIn('the next `/frontlights` start runs `git fetch --prune origin` and then `cleanup.py plan` for the '
                      'issue ids of the authorization records (an issue already closed by `Closes #n` included)', runbook)
        self.assertIn('| 17. Espera do merge, marcação no pai e limpeza | Pendente |', flat('docs', 'acceptance.md'))

    def test_the_new_files_carry_no_machine_path_and_no_real_name(self):
        names = [ROOT / 'evals' / 'merge-wait-and-cleanup.md', ROOT / 'skills' / 'frontlights' / 'scripts' / 'cleanup.py', ROOT / 'tests' / 'test_cleanup.py',
                 SKILL / 'references' / 'closeout.md', SKILL / 'references' / 'development.md', ROOT / 'skills' / 'frontlights' / 'templates' / 'handoff.md']
        for path in names:
            text = path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertIsNone(re.search(r'[A-Za-z]:[\\/]+(Users|Software)\b|/(home|Users)/[A-Za-z]', text), 'a machine path')
                self.assertIsNone(re.search(r'github\.com/(?!OWNER/REPOSITORY)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(issues|pull)/\d+', text),
                                  'a real issue or pull request address')


if __name__ == '__main__':
    unittest.main()
