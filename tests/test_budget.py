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

# contagem de 23/10/2026, no fim do redesenho (issue 10): cada arquivo com a sua contagem do dia; só desce
BUDGET = {
    'SKILL.md': 1999,  # teto sem folga em test_skill_md (CEILING)
    'docs/protocol.md': 2943,
    'docs/roads-contract.md': 2554,  # entrou na skill na issue 10 do redesenho
    'docs/security.md': 3743,
    'references/LICENSE-pr.md': 279,
    'references/LICENSE-tdd.md': 206,
    'references/browser-conductor.md': 821,
    'references/browser-testing.md': 4680,
    'references/closeout.md': 1305,
    'references/development.md': 4126,
    'references/family.md': 2126,
    'references/grilling.md': 1893,
    'references/issue.md': 360,
    'references/issues.md': 2616,
    'references/progress-report.md': 2325,
    'references/retro.md': 417,
    'references/review.md': 991,
    'references/setup.md': 181,
    'references/tdd.md': 1274,
    'references/worker.md': 526,
    'templates/artifact-page.html': 444,
    'templates/discovery.md': 292,
    'templates/grilling-section.html': 244,
    'templates/handoff.md': 259,
    'templates/issue.md': 775,
    'templates/pr.md': 374,
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
