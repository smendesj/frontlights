"""Artefato visual no grilling e na lista de CAs (issues 33 e 61): cada entrevista tem um artefato, uma página
privada publicada pela ferramenta de artefatos do host, criada na rodada do problema com o antes (montado do template
real; sem tela, o diagrama do fluxo, das camadas ou da regra atual) e atualizada na mesma URL com uma seção por
pergunta de decisão, cada uma no modelo `templates/grilling-section.html`, acrescentada por edição pequena da fonte
local; trecho de código real com segredo mascarado entra, dado real nunca; a URL e o caminho da fonte no log de
descoberta; o quiz das CAs cita, por CA, a seção do artefato com o que ela entrega. Não há mais "não se aplica":
só "artefato indisponível", sem a ferramenta.

Seams: o texto de `SKILL.md` (etapas 3 e 5), `references/grilling.md`, `references/issues.md`,
`templates/discovery.md`, `templates/grilling-section.html`, `docs/protocol.md`, `docs/security.md`, `README.md`,
`docs/acceptance.md`, `evals/grilling-artifact.md` e `evals/runbook.md`. É regra da skill, não barreira: nenhum
script monta o artefato.
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


OLD_CONDITION = 'touches a screen, a flow or the layers'
GONE_OUTCOME = 'não se aplica'
ARTIFACT_FILES = (('skills', 'frontlights', 'references', 'grilling.md'), ('skills', 'frontlights', 'SKILL.md'),
                  ('skills', 'frontlights', 'references', 'issues.md'), ('skills', 'frontlights', 'docs', 'protocol.md'),
                  ('skills', 'frontlights', 'templates', 'discovery.md'), ('README.md',),
                  ('evals', 'grilling-artifact.md'))
# arquivos em que "não se aplica" só aparecia como desfecho do artefato
OUTCOME_FILES = (('skills', 'frontlights', 'references', 'issues.md'), ('skills', 'frontlights', 'docs', 'protocol.md'),
                 ('README.md',), ('evals', 'grilling-artifact.md'))


class ArtifactInTheGrillingTests(unittest.TestCase):
    """Issues 33 e 61: um artefato por grilling, mesma URL, antes na rodada do problema, uma seção por decisão."""

    def artifact(self):
        return flat(section_containing(read('skills', 'frontlights', 'references', 'grilling.md'), 'The artifact'))

    def test_grilling_has_one_artifact_on_one_url(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        artifact = self.artifact()
        self.assertNotEqual(artifact, '')
        for phrase in ('one **artifact** per grilling',
                       'created at the problem round with the **before**',
                       'updated **on the same URL**', 'never one page per round',
                       'built from the real template of the component', 'never a free sketch',
                       'a diagram of the flow, of the layers or of the current rule',
                       '**one section per decision question**',
                       'the solution round and every branch of the decision tree, the pre-mortem included',
                       'Confirmation questions, the depth question and the closing "Seguimos?" get no section',
                       'the before first, then the decision questions', 'titled by the question',
                       "in stage 5 the slices' sections follow them",
                       'Every section follows `templates/grilling-section.html`',
                       'a field with nothing to say is omitted',
                       'the **after** for each approach',
                       '"artefato" is the page, "preview" is the field',
                       'Never a real screenshot', 'never an inline widget',
                       'say so in one line, go on in text', 'artefato indisponível'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertLess(grilling.index('## The artifact'), grilling.index('## 1. Problem round'))

    def test_each_section_is_a_small_edit_of_the_local_source(self):
        artifact = self.artifact()
        for phrase in ('`.frontlights/artifact.html`', '`.frontlights/issues/<n>/artifact.html`', 'untracked',
                       'a small edit of that file', 'never rewrite the whole page each round',
                       'The discovery log records the URL and the source path',
                       "read the published page back with the artifact tool's read and go on editing that copy"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)

    def test_code_enters_the_page_data_never(self):
        artifact = self.artifact()
        for phrase in ("A real excerpt of the project's code (up to 15 lines, with its path)",
                       'replaced by `***`', '(password, token, key, connection string)',
                       "real records, people's data, real endpoints and client or organization names stay out"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertNotIn('only fictitious data', artifact)

    def test_the_code_excerpt_limit_is_up_to_15_lines_everywhere(self):
        for parts, phrase in ((('skills', 'frontlights', 'references', 'grilling.md'), 'up to 15 lines'),
                              (('skills', 'frontlights', 'docs', 'security.md'), 'até 15 linhas'),
                              (('skills', 'frontlights', 'templates', 'grilling-section.html'), 'até 15 linhas'),
                              (('README.md',), 'até 15 linhas'),
                              (('evals', 'grilling-artifact.md'), 'up to 15 lines')):
            text = flat(read(*parts))
            with self.subTest(file=parts[-1]):
                self.assertIn(phrase, text)
                self.assertNotIn('about 15', text)
                self.assertNotIn('cerca de 15', text)

    def test_the_section_template_has_its_fields(self):
        path = ROOT / 'skills' / 'frontlights' / 'templates' / 'grilling-section.html'
        self.assertTrue(path.exists())
        section = path.read_text(encoding='utf-8')
        labels = ('O que esta pergunta decide', 'Conceitos', 'Onde o projeto já faz', 'O que cada opção muda',
                  'Antes e depois', 'Recomendação (opinião)', 'Escolha')
        positions = []
        for label in labels:
            with self.subTest(label=label):
                self.assertIn(label, section)
                positions.append(section.index(label))
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<pergunta>', section)
        self.assertNotIn('style="', section)
        self.assertNotIn('<html', section.lower())

    def test_every_decision_question_cites_the_artifact(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        problem = flat(grilling.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        self.assertIn('Publish the artifact with the **before**', problem)
        self.assertIn('the confirmation question cites its section', problem)
        solution = flat(grilling.split('## 3. Solution round')[1].split('## 4. Decision tree')[0])
        self.assertIn('the section of the artifact that shows what this approach changes', solution)
        tree = flat(grilling.split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0])
        self.assertIn('Every branch that is asked cites its section of the artifact', tree)
        recording = flat(grilling.split('## Recording')[1])
        self.assertIn('the URL of the artifact and its source path (or "artefato indisponível")', recording)

    def test_the_old_condition_and_outcome_are_gone(self):
        for parts in ARTIFACT_FILES:
            text = flat(read(*parts))
            with self.subTest(file='/'.join(parts)):
                self.assertNotIn(OLD_CONDITION, text)
                self.assertNotIn('toca tela, fluxo ou camadas', text)
                self.assertNotIn('touches no screen', text)
        for parts in OUTCOME_FILES:
            with self.subTest(file='/'.join(parts)):
                self.assertNotIn(GONE_OUTCOME, flat(read(*parts)))
        template = read('skills', 'frontlights', 'templates', 'discovery.md')
        self.assertNotIn(GONE_OUTCOME, template.split('## Project conventions')[0])
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        self.assertNotIn(GONE_OUTCOME, self.artifact())
        self.assertNotIn(GONE_OUTCOME, flat(grilling.split('## Recording')[1]))
        skill = read('skills', 'frontlights', 'SKILL.md')
        for stage in (skill.split('## 3.')[1].split('## 4.')[0], skill.split('## 5.')[1].split('## 6.')[0]):
            self.assertNotIn(GONE_OUTCOME, flat(stage))

    def test_the_skill_names_the_artifact_in_stage_3(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage3 = flat(skill.split('## 3.')[1].split('## 4.')[0])
        for phrase in ('one artifact per grilling', 'the same URL', 'built from the real template',
                       'created at the problem round with the before', 'one section per decision question',
                       '`templates/grilling-section.html`', 'a small edit of the local source',
                       'real code excerpts with secrets masked, never real data',
                       'the URL and the source path in the discovery log', '"The artifact"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage3)
        self.assertNotIn('only fictitious data', stage3)

    def test_the_discovery_template_has_the_url_and_source_field(self):
        template = read('skills', 'frontlights', 'templates', 'discovery.md')
        self.assertIn('- Artifact URL and source path (one per grilling, the same URL every round', template)
        self.assertIn('`.frontlights/artifact.html`', template)
        self.assertIn('"artefato indisponível" when the host has no artifact tool', template)
        self.assertLess(template.index('- Grilling depth'), template.index('- Artifact URL'))
        self.assertLess(template.index('- Artifact URL'), template.index('## Project conventions'))

    def test_the_docs_separate_code_from_data(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('publicar o artefato (uma página por grilling, na mesma URL; trecho de código real com segredo '
                      'mascarado, nunca dado real)', protocol)
        self.assertIn('a URL do artefato e o caminho da fonte no log de descoberta (ou "artefato indisponível", sem a '
                      'ferramenta)', protocol)
        self.assertIn('artifact.html', protocol.split('## Registros')[1])
        raw_security = read('skills', 'frontlights', 'docs', 'security.md')
        self.assertIn('## Artefato do grilling', raw_security)
        artifact = flat(section_containing(raw_security, 'Artefato do grilling'))
        for phrase in ('trecho real do código do projeto', 'até 15 linhas',
                       'o valor de todo segredo (senha, token, chave, string de conexão) trocado por `***`',
                       'nenhum registro real, dado de pessoa, endpoint real, nome de cliente ou organização entra na página',
                       'fica fora da máquina', 'nunca do artefato', 'artefato indisponível'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertNotIn('só dados fictícios', flat(raw_security))
        readme = flat(read('README.md'))
        for phrase in ('**Artefato visual.**', 'um artefato por entrevista, na mesma URL',
                       'uma seção por pergunta de decisão', '`templates/grilling-section.html`',
                       'trecho de código real', 'segredo trocado por `***`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)


class ArtifactInTheSliceQuizTests(unittest.TestCase):
    """Issue 33, S2: a lista numerada das CAs cita, por CA, a seção do artefato com o que ela entrega; ensaio a seco."""

    def test_the_numbered_list_cites_the_artifact_section_of_each_slice(self):
        issues = read('skills', 'frontlights', 'references', 'issues.md')
        quiz = flat(section_containing(issues, 'Slices as acceptance criteria'))
        for phrase in ('for each slice, the section of the artifact that shows what it delivers',
                       'the drawing of each slice', 'the same URL as the grilling',
                       'the quiz itself stays the same', 'a slice whose drawing shows nothing demonstrable is horizontal',
                       'numbered after the grilling\'s sections and titled by the slice',
                       'the same rule for code and data as the grilling', '"artefato indisponível" once'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, quiz)
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage5 = flat(skill.split('## 5.')[1].split('## 6.')[0])
        self.assertIn('the section of the artifact with what it delivers', stage5)
        self.assertIn('on the same URL as the grilling', stage5)
        self.assertIn('numbered after the grilling\'s sections', stage5)
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('cada slice com a seção do artefato que mostra o que ela entrega', protocol)
        self.assertNotIn('sem seção, dito uma vez', protocol)
        readme = flat(read('README.md'))
        self.assertIn('cada CA com a seção do artefato que mostra o que ela entrega', readme)

    def test_the_dry_run_and_the_runbook_cover_the_artifact(self):
        case = read('evals', 'grilling-artifact.md')
        self.assertTrue(case.startswith('# Visual artifact in the grilling and in the list of slices (manual; no model score claimed)'))
        for phrase in ('Setup:', 'Expected', 'Reject:', 'on the same URL as the grilling', 'fictitious',
                       'artefato indisponível', 'templates/grilling-section.html', 'one section per decision question',
                       'replaced by `***`', '`.frontlights/artifact.html`', 'read back',
                       'one section per slice', 'never one page per round',
                       'a decision branch without a section (a naming decision, say)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat(case))
        self.assertNotIn('adds nothing to the page', flat(case))
        self.assertNotIn('a page published for a request', flat(case))
        runbook = read('evals', 'runbook.md')
        item = '28. Visual artifact in the grilling and in the list of slices (`evals/grilling-artifact.md`, issue 33).'
        self.assertIn(item, runbook)
        self.assertLess(runbook.index('27. Local main as homologation'), runbook.index(item))
        self.assertLess(runbook.index(item), runbook.index('Only after all required checks pass'))
        entry = flat(runbook[runbook.index(item):runbook.index('29. Pull request template')])
        for phrase in ('one section per decision question', '`templates/grilling-section.html`', 'masked as `***`',
                       'reads the published page back'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry)
        self.assertNotIn('não se aplica', entry)
        acceptance = read('docs', 'acceptance.md')
        self.assertIn('| 28. Artefato visual no grilling e na lista de CAs (issue 33) |', acceptance)
        row = acceptance[acceptance.index('| 28. Artefato visual'):].split('\n')[0]
        self.assertIn('uma seção por pergunta de decisão', row)
        self.assertIn('templates/grilling-section.html', row)
        self.assertNotIn('só dados fictícios', row)


if __name__ == '__main__':
    unittest.main()
