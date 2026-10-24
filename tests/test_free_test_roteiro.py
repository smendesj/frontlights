"""Teste livre guiado e sem pedir ao usuário que suba o ambiente (GeoCloud #1124, 23/10/2026).

(a) `frontlights.py artifact roteiro --content <arquivo>` acrescenta a última seção do artefato, "Roteiro do teste
livre": um grupo por critério ou correção (`## <título>`, `Conta:` opcional, passos `- `, uma linha `Esperado:`); uma
segunda chamada substitui a seção; uma seção numerada nova entra antes dela; recusa grupo sem passo ou sem Esperado,
estilo inline e senha.
(b) A regra do teste livre manda escrever o roteiro antes da janela e a sessão subir API e web sozinha.

Seam: a CLI do artefato numa pasta temporária e o texto da skill.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
SCRIPT = SKILL / 'scripts' / 'frontlights.py'

ROTEIRO = """## S1 Catálogo mostra chaves sem autor
Conta: conta1
- Abra Configurações > Perfis > Acesso
- Procure a chave `Relatórios`
Esperado: a chave aparece na lista

## Correção do teste livre: menu vazio
- Abra Usuários
Esperado: o menu some na linha alheia
"""

SECTION = """## Visual
Um fluxo.
## Cenário por opção
- **A**: faz A
## Consequências
- **A**: custa pouco
"""


def flat(text):
    return ' '.join(text.split())


class RoteiroCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / '.frontlights' / 'issues' / '9' / 'artifact.html'
        self.assertEqual(self.cli('init', '--issue', '9', '--kind', 'fluxo')[0], 0)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        done = subprocess.run([sys.executable, str(SCRIPT), 'artifact', *argv, '--root', str(self.root)],
                              capture_output=True, encoding='utf-8', timeout=60)
        return done.returncode, json.loads(done.stdout)

    def file(self, text, name='roteiro.md'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return str(path)

    def roteiro(self, text=ROTEIRO):
        return self.cli('roteiro', '--issue', '9', '--content', self.file(text))

    def test_the_roteiro_is_the_last_section_with_steps_and_expected(self):
        code, out = self.roteiro()
        self.assertEqual((code, out['groups'], out['publish']['file_path']), (0, 2, str(self.source)))
        page = self.source.read_text(encoding='utf-8')
        self.assertLess(page.index('id="secao-1"'), page.index('id="roteiro"'))
        self.assertLess(page.index('id="roteiro"'), page.rindex('<!-- /secoes -->'))
        for piece in ('Roteiro do teste livre', '<li>Procure a chave <code>Relatórios</code></li>', 'Conta: conta1',
                      '<strong>Esperado:</strong> a chave aparece na lista', 'Correção do teste livre: menu vazio'):
            self.assertIn(piece, page)

    def test_a_second_call_replaces_it_and_a_new_section_goes_before_it(self):
        self.roteiro()
        self.roteiro('## S2 Outro\n- passo\nEsperado: algo\n')
        code, _ = self.cli('section', '--issue', '9', '--n', '2', '--kind', 'fluxo', '--title', 'Qual?',
                           '--option', 'A', '--content', self.file(SECTION, 'secao.md'))
        self.assertEqual(code, 0)
        page = self.source.read_text(encoding='utf-8')
        self.assertEqual(page.count('id="roteiro"'), 1)
        self.assertNotIn('Catálogo mostra', page)
        self.assertLess(page.index('id="secao-2"'), page.index('id="roteiro"'))

    def test_refusals(self):
        for text, reason in (('## S1\nEsperado: x\n', 'roteiro_incomplete'), ('## S1\n- passo\n', 'roteiro_incomplete'),
                             ('sem grupo\n', 'roteiro_empty'), ('## S1\n- <p style="x">a</p>\nEsperado: b\n', 'inline_style'),
                             ('## S1\n- entre com senha: 123\nEsperado: b\n', 'secret')):
            with self.subTest(reason=reason, text=text):
                code, out = self.roteiro(text)
                self.assertEqual((code, out['reason']), (1, reason))


class FreeTestRuleTests(unittest.TestCase):
    def test_the_free_test_writes_the_roteiro_and_brings_the_product_up(self):
        development = flat((SKILL / 'references' / 'development.md').read_text(encoding='utf-8'))
        for phrase in ('the session brings the API and the web of the main worktree up itself, never asking the user to',
                       '`frontlights.py artifact roteiro --issue <n> --content <file>` adds the last section of the artifact',
                       'each free-test fix adds its group', 'with the link to the roteiro'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)
        testing = flat((SKILL / 'references' / 'browser-testing.md').read_text(encoding='utf-8'))
        self.assertIn('never asks the user to bring them up', testing)
        self.assertNotIn('is asked to bring it up', testing)


class TwoConfirmationsTests(unittest.TestCase):
    # 23/10/2026: o ANTES que não reproduzia o problema não parava nada
    def test_each_end_is_confirmed_by_code_and_by_screen(self):
        testing = flat((SKILL / 'references' / 'browser-testing.md').read_text(encoding='utf-8'))
        for phrase in ('**Two confirmations, code and screen.**', 'by code (red at the base, green on the branch of the issue)',
                       'by screen (ANTES shows the defect, DEPOIS shows it fixed)',
                       'an ANTES that does not reproduce it becomes a question before any code for that criterion',
                       'a green test never stands in for it'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, testing)


if __name__ == '__main__':
    unittest.main()
