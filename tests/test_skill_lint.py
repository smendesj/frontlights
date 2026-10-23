"""`scripts/skill_lint.py --shingles`: o relatório de duplicação dos textos da skill (redesenho, issue 10).

Seam: a linha de comando do script sobre uma pasta de skill inventada, e a função `report`. Só relata: sai com 0
com ou sem trechos repetidos.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'skill_lint.py'
sys.path.insert(0, str(SCRIPT.parent))
import skill_lint

RULE = ('A sessão coordenadora é uma só e apenas ela pergunta ao usuário, aprova, escreve no GitHub e grava a '
        'passagem de cada issue.')


class ShingleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'references').mkdir()
        (self.root / 'SKILL.md').write_text('# Skill\n\nNada repetido aqui.\n', encoding='utf-8')

    def write(self, name, text):
        (self.root / name).write_text(text, encoding='utf-8')

    def run_cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), '--shingles', '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8')
        return done.returncode, done.stdout

    def test_a_passage_in_two_files_is_reported_once_and_the_exit_is_zero(self):
        self.write('references/a.md', RULE + '\n')
        self.write('references/b.md', 'Antes disso. ' + RULE.replace('.', ',', 1) + '\n')
        code, out = self.run_cli('--json')
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['passages'][0]['file'], 'references/a.md')
        self.assertEqual(result['passages'][0]['also'], ['references/b.md:1'])
        self.assertGreaterEqual(result['passages'][0]['words'], 15)

    def test_nothing_repeated_still_exits_zero(self):
        self.write('references/a.md', RULE + '\n')
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn('Trechos repetidos de 15+ palavras: 0 (relatório, não bloqueia)', out)

    def test_backticks_code_blocks_and_paragraphs_do_not_count_by_default(self):
        command = 'Rode `frontlights.py open` ' + RULE
        self.write('references/a.md', command + '\n\n```\n' + RULE + '\n```\n')
        self.write('references/b.md', command + '\n')
        result = skill_lint.report(skill_lint.texts(self.root), self.root)
        self.assertEqual([p['also'] for p in result['passages']], [['references/b.md:1']])  # o trecho sem crase
        self.assertTrue(all('`' not in p['start'] for p in result['passages']))
        allowed = skill_lint.report(skill_lint.texts(self.root), self.root, allow_backticks=True)
        self.assertGreater(allowed['passages'][0]['words'], result['passages'][0]['words'])
        broken = 'Uma regra longa com palavras\n\nquebrada em dois parágrafos ' + RULE
        self.write('references/a.md', broken + '\n')
        self.write('references/b.md', 'Uma regra longa com palavras quebrada em dois parágrafos.\n')
        self.assertEqual(skill_lint.report(skill_lint.texts(self.root), self.root)['count'], 0)

    def test_the_licenses_are_left_out(self):
        self.write('references/LICENSE-a.md', RULE + '\n')
        self.write('references/LICENSE-b.md', RULE + '\n')
        self.assertEqual(skill_lint.report(skill_lint.texts(self.root), self.root)['count'], 0)

    def test_a_bad_minimum_is_a_usage_error(self):
        code, _ = self.run_cli('--min-words', '1')
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
