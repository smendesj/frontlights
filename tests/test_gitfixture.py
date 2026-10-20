"""The class template repository of `tests/gitfixture.py`: built once per class, copied whole into each test.

Seam: the helper's public functions (`template`, `copy`, `git`, `init`). A copy is independent of the template and of
other copies; a bare origin built with the template answers at its new place in the copy; the template folder is
gone after the class; a template with a worktree is refused. Only generic markers (public repository).
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture


def build(root):
    """A repository `main` with one commit, and its bare `origin.git` already pushed to."""
    main = root / 'main'
    gitfixture.init(main)
    (main / 'a.txt').write_text('one\n', encoding='utf-8')
    gitfixture.git(main, 'add', '.')
    gitfixture.git(main, 'commit', '-q', '-m', 'base')
    gitfixture.git(root, 'init', '-q', '--bare', '-b', 'main', str(root / 'origin.git'))
    gitfixture.git(main, 'remote', 'add', 'origin', str(root / 'origin.git'))
    gitfixture.git(main, 'push', '-q', 'origin', 'main')


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build)

    def fresh(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return gitfixture.copy(self.template, Path(tmp.name) / 'copy')

    def head(self, root):
        return gitfixture.git(root, 'rev-parse', 'HEAD').stdout.strip()

    def test_a_commit_in_a_copy_changes_neither_the_template_nor_another_copy(self):
        first, second = self.fresh(), self.fresh()
        before = self.head(self.template / 'main')
        (first / 'main' / 'a.txt').write_text('two\n', encoding='utf-8')
        gitfixture.git(first / 'main', 'commit', '-q', '-am', 'in the copy')
        self.assertNotEqual(self.head(first / 'main'), before)
        self.assertEqual(self.head(self.template / 'main'), before)
        self.assertEqual(self.head(second / 'main'), before)
        self.assertEqual((second / 'main' / 'a.txt').read_text(encoding='utf-8'), 'one\n')

    def test_the_copied_origin_answers_at_its_new_place(self):
        copied = self.fresh()
        url = gitfixture.git(copied / 'main', 'remote', 'get-url', 'origin').stdout.strip()
        self.assertEqual(Path(url).resolve(), (copied / 'origin.git').resolve())
        template_origin = self.head(self.template / 'origin.git')
        (copied / 'main' / 'a.txt').write_text('pushed\n', encoding='utf-8')
        gitfixture.git(copied / 'main', 'commit', '-q', '-am', 'to push')
        gitfixture.git(copied / 'main', 'push', '-q', 'origin', 'main')
        self.assertEqual(self.head(copied / 'origin.git'), self.head(copied / 'main'))
        self.assertEqual(self.head(self.template / 'origin.git'), template_origin)
        gitfixture.git(copied / 'main', 'fetch', '-q', 'origin')
        self.assertEqual(gitfixture.git(copied / 'main', 'rev-parse', 'origin/main').stdout.strip(),
                         self.head(copied / 'main'))
        self.assertEqual(gitfixture.git(self.template / 'main', 'rev-parse', 'origin/main').stdout.strip(),
                         template_origin)

    def test_the_template_folder_is_gone_after_the_class(self):
        seen = {}

        class Inner(unittest.TestCase):          # defined here, so the loader never collects it on its own
            @classmethod
            def setUpClass(cls):
                cls.template = gitfixture.template(cls, build)

            def test_uses_it(self):
                seen['template'] = self.template
                self.assertTrue((self.template / 'main' / '.git').is_dir())

        result = unittest.TestResult()
        unittest.TestSuite([Inner('test_uses_it')]).run(result)
        self.assertEqual((result.testsRun, result.errors, result.failures), (1, [], []))
        self.assertFalse(seen['template'].exists())

    def test_a_copy_into_an_existing_folder_keeps_what_is_there(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / 'root'
        (dest / '.frontlights').mkdir(parents=True)
        (dest / '.frontlights' / 'config.json').write_text('{}\n', encoding='utf-8')
        gitfixture.copy(self.template, dest, exist_ok=True)
        self.assertEqual((dest / '.frontlights' / 'config.json').read_text(encoding='utf-8'), '{}\n')
        self.assertEqual(self.head(dest / 'main'), self.head(self.template / 'main'))
        url = gitfixture.git(dest / 'main', 'remote', 'get-url', 'origin').stdout.strip()
        self.assertEqual(Path(url).resolve(), (dest / 'origin.git').resolve())

    def test_a_template_with_a_worktree_is_refused(self):
        def with_worktree(root):
            build(root)
            gitfixture.git(root / 'main', 'worktree', 'add', '-q', '-b', 'side', str(root / 'side'), 'main')

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name) / 'template'
        folder.mkdir()
        with_worktree(folder)
        with self.assertRaisesRegex(ValueError, 'worktree'):
            gitfixture.copy(folder, Path(tmp.name) / 'copy')


if __name__ == '__main__':
    unittest.main()
