"""Modelo de PR sucinto (issue 35): `templates/pr.md`, em português, com três seções (Resumo com o menor visual,
Evidência com o antes e o depois, Risco do merge com a porta e o raio de impacto), um arquivo de licença no padrão
de `references/LICENSE-tdd.md` que cita a fonte adaptada, e palavra de fechamento só na linha-modelo `Closes #<n>`
das issues do `closes` do `release-plan` (issue 63, S3).

Seams: o texto de `templates/pr.md`, de `references/LICENSE-pr.md` e de `SKILL.md` (S1); o de
`references/development.md` ("The release"), `SKILL.md` etapa 6, `docs/protocol.md`, `README.md`, `docs/acceptance.md`
e `evals/` (S2: a PR da release usa o modelo, Resumo e Evidência por issue e Risco do merge consolidado). É regra da skill, não barreira:
nenhum script monta o corpo da PR.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'

# Uma palavra de fechamento do GitHub seguida de uma referência de issue fecharia a issue no merge.
# redesenho, issue 3: o título da seção ficou curto em development.md.
RELEASE = chr(10) + '## The release' + chr(10)

CLOSING = re.compile(r'(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b\s*:?\s*(\S+/\S+)?#(\d+|<[^>]+>)')


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
                       'o portão do merge na main local, o teste assistido', 'só aponta registros que já existem',
                       'nunca inventa'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evidence)

    def test_the_evidence_requires_no_suite(self):
        """Decisão de 20/10/2026: o único portão é o teste assistido; a Evidência não pede a suíte inteira da
        release nem a adoção dela, e os testes e a revisão entram só quando rodaram."""
        evidence = flat(section(self.text, 'Evidência'))
        for phrase in ('**Portões:** teste assistido', '**Testes e revisão:** só quando rodaram',
                       'Apague a linha quando nenhum rodou'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evidence)
        for gone in ('**Suíte inteira da release:**', 'adotada da ponta'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, evidence)

    def test_the_merge_risk_names_the_door_and_the_blast_radius(self):
        risk = flat(section(self.text, 'Risco do merge'))
        for phrase in ('**Porta:**', 'mão única', 'mão dupla', '**Raio de impacto:**',
                       'migration', 'dado apagado', 'consolidado'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, risk)

    def test_the_template_closes_only_the_closes_of_the_release_plan_and_says_so(self):
        """Issue 63, S3: a única palavra de fechamento do modelo é a linha-modelo `Closes #<n>`, para as issues do
        `closes` do `release-plan`; as outras a PR cita pelo número, sem palavra."""
        self.assertEqual([m.group(0) for m in CLOSING.finditer(self.text)], ['Closes #<n>'])
        for phrase in ('Cada issue do `closes` do `release-plan`', 'copiada da lista, nunca contada à mão',
                       'só o merge aprovado da PR a fecha', 'a PR cita pelo número, sem palavra de fechamento',
                       '`Closes`', '`Fixes`', '`Resolves`', 'seguem a pergunta de fechamento da etapa 7'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_closes_lines_sit_right_before_the_summary_outside_any_fence(self):
        """Review r1 of issue 63 (R1-4): the `Closes #<n>` line is in the body itself, right before `## Resumo`, a plain
        line outside any code fence, and the guidance says it stays when the guidance is deleted."""
        lines = self.text.splitlines()
        summary = lines.index('## Resumo')
        before = [line for line in lines[:summary] if line.strip()]
        self.assertEqual(before[-1], 'Closes #<n>')
        place = max(i for i, line in enumerate(lines[:summary]) if line == 'Closes #<n>')
        self.assertEqual(sum(1 for line in lines[:place] if line.startswith('```')) % 2, 0, 'inside a code fence')
        self.assertNotIn('```text\nCloses', self.text)
        for phrase in ('logo antes de `## Resumo`', 'uma linha simples por issue, fora de bloco de código',
                       'ficam quando estas orientações são apagadas', 'com `closes` vazio, apague a linha-modelo'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)
        release = flat(read('skills', 'frontlights', 'references', 'development.md').split(RELEASE)[1])
        self.assertIn('right before `## Resumo`, plain lines outside any code fence, the place `templates/pr.md` fixes',
                      release)

    def test_a_finding_never_has_the_body_as_destination(self):
        self.assertIn('o corpo da PR nunca é destino de um achado', self.flat)

    def test_the_closing_pattern_also_catches_a_placeholder(self):
        for sample in ('Closes #12', 'fixes: #<a>', 'Resolves OWNER/REPOSITORY#<b>'):
            with self.subTest(sample=sample):
                self.assertIsNotNone(CLOSING.search(sample))
        self.assertIsNone(CLOSING.search('Issue #<a>: <título>'))

    def test_a_print_is_cited_by_name_and_relative_folder_never_attached(self):
        evidence = flat(section(self.text, 'Evidência'))
        for phrase in ('pelo nome do arquivo e pela pasta `.frontlights/issues/<n>/browser/` da worktree da issue',
                       '(a da issue líder, numa família)', 'uma frase do que ele mostra',
                       'quem revisa o abre no projeto local', 'nunca caminho absoluto', 'imagem anexada ou commitada',
                       'login', 'dado de pessoa'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evidence)

    def test_the_door_rule_is_the_approved_one_and_the_guidance_stands_apart(self):
        risk = section(self.text, 'Risco do merge')
        flat_risk = flat(risk)
        for phrase in ('A porta é de mão única quando há migration ou dado apagado', 'Nos outros casos é de mão dupla'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat_risk)
        self.assertNotIn('outra decisão difícil de desfazer', flat_risk)
        for line in risk.splitlines():
            if '<opcional' in line or '<mão única' in line or '<uma palavra>' in line:
                with self.subTest(line=line):
                    self.assertRegex(line.strip(), r'^(\*\*[^*]+\*\* )?<[^>]+>$')

    def test_the_language_is_the_users_with_the_domain_vocabulary(self):
        self.assertIn('na língua do usuário', self.flat)
        self.assertIn('com o vocabulário do domínio do projeto', self.flat)

    def test_the_template_credits_the_source_and_points_to_its_license(self):
        for phrase in ('`references/LICENSE-pr.md`', 'adaptado', 'show-me', 'as formas da skill `pr`'):
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
                       '`templates/pr.md`', 'adapts', 'The guidance of the **Resumo** section',
                       'follows a local pull request skill whose metadata credits show-me',
                       'no published source of the evidence and merge-danger sections was found'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_it_carries_the_mit_notice_of_the_source_as_the_tdd_license_does(self):
        tdd = read('skills', 'frontlights', 'references', 'LICENSE-tdd.md')
        mit_body = tdd[tdd.index('Permission is hereby granted'):].strip()
        self.assertIn('MIT License', self.text)
        self.assertIn('Copyright (c) 2026 HumanLayer', self.text)
        self.assertNotIn('The three sections (summary, evidence, merge danger) and their', self.flat)
        self.assertIn(flat(mit_body), self.flat)


class SkillListsTheTemplateTests(unittest.TestCase):
    """Issue 35, S1: `SKILL.md` lista o modelo na tabela de ponteiros, com a licença, para a PR da release."""

    def test_the_header_of_the_skill_names_the_template(self):
        # redesenho, issue 3: a lista de referências do cabeçalho virou a tabela `## Pointers`.
        pointers = flat(skilltext.pointers())
        self.assertIn('| templates/pr.md with references/LICENSE-pr.md | the release PR |', pointers)


class ReleaseUsesTheTemplateTests(unittest.TestCase):
    """Issue 35, S2: a PR da release usa o modelo, Resumo e Evidência por issue, Risco do merge consolidado, sem
    palavra de fechamento, e a Evidência aponta os prints do teste assistido e os testes do checkpoint de cada issue."""

    def setUp(self):
        text = read('skills', 'frontlights', 'references', 'development.md')
        release = text.split(RELEASE)[1]
        self.release = flat(re.split(r'(?m)^## ', release)[0])

    def test_the_release_body_follows_the_template_without_a_condition(self):
        self.assertIn('The body follows `templates/pr.md` (the model of the pull request)', self.release)
        self.assertNotIn('`templates/pr.md` when it exists', self.release)

    def test_summary_and_evidence_per_issue_and_one_consolidated_risk(self):
        for phrase in ('**Resumo** and **Evidência** once per issue', 'the smallest visual that makes its point clear',
                       '**Risco do merge** once, consolidated for the whole release',
                       'a one-way door when a migration or deleted data is in it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.release)

    def test_the_evidence_points_to_the_records_of_each_issue(self):
        for phrase in ("the prints of each issue's watched run", 'the tests of its checkpoints',
                       'its gate (the watched run)', 'records that already exist, never invented'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.release)

    def test_prints_door_and_language_say_the_same_as_the_template(self):
        for phrase in ("a print is cited by its file name and its folder in the issue's worktree (the lead issue's for a family)",
                       "never an absolute path, an attached or committed image, a login or a person's data",
                       'a one-way door when a migration or deleted data is in it, a two-way door otherwise',
                       "in the user's language, with the project's domain vocabulary"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.release)
        runbook = flat(read('evals', 'runbook.md'))
        self.assertIn('a one-way door when a migration or deleted data is in it, a two-way door otherwise', runbook)
        self.assertNotIn('a one-way door only with', runbook)
        self.assertIn('prints cited by file name and relative folder, never attached', runbook)

    def test_closes_only_from_the_list_and_no_finding_in_the_body(self):
        for phrase in ('**`Closes #n` only from `closes`.**', 'copied from that list, never counted by hand',
                       'without a closing keyword (`Closes`, `Fixes`, `Resolves` or a variant of them)',
                       'the body of the pull request is never the destination of a finding'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.release)

    def test_stage_six_of_the_skill_says_the_same(self):
        stage6 = flat(skilltext.stage(6))
        # redesenho, issue 3: a etapa 6 aponta a seção pelo nome entre parênteses, sem repetir "development.md".
        self.assertIn('`release landed` ("The release")', stage6)
        release = flat(read('skills', 'frontlights', 'references', 'development.md').split(RELEASE)[1])
        for phrase in ('The body follows `templates/pr.md`', '**Resumo** and **Evidência** once per issue',
                       '**Risco do merge**', '**`Closes #n` only from `closes`.**'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, release)
        self.assertNotIn('`templates/pr.md` when it exists', stage6)

    def test_the_protocol_and_the_readme_say_the_same_in_portuguese(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('a PR única leva o corpo do modelo `templates/pr.md`', protocol)
        self.assertNotIn('`templates/pr.md` quando existir', protocol)
        readme = flat(read('README.md'))
        for phrase in ('abre a PR única pelo modelo `templates/pr.md`', 'Resumo (o menor visual) e Evidência (antes e depois) por issue',
                       'Risco do merge consolidado (porta de mão única ou de mão dupla e raio de impacto)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_the_acceptance_record_and_the_rehearsals_name_the_template(self):
        self.assertIn('S2: a PR da release usa o modelo', flat(read('docs', 'acceptance.md')))
        self.assertIn('29. Pull request template (issue 35)', flat(read('evals', 'runbook.md')))
        self.assertIn('`templates/pr.md`', flat(read('evals', 'merge-wait-and-cleanup.md')))


if __name__ == '__main__':
    unittest.main()
