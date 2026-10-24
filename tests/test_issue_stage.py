"""A etapa 4 escreve a issue, sem entrevista: a spec é o corpo da issue e o documento local de requisitos deixa de existir.

Seams: o texto da skill, da referência da etapa 4, do modelo de issue e da documentação (manifestos de
texto). O ensaio a seco de `evals/runbook.md` (item 3) é o que prova que a regra é seguida.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
RETIRED_WORD = 'P' + 'RD'   # montada em duas partes para este arquivo nunca carregar a palavra aposentada
RETIRED_FILE = RETIRED_WORD.lower() + '.md'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    """O corpo da seção markdown cujo título contém `heading`, até o próximo título do mesmo nível ou acima."""
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return None
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


def positions(text, headings):
    found = []
    for heading in headings:
        index = text.find(heading)
        if index < 0:
            raise AssertionError(f'heading ausente: {heading}')
        found.append(index)
    return found


class IssueStageTests(unittest.TestCase):
    def test_stage_4_writes_the_issue_body_without_a_new_interview(self):
        # redesenho, issue 3: a etapa 4 virou um item da lista numerada; "goes back there instead of being invented",
        # "ideally one" e "approval of its exact revision" vivem em references/issue.md (teste seguinte)
        skill = read('skills', 'frontlights', 'SKILL.md')
        body = flat(skilltext.stage(4))
        self.assertNotEqual(body, '')
        for phrase in ('Read `references/issue.md`', 'The body comes from the discovery log, no new interview',
                       'the one question is the seams', 'field-by-field trace', 'text approved by link and stamp'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertIn('the text (stage 4) and the GitHub write (stage 5) are separate',
                      flat(skilltext.rule('Show before approval')))
        self.assertIn('| references/issue.md | stage 4 |', skilltext.pointers())
        self.assertNotIn('4. **' + RETIRED_WORD, skill)
        self.assertNotIn('## 4. ' + RETIRED_WORD, skill)

    def test_the_stage_4_reference_records_decisions_and_asks_only_the_seams(self):
        text = read('skills', 'frontlights', 'references', 'issue.md')
        reference = flat(text)
        for phrase in ('write, do not interview', 'it goes back to stage 3',
                       'A statement in the body that the user never made is a defect',
                       'The ideal number of seams is one', 'Confirm them with `AskUserQuestion`',
                       'Problema', 'Solução', 'Decisões de implementação', 'Decisões de teste', 'Fora de escopo',
                       'Mark a section that does not apply with the reason', 'Do not write user stories',
                       'without file paths or code snippets in the prose', 'trace table',
                       'Ask approval of the revision by link and stamp', '`.frontlights/issue.md`',
                       'does not authorize code', 'is a new approval of the exact file with its stamp'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, reference)
        self.assertEqual(positions(text, ('## The only question: the seams', '## The body', '## Approval')),
                         sorted(positions(text, ('## The only question: the seams', '## The body', '## Approval'))))

    def test_the_retired_reference_and_template_are_gone(self):
        self.assertFalse((SKILL / 'references' / RETIRED_FILE).exists())
        self.assertFalse((SKILL / 'templates' / RETIRED_FILE).exists())

    def test_the_issue_template_carries_the_spec_before_the_criteria(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        headings = ('## Problema', '## Solução', '## Decisões de implementação', '## Decisões de teste',
                    '## Fora de escopo', '## Critérios de aceitação', '## Camadas da fatia')
        self.assertEqual(positions(template, headings), sorted(positions(template, headings)))
        for retired in ('## Resultado', '## Limites e fora de escopo', '## Abordagem e convenções',
                        '## Seams sob teste', '## Expectativas de teste', '## Riscos e tamanho da sessão'):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, template)
        self.assertIn('## Riscos e dependências', template)
        flat_template = flat(template)
        for phrase in ('alternativas rejeitadas', 'não cita arquivo nem trecho de código',
                       'seams sob teste', 'O que foi recusado'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat_template)

    def test_the_template_is_the_short_one_and_keeps_what_roads_reads(self):
        # redesenho, issue 6 (proposta, seção 3.2): as instruções saíram do corpo para references/issue.md e
        # references/issues.md; ficam "## Propriedade" e as linhas que o RoadS lê (docs/roads-contract.md)
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        flat_template = flat(template)
        for kept in ('## Propriedade', 'Caminhos que a issue pode tocar', '- [ ] S1. <resultado observável',
                     '`- Bloqueada: <o que falta e de quem>`', '- Fluxo: <telas e ações', 'Depends on: none',
                     # retro de 23/10/2026: o achado entra como slice nova, nunca caixa P nem "Pendência"
                     '`- [ ] S<k>. <resultado observável> (achado da revisão)`'):
            with self.subTest(kept=kept):
                self.assertIn(kept, flat_template)
        for gone in ('## Pontos de evidência', '## Propriedade e contenção', 'As seções até "Fora de escopo" são a spec'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, template)
        self.assertLessEqual(len(template.split()), 800)
        reference = flat(read('skills', 'frontlights', 'references', 'issue.md'))
        self.assertIn('with no new question beyond the seams', reference)
        self.assertIn('the instructions stay here, never in the body', reference)

    def test_the_retired_word_is_gone_from_the_skill_the_records_and_the_tests(self):
        files = [SKILL / 'SKILL.md', ROOT / 'README.md', ROOT / 'CLAUDE.md']
        for folder in ('references', 'templates', 'docs'):
            files.extend(sorted((SKILL / folder).glob('*.md')))
        files.extend(sorted((ROOT / 'tests').glob('*.py')))
        for path in files:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                text = path.read_text(encoding='utf-8')
                self.assertNotIn(RETIRED_WORD, text)
                self.assertNotIn(RETIRED_FILE, text)

    def test_grilling_hands_the_decisions_to_the_issue_stage(self):
        grilling = flat(read('skills', 'frontlights', 'references', 'grilling.md'))
        self.assertIn('"Seguir para a issue"', grilling)
        self.assertIn('into stage 4 (the issue) as the input', grilling)

    def test_the_later_stages_read_the_approved_issue_body(self):
        issues = flat(read('skills', 'frontlights', 'references', 'issues.md'))
        self.assertIn('Read the approved issue body (stage 4)', issues)
        self.assertIn('The issue body (stage 4) and the plan (stage 5) carry the complete trace table', issues)
        # redesenho, issue 5: o laço do implementador saiu de development.md para references/tdd.md
        development = flat(read('skills', 'frontlights', 'references', 'tdd.md'))
        self.assertIn("Follow the conventions recorded in the issue's `## Decisões de implementação`", development)
        self.assertIn('`## Decisões de teste` in `templates/issue.md`', development)

    def test_the_protocol_names_the_issue_stage_and_its_record(self):
        protocol = read('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('| Issue |', protocol)
        self.assertIn('sem nova entrevista', protocol)
        self.assertRegex(protocol, r'(?m)^  issue\.md')
        self.assertIn("(the issue's text, issue plan and publication, closeout and summary)",
                      flat(read('skills', 'frontlights', 'references', 'development.md')))


if __name__ == '__main__':
    unittest.main()
