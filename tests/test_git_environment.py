"""D8 (teste real contra o GitHub): um `git fetch` dos scripts ficou preso no seletor de conta do Git Credential
Manager. Todo subprocess de git dos scripts roda com `GIT_TERMINAL_PROMPT=0` e `GCM_INTERACTIVE=never`, vindos de um
ponto só, `_cli.git_environment`.

Seams: `_cli.git_environment`, os helpers de git de cada script (comportamento, com `subprocess.run` simulado) e o
texto dos scripts (toda chamada de git passa `env=`; o nome das variáveis só aparece em `_cli.py`).
"""
import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import _cli  # noqa: E402
import cleanup  # noqa: E402
import frontlights  # noqa: E402
import homolog  # noqa: E402
import serve  # noqa: E402

WANTED = {'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
CALLS = {'run', 'Popen', 'check_output', 'check_call', 'call'}


def git_calls(tree):
    """The subprocess calls whose argv is a list literal that starts with 'git' (or the `executable` serve finds)."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess' and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.List) and first.elts:
            head = first.elts[0]
            if (isinstance(head, ast.Constant) and head.value == 'git') or (
                    isinstance(head, ast.Name) and head.id == 'executable'):
                yield node


class GitEnvironmentTests(unittest.TestCase):
    def test_the_common_environment_never_prompts(self):
        environment = _cli.git_environment()
        for name, value in WANTED.items():
            self.assertEqual(environment.get(name), value)
        self.assertEqual(_cli.git_environment({'A': '1'}), {'A': '1', **WANTED})

    def test_every_git_subprocess_of_the_scripts_passes_env(self):
        missing = []
        for path in sorted(SCRIPTS.glob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for call in git_calls(tree):
                if not any(k.arg == 'env' for k in call.keywords):
                    missing.append(f'{path.name}:{call.lineno}')
        self.assertEqual(missing, [])

    def test_the_variables_are_named_only_in_cli(self):
        named = [p.name for p in sorted(SCRIPTS.glob('*.py')) if p.name != '_cli.py'
                 and any(n in p.read_text(encoding='utf-8') for n in WANTED)]
        self.assertEqual(named, [])

    def test_the_git_helpers_run_with_the_common_environment(self):
        seen = []

        def fake(argv, **options):
            seen.append(options.get('env') or {})
            return subprocess.CompletedProcess(argv, 0, '', '')
        helpers = [lambda: homolog.git('.', 'status'), lambda: frontlights.git_call('.', 'status'),
                   lambda: cleanup.git('.', 'status'), lambda: serve.git('.', 'status'),
                   lambda: _cli.git_line('.', 'status')]
        with mock.patch('subprocess.run', fake):
            for helper in helpers:
                helper()
        self.assertEqual(len(seen), len(helpers))
        for environment in seen:
            self.assertEqual({k: environment.get(k) for k in WANTED}, WANTED)


if __name__ == '__main__':
    unittest.main()
