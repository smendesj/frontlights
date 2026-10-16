"""Modelo de PR sucinto (issue 35): `templates/pr.md`, em português, com três seções (Resumo com o menor visual,
Evidência com o antes e o depois, Risco do merge com a porta e o raio de impacto), um arquivo de licença no padrão
de `references/LICENSE-tdd.md` que cita a fonte adaptada, e nenhuma palavra de fechamento.

Seams: o texto de `templates/pr.md`, de `references/LICENSE-pr.md` e de `SKILL.md`. É regra da skill, não barreira:
nenhum script monta o corpo da PR.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'

# Uma palavra de fechamento do GitHub seguida de uma referência de issue fecharia a issue no merge.
CLOSING = re.compile(r'(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b\s*:?\s*(\S+/\S+)?#\d+')


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(r'(?m)^## ' + re.escape(heading) + r'\s*$', text)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'(?m)^## ', rest)
    return rest[:following.start()] if following else rest


class PullRequestTemplateTests(unittest.TestCase):
    """Issue 35, S1: o modelo existe, em português, com as três seções na ordem e as orientações de cada uma."""

    def setUp(self):
        self.path = SKILL / 'templates' / 'pr.md'
        self.text = self.path.read_text(encoding='utf-8') if self.path.is_file() else ''
        self.flat = flat(self.text)

    def test_the_template_exists_with_the_three_sections_in_order(self):
        self.assertTrue(self.path.is_file(), 'templates/pr.md não existe')
        headings = ('## Resumo', '## Evidência', '## Risco do merge')
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertRegex(self.text, r'(?m)^' + re.escape(heading) + r'\s*$')
        positions = [self.text.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_the_summary_asks_for_the_smallest_visual_per_issue(self):
        summary = flat(section(self.text, 'Resumo'))
        for phrase in ('o menor visual que deixa o ponto claro', 'pseudocódigo', 'árvore de chamadas',
                       'árvore de arquivos', 'Mermaid', '`diff`', 'por issue'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, summary)

    def test_the_evidence_shows_before_and_after_from_records_that_already_exist(self):
        evidence = flat(section(self.text, 'Evidência'))
        for phrase in ('**Antes:**', '**Depois:**', 'prints do teste assistido',
                       'o teste que falhava e passou a passar', 'checkpoint', 'revisão independente',
                       'os três portões', 'só aponta registros que já existem', 'nunca inventa'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evidence)

    def test_the_merge_risk_names_the_door_and_the_blast_radius(self):
        risk = flat(section(self.text, 'Risco do merge'))
        for phrase in ('**Porta:**', 'mão única', 'mão dupla', '**Raio de impacto:**',
                       'migration', 'dado apagado', 'consolidado'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, risk)

    def test_the_template_never_carries_a_closing_keyword_and_says_so(self):
        self.assertIsNone(CLOSING.search(self.text), 'o modelo traz uma palavra de fechamento com referência')
        for phrase in ('sem palavra de fechamento', '`Closes`', '`Fixes`', '`Resolves`', 'cita a issue pelo número'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_a_finding_never_has_the_body_as_destination(self):
        self.assertIn('o corpo da PR nunca é destino de um achado', self.flat)

    def test_the_template_credits_the_source_and_points_to_its_license(self):
        for phrase in ('`references/LICENSE-pr.md`', 'adaptado'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)


class LicenseTests(unittest.TestCase):
    """Issue 35, S1: o arquivo de licença segue o padrão de `references/LICENSE-tdd.md` e cita a fonte."""

    def setUp(self):
        self.path = SKILL / 'references' / 'LICENSE-pr.md'
        self.text = self.path.read_text(encoding='utf-8') if self.path.is_file() else ''
        self.flat = flat(self.text)

    def test_the_license_file_exists_beside_the_tdd_one(self):
        self.assertTrue(self.path.is_file(), 'references/LICENSE-pr.md não existe')
        self.assertTrue((SKILL / 'references' / 'LICENSE-tdd.md').is_file())

    def test_it_names_the_source_and_what_was_adapted(self):
        for phrase in ('https://github.com/humanlayer/skills', 'plugins/show-me/skills/show-me/SKILL.md',
                       '`templates/pr.md`', 'adapts'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_it_carries_the_mit_notice_of_the_source_as_the_tdd_license_does(self):
        tdd = read('skills', 'frontlights', 'references', 'LICENSE-tdd.md')
        mit_body = tdd[tdd.index('Permission is hereby granted'):].strip()
        self.assertIn('MIT License', self.text)
        self.assertIn('Copyright (c) 2026 HumanLayer', self.text)
        self.assertIn(flat(mit_body), self.flat)


class SkillListsTheTemplateTests(unittest.TestCase):
    """Issue 35, S1: `SKILL.md` lista o modelo junto das referências, antes das regras de toda etapa."""

    def test_the_header_of_the_skill_names_the_template(self):
        header = flat(read('skills', 'frontlights', 'SKILL.md').split('## Rules that hold in every stage')[0])
        self.assertIn('`templates/pr.md`', header)
        self.assertIn("the model of the release's pull request", header)


if __name__ == '__main__':
    unittest.main()
