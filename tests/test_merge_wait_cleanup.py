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
                       'the release branch is the only branch of the flow that is pushed'):
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

    def test_the_release_is_offered_once_the_free_test_window_is_closed(self):
        self.assertIn('once the window of its free test is closed', ' '.join(read(
            'skills', 'frontlights', 'references', 'development.md').split()))


class CloseoutReferenceTests(unittest.TestCase):
    def setUp(self):
        self.text = read('skills', 'frontlights', 'references', 'closeout.md')
        self.flat = ' '.join(self.text.split())

    def test_a_merge_is_one_of_the_ways_into_the_closeout(self):
        for phrase in ('when the release of stage 6', 'finds its pull request merged into the approved base',
                       'Pass `--issues` with the other issues `release-plan` listed for that release',
                       'they skip the question, and the verify confirms them',
                       'the merge of an issue into the local main, or of a child into its parent\'s branch, closes nothing',
                       'comes back in `excluded` as `unchecked_criteria`: say which criteria are left'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_parent_ticks_are_line_numbers_only_and_shared_items_are_never_ticked(self):
        for phrase in ('A sub-issue candidate also carries `parentTicks`', '`lines`', '`shared`',
                       'never ticked for one of them', 'Only line numbers come from the helper',
                       'no item of the parent cites it, or the parent is closed, in another repository or unknown) is only closed'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_table_and_the_question_carry_the_ticks(self):
        for phrase in ('"marcar no corpo de #P as linhas L"', '"não marcadas: citam outras issues"',
                       '"Fechar estas <N> issues e marcar os itens dos pais?"',
                       '"Só fechar, sem marcar" comes before "Não agora" and writes only the closes (no tick)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_tick_is_written_checked_before_and_after_and_only_after_the_close(self):
        step3 = ' '.join(section(self.text, '3. Write what was approved').split())
        for phrase in ('**The tick in a parent.**', 'After a sub-issue is closed', 'the Capture command of the recipe in `issues.md`',
                       'and before that parent is closed when it is in the same list',
                       'that cites the sub-issue and no other issue, and is the line the user was shown',
                       'only the `[ ]` of those lines became `[x]`, by an exact-replace edit',
                       'closeout.py" tick-check --before <saved> --after <new> --lines <lines>',
                       'it must answer `ok` before anything is written', 'compare it with the saved copy',
                       'gh issue edit <parent> --repo <repo> --body-file <file>', '`ok` is the verification',
                       'A sub-issue whose close failed leaves its parent alone', 'only the tick is retried',
                       'run `candidates` again for the parents'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step3)
        self.assertIn('with the `tick-check` result of each parent', ' '.join(section(self.text, '4. Verify').split()))

    def test_the_cleanup_of_merged_work_runs_first_without_a_question(self):
        step5 = ' '.join(section(self.text, '5. Clean up the merged work (first, without a question)').split())
        for phrase in ('This step runs first, before the closing question of step 1',
                       'right after `git pull --ff-only origin <base>`',
                       'at stage 1 of every session whose authorization records list issue ids, after '
                       '`git fetch --prune origin` and whatever `candidates` finds (the plan alone judges what is merged',
                       'It is the written exception to "deleting anything" of the denied operations',
                       'the session removes them **without a question**',
                       'The remote branch is GitHub\'s job', '"Automatically delete head branches"',
                       'no command of the cleanup ever runs `git push origin --delete`',
                       '`git fetch --prune origin` first (`fetch_prune`',
                       'gets `copy_records` before `git worktree remove`',
                       'cleanup.py archive --from <worktree>/.frontlights --to <recordsTo>',
                       "`.frontlights/issues/<n>/worktrees/<worktree folder>-<short tip>/` (a folder of its own per archive",
                       'A destination with any differing or extra file is refused (exit 1, nothing copied)',
                       '`archive` copies what it lacks and is ok, so the removal runs again',
                       'report it and leave that item, naming the folder for the user to compare; never overwrite it',
                       'so no earlier archive is ever overwritten',
                       "under the main worktree's `.frontlights` (the main worktree read from Git for the worktree of `--from`)",
                       'Each command carries `item` (the branch of its candidate; null for the fetch)',
                       'the session runs them item by item', 'when any command of an item fails, it runs nothing more of that item',
                       '(no `git worktree remove` after a failed `copy_records`',
                       'A failed copy stops that item, so the worktree keeps its records',
                       'A local release branch (`<branch_prefix>release-<date>[-N]`',
                       'exists only when the release took the old path',
                       'with the refspec push there is no local release branch to remove',
                       '`merged_release_branch` and only `git branch -D`', 'one not merged yet is left alone and not listed',
                       'carries `ask: true`, `askReason` `ignored_files_besides_dependencies` and `askIgnored`',
                       'it is the only candidate asked about',
                       'Run `commands` in order, without a question',
                       '"Remover a worktree <pasta> com os arquivos ignorados <nomes>?"',
                       'The `excluded` stay where they are: say them in one line',
                       '--records <recordsTo>', '`copied: false`',
                       'cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base>',
                       '--integration <integration worktree>',
                       "Run it from the folder the session stands in, with `--root` pointing at the project's main worktree",
                       'the helper never offers the folder it runs in', '`--integration` names the local-only worktree of a family',
                       'it goes only when its branch holds no commit of its own that is not already in a pull request that reached the base',
                       '`contained_in_base_without_pull_request`', 'the branch of an issue that reached GitHub through a release',
                       '`ignored_files` comes with `ignoredCount` and `ignored`', 'those files go away with it',
                       "the rest of that item's commands are not run",
                       'a stacked child through its parent',
                       'A merge counts as a commit of its own when it carries content (a conflict resolved by hand, a file added to it)',
                       'Never add `--force` or `-f`', 'never retried with force', 'cleanup.py" verify',
                       'list every `gone: false`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step5)

    def test_an_issue_of_closes_still_open_after_the_merge_joins_the_closing_question(self):
        """Review r1 of issue 63 (R1-5): an issue of `closes` that the verify still shows open after the merge is
        read once more and, still open, joins the closing question of step 2 with the reason in one line."""
        step1 = ' '.join(section(self.text, '1. Find the candidates (read only)').split())
        for phrase in ('first run `closeout.py verify --issues <closes>`',
                       'an issue it reports still open is read once more (the same verify, a few seconds later)',
                       'one still open then joins the closing question of step 2',
                       'with the reason said in one line (the `Closes #n` of the merged pull request did not close it)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step1)
        self.assertNotIn('stays out of this list too', step1)
        step4 = ' '.join(section(self.text, '4. Verify').split())
        self.assertIn('an issue of `closes` still open there was already read twice and asked in step 2', step4)

    def test_the_question_of_a_candidate_that_asks_fits_the_five_word_limit(self):
        step5 = ' '.join(section(self.text, '5. Clean up the merged work (first, without a question)').split())
        asking = step5.split('For each candidate with `ask: true`, ask with `AskUserQuestion`', 1)[1].split(', naming the files')[0]
        labels = list(dict.fromkeys(x for x in re.findall(r'"([^"]+)"', asking) if not x.startswith('Remover a worktree')))
        self.assertEqual(labels, ['Sim, remover', 'Não, manter'])
        self.assertTrue(all(len(label.split()) <= 5 for label in labels))

    def test_the_sync_offer_moved_to_step_six_and_the_never_list_names_the_new_limits(self):
        self.assertTrue(section(self.text, '6. Let RoadS see it'))
        never = ' '.join(section(self.text, 'Never').split())
        self.assertIn('step 5 (the cleanup of the merged work, without a question) runs first, before the closing question of step 1',
                      self.flat)
        for phrase in ('the one body edit is the approved tick of the item of a parent that cites a sub-issue closed in the same list',
                       'Close an issue on the strength of the merge alone',
                       'Remove a worktree or a branch that `cleanup.py plan` did not offer (or, with `ask: true`, that the user did not approve)',
                       'delete a remote branch (`git push origin --delete`: GitHub deletes the merged head branch), use `--force`',
                       'Merge a pull request, deploy or release: the closeout never does'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, never)

    def test_every_reason_the_cleanup_script_produces_is_documented(self):
        source = read('skills', 'frontlights', 'scripts', 'cleanup.py')
        for code in ('main_worktree', 'current_directory', 'detached_head', 'not_a_worktree', 'path_missing', 'unsafe_path',
                     'unsafe_branch', 'protected_branch', 'uncommitted_changes', 'unreadable_status', 'open_pr',
                     'no_merged_pr', 'newer_than_merged_pr', 'merged_into_other_branch', 'ancestry_unverifiable',
                     'open_dependents', 'pull_requests_unreadable', 'merged_release_branch', 'ignored_files_besides_dependencies',
                     'fetch_prune', 'copy_records',
                     'frontlights_records', 'branch_differs_from_authorization', 'locked_worktree', 'checked_out_elsewhere',
                     'not_found', 'integration_has_pull_request', 'integration_pushed', 'integration_has_unique_commits',
                     'ignored_files', 'local_only_integration',
                     'slice_not_in_issue_branch', 'slice_has_pull_request', 'slice_pushed', 'slice_issue_branch_unknown',
                     'slice_is_issue_branch', 'slice_merged_into_issue_branch', 'contained_in_base_without_pull_request'):
            with self.subTest(code=code):
                self.assertIn(f"'{code}'", source, 'the script no longer produces it')
                self.assertIn(code, self.flat, 'the reference does not explain it')

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
                       'never a remote branch (GitHub deletes it)',
                       'Closing (with the tick in a parent, in the same approval) waits for its own'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage7)
        closeout = ' '.join(read('skills', 'frontlights', 'references', 'closeout.md').split())
        for phrase in ('**The tick in a parent.**', 'scripts/cleanup.py', 'with **its own approval**'):
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
                             'A branch remota nunca é apagada pela limpeza', 'a branch local da release mesclada',
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
                                      'nunca `git push origin --delete`, porque o GitHub apaga a branch de cabeça da PR mesclada',
                                      'worktrees/<pasta>-<tip curto>/ cópia do `.frontlights` de cada worktree da issue'),
            ('skills', 'frontlights', 'templates', 'handoff.md'): ('Aguardando o merge',),
            ('skills', 'frontlights', 'references', 'closeout.md'): ('`contained_in_base_without_pull_request`',
                                                                    'parentTicks', 'line numbers'),
            ('skills', 'frontlights', 'docs', 'security.md'): ('A limpeza de worktrees e branches (`scripts/cleanup.py`) só lê, exceto o `archive`:',
                                      'a sessão age só sobre a resposta do `merge-status`, e o gatilho do ambiente (inscrição na PR ou monitor) só a acorda',
                                      'um item que cita outras issues junto nunca é marcado', 'nunca com `--force`',
                                      'cujo tip é a cabeça de uma PR mesclada que chegou à base aprovada',
                                      'ou, sem PR nenhuma, cujo tip já está contido em `origin/<base>`',
                                      'a branch remota nunca entra: o GitHub apaga a branch de cabeça da PR mesclada',
                                      'o `archive` é a única escrita do script',
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
                       'No command is `git push origin --delete`', 'before `git worktree remove`',
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
