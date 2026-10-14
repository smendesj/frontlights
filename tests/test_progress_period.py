"""Período do resumo por instante e rascunho de outro período: a referência do resumo, o README, o protocolo e o
contrato dizem o mesmo que o `progress_report.py` faz.

Seam: o texto de `references/progress-report.md`, `README.md`, `docs/protocol.md`, `docs/roads-contract.md`,
`docs/acceptance.md`, `evals/runbook.md` e `examples/config.json`; o comportamento do script tem os próprios
testes em `test_progress_report.py` (`window` com `draftOtherPeriod`, `collect --start --end`).
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def flat(*parts):
    return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.reference = flat('skills', 'frontlights', 'references', 'progress-report.md')

    def test_the_period_is_the_window_with_its_instants(self):
        for phrase in ('from the exact instant the previous one ended',
                       'never from a midnight, a weekday or a date you choose',
                       'Run `collect --start <start> --end <end>` with the instants `window` printed',
                       '**The period is `window`\'s, never yours.**',
                       'run `window` again and use its new answer'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)
        self.assertNotIn('Run `collect --from <from> --to <to>`', self.reference)

    def test_a_draft_of_another_period_stops_and_asks(self):
        for phrase in ('**A draft of another period** (`draftOtherPeriod` true)', 'pushing this one would replace it',
                       '"Marquei como enviado agora" first', '"Parar aqui" second',
                       'Never collect or push while it is true'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_the_docs_tell_the_same_rule(self):
        self.assertIn('**Período de cada resumo.**', flat('README.md'))
        self.assertIn('o de quarta começa onde o de sexta terminou, e o de sexta onde o de quarta terminou', flat('README.md'))
        self.assertIn('`collect --start <start> --end <end>`', flat('skills', 'frontlights', 'docs', 'protocol.md'))
        contract = flat('docs', 'roads-contract.md')
        for phrase in ('**Corte por instante.**', 'nunca arredondado para a meia-noite', '`other_draft_pending`',
                       '`draftOtherPeriod`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)

    def test_the_example_collector_takes_the_instants(self):
        config = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))
        command = config['roadmapSync']['progress']['collectors'][0]['command']
        self.assertEqual(command[-4:], ['--start', '{start}', '--end', '{end}'])

    def test_acceptance_and_runbook_track_it_as_pending(self):
        self.assertIn('| 24. Período do resumo por instante | Pendente |', flat('docs', 'acceptance.md'))
        self.assertIn('24. Summary period by instant.', flat('evals', 'runbook.md'))


if __name__ == '__main__':
    unittest.main()
