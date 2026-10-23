"""The prints of the summary in the week folder (`weekShots`): where they go, what captions.json may
carry, the rule of one print per visible delivery and what the approval covers."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress_report as pr
import roads as rs
from test_progress_report import ProgressTestCase, state

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
JPEG = b'\xff\xd8\xff\xe0' + b'0' * 32


class WeekShotsTestCase(ProgressTestCase):
    def setUp(self):
        super().setUp()
        self.facts = self.project / '.frontlights' / 'facts.json'
        self.write_facts([])
        self.write_config(progress=self.week_block())
        self.draft = self.out / 'draft.json'
        self.write_draft([])

    def week_block(self, **overrides):
        block = self.block(pushCommand=[sys.executable, str(self.tools / 'push.py'), str(self.out / 'push.json'),
                                        '--draft', '{draft}', '--shots-dir', '{shotsDir}'],
                           factsFile='.frontlights/facts.json', weekShots='summary')
        block.update(overrides)
        return block

    def write_facts(self, entries):
        self.facts.write_text(json.dumps({'window': {}, 'entries': entries, 'internal': {'count': 0}}), encoding='utf-8')

    def write_draft(self, entries):
        self.draft.write_text(json.dumps({'headline': 'x', 'entries': entries}), encoding='utf-8')

    def folder(self):
        return self.out / '2026' / '05_10' / 'summary' / '30_09'

    def prints(self, captions, files=None):
        folder = self.folder()
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in (files if files is not None else {item['file']: PNG for item in captions
                                                            if isinstance(item, dict) and isinstance(item.get('file'), str)}).items():
            (folder / name).write_bytes(data)
        (folder / 'captions.json').write_text(json.dumps(captions), encoding='utf-8')

    def push(self, date_to='2026-09-30', **kwargs):
        return self.run_op('push', draft=str(self.draft), date_to=date_to, **kwargs)

    def pushed(self):
        return json.loads((self.out / 'push.json').read_text(encoding='utf-8'))


class WeekFolderTests(WeekShotsTestCase):
    def test_the_folder_is_the_one_of_the_monday_after_the_week_of_the_last_day_of_the_period(self):
        self.approved()
        for day, folder in (('2026-09-28', '28_09'), ('2026-09-30', '30_09'), ('2026-10-02', '02_10'),
                            ('2026-10-03', '03_10'), ('2026-10-04', '04_10')):
            with self.subTest(day=day):
                result = self.run_op('shots', date_to=day)
                self.assertTrue(result['ok'], result)
                self.assertEqual(Path(result['shotsDir']), self.out / '2026' / '05_10' / 'summary' / folder)
                self.assertEqual(result['presentedOn'], '2026-10-05')
        result = self.run_op('shots', date_to='2026-10-05')
        self.assertEqual(Path(result['shotsDir']), self.out / '2026' / '12_10' / 'summary' / '05_10')
        self.assertEqual(result['presentedOn'], '2026-10-12')

    def test_a_period_that_starts_on_a_weekend_follows_its_end_not_its_start(self):
        # Saturday 03/10 to Wednesday 07/10: the week of the end is 05/10, presented on 12/10.
        self.approved()
        result = self.run_op('shots', date_to='2026-10-07')
        self.assertEqual(Path(result['shotsDir']), self.out / '2026' / '12_10' / 'summary' / '07_10')
        self.assertEqual(result['presentedOn'], '2026-10-12')

    def test_two_summaries_of_one_week_never_share_a_folder(self):
        self.approved()
        wednesday = Path(self.run_op('shots', date_to='2026-10-07')['shotsDir'])
        friday = Path(self.run_op('shots', date_to='2026-10-09')['shotsDir'])
        self.assertNotEqual(wednesday, friday)
        self.assertEqual(wednesday.parent, friday.parent)
        (wednesday / 'captions.json').write_text('[{"file": "a.png", "caption": "A", "issue": 1}]', encoding='utf-8')
        self.assertFalse((friday / 'captions.json').exists())

    def test_a_meeting_from_the_service_replaces_the_local_monday_for_its_own_period(self):
        self.approved()
        result = self.run_op('shots', date_to='2026-10-07', meeting='2026-10-19')
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(result['shotsDir']), self.out / '2026' / '19_10' / 'summary' / '07_10')
        self.assertEqual(result['presentedOn'], '2026-10-19')

    def test_a_meeting_outside_the_plausible_range_never_picks_the_folder(self):
        self.approved()
        for bad in ('2020-01-06', '2026-09-28', '2026-10-05', '2027-01-04'):
            with self.subTest(bad=bad):
                result = self.run_op('shots', date_to='2026-10-07', meeting=bad)
                self.assertFalse(result['ok'])
                self.assertIn('--meeting', result['message'])
        self.assertFalse((self.out / '2020').exists())

    def test_a_meeting_that_is_not_a_monday_or_not_a_date_is_refused(self):
        self.approved()
        for bad in ('2026-10-13', '12/10/2026', '2026-02-30'):
            with self.subTest(bad=bad):
                result = self.run_op('shots', date_to='2026-10-07', meeting=bad)
                self.assertFalse(result['ok'])
                self.assertIn('--meeting', result['message'])

    def test_from_is_no_longer_the_day_of_the_folder(self):
        self.approved()
        result = self.run_op('shots', date_from='2026-09-30')
        self.assertFalse(result['ok'])
        self.assertIn('--to', result['message'])
        self.assertIn('last day', result['message'])
        pushed = self.run_op('push', draft=str(self.draft), date_from='2026-09-30')
        self.assertFalse(pushed['ok'])
        self.assertIn('--to', pushed['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_the_folder_is_created_when_missing_and_kept_when_present(self):
        self.approved()
        self.assertFalse(self.folder().exists())
        self.assertTrue(self.run_op('shots', date_to='2026-09-30')['ok'])
        self.assertTrue(self.folder().is_dir())
        (self.folder() / 'keep.png').write_bytes(PNG)
        self.assertTrue(self.run_op('shots', date_to='2026-09-30')['ok'])
        self.assertTrue((self.folder() / 'keep.png').exists())

    def test_shots_needs_the_approval_a_date_and_weekShots(self):
        result = self.run_op('shots', date_to='2026-09-30')
        self.assertFalse(result['ok'])
        self.assertIn('approve', result['message'])
        self.assertFalse(self.folder().exists())
        self.approved()
        for bad in (None, '30/09/2026', '2026-02-30', '2026-09-30; x'):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_op('shots', date_to=bad)['ok'])
        self.write_config()
        self.approved()
        self.assertIn('weekShots', self.run_op('shots', date_to='2026-09-30')['message'])

    def test_a_file_where_the_folder_should_be_is_refused(self):
        self.approved()
        self.folder().parent.mkdir(parents=True)
        self.folder().write_text('x', encoding='utf-8')
        result = self.run_op('shots', date_to='2026-09-30')
        self.assertFalse(result['ok'])
        self.assertIn('is a file', result['message'])

    def test_a_link_on_the_way_is_refused(self):
        self.approved()
        elsewhere = self.out / 'elsewhere'
        elsewhere.mkdir()
        (self.out / '2026').mkdir()
        link = self.out / '2026' / '05_10'
        if sys.platform.startswith('win'):
            import subprocess
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(elsewhere)], capture_output=True)
            if made.returncode != 0:
                self.skipTest('cannot create a junction here')
        else:
            os.symlink(elsewhere, link, target_is_directory=True)
        result = self.run_op('shots', date_to='2026-09-30')
        self.assertFalse(result['ok'])
        self.assertIn('reparse point', result['message'])
        self.assertEqual(list(elsewhere.iterdir()), [])
        # the push refuses the same way, even when the prints are already there
        (elsewhere / 'summary' / '30_09').mkdir(parents=True)
        (elsewhere / 'summary' / '30_09' / 'captions.json').write_text('[]', encoding='utf-8')
        self.assertIn('reparse point', self.push()['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_a_pattern_that_leaves_the_root_is_refused(self):
        self.write_config(progress=self.week_block(), weekFolderPattern='../{dd_MM}')
        self.approved()
        result = self.run_op('shots', date_to='2026-09-30')
        self.assertFalse(result['ok'])
        self.assertFalse((self.out.parent / '05_10').exists())


class LegacyFlatFolderTests(WeekShotsTestCase):
    """Before the day folder, the prints of a week lived directly in `weekShots`. A push still reads that
    flat folder when the day folder has no captions.json, and says so."""

    def flat(self):
        return self.out / '2026' / '05_10' / 'summary'

    def put_flat(self, captions):
        folder = self.flat()
        folder.mkdir(parents=True, exist_ok=True)
        for item in captions:
            (folder / item['file']).write_bytes(PNG)
        (folder / 'captions.json').write_text(json.dumps(captions), encoding='utf-8')

    def test_the_flat_folder_is_used_with_a_warning_when_the_day_folder_does_not_exist(self):
        self.approved()
        self.put_flat([{'file': 'a.png', 'caption': 'A'}])
        result = self.push()
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(self.pushed()['argv'][-1]), self.flat())
        self.assertTrue(any('flat folder' in warning for warning in result['warnings']))

    def test_the_day_folder_wins_when_both_exist(self):
        self.approved()
        self.put_flat([{'file': 'old.png', 'caption': 'Old'}])
        self.prints([{'file': 'new.png', 'caption': 'New'}])
        result = self.push()
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(self.pushed()['argv'][-1]), self.folder())
        self.assertNotIn('warnings', result)

    def test_an_existing_day_folder_without_captions_is_never_replaced_by_the_flat_one(self):
        self.approved()
        self.put_flat([{'file': 'old.png', 'caption': 'Old'}])
        self.folder().mkdir(parents=True)
        result = self.push()
        self.assertFalse(result['ok'])
        self.assertIn('captions.json', result['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_with_neither_folder_the_push_is_refused_before_the_command_runs(self):
        self.approved()
        result = self.push()
        self.assertFalse(result['ok'])
        self.assertFalse((self.out / 'push.json').exists())


class WindowWeekMeetingTests(WeekShotsTestCase):
    """GET progress-report may carry `weekMeeting` for the window it returns. The plugin computes the same
    day itself, uses the service's value only for that window, and warns when they differ."""

    def window(self, **extra):
        self.approved()
        self.roads.answer = (200, dict(state(start='2026-10-03T00:00:00-03:00', end='2026-10-08T00:00:00-03:00'), **extra))
        return self.run_op('window')

    def test_without_the_field_the_plugin_computes_the_monday_of_the_presentation(self):
        result = self.window()
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['to'], result['weekMeeting'], result['summaryFolder']), ('2026-10-07', '2026-10-12', '07_10'))
        self.assertNotIn('warnings', result)

    def test_the_service_value_is_used_when_it_agrees(self):
        result = self.window(weekMeeting='2026-10-12')
        self.assertEqual(result['weekMeeting'], '2026-10-12')
        self.assertNotIn('warnings', result)

    def test_a_different_service_value_wins_for_the_window_and_is_reported(self):
        result = self.window(weekMeeting='2026-10-19')
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['weekMeeting'], result['weekMeetingLocal']), ('2026-10-19', '2026-10-12'))
        self.assertTrue(any('weekMeeting' in warning for warning in result['warnings']))

    def test_an_invalid_service_value_is_refused(self):
        for value in ('2026-10-13', '12/10/2026', 20261012, True, '2026-02-30'):
            with self.subTest(value=value):
                result = self.window(weekMeeting=value)
                self.assertFalse(result['ok'])
                self.assertIn('weekMeeting', result['message'])

    def test_a_null_service_value_counts_as_absent(self):
        result = self.window(weekMeeting=None)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['weekMeeting'], '2026-10-12')
        self.assertNotIn('warnings', result)

    def test_a_meeting_that_is_implausible_for_the_period_is_refused(self):
        # Wednesday 07/10 is presented on 12/10; a Monday before the period's end, or months away, is a stale value.
        for value in ('2026-10-05', '2026-09-28', '2020-01-06', '2027-01-04'):
            with self.subTest(value=value):
                result = self.window(weekMeeting=value)
                self.assertFalse(result['ok'])
                self.assertIn('weekMeeting', result['message'])
        for value in ('2026-10-19', '2026-12-07'):   # later is allowed, up to eight weeks after the usual Monday
            with self.subTest(value=value):
                self.assertTrue(self.window(weekMeeting=value)['ok'])

    def test_the_window_is_read_in_the_Sao_Paulo_calendar_whatever_offset_the_answer_uses(self):
        self.approved()
        # 2026-10-03 03:00Z to 2026-10-08 03:00Z is Saturday 03/10 00:00 to Thursday 08/10 00:00 in Sao Paulo.
        self.roads.answer = (200, state(start='2026-10-03T03:00:00Z', end='2026-10-08T03:00:00Z'))
        result = self.run_op('window')
        self.assertEqual((result['from'], result['to'], result['weekMeeting']), ('2026-10-03', '2026-10-07', '2026-10-12'))
        self.roads.answer = (200, state(start='2026-10-05T03:00:00Z', end='2026-10-12T03:00:00Z'))
        result = self.run_op('window')
        self.assertEqual((result['from'], result['to'], result['weekMeeting']), ('2026-10-05', '2026-10-11', '2026-10-12'))

    def test_a_window_that_ends_on_a_monday_midnight_belongs_to_the_week_that_ended(self):
        self.approved()
        self.roads.answer = (200, state(start='2026-09-28T00:00:00-03:00', end='2026-10-05T00:00:00-03:00'))
        result = self.run_op('window')
        self.assertEqual((result['to'], result['weekMeeting']), ('2026-10-04', '2026-10-05'))


class WeekBlockTests(WeekShotsTestCase):
    def test_weekShots_is_one_folder_name(self):
        for bad in ('', ' ', '../x', 'a/b', 'a\\b', '.hidden', 'x.', 'x ', 'C:', '~', 5, 'a' * 65, 'sum mary'):
            with self.subTest(bad=bad):
                self.write_config(progress=self.week_block(weekShots=bad))
                result = self.run_op('status')
                self.assertFalse(result['valid'])
                self.assertIn('weekShots', result['message'])
                self.assertFalse(self.run_op('approve')['ok'])

    def test_shotsDir_and_weekShots_together_are_refused(self):
        self.write_config(progress=self.week_block(shotsDir='.frontlights/progress/shots'))
        self.assertIn('not both', self.run_op('status')['message'])

    def test_the_placeholder_and_the_facts_file_go_with_weekShots_only(self):
        self.write_config(progress=self.week_block(pushCommand=[sys.executable, 'push.py', '{draft}']))
        self.assertIn('{shotsDir}', self.run_op('status')['message'])
        self.write_config(progress=self.week_block(factsFile=None))
        self.assertIn('factsFile', self.run_op('status')['message'])
        self.write_config(progress=self.block(pushCommand=[sys.executable, 'push.py', '{draft}', '{shotsDir}']))
        self.assertIn('only weekShots', self.run_op('status')['message'])

    def test_a_root_that_is_not_fully_qualified_is_refused(self):
        for bad in ('rel', '..\\algo', 'C:pasta', '%FRONTLIGHTS_UNSET_VAR_X%\\Scrum'):
            with self.subTest(bad=bad):
                self.write_config(progress=self.week_block(), scrumRoot=bad)
                result = self.run_op('status')
                self.assertFalse(result['valid'])
                self.assertIn('fully qualified', result['message'])

    def test_the_placeholder_must_be_a_whole_argument(self):
        self.write_config(progress=self.week_block(pushCommand=[sys.executable, 'push.py', '{draft}', '--dir={shotsDir}']))
        self.assertIn('whole argument', self.run_op('status')['message'])

    def test_the_week_end_follows_the_sprint_week(self):
        self.write_config(progress=self.week_block(), weekFolderPattern='{yyyy}/{dd_MM}_a_{dd_MM}')
        self.approved()
        result = self.run_op('shots', date_to='2026-09-30')
        self.assertEqual(Path(result['shotsDir']), self.out / '2026' / '05_10_a_09_10' / 'summary' / '30_09')

    def test_status_reports_where_the_prints_go(self):
        result = self.run_op('status')
        self.assertTrue(result['valid'], result)
        self.assertEqual((result['weekShots'], result['weekFolderPattern']), ('summary', '{yyyy}/{dd_MM}'))
        self.assertEqual(Path(result['scrumRoot']), self.out)

    def test_the_root_the_pattern_and_the_folder_are_part_of_the_approval(self):
        self.approved()
        self.assertEqual(self.run_op('status')['approval'], 'approved')
        other = self.out / 'other'
        other.mkdir()
        for change in ({'scrumRoot': str(other)}, {'weekFolderPattern': '{yyyy}/W{dd_MM}'}):
            with self.subTest(change=change):
                self.write_config(progress=self.week_block(), **change)
                self.assertEqual(self.run_op('status')['approval'], 'changed')
        self.write_config(progress=self.week_block(weekShots='prints'))
        self.assertEqual(self.run_op('status')['approval'], 'changed')

    def test_a_block_without_weekShots_keeps_its_approval_when_the_root_changes(self):
        self.write_config()
        self.approved()
        other = self.out / 'other'
        other.mkdir()
        self.write_config(scrumRoot=str(other))
        self.assertEqual(self.run_op('status')['approval'], 'approved')


class CaptionsTests(WeekShotsTestCase):
    def setUp(self):
        super().setUp()
        self.approved()

    def test_a_valid_set_is_pushed_with_the_folder_and_no_shot_arguments(self):
        self.prints([{'file': '101-tela.png', 'caption': 'Uma frase.', 'issue': 101},
                     {'file': 'geral.jpg', 'caption': 'Sem issue.'}],
                    files={'101-tela.png': PNG, 'geral.jpg': JPEG})
        result = self.push()
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.pushed()['argv'], ['--draft', str(self.draft.resolve()), '--shots-dir', str(self.folder())])

    def test_an_empty_list_is_fine_when_no_delivery_needs_a_print(self):
        self.prints([])
        self.assertTrue(self.push()['ok'])

    def test_push_needs_the_date_and_refuses_shot_arguments(self):
        self.prints([])
        self.assertFalse(self.push(date_to=None)['ok'])
        shot = self.out / 'a.png'
        shot.write_bytes(PNG)
        result = self.push(shots=[str(shot)])
        self.assertFalse(result['ok'])
        self.assertIn('--shot', result['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_a_missing_folder_or_captions_file_is_refused(self):
        result = self.push()
        self.assertFalse(result['ok'])
        self.folder().mkdir(parents=True)
        self.assertIn('captions.json', self.push()['message'])
        (self.folder() / 'captions.json').write_text('{not json', encoding='utf-8')
        self.assertIn('captions.json', self.push()['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_bad_items_are_refused_before_the_command_runs(self):
        cases = [
            ({'file': 'a.png'}, {}),
            ({'file': 'a.png', 'caption': ' '}, None),
            ({'file': 'a.png', 'caption': 'x', 'issue': '101'}, None),
            ({'file': 'a.png', 'caption': 'x', 'issue': True}, None),
            ({'file': 'a.png', 'caption': 'x', 'issue': 0}, None),
            ({'file': 'a.png', 'caption': 'x', 'issue': 1.5}, None),
            ({'file': 'a.png', 'caption': 'x', 'extra': 1}, None),
            ({'file': '../a.png', 'caption': 'x'}, {}),
            ({'file': 'sub/a.png', 'caption': 'x'}, {}),
            ({'file': 'a.gif', 'caption': 'x'}, None),
            ({'file': '.png', 'caption': 'x'}, {}),
            ({'file': 'nope.png', 'caption': 'x'}, {}),
            ({'file': 'fake.png', 'caption': 'x'}, {'fake.png': b'GIF89a' + b'0' * 20}),
            ({'file': 'big.png', 'caption': 'x'}, {'big.png': PNG + b'0' * pr.MAX_SHOT_BYTES}),
            ('a.png', {}),
        ]
        for item, files in cases:
            with self.subTest(item=item):
                self.prints([item], files=files)
                result = self.push()
                self.assertFalse(result['ok'], result)
                self.assertIn('captions.json', result['message'])
                self.assertFalse((self.out / 'push.json').exists())

    def test_at_most_forty_prints_and_no_repeated_file(self):
        many = [{'file': f'p{n}.png', 'caption': 'x'} for n in range(pr.MAX_SHOTS + 1)]
        self.prints(many)
        self.assertIn('at most 40', self.push()['message'])
        self.prints(many[:pr.MAX_SHOTS])
        self.assertTrue(self.push()['ok'])
        self.prints([{'file': 'a.png', 'caption': 'x'}, {'file': 'A.PNG', 'caption': 'y'}], files={'a.png': PNG})
        self.assertIn('repeats', self.push()['message'])

    def test_the_captions_file_itself_is_checked(self):
        self.folder().mkdir(parents=True)
        (self.folder() / 'captions.json').write_text('[' + ' ' * pr.MAX_CAPTIONS_BYTES + ']', encoding='utf-8')
        self.assertIn('256 KB', self.push()['message'])
        (self.folder() / 'captions.json').unlink()
        (self.folder() / 'captions.json').mkdir()
        self.assertIn('captions.json', self.push()['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_a_folder_named_like_an_image_is_refused(self):
        self.prints([{'file': 'x.png', 'caption': 'x'}], files={})
        (self.folder() / 'x.png').mkdir()
        result = self.push()
        self.assertFalse(result['ok'])
        self.assertIn('not a file', result['message'])

    def test_a_value_holding_a_placeholder_is_not_substituted_again(self):
        self.assertEqual(pr.substitute(['--draft', '{draft}', '{shotsDir}'], {'draft': 'C:/x/{shotsDir}.json', 'shotsDir': 'D:/w'}),
                         ['--draft', 'C:/x/{shotsDir}.json', 'D:/w'])
        self.assertEqual(pr.substitute(['a{from}b'], {}), ['a{from}b'])

    def test_exactly_one_megabyte_is_accepted(self):
        self.prints([{'file': 'edge.png', 'caption': 'x'}], files={'edge.png': PNG + b'0' * (pr.MAX_SHOT_BYTES - len(PNG))})
        self.assertTrue(self.push()['ok'])

    def test_an_online_only_cloud_file_is_refused(self):
        self.prints([{'file': 'a.png', 'caption': 'x'}])
        real = os.stat

        class Offline:
            def __init__(self, info):
                self.st_mode, self.st_size, self.st_file_attributes = info.st_mode, info.st_size, rs.OFFLINE_MASK

        with patch.object(pr.os, 'stat', side_effect=lambda path, *a, **k: Offline(real(path)) if str(path).endswith('a.png') else real(path, *a, **k)):
            result = self.push()
        self.assertFalse(result['ok'])
        self.assertIn('online-only', result['message'])


class BeforeTests(WeekShotsTestCase):
    """Issue 74, S3: a entrada do print do depois leva, opcional, o print do antes em `before`, na mesma pasta, com a
    mesma regra de nome, formato e tamanho; o par conta como um dos 40."""

    def setUp(self):
        super().setUp()
        self.approved()

    def test_a_print_with_its_before_is_pushed(self):
        self.prints([{'file': 'depois-1123-S1.png', 'caption': 'A tabela com a coluna nova.', 'issue': 1123,
                      'before': 'antes-1123-S1.png'}],
                    files={'depois-1123-S1.png': PNG, 'antes-1123-S1.png': JPEG})
        result = self.push()
        self.assertTrue(result['ok'], result)

    def test_a_bad_before_is_refused_naming_the_file(self):
        cases = [
            ({}, 'antes-1123-S1.png'),
            ({'antes-1123-S1.png': b'GIF89a' + b'0' * 20}, 'antes-1123-S1.png'),
            ({'antes-1123-S1.png': PNG + b'0' * pr.MAX_SHOT_BYTES}, 'antes-1123-S1.png'),
        ]
        for extra, name in cases:
            with self.subTest(extra=list(extra)):
                self.prints([{'file': 'depois-1123-S1.png', 'caption': 'x', 'issue': 1123, 'before': name}],
                            files={'depois-1123-S1.png': PNG, **extra})
                result = self.push()
                self.assertFalse(result['ok'], result)
                self.assertIn('before', result['message'])
                self.assertIn(name, result['message'])
                self.assertFalse((self.out / 'push.json').exists())
        for name in ('antes#1123-S1.png', '../antes.png', '', 3):
            with self.subTest(name=name):
                self.prints([{'file': 'depois-1123-S1.png', 'caption': 'x', 'before': name}],
                            files={'depois-1123-S1.png': PNG})
                result = self.push()
                self.assertFalse(result['ok'], result)
                self.assertIn('before', result['message'])

    def test_the_before_is_never_the_same_file_as_a_print(self):
        self.prints([{'file': 'a.png', 'caption': 'x', 'before': 'a.png'}], files={'a.png': PNG})
        self.assertIn('before', self.push()['message'])

    def test_the_pair_counts_as_one_of_the_forty(self):
        many = [{'file': f'p{n}.png', 'caption': 'x', 'before': f'b{n}.png'} for n in range(pr.MAX_SHOTS)]
        files = {**{f'p{n}.png': PNG for n in range(pr.MAX_SHOTS)}, **{f'b{n}.png': PNG for n in range(pr.MAX_SHOTS)}}
        self.prints(many, files=files)
        self.assertTrue(self.push()['ok'])

    def test_one_before_may_serve_two_prints(self):
        self.prints([{'file': 'd1.png', 'caption': 'x', 'before': 'antes.png'},
                     {'file': 'd2.png', 'caption': 'y', 'before': 'antes.png'}],
                    files={'d1.png': PNG, 'd2.png': PNG, 'antes.png': PNG})
        self.assertTrue(self.push()['ok'])


class OnePrintPerDeliveryTests(WeekShotsTestCase):
    def setUp(self):
        super().setUp()
        self.approved()

    def fact(self, issue, status='em_andamento', hidden=None):
        entry = {'issue': issue, 'status': status, 'id': f'x-{issue}', 'sources': []}
        if hidden is not None:
            entry['hidden'] = hidden
        return entry

    def test_a_visible_delivery_without_its_print_is_refused_with_its_number(self):
        self.write_facts([self.fact(101), self.fact(102, 'concluido'), self.fact(103, 'bloqueado')])
        self.prints([{'file': 'a.png', 'caption': 'x', 'issue': 102}])
        result = self.push()
        self.assertFalse(result['ok'])
        self.assertIn('#101', result['message'])
        self.assertIn('#103', result['message'])
        self.assertNotIn('#102', result['message'])
        self.assertFalse((self.out / 'push.json').exists())

    def test_every_status_but_proximo_needs_a_print(self):
        for status in ('concluido', 'em_validacao', 'em_andamento', 'bloqueado'):
            with self.subTest(status=status):
                self.write_facts([self.fact(7, status)])
                self.prints([])
                self.assertIn('#7', self.push()['message'])
        self.write_facts([self.fact(7, 'proximo')])
        self.prints([])
        self.assertTrue(self.push()['ok'])

    def test_the_texts_file_hidden_wins_over_the_collector(self):
        self.write_facts([self.fact(1, hidden=True), self.fact(2), self.fact(3, hidden=True)])
        self.write_draft([{'issue': 1, 'title': 't', 'summary': 's', 'hidden': False},
                          {'issue': 2, 'title': 't', 'summary': 's', 'hidden': True},
                          {'issue': 3, 'title': 't', 'summary': 's', 'hidden': 'no'}])
        self.prints([])
        result = self.push()
        self.assertIn('#1', result['message'])
        self.assertNotIn('#2', result['message'])
        self.assertNotIn('#3', result['message'])

    def test_only_a_collector_hidden_true_hides_like_the_strict_equality_in_RoadS(self):
        self.write_facts([self.fact(8, hidden='yes'), self.fact(9, hidden=1), self.fact(10, hidden=True)])
        self.prints([])
        result = self.push()
        self.assertIn('#8', result['message'])
        self.assertIn('#9', result['message'])
        self.assertNotIn('#10', result['message'])

    def test_a_delivery_takes_a_single_print_and_the_second_is_refused(self):
        self.write_facts([self.fact(101), self.fact(102)])
        self.prints([{'file': 'a.png', 'caption': 'x', 'issue': 101}, {'file': 'b.png', 'caption': 'y', 'issue': 101},
                     {'file': 'c.png', 'caption': 'z', 'issue': 102}])
        result = self.push()
        self.assertFalse(result['ok'])
        self.assertIn('single print per delivery', result['message'])
        self.assertIn('#101', result['message'])
        self.assertNotIn('#102', result['message'])
        self.assertFalse((self.out / 'push.json').exists())
        self.prints([{'file': 'a.png', 'caption': 'x', 'issue': 101}, {'file': 'c.png', 'caption': 'z', 'issue': 102}])
        self.assertTrue(self.push()['ok'])

    def test_prints_without_an_issue_are_not_counted_as_repeats(self):
        self.write_facts([self.fact(101)])
        self.prints([{'file': 'a.png', 'caption': 'x', 'issue': 101}, {'file': 'b.png', 'caption': 'y'},
                     {'file': 'c.png', 'caption': 'z'}])
        self.assertTrue(self.push()['ok'])

    def test_a_print_without_issue_does_not_count_for_a_delivery(self):
        self.write_facts([self.fact(5)])
        self.prints([{'file': 'a.png', 'caption': 'x'}])
        self.assertIn('#5', self.push()['message'])

    def test_entries_without_an_integer_issue_are_ignored_like_RoadS_does(self):
        self.write_facts([{'issue': '5', 'status': 'em_andamento'}, {'issue': True, 'status': 'concluido'},
                          {'status': 'concluido'}, 'x'])
        self.write_draft([{'issue': '5', 'hidden': False}])
        self.prints([])
        self.assertTrue(self.push()['ok'])

    def test_malformed_facts_or_draft_are_refused(self):
        self.prints([])
        self.facts.write_text('[]', encoding='utf-8')
        self.assertIn('facts', self.push()['message'])
        self.facts.unlink()
        self.assertIn('factsFile', self.push()['message'])
        self.write_facts([])
        self.draft.write_text('{"headline": "x"}', encoding='utf-8')
        self.assertIn('draft', self.push()['message'])

    def test_rule_matches_the_contract_function(self):
        facts = {'entries': [self.fact(1), self.fact(1), self.fact(2, 'proximo')]}
        self.assertEqual(pr.deliveries_without_prints(facts, {'entries': []}, []), [1])


class ShotsDocumentationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def read(self, *parts):
        return self.ROOT.joinpath(*parts).read_text(encoding='utf-8')

    def test_the_reference_describes_the_week_folder_step(self):
        text = self.read('skills', 'frontlights', 'references', 'progress-report.md')
        for needle in ('weekShots', 'shots --to', '--meeting <weekMeeting>', 'weekMeeting', '{shotsDir}', '"issue"', 'proximo',
                       '40', '1 MB', 'push --draft <file> --to'):
            self.assertIn(needle, text)

    def test_security_and_readme_describe_the_write_outside_the_project(self):
        self.assertIn('weekShots', self.read('skills', 'frontlights', 'docs', 'security.md'))
        config = json.loads(self.read('skills', 'frontlights', 'examples', 'config.json'))
        self.assertNotIn('weekShots', config['roadmapSync']['progress'])


if __name__ == '__main__':
    unittest.main()
