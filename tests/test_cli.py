"""Base dos scripts (redesenho, issue 1, S1): `scripts/_cli.py` deduz raiz, árvore, config e issue, devolve o erro de
uso em JSON com `hint` e reconfigura a saída em UTF-8 em todo `main`.

Seam: as funções de `_cli` sobre repositórios Git temporários (gitfixture, worktrees criadas no teste) e os scripts
por subprocesso, rodados de dentro de uma worktree de issue sem `--root`, `--config` nem `--issue`.
Só dados de teste: nenhum projeto real, nenhum caminho de máquina.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _cli  # noqa: E402
import gitfixture  # noqa: E402


def build(folder):
    repo = gitfixture.init(Path(folder) / 'main')
    (repo / 'README.md').write_text('fixture\n', encoding='utf-8')
    gitfixture.git(repo, 'add', '-A')
    gitfixture.git(repo, 'commit', '-q', '-m', 'base')


def same(a, b):
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.main = gitfixture.copy(self.template, self.base / 'repo') / 'main'
        self.tree = self.base / 'wt-issue-7'
        gitfixture.git(self.main, 'worktree', 'add', '-q', '-b', 'sergio/issue-7', str(self.tree))
        self.other = self.base / 'wt-solta'
        gitfixture.git(self.main, 'worktree', 'add', '-q', '-b', 'sergio/solta', str(self.other))
        folder = self.main / '.frontlights'
        folder.mkdir()
        (folder / 'config.json').write_text(json.dumps({'repository': None}), encoding='utf-8')
        charter = {'issue_ids': [7, 9], 'branch_prefix': 'sergio/',
                   'worktrees': [{'issue': 7, 'path': str(self.tree), 'branch': 'sergio/issue-7', 'ownership': ['src']},
                                 {'direct': 'melhoria-x', 'path': str(self.base / 'wt-direta'),
                                  'branch': 'sergio/melhoria-x', 'ownership': ['docs']}]}
        (folder / 'authorization.json').write_text(json.dumps(charter), encoding='utf-8')


class DefaultsTests(Fixture):
    def test_root_is_the_main_worktree_and_tree_the_one_of_the_cwd(self):
        self.assertTrue(same(_cli.main_worktree(self.tree), self.main))
        self.assertTrue(same(_cli.main_worktree(self.main), self.main))
        self.assertTrue(same(_cli.current_tree(self.tree / '.'), self.tree))

    def test_outside_git_both_are_the_folder_itself(self):
        with tempfile.TemporaryDirectory() as loose:
            self.assertTrue(same(_cli.main_worktree(loose), loose))
            self.assertTrue(same(_cli.current_tree(loose), loose))

    def test_config_defaults_to_the_main_worktree(self):
        self.assertTrue(same(_cli.config_path(None, self.main), self.main / '.frontlights' / 'config.json'))
        self.assertEqual(_cli.config_path('outro.json', self.main), 'outro.json')

    def test_missing_config_is_refused_with_a_hint_or_left_out_when_optional(self):
        (self.main / '.frontlights' / 'config.json').unlink()
        with self.assertRaises(_cli.UsageError) as caught:
            _cli.config_path(None, self.main)
        self.assertIn('--config', caught.exception.hint)
        self.assertIsNone(_cli.config_path(None, self.main, required=False))

    def test_issue_comes_from_the_charter_entry_of_the_tree(self):
        self.assertEqual(_cli.issue_number(None, self.tree, self.main), 7)
        self.assertEqual(_cli.issue_number('12', self.other, self.main), 12)

    def test_a_tree_outside_the_charter_is_refused_with_the_open_issues(self):
        with self.assertRaises(_cli.UsageError) as caught:
            _cli.issue_number(None, self.other, self.main)
        self.assertIn('--issue', caught.exception.hint)
        self.assertIn('7, 9', caught.exception.hint)

    def test_without_a_charter_the_issue_is_never_chosen(self):
        (self.main / '.frontlights' / 'authorization.json').unlink()
        with self.assertRaises(_cli.UsageError) as caught:
            _cli.issue_number(None, self.tree, self.main)
        self.assertIn('--issue', caught.exception.hint)


class ScriptsTests(Fixture):
    def run_script(self, name, *args, cwd=None, env=None):
        done = subprocess.run([sys.executable, str(SCRIPTS / name), *args], capture_output=True, cwd=cwd or self.tree,
                              stdin=subprocess.DEVNULL, timeout=120, env=env)
        self.assertNotIn(b'Traceback', done.stderr)
        return done

    def test_suite_gate_runs_in_an_issue_worktree_without_any_flag(self):
        done = self.run_script('homolog.py', 'suite-gate')
        result = json.loads(done.stdout.decode('utf-8'))
        self.assertEqual(result['status'], 'unconfigured', result)   # the config of the main worktree was read
        self.assertTrue(same(result['recordPath'], self.tree / '.frontlights' / 'issues' / '7' / 'suite.json'))

    def test_suite_gate_outside_the_charter_refuses_with_a_hint(self):
        done = self.run_script('homolog.py', 'suite-gate', cwd=self.other)
        result = json.loads(done.stdout.decode('utf-8'))
        self.assertEqual(done.returncode, 1)
        self.assertFalse(result['ok'])
        self.assertIn('7, 9', result['hint'])

    def test_a_usage_error_is_json_with_a_hint_in_every_script(self):
        for name, argv in (('frontlights.py', ['inspect', '--nada']), ('homolog.py', ['sync', '--nada']),
                           ('closeout.py', ['tick', '--nada']), ('cleanup.py', ['plan', '--nada']),
                           ('stamp.py', ['--nada']), ('serve.py', ['status', '--nada']),
                           ('browser_gate.py', ['--nada']), ('checks.py', ['smoke', '--nada']),
                           ('progress_report.py', ['status', '--nada']), ('roads.py', ['status', '--nada'])):
            with self.subTest(script=name):
                done = self.run_script(name, *argv)
                result = json.loads(done.stdout.decode('utf-8'))
                self.assertNotEqual(done.returncode, 0)
                self.assertFalse(result['ok'])
                # serve and checks keep the text in `error` (their convention); the others say `usage`
                self.assertIn(result['error'], ('usage', result['message']))
                self.assertIn('inválido', result['message'])
                self.assertIn('--help', result['hint'])

    def test_output_is_utf8_whatever_the_console_encoding(self):
        env = dict(os.environ, PYTHONIOENCODING='cp1252')
        for name, argv in (('frontlights.py', ['inspect', '--nada']), ('serve.py', ['status', '--nada'])):
            with self.subTest(script=name):
                done = self.run_script(name, *argv, env=env)
                text = done.stdout.decode('utf-8')   # cp1252 bytes for "á" would not decode
                self.assertIn('inválido', text)


if __name__ == '__main__':
    unittest.main()
