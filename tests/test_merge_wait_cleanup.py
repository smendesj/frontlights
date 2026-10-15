"""Aguardar o merge, fechar, marcar no pai e limpar worktrees e branches: o texto da skill, das referências, dos
modelos, dos docs e do eval diz o mesmo que os scripts `closeout.py` e `cleanup.py` fazem.

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
        self.wait = ' '.join(section(text, 'After the pull request: waiting for the merge').split())

    def test_the_wait_is_the_default_and_the_user_can_end_it(self):
        for phrase in ('By default, as soon as a PR of the family is open, the session waits for the user\'s merge',
                       '"não aguardar"', 'the closeout question of the next session picks the work up'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_it_is_said_to_the_user_and_recorded_in_the_handoff(self):
        for phrase in ('One line to the user, in their language', '`Aguardando o merge`', 'head and base branch',
                       'the approved base'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_no_pr_of_the_plugin_carries_a_closing_keyword(self):
        for phrase in ('never carries `Closes`, `Fixes`, `Resolves` or a variant of them, in its body or in its commits',
                       'closing an issue has its own approval'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_notification_is_only_a_trigger_and_merge_status_decides(self):
        for phrase in ('Either is only a trigger', 'run `merge-status` and act only on its answer, never on the notification',
                       'may not report a merge at all, so the monitor is the dependable trigger',
                       'prints one short line only when the set of `ready` or `settled` PRs changes',
                       '`${CLAUDE_SKILL_DIR}` may be unset in a background shell', 'The user can also say "mesclei"',
                       'closeout.py" merge-status --config <config> --prs 12,13 --base <approved base>',
                       'the same GitHub account as the session\'s `gh`',
                       'When the host offers neither, say so in the handoff and stop waiting'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_only_a_merge_into_the_approved_base_counts(self):
        for phrase in ('`ready` lists the PRs merged into the approved base',
                       'A PR merged into another branch (a stacked parent), closed without a merge, or not found is never ready',
                       'shows as `merged_elsewhere`: its work reaches the base through the parent',
                       "its issue enters the closeout together with the parent's, once the parent's PR is `ready` with a `mergedAt` later than the child's",
                       'A child PR not merged yet is retargeted when the parent merges'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_merge_leads_to_three_separate_approvals_and_independent_work_goes_on(self):
        for phrase in ('the closing (with the tick in a parent, for a sub-issue) and the cleanup of worktrees and branches are two separate approvals, in that order',
                       'An issue whose criteria are not all ticked is not offered: say which are left, and tick only what the evidence supports',
                       'The wait never blocks independent issues'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.wait)

    def test_the_stacking_rule_points_to_the_wait_and_the_skill_states_it_in_stage_six(self):
        self.assertIn('the wait below is how the session learns it', flat('skills', 'frontlights', 'references', 'development.md'))
        stage6 = ' '.join(read('skills', 'frontlights', 'SKILL.md').split('## 6.')[1].split('## 7.')[0].split())
        for phrase in ("After a PR is opened, wait for the user's merge by default", '"After the pull request"',
                       'open no PR with a closing keyword and never merge',
                       'a PR merged into another branch or closed unmerged closes nothing'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage6)


class CloseoutReferenceTests(unittest.TestCase):
    def setUp(self):
        self.text = read('skills', 'frontlights', 'references', 'closeout.md')
        self.flat = ' '.join(self.text.split())

    def test_a_merge_is_one_of_the_ways_into_the_closeout(self):
        for phrase in ('when the wait for the merge of stage 6', 'finds a pull request merged into the approved base',
                       'pass `--issues` with the issues of the pull requests `merge-status` lists as `ready`',
                       'the merge of a child into its parent\'s branch closes nothing',
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
                       '"Fechar estas <N> issues, mover os cartões para Done e marcar os itens dos pais?"',
                       '"Só fechar, sem mover" writes only the closes (no move and no tick)'):
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

    def test_the_cleanup_is_its_own_approval_after_the_closing_was_written(self):
        step5 = ' '.join(section(self.text, '5. Clean up what the work left behind (its own approval)').split())
        for phrase in ('Ask this only after the closing of the approved list was written and verified',
                       'when the user answered "Não agora" to the closing, ask nothing here',
                       'removing them is a write of its own, with **its own approval**',
                       'cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base>',
                       '--integration <integration worktree>',
                       "Run it from the folder the session stands in, with `--root` pointing at the project's main worktree",
                       'the helper never offers the folder it runs in', '`--integration` names the local-only worktree of a family',
                       'it goes only when its branch holds no commit of its own that is not already in a pull request that reached the base',
                       '`ignored_files` comes with `ignoredCount` and `ignored`', 'those files go away with it',
                       'the remote branch goes only when `origin` is this repository',
                       'that the files in `ignored` go too (name them)',
                       'recommend "Escolher quais" instead when some candidate has `frontlights_records` or an `ignored` list with anything besides dependency or build folders',
                       "the rest of that item's commands are not run",
                       'a stacked child through its parent',
                       'A merge counts as a commit of its own when it carries content (a conflict resolved by hand, a file added to it)',
                       '"Remover estas <N> worktrees e branches?"', '"Sim, remover tudo" first and recommended',
                       '"Escolher quais"', '"Não agora"', 'a worktree with `frontlights_records` takes those records with it',
                       'Never add `--force` or `-f`', 'never retried with force', 'cleanup.py" verify',
                       'list every `gone: false`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step5)

    def test_the_cleanup_options_fit_the_five_word_limit(self):
        step5 = ' '.join(section(self.text, '5. Clean up what the work left behind (its own approval)').split())
        asking = step5.split('Then ask with `AskUserQuestion`:', 1)[1].split('Record the answer')[0]
        labels = list(dict.fromkeys(x for x in re.findall(r'"([^"]+)"', asking) if not x.startswith('Remover estas')))
        self.assertEqual(labels, ['Sim, remover tudo', 'Escolher quais', 'Não agora'])
        self.assertTrue(all(len(label.split()) <= 5 for label in labels))

    def test_the_sync_offer_moved_to_step_six_and_the_never_list_names_the_new_limits(self):
        self.assertTrue(section(self.text, '6. Let RoadS see it'))
        never = ' '.join(section(self.text, 'Never').split())
        for phrase in ('the one body edit is the approved tick of the item of a parent that cites a sub-issue closed in the same list',
                       'Close an issue on the strength of the merge alone',
                       'Remove a worktree or a branch that is not in an approved cleanup list, use `--force`',
                       'Merge a pull request, deploy or release: the closeout never does'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, never)

    def test_every_reason_the_cleanup_script_produces_is_documented(self):
        source = read('skills', 'frontlights', 'scripts', 'cleanup.py')
        for code in ('main_worktree', 'current_directory', 'detached_head', 'not_a_worktree', 'path_missing', 'unsafe_path',
                     'unsafe_branch', 'protected_branch', 'uncommitted_changes', 'unreadable_status', 'open_pr',
                     'no_merged_pr', 'newer_than_merged_pr', 'merged_into_other_branch', 'ancestry_unverifiable',
                     'open_dependents', 'pull_requests_unreadable', 'remote_branch_gone', 'remote_branch_moved',
                     'frontlights_records', 'branch_differs_from_authorization', 'locked_worktree', 'checked_out_elsewhere',
                     'not_found', 'integration_has_pull_request', 'integration_pushed', 'integration_has_unique_commits',
                     'ignored_files', 'local_only_integration', 'origin_is_not_the_repository',
                     'slice_not_in_issue_branch', 'slice_has_pull_request', 'slice_pushed', 'slice_issue_branch_unknown',
                     'slice_merged_into_issue_branch'):
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
        for phrase in ('when the wait of stage 6 finds a pull request merged into the approved base',
                       "adds for a closed sub-issue the tick of the parent's item that cites it",
                       'asks separately whether to remove the worktrees and branches the work created',
                       '`scripts/cleanup.py`, its own approval'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage7)

    def test_the_handoff_template_has_the_wait_and_the_closing_and_cleanup_lines(self):
        text = flat('skills', 'frontlights', 'templates', 'handoff.md')
        for phrase in ('Aguardando o merge (cada PR com a issue', 'ou "não aguardar" com a resposta literal do usuário',
                       'Fechamento e limpeza (a lista aprovada de cada um, a resposta literal, os comandos rodados',
                       '`closeout.py verify`, `tick-check` e `cleanup.py verify`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class DocsAndEvalsTests(unittest.TestCase):
    def test_the_documents_carry_the_rules(self):
        cases = {
            ('README.md',): ('#### Esperar o merge, fechar, marcar no pai e limpar', 'aguarda o seu merge por padrão',
                             'nunca leva palavra de fechamento', 'só vale o merge **na branch base aprovada**',
                             '`closeout.py tick-check` antes e depois', 'Sem item citando a filha, ela só fecha',
                             '`cleanup.py plan`', 'Nunca usa `--force`', 'Responder "Não agora" ao fechamento não gera a pergunta da limpeza',
                             'A espera é regra da skill, não barreira do Frontlights',
                             '`python scripts/closeout.py candidates|verify|merge-status|tick-check ...`',
                             '`python scripts/cleanup.py plan|verify ...`', 'os arquivos que o Git ignora (um `.env`, `node_modules`) também',
                             'A worktree de integração local da família (nunca enviada, sem PR)',
                             'só é apagada se `origin` é o repositório configurado'),
            ('skills', 'frontlights', 'docs', 'protocol.md'): ('| Espera do merge |', '| Limpeza |', 'Aguardando o merge', 'só `merged_into_base` vale',
                                      '(`parentTicks`: números de linha', '`closeout.py tick-check` confere antes e depois',
                                      '`scripts/cleanup.py plan|verify`', 'nunca com `--force`'),
            ('skills', 'frontlights', 'docs', 'security.md'): ('A limpeza de worktrees e branches (`scripts/cleanup.py`) só lê:',
                                      'o gatilho do ambiente (inscrição na PR ou monitor) não é prova',
                                      'um item que cita outras issues junto nunca é marcado', 'nunca com `--force`',
                                      'cujo tip é a cabeça de uma PR mesclada que chegou à base aprovada',
                                      'a branch remota só entra se `origin` é o repositório configurado e ela ainda aponta para esse mesmo commit',
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
        for phrase in ('the session says in one line that it waits for the merge', 'The notification alone is never taken as proof',
                       '`merged_elsewhere`', 'marcar no corpo de #P a linha L', 'the item that cites two issues is listed as not ticked',
                       'exactly the listed line with `[ ]` turned into `[x]`', '`tick-check` answers `ok` before the write and on the reread',
                       'Only after the closing is written and verified, a second question', 'with no `--force`',
                       '"Não agora" to the closing asks no cleanup question', 'the next `/frontlights` start asks the closeout question',
                       'Reject:', 'it is a rule of the skill', 'Cleanup details (same case)', 'Reject (cleanup):',
                       'removing a worktree without naming the ignored files that go with it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        runbook = flat('evals', 'runbook.md')
        self.assertIn('17. Merge wait, closing, parent tick and cleanup (`evals/merge-wait-and-cleanup.md`)', runbook)
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
