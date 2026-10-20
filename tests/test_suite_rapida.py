"""Suíte rápida por variável de ambiente (issue 25, S1).

Seams: o runner por módulo (quantos testes o `unittest` carrega e roda, por nome e por `discover`, com e
sem `FRONTLIGHTS_SUITE=rapida`, e o motivo do pulo) e os manifestos de texto (a referência da etapa 6, o
README, o protocolo e a ausência de workflow de CI, issue 63). Nenhum teste aqui roda os módulos lentos de verdade: sem a
variável, só se conta o que o carregador carrega.
"""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIABLE = 'FRONTLIGHTS_SUITE'
SLOW_MODULES = ('tests.test_serve_ports', 'tests.test_checks_integration', 'tests.test_serve_preview')
# Quantos testes cada um carrega, no mínimo, sem a variável: a prova de que o pulo é só da suíte rápida.
MINIMUM_LOADED = {'tests.test_serve_ports': 100, 'tests.test_checks_integration': 100, 'tests.test_serve_preview': 10}

# Conta e nomeia o que o carregador carrega para cada módulo pedido, sem rodar nada.
COUNT_LOADED = r"""
import json, sys, unittest
loader = unittest.TestLoader()
result = {}
for name in sys.argv[1:]:
    tests = []
    def walk(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                walk(item)
            else:
                tests.append(item.id())
    walk(loader.loadTestsFromName(name))
    result[name] = {'count': len(tests), 'ids': tests[:3], 'errors': list(loader.errors)}
print(json.dumps(result))
"""


def environment(value):
    env = {key: val for key, val in os.environ.items() if key != VARIABLE}
    if value is not None:
        env[VARIABLE] = value
    return env


def run(args, value):
    return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=environment(value),
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)


def loaded(value):
    completed = run(['-c', COUNT_LOADED, *SLOW_MODULES], value)
    assert completed.returncode == 0, completed.stderr
    import json
    return json.loads(completed.stdout)


def marked(test, module):
    """Pré-condição barata: sem a marcação, o runner rodaria o módulo lento inteiro (minutos) só para falhar."""
    count = loaded('rapida')[module]['count']
    test.assertEqual(count, 1, f'{module} carrega {count} testes com {VARIABLE}=rapida: a marcação de pulo está '
                               'ausente, e a rodada do módulo inteiro não é disparada')


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def section(text, heading, next_heading):
    return ' '.join(text.split(heading)[1].split(next_heading)[0].split())


class FastSuiteRunnerTests(unittest.TestCase):
    """Seam: o runner por módulo."""

    def test_each_slow_module_is_one_skipped_test_by_name_with_the_variable(self):
        for module in SLOW_MODULES:
            with self.subTest(module=module):
                marked(self, module)
                completed = run(['-m', 'unittest', module, '-v'], 'rapida')
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn('Ran 1 test', completed.stderr)
                self.assertIn('OK (skipped=1)', completed.stderr)
                reason = re.search(r"skipped '([^']*)'", completed.stderr)
                self.assertIsNotNone(reason, completed.stderr)
                self.assertIn(f'{VARIABLE}=rapida', reason.group(1))
                self.assertIn(module.split('.')[-1], completed.stderr.split('skipped')[0])

    def test_each_slow_module_is_one_skipped_test_by_discover_with_the_variable(self):
        for module in SLOW_MODULES:
            with self.subTest(module=module):
                marked(self, module)
                pattern = module.split('.')[-1] + '.py'
                completed = run(['-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern, '-v'], 'rapida')
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn('Ran 1 test', completed.stderr)
                self.assertIn('OK (skipped=1)', completed.stderr)
                self.assertIn(f'{VARIABLE}=rapida', completed.stderr)

    def test_the_variable_loads_exactly_one_test_named_after_the_module(self):
        result = loaded('rapida')
        for module in SLOW_MODULES:
            with self.subTest(module=module):
                self.assertEqual(result[module]['count'], 1, result[module])
                self.assertEqual(result[module]['errors'], [])
                self.assertIn(module.split('.')[-1], result[module]['ids'][0])

    def test_without_the_variable_the_same_tests_load_as_with_any_other_value(self):
        absent = loaded(None)
        other = loaded('completa')
        for module in SLOW_MODULES:
            with self.subTest(module=module):
                self.assertGreater(absent[module]['count'], MINIMUM_LOADED[module], absent[module])
                self.assertEqual(absent[module]['count'], other[module]['count'])
                self.assertEqual(absent[module]['errors'], [])
                self.assertEqual(other[module]['errors'], [])
                for ids in (absent[module]['ids'], other[module]['ids']):
                    self.assertFalse(any('ModuloPulado' in test_id for test_id in ids), ids)


class FastSuiteTextTests(unittest.TestCase):
    """Seam: os manifestos de texto."""

    def test_the_repository_has_no_ci_workflow(self):
        # Decisão de 20/10/2026: nenhuma conferência inteira é exigida; a suíte inteira roda à mão, a pedido.
        self.assertFalse(ROOT.joinpath('.github', 'workflows', 'tests.yml').exists())
        self.assertFalse(ROOT.joinpath('.github').exists())

    def test_the_stage_six_reference_says_when_each_run_is_used(self):
        text = section(read('skills', 'frontlights', 'references', 'development.md'),
                       '## Slices in order', '## Dispatch and ownership')
        for phrase in ('**Which tests run when.**',
                       'TDD per slice is the default practice',
                       'plus the test modules the slice touches and the type checks',
                       'These tests are evidence, never a gate: no suite holds back the merge into the local main or '
                       'the release.',
                       'When the user asks to implement "só com teste assistido", the session writes and runs no tests '
                       'in that run',
                       'A broader suite runs only when the user asks for one, through the optional tools',
                       'homolog suite --root <issue-worktree> --config <config> --issue <n> --mode impact|full --base <base>',
                       'judged by `homolog suite-gate`',
                       '`--impact <base>` runs only what the diff touches, by the selection of `tests/pre_commit.py`',
                       f'`{VARIABLE}=rapida`, Windows only, it skips the modules that start real processes and ports',
                       '`python -m unittest discover -s tests -v` for the whole',
                       'a red one is a finding',
                       "No whole check is required anywhere: a project's CI, when there is one, is neither expected "
                       'nor a gate, and the watched run of each issue is the evidence.'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for old in ('with or without CI in the project', 'The CI of this repository stays the full check',
                    "Per issue, the gate is the project's impact suite", 'the only whole check',
                    '"Rodar a suíte inteira desta vez"'):
            with self.subTest(old=old):
                self.assertNotIn(old, text)

    def test_the_release_requires_no_suite(self):
        # "The release" é a última seção da referência da etapa 6.
        text = flat('skills', 'frontlights', 'references', 'development.md').split('## The release')[1]
        self.assertIn('No suite is required for the release (no whole check is: the watched run of each issue is its '
                      'evidence)', text)
        self.assertIn('runs only when the user asks for it', text)
        self.assertNotIn("This run is the release's only whole check", text)
        self.assertNotIn("The CI of the release's pull request stays the full check", text)

    def test_the_readme_documents_the_variable_and_the_rule(self):
        text = flat('README.md')
        for phrase in (f'{VARIABLE}=rapida', '`tests.test_serve_ports`', '`tests.test_checks_integration`',
                       'pulado com o motivo', 'qualquer outro valor, ou a ausência dela, roda tudo',
                       'o TDD de cada slice é a prática padrão e nenhuma suíte é portão: nem no merge na main local, '
                       'nem na release',
                       'nenhuma conferência inteira é exigida (a CI de um projeto, quando houver, não é esperada nem é '
                       'portão)',
                       'Este repositório não tem workflow de CI', '`tests.test_serve_preview`',
                       'os seis sensíveis'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for old in ('com ou sem CI no projeto', 'A CI do GitHub'):
            with self.subTest(old=old):
                self.assertNotIn(old, text)
        self.assertIn('python -m unittest discover -s tests -v', read('README.md'))

    def test_the_protocol_documents_the_rule(self):
        text = flat('skills', 'frontlights', 'docs', 'protocol.md')
        for phrase in (f'`{VARIABLE}=rapida`', 'os módulos que ela toca',
                       'Esses testes são evidência, nunca portão: nenhuma suíte segura o merge na main local nem a '
                       'release.',
                       'são ferramentas opcionais, rodadas só a pedido do usuário',
                       'nenhuma conferência inteira é exigida, e a CI de um projeto, quando houver, não é esperada nem '
                       'é portão'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for old in ('com ou sem CI no projeto', 'A CI do GitHub'):
            with self.subTest(old=old):
                self.assertNotIn(old, text)


if __name__ == '__main__':
    unittest.main()
