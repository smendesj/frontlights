"""Armadilhas do projeto (issue 65, S5): todo critério que entra depois da aprovação deixa uma linha nas armadilhas
do projeto. O degrau "critério novo da issue de origem" dos Follow-ups grava a linha em `.frontlights/pitfalls.md`
do projeto de destino (fora do versionamento, criado no primeiro uso, só acréscimo), na mesma aprovação do lote; o
formato da linha (data, issue, fato sem dado real, sonda que o pegaria) vive só ali; o reconhecimento do grilling a
lê primeiro e aponta para esse formato; o relatório da etapa 6 conta as linhas por issue, a medida de sucesso.

Seams: o texto de `references/issues.md` (Follow-ups), `references/grilling.md` (Reconnaissance),
`references/development.md` ("Review, checkpoints and renewal"), `docs/protocol.md` ("Registros") e do README. É
regra da skill, não barreira: nenhum script grava nem conta as linhas.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
ISSUES = SKILL / 'references' / 'issues.md'
GRILLING = SKILL / 'references' / 'grilling.md'
DEVELOPMENT = SKILL / 'references' / 'development.md'
PROTOCOL = SKILL / 'docs' / 'protocol.md'
README = ROOT / 'README.md'


def read(path):
    return path.read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    """O corpo da seção cujo título começa por `heading`, até o próximo título do mesmo nível ou acima."""
    match = re.search(r'(?m)^(#+) ' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


class ThePitfallLineIsBornAtTheNewCriterionRungTests(unittest.TestCase):

    def setUp(self):
        self.followups = flat(section(read(ISSUES), 'Follow-ups'))

    def test_the_new_criterion_rung_writes_the_line_in_the_same_batch_approval(self):
        for phrase in ('`.frontlights/pitfalls.md`', 'in the same approval as the batch',
                       'no question of its own'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.followups)
        # o degrau 2 aponta para a receita; a linha vem depois do degrau, antes do degrau 3
        rung2 = self.followups.index('2. A new slice of the source issue')
        rung3 = self.followups.index('3. A top-level issue')
        self.assertLess(rung2, self.followups.index('one line in the project\'s pitfalls'))
        self.assertLess(self.followups.index('one line in the project\'s pitfalls'), rung3)

    def test_the_line_format_lives_in_the_follow_ups(self):
        recipe = flat(section(read(ISSUES), 'A pitfall line'))
        for phrase in ('`- <AAAA-MM-DD> · #<n> · <fato> · sonda: <sonda>`', 'the date', 'the source issue',
                       'without real data', 'no login, name, endpoint or customer data',
                       'the probe that would have caught it', '`references/grilling.md`, "Reconnaissance"',
                       'created on first use', 'append-only', 'Outside version control',
                       'lines per issue', 'the success measure'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, recipe)

    def test_the_line_goes_in_the_stamped_file_and_is_written_after_the_answer(self):
        recipe = flat(section(read(ISSUES), 'A pitfall line'))
        self.assertIn('in the stamped file of the batch', recipe)
        self.assertIn('written only after the answer', recipe)

    def test_the_format_is_defined_in_one_place(self):
        fmt = '· sonda: <sonda>'
        holders = [p for p in SKILL.rglob('*.md') if fmt in read(p)]
        self.assertEqual([ISSUES], holders)


class TheReconnaissanceReadsThePitfallsTests(unittest.TestCase):

    def test_the_reconnaissance_points_to_the_format_and_lists_their_screen_states(self):
        recon = flat(section(read(GRILLING), 'Reconnaissance'))
        self.assertIn('`.frontlights/pitfalls.md`, when it exists (its line format: `references/issues.md`, '
                      '"Follow-ups")', recon)
        self.assertIn('plus the states the project\'s pitfalls list', recon)
        self.assertNotIn('sonda: <sonda>', recon)


class TheReportCountsThePitfallsTests(unittest.TestCase):

    def test_the_stage_6_report_shows_the_pitfall_lines_per_issue(self):
        report = flat(section(read(DEVELOPMENT), 'Review, checkpoints and renewal'))
        self.assertIn('the count of its lines in `.frontlights/pitfalls.md` (criteria that entered after the '
                      'approval', report)
        self.assertLess(report.index('Report each issue\'s state'), report.index('`.frontlights/pitfalls.md`'))


class TheRecordIsListedTests(unittest.TestCase):

    def test_the_protocol_lists_the_pitfalls_file(self):
        records = section(read(PROTOCOL), 'Registros')
        self.assertRegex(records, r'(?m)^  pitfalls\.md ')

    def test_the_readme_mentions_the_line_with_the_leftover(self):
        text = flat(read(README))
        # issue 12 do redesenho: o README virou guia curto; a linha das armadilhas vive em references/issues.md
        self.assertNotIn('deixa uma linha nas armadilhas do projeto', text)


if __name__ == '__main__':
    unittest.main()
