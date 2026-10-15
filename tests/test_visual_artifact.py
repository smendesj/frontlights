"""Artefato visual no grilling e na lista de CAs (issue 33): cada entrevista tem um artefato, uma página privada
publicada pela ferramenta de artefatos do host, criada na primeira rodada que toca tela, fluxo ou camadas e
atualizada na mesma URL, com uma seção por pergunta (o antes montado do template real, o depois por abordagem,
sem tela o diagrama de fluxo e de camadas), só dados fictícios e a URL no log de descoberta; o quiz das CAs cita,
por CA, a seção do artefato com o que ela entrega.

Seams: o texto de `SKILL.md` (etapas 3 e 5), `references/grilling.md`, `references/issues.md`,
`templates/discovery.md`, `docs/protocol.md`, `docs/security.md`, `README.md`, `docs/acceptance.md` e
`evals/runbook.md`. É regra da skill, não barreira: nenhum script monta o artefato.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section_containing(text, heading):
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


class ArtifactInTheGrillingTests(unittest.TestCase):
    """Issue 33, S1: um artefato por grilling, mesma URL, antes do template real, só dados fictícios."""

    def test_grilling_has_one_artifact_on_one_url(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        artifact = flat(section_containing(grilling, 'The artifact'))
        self.assertNotEqual(artifact, '')
        for phrase in ('one **artifact** per grilling',
                       'created at the first round that touches a screen, a flow or the layers',
                       'updated at every later round **on the same URL**', 'never one page per round',
                       'one section per question that touches a screen, a flow or the layers',
                       'built from the real template of the component', 'never a free sketch',
                       'the **after** for each approach', 'a diagram of the flow and of the layers, before and after',
                       'only fictitious data', 'no real record, secret, endpoint, person or client',
                       'The URL is recorded in the discovery log', 'the log line reads "não se aplica"',
                       'numbered in the order of those questions and titled by the question',
                       '"artefato" is the page, "preview" is the field',
                       'Never a real screenshot', 'never an inline widget',
                       'say so in one line, go on in text', 'artefato indisponível'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertLess(grilling.index('## The artifact'), grilling.index('## 1. Problem round'))

    def test_every_round_that_touches_a_screen_cites_the_artifact(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        problem = flat(grilling.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        self.assertIn('publish the artifact with the **before**', problem)
        self.assertIn('the confirmation question cites its section', problem)
        solution = flat(grilling.split('## 3. Solution round')[1].split('## 4. Decision tree')[0])
        self.assertIn('the section of the artifact that shows the **after** of this approach', solution)
        tree = flat(grilling.split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0])
        self.assertIn('cites the section of the artifact that shows it', tree)
        recording = flat(grilling.split('## Recording')[1])
        self.assertIn('the URL of the artifact', recording)

    def test_the_skill_names_the_artifact_in_stage_3(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage3 = flat(skill.split('## 3.')[1].split('## 4.')[0])
        for phrase in ('one artifact per grilling', 'the same URL', 'built from the real template',
                       'only fictitious data', 'the URL in the discovery log', '"The artifact"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage3)

    def test_the_discovery_template_has_the_url_field(self):
        template = read('skills', 'frontlights', 'templates', 'discovery.md')
        self.assertIn('- Artifact URL (one per grilling, the same URL every round', template)
        self.assertIn('"não se aplica" when no round touches a screen, a flow or the layers', template)
        self.assertLess(template.index('- Learning mode changes'), template.index('- Artifact URL'))
        self.assertLess(template.index('- Artifact URL'), template.index('## Project conventions'))

    def test_the_docs_say_the_page_carries_only_fictitious_data(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('publicar o artefato (uma página por grilling, na mesma URL, só com dados fictícios)', protocol)
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('**Artefato do grilling.**', 'só dados fictícios',
                       'nenhum dado real, segredo, endpoint, nome de pessoa, cliente ou organização entra na página',
                       'fica fora da máquina', 'nunca do artefato'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        readme = flat(read('README.md'))
        self.assertIn('**Artefato visual.**', readme)
        self.assertIn('um artefato por entrevista, na mesma URL', readme)


class ArtifactInTheSliceQuizTests(unittest.TestCase):
    """Issue 33, S2: a lista numerada das CAs cita, por CA, a seção do artefato com o que ela entrega; ensaio a seco."""

    def test_the_numbered_list_cites_the_artifact_section_of_each_slice(self):
        issues = read('skills', 'frontlights', 'references', 'issues.md')
        quiz = flat(section_containing(issues, 'Slices as acceptance criteria'))
        for phrase in ('for each slice, the section of the artifact that shows what it delivers',
                       'the drawing of each slice', 'the same URL as the grilling',
                       'the quiz itself stays the same', 'a slice whose drawing shows nothing demonstrable is horizontal'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, quiz)
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage5 = flat(skill.split('## 5.')[1].split('## 6.')[0])
        self.assertIn('for each slice, the section of the artifact with what it delivers', stage5)
        self.assertIn('updated on the same URL as the grilling', stage5)
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('cada slice com a seção do artefato que mostra o que ela entrega', protocol)
        readme = flat(read('README.md'))
        self.assertIn('cada CA com a seção do artefato que mostra o que ela entrega', readme)

    def test_the_dry_run_and_the_runbook_cover_the_artifact(self):
        case = read('evals', 'grilling-artifact.md')
        self.assertTrue(case.startswith('# Visual artifact in the grilling and in the list of slices (manual; no model score claimed)'))
        for phrase in ('Setup:', 'Expected', 'Reject:', 'on the same URL as the grilling', 'fictitious',
                       'artefato indisponível', 'não se aplica',
                       'one section per slice', 'never one page per round'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, case)
        runbook = read('evals', 'runbook.md')
        item = '28. Visual artifact in the grilling and in the list of slices (`evals/grilling-artifact.md`, issue 33).'
        self.assertIn(item, runbook)
        self.assertLess(runbook.index('27. Local main as homologation'), runbook.index(item))
        self.assertLess(runbook.index(item), runbook.index('Only after all required checks pass'))
        acceptance = read('docs', 'acceptance.md')
        self.assertIn('| 28. Artefato visual no grilling e na lista de CAs (issue 33) |', acceptance)


if __name__ == '__main__':
    unittest.main()
