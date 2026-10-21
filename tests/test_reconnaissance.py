"""Reconhecimento por gatilho no grilling (issue 65, S2): a pergunta de profundidade sai; antes das abordagens, o
grilling lê as armadilhas do projeto e, com tela, o antes no app rodando, a origem dos textos, os estados, o ambiente
e as personas; cada gatilho ligado roda a sua sonda num subagente que devolve uma tabela curta de fatos; fato não
verificado não vira opção; a árvore pergunta só produto, escopo e visual; o pré-mortem roda por gatilho e o desafio
da issue sempre que o reconhecimento acha algo; o artefato mostra os estados da tela; o Direct roda o reconhecimento
completo; o log de descoberta registra cada gatilho como "ligado" ou "não se aplica, porque…".

Seams: o texto de `references/grilling.md`, da etapa 3 e do Direct no `SKILL.md`, de `templates/discovery.md`, do
README e de `evals/grilling-artifact.md`. É regra da skill, não barreira: nenhum script roda as sondas.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


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


GRILLING = SKILL / 'references' / 'grilling.md'
# frases da pergunta de profundidade, aposentadas na issue 65
RETIRED = ('Qual profundidade de grilling', '## 0. Depth', 'Grilling depth', 'the depth question', 'Ask the depth',
           'every depth', 'Rápida depth', 'At Exaustiva', 'Depth is asked once', 'pergunta da profundidade',
           'pergunta de profundidade', 'rápida / padrão / exaustiva')


class ReconnaissanceInTheGrillingTests(unittest.TestCase):

    def recon(self):
        return flat(section(read(GRILLING), 'Reconnaissance'))

    def test_the_depth_question_is_gone_from_the_grilling(self):
        text = read(GRILLING)
        self.assertNotIn('## 0. Depth', text)
        self.assertNotRegex(text.lower(), r'\bdepth\b')
        for word in ('Rápida', 'Exaustiva', '**Padrão:**'):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_reconnaissance_sits_between_the_conventions_and_the_solution_round(self):
        text = read(GRILLING)
        self.assertRegex(text, r'(?m)^## Reconnaissance')
        self.assertLess(text.index('## 2. Project conventions'), text.index('## Reconnaissance'))
        self.assertLess(text.index('## Reconnaissance'), text.index('## 3. Solution round'))

    def test_the_minimum_always_runs_with_the_pitfalls_first(self):
        recon = self.recon()
        for phrase in ('What runs is decided by the minimum below and by triggers, never asked',
                       'Read the project\'s pitfalls first', '`.frontlights/pitfalls.md`, when it exists',
                       'With a screen', 'the **before** in the running app', 'the origin of each text',
                       'its states', 'the environment and the personas', 'the app and the API up',
                       'one login attempt per persona', 'never a password'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, recon)
        self.assertLess(recon.index('pitfalls first'), recon.index('With a screen'))

    def test_each_trigger_has_its_probe(self):
        recon = self.recon()
        for trigger, probe in (
                ('Rule or data of more than one actor',
                 "actors × the controller's endpoints × the guard and the claim it reads, the inverse operation "
                 'included'),
                ('Consumes an existing endpoint',
                 'live HTTP probe on the local API: search, ordering, empty page and another account'),
                ('Rule over existing data, or a migration', 'count `SELECT` of the states that contradict the premise'),
                ('Shared contract, route, field or text', 'its writers and its consumers'),
                ('Multi-step flow', 'each exit per step, retry, double click and partial failure')):
            with self.subTest(trigger=trigger):
                self.assertIn(f'| {trigger} | ', recon)
                self.assertIn(probe, recon)

    def test_the_trigger_table_feeds_the_decision_tree_instead_of_repeating_it(self):
        recon = self.recon()
        self.assertIn('The decision tree (section 4) names where to look; these probes bring the facts', recon)
        tree = flat(read(GRILLING).split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0])
        self.assertEqual(tree.count('| Feature |'), 1)
        self.assertNotIn('live HTTP probe', tree)

    def test_a_fact_comes_before_the_option(self):
        recon = self.recon()
        for phrase in ('Each probe runs in a subagent', 'launched together in one message',
                       'returns a short fact table (up to about 20 lines', 'its evidence by path',
                       'An unverified fact never becomes an option.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, recon)

    def test_the_log_records_each_trigger_on_or_not_applicable(self):
        recon = self.recon()
        self.assertIn('The discovery log records every trigger as "ligado" or "não se aplica, porque…"', recon)
        self.assertIn('`templates/discovery.md`, "Reconnaissance"', recon)

    def test_the_tree_asks_only_product_scope_and_visual(self):
        tree = flat(read(GRILLING).split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0])
        for phrase in ('The tree asks the user only product, scope and visual',
                       'a technical branch the evidence settles is not asked',
                       'it becomes an assumption shown in the plan with its evidence'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, tree)

    def test_pre_mortem_by_trigger_and_challenge_when_the_reconnaissance_finds_something(self):
        text = read(GRILLING)
        premortem = flat(text.split('## 5. Pre-mortem')[1].split('## Sub-issues')[0])
        self.assertIn('when the reconnaissance turned on the actor, the existing-data or the migration trigger',
                      premortem)
        recon = self.recon()
        self.assertIn('Whenever the reconnaissance finds something', recon)
        self.assertIn('challenge the issue', recon)
        self.assertIn('A change of scope is a divergence from GitHub', recon)
        problem = flat(text.split('## 1. Problem round')[1].split('## 2. Project conventions')[0])
        self.assertNotIn('Challenge the issue', problem)

    def test_the_artifact_shows_the_screen_states(self):
        recon = self.recon()
        self.assertIn('the **after** of each approach in the artifact shows the empty state, no image, error, '
                      'loading, dark theme and 1366 px, plus the states the project\'s pitfalls list', recon)
        artifact = flat(section(read(GRILLING), 'The artifact'))
        self.assertIn('the screen states of "Reconnaissance"', artifact)


class ReconnaissanceInTheSkillTests(unittest.TestCase):

    def test_stage_3_runs_the_reconnaissance_before_the_approaches(self):
        stage3 = flat(read(SKILL / 'SKILL.md').split('## 3.')[1].split('## 4.')[0])
        self.assertNotIn('depth', stage3.lower())
        for phrase in ('run the reconnaissance by trigger', 'the project\'s pitfalls first',
                       'each probe in a subagent that returns a short fact table',
                       'an unverified fact never becomes an option',
                       'asking only product, scope and visual'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage3)
        self.assertLess(stage3.index('run the reconnaissance by trigger'), stage3.index('at least three'))

    def test_direct_runs_the_full_reconnaissance_and_records_the_before(self):
        text = read(SKILL / 'SKILL.md')
        direct = flat(text.split('- **Direct.**')[1].split('- **Short.**')[0])
        for phrase in ('runs the full reconnaissance by trigger, even without an issue',
                       '(`references/grilling.md`, "Reconnaissance")',
                       'writes its walkthrough with the before recorded before the code'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, direct)

    def test_the_discovery_template_carries_the_trigger_table(self):
        template = read(SKILL / 'templates' / 'discovery.md')
        self.assertNotIn('Grilling depth', template)
        recon = flat(section(template, 'Reconnaissance'))
        self.assertIn('ligado / não se aplica, porque…', recon)
        for row in ('Pitfalls of the project', 'Screen: before, origin of the texts, states',
                    'Environment and personas', 'Rule or data of more than one actor',
                    'Consumes an existing endpoint', 'Rule over existing data, or a migration',
                    'Shared contract, route, field or text', 'Multi-step flow'):
            with self.subTest(row=row):
                self.assertIn(f'| {row} |', recon)
        self.assertLess(template.index('## Project conventions'), template.index('## Reconnaissance'))
        self.assertLess(template.index('## Reconnaissance'), template.index('## Approaches considered'))

    def test_the_readme_describes_the_reconnaissance(self):
        readme = flat(read(ROOT / 'README.md'))
        for phrase in ('reconhecimento por gatilho', 'as armadilhas do projeto', 'tabela curta de fatos',
                       'fato não verificado não vira opção', 'só produto, escopo e visual'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_the_depth_question_is_retired_everywhere(self):
        files = (sorted(SKILL.rglob('*.md')) + [ROOT / 'README.md'] + sorted((ROOT / 'evals').glob('*.md'))
                 + sorted((ROOT / 'docs').glob('*.md')))
        for path in files:
            text = flat(read(path))
            for phrase in RETIRED:
                with self.subTest(file=path.relative_to(ROOT).as_posix(), phrase=phrase):
                    self.assertNotIn(phrase.lower(), text.lower())


if __name__ == '__main__':
    unittest.main()
