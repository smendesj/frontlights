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
import json
import re
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

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


SECTION_FIELDS = ('Por que estamos perguntando isso', 'Visual', 'Cenário por opção', 'Consequências', 'Conceitos',
                  'Onde o projeto já faz', 'Recomendação (opinião)', 'Escolha')
GONE_FIELDS = ('O que esta pergunta decide', 'O que cada opção muda', 'Antes e depois')
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
        for phrase in ('One **artifact** per grilling',
                       'created at the problem round with the **base**',
                       'updated **on the same URL**', 'never one page per round',
                       'a **print of the system running at the base**',
                       'a diagram of the flow, of the layers or of the current rule',
                       '**one section per decision question**',
                       'the solution round and every branch of the decision tree, the pre-mortem included',
                       'Confirmation questions and the closing "Seguimos?" get no section',
                       'the base first, then the decision questions', 'titled by the question',
                       "in stage 5 the slices' sections follow them",
                       'Every section follows `templates/grilling-section.html`',
                       'a field with nothing to say is omitted',
                       'which for each approach carries the screen states',
                       '"artefato" is the page, "preview" is the field',
                       'Never an inline widget',
                       'say so in one line, go on in text', 'artefato indisponível'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertLess(grilling.index('## The artifact'), grilling.index('## 1. Problem round'))

    def test_the_script_builds_and_the_session_publishes_once_per_round(self):
        # redesenho, issue 6: a edição pequena da fonte virou `frontlights.py artifact`; uma publicação por rodada
        artifact = self.artifact()
        for phrase in ('`.frontlights/artifact.html`', '`.frontlights/issues/<n>/artifact.html`', 'untracked',
                       '`frontlights.py artifact init`', '`frontlights.py artifact section --n <k> --kind '
                       'tela|fluxo|regra|camadas|texto', '`frontlights.py artifact choose --n <k> --answer',
                       'the same number replaces a section',
                       'Publish the whole source once per round, on the same URL, never by `edits`',
                       'The discovery log records the URL and the source path',
                       "read the published page back with the artifact tool's read into that path"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        for gone in ('a small edit of that file', 'never rewrite the whole page each round'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, artifact)

    def test_code_enters_the_page_data_never(self):
        # redesenho, issue 6: a regra vive só em security.md, "Artefato do grilling", que a etapa lê ao entrar
        artifact = self.artifact()
        self.assertIn('**Code, never data:** `docs/security.md`, "Artefato do grilling"', artifact)
        self.assertIn('On entering, read `docs/security.md`, "Artefato do grilling"',
                      flat(read('skills', 'frontlights', 'references', 'grilling.md')))
        self.assertNotIn('only fictitious data', artifact)

    def test_the_code_excerpt_limit_is_up_to_15_lines_everywhere(self):
        for parts, phrase in ((('skills', 'frontlights', 'docs', 'security.md'), 'até 15 linhas'),
                              (('skills', 'frontlights', 'templates', 'grilling-section.html'), 'até 15 linhas'),
                              (('README.md',), 'até 15 linhas'),
                              (('evals', 'grilling-artifact.md'), 'up to 15 lines')):
            text = flat(read(*parts))
            with self.subTest(file=parts[-1]):
                self.assertIn(phrase, text)
                self.assertNotIn('about 15', text)
                self.assertNotIn('cerca de 15', text)

    def test_the_section_template_has_its_fields(self):
        """Issue 68: os campos explicam o que a pergunta implica; Visual, Cenário e Consequências sempre."""
        path = ROOT / 'skills' / 'frontlights' / 'templates' / 'grilling-section.html'
        self.assertTrue(path.exists())
        section = path.read_text(encoding='utf-8')
        headings = re.findall(r'<h3>([^<]*)</h3>', section)
        self.assertEqual(headings, list(SECTION_FIELDS))
        for gone in GONE_FIELDS:
            with self.subTest(gone=gone):
                self.assertNotIn(gone, headings)
        for css in ('campo-por-que', 'campo-visual', 'campo-cenario', 'campo-consequencias', 'campo-conceitos',
                    'campo-projeto', 'campo-recomendacao', 'campo-escolha'):
            with self.subTest(css=css):
                self.assertIn('class="campo ' + css + '"', section)
        visual = section[section.index('campo-visual'):section.index('campo-cenario')]
        self.assertIn('class="comparacao"', visual)
        comment = flat(section.split('-->')[0])
        for phrase in ('Visual, Cenário por opção e Consequências estão em toda seção', 'nunca repete a pergunta',
                       'até 15 linhas', '***'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, comment)
        self.assertIn('<pergunta>', section)
        self.assertNotIn('style="', section)
        self.assertNotIn('<html', section.lower())

    def test_a_section_explains_more_than_the_question(self):
        """Issue 68: a seção nunca repete a pergunta; o visual vem do tipo de pergunta; os três tipos de seção."""
        artifact = self.artifact()
        for phrase in ('explains more than the question, never repeats it', 'what does this imply',
                       'Visual, Cenário por opção and Consequências are always present',
                       'the base of the problem round', 'each decision question',
                       'each slice section of the stage 5 quiz', 'why it is a problem'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        # redesenho, issue 6: a tabela de tipos virou uma frase, "The visual follows the kind of question: ..."
        for kind, drawing in (('a screen', 'the base print and, per option, the **same print with markings**'),
                              ('a flow', 'a timeline per option, side by side'),
                              ('a rule', 'a table of cases'),
                              ('layers', 'a layers diagram per option'),
                              ('a name or a text', 'a side-by-side comparison of where it appears')):
            with self.subTest(kind=kind):
                self.assertIn(f'{kind}, {drawing}', artifact)
        for gone in ('what the question decides', 'what each option changes'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, artifact)

    def test_every_decision_question_cites_the_artifact(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        problem = flat(grilling.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        self.assertIn('Publish the artifact with the **base**', problem)
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
        for stage in (skilltext.stage(3), skilltext.stage(5)):
            self.assertNotEqual(stage, '')
            self.assertNotIn(GONE_OUTCOME, flat(stage))

    def test_the_skill_names_the_artifact_in_stage_3(self):
        # redesenho, issue 3: a etapa 3 diz só "One artifact per grilling, the base print first" e aponta para
        # grilling.md, "The artifact"; o resto da regra vive lá, nas palavras da referência
        stage3 = flat(skilltext.stage(3))
        # redesenho, issue 6: a etapa 3 cita os comandos do print da base e do artefato
        for phrase in ('One artifact per grilling', 'the base print first', '(`references/grilling.md`, "The artifact")',
                       '`serve.py window shot --pass antes`', '`frontlights.py artifact init`',
                       '`frontlights.py artifact section` per question', 'one publication per round, never `edits`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage3)
        self.assertNotIn('only fictitious data', stage3)
        artifact = self.artifact()
        for phrase in ('One **artifact** per grilling', '**on the same URL**', '**print of the system running at the base**',
                       '**same print with markings**', 'created at the problem round with the **base**',
                       'one section per decision question', '`templates/grilling-section.html`',
                       '`frontlights.py artifact section', 'never by `edits`',
                       'The discovery log records the URL and the source path'):
            with self.subTest(where='grilling.md', phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertNotIn('only fictitious data', artifact)

    def test_the_discovery_template_has_the_url_and_source_field(self):
        template = read('skills', 'frontlights', 'templates', 'discovery.md')
        self.assertIn('- Artifact URL and source path (one per grilling, the same URL every round', template)
        self.assertIn('`.frontlights/artifact.html`', template)
        self.assertIn('"artefato indisponível" when the host has no artifact tool', template)
        self.assertLess(template.index('- Assumptions requiring verification'), template.index('- Artifact URL'))
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
                       'fica fora da máquina', 'artefato indisponível'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        self.assertNotIn('só dados fictícios', flat(raw_security))
        readme = flat(read('README.md'))
        for phrase in ('**Artefato visual.**', 'um artefato por entrevista, na mesma URL',
                       'uma seção por pergunta de decisão', '`templates/grilling-section.html`',
                       'trecho de código real', 'segredo trocado por `***`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)


class PrintOfTheBaseTests(unittest.TestCase):
    """Issue 74, S1: com tela, o antes é um print do sistema rodando na base, tirado com conta de teste na janela do
    teste assistido; o depois é o mesmo print com marcações em HTML; sem print o grilling para; sem tela, o diagrama."""

    def artifact(self):
        return flat(section_containing(read('skills', 'frontlights', 'references', 'grilling.md'), 'The artifact'))

    def security(self):
        return flat(section_containing(read('skills', 'frontlights', 'docs', 'security.md'), 'Artefato do grilling'))

    def test_the_before_is_a_print_of_the_base_with_a_test_account(self):
        artifact = self.artifact()
        for phrase in ('With a screen, the base is a **print of the system running at the base** (`origin/<base>`)',
                       'taken with a test account and test data',
                       'in the disposable Chrome window of the watched run (`references/browser-testing.md`)',
                       'never a screen rebuilt from the template or redrawn in the style of the page',
                       'Without a screen, it is a diagram of the flow, of the layers or of the current rule'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        for gone in ('built from the real template of the component', 'never a free sketch'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, artifact)
        # redesenho, issue 3: a etapa 3 diz "the base print first"; a conta de teste está fixada acima, em grilling.md
        stage3 = flat(skilltext.stage(3))
        self.assertIn('the base print first (`references/grilling.md`, "The artifact")', stage3)
        self.assertNotIn('built from the real template', stage3)

    def test_the_screen_states_are_notes_on_the_marked_print(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        states = flat(grilling.split('**Screen states in the artifact.**')[1].split('## 3.')[0])
        for phrase in ('as notes on its one marked print', 'never one print per state',
                       'the evidence of DEPOIS still comes from the watched run'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, states)

    def test_the_after_is_the_same_print_with_markings(self):
        artifact = self.artifact()
        for phrase in ('the **same print with markings** overlaid in HTML (boxes, arrows and texts on top)',
                       'never a redrawn screen'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, artifact)
        quiz = flat(section_containing(read('skills', 'frontlights', 'references', 'issues.md'),
                                       'Slices as acceptance criteria'))
        self.assertIn('with a screen, the same before print with the markings of what that slice changes', quiz)
        template = read('skills', 'frontlights', 'templates', 'grilling-section.html')
        for phrase in ('o print da base', 'o mesmo print da base', 'class="marca'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, template)
        self.assertNotIn('montada do template real', template)

    def test_the_ban_on_the_print_is_gone_and_data_still_never_enters(self):
        artifact = self.artifact()
        self.assertNotIn('Never a real screenshot', artifact)
        self.assertNotIn('that belongs to the watched run', artifact)
        security = self.security()
        self.assertNotIn('Os prints do produto em execução são do teste assistido', security)
        self.assertNotIn('nunca do artefato', security)
        for phrase in ('Dado nunca entra', 'a base é um print do sistema rodando na base',
                       'tirado com conta de teste e dados de teste', 'cada opção é o mesmo print com marcações',
                       'nem num print'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn('montado do template real', security)

    def test_no_print_stops_the_grilling(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        problem = flat(grilling.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        for phrase in ('any test account that already exists (those of `browserTest.users` or any other) serves',
                       'the session may create one on demand',
                       'when there is no test account or the base does not come up, the grilling stops',
                       'goes on only once the account exists and the base is up'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, problem)

    def test_the_print_points_to_the_clean_rule_without_copying_it(self):
        pointer = '`references/browser-testing.md`, "Prints kept for the progress summary", item "Clean"'
        artifact = self.artifact()
        self.assertIn(pointer, artifact)
        self.assertIn("an image of the artifact: an asset of the host's artifact tool, or embedded in the page when "
                      'the host has nowhere to keep assets', artifact)
        self.assertIn(pointer, self.security())
        for copied in ('1 MB', 'browser chrome', 'ANTES/DEPOIS strip'):
            with self.subTest(copied=copied):
                self.assertNotIn(copied, artifact)

    def test_readme_acceptance_and_dry_run_describe_the_print(self):
        readme = flat(read('README.md'))
        for phrase in ('print do sistema rodando na base', 'o mesmo print com marcações', 'o grilling para'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertNotIn('a tela montada do template real', readme)
        acceptance = read('docs', 'acceptance.md')
        row = acceptance[acceptance.index('| 28. Artefato visual'):].split('\n')[0]
        for phrase in ('issue 74', 'print do sistema rodando na base', 'o mesmo print com marcações',
                       'o grilling para'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)
        self.assertNotIn('antes montado do template real', row)
        case = flat(read('evals', 'grilling-artifact.md'))
        for phrase in ('a print of the system running at the base', 'the same print with markings',
                       'the grilling stops', 'a screen rebuilt from the template'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, case)
        self.assertNotIn('built from the real template', case)
        self.assertNotIn('a real screenshot of the running product in the grilling', case)
        runbook = flat(read('evals', 'runbook.md'))
        self.assertNotIn('the before built from the real template', runbook)


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
        for phrase in ('the same model (`templates/grilling-section.html`)',
                       'opens with what can be demoed when the slice is done', 'the drawing of the slice is its Visual'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, quiz)
        # redesenho, issue 3: a etapa 5 diz "the numbered list with its artifact section"; a mesma URL e a numeração
        # depois das seções do grilling estão fixadas acima, em issues.md
        stage5 = flat(skilltext.stage(5))
        self.assertIn('Show the numbered list with its artifact section', stage5)
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
        for phrase in ('a section that repeats the question', 'a section without Visual, Cenário por opção or Consequências'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat(case))
        for gone in ('what the question decides', 'what each option changes'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, flat(case))
                self.assertNotIn(gone, flat(read('skills', 'frontlights', 'references', 'grilling.md')))
        readme = flat(read('README.md'))
        for gone in ('o que a pergunta decide', 'o que cada opção muda'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, readme)
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


class BaseAndOptionVocabularyTests(unittest.TestCase):
    """Redesenho, issue 6, S5: o artefato diz "base" e "com a opção", nunca antes/depois (nem before/after no texto
    que o descreve): ANTES e DEPOIS são as janelas do teste assistido."""

    def test_the_grilling_describes_the_artifact_with_base_and_option(self):
        grilling = read('skills', 'frontlights', 'references', 'grilling.md')
        artifact = flat(section_containing(grilling, 'The artifact'))
        self.assertIn('**Base and com a opção.** The page, its labels and the questions that cite it say "base" and '
                      '"com a opção", never antes/depois nor before/after: ANTES and DEPOIS name the windows of the '
                      'watched run.', artifact)
        rule = artifact.replace('never antes/depois nor before/after', '')
        self.assertNotRegex(rule, r'(?i)\b(before|after)\b')
        problem = flat(grilling.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        states = flat(grilling.split('**Screen states in the artifact.**')[1].split('## 3.')[0])
        for text in (problem, states):
            self.assertNotRegex(text, r'\*\*(before|after)\*\*')

    def test_the_templates_and_the_security_doc_say_base_and_option(self):
        section = read('skills', 'frontlights', 'templates', 'grilling-section.html')
        body = section.split('-->', 1)[1]
        page = read('skills', 'frontlights', 'templates', 'artifact-page.html').split('-->', 1)[1]
        for name, text in (('grilling-section.html', body), ('artifact-page.html', page)):
            visible = re.sub(r'src="[^"]*"', '', text)
            with self.subTest(template=name):
                self.assertNotRegex(visible, r'(?i)\b(antes|depois)\b')
        self.assertIn('<figcaption>Base</figcaption>', body)
        self.assertIn('<figcaption>Com a opção: <opção></figcaption>', body)
        self.assertIn('Rótulos "Base" e "Com a opção", nunca antes/depois', flat(section.split('-->')[0]))
        security = flat(section_containing(read('skills', 'frontlights', 'docs', 'security.md'), 'Artefato do grilling'))
        self.assertIn('na página, "base" e "com a opção", nunca antes/depois, que são as janelas do teste assistido',
                      security)
        for gone in ('o antes é', 'o depois é'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, security)


SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
SECTION = """## Por que
A lista cresce e ninguém acha o pedido.
## Visual
- **Filtro no topo** @10,5: um campo de data acima da tabela
- **Filtro lateral**: um painel à direita
## Cenário por opção
- **Filtro no topo**: Ana filtra 03/10 e vê 4 pedidos.
- **Filtro lateral**: Ana abre o painel e escolhe 03/10.
## Consequências
- **Filtro no topo**: barato e reversível.
- **Filtro lateral**: mais espaço, custo maior.
## Onde o projeto já faz
`src/lista.ts:12`
```ts
const filtro = null;
```
"""


class ArtifactCommandTests(unittest.TestCase):
    """Redesenho, issue 6, S1: `frontlights.py artifact init|section|choose` monta o esqueleto na fonte local;
    conteúdo, publicação (uma por rodada, nunca `edits`) e URL são da sessão."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / '.frontlights' / 'artifact.html'

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        done = subprocess.run([sys.executable, str(SCRIPT), 'artifact', *argv, '--root', str(self.root)],
                              capture_output=True, encoding='utf-8', timeout=60)
        return done.returncode, json.loads(done.stdout)

    def content(self, text=SECTION, name='secao.md'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return str(path)

    def section(self, *extra, content=None):
        return self.run_cli('section', '--n', '2', '--kind', 'tela', '--title', 'Onde fica o filtro?',
                            '--option', 'Filtro no topo', '--option', 'Filtro lateral',
                            '--content', content or self.content(), *extra)

    def test_init_writes_the_page_with_the_base_print_and_says_how_to_publish(self):
        code, out = self.run_cli('init', '--title', 'Filtro por data', '--before', 'base.png')
        self.assertEqual(code, 0, out)
        page = self.source.read_text(encoding='utf-8')
        self.assertIn('<title>Filtro por data</title>', page)
        self.assertIn('<img class="print" src="antes.png"', page)
        self.assertIn('id="secao-1"', page)
        self.assertEqual(out['publish'], {'file_path': str(self.source.resolve()), 'files': {'antes.png': 'base.png'}})
        self.assertIn('nunca por edits', out['message'])
        self.assertIn('Artifact URL and source path', out['message'])
        code, out = self.run_cli('init')
        self.assertEqual((code, out['reason']), (1, 'artifact_exists'))

    def test_init_of_a_published_issue_goes_to_its_records(self):
        code, out = self.run_cli('init', '--issue', '12', '--kind', 'fluxo')
        self.assertEqual(code, 0, out)
        page = (self.root / '.frontlights' / 'issues' / '12' / 'artifact.html').read_text(encoding='utf-8')
        self.assertNotIn('antes.png', page)

    def test_section_fills_the_fields_of_the_model_in_order(self):
        self.run_cli('init')
        code, out = self.section()
        self.assertEqual(code, 0, out)
        self.assertEqual(out['sections'], [2])
        page = self.source.read_text(encoding='utf-8')
        model = (ROOT / 'skills' / 'frontlights' / 'templates' / 'grilling-section.html').read_text(encoding='utf-8')
        block = page[page.index('id="secao-2"'):]
        block = block[:block.index('</section>')]
        model_fields = re.findall(r'<h3>([^<]*)</h3>', model)
        found = re.findall(r'<h3>([^<]*)</h3>', block)
        self.assertEqual(found, [f for f in model_fields if f not in ('Conceitos', 'Recomendação (opinião)')])
        for phrase in ('<figcaption>Base</figcaption>', '<figcaption>Com a opção: Filtro no topo</figcaption>',
                       'class="marca marca-texto" id="marca-2-1"', '<pre class="codigo"><code>const filtro = null;'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)
        self.assertIn('#marca-2-1 { left: 10%; top: 5%; }', page)
        self.assertNotIn('style="', page)
        visible = re.sub(r'src="[^"]*"', '', block)
        self.assertNotRegex(visible, r'(?i)\b(antes|depois)\b')

    def test_the_same_number_replaces_the_section_and_choose_records_the_answer(self):
        self.run_cli('init')
        self.section()
        self.section()
        page = self.source.read_text(encoding='utf-8')
        self.assertEqual(page.count('id="secao-2"'), 1)
        code, out = self.run_cli('choose', '--n', '2', '--answer', 'Filtro no topo')
        self.assertEqual(code, 0, out)
        block = self.source.read_text(encoding='utf-8').split('id="secao-2"')[1]
        self.assertIn('<h3>Escolha</h3>\n<p>Filtro no topo</p>', block)

    def test_several_sections_in_one_call(self):
        self.run_cli('init')
        rule = self.content('## Visual\n| Caso | A | B |\n| --- | --- | --- |\n| vazio | erro | ignora |\n'
                            '## Cenário\n- **A**: x\n- **B**: y\n## Consequências\n- **A**: x\n- **B**: y\n', 'regra.md')
        code, out = self.run_cli('section', '--n', '4', '--n', '3', '--kind', 'regra', '--title', 'Regra?',
                                 '--title', 'Outra?', '--option', '4:A', '--option', '4:B', '--option', '3:A',
                                 '--option', '3:B', '--content', rule, '--content', rule)
        self.assertEqual(code, 0, out)
        page = self.source.read_text(encoding='utf-8')
        self.assertLess(page.index('id="secao-3"'), page.index('id="secao-4"'))
        self.assertIn('<table class="casos">', page)

    def test_refusals(self):
        self.run_cli('init')
        for text, reason in (('## Visual\nx\n## Cenário\n- **Filtro no topo**: a\n- **Filtro lateral**: b\n', 'missing_field'),
                             (SECTION.replace('- **Filtro lateral**: mais espaço, custo maior.', ''), 'option_missing'),
                             (SECTION + '<div style="color:red">x</div>\n', 'inline_style'),
                             (SECTION.replace('const filtro = null;', '\n'.join(['x'] * 16)), 'code_too_long')):
            with self.subTest(reason=reason):
                code, out = self.section(content=self.content(text))
                self.assertEqual((code, out['reason']), (1, reason))

    def test_a_missing_source_with_a_logged_url_is_read_back(self):
        (self.root / '.frontlights').mkdir()
        (self.root / '.frontlights' / 'discovery.md').write_text(
            '- Artifact URL and source path (...): https://claude.ai/code/artifact/abc, .frontlights/artifact.html\n',
            encoding='utf-8')
        code, out = self.section()
        self.assertEqual((code, out['reason']), (1, 'source_missing'))
        self.assertIn('leia a página publicada de volta para', out['message'])
        self.assertIn('https://claude.ai/code/artifact/abc', out['hint'])
        (self.root / '.frontlights' / 'discovery.md').unlink()
        code, out = self.section()
        self.assertEqual(out['reason'], 'no_artifact')

    def test_the_security_doc_gives_the_skeleton_to_the_script_and_the_rest_to_the_session(self):
        security = flat(section_containing(read('skills', 'frontlights', 'docs', 'security.md'), 'Artefato do grilling'))
        for phrase in ('O esqueleto vem do script (`frontlights.py artifact`', 'conteúdo, publicação e URL são da sessão',
                       'uma vez por rodada', 'nunca por `edits`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn('nenhum script monta a página', security)


if __name__ == '__main__':
    unittest.main()
