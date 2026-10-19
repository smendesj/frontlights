"""The prints of the watched browser test in the folder of the sprint the test ran in (`evidence-dir`), and the
prints kept for the summary read back from there by `candidates`.

The folder is `<scrumRoot>/<weekFolderPattern of the Monday of the run>/evidencias/<repository>/<issue>`, with the
summary prints in its `resumo/`; a project without `scrumRoot` or `weekFolderPattern` keeps them in `.frontlights`.
Seam: `progress_report.run`, on a temporary Git repository with its own `.frontlights/config.json` and a temporary
scrumRoot; the texts are checked flattened, as in the other text tests.
"""

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


class EvidenceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'produto'
        self.root.mkdir()
        self.scrum = base / 'SCRUM'
        self.scrum.mkdir()
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 'a@example.test')
        git(self.root, 'config', 'user.name', 'a')
        git(self.root, 'config', 'commit.gpgsign', 'false')
        (self.root / 'web' / 'src').mkdir(parents=True)
        (self.root / VISIBLE).write_text('<p>one</p>', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-q', '-m', 'first')
        self.blob = git(self.root, 'rev-parse', f'HEAD:{VISIBLE}')

    def configure(self, repository='OWNER/REPOSITORY', **sync):
        block = {'enabled': False, 'scrumRoot': str(self.scrum), 'weekFolderPattern': '{yyyy}/{dd_MM}'}
        block.update(sync)
        config = {'roadmapSync': {key: value for key, value in block.items() if value is not None}}
        if repository is not None:
            config['repository'] = repository
        (self.root / '.frontlights').mkdir(exist_ok=True)
        (self.root / '.frontlights' / 'config.json').write_text(json.dumps(config), encoding='utf-8')

    def resolve(self, issue=1107, at='2026-10-21T10:00:00-03:00', root=None):
        return pr.run('evidence-dir', str(root or self.root), issue=issue, at=at)

    def sprint(self, monday, issue=100):
        return self.scrum / '2026' / monday / 'evidencias' / 'REPOSITORY' / str(issue)


class FolderTests(EvidenceTestCase):
    def test_the_prints_go_to_the_sprint_of_the_monday_of_the_run(self):
        self.configure()
        result = self.resolve()
        self.assertTrue(result['ok'], result)
        folder = self.sprint('19_10', 1107)
        self.assertEqual((Path(result['evidenceDir']), Path(result['summaryDir']), result['sprint'], result['inSprint']),
                         (folder, folder / 'resumo', '2026-10-19', True))
        self.assertTrue(folder.is_dir())

    def test_a_run_on_monday_and_one_on_sunday_belong_to_their_own_week(self):
        self.configure()
        self.assertEqual(self.resolve(at='2026-10-19T08:00:00-03:00')['sprint'], '2026-10-19')
        self.assertEqual(self.resolve(at='2026-10-25T23:30:00-03:00')['sprint'], '2026-10-19')

    def test_the_week_is_the_sao_paulo_one_not_the_utc_one(self):
        self.configure()   # 02:30 UTC of Monday the 26th is still Sunday the 25th in Sao Paulo
        self.assertEqual(self.resolve(at='2026-10-26T02:30:00+00:00')['sprint'], '2026-10-19')

    def test_without_an_instant_it_is_the_week_of_now(self):
        self.configure()
        result = self.resolve(at=None)
        self.assertTrue(result['ok'], result)
        self.assertEqual(pr.dt.date.fromisoformat(result['sprint']).weekday(), 0)

    def test_without_scrum_root_or_pattern_the_prints_stay_in_frontlights(self):
        for sync in ({'scrumRoot': None}, {'weekFolderPattern': None}):
            with self.subTest(sync=sync):
                self.configure(**sync)
                result = self.resolve()
                self.assertTrue(result['ok'], result)
                browser = (self.root / '.frontlights' / 'issues' / '1107' / 'browser').resolve()
                self.assertEqual((Path(result['evidenceDir']).resolve(), Path(result['summaryDir']).resolve(),
                                  result['inSprint'], result['sprint']), (browser, browser / 'resumo', False, None))

    def test_without_any_configuration_the_prints_stay_in_frontlights(self):
        result = self.resolve()
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['inSprint'])

    def test_it_needs_neither_roadmap_sync_enabled_nor_the_progress_block_nor_an_approval(self):
        self.configure(enabled=False)
        self.assertTrue(self.resolve()['ok'])
        self.assertFalse((self.root / '.frontlights' / 'progress-report').exists())

    def test_without_a_repository_the_folder_is_named_after_the_main_worktree(self):
        self.configure(repository=None)
        result = self.resolve()
        self.assertEqual(Path(result['evidenceDir']), self.scrum / '2026' / '19_10' / 'evidencias' / 'produto' / '1107')

    def test_a_repository_that_is_not_owner_slash_name_is_refused(self):
        for bad in ('REPOSITORY', 'OWNER/..', 'OWNER/a b', 'OWNER/REPOSITORY.'):
            with self.subTest(bad=bad):
                self.configure(repository=bad)
                self.assertFalse(self.resolve()['ok'])

    def test_the_issue_must_be_a_positive_integer_and_the_instant_carry_its_offset(self):
        self.configure()
        for issue in (None, 0, -3, '12'):
            with self.subTest(issue=issue):
                self.assertFalse(self.resolve(issue=issue)['ok'])
        for at in ('2026-10-21T10:00:00', '21/10/2026', 'agora'):
            with self.subTest(at=at):
                self.assertFalse(self.resolve(at=at)['ok'])

    def test_a_missing_scrum_root_or_a_pattern_that_leaves_it_is_refused(self):
        self.configure(scrumRoot=str(self.scrum / 'nao-existe'))
        self.assertFalse(self.resolve()['ok'])
        self.configure(weekFolderPattern='../{dd_MM}')
        self.assertFalse(self.resolve()['ok'])
        self.assertFalse((self.scrum.parent / '19_10').exists())

    def test_a_relative_scrum_root_is_refused(self):
        self.configure(scrumRoot='SCRUM')
        self.assertFalse(self.resolve()['ok'])

    def test_a_linked_worktree_uses_the_configuration_of_the_main_one(self):
        self.configure()
        linked = Path(self.tmp.name) / 'linked'
        git(self.root, 'worktree', 'add', '-q', '--detach', str(linked))
        result = self.resolve(root=linked)
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(result['evidenceDir']), self.sprint('19_10', 1107))


class CandidatesInSprintTests(EvidenceTestCase):
    def put(self, monday, issue=100, cover=None, taken='2026-10-21T10:00:00-03:00', name='101-lista.png'):
        folder = self.sprint(monday, issue) / 'resumo'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(PNG)
        item = {'file': name, 'caption': 'A lista mostra a empresa excluída.', 'issue': 101, 'cover': cover or issue,
                'repository': 'OWNER/REPOSITORY', 'takenAt': taken, 'head': 'abc', 'visibleFiles': {VISIBLE: self.blob}}
        (folder / 'candidates.json').write_text(json.dumps([item]), encoding='utf-8')
        return folder

    def candidates(self, to='2026-10-23'):
        return pr.run('candidates', str(self.root), date_to=to)

    def test_the_prints_kept_in_the_sprint_folder_are_found(self):
        self.configure()
        folder = self.put('19_10')
        result = self.candidates()
        self.assertTrue(result['ok'], result)
        [entry] = result['candidates']
        self.assertEqual((entry['usable'], entry['record'], Path(entry['file'])), (True, '100', folder / '101-lista.png'))

    def test_the_old_frontlights_folder_is_still_read_beside_the_sprint_one(self):
        self.configure()
        self.put('19_10')
        old = self.root / '.frontlights' / 'issues' / '90' / 'browser' / 'resumo'
        old.mkdir(parents=True)
        (old / 'velho.png').write_bytes(PNG)
        item = {'file': 'velho.png', 'caption': 'Antes da migração.', 'issue': 90, 'cover': 90, 'repository': 'OWNER/REPOSITORY',
                'takenAt': '2026-10-14T10:00:00-03:00', 'head': 'abc', 'visibleFiles': {VISIBLE: self.blob}}
        (old / 'candidates.json').write_text(json.dumps([item]), encoding='utf-8')
        covers = sorted(entry['cover'] for entry in self.candidates()['candidates'])
        self.assertEqual(covers, [90, 100])

    def test_only_the_sprints_up_to_the_last_day_and_within_the_lookback_are_read(self):
        self.configure()
        self.put('19_10', issue=100)
        self.put('26_10', issue=200, taken='2026-10-27T10:00:00-03:00')
        self.put('03_08', issue=300, taken='2026-08-04T10:00:00-03:00')   # 11 weeks before the 19th
        self.assertEqual([entry['cover'] for entry in self.candidates()['candidates']], [100])

    def test_another_repository_folder_of_the_same_sprint_is_never_read(self):
        self.configure()
        other = self.scrum / '2026' / '19_10' / 'evidencias' / 'OUTRO' / '100' / 'resumo'
        other.mkdir(parents=True)
        (other / 'candidates.json').write_text('[]', encoding='utf-8')
        self.assertEqual(self.candidates()['candidates'], [])

    def test_a_sprint_without_evidence_and_a_missing_scrum_root_are_not_errors(self):
        self.configure()
        (self.scrum / '2026' / '19_10').mkdir(parents=True)
        self.assertEqual(self.candidates()['candidates'], [])
        self.configure(scrumRoot=str(self.scrum / 'nao-existe'))
        result = self.candidates()
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['warnings'])

    def test_a_non_numeric_folder_in_the_repository_folder_is_skipped(self):
        self.configure()
        self.put('19_10')
        (self.scrum / '2026' / '19_10' / 'evidencias' / 'REPOSITORY' / 'notas').mkdir()
        self.assertEqual(len(self.candidates()['candidates']), 1)


class TextTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def flat(self, *parts):
        return ' '.join(self.ROOT.joinpath(*parts).read_text(encoding='utf-8').split())

    def test_the_browser_reference_saves_the_prints_where_evidence_dir_says(self):
        text = self.flat('skills', 'frontlights', 'references', 'browser-testing.md')
        for phrase in ('progress_report.py" evidence-dir', '`evidenceDir`', '`summaryDir`', '`pastaDosPrints`',
                       '`evidencias/<repository>/<n>`', 'synced and shared'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('nothing leaves the project', text)
        self.assertNotIn('These files stay in the project', text)

    def test_the_protocol_and_the_security_doc_name_the_sprint_folder(self):
        protocol = self.flat('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('`pastaDosPrints`', protocol)
        security = self.flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('`evidence-dir`', 'evidencias/<repositório>/<issue>', 'compartilhada'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn('ficam dentro do projeto e não são versionados', security)

    def test_the_summary_step_reads_the_kept_prints_from_the_sprint_folder(self):
        text = self.flat('skills', 'frontlights', 'references', 'progress-report.md')
        self.assertIn('sprint folder', text)


if __name__ == '__main__':
    unittest.main()
