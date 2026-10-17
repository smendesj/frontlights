"""Fonte única das regras da etapa 6 e descrição curta da skill (refatoração dos textos, melhorias 4 e 6).

Cada regra que a etapa 6 aplica (os merges cobertos, as operações negadas, os três portões, a pergunta da release)
vive num lugar só, `references/development.md`; os outros textos (SKILL.md, docs, README, CLAUDE.md) apontam para
ela. Uma cópia literal num segundo arquivo volta a ser pega aqui. A descrição do frontmatter, carregada em toda
sessão de todo projeto, fica curta: diz o que a skill é e traz os gatilhos.

Seam: o texto dos arquivos, achatado pelos espaços (`flat`), como nos outros testes de texto.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / 'skills' / 'frontlights'
SOURCE = SKILL_DIR / 'references' / 'development.md'
FILES = sorted(SKILL_DIR.rglob('*.md')) + [ROOT / 'README.md', ROOT / 'CLAUDE.md']

# fragmento que só a fonte pode ter -> o que ele marca
SINGLE = {
    'into the local main by `homolog sync`': 'a lista dos merges cobertos',
    'turning on a setting, key or flag in production': 'a lista das operações negadas',
    '`{"full_suite": "green", "review_gate": "current", "browser_gate": "answered"}`': 'os três portões',
    'Lançar a release com as issues': 'a pergunta da release',
    '"Mesclar a PR #<n> em <base>?"': 'a pergunta do merge da release',
    '"Dar destino pela escada"': 'a pergunta do limite de rodadas da revisão',
}

# cópias em português que deram lugar a um ponteiro
GONE = {
    'chave ou flag em produção': 'a lista das negadas copiada em português',
    'na branch da prévia pelo `serve preview refresh`': 'a lista dos merges cobertos copiada em português',
    '`review-gate` `current` for it': 'os portões repetidos fora da fonte',
    '`review-gate` em dia e `browser-gate` respondido': 'os portões repetidos em português',
}

DESCRIPTION_MAX_WORDS = 80


def flat(text):
    return ' '.join(text.split())


def texts():
    return {path: flat(path.read_text(encoding='utf-8')) for path in FILES if path.exists()}


class SingleSourceTests(unittest.TestCase):
    def test_each_rule_lives_once_in_development(self):
        found = texts()
        for fragment, rule in SINGLE.items():
            with self.subTest(rule=rule):
                homes = {path.relative_to(ROOT).as_posix(): text.count(fragment)
                         for path, text in found.items() if fragment in text}
                self.assertEqual(homes, {SOURCE.relative_to(ROOT).as_posix(): 1},
                                 f'{rule} deve aparecer uma vez, só em references/development.md')

    def test_portuguese_copies_point_to_the_source(self):
        found = texts()
        for fragment, copy in GONE.items():
            with self.subTest(copy=copy):
                homes = [path.relative_to(ROOT).as_posix() for path, text in found.items() if fragment in text]
                self.assertEqual(homes, [], f'{copy} deve virar um ponteiro para references/development.md')


class DescriptionTests(unittest.TestCase):
    def test_description_is_short_and_keeps_the_triggers(self):
        front = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8').split('---')[1]
        match = re.search(r'^description: (.*)$', front, re.M)
        self.assertIsNotNone(match)
        description = match.group(1)
        self.assertLessEqual(len(description.split()), DESCRIPTION_MAX_WORDS)
        for trigger in ('frontlights, ataque a issue', 'ativar frontlights', 'with or without the slash',
                        'not a session or project of the same name'):
            self.assertIn(trigger, description)


if __name__ == '__main__':
    unittest.main()
