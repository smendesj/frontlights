"""Verificação de antes do commit no repositório do Frontlights (`tests/pre_commit.py`), sem hook.

Seam: a linha de comando de `tests/pre_commit.py` (`--root`, `--timeout`, `--workers`), observada por subprocess
sobre um repositório Git temporário que o próprio teste monta, com `skills/frontlights/scripts`, um documento e
módulos de teste falsos: o que sai no stdout (os arquivos mudados, uma linha por módulo, o comando para rodar
sozinho o que falhou, o que ficou para a suíte inteira) e o código de saída. Os módulos falsos gravam a variável
`FRONTLIGHTS_SUITE` que receberam. Mais os manifestos de texto: `CLAUDE.md` e o `README.md` citam o comando.
Nada aqui roda a suíte real.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = ROOT / 'tests' / 'pre_commit.py'
VARIABLE = 'FRONTLIGHTS_SUITE'

CITES_DOC = """
import unittest
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / 'docs' / 'guia.md'


class Guia(unittest.TestCase):
    def test_a_frase_continua_no_guia(self):
        self.assertIn('frase conferida', DOC.read_text(encoding='utf-8'))
"""

UNRELATED = """
import unittest


class Outro(unittest.TestCase):
    def test_nada_a_ver(self):
        self.assertTrue(True)
"""

RECORDS_VARIABLE = """
import os
import unittest
from pathlib import Path


class Variavel(unittest.TestCase):
    def test_grava_a_variavel(self):
        # guia.md: citado para ser acionado quando o documento muda
        target = Path(__file__).resolve().parents[1] / 'variavel.txt'
        target.write_text(os.environ.get('FRONTLIGHTS_SUITE', '<ausente>'), encoding='utf-8')
"""

MIXED = """
'''Um módulo misto: o docstring cita guia.md, mas só descreve.'''
import unittest
from pathlib import Path


class Texto(unittest.TestCase):
    def test_le_o_guia(self):
        doc = Path(__file__).resolve().parents[1] / 'docs' / 'guia.md'
        self.assertTrue(doc.read_text(encoding='utf-8'))


class TextoPesado(unittest.TestCase):
    def test_que_nao_cita_o_guia(self):
        self.fail('a classe que nao cita o documento nao devia rodar')
"""

IMPORTS_SCRIPT = """
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import ferramenta


class Ferramenta(unittest.TestCase):
    def test_o_valor(self):
        self.assertEqual(ferramenta.VALOR, 1)
"""

IMPORTS_IN_CLASS = """
import importlib
import sys
import unittest
from pathlib import Path

PASTA = ('skills', 'ferramenta')  # uma string solta igual ao nome do script não é carga


class SemImport(unittest.TestCase):
    def test_que_falha_se_rodar(self):
        self.fail('a classe que so tem a string ferramenta solta nao devia rodar: ' + 'ferramenta')


class ComImport(unittest.TestCase):
    def test_carrega(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
        self.assertEqual(importlib.import_module('ferramenta').VALOR, 1)
"""

DOCSTRING_ONLY = """
'''Este módulo só descreve o guia.md no docstring.'''
import unittest


class Nada(unittest.TestCase):
    def test_falha_se_rodar(self):
        self.fail('um docstring nao aciona o modulo')
"""

SLOW = """
import time
import unittest


class Lento(unittest.TestCase):
    def test_demora(self):
        # guia.md: citado para ser acionado quando o documento muda
        time.sleep(60)
"""


def utf8_env(**extra):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    env.pop(VARIABLE, None)
    env.update(extra)
    return env


class RepositoryCase(unittest.TestCase):
    """Base: um repositório Git temporário com um script, um documento e os módulos pedidos, já commitados."""

    MODULES = {'test_guia': CITES_DOC, 'test_outro': UNRELATED}

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='frontlights-pre-commit-'))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = self.base / 'repo'
        self.env = utf8_env(GIT_CONFIG_GLOBAL=str(self.base / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                            GIT_TERMINAL_PROMPT='0')
        (self.base / 'gitconfig').write_text('', encoding='utf-8')
        self.write('skills/frontlights/scripts/ferramenta.py', 'VALOR = 1\n')
        self.write('docs/guia.md', 'Uma frase conferida pelo teste.\n')
        for name, source in self.MODULES.items():
            self.write(f'tests/{name}.py', source)
        self.git('init', '-q', '-b', 'main')
        for key, value in (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'),
                           ('commit.gpgsign', 'false')):
            self.git('config', key, value)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip('\n'), encoding='utf-8')

    def git(self, *args):
        done = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', env=self.env, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(done.returncode, 0, f'git {" ".join(args)}: {done.stderr}')
        return done

    def run_pre_commit(self, *args, root=None):
        started = time.monotonic()
        done = subprocess.run([sys.executable, str(PRE_COMMIT), '--root', str(root or self.root), *args],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', env=self.env,
                              stdin=subprocess.DEVNULL, timeout=120)
        return done, time.monotonic() - started


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class SelectionTest(RepositoryCase):
    def test_a_changed_document_runs_only_the_modules_that_cite_it(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('docs/guia.md', done.stdout)
        self.assertIn('test_guia', done.stdout)
        self.assertNotIn('test_outro', done.stdout)

    def test_an_untracked_test_module_runs(self):
        self.write('tests/test_novo.py', UNRELATED)
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('test_novo', done.stdout)
        self.assertNotIn('test_guia', done.stdout)

    def test_a_staged_change_counts_too(self):
        self.write('docs/guia.md', 'Uma frase conferida, no índice.\n')
        self.git('add', 'docs/guia.md')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('test_guia', done.stdout)

    def test_no_change_runs_nothing_and_exits_zero(self):
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('Nenhum arquivo mudado', done.stdout)
        self.assertNotIn('test_guia', done.stdout)

    def test_outside_a_git_repository_exits_two(self):
        loose = self.base / 'solta'
        loose.mkdir()
        done, _ = self.run_pre_commit(root=loose)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class FailureTest(RepositoryCase):
    def test_a_red_module_exits_one_with_the_command_to_run_it_alone(self):
        self.write('docs/guia.md', 'O texto perdeu a frase.\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('test_guia', done.stdout)
        self.assertIn('Rode sozinho:', done.stdout)
        self.assertIn('-p test_guia.py', done.stdout)

    def test_a_syntax_error_in_a_script_exits_one(self):
        self.write('skills/frontlights/scripts/ferramenta.py', 'def quebrado(:\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('compileall', done.stdout)

    def test_a_module_that_does_not_import_exits_one(self):
        self.write('tests/test_outro.py', 'import modulo_que_nao_existe\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('test_outro', done.stdout)


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class VariableTest(RepositoryCase):
    MODULES = {'test_variavel': RECORDS_VARIABLE}

    def test_the_modules_run_with_the_fast_suite_variable(self):
        self.write('docs/guia.md', 'Outra frase.\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.root / 'variavel.txt').read_text(encoding='utf-8'), 'rapida')


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class ClassSelectionTest(RepositoryCase):
    MODULES = {'test_guia': CITES_DOC, 'test_misto': MIXED, 'test_docstring': DOCSTRING_ONLY}

    def test_only_the_classes_that_cite_the_file_run_when_the_module_did_not_change(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r'test_misto .*\(Texto\)')
        self.assertNotIn('TextoPesado', done.stdout)

    def test_a_citation_outside_a_test_class_runs_the_whole_module(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, _ = self.run_pre_commit()
        guia = [line for line in done.stdout.splitlines() if 'test_guia' in line]
        self.assertTrue(guia, done.stdout)
        self.assertTrue(all('(' not in line for line in guia), guia)

    def test_a_citation_only_in_the_module_docstring_runs_nothing_there(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, _ = self.run_pre_commit()
        self.assertNotIn('test_docstring', done.stdout)

    def test_a_changed_module_runs_whole(self):
        self.write('tests/test_misto.py', MIXED + '\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('TextoPesado', done.stdout)


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class ImportTest(RepositoryCase):
    MODULES = {'test_ferramenta': IMPORTS_SCRIPT, 'test_dentro': IMPORTS_IN_CLASS, 'test_outro': UNRELATED}

    def test_a_changed_script_runs_the_modules_that_import_it(self):
        self.write('skills/frontlights/scripts/ferramenta.py', 'VALOR = 2\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('test_ferramenta', done.stdout)
        self.assertNotIn('test_outro', done.stdout)

    def test_a_loader_call_in_a_class_runs_only_it_and_a_loose_string_runs_nothing(self):
        self.write('skills/frontlights/scripts/ferramenta.py', 'VALOR = 1  # editado\n')
        done, _ = self.run_pre_commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r'test_dentro .*\(ComImport\)')
        self.assertNotIn('SemImport', done.stdout)


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class RenameTest(RepositoryCase):
    def test_a_renamed_file_counts_by_its_new_name(self):
        self.git('mv', 'docs/guia.md', 'docs/guia2.md')
        done, _ = self.run_pre_commit()
        self.assertIn('Mudados (1): docs/guia2.md', done.stdout, done.stdout + done.stderr)


@unittest.skipUnless(os.name == 'nt', 'o comando reaproveita o runner de tests/suite.py, que só roda no Windows')
class DeadlineTest(RepositoryCase):
    MODULES = {'test_guia': CITES_DOC, 'test_lento': SLOW, 'test_lento2': SLOW}

    def test_a_slow_module_is_left_to_the_whole_suite_without_failing(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, wall = self.run_pre_commit('--timeout', '12')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('fica para a suíte inteira', done.stdout)
        self.assertLess(wall, 30, done.stdout)
        guia = [line for line in done.stdout.splitlines() if 'test_guia' in line]
        self.assertTrue(any('OK' in line for line in guia), done.stdout)

    def test_a_module_that_never_started_is_said_so(self):
        self.write('docs/guia.md', 'Uma frase conferida pelo teste, editada.\n')
        done, wall = self.run_pre_commit('--timeout', '3', '--workers', '1')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('não começou', done.stdout)
        self.assertLess(wall, 30, done.stdout)


class DocumentationTest(unittest.TestCase):
    def test_claude_md_asks_for_the_command_before_every_commit(self):
        text = ' '.join((ROOT / 'CLAUDE.md').read_text(encoding='utf-8').split())
        self.assertIn('Antes de cada commit, rode `python tests/pre_commit.py`', text)
        self.assertIn('nenhum hook o roda', text)

    def test_the_readme_development_section_cites_the_command(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        section = ' '.join(text.split('## Para quem desenvolve o Frontlights')[1].split('\n## ')[0].split())
        self.assertIn('python tests/pre_commit.py', section)
        self.assertIn('fica para a suíte inteira', section)
        self.assertIn('nenhum hook o roda', section)


if __name__ == '__main__':
    unittest.main()
