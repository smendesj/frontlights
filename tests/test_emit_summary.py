"""Base dos scripts (redesenho, issue 1, S2): `_cli.emit()` imprime um resumo quando a saída passa de 4 KB ou de 80
linhas e grava o JSON inteiro em `<tree>/.frontlights/out/<verbo>-<AAAAMMDD-HHMMSS>-<pid>.json`.

Seam: `_cli.emit` sobre pastas temporárias, e `frontlights.py drift` por subprocesso, com uma saída longa feita de
dados de teste. Só dados de teste: nenhum projeto real, nenhum caminho de máquina.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import _cli  # noqa: E402
import cleanup  # noqa: E402

NAME = re.compile(r'(?P<verb>[a-z-]+)-(?P<stamp>\d{8}-\d{6})-(?P<pid>\d+)\.json')


def long_result(items=200):
    return {'ok': True, 'exitCode': 0, 'status': 'ready', 'message': 'há muitas linhas',
            'issues': [{'number': n, 'title': f'issue de teste {n}'} for n in range(items)], 'plan': {'a': 1, 'b': 2}}


class EmitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tree = Path(tmp.name)
        self.out = self.tree / '.frontlights' / 'out'

    def emit(self, result, verb='release-plan', full=False):
        text = json.dumps(result, indent=2, ensure_ascii=True)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            _cli.emit(text, verb, full=full, tree=self.tree)
        return text, printed.getvalue()

    def test_a_short_output_is_printed_whole_and_nothing_is_saved(self):
        text, printed = self.emit({'ok': True, 'exitCode': 0, 'status': 'ready'})
        self.assertEqual(printed.strip(), text)
        self.assertFalse(self.out.exists())

    def test_a_long_output_prints_a_summary_and_saves_the_whole_json(self):
        text, printed = self.emit(long_result())
        summary = json.loads(printed)
        self.assertLessEqual(len(printed.splitlines()), _cli.SUMMARY_LINES)
        self.assertEqual((summary['summary'], summary['ok'], summary['exitCode'], summary['status']),
                         (True, True, 0, 'ready'))
        self.assertEqual(summary['message'], 'há muitas linhas')
        self.assertEqual(summary['counts'], {'issues': 200, 'plan': 2})
        saved = Path(summary['full'])
        self.assertEqual(saved.parent, self.out)
        self.assertEqual(saved.read_text(encoding='utf-8'), text)
        self.assertIn('--full', summary['hint'])

    def test_more_than_80_lines_is_long_even_under_4_kb(self):
        result = {'ok': True, 'exitCode': 0, 'ids': list(range(90))}
        text, printed = self.emit(result)
        self.assertLess(len(text.encode()), _cli.SUMMARY_BYTES)
        self.assertTrue(json.loads(printed)['summary'])

    def test_the_name_has_the_verb_the_sao_paulo_time_and_the_pid(self):
        _, printed = self.emit(long_result())
        match = NAME.fullmatch(Path(json.loads(printed)['full']).name)
        self.assertIsNotNone(match)
        self.assertEqual((match['verb'], int(match['pid'])), ('release-plan', os.getpid()))
        now = _cli.sao_paulo_now()
        self.assertEqual(now.utcoffset(), timedelta(hours=-3))
        when = datetime.strptime(match['stamp'], '%Y%m%d-%H%M%S').replace(tzinfo=now.tzinfo)
        self.assertLess(abs(now - when), timedelta(minutes=2))

    def test_full_prints_everything(self):
        text, printed = self.emit(long_result(), full=True)
        self.assertEqual(printed.strip(), text)
        self.assertFalse(self.out.exists())

    def test_the_verbs_that_are_never_summarized(self):
        for verb in ('stamp', 'authorize', 'tick', 'verify', 'checkpoint'):
            with self.subTest(verb=verb):
                text, printed = self.emit(long_result(), verb=verb)
                self.assertEqual(printed.strip(), text)
        self.assertFalse(self.out.exists())

    def test_only_the_last_five_of_each_verb_are_kept(self):
        self.out.mkdir(parents=True)
        other = self.out / 'inspect-20000101-000000-1.json'
        other.write_text('{}', encoding='utf-8')
        for second in range(7):
            (self.out / f'release-plan-20000101-0000{second:02d}-1.json').write_text('{}', encoding='utf-8')
        _, printed = self.emit(long_result())
        kept = sorted(p.name for p in self.out.glob('release-plan-*.json'))
        self.assertEqual(len(kept), _cli.KEEP_PER_VERB)
        self.assertIn(Path(json.loads(printed)['full']).name, kept)
        self.assertTrue(other.is_file())
        self.assertEqual([p for p in self.out.iterdir() if p.name.endswith('.tmp')], [])

    def test_a_folder_that_cannot_be_written_prints_everything(self):
        (self.tree / '.frontlights').write_text('not a folder', encoding='utf-8')
        text, printed = self.emit(long_result())
        self.assertEqual(printed.strip(), text)


class ScriptTests(unittest.TestCase):
    def test_a_script_summarizes_a_long_output_and_full_prints_it(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'before.md').write_text(''.join(f'- [ ] item {n}\n' for n in range(120)), encoding='utf-8')
            (folder / 'after.md').write_text(''.join(f'- [ ] outro {n}\n' for n in range(120)), encoding='utf-8')
            argv = [sys.executable, str(SCRIPTS / 'closeout.py'), 'tick-check', '--before', 'before.md', '--after',
                    'after.md', '--lines', '1']
            done = subprocess.run(argv, capture_output=True, cwd=folder, timeout=60)
            self.assertNotIn(b'Traceback', done.stderr)
            summary = json.loads(done.stdout)
            self.assertTrue(summary['summary'], summary)
            self.assertLessEqual(len(done.stdout.splitlines()), _cli.SUMMARY_LINES)
            saved = Path(summary['full'])
            self.assertEqual(saved.resolve().parent, (folder / '.frontlights' / 'out').resolve())
            whole = json.loads(saved.read_text(encoding='utf-8'))
            self.assertEqual(summary['exitCode'], whole['exitCode'])
            self.assertEqual(done.returncode, whole['exitCode'])
            for flag in ('--full', '--json'):
                with self.subTest(flag=flag):
                    done = subprocess.run(argv + [flag], capture_output=True, cwd=folder, timeout=60)
                    self.assertEqual(json.loads(done.stdout), whole)


class ArchiveTests(unittest.TestCase):
    def test_archive_leaves_out_the_out_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            main = Path(folder) / 'main'
            main.mkdir()
            for args in (['init', '-q', '-b', 'main'], ['config', 'user.email', 'fixture@example.invalid'],
                         ['config', 'user.name', 'Fixture'], ['commit', '-q', '--allow-empty', '-m', 'base'],
                         ['worktree', 'add', '-q', '-b', 'sergio/issue-3', str(Path(folder) / 'wt')]):
                subprocess.run(['git', '-C', str(main), *args], check=True, capture_output=True)
            records = Path(folder) / 'wt' / '.frontlights'
            (records / 'out').mkdir(parents=True)
            (records / 'out' / 'inspect-20000101-000000-1.json').write_text('{}', encoding='utf-8')
            (records / 'handoff.md').write_text('# handoff\n', encoding='utf-8')
            target = main / '.frontlights' / 'issues' / '3' / 'worktrees' / 'wt'
            result = cleanup.op_archive(str(records), str(target))
            self.assertEqual(result.get('exitCode', 0), 0, result)
            self.assertTrue((target / 'handoff.md').is_file())
            self.assertFalse((target / 'out').exists())


if __name__ == '__main__':
    unittest.main()
