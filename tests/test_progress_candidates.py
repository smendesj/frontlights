"""The prints that watched browser tests keep for the summary (`candidates`): what is listed, when the
code they show still counts as the delivered code, and what is never offered."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import progress_report as pr

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
VISIBLE = 'web/src/page.html'


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class CandidatesTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 'a@example.test')
        git(self.root, 'config', 'user.name', 'a')
        git(self.root, 'config', 'commit.gpgsign', 'false')
        (self.root / 'web' / 'src').mkdir(parents=True)
        (self.root / VISIBLE).write_text('<p>one</p>', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-q', '-m', 'first')
        self.blob = git(self.root, 'rev-parse', f'HEAD:{VISIBLE}')
        self.folder = self.root / '.frontlights' / 'issues' / '100' / 'browser' / 'resumo'
        self.folder.mkdir(parents=True)

    def shot(self, name='101-lista.png', data=PNG):
        (self.folder / name).write_bytes(data)
        return name

    def item(self, **overrides):
        item = {'file': self.shot(), 'caption': 'A lista mostra a empresa excluída.', 'issue': 101, 'cover': 100,
                'repository': 'OWNER/REPOSITORY', 'takenAt': '2026-10-07T10:00:00-03:00', 'head': 'abc',
                'visibleFiles': {VISIBLE: self.blob}}
        item.update(overrides)
        return item

    def write(self, *items):
        (self.folder / 'candidates.json').write_text(json.dumps(list(items)), encoding='utf-8')

    def run_op(self, to='2026-10-07', **kwargs):
        return pr.run('candidates', str(self.root), date_to=to, **kwargs)


class ListingTests(CandidatesTestCase):
    def test_a_fresh_clean_print_is_usable_and_carries_its_cover(self):
        self.write(self.item())
        result = self.run_op()
        self.assertTrue(result['ok'], result)
        [entry] = result['candidates']
        self.assertEqual((entry['cover'], entry['issue'], entry['fresh'], entry['usable'], entry['problems']),
                         (100, 101, True, True, []))
        self.assertEqual(Path(entry['file']), self.folder / '101-lista.png')
        self.assertEqual(entry['record'], '100')

    def test_without_any_record_the_list_is_empty(self):
        (self.folder / 'candidates.json').unlink(missing_ok=True)
        self.assertEqual(self.run_op()['candidates'], [])

    def test_a_print_taken_after_the_last_day_is_left_out(self):
        self.write(self.item(takenAt='2026-10-08T00:30:00-03:00'))
        self.assertEqual(self.run_op(to='2026-10-07')['candidates'], [])
        self.assertEqual(len(self.run_op(to='2026-10-08')['candidates']), 1)

    def test_the_day_is_the_sao_paulo_day_not_the_utc_one(self):
        self.write(self.item(takenAt='2026-10-07T22:30:00-03:00'))   # 01:30 UTC of the 8th
        self.assertEqual(len(self.run_op(to='2026-10-07')['candidates']), 1)

    def test_a_print_taken_before_the_window_still_counts(self):
        self.write(self.item(takenAt='2026-10-03T10:00:00-03:00'))
        self.assertTrue(self.run_op(to='2026-10-07')['candidates'][0]['usable'])

    def test_to_is_required_and_must_be_a_date(self):
        self.assertFalse(pr.run('candidates', str(self.root))['ok'])
        self.assertFalse(self.run_op(to='07/10/2026')['ok'])

    def test_it_copies_nothing_and_needs_no_configuration(self):
        self.write(self.item())
        before = sorted(os.listdir(self.folder))
        self.run_op()
        self.assertEqual(sorted(os.listdir(self.folder)), before)
        self.assertFalse((self.root / '.frontlights' / 'config.json').exists())


class FreshnessTests(CandidatesTestCase):
    def test_changed_visible_code_makes_the_print_not_fresh(self):
        self.write(self.item())
        (self.root / VISIBLE).write_text('<p>two</p>', encoding='utf-8')
        git(self.root, 'commit', '-q', '-am', 'second')
        [entry] = self.run_op()['candidates']
        self.assertFalse(entry['fresh'])
        self.assertFalse(entry['usable'])
        self.assertIn(VISIBLE, ' '.join(entry['problems']))

    def test_a_ref_compares_against_the_branch_that_holds_the_work(self):
        git(self.root, 'branch', 'delivered')
        (self.root / VISIBLE).write_text('<p>two</p>', encoding='utf-8')
        git(self.root, 'commit', '-q', '-am', 'second')
        self.write(self.item())
        self.assertTrue(self.run_op(ref='delivered')['candidates'][0]['fresh'])
        self.assertFalse(self.run_op()['candidates'][0]['fresh'])

    def test_without_visible_files_it_cannot_be_told_and_is_not_usable(self):
        self.write(self.item(visibleFiles={}))
        [entry] = self.run_op()['candidates']
        self.assertFalse(entry['usable'])
        self.assertIn('visible files', ' '.join(entry['problems']))

    def test_a_tree_id_is_not_a_file_and_never_counts_as_fresh(self):
        tree = git(self.root, 'rev-parse', 'HEAD:web/src')
        self.write(self.item(visibleFiles={'web/src': tree}))
        [entry] = self.run_op()['candidates']
        self.assertFalse(entry['fresh'])

    def test_a_list_of_visible_files_past_the_limit_is_a_problem_not_a_wait(self):
        many = {f'web/src/f{i}.html': self.blob for i in range(pr.MAX_VISIBLE_FILES + 1)}
        self.write(self.item(visibleFiles=many))
        [entry] = self.run_op()['candidates']
        self.assertFalse(entry['fresh'])
        self.assertIn('more than', ' '.join(entry['problems']))

    def test_a_deleted_visible_file_is_not_fresh(self):
        self.write(self.item(visibleFiles={'web/src/gone.html': self.blob}))
        self.assertFalse(self.run_op()['candidates'][0]['fresh'])

    def test_paths_that_leave_the_repository_are_refused_not_asked_to_git(self):
        for path in ('../outside.html', '/abs.html', '-flag'):
            with self.subTest(path=path):
                self.write(self.item(visibleFiles={path: self.blob}))
                entry = self.run_op()['candidates'][0]
                self.assertFalse(entry['fresh'])
                self.assertIn('relative path', ' '.join(entry['problems']))

    def test_a_ref_that_looks_like_an_option_or_a_range_is_refused(self):
        for ref in ('--output=x', 'a..b', 'bad ref'):
            with self.subTest(ref=ref):
                self.assertFalse(self.run_op(ref=ref)['ok'])


class ImageAndShapeTests(CandidatesTestCase):
    def problems(self):
        return ' '.join(self.run_op()['candidates'][0]['problems'])

    def test_a_non_image_a_large_file_and_a_path_name_are_problems(self):
        self.write(self.item(file=self.shot('x.png', b'not an image')))
        self.assertIn('not a PNG or JPEG', self.problems())
        self.write(self.item(file=self.shot('big.png', PNG + b'0' * (1024 * 1024))))
        self.assertIn('larger than 1 MB', self.problems())
        self.write(self.item(file='../escape.png'))
        self.assertIn('plain', self.problems())
        self.write(self.item(file='missing.png'))
        self.assertIn('missing', self.problems())

    def test_a_file_with_a_problem_never_gets_a_path_to_copy(self):
        for name in ('../escape.png', 'missing.png', 'sub/inside.png'):
            with self.subTest(name=name):
                self.write(self.item(file=name))
                [entry] = self.run_op()['candidates']
                self.assertIsNone(entry['file'])
                self.assertFalse(entry['usable'])

    def test_bad_fields_are_problems_and_never_crash(self):
        self.write(self.item(issue='101', cover=0, caption=' ', takenAt='yesterday'))
        text = self.problems()
        for part in ('issue must', 'cover must', 'caption must', 'takenAt must'):
            with self.subTest(part=part):
                self.assertIn(part, text)

    def test_an_extreme_takenAt_is_a_problem_of_that_item_not_a_crash(self):
        self.write(self.item(takenAt='0001-01-01T00:00:00+05:00'), self.item(file=self.shot('b.png')))
        result = self.run_op()
        self.assertTrue(result['ok'], result)
        self.assertEqual([entry['usable'] for entry in result['candidates']], [False, True])
        self.write(self.item(takenAt='9999-12-31T23:59:59-05:00'))
        self.assertTrue(self.run_op()['ok'])

    def test_a_takenAt_without_an_offset_is_a_problem(self):
        self.write(self.item(takenAt='2026-10-07T10:00:00'))
        self.assertIn('offset', self.problems())

    def test_unknown_keys_make_the_entry_unusable(self):
        self.write(dict(self.item(), password='x'))
        [entry] = self.run_op()['candidates']
        self.assertFalse(entry['usable'])
        self.assertIsNone(entry['file'])

    def test_a_broken_or_non_list_file_is_a_warning_not_an_error(self):
        (self.folder / 'candidates.json').write_text('{not json', encoding='utf-8')
        result = self.run_op()
        self.assertTrue(result['ok'])
        self.assertEqual(result['candidates'], [])
        self.assertTrue(result['warnings'])
        (self.folder / 'candidates.json').write_text('{}', encoding='utf-8')
        self.assertTrue(self.run_op()['warnings'])

    def test_candidates_of_several_issues_are_ordered_by_cover(self):
        other = self.root / '.frontlights' / 'issues' / '200' / 'browser' / 'resumo'
        other.mkdir(parents=True)
        (other / 'a.png').write_bytes(PNG)
        (other / 'candidates.json').write_text(json.dumps([dict(self.item(), file='a.png', cover=50, issue=51)]), encoding='utf-8')
        self.write(self.item())
        self.assertEqual([entry['cover'] for entry in self.run_op()['candidates']], [50, 100])


class RepositoryTests(CandidatesTestCase):
    def test_a_print_of_another_repository_is_a_problem_when_the_summary_names_its_own(self):
        self.write(self.item(repository='OTHER/PRODUCT'))
        [entry] = self.run_op(repository='OWNER/REPOSITORY')['candidates']
        self.assertFalse(entry['usable'])
        self.assertIn('another repository', ' '.join(entry['problems']))

    def test_the_comparison_ignores_case_and_a_missing_repository_is_a_problem(self):
        self.write(self.item(repository='owner/repository'))
        self.assertTrue(self.run_op(repository='OWNER/REPOSITORY')['candidates'][0]['usable'])
        item = self.item()
        del item['repository']
        self.write(item)
        [entry] = self.run_op(repository='OWNER/REPOSITORY')['candidates']
        self.assertFalse(entry['usable'])
        self.assertIn('OWNER/REPOSITORY', ' '.join(entry['problems']))

    def test_without_a_repository_to_compare_the_check_is_off(self):
        self.write(self.item(repository='OTHER/PRODUCT'))
        self.assertTrue(self.run_op()['candidates'][0]['usable'])

    def test_a_malformed_repository_argument_is_refused(self):
        for bad in ('owner', '--x/y', 'a b/c', 'a/b/c'):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_op(repository=bad)['ok'])


class TextTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def flat(self, *parts):
        return ' '.join(self.ROOT.joinpath(*parts).read_text(encoding='utf-8').split())

    def test_the_reference_offers_the_prints_of_the_watched_test_or_new_ones(self):
        text = self.flat('skills', 'frontlights', 'references', 'progress-report.md')
        for phrase in ('progress_report.py" candidates', '"Usar os do teste assistido"', '"Capturar novos"', '"Misturar"',
                       'Copy, never move', 'the cover', 'is not offered', '--repository', 'main worktree'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_family_rule_leaves_the_count_to_the_email_and_reports_a_cut_read(self):
        text = self.flat('skills', 'frontlights', 'references', 'progress-report.md')
        for phrase in ('do not repeat the count in the text', '`slices.closed`', '`slices.blocked`', 'Product scope'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn('ignored.cut', self.flat('docs', 'roads-contract.md'))

    def test_the_sprint_block_and_the_chips_are_documented_for_every_summary(self):
        text = self.flat('skills', 'frontlights', 'references', 'progress-report.md')
        for phrase in ('Sprint block and chips', '`delivered`', '"Concluído: N sub-issues em M issues"',
                       '"Em andamento: N sub-issues em K issues"', 'There is no "Em validação" chip',
                       'The covers are not deliveries', 'only the fallback when the facts have no `sprint`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        contract = self.flat('docs', 'roads-contract.md')
        for phrase in ('`sprint.epics[]`', 'sem o chip "Em validação"', 'Decisão de 07/10/2026'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)

    def test_the_watched_test_keeps_clean_prints_for_the_summary(self):
        text = self.flat('skills', 'frontlights', 'references', 'browser-testing.md')
        for phrase in ('Prints kept for the progress summary', 'candidates.json', 'DEPOIS only, never ANTES', 'visibleFiles',
                       'Without the ANTES/DEPOIS strip', 'a single print per delivery'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == '__main__':
    unittest.main()
