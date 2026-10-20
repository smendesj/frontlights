"""Uma pendência que não é corrigida no PR vira critério de aceitação da issue de origem, e não texto de PR.

Seams: o texto de `SKILL.md`, `references/issues.md` (escada de destinos, receita do critério e portão),
`references/development.md`, `references/closeout.md`, `templates/issue.md`, `templates/handoff.md`,
`docs/`, `README.md` e `evals/`; e o `closeout.scan`/`op_candidates` (ver `test_closeout.py`) para provar que o
modelo de issue e o critério escrito pela receita são contados pelo fechamento. O portão é uma regra da skill
(o Frontlights não a impõe), então ela só se prova pelo texto e pela revisão manual de `evals/leftovers-as-criteria.md`.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import closeout


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def section(text, heading, marks='##'):
    match = re.search(rf'^{marks} {re.escape(heading)}\n(.*?)(?=^#{{1,{len(marks)}}} |\Z)', text, re.M | re.S)
    return match.group(1) if match else ''


ISSUES = ('skills', 'frontlights', 'references', 'issues.md')
LEFTOVER = ('- [ ] Pendência (achado da revisão): a exportação mantém o filtro depois de recarregar. '
            'Evidência que fecha: o teste da exportação no seam passa\n')


class LadderTests(unittest.TestCase):
    def setUp(self):
        self.followups = section(read(*ISSUES), 'Follow-ups')
        self.ladder = ' '.join(self.followups.split('No finding becomes')[0].split())

    def test_destination_two_is_a_new_criterion_inside_the_criteria_section(self):
        two = self.ladder.split('2. ', 1)[1].split(' 3. ')[0]
        for phrase in ('A new acceptance criterion in the source issue', 'checklist item (`- [ ] ...`)',
                       'inside its acceptance-criteria section', 'for a leftover that belongs to that outcome',
                       'treated, completed and ticked with evidence'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, two)
        self.assertNotIn("in the source issue's body", self.ladder)

    def test_the_ladder_names_the_live_check_and_other_verification_passes_as_sources(self):
        self.assertIn('a test run, a live check or another verification pass', self.ladder)

    def test_an_unfixed_finding_always_leaves_with_a_destination_github_tracks(self):
        self.assertIn('Every finding that is not fixed in the PR leaves with a destination GitHub tracks', self.ladder)
        self.assertIn('text in the PR body is never a destination', self.ladder)

    def test_the_batch_shows_and_approves_the_exact_criterion_text(self):
        batch = ' '.join(self.followups.split())
        for phrase in ('the whole text of every new criterion and top-level issue body', 'single `AskUserQuestion`',
                       'with the criterion text exactly as in the stamped file'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, batch)


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.followups = section(read(*ISSUES), 'Follow-ups')
        self.recipe = ' '.join(section(self.followups, 'A leftover as an acceptance criterion', '###').split())

    def test_the_recipe_exists_inside_the_follow_ups_section(self):
        self.assertTrue(self.recipe)
        self.assertIn('### A leftover as an acceptance criterion', self.followups)

    def test_the_leftover_is_one_more_criterion_in_the_counted_section_never_a_section_of_its_own(self):
        for phrase in ('it is one more acceptance criterion', 'never into a section of its own',
                       'the only one `scripts/closeout.py` counts', 'proposed for closing with it still open'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_a_source_issue_without_the_section_or_already_closed_takes_a_top_level_issue_instead(self):
        for phrase in ('has no such section, or is closed, cannot take destination 2',
                       'use a top-level issue that cites it and say why'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_text_is_objective_observable_with_evidence_and_an_origin_prefix(self):
        for phrase in ('One objective, observable item that names the evidence that will close it',
                       'in the user\'s language', 'Pendência (achado da revisão)', 'Evidência que fecha',
                       'do teste ao vivo', 'dos testes', 'da conferência'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_it_changes_scope_so_it_is_approved_before_any_write(self):
        for phrase in ('like any update of a published issue, it keeps what is there and is approved before it is written',
                       'the exact text', 'approved in that single question', 'Nothing is written before the answer'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_capture_is_byte_exact_without_a_shell_redirect_and_with_a_windows_safe_name(self):
        for phrase in ('never with a shell redirect', 'Windows PowerShell re-encodes redirected output',
                       "json.loads(subprocess.run(['gh','issue','view','<n>','--repo','<repo>','--json','body']",
                       "pathlib.Path(r'<file>').write_bytes(b.encode('utf-8'))", 'body-before-<YYYYMMDDTHHMMSSZ>.md',
                       'a colon is not valid in a Windows file name', 'create the folder first when it does not exist',
                       'is the baseline'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_documented_capture_command_writes_the_body_byte_for_byte(self):
        match = re.search(r'python -c "(import json,subprocess,pathlib;.*?)"`', self.recipe)
        self.assertIsNotNone(match, 'the capture command is no longer documented in one piece')
        body = '## Acceptance criteria\r\n- [x] Comportamento \u2713\r\n- [ ] Pend\u00eancia\n\n'
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'body-before.md'
            code = match.group(1).replace('<n>', '12').replace('<repo>', 'OWNER/REPOSITORY').replace('<file>', str(target))
            answer = SimpleNamespace(stdout=json.dumps({'body': body}).encode('utf-8'))
            with mock.patch('subprocess.run', return_value=answer) as run:
                exec(code, {})
            argv = run.call_args.args[0]
            self.assertEqual(argv, ['gh', 'issue', 'view', '12', '--repo', 'OWNER/REPOSITORY', '--json', 'body'])
            written = target.read_bytes()
        self.assertEqual(written, body.encode('utf-8'))      # CRLF kept, accents intact
        self.assertFalse(written.startswith(b'\xef\xbb\xbf'))   # no byte-order mark

    def test_the_write_rereads_before_writing_only_adds_and_never_overwrites_a_changed_body(self):
        for phrase in ('with only the new items inserted right after the last item of the section',
                       'by an exact-replace edit of the copy and never by retyping the whole body',
                       'git diff --no-index --ignore-cr-at-eol --numstat <before> <new>` must show no deleted line',
                       'Capture the body once more right before writing',
                       'git diff --no-index --ignore-cr-at-eol --exit-code <before> <now>',
                       'any difference means someone edited the issue meanwhile, so stop and show it instead of overwriting',
                       'gh issue edit <n> --repo <repo> --body-file <file>', 'never an interpolated string',
                       'GitHub offers no compare-and-swap'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_write_is_verified_by_the_closeout_count_and_by_the_difference(self):
        for phrase in ('python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" candidates --config <config> --root <project> --issues <n>',
                       'Run the same closeout command again', 'criteria.total`, under `candidates` or `excluded`',
                       'grown by the number of items added', 'unchecked_criteria', 'open_children',
                       'with the same flag (`--ignore-cr-at-eol`)',
                       'the only differences are the added lines, inside the section '
                       '(in a legacy migration, also the removed legacy lines)',
                       'restoring the saved body is a write of its own and needs its own approval'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_approved_text_the_answer_and_the_write_are_recorded(self):
        for phrase in ('the approved text', "the user's literal answer with a reference", 'handoff',
                       "authorization's record of GitHub writes"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_criterion_is_ticked_only_with_evidence_and_never_to_get_the_issue_closed(self):
        self.assertIn('Tick it only with evidence', self.recipe)
        self.assertIn('never to get the issue closed', self.recipe)

    def test_the_pr_cites_the_issue_without_a_closing_keyword_while_a_leftover_is_open(self):
        self.assertIn('the PR cites the issue without a closing keyword (`Closes`, `Fixes`, `Resolves`), in its body '
                      'and in the commit messages', self.recipe)
        self.assertIn('the merge would close the issue with the criterion unticked', self.recipe)
        self.assertIn('without a closing keyword, in its body and in the commit messages, while such a criterion is open',
                      flat('skills', 'frontlights', 'references', 'development.md'))

    def test_a_legacy_section_is_moved_only_on_request_by_a_write_of_its_own_and_the_closeout_only_warns(self):
        for phrase in ('already kept in a section of its own', 'only when the user asks for it',
                       'with its own approval', 'removed from the old section',
                       'the only differences are those added lines and those removed ones', '`pending_outside_criteria`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_recipe_uses_no_board_command(self):
        for word in ('item-add', 'item-edit', '--project'):
            with self.subTest(word=word):
                self.assertNotIn(word, self.recipe)


class GateTests(unittest.TestCase):
    def setUp(self):
        followups = section(read(*ISSUES), 'Follow-ups')
        self.gate = ' '.join(section(followups, 'The gate: no open finding without a destination', '###').split())

    def test_every_open_finding_has_a_destination_before_the_report_and_before_the_pr(self):
        for phrase in ('Before an issue is reported as reviewed or complete, and before a PR is opened or updated',
                       'every open finding of the review, the tests, the live check and any other verification pass',
                       'the ones of earlier rounds included', 'fixed (the commit)', 'new criterion',
                       'top-level issue (its number)', 'not a defect, or dropped by the user'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.gate)

    def test_a_finding_without_destination_stops_the_report_and_the_pr(self):
        self.assertIn('A finding with none of these stops the report and the PR', self.gate)

    def test_text_in_the_pr_body_the_chat_or_the_handoff_is_never_a_destination(self):
        self.assertIn('A mention in the PR body, in a comment, in the chat or in the handoff is never a destination', self.gate)
        self.assertIn('only when it also has its destination, which the body then cites', self.gate)

    def test_only_noise_that_is_not_a_defect_may_stay_as_text_and_with_evidence(self):
        for phrase in ('Only noise that is not a defect may stay as text', 'a 404 for a file that is only missing from the local disk',
                       '"não é defeito"', 'the evidence that shows it', 'When in doubt it is a finding'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.gate)

    def test_only_the_user_can_drop_a_finding_and_never_by_default_or_silence(self):
        for phrase in ('Only the user can drop a finding that has no destination', 'explicit answer to the batch question',
                       'record the answer verbatim in the handoff', '"descartado pelo usuário"',
                       'Never offer it as the default and never infer it from silence'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.gate)

    def test_the_handoff_keeps_the_list(self):
        self.assertIn('Achados sem correção e destino de cada um', self.gate)
        handoff = read('skills', 'frontlights', 'templates', 'handoff.md')
        self.assertIn('Achados sem correção e destino de cada um', handoff)
        self.assertIn('"descartado pelo usuário"', handoff)


class SkillAndDevelopmentTests(unittest.TestCase):
    def test_stage_six_makes_the_gate_a_condition_of_the_report_and_of_the_pr(self):
        stage6 = ' '.join(read('skills', 'frontlights', 'SKILL.md').split('## 6.')[1].split('## 7.')[0].split())
        for phrase in ('every open finding with its destination (the gate of the Follow-ups section of '
                       '`references/issues.md`)', 'the findings left unfixed with the destination of each'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage6)
        development = ' '.join(read('skills', 'frontlights', 'references', 'development.md').split())
        for phrase in ('Before an issue is reported as reviewed or complete, and before the merge into the local main '
                       'and before a PR is opened or updated, every open finding',
                       'an acceptance criterion of the source issue', "is dropped by the user's explicit answer",
                       '"cited in the PR" does not pass the gate'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)

    def test_stage_five_sends_unfixed_findings_to_a_tracked_destination(self):
        stage5 = ' '.join(read('skills', 'frontlights', 'SKILL.md').split('## 5.')[1].split('## 6.')[0].split())
        self.assertIn('the Follow-ups ladder of the same file for findings', stage5)
        self.assertIn('the PR body is never a destination',
                      ' '.join(read('skills', 'frontlights', 'references', 'issues.md').split()))

    def test_development_has_the_gate_and_still_ticks_only_with_evidence(self):
        text = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('**Gate on the findings.**', 'a new acceptance criterion in the source issue',
                       'is never a destination, so "cited in the PR" does not pass the gate',
                       'any other verification pass', "or is dropped by the user's explicit answer",
                       'tick an acceptance criterion in the issue body only with evidence for it',
                       'a criterion born from a finding is ticked the same way',
                       'the findings left unfixed with the destination of each'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('checklist in the source issue', text)


class TemplateAndCloseoutTests(unittest.TestCase):
    def test_the_issue_template_tells_where_the_leftovers_go_without_adding_a_criterion(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        note = ' '.join(section(template, 'Critérios de aceitação').split())
        for phrase in ('Pendência (achado da revisão)', 'Evidência que fecha', 'nunca numa seção à parte',
                       'só esta seção conta para fechar a issue', 'tratada, concluída e marcada com evidência'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, note)
        self.assertEqual(closeout.scan(template), ((0, 1), 0))   # the explanation is not a criterion

    def test_a_leftover_written_as_the_recipe_says_is_counted_and_blocks_the_closeout_until_ticked(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        box = '- [ ] S1. <resultado observável de ponta a ponta desta slice>\n'
        self.assertIn(box, template)   # the slice box of the template is the one a session ticks
        body = template.replace(box, '- [x] S1. Behavior\n' + LEFTOVER)
        self.assertEqual(closeout.scan(body), ((1, 2), 0))
        self.assertEqual(closeout.scan(body.replace('- [ ] Pendência', '- [x] Pendência')), ((2, 2), 0))
        # the prefix the recipe tells the session to write is the one the template shows
        self.assertIn('Pendência (achado da revisão)', read('skills', 'frontlights', 'templates', 'issue.md'))
        self.assertIn('Pendência (achado da revisão)', read(*ISSUES))

    def test_the_leftover_kept_in_a_section_of_its_own_is_the_one_the_closeout_warns_about(self):
        body = '## Acceptance criteria\n- [x] Behavior\n\n## Pendências conhecidas\n' + LEFTOVER
        self.assertEqual(closeout.scan(body), ((1, 1), 1))

    def test_the_closeout_reference_shows_the_warning_and_recommends_choosing(self):
        text = flat('skills', 'frontlights', 'references', 'closeout.md')
        for phrase in ('`pending_outside_criteria`', '`pendingOutside`', '"fecha com N pendências fora dos critérios"',
                       'an open one keeps its issue out of this list as `unchecked_criteria`',
                       'recommend "Escolher quais" instead when some candidate has `open_pr` or `pendingOutside` above zero',
                       'it is the user\'s call whether to close with them open',
                       'Say in the question that moving them into the criteria is available',
                       'done only when the user asks for it, with its own approval'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class DocsAndEvalsTests(unittest.TestCase):
    def test_the_documents_carry_the_rule(self):
        cases = {
            ('README.md',): ('critério `- [ ] Pendência (achado da revisão): ...`', 'seção de critérios de aceitação da issue de origem',
                             '"citado no corpo do PR" nunca é destino', 'Achados sem correção e destino de cada um',
                             'fecha com N pendências fora dos critérios'),
            ('skills', 'frontlights', 'docs', 'protocol.md'): ('critério de aceitação novo na issue de origem', 'nunca numa seção à parte',
                                      '"citado no corpo do PR" nunca é destino', 'Achados sem correção e destino de cada um'),
            ('skills', 'frontlights', 'docs', 'security.md'): ('O Frontlights não impede a sessão de encerrar com o achado só no texto do PR',
                                      '`pending_outside_criteria`', '`pendingOutside`'),
        }
        for name, phrases in cases.items():
            text = flat(*name)
            for phrase in phrases:
                with self.subTest(doc=name[-1], phrase=phrase):
                    self.assertIn(phrase, text)

    def test_the_old_checklist_wording_is_gone_from_the_documents(self):
        for name in (('README.md',), ('skills', 'frontlights', 'docs', 'protocol.md')):
            with self.subTest(doc=name[-1]):
                self.assertNotIn('item de checklist no corpo da issue de origem', flat(*name))
                self.assertNotIn('checklist na issue de origem', flat(*name))

    def test_the_eval_covers_the_case_and_the_runbook_and_the_record_point_to_it(self):
        text = flat('evals', 'leftovers-as-criteria.md')
        for phrase in ('"Cited in the PR body" is refused as a destination', 'the exact text of each',
                       'nothing is written before the answer', 'the difference against the saved copy is only the added lines',
                       'the issue as `unchecked_criteria`', 'the closeout lists it as a candidate with `pending_outside_criteria`',
                       'Legacy case', 'Reject:', 'it is a rule of the skill'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn('evals/leftovers-as-criteria.md', flat('evals', 'runbook.md'))
        self.assertIn('16. Leftovers as criteria', flat('evals', 'runbook.md'))
        self.assertIn('| 16. Pendências como critério de aceitação | Pendente |', flat('docs', 'acceptance.md'))

    def test_the_new_files_carry_no_machine_path_and_no_real_name(self):
        for path in (ROOT / 'evals' / 'leftovers-as-criteria.md', ROOT / 'skills' / 'frontlights' / 'templates' / 'issue.md',
                     ROOT / 'skills' / 'frontlights' / 'templates' / 'handoff.md', SKILL / 'references' / 'issues.md'):
            text = path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertNotRegex(text, r'\b[A-Za-z]:[\\/]|/(home|Users)/[A-Za-z]')
                self.assertNotRegex(text, r'github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+')


if __name__ == '__main__':
    unittest.main()
