"""Carimbo de aprovação (issue 61, S1): `frontlights.py stamp` liga a aprovação de um documento ao conteúdo exato
do arquivo.

Seam: a entrada `frontlights.py stamp` (que delega a `scripts/stamp.py`), por subprocesso, em pastas temporárias.
Só dados de teste: nenhum documento real, nenhum caminho de máquina.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
CONTENT = b'# Spec\n\nCriterio de teste.\n'
ANSWER = 'Sim, aprovo a r1'


def stamp_of(data):
    return hashlib.sha256(data).hexdigest()[:12]


class StampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.doc = self.root / 'docs' / 'spec.md'
        self.doc.parent.mkdir()
        self.doc.write_bytes(CONTENT)

    def tearDown(self):
        self.temp.cleanup()

    def run_stamp(self, *args, cwd=None, root=True):
        argv = [sys.executable, str(SCRIPT), 'stamp', *args]
        if root:
            argv += ['--root', str(self.root)]
        done = subprocess.run(argv, capture_output=True, cwd=cwd or self.root, stdin=subprocess.DEVNULL, timeout=60)
        self.assertNotIn(b'Traceback', done.stderr)
        result = json.loads(done.stdout.decode('utf-8'))
        self.assertEqual(result['exitCode'], done.returncode)
        self.assertEqual(result['operation'], 'stamp')
        self.assertIn('message', result)
        return done.returncode, result

    def approve(self, doc, revision, answer):
        code, result = self.run_stamp(str(doc), '--revision', revision, '--approve', '--answer', answer,
                                      '--expect', stamp_of(doc.read_bytes()))
        self.assertEqual(code, 0, result['message'])
        return result

    def approvals(self):
        return json.loads((self.root / '.frontlights' / 'approvals.json').read_text(encoding='utf-8'))

    def test_prints_the_stamp_of_the_raw_bytes(self):
        code, result = self.run_stamp(str(self.doc), '--revision', 'r2')
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['path'], 'docs/spec.md')
        self.assertEqual(result['revision'], 'r2')
        self.assertEqual(result['sha256'], stamp_of(CONTENT))
        self.assertEqual(result['bytes'], len(CONTENT))
        self.assertFalse((self.root / '.frontlights' / 'approvals.json').exists())

    def test_options_may_come_before_the_file(self):
        code, result = self.run_stamp('--expect', stamp_of(CONTENT), str(self.doc))
        self.assertEqual(code, 0)
        self.assertEqual(result['sha256'], stamp_of(CONTENT))

    def test_revision_defaults_to_null(self):
        code, result = self.run_stamp(str(self.doc))
        self.assertEqual(code, 0)
        self.assertIsNone(result['revision'])

    def test_path_outside_root_is_kept_as_given(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / 'nota.md'
            outside.write_bytes(CONTENT)
            code, result = self.run_stamp(str(outside))
        self.assertEqual(code, 0)
        self.assertEqual(result['path'], str(outside).replace('\\', '/'))

    def test_root_defaults_to_the_current_directory(self):
        code, result = self.run_stamp('docs/spec.md', '--approve', '--answer', ANSWER, '--expect', stamp_of(CONTENT),
                                      root=False)
        self.assertEqual(code, 0)
        self.assertEqual(result['path'], 'docs/spec.md')
        self.assertEqual(self.approvals()[0]['path'], 'docs/spec.md')

    def test_approve_appends_the_entry_with_the_verbatim_answer(self):
        code, result = self.run_stamp(str(self.doc), '--revision', 'r1', '--approve', '--answer', ANSWER,
                                      '--stage', '3', '--expect', stamp_of(CONTENT))
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])
        [entry] = self.approvals()
        self.assertEqual(entry['path'], 'docs/spec.md')
        self.assertEqual(entry['revision'], 'r1')
        self.assertEqual(entry['sha256'], stamp_of(CONTENT))
        self.assertEqual(entry['bytes'], len(CONTENT))
        self.assertEqual(entry['answer'], ANSWER)
        self.assertEqual(entry['stage'], 3)
        self.assertTrue(entry['at'].endswith('-03:00'), entry['at'])
        self.assertNotIn('Z', entry['at'])

    def test_approve_without_stage_leaves_stage_out(self):
        self.run_stamp(str(self.doc), '--approve', '--answer', ANSWER, '--expect', stamp_of(CONTENT))
        self.assertNotIn('stage', self.approvals()[0])

    def test_approve_keeps_entries_written_by_hand(self):
        folder = self.root / '.frontlights'
        folder.mkdir()
        by_hand = {'path': 'docs/outra.md', 'revision': 'r1', 'sha256': 'a' * 12, 'bytes': 3,
                   'answer': 'Sim', 'at': '2026-10-01T10:00:00-03:00', 'published': True}
        (folder / 'approvals.json').write_text(json.dumps([by_hand]), encoding='utf-8')
        code, _ = self.run_stamp(str(self.doc), '--approve', '--answer', ANSWER, '--expect', stamp_of(CONTENT))
        self.assertEqual(code, 0)
        entries = self.approvals()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0], by_hand)
        self.assertEqual(entries[1]['path'], 'docs/spec.md')

    def test_approve_requires_an_answer(self):
        code, result = self.run_stamp(str(self.doc), '--approve', '--expect', stamp_of(CONTENT))
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertIn('--answer', result['message'])
        self.assertFalse((self.root / '.frontlights' / 'approvals.json').exists())

    def test_check_matches_the_last_approval(self):
        self.approve(self.doc, 'r1', ANSWER)
        code, result = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])

    def test_check_reports_a_change_since_the_approval(self):
        self.approve(self.doc, 'r1', ANSWER)
        self.doc.write_bytes(CONTENT + b'Mais uma linha.\n')
        code, result = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertEqual(result['approved'], {'revision': 'r1', 'sha256': stamp_of(CONTENT)})
        self.assertIn('mudou desde a aprovação r1', result['message'])
        self.assertIn('nova aprovação', result['message'])

    def test_check_uses_the_last_approval_of_the_same_path(self):
        self.approve(self.doc, 'r1', ANSWER)
        self.doc.write_bytes(b'r2\n')
        self.approve(self.doc, 'r2', 'Sim, r2')
        code, _ = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 0)

    def test_approve_without_expect_is_refused(self):
        code, result = self.run_stamp(str(self.doc), '--approve', '--answer', ANSWER)
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertIn('--expect', result['message'])
        self.assertFalse((self.root / '.frontlights' / 'approvals.json').exists())

    def test_edit_between_the_question_and_the_approve_writes_nothing(self):
        shown = stamp_of(CONTENT)
        self.doc.write_bytes(CONTENT + b'Editado depois da pergunta.\n')
        code, result = self.run_stamp(str(self.doc), '--revision', 'r1', '--approve', '--answer', ANSWER,
                                      '--expect', shown)
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertNotIn('approval', result)
        self.assertIn('mudou desde a pergunta', result['message'])
        self.assertIn('pedir a aprovação de novo', result['message'])
        self.assertFalse((self.root / '.frontlights' / 'approvals.json').exists())
        code, _ = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 1)

    def test_edit_between_the_question_and_the_approve_keeps_the_file_unchanged(self):
        self.approve(self.doc, 'r1', ANSWER)
        before = (self.root / '.frontlights' / 'approvals.json').read_bytes()
        shown = stamp_of(CONTENT)
        self.doc.write_bytes(b'r2 editada\n')
        code, _ = self.run_stamp(str(self.doc), '--revision', 'r2', '--approve', '--answer', 'Sim, r2',
                                 '--expect', shown)
        self.assertEqual(code, 1)
        self.assertEqual((self.root / '.frontlights' / 'approvals.json').read_bytes(), before)
        code, _ = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 1)

    def test_check_picks_the_line_of_its_own_path(self):
        other = self.root / 'docs' / 'outra.md'
        other.write_bytes(b'Outro documento.\n')
        self.approve(self.doc, 'r1', ANSWER)
        self.approve(other, 'r1', 'Sim, a outra')
        code, result = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 0, result['message'])
        self.assertIn('confere com a aprovação r1', result['message'])
        third = self.root / 'docs' / 'terceira.md'
        third.write_bytes(b'Sem aprovacao.\n')
        code, result = self.run_stamp(str(third), '--check')
        self.assertEqual(code, 1)
        self.assertIn('nenhuma aprovação', result['message'].lower())
        self.assertIn('docs/terceira.md', result['message'])

    def test_check_counts_the_last_approval_not_any(self):
        self.approve(self.doc, 'r1', ANSWER)
        self.doc.write_bytes(b'r2\n')
        self.approve(self.doc, 'r2', 'Sim, r2')
        self.doc.write_bytes(CONTENT)
        code, result = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 1)
        self.assertEqual(result['approved'], {'revision': 'r2', 'sha256': stamp_of(b'r2\n')})

    def test_check_without_an_approval_fails_clearly(self):
        code, result = self.run_stamp(str(self.doc), '--check')
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertIn('nenhuma aprovação', result['message'].lower())
        self.assertIn('docs/spec.md', result['message'])

    def test_expect_equal_and_different(self):
        code, result = self.run_stamp(str(self.doc), '--expect', stamp_of(CONTENT))
        self.assertEqual(code, 0)
        self.assertTrue(result['ok'])
        code, result = self.run_stamp(str(self.doc), '--expect', 'b' * 12)
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])

    def test_missing_file_names_the_path_without_traceback(self):
        code, result = self.run_stamp(str(self.root / 'docs' / 'ausente.md'))
        self.assertEqual(code, 1)
        self.assertFalse(result['ok'])
        self.assertIn('docs/ausente.md', result['message'])


if __name__ == '__main__':
    unittest.main()
