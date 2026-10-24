"""Critério de parada da revisão e padrão do revisor (melhoria direta, branch `sergio/melhoria-revisao`).

O revisor independente julga pelo padrão de `references/review.md` (o que é achado, em que gravidade, o que é só
estilo e nunca vira achado, as rodadas e o relato), que só o brief do revisor cita; a revisão termina na primeira
rodada com 0 sérios e 0 médios, com no máximo três rodadas, e os baixos vão ao lote de achados como critério novo
da issue de origem.

Seams: o texto de `references/review.md`, de `references/development.md` ("Review, checkpoints and renewal"), da
`SKILL.md`, de `templates/handoff.md`, de `docs/protocol.md`, do README, de `docs/acceptance.md` e de
`evals/runbook.md`. É regra da skill, não barreira: nenhum script conta as rodadas nem classifica achados.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
REVIEW = SKILL / 'references' / 'review.md'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading, level='##'):
    match = re.search(r'(?m)^' + level + ' ' + re.escape(heading) + r'\s*$', text)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,' + str(len(level)) + '} ', rest)
    return rest[:following.start()] if following else rest


class ReviewerStandardTests(unittest.TestCase):
    """O arquivo do revisor: achado, gravidades, estilo, rodadas e relato."""

    def setUp(self):
        self.text = REVIEW.read_text(encoding='utf-8') if REVIEW.is_file() else ''

    def test_the_file_exists_with_its_sections_in_order(self):
        self.assertTrue(REVIEW.is_file(), 'references/review.md não existe')
        headings = ('## What a finding is', '## Severity', '## Style', '## Rounds', '## The report')
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertRegex(self.text, r'(?m)^' + re.escape(heading) + r'\s*$')
        positions = [self.text.find(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_a_finding_is_a_defect_with_a_failure_scenario(self):
        finding = flat(section(self.text, 'What a finding is'))
        for phrase in ('A finding is a defect', '**failure scenario**',
                       'What has no failure scenario is not a finding'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, finding)

    def test_three_severities_with_their_examples(self):
        severity = flat(section(self.text, 'Severity'))
        for phrase in ('**Sério:**', '**Médio:**', '**Baixo:**', 'data lost or corrupted',
                       'a secret or personal data exposed', 'a regression of existing behaviour', 'tautological',
                       'a small blast radius', 'take the higher one'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, severity)
        self.assertLess(severity.find('**Sério:**'), severity.find('**Médio:**'))
        self.assertLess(severity.find('**Médio:**'), severity.find('**Baixo:**'))

    def test_style_never_becomes_a_finding(self):
        style = flat(section(self.text, 'Style'))
        for phrase in ('It stays out of the report, at every severity', 'line width', 'blank lines',
                       'paragraph breaks', 'punctuation and parentheses', 'a synonym',
                       'another way of writing code that behaves the same'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, style)
        # Um verificador que o projeto roda e falha é defeito, não estilo.
        self.assertIn('A formatter, linter or test the project runs owns its own rules', style)

    def test_later_rounds_review_the_delta_and_the_earlier_findings(self):
        rounds = flat(section(self.text, 'Rounds'))
        for phrase in ('A round is one dispatch of the reviewer on the current tip',
                       '`git diff <base>...HEAD`', '`git diff <previous tip>..HEAD`',
                       'each finding of the earlier rounds', 'comes from that delta or from what it touches'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rounds)

    def test_the_delta_leaves_out_what_the_base_brought(self):
        # 1ª revisão, médio 1: depois do `git merge main`, o `..HEAD` cru traria o código das outras issues.
        rounds = flat(section(self.text, 'Rounds'))
        for phrase in ('When the base was brought into the branch between the rounds',
                       "the delta is the issue's own change, not what the base brought",
                       '`git range-diff <previous base>..<previous tip> <base>..HEAD`',
                       '`git show --remerge-diff <merge commit>`',
                       'the code the base brought belongs to the issues that delivered it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rounds)

    def test_the_report_has_the_counts_and_one_block_per_finding(self):
        report = flat(section(self.text, 'The report'))
        for phrase in ('`sérios/médios/baixos: s/m/b`', 'the most severe first', '**Gravidade**', '**Onde:**',
                       '**O que está errado:**', '**Cenário de falha:**', '**Evidência:**',
                       '**Correção sugerida:**', '`corrigido`', '`aberto`',
                       'the coordinating session reads the counts'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, report)
        self.assertIn("Write the report in the user's language", flat(self.text))


class StopCriterionTests(unittest.TestCase):
    """O critério de parada e o brief do revisor, em `development.md`."""

    def setUp(self):
        self.review = flat(section(read('skills', 'frontlights', 'references', 'development.md'),
                                   'Review, checkpoints and renewal'))

    def test_the_reviewers_brief_names_the_standard_and_the_implementers_leaves_it_out(self):
        # issue 11 do redesenho: o brief do revisor vive em "Review (on request)", um por eixo.
        for phrase in ('### Review (on request)', 'each brief names `review.md`, the issue, its base and, after round '
                       'one, the previous tip and findings', "and the implementer's brief never names it"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.review)

    def test_the_review_is_done_at_zero_serious_and_zero_medium(self):
        # redesenho, issue 3: o negrito "When the review is done" virou subtítulo `###` de development.md.
        for phrase in ('### When the review is done', 'done at the first round that reports 0 sérios and 0 médios',
                       'a new slice of the source issue', '"Corrigir os baixos agora"',
                       'There is no limit of rounds to keep', '"Mais uma rodada"', '"Dar destino pela escada"',
                       'a sério or médio without a destination keeps the issue out of the local main by the gate on '
                       'the findings',
                       'The handoff records each round: its HEAD and its counts'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.review)

    def test_the_limit_of_rounds_is_gone(self):
        # Decisão de 20/10/2026: a revisão roda só a pedido e não tem mais limite de rodadas, nem a exceção da
        # rodada que só reconfere a base.
        stage6 = flat(skilltext.stage(6))
        for text in (self.review, stage6):
            for gone in ('Three rounds per issue is the limit', 'three rounds at most', 'stays outside the limit'):
                with self.subTest(gone=gone):
                    self.assertNotIn(gone, text)

    def test_the_protocol_and_the_readme_point_to_the_stop_criterion(self):
        # Rodada 5, médio 1, depois da fonte única: a exceção da reconferência vive em development.md, e o
        # protocolo e o README apontam para "When the review is done" em vez de copiar o critério.
        for name in (('skills', 'frontlights', 'docs', 'protocol.md'),):  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
            text = flat(read(*name))
            with self.subTest(file='/'.join(name)):
                self.assertIn('"When the review is done"', text)
                self.assertNotIn('"Mais uma rodada"', text)

    def test_the_ladder_names_the_default_of_the_baixos(self):
        # 1ª revisão, médio 2: a escada manda corrigir na branch o que cabe no escopo; os baixos de uma revisão
        # fechada em 0 sérios e 0 médios têm o critério novo como proposta padrão, e a correção vira opção do lote.
        self.assertIn('Each axis stops by "When the review is done"; findings take the destination ladder '
                      '(`issues.md`, "Follow-ups"), a new slice of the source issue first.', self.review)
        follow_ups = flat(section(read('skills', 'frontlights', 'references', 'issues.md'), 'Follow-ups'))
        for phrase in ('The baixos left by a review that ends at 0 sérios and 0 médios',
                       'take destination 2 as the proposed default, with destination 1 offered in the same batch as '
                       '"Corrigir os baixos agora"', 'every other finding takes the first destination that fits'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, follow_ups)

    def test_the_two_blocks_sit_before_the_gate_on_the_findings(self):
        brief = self.review.find('### Review (on request)')
        done = self.review.find('### When the review is done')
        gate = self.review.find('**Gate on the findings.**')
        self.assertTrue(0 <= brief < done < gate, (brief, done, gate))

class TwoAxesTests(unittest.TestCase):
    """Issue 11 do redesenho, S3: revisão em dois eixos (Spec e Standards), só a pedido, nunca portão."""

    def setUp(self):
        self.text = flat(section(REVIEW.read_text(encoding='utf-8'), 'Two axes'))
        self.development = read('skills', 'frontlights', 'references', 'development.md')
        self.on_request = section(self.development, 'Review (on request)', '###')

    def test_two_reviewers_one_per_axis_with_the_same_standard(self):
        for phrase in ("Two reviewers, one per axis, each with this file's finding, severity, rounds and report",
                       '**Spec:** the issue body (criteria, decisions, out of scope) against the diff',
                       'each finding cites the criterion or decision it breaks',
                       "**Standards:** the conventions of the issue's `## Decisões de implementação`",
                       'The coordinator shows the two reports side by side, never reordered across axes; each axis '
                       'keeps its own counts.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_the_smells_are_twelve_lines_of_judgment(self):
        raw = section(REVIEW.read_text(encoding='utf-8'), 'Two axes')
        self.assertEqual(re.findall(r'(?m)^(\d+)\. ', raw), [str(n) for n in range(1, 13)])
        self.assertIn('The smells are judgment, never a checklist: one is a finding only with a failure scenario.',
                      self.text)

    def test_development_says_it_in_about_110_words_with_the_stop_criterion(self):
        self.assertLessEqual(len(self.on_request.split()), 150)
        body = flat(self.on_request)
        for phrase in ('The independent review runs only when the user asks for one: it is not dispatched by default '
                       'and is not a gate of the merge into the local main nor of the release.',
                       'Two reviewers go out in one message, one per axis (`references/review.md`, "Two axes")',
                       'Each axis stops by "When the review is done"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        done = flat(section(self.development, 'When the review is done', '###'))
        self.assertIn('done at the first round that reports 0 sérios and 0 médios', done)

class RetroTests(unittest.TestCase):
    """Issue 11 do redesenho, S4: retro oferecida uma vez após o merge da release, recusável, nunca hook."""

    def setUp(self):
        self.text = flat(read('skills', 'frontlights', 'references', 'retro.md'))

    def test_offered_once_after_the_release_and_refusable(self):
        self.assertLessEqual(len(self.text.split()), 440)
        self.assertIn('After the merge of a release, offer the retro once (`references/retro.md`; "Agora não" is an '
                      'option).', flat(skilltext.stage(7)))
        self.assertIn("| references/retro.md | the user accepts the retro offered after a release's merge; on request |",
                      flat(skilltext.pointers()))
        for phrase in ('Once per release, after `release landed` and the closeout: "Fazer a retro desta release?", '
                       'options "Sim, fazer a retro" and "Agora não".',
                       'The retro is never a gate: nothing waits on its answer.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_it_reads_the_records_never_the_transcript(self):
        self.assertIn('The records of each issue of the release, never the transcript', self.text)
        self.assertIn('A fact the records do not hold is not a finding.', self.text)

    def test_each_finding_has_one_of_four_destinations_and_never_a_hook(self):
        for phrase in ('Each one gets exactly one destination', '**A script check:**', '**A pitfall line:**',
                       '**A rule in its single home:**', '**A no-op to delete:**',
                       'Never a hook that blocks: a guard is a test or a warning.',
                       'in the format of `references/issues.md`, "A pitfall line"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_the_batch_is_stamped_and_the_skill_is_never_edited_from_a_consumer(self):
        for phrase in ('It is approved by link and stamp as one batch.',
                       'each other finding becomes one issue in the Frontlights repository',
                       'The retro never edits the skill while it runs in a consumer project'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)


class OnlyTheReviewerReadsItTests(unittest.TestCase):
    """Dentro da skill, o padrão do revisor só é citado onde o coordenador monta o brief e nos registros."""

    def test_the_implementers_material_never_names_the_standard(self):
        for name in ('tdd.md', 'worker.md', 'browser-testing.md', 'issue.md', 'issues.md', 'grilling.md'):
            with self.subTest(reference=name):
                self.assertNotIn('review.md', read('skills', 'frontlights', 'references', name))

    def test_only_the_skill_development_and_the_protocol_name_it(self):
        naming = sorted(path.relative_to(SKILL).as_posix() for path in SKILL.rglob('*.md')
                        if path != REVIEW and 'references/review.md' in path.read_text(encoding='utf-8'))
        self.assertTrue(set(naming) <= {'SKILL.md', 'references/development.md', 'docs/protocol.md'}, naming)
        self.assertIn('SKILL.md', naming)
        self.assertIn('references/development.md', naming)

    def test_skill_md_lists_the_standard_and_the_stop_criterion_in_stage_6(self):
        # redesenho, issue 3: a lista do cabeçalho virou a tabela `## Pointers`, e a etapa 6 aponta a seção dos
        # achados; "a revisão só a pedido, julgada por review.md" vive em development.md.
        self.assertIn("| references/review.md | only in a requested review's brief |", flat(skilltext.pointers()))
        self.assertIn('findings, each with a destination ("Review, checkpoints and renewal")', flat(skilltext.stage(6)))
        development = read('skills', 'frontlights', 'references', 'development.md')
        review = flat(section(development, 'Review, checkpoints and renewal'))
        for phrase in ('The independent review runs only when the user asks for one',
                       '(`references/review.md`, "Two axes")', '### When the review is done'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, review)


class DocumentationTests(unittest.TestCase):
    """Protocolo, README, modelo de handoff, aceitação e runbook trazem a regra."""

    def test_the_protocol_says_it_in_portuguese(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        for phrase in ('O revisor julga pelo padrão de `references/review.md`', 'que só o brief do revisor cita',
                       'A revisão independente roda só a pedido do usuário.',
                       'a pergunta depois de uma rodada com sério ou médio e o destino dos baixos estão numa fonte só',
                       '`references/development.md`, "When the review is done"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, protocol)

    def test_the_readme_says_it_in_portuguese(self):
        readme = flat(read('README.md'))
        # issue 12 do redesenho: o README virou guia curto; a revisão, só a pedido, vive em references/review.md
        self.assertNotIn('"Mais uma rodada"', readme)

    def test_the_handoff_records_each_round(self):
        handoff = flat(read('skills', 'frontlights', 'templates', 'handoff.md'))
        self.assertIn('cada rodada com o HEAD e `sérios/médios/baixos`', handoff)  # redesenho, issue 9: em português

    def test_the_acceptance_and_the_runbook_carry_the_item(self):
        acceptance = flat(read('docs', 'acceptance.md'))
        self.assertRegex(acceptance, r'\| \d+\. Critério de parada da revisão e padrão do revisor \| Pendente \|')
        self.assertIn('`tests/test_review_criteria.py`', acceptance)
        self.assertRegex(flat(read('evals', 'runbook.md')), r'\d+\. Review stop criterion\. ')


if __name__ == '__main__':
    unittest.main()
