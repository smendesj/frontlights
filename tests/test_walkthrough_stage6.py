"""Na etapa 6 o roteiro confirma cada caixa (issue 65, fatia S4).

Com tela, o teste assistido percorre os roteiros das caixas, na ordem do `Fluxo:`, e o "Aprovado" confirma cada
caixa percorrida. Sem tela (`browser-gate` `not_needed`), rodar o roteiro de cada caixa é condição do merge na main
local, sem pergunta nova: um `.md` por caixa em `.frontlights/issues/<n>/walkthroughs/S<k>.md` e a tabela-resumo
no handoff. O formato do roteiro vive em `references/issues.md`; a regra do merge, só em `references/development.md`.

Seam: o texto de `references/development.md`, `references/browser-testing.md` e `templates/handoff.md`, lido por
seção e achatado pelos espaços, como nos outros testes de texto.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return SKILL.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(rf'^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return flat(match.group(1)) if match else ''


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.text = read('references', 'development.md')

    def test_into_the_local_main_requires_the_walkthroughs_without_a_screen(self):
        local = section(self.text, 'Into the local main')
        step = '**Without a screen, the walkthroughs.**'
        self.assertIn(step, local)
        self.assertLess(local.index('**The gate, the watched run.**'), local.index(step))
        self.assertLess(local.index(step), local.index('**The check and the merge.**'))
        rule = local.split(step)[1].split('**The check and the merge.**')[0]
        for phrase in ('`not_needed`',
                       'is a condition of the merge into the local main, with no new question',
                       '`.frontlights/issues/<n>/walkthroughs/S<k>.md`',
                       '`## Antes`', '`## Depois`', 'code block', 'masked',
                       'the issue, the box, the persona, the date', 'the base and the commit it ran on',
                       '`references/issues.md`',
                       'the handoff'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        # sem o arquivo de uma caixa, nada de merge; e nenhuma pergunta nova sai daqui
        self.assertIn('a box without its file keeps the issue out of the local main', rule)
        self.assertNotIn('AskUserQuestion', rule)

    def test_the_record_step_carries_the_walkthroughs(self):
        local = section(self.text, 'Into the local main')
        record = local.split('**Record it.**')[1]
        self.assertIn('the walkthroughs run without a screen', record)

    def test_slices_in_order_runs_the_walkthrough_before_the_tick(self):
        slices = section(self.text, 'Slices in order')
        for phrase in ('runs the walkthrough of its box', 'the `.md` is the evidence of the tick',
                       'waits for the "Aprovado" of the watched run'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, slices)
        self.assertLess(slices.index('runs the walkthrough of its box'), slices.index('then comes the tick of its box'))

    def test_the_report_lists_the_walkthroughs(self):
        review = section(self.text, 'Review, checkpoints and renewal')
        report = review.split("Report each issue's state")[1]
        self.assertIn('the walkthroughs run without a screen', report)
        self.assertLess(report.index('the watched run'), report.index('the walkthroughs run without a screen'))


class BrowserTestingTests(unittest.TestCase):
    def setUp(self):
        self.text = read('references', 'browser-testing.md')

    def test_the_flow_is_the_order_of_the_walkthroughs(self):
        plan = section(self.text, 'What the plan turns on')
        self.assertIn('`Fluxo:` the order in which the watched run walks the walkthroughs of the boxes', plan)
        self.assertIn('`references/issues.md`', plan)

    def test_approved_confirms_each_box_walked(self):
        run = section(self.text, 'Watched run: before and after, with the user watching')
        approved = run.split('- "Aprovado":')[1].split('- "Precisa de alteração":')[0]
        for phrase in ('confirms each box whose walkthrough the run walked',
                       'the evidence of the tick of that box'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, approved)
        go_on = run.split('- "Pode prosseguir":')[1]
        self.assertIn('confirms no box', go_on)

    def test_the_walkthrough_format_is_not_copied_here(self):
        flat_text = flat(self.text)
        self.assertNotIn('`## Antes`', flat_text)
        self.assertNotIn('walkthroughs/S<k>.md', flat_text)


class HandoffTests(unittest.TestCase):
    def test_the_handoff_has_the_walkthrough_table(self):
        text = read('templates', 'handoff.md')
        self.assertIn('Roteiros rodados sem tela', text)
        self.assertIn('| Caixa | Antes | Depois | Arquivo |', text)
        self.assertIn('`.frontlights/issues/<n>/walkthroughs/S<k>.md`', text)


if __name__ == '__main__':
    unittest.main()
