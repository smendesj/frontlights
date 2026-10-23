"""Issue 74, S2: a passada ANTES abre no grilling e a janela fica aberta; no fim, o teste assistido roda só a DEPOIS.

(a) Em issue com tela, a janela ANTES (Chrome descartável, faixa "ANTES: origin/main", conta de teste, base
`origin/<base>` num checkout destacado) abre na rodada do problema do grilling, tira os prints do artefato e, aprovado
o plano, roda o `Fluxo:` de cada critério na base enquanto as slices andam; fecha na última evidência ANTES ou quando
o usuário fecha; holder sem limite de tempo; servidor da base em porta `auto` (com porta fixa, os servidores das
slices esperam); janela fechada no meio reabre sem pergunta; mudança de tela na base antes da DEPOIS roda de novo o
ANTES daquele critério no fim. A pergunta "Pronto para assistir…?" sai antes da primeira janela ANTES e antes da
janela DEPOIS.
(b) Nenhuma slice aplica migração no banco local antes de o ANTES fechar (condição da operação coberta, em
`references/development.md`); aplicada antes, o relatório diz que o ANTES não é fiel.
(c) No fim, só a DEPOIS, um print por critério, no mesmo ponto do ANTES; "Assistir de novo" repete só a DEPOIS; o
ritmo da DEPOIS não muda (cada caso duas vezes, cerca de 5 minutos).
(d) Nomes `antes-<cover>-S<n>.png`, `depois-<cover>-S<n>.png` e `falha-<caso>`; no texto, `antes#<cover>-S<n>`.
(e) Contas e dados de teste ficam para reuso no banco local de desenvolvimento; nada de remoção no fim da passada;
o perfil movido continua sendo desfeito.

Seam: o texto da skill, dos docs, do README, dos evals e dos modelos, achatado pelos espaços. É regra da skill, não
barreira: nenhum script abre a janela ANTES.
"""
import re
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, title):
    match = re.search(rf'^## {re.escape(title)}\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    return flat(match.group(1)) if match else ''


REFERENCE = read('skills', 'frontlights', 'references', 'browser-testing.md')
WATCHED = section(REFERENCE, 'Watched run: before and after, with the user watching')
DEVELOPMENT = flat(read('skills', 'frontlights', 'references', 'development.md'))


class AntesOpensInTheGrillingTests(unittest.TestCase):
    def test_the_antes_window_opens_in_the_grilling_and_stays_open(self):
        for phrase in ('**The ANTES window, from the grilling.**',
                       'opens at the problem round of the grilling',
                       'first it takes the prints of the screens for the before of the artifact',
                       'the same window runs the `Fluxo:` of each criterion on the base',
                       'while the slices go on in parallel',
                       'It closes when the last ANTES evidence is taken or when the user closes it',
                       'Its holder has no time limit',
                       'reopens on the base, with no question, when the next capture is due',
                       'the ANTES of that criterion runs again at the end',
                       'The base server takes an `auto` port of its own',
                       'the servers of the slices and of the issue wait for the ANTES window to close'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)

    def test_a_grilling_without_an_issue_serves_the_base_on_a_provisional_record(self):
        for phrase in ('Before the issue exists',
                       'named after the discovery log',
                       '`serve start --root <base-checkout> --issue 0`',
                       'once the issue is published, its prints move to the evidence folder of the issue'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)

    def test_only_a_running_pass_holds_another_issue_back(self):
        for phrase in ('Passes never overlap while one is running',
                       'an ANTES window that is open but idle holds no other issue back'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)

    def test_the_question_comes_before_each_of_the_two_windows_and_not_on_a_reopening(self):
        for phrase in ('Pronto para assistir ao teste de navegador da issue #<n>?',
                       'Before each of the two windows opens',
                       'A reopened ANTES window asks nothing'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)

    def test_the_grilling_and_the_skill_point_to_the_window_rule(self):
        grilling = flat(read('skills', 'frontlights', 'references', 'grilling.md'))
        self.assertIn('its ANTES window, which opens here and stays open', grilling)
        # redesenho, issue 6: o grilling cita os comandos da janela ANTES que a issue 8 entregou
        self.assertIn('(`serve.py window open --strip "ANTES: origin/main"`, then `serve.py window shot --pass antes '
                      '--name base`)', grilling)
        # redesenho, issue 3: a etapa 3 diz a mesma regra em palavras novas e aponta para "Watched run"
        stage3 = flat(skilltext.stage(3))
        self.assertIn('with a screen the ANTES window opens here and stays open '
                      '(`references/browser-testing.md`, "Watched run")', stage3)
        self.assertIn('the ANTES window, open since the grilling, runs the `Fluxo:` of each criterion on the base', DEVELOPMENT)

    def test_the_window_rule_lives_only_in_the_reference(self):
        fragment = 'reopens on the base, with no question, when the next capture is due'
        homes = [path.relative_to(ROOT).as_posix() for path in sorted(SKILL.rglob('*.md'))
                 if fragment in flat(path.read_text(encoding='utf-8'))]
        self.assertEqual(homes, ['skills/frontlights/references/browser-testing.md'])


class MigrationsWaitTests(unittest.TestCase):
    def test_the_covered_operation_waits_for_antes(self):
        self.assertIn('running migrations on the local development database, never before the ANTES window of the '
                      'issue has closed', DEVELOPMENT)
        self.assertIn('the report says that ANTES is not faithful', DEVELOPMENT)

    def test_the_reference_points_to_the_condition(self):
        self.assertIn('**Migrations wait for ANTES.**', WATCHED)
        self.assertIn('"Standing authorization and the denied operations"', WATCHED)
        self.assertNotIn('Faithful ANTES', WATCHED)

    def test_the_condition_lives_only_in_development(self):
        fragment = 'never before the ANTES window of the issue has closed'
        homes = [path.relative_to(ROOT).as_posix() for path in sorted(SKILL.rglob('*.md'))
                 if fragment in flat(path.read_text(encoding='utf-8'))]
        self.assertEqual(homes, ['skills/frontlights/references/development.md'])


class OnlyDepoisAtTheEndTests(unittest.TestCase):
    def test_the_end_runs_only_depois_with_one_print_per_criterion(self):
        for phrase in ('At the end the watched run runs only DEPOIS',
                       '**One print per criterion.**',
                       'at the same place in ANTES and DEPOIS',
                       'the result of each step stays in text, only in `result.json`',
                       'Each case runs twice in each pass', 'about 5 minutes'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)
        self.assertNotIn('One print per pass', WATCHED)
        what_runs = flat(re.search(r'\*\*What runs\.\*\*.*?(?=\n\n)', REFERENCE, re.S).group(0))
        self.assertIn('only DEPOIS', what_runs)

    def test_watching_again_runs_only_depois(self):
        after = flat(re.search(r'\*\*After the watched run.*?(?=\n\*\*Real back first)', REFERENCE, re.S).group(0))
        self.assertIn('runs only DEPOIS again', after)
        self.assertNotIn('Start ANTES again', after)


class NamesTests(unittest.TestCase):
    def test_the_reference_names_the_files_and_the_text_labels(self):
        for phrase in ('`antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png`', '`antes#<cover>-S<n>`',
                       '`#` breaks a URL and the check of the push', '`falha-<caso>`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, WATCHED)
        evidence = section(REFERENCE, 'Evidence')
        self.assertIn('exactly one per pass and criterion, named `antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png`',
                      evidence)
        self.assertNotIn('`antes-<n>`', evidence)

    def test_the_docs_use_the_new_names(self):
        for name in (('README.md',), ('skills', 'frontlights', 'docs', 'security.md'), ('evals', 'runbook.md'),
                     ('skills', 'frontlights', 'templates', 'pr.md')):
            text = flat(read(*name))
            with self.subTest(doc=name[-1]):
                self.assertIn('antes-<cover>-S<n>', text)
                self.assertNotIn('`antes-<n>`', text)


class TestDataStaysTests(unittest.TestCase):
    def test_the_rule_keeps_accounts_and_data_for_reuse(self):
        rule = section(REFERENCE, 'Test data the run creates')
        for phrase in ('any test account that already exists', 'creates on demand',
                       '**Kept for reuse.**', 'is not removed at the end of a pass',
                       'the same accounts and data serve ANTES and DEPOIS', 'kind and id, for reuse',
                       '`perfil-original.json`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        for gone in ('`removido', 'in reverse order of creation', '`DELETE`', '**Cleanup.**'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, rule)

    def test_the_question_and_the_docs_say_the_data_stays(self):
        self.assertIn('which stays on the local development database for reuse', WATCHED)
        self.assertNotIn('removes it afterwards', WATCHED)
        for name in (('README.md',), ('skills', 'frontlights', 'docs', 'security.md')):
            text = flat(read(*name))
            with self.subTest(doc=name[-1]):
                self.assertIn('ficam para reuso', text)
                self.assertNotIn('removido: true', text)
        self.assertIn("creating test data through the product's own endpoints and keeping it for reuse", DEVELOPMENT)
        # redesenho, issue 3: "creates on demand ... which stay for reuse" saiu da etapa 6 do SKILL.md e vive em
        # browser-testing.md, "Test data the run creates"; o SKILL.md manda ler essa referência antes de cada passada
        self.assertIn('creates on demand the test data the `Fluxo:` needs to run completely, and keeps it for reuse',
                      section(REFERENCE, 'Test data the run creates'))
        self.assertIn('| references/browser-testing.md | before any pass;', skilltext.pointers())

    def test_the_evals_and_acceptance_follow(self):
        eval_text = flat(read('evals', 'test-data-and-summary-prints.md'))
        self.assertNotIn('removido', eval_text)
        self.assertIn('kept for reuse', eval_text)
        acceptance = flat(read('docs', 'acceptance.md'))
        self.assertNotIn('remova tudo e registre o resíduo', acceptance)
        self.assertIn('ANTES aberto no grilling', acceptance)


class DocsFollowTests(unittest.TestCase):
    def test_protocol_template_and_runbook_follow(self):
        self.assertIn('no fim, só a DEPOIS', flat(read('skills', 'frontlights', 'docs', 'protocol.md')))
        # redesenho, issue 6: o modelo da issue perdeu as instruções (a regra da janela vive em browser-testing.md);
        # fica o `Fluxo:` que a janela ANTES roda na base
        self.assertIn('- Fluxo:', read('skills', 'frontlights', 'templates', 'issue.md'))
        runbook = flat(read('evals', 'runbook.md'))
        self.assertIn('the ANTES window opens at the problem round', runbook)
        self.assertNotIn('Close the ANTES window early and confirm DEPOIS starts at once', runbook)
        self.assertIn('ANTES abre no grilling', flat(read('README.md')))


if __name__ == '__main__':
    unittest.main()
