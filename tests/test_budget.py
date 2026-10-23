"""Catraca de tamanho dos textos da skill (redesenho, issue 3).

development.md cresceu de 1.818 para 10.924 palavras em dez dias sem que nada o notasse. Aqui cada texto da skill tem
um orçamento: `BUDGET` é a contagem do dia em que o arquivo entrou na tabela (palavras separadas por espaço, como o
`wc -w`), e o arquivo pode passar dela em no máximo `SLACK` (10%), a folga de uma correção pequena. O número só desce:
quem encolhe um arquivo baixa o seu orçamento no mesmo commit; um arquivo novo entra na tabela com a sua contagem. O
`SKILL.md` tem teto próprio, sem folga, em `test_skill_md.py`.

Seam: o texto dos arquivos. Teste que só relata; nenhum hook o roda.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'

SLACK = 1.10

# contagem de 23/10/2026 (integração do redesenho, issue 3); só desce
BUDGET = {
    'SKILL.md': 1800,
    'docs/protocol.md': 6289,   # issue 7: "Quadro e publicação" vira registros e ponteiro
    'docs/security.md': 8112,   # issue 7: "Revisão e sobras"
    'references/browser-conductor.md': 821,
    'references/browser-testing.md': 4680,
    'references/closeout.md': 1305,
    'references/development.md': 11294,
    'references/grilling.md': 2871,
    'references/issue.md': 596,
    'references/issues.md': 2609,   # issue 7: etapa 5 por comando
    'references/LICENSE-pr.md': 279,
    'references/LICENSE-tdd.md': 198,
    'references/progress-report.md': 3797,
    'references/review.md': 753,
    'references/tdd-mocking.md': 202,
    'references/tdd-tests.md': 291,
    'templates/discovery.md': 339,
    'templates/grilling-section.html': 497,
    'templates/handoff.md': 729,
    'templates/issue.md': 1359,
    'templates/pr.md': 753,
}


def texts():
    files = [SKILL / 'SKILL.md', *SKILL.glob('references/*.md'), *SKILL.glob('docs/*.md'),
             *SKILL.glob('templates/*.md'), *SKILL.glob('templates/*.html')]
    return {p.relative_to(SKILL).as_posix(): p for p in files}


def words(path):
    return len(path.read_text(encoding='utf-8').split())


class BudgetTests(unittest.TestCase):
    def test_every_text_has_a_budget(self):
        self.assertEqual(sorted(set(texts()) - set(BUDGET)), [], 'arquivo novo: ponha a contagem dele em BUDGET')
        self.assertEqual(sorted(set(BUDGET) - set(texts())), [], 'arquivo apagado: tire a linha de BUDGET')

    def test_no_text_grows_past_its_budget(self):
        for name, path in sorted(texts().items()):
            if name not in BUDGET:
                continue
            with self.subTest(file=name):
                count = words(path)
                self.assertLessEqual(count, int(BUDGET[name] * SLACK),
                                     f'{name}: {count} palavras; orçamento {BUDGET[name]} (+10%)')


if __name__ == '__main__':
    unittest.main()
