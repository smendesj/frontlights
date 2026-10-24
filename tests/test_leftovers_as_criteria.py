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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext
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
# retro de 23/10/2026 (GeoCloud #1123): todo achado entra como slice nova, nunca caixa P nem "Pendência"
LEFTOVER = '- [ ] S2. A exportação mantém o filtro depois de recarregar (achado da revisão)\n'
LEGACY = ('- [ ] Pendência (achado da revisão): a exportação mantém o filtro depois de recarregar. '
          'Evidência que fecha: o teste da exportação no seam passa\n')


class LadderTests(unittest.TestCase):
    def setUp(self):
        self.followups = section(read(*ISSUES), 'Follow-ups')
        self.ladder = ' '.join(self.followups.split('No finding becomes')[0].split())

    def test_destination_two_is_a_new_slice_inside_the_criteria_section(self):
        two = self.ladder.split('2. ', 1)[1].split(' 3. ')[0]
        for phrase in ('A new slice of the source issue', 'the next box `S<k>` of its acceptance criteria',
                       'for a finding that belongs to that outcome', '"A finding as a new slice"',
                       'done like any other slice'):
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
        self.recipe = ' '.join(section(self.followups, 'A finding as a new slice', '###').split())

    def test_the_recipe_exists_inside_the_follow_ups_section(self):
        self.assertTrue(self.recipe)
        self.assertIn('### A finding as a new slice', self.followups)

    def test_the_finding_is_one_more_slice_never_a_section_of_its_own_nor_another_kind_of_box(self):
        for phrase in ('(a free-test fix, a review\'s baixo) is one more slice', 'never a section of its own',
                       'another kind of box (`P<k>`, `Pendência`, `Correção (do teste livre)`)',
                       'the only one `scripts/closeout.py` counts', 'every tool finds a box by its label `S<k>`',
                       'proposed for closing with it still open'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_a_source_issue_without_the_section_or_already_closed_takes_a_top_level_issue_instead(self):
        for phrase in ('has no such section, or is closed, cannot take destination 2',
                       'use a top-level issue that cites it and say why'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_text_is_the_slice_box_numbered_after_the_last_with_its_origin(self):
        for phrase in ('The box of "Slices as acceptance criteria", numbered after the last',
                       'in the user\'s language', '`- [ ] S<k>. <what must be true> (achado da revisão)`',
                       '`do teste livre`', 'it refuses an item without the next label'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_it_changes_scope_so_it_is_approved_before_any_write(self):
        for phrase in ('Like any update of a published issue, it keeps what is there and is approved before it is written',
                       'the exact text', 'approved in that single question', 'Nothing is written before the answer'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)

    def test_the_write_is_one_command_that_captures_inserts_rereads_and_stops_on_a_divergence(self):
        """Issue 7 do redesenho: a captura com `python -c`, os dois `git diff --no-index` e a contagem pelo
        `closeout.py candidates` viraram `closeout.py append`, coberto em tests/test_closeout_append.py."""
        for phrase in ('`closeout.py append --issue <n> --items <stamped file> [--pitfall <file>]`',
                       'captures the body byte for byte', 'inserts after the last item of the section',
                       'captures again right before writing (someone edited it: it stops)',
                       'rereads and prints `criteria.total` before and after',
                       'restoring the saved body is a write of its own and needs its own approval'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.recipe)
        for gone in ('python -c', 'git diff --no-index', 'closeout.py" candidates'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.recipe)

    def test_the_approved_text_the_answer_and_the_write_are_recorded(self):
        self.assertIn('The handoff keeps the text, the literal answer and the files `append` printed', self.recipe)

    def test_the_criterion_is_ticked_only_with_evidence_and_never_to_get_the_issue_closed(self):
        self.assertIn('Tick it only with its recorded evidence', self.recipe)
        self.assertIn('never to get the issue closed', self.recipe)

    def test_the_pr_cites_the_issue_without_a_closing_keyword_while_a_leftover_is_open(self):
        self.assertIn('the issue is not in the `closes` of `release-plan`, so the PR cites it without a closing keyword '
                      '(`Closes`, `Fixes`, `Resolves`), in its body and in the commit messages', self.recipe)
        self.assertIn('the merge would close the issue with the criterion unticked', self.recipe)
        # issue 7 do redesenho: a frase dizia "While one is open the issue..." em issues.md; o pin de
        # development.md abaixo segue igual
        self.assertIn('While such a criterion is open the issue is not in the `closes` of `release-plan`, so the PR '
                      'cites it without a closing keyword, in its body and in the commit messages',
                      flat('skills', 'frontlights', 'references', 'development.md'))

    def test_a_legacy_section_is_moved_only_on_request_by_a_write_of_its_own_and_the_closeout_only_warns(self):
        for phrase in ('kept in a section of its own', 'only when the user asks for it',
                       'with its own approval', '`pending_outside_criteria`'):
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
                       'every open finding that came up (the watched run, a review the user asked for, the tests that ran, '
                       'the live check and any other verification pass)',
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
        # redesenho, issue 3: a etapa 6 do SKILL.md diz "findings, each with a destination" e aponta para a seção; as
        # fontes dos achados, o portão e o relatório com o destino de cada um vivem em development.md
        stage6 = skilltext.flat(skilltext.stage(6))
        self.assertIn('findings, each with a destination ("Review, checkpoints and renewal")', stage6)
        development = ' '.join(read('skills', 'frontlights', 'references', 'development.md').split())
        for phrase in ('every open finding that came up (the watched run, a review the user asked for, tests that ran',
                       'the gate of the Follow-ups section',
                       'the findings left unfixed with the destination of each',
                       'Before an issue is reported as reviewed or complete, and before the merge into the local main '
                       'and before a PR is opened or updated, every open finding',
                       'becomes a new slice of the source issue', "is dropped by the user's explicit answer",
                       '"cited in the PR" does not pass the gate'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)

    def test_stage_five_sends_unfixed_findings_to_a_tracked_destination(self):
        # redesenho, issue 3: a escada dos achados saiu da etapa 5; a tabela de ponteiros e a regra "The issue is the
        # unit" mandam a "Follow-ups" de references/issues.md
        self.assertIn('| references/issues.md | stage 5; "Follow-ups" for a finding;', skilltext.pointers())
        self.assertIn('(`references/issues.md`, "Follow-ups")', skilltext.rule('The issue is the unit'))
        self.assertIn('the PR body is never a destination',
                      ' '.join(read('skills', 'frontlights', 'references', 'issues.md').split()))

    def test_development_has_the_gate_and_still_ticks_only_with_evidence(self):
        text = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('**Gate on the findings.**', 'a new slice of the source issue first',
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
        for phrase in ('uma slice nova, `- [ ] S<k>. <resultado observável> (achado da revisão)`',
                       'nunca numa seção à parte nem caixa `P<k>`',
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
        self.assertEqual(closeout.scan(body.replace('- [ ] S2.', '- [x] S2.')), ((2, 2), 0))
        self.assertEqual([b['label'] for b in closeout.slice_boxes(body)], ['S1', 'S2'])   # a slice like any other
        # the origin the recipe tells the session to write is the one the template shows
        self.assertIn('(achado da revisão)`', read('skills', 'frontlights', 'templates', 'issue.md'))
        self.assertIn('(achado da revisão)`', read(*ISSUES))

    def test_the_leftover_kept_in_a_section_of_its_own_is_the_one_the_closeout_warns_about(self):
        body = '## Acceptance criteria\n- [x] Behavior\n\n## Pendências conhecidas\n' + LEGACY
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
            ('skills', 'frontlights', 'docs', 'protocol.md'): ('slice nova na issue de origem', 'nunca numa seção à parte',
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
