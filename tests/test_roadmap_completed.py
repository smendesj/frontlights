"""Roadmap sync records the items RoadS shows as done (`done` true in `roadmap-state`) as synthetic
`completed` changes: the same plan, marker, staged copy, diff, backup and verification as the changes of the
queue, but with nothing to acknowledge at RoadS.

Seams: `roadmap_sync.run('fetch' | 'apply' | 'ack' | 'rotate-markers' | 'status', ...)` with the HTTP transport
simulated, on top of the base class and the fixtures of test_roadmap_sync.
"""

import datetime as dt
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import roadmap_sync as rs
from test_roadmap_sync import (CURRENT, NEXT, REMOVE_ID, ADD_ID, MOVE_ID, MONDAY, RoadmapSyncTestCase, Transport,
                               fetch_answers, fixture, state_fixture)

ITEM_B = '5a5a5a5a-0000-4000-8000-00000000000b'   # current sprint, position 1, has a pending modify
ITEM_E = '5a5a5a5a-0000-4000-8000-00000000000e'   # current sprint, position 3, no pending change
ITEM_A = '5a5a5a5a-0000-4000-8000-00000000000a'   # next sprint, position 1
DONE_E = 'done-' + ITEM_E
DONE_B = 'done-' + ITEM_B
DONE_A = 'done-' + ITEM_A
MODIFY_ID = '7f1c2d3e-0000-4000-8000-000000000002'
AS_OF = '2026-09-28T12:00:00.000Z'
NO_CHANGES = {'asOf': AS_OF, 'changes': []}


def done_state(*picks):
    """The state fixture with items done: (sprint index, item index) pairs; by default item e of the current sprint."""
    state = state_fixture()
    for sprint, index in picks or ((0, 2),):
        state['sprints'][sprint]['items'][index].update(done=True, status='done')
    return state


class CompletedTestCase(RoadmapSyncTestCase):
    @property
    def sync_dir(self):
        return self.project / '.frontlights' / 'roadmap-sync'

    def nonce(self):
        return json.loads((self.sync_dir / 'marker.json').read_text(encoding='utf-8'))['nonce']

    def fetch_again(self, payload=None, state=None, **kwargs):
        return self.run_op('fetch', Transport(*fetch_answers(payload, state)), **kwargs)

    def only_completions(self, state=None, **kwargs):
        """One fetch where RoadS queued nothing and an item shows as done."""
        return self.approve_and_fetch(NO_CHANGES, state=state or done_state(), **kwargs)

    def write_plan_and_apply(self, state=None, payload=None, declined=(), skip=(), transport=None, **kwargs):
        result, _ = self.approve_and_fetch(payload if payload is not None else NO_CHANGES, state=state or done_state())
        self.assertTrue(result['ok'], result['message'])
        self.draft(result['plan'], declined=declined, skip=skip)
        return result['plan'], self.run_op('apply', transport or Transport(), **kwargs)


class WhatBecomesACompletionTests(CompletedTestCase):
    def test_a_done_item_of_the_current_sprint_becomes_a_synthetic_completion(self):
        result, transport = self.only_completions()
        self.assertTrue(result['ok'], result['message'])
        self.assertNotIn('Nothing pending', result['message'])
        self.assertEqual([c['url'].rsplit('/', 1)[1] for c in transport.calls], ['sync-board', 'roadmap-state', 'pending-changes'])
        plan = result['plan']
        self.assertEqual(list(plan['targets']), ['roadmap', CURRENT])
        change, = plan['changes']
        self.assertEqual((change['id'], change['action'], change['knownAction'], change['synthetic'], change['needsIssue']),
                         (DONE_E, 'completed', True, True, False))
        self.assertEqual(change['itemId'], ITEM_E)
        self.assertEqual(change['sprintTargets'], [CURRENT])
        self.assertEqual((change['completedOn'], change['completedOnMeans']), ('2026-09-28', 'sync date'))
        self.assertEqual({key: change['item'][key] for key in ('title', 'produto', 'prioridade', 'effort', 'githubIssueUrl', 'lane')},
                         {'title': 'Item sem mudança', 'produto': 'Example Product', 'prioridade': 'Low', 'effort': 'Low',
                          'githubIssueUrl': None, 'lane': 'Sprint da semana'})
        self.assertEqual(plan['pending'], [DONE_E])
        self.assertEqual(plan['targets'][CURRENT]['changeIds'], [DONE_E])
        self.assertNotIn('outOfLimitChangeIds', plan['targets'][CURRENT])
        self.assertEqual(plan['completed'], {'enabled': True, 'new': 1, 'alreadyRecorded': 0,
                                             'completedOn': '2026-09-28', 'completedOnMeans': 'sync date'})
        self.assertRegex(change['marker'], r'^<!-- roads:done-\S+ [0-9a-f]{16} -->$')
        self.assertRegex(change['declinedMarker'], r'^<!-- roads:done-\S+ [0-9a-f]{16} declined -->$')
        self.assertTrue(re.fullmatch(rs.ID_PATTERN, change['id']))
        for name, target in plan['targets'].items():
            self.assertEqual(Path(target['staged']).read_text(encoding='utf-8'), Path(target['path']).read_text(encoding='utf-8'), name)
        for private in ('_created', '_move', '_sprints'):
            self.assertNotIn(private, change)
        self.assertNotIn(self.nonce(), json.dumps(result))

    def test_the_marker_is_the_local_hmac_of_the_derived_id(self):
        result, _ = self.only_completions()
        change = result['plan']['changes'][0]
        self.assertEqual(change['marker'], rs.marker_text(DONE_E, self.nonce()))
        self.assertEqual(rs.marker_inventory(change['marker'], self.nonce()), {DONE_E: 'applied'})
        self.assertEqual(rs.marker_inventory(change['marker'], rs.new_nonce()), {})

    def test_a_done_item_of_the_next_sprint_goes_to_that_sprints_new_file(self):
        result, _ = self.only_completions(state=done_state((1, 0)))
        self.assertTrue(result['ok'], result['message'])
        plan = result['plan']
        change, = plan['changes']
        self.assertEqual((change['id'], change['sprintTargets']), (DONE_A, [NEXT]))
        self.assertEqual(list(plan['targets']), ['roadmap', NEXT])
        target = plan['targets'][NEXT]
        self.assertEqual(target['path'], str(self.scrum / '2026' / '05_10' / 'SPRINT_05_10_a_09_10.md'))
        self.assertEqual((target['exists'], target['createsFolder'], target['changeIds']), (False, True, [DONE_A]))
        self.assertEqual(Path(target['staged']).read_bytes(), b'')

    def test_what_is_not_done_in_a_sprint_within_the_limit_is_not_a_completion(self):
        def in_group(state):
            moved = {k: v for k, v in state['sprints'][0]['items'].pop(2).items() if k != 'overLimit'}
            state['groups'][0]['items'].append(dict(moved, done=True, status='done'))

        def status_without_the_flag(state):
            state['sprints'][0]['items'][2].update(status='done', done=False)

        def text_and_issue_are_not_evidence(state):
            state['sprints'][0]['items'][2].update(title='Concluída (done)', description='status: done, issue fechada',
                                                   githubIssueUrl='https://github.com/OWNER/REPOSITORY/issues/99',
                                                   issueNumber=99, status='development', done=False)

        cases = {'a group item': in_group,
                 'status done without the flag': status_without_the_flag, 'text and a closed issue': text_and_issue_are_not_evidence}
        for label, mutate in cases.items():
            with self.subTest(label):
                state = state_fixture()
                mutate(state)
                result, _ = self.approve_and_fetch(NO_CHANGES, state=state, discard_staged=True)
                self.assertTrue(result['ok'], result['message'])
                self.assertEqual(result['pending'], 0)
                self.assertIn('Nothing pending', result['message'])
                self.assertEqual(result['completed']['new'], 0)
                self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_a_done_item_past_the_limit_is_a_completion_in_its_week(self):
        state = state_fixture()
        items = state['sprints'][0]['items']
        items.append(dict(items[2], id='5a5a5a5a-0000-4000-8000-00000000000f', position=4, title='Quarto item'))
        items.append(dict(items[2], id='5a5a5a5a-0000-4000-8000-000000000010', position=5, title='Quinto item',
                          overLimit=True, done=True, status='done'))
        result, _ = self.approve_and_fetch(NO_CHANGES, state=state)
        self.assertTrue(result['ok'], result['message'])
        self.assertNotIn('Nothing pending', result['message'])
        change, = result['plan']['changes']
        self.assertEqual((change['action'], change['itemId'], change['item']['title']),
                         ('completed', '5a5a5a5a-0000-4000-8000-000000000010', 'Quinto item'))
        self.assertEqual(change['sprintTargets'], [CURRENT])
        self.assertEqual(result['completed']['new'], 1)

    def test_a_done_item_without_a_title_is_left_out_and_reported(self):
        state = done_state()
        state['sprints'][0]['items'][2]['title'] = '  '
        result, _ = self.approve_and_fetch(NO_CHANGES, state=state)
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(result['pending'], 0)
        self.assertEqual(result['completed']['new'], 0)
        self.assertEqual(result['completed']['withoutTitle'], 1)
        self.assertIn('no title', result['message'])
        self.assertFalse((self.sync_dir / 'plan.json').exists())
        titled = done_state((0, 2), (0, 0))
        titled['sprints'][0]['items'][2]['title'] = ''
        mixed, _ = self.approve_and_fetch(NO_CHANGES, state=titled)
        self.assertEqual([c['id'] for c in mixed['plan']['changes']], [DONE_B])
        self.assertEqual(mixed['plan']['completed']['withoutTitle'], 1)

    def test_several_done_items_are_listed_by_sprint_and_position(self):
        result, _ = self.only_completions(state=done_state((0, 2), (1, 0), (0, 0)))
        self.assertEqual([c['id'] for c in result['plan']['changes']], [DONE_B, DONE_E, DONE_A])
        self.assertEqual(result['plan']['completed']['new'], 3)
        self.assertEqual(list(result['plan']['targets']), ['roadmap', CURRENT, NEXT])

    def test_one_item_listed_done_in_two_sprints_is_one_completion_for_both_files(self):
        state = done_state()
        state['sprints'][1]['items'][0] = dict(state['sprints'][0]['items'][2], position=1)
        result, _ = self.only_completions(state=state)
        change, = result['plan']['changes']
        self.assertEqual((change['id'], change['sprintTargets']), (DONE_E, [CURRENT, NEXT]))

    def test_a_long_item_id_gets_a_stable_valid_id(self):
        long_id = 'i' + 'a' * 125
        state = done_state()
        state['sprints'][0]['items'][2]['id'] = long_id
        first, _ = self.only_completions(state=state)
        change, = first['plan']['changes']
        self.assertRegex(change['id'], rs.ID_PATTERN)
        self.assertEqual(change['itemId'], long_id)
        self.assertNotEqual(change['id'], 'done-' + long_id)
        self.assertEqual(rs.completion_id(long_id), change['id'])
        self.assertNotEqual(rs.completion_id('j' + 'a' * 125), change['id'])
        self.assertEqual(rs.completion_id(ITEM_E), DONE_E)
        self.draft(first['plan'])
        self.assertTrue(self.run_op('apply')['ok'])
        self.assertEqual(rs.marker_state(self.roadmap.read_text(encoding='utf-8'), change['id'], self.nonce()), 'applied')
        second = self.fetch_again(NO_CHANGES, state)
        self.assertEqual(second['completed']['alreadyRecorded'], 1)

    def test_a_queued_change_with_the_id_of_a_completion_is_refused(self):
        payload = fixture()
        payload['changes'][0]['id'] = DONE_E
        result, _ = self.approve_and_fetch(payload, state=done_state())
        self.assertFalse(result['ok'])
        self.assertIn(DONE_E, result['message'])
        self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_real_and_synthetic_changes_share_one_plan_and_the_real_ones_come_first(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.assertTrue(result['ok'], result['message'])
        plan = result['plan']
        self.assertEqual([c['synthetic'] for c in plan['changes']], [False, False, False, False, True])
        self.assertEqual(plan['changes'][-1]['id'], DONE_E)
        self.assertEqual(len(plan['pending']), 5)
        self.assertEqual(plan['targets'][CURRENT]['changeIds'], sorted([MODIFY_ID, MOVE_ID, DONE_E]))
        self.assertEqual(plan['asOf'], AS_OF)
        self.assertEqual(plan['completed']['new'], 1)
        self.assertIn('1 completion(s)', result['message'])

    def test_a_done_item_that_also_has_a_pending_change_gets_both(self):
        result, _ = self.approve_and_fetch(state=done_state((0, 0)))
        by_id = {c['id']: c for c in result['plan']['changes']}
        self.assertEqual(by_id[DONE_B]['sprintTargets'], [CURRENT])
        self.assertEqual(by_id[MODIFY_ID]['sprintTargets'], [CURRENT])
        self.assertFalse(by_id[MODIFY_ID]['synthetic'])


class ConfigurationTests(CompletedTestCase):
    def test_mark_completed_defaults_to_true_and_is_reported_by_status(self):
        self.assertIs(self.run_op('status')['markCompleted'], True)
        self.write_config(markCompleted=True)
        self.assertIs(self.run_op('status')['markCompleted'], True)
        self.write_config(markCompleted=False)
        self.assertIs(self.run_op('status')['markCompleted'], False)

    def test_false_turns_the_completions_off(self):
        self.write_config(markCompleted=False)
        result, _ = self.only_completions()
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(result['pending'], 0)
        self.assertIn('Nothing pending', result['message'])
        self.assertEqual(result['completed'], {'enabled': False, 'new': 0, 'alreadyRecorded': 0,
                                               'completedOn': '2026-09-28', 'completedOnMeans': 'sync date'})
        self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_false_leaves_the_queue_exactly_as_it_was(self):
        self.write_config(markCompleted=False)
        result, _ = self.approve_and_fetch(state=done_state())
        plan = result['plan']
        self.assertEqual(len(plan['changes']), 4)
        self.assertFalse(any(c['synthetic'] for c in plan['changes']))
        self.assertEqual(plan['completed']['enabled'], False)
        self.assertEqual(plan['targets'][CURRENT]['changeIds'], sorted([MODIFY_ID, MOVE_ID]))

    def test_a_value_that_is_not_true_or_false_is_refused(self):
        self.assertTrue(self.run_op('approve')['ok'])
        for bad in ('false', 'true', 'sim', 1, 0, None, [], {}):
            with self.subTest(bad=bad):
                self.write_config(markCompleted=bad)
                status = self.run_op('status')
                self.assertFalse(status['configured'])
                self.assertIn('markCompleted', status['message'])
                transport = Transport(*fetch_answers(NO_CHANGES, done_state()))
                fetched = self.run_op('fetch', transport)
                self.assertFalse(fetched['ok'])
                self.assertIn('markCompleted', fetched['message'])
                self.assertEqual(transport.calls, [])

    def test_the_example_configuration_documents_the_key(self):
        example = json.loads((Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))
        self.assertIs(example['roadmapSync']['markCompleted'], True)


class DateTests(CompletedTestCase):
    def test_completed_on_is_the_day_of_the_sync_not_of_the_delivery(self):
        for today, expected in ((dt.date(2026, 9, 28), '2026-09-28'), (dt.date(2026, 9, 30), '2026-09-30'),
                                (dt.date(2026, 10, 3), '2026-10-03')):
            with self.subTest(today=today):
                result, _ = self.only_completions(today=today, discard_staged=True)
                change, = result['plan']['changes']
                self.assertEqual((change['completedOn'], change['completedOnMeans']), (expected, 'sync date'))
                self.assertEqual(result['plan']['completed']['completedOn'], expected)

    def test_today_is_the_calendar_day_in_sao_paulo(self):
        utc = dt.timezone.utc
        self.assertEqual(rs.sao_paulo_today(dt.datetime(2026, 10, 6, 2, 59, tzinfo=utc)), dt.date(2026, 10, 5))
        self.assertEqual(rs.sao_paulo_today(dt.datetime(2026, 10, 6, 3, 0, tzinfo=utc)), dt.date(2026, 10, 6))
        self.assertEqual(rs.sao_paulo_today(dt.datetime(2026, 10, 5, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-3)))),
                         dt.date(2026, 10, 5))
        self.assertIsInstance(rs.sao_paulo_today(), dt.date)

    def test_run_without_today_uses_the_sao_paulo_day(self):
        self.assertTrue(self.run_op('approve')['ok'])
        with patch.object(rs, 'sao_paulo_today', return_value=dt.date(2026, 9, 29)):
            result = rs.run('fetch', str(self.project), transport=Transport(*fetch_answers(NO_CHANGES, done_state())))
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(result['plan']['changes'][0]['completedOn'], '2026-09-29')
        self.assertEqual(result['plan']['week'], {'start': '2026-09-28', 'end': '2026-10-02'})


class ApplyAndAcknowledgeTests(CompletedTestCase):
    def test_only_completions_are_written_and_verified_and_nothing_is_acknowledged(self):
        before_roadmap, before_sprint = self.roadmap.read_text(encoding='utf-8'), self.sprint.read_text(encoding='utf-8')
        transport = Transport()
        plan, applied = self.write_plan_and_apply(transport=transport)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual((applied['exitCode'], applied['ack'], applied['verified']), (0, 'not_needed', True))
        self.assertIn('No acknowledgement is needed', applied['message'])
        self.assertEqual(transport.calls, [])
        self.assertEqual(sorted(applied['written']), sorted([str(self.roadmap), str(self.sprint)]))
        marker = plan['changes'][0]['marker']
        self.assertIn(marker, self.roadmap.read_text(encoding='utf-8'))
        self.assertIn(marker, self.sprint.read_text(encoding='utf-8'))
        self.assertEqual(sorted(Path(b).read_text(encoding='utf-8') for b in applied['backups']), sorted([before_roadmap, before_sprint]))
        self.assertFalse((self.sync_dir / 'state.json').exists())
        stored = json.loads((self.sync_dir / 'plan.json').read_text(encoding='utf-8'))
        self.assertIn('ackNotNeededAt', stored)
        self.assertNotIn('ackedAt', stored)
        again = self.run_op('apply', transport)
        self.assertFalse(again['ok'])
        self.assertIn('already acknowledged', again['message'])
        explicit = self.run_op('ack', transport)
        self.assertTrue(explicit['ok'], explicit['message'])
        self.assertEqual(explicit['ack'], 'not_needed')
        self.assertEqual(transport.calls, [])

    def test_a_server_as_of_does_not_make_a_completion_acknowledgeable(self):
        transport = Transport((200, {'acked': 9}))
        plan, applied = self.write_plan_and_apply(transport=transport)
        self.assertEqual(plan['asOf'], AS_OF)
        self.assertEqual((applied['ack'], transport.calls), ('not_needed', []))

    def test_a_plan_of_completions_needs_no_as_of_to_finish(self):
        transport = Transport()
        plan, applied = self.write_plan_and_apply(payload={'asOf': None, 'changes': []}, transport=transport)
        self.assertIsNone(plan['asOf'])
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual((applied['exitCode'], applied['ack'], transport.calls), (0, 'not_needed', []))

    def test_no_ack_with_only_completions_still_finishes_the_plan(self):
        transport = Transport()
        _, applied = self.write_plan_and_apply(transport=transport, no_ack=True)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual(applied['ack'], 'not_needed')
        self.assertEqual(transport.calls, [])
        self.assertIn('ackNotNeededAt', json.loads((self.sync_dir / 'plan.json').read_text(encoding='utf-8')))

    def test_real_and_synthetic_changes_are_acknowledged_once_with_every_marker_verified(self):
        result, _ = self.approve_and_fetch(state=done_state())
        plan = result['plan']
        self.draft(plan)
        transport = Transport((200, {'acked': 4}))
        applied = self.run_op('apply', transport)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual((applied['ack'], applied['acked'], applied['verified']), ('sent', 4, True))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]['url'], 'https://roads.example.test/api/frontlights/ack')
        self.assertEqual(json.loads(transport.calls[0]['body']), {'schemaVersion': 1, 'asOf': AS_OF})
        self.assertIn('acknowledged up to', applied['message'])
        roadmap = self.roadmap.read_text(encoding='utf-8')
        for change in plan['changes']:
            self.assertIn(change['marker'], roadmap)
        self.assertIn(plan['changes'][-1]['marker'], self.sprint.read_text(encoding='utf-8'))
        stored = json.loads((self.sync_dir / 'plan.json').read_text(encoding='utf-8'))
        self.assertIn('ackedAt', stored)
        state = json.loads((self.sync_dir / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['lastAckAsOf'], AS_OF)

    def test_a_missing_completion_marker_blocks_the_ack_of_the_real_changes_too(self):
        result, _ = self.approve_and_fetch(state=done_state())
        plan = result['plan']
        self.draft(plan, skip={DONE_E})
        transport = Transport((200, {'acked': 5}))
        applied = self.run_op('apply', transport)
        self.assertEqual(applied['exitCode'], 1)
        self.assertEqual(applied['missingMarkers'], [DONE_E])
        self.assertTrue(applied['written'])
        self.assertEqual(transport.calls, [])
        staged = Path(plan['targets']['roadmap']['staged'])
        staged.write_text(staged.read_text(encoding='utf-8') + f"\n{plan['changes'][-1]['marker']}\n", encoding='utf-8')
        retry = self.run_op('apply', transport)
        self.assertTrue(retry['ok'], retry['message'])
        self.assertEqual(len(transport.calls), 1)

    def test_a_completion_without_its_marker_anywhere_refuses_and_the_retry_finishes_it(self):
        transport = Transport()
        plan, applied = self.write_plan_and_apply(skip={DONE_E}, transport=transport)
        self.assertEqual((applied['ok'], applied['exitCode']), (False, 1))
        self.assertEqual(applied['missingMarkers'], [DONE_E])
        self.assertNotIn('ack', applied)
        stored = json.loads((self.sync_dir / 'plan.json').read_text(encoding='utf-8'))
        self.assertNotIn('ackNotNeededAt', stored)
        staged = Path(plan['targets'][CURRENT]['staged'])
        staged.write_text(staged.read_text(encoding='utf-8') + f"\nConcluída. {plan['changes'][0]['marker']}\n", encoding='utf-8')
        retry = self.run_op('apply', transport)
        self.assertTrue(retry['ok'], retry['message'])
        self.assertEqual((retry['ack'], transport.calls), ('not_needed', []))

    def test_a_staged_copy_that_loses_a_completion_marker_is_refused_and_writes_nothing(self):
        plan, applied = self.write_plan_and_apply()
        self.assertTrue(applied['ok'], applied['message'])
        written = self.roadmap.read_text(encoding='utf-8')
        payload = fixture()
        payload['changes'] = [dict(payload['changes'][0], id='7f1c2d3e-0000-4000-8000-0000000000ff')]
        second = self.fetch_again(payload, done_state())
        self.assertTrue(second['ok'], second['message'])
        self.assertEqual([c['id'] for c in second['plan']['changes']], ['7f1c2d3e-0000-4000-8000-0000000000ff'])
        marker = plan['changes'][0]['marker']
        Path(second['plan']['targets']['roadmap']['staged']).write_text(written.replace(marker, ' ' * len(marker)), encoding='utf-8')
        lost = self.run_op('apply')
        self.assertFalse(lost['ok'])
        self.assertIn('lost the marker', lost['message'])
        self.assertIn(DONE_E, lost['message'])
        self.assertEqual(lost['written'], [])
        self.assertEqual(self.roadmap.read_text(encoding='utf-8'), written)

    def test_a_completion_marker_the_plan_does_not_carry_is_refused(self):
        result, _ = self.only_completions()
        plan = result['plan']
        self.draft(plan)
        staged = Path(plan['targets'][CURRENT]['staged'])
        staged.write_text(staged.read_text(encoding='utf-8') + '\n' + rs.marker_text('done-' + ITEM_B, self.nonce()) + '\n', encoding='utf-8')
        applied = self.run_op('apply')
        self.assertFalse(applied['ok'])
        self.assertIn('not in this plan', applied['message'])
        self.assertEqual(applied['written'], [])

    def test_an_edited_target_is_still_refused_for_a_completion_plan(self):
        result, _ = self.only_completions()
        self.draft(result['plan'])
        self.sprint.write_text(self.sprint.read_text(encoding='utf-8') + 'Edição manual.\n', encoding='utf-8')
        applied = self.run_op('apply')
        self.assertFalse(applied['ok'])
        self.assertIn('changed after the plan', applied['message'])
        self.assertEqual(applied['written'], [])

    def test_a_shrinking_completion_draft_is_refused(self):
        result, _ = self.only_completions()
        Path(result['plan']['targets']['roadmap']['staged']).write_text('# Roadmap 2026\n', encoding='utf-8')
        applied = self.run_op('apply')
        self.assertFalse(applied['ok'])
        self.assertIn('dropping', applied['message'])
        self.assertEqual(applied['written'], [])

    def test_the_mixed_plan_with_no_ack_acknowledges_nothing_and_stays_open(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.draft(result['plan'])
        transport = Transport()
        applied = self.run_op('apply', transport, no_ack=True)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual(applied['ack'], 'not requested')
        self.assertEqual(transport.calls, [])
        stored = json.loads((self.sync_dir / 'plan.json').read_text(encoding='utf-8'))
        self.assertNotIn('ackedAt', stored)
        self.assertNotIn('ackNotNeededAt', stored)
        late = self.run_op('ack', Transport((200, {'acked': 5})))
        self.assertTrue(late['ok'], late['message'])
        self.assertEqual(late['ack'], 'sent')

    def test_a_failed_ack_of_a_mixed_plan_is_retryable(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.draft(result['plan'])
        applied = self.run_op('apply', Transport((503, '')))
        self.assertEqual((applied['exitCode'], applied['retryable']), (2, True))
        self.assertTrue(self.run_op('ack', Transport((200, {'acked': 5})))['ok'])


class DeclinedCompletionTests(CompletedTestCase):
    def test_a_declined_completion_alone_needs_no_confirmation_and_consumes_nothing(self):
        transport = Transport()
        plan, applied = self.write_plan_and_apply(declined={DONE_E}, transport=transport)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual((applied['exitCode'], applied['ack']), (0, 'not_needed'))
        self.assertEqual(applied['declinedCompletions'], [DONE_E])
        self.assertNotIn('declined', applied)
        self.assertNotIn('declinedConfirmed', applied)
        self.assertEqual(transport.calls, [])
        self.assertEqual(rs.marker_state(self.roadmap.read_text(encoding='utf-8'), DONE_E, self.nonce()), 'declined')

    def test_a_declined_completion_is_not_offered_again(self):
        self.write_plan_and_apply(declined={DONE_E})
        again = self.fetch_again(NO_CHANGES, done_state())
        self.assertTrue(again['ok'], again['message'])
        self.assertEqual((again['pending'], again['completed']['new'], again['completed']['alreadyRecorded']), (0, 0, 1))

    def test_declined_real_changes_still_need_the_confirmation_and_the_completion_is_not_among_them(self):
        result, _ = self.approve_and_fetch(state=done_state())
        declined_real = result['plan']['changes'][2]['id']
        self.draft(result['plan'], declined={declined_real, DONE_E})
        transport = Transport()
        applied = self.run_op('apply', transport)
        self.assertEqual(applied['exitCode'], 1)
        self.assertEqual(applied['declined'], [declined_real])
        self.assertEqual(applied['declinedCompletions'], [DONE_E])
        self.assertEqual(transport.calls, [])
        confirmed = self.run_op('ack', Transport((200, {'acked': 5})), confirm_declined=True)
        self.assertTrue(confirmed['ok'], confirmed['message'])
        self.assertEqual((confirmed['declined'], confirmed['declinedConfirmed']), ([declined_real], True))
        self.assertEqual(confirmed['declinedCompletions'], [DONE_E])

    def test_a_declined_completion_next_to_applied_real_changes_acknowledges_without_confirmation(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.draft(result['plan'], declined={DONE_E})
        transport = Transport((200, {'acked': 5}))
        applied = self.run_op('apply', transport)
        self.assertTrue(applied['ok'], applied['message'])
        self.assertEqual(applied['ack'], 'sent')
        self.assertEqual(applied['declinedCompletions'], [DONE_E])
        self.assertNotIn('declined', applied)
        self.assertEqual(len(transport.calls), 1)

    def test_an_applied_completion_with_a_declined_real_change_does_not_hide_the_decline(self):
        result, _ = self.approve_and_fetch(state=done_state())
        declined_real = result['plan']['changes'][2]['id']
        self.draft(result['plan'], declined={declined_real})
        applied = self.run_op('apply', Transport(), no_ack=True)
        self.assertEqual(applied['declined'], [declined_real])
        self.assertNotIn('declinedCompletions', applied)


class IdempotencyTests(CompletedTestCase):
    def test_a_second_fetch_after_the_write_does_not_propose_the_completion_again(self):
        self.write_plan_and_apply()
        second = self.fetch_again(NO_CHANGES, done_state())
        self.assertTrue(second['ok'], second['message'])
        self.assertEqual(second['pending'], 0)
        self.assertIn('Nothing pending', second['message'])
        self.assertEqual(second['completed'], {'enabled': True, 'new': 0, 'alreadyRecorded': 1,
                                               'completedOn': '2026-09-28', 'completedOnMeans': 'sync date'})
        self.assertIn('already recorded', second['message'])

    def test_the_recorded_completion_is_left_out_of_a_later_plan_and_its_files_are_not_staged(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.draft(result['plan'])
        self.assertTrue(self.run_op('apply', Transport((200, {'acked': 5})))['ok'])
        second = self.fetch_again(state=done_state())
        self.assertTrue(second['ok'], second['message'])
        plan = second['plan']
        self.assertEqual(plan['pending'], [])
        self.assertEqual([c['synthetic'] for c in plan['changes']], [False] * 4)
        self.assertEqual(plan['completed']['alreadyRecorded'], 1)
        self.assertEqual(plan['completed']['new'], 0)
        self.assertIn('already marked', second['message'])

    def test_a_new_done_item_is_proposed_next_to_a_recorded_one(self):
        self.write_plan_and_apply()
        second = self.fetch_again(NO_CHANGES, done_state((0, 2), (1, 0)))
        self.assertEqual([c['id'] for c in second['plan']['changes']], [DONE_A])
        self.assertEqual(second['plan']['completed'], {'enabled': True, 'new': 1, 'alreadyRecorded': 1,
                                                       'completedOn': '2026-09-28', 'completedOnMeans': 'sync date'})
        self.assertEqual(list(second['plan']['targets']), ['roadmap', NEXT])

    def test_a_marker_in_the_roadmap_alone_keeps_the_completion_recorded(self):
        result, _ = self.only_completions()
        staged = Path(result['plan']['targets']['roadmap']['staged'])
        staged.write_text(staged.read_text(encoding='utf-8') + f"\nConcluída. {result['plan']['changes'][0]['marker']}\n", encoding='utf-8')
        self.assertTrue(self.run_op('apply')['ok'])
        self.assertEqual(self.fetch_again(NO_CHANGES, done_state())['completed']['alreadyRecorded'], 1)

    def test_rotating_the_markers_keeps_the_completion_recorded(self):
        plan, _ = self.write_plan_and_apply()
        old_nonce = self.nonce()
        rotated = self.run_op('rotate-markers')
        self.assertTrue(rotated['ok'], rotated['message'])
        self.assertEqual(rotated['rotatedMarkers'], [DONE_E])
        self.assertEqual(len(rotated['rewritten']), 2)
        self.assertNotEqual(self.nonce(), old_nonce)
        for path in (self.roadmap, self.sprint):
            self.assertEqual(rs.marker_inventory(path.read_text(encoding='utf-8'), self.nonce()), {DONE_E: 'applied'})
            self.assertEqual(rs.marker_inventory(path.read_text(encoding='utf-8'), old_nonce), {})
        second = self.fetch_again(NO_CHANGES, done_state())
        self.assertEqual((second['pending'], second['completed']['new'], second['completed']['alreadyRecorded']), (0, 0, 1))
        self.assertFalse(second.get('markerNonceMinted'))

    def test_rotating_keeps_a_completion_recorded_by_the_roadmap_when_its_sprint_file_is_not_the_current_one(self):
        state = done_state((1, 0))
        plan, applied = self.write_plan_and_apply(state=state)
        self.assertTrue(applied['ok'], applied['message'])
        later = self.scrum / '2026' / '05_10' / 'SPRINT_05_10_a_09_10.md'
        stale = later.read_text(encoding='utf-8')
        old_nonce = self.nonce()
        rotated = self.run_op('rotate-markers')
        self.assertEqual(rotated['rewritten'], [str(self.roadmap)])
        self.assertEqual(later.read_text(encoding='utf-8'), stale)
        self.assertEqual(rs.marker_inventory(stale, old_nonce), {DONE_A: 'applied'})
        self.assertEqual(rs.marker_inventory(stale, self.nonce()), {})
        second = self.fetch_again(NO_CHANGES, state)
        self.assertEqual((second['pending'], second['completed']['new'], second['completed']['alreadyRecorded']), (0, 0, 1))

    def test_rotating_the_markers_after_a_completion_only_plan_is_not_blocked(self):
        self.write_plan_and_apply()
        self.assertTrue(self.run_op('rotate-markers')['ok'])

    def test_rotating_is_still_refused_while_a_mixed_plan_is_not_acknowledged(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.draft(result['plan'])
        self.assertTrue(self.run_op('apply', Transport(), no_ack=True)['ok'])
        refused = self.run_op('rotate-markers')
        self.assertFalse(refused['ok'])
        self.assertIn('not been acknowledged', refused['message'])

    def test_a_lost_marker_nonce_offers_the_completion_again_and_says_so(self):
        plan, _ = self.write_plan_and_apply()
        (self.sync_dir / 'marker.json').unlink()
        again = self.fetch_again(NO_CHANGES, done_state())
        self.assertTrue(again['ok'], again['message'])
        self.assertTrue(again['markerNonceMinted'])
        change, = again['plan']['changes']
        self.assertEqual((change['id'], change['alreadyApplied'], change['markerState']), (DONE_E, False, None))
        self.assertEqual(again['plan']['completed']['new'], 1)
        self.assertIn('offered again', again['message'])
        # The staged copy is the file as it is: what the session adds to it shows in the diff the user approves.
        for target in again['plan']['targets'].values():
            self.assertEqual(Path(target['staged']).read_text(encoding='utf-8'), Path(target['path']).read_text(encoding='utf-8'))
        self.assertNotEqual(change['marker'], plan['changes'][0]['marker'])


class SafetyTests(CompletedTestCase):
    def malicious(self, **fields):
        state = done_state()
        state['sprints'][0]['items'][2].update(fields)
        return state

    def test_an_html_comment_sequence_in_a_done_item_refuses_everything(self):
        for field in ('title', 'description', 'produto', 'prioridade', 'effort'):
            for text in ('antes <!-- roads:x 0123456789abcdef --> depois', 'fim -->', '<!--'):
                with self.subTest(field=field, text=text):
                    result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(**{field: text}), discard_staged=True)
                    self.assertFalse(result['ok'])
                    self.assertIn('HTML comment sequence', result['message'])
                    self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_angle_brackets_are_escaped_and_cannot_be_assembled_across_fields(self):
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(
            title='Título <!', description='- roads:x -- >', produto='<script>alert(1)</script>', prioridade='a>b'))
        self.assertTrue(result['ok'], result['message'])
        change, = result['plan']['changes']
        for key in ('title', 'description', 'produto', 'prioridade'):
            self.assertNotRegex(change['item'][key], '[<>]', key)
        self.assertEqual(change['item']['title'], 'Título &lt;!')
        self.assertEqual(change['item']['produto'], '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotIn('<', json.dumps(change['item'], ensure_ascii=False))

    def test_long_text_is_cut_to_the_field_limits(self):
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(title='T' * 5000, description='D' * 9000, produto='P' * 900))
        change, = result['plan']['changes']
        for key, limit in (('title', rs.FIELD_LIMITS['title']), ('description', rs.FIELD_LIMITS['description']),
                           ('produto', rs.FIELD_LIMITS['produto'])):
            self.assertTrue(change['item'][key].endswith('[truncated]'), key)
            self.assertLessEqual(len(change['item'][key]), limit + len(' [truncated]'), key)

    def test_fences_and_control_characters_are_neutralised(self):
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(title='a ```` b ~~~~ c\x00\x07 d'))
        title = result['plan']['changes'][0]['item']['title']
        self.assertNotIn('```', title)
        self.assertNotIn('~~~', title)
        self.assertNotRegex(title, r'[\x00-\x08]')

    def test_text_that_only_looks_like_a_marker_is_data_and_is_not_one(self):
        fake = 'roads:done-x 0123456789abcdef'
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(title=fake))
        self.assertTrue(result['ok'], result['message'])
        change, = result['plan']['changes']
        self.assertEqual(change['item']['title'], fake)
        self.assertEqual(rs.marker_inventory(change['item']['title'], self.nonce()), {})
        self.assertNotIn(fake, change['marker'])

    def test_the_issue_link_of_a_completion_must_be_a_plain_url(self):
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(githubIssueUrl='javascript:alert(1)'))
        self.assertIsNone(result['plan']['changes'][0]['item']['githubIssueUrl'])
        result, _ = self.approve_and_fetch(NO_CHANGES, state=self.malicious(githubIssueUrl='https://x.test/<b>'), discard_staged=True)
        self.assertIsNone(result['plan']['changes'][0]['item']['githubIssueUrl'])

    def test_a_state_cannot_link_a_completion_to_a_sprint_that_does_not_hold_the_item(self):
        state = done_state()
        state['sprints'][1]['items'][0]['pendingChangeIds'] = [DONE_E]
        state['removedPending'].append({'changeId': DONE_E, 'itemId': None, 'title': 'x', 'laneId': 'proxima'})
        result, _ = self.approve_and_fetch(NO_CHANGES, state=state)
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(list(result['plan']['targets']), ['roadmap', CURRENT])
        self.assertEqual(result['plan']['changes'][0]['sprintTargets'], [CURRENT])
        self.assertEqual(result['plan']['targets'][CURRENT]['changeIds'], [DONE_E])

    def test_a_state_cannot_name_a_completion_as_a_change_of_an_item_past_the_limit(self):
        state = done_state()
        items = state['sprints'][0]['items']
        items.append(dict(items[2], id='5a5a5a5a-0000-4000-8000-00000000000f', position=4, title='Quarto item', done=False, status='open'))
        items.append(dict(items[2], id='5a5a5a5a-0000-4000-8000-000000000010', position=5, title='Quinto item', done=False,
                          status='open', overLimit=True, pendingChangeIds=[DONE_E]))
        result, _ = self.approve_and_fetch(NO_CHANGES, state=state)
        self.assertEqual(result['plan']['targets'][CURRENT]['changeIds'], [DONE_E])
        self.assertEqual(result['plan']['changes'][0]['sprintTargets'], [CURRENT])

    def test_nothing_is_written_outside_the_scrum_root(self):
        self.assertTrue(self.run_op('approve')['ok'])
        self.write_config(weekFolderPattern='../fora_{dd_MM}')
        transport = Transport(*fetch_answers(NO_CHANGES, done_state((1, 0))))
        result = self.run_op('fetch', transport)
        self.assertFalse(result['ok'])
        self.assertFalse((self.scrum.parent / 'fora_28_09').exists())
        self.assertFalse((self.scrum.parent / 'fora_05_10').exists())
        self.assertFalse((self.sync_dir / 'plan.json').exists())
        self.assertEqual(transport.calls, [])

    def test_a_junction_on_the_way_to_the_sprint_of_a_completion_is_refused(self):
        outside = self.scrum.parent / 'outside'
        outside.mkdir()
        link = self.scrum / '2026' / '05_10'
        if sys.platform.startswith('win'):
            import subprocess
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            if made.returncode != 0:
                self.skipTest('cannot create a junction here')
        else:
            os.symlink(outside, link, target_is_directory=True)
        result, _ = self.approve_and_fetch(NO_CHANGES, state=done_state((1, 0)))
        self.assertFalse(result['ok'])
        self.assertIn('reparse point', result['message'])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_a_completion_plan_pointing_elsewhere_is_refused_at_apply(self):
        result, _ = self.only_completions()
        self.draft(result['plan'])
        plan_path = self.sync_dir / 'plan.json'
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        plan['targets'][CURRENT]['path'] = str(self.project / 'elsewhere.md')
        plan_path.write_text(json.dumps(plan), encoding='utf-8')
        applied = self.run_op('apply')
        self.assertFalse(applied['ok'])
        self.assertEqual(applied['written'], [])
        self.assertFalse((self.project / 'elsewhere.md').exists())

    def test_the_synthetic_flag_cannot_come_from_the_service(self):
        payload = fixture()
        payload['changes'][0]['synthetic'] = True
        payload['changes'][0]['action'] = 'completed'
        result, _ = self.approve_and_fetch(payload)
        self.assertTrue(result['ok'], result['message'])
        first = result['plan']['changes'][0]
        self.assertIs(first['synthetic'], False)
        self.assertFalse(first['knownAction'])
        self.assertTrue(first['id'] in result['plan']['pending'])

    def test_a_service_cannot_pass_a_queued_change_off_as_a_completion_to_skip_the_confirmation(self):
        payload = fixture()
        payload['changes'][1]['synthetic'] = True
        result, _ = self.approve_and_fetch(payload)
        declined = result['plan']['changes'][1]['id']
        self.draft(result['plan'], declined={declined})
        applied = self.run_op('apply', Transport())
        self.assertEqual((applied['exitCode'], applied['declined']), (1, [declined]))
        self.assertNotIn('declinedCompletions', applied)


class ReviewFindingsTests(CompletedTestCase):
    """The third review: the reserved id, and a plan of completions nobody approved."""

    def queued(self, change_id):
        payload = fixture()
        payload['changes'][0]['id'] = change_id
        return payload

    def test_a_queued_change_whose_id_starts_with_the_reserved_prefix_is_refused(self):
        for change_id in ('done-' + ITEM_B, 'done-anything-else', 'done-'):
            with self.subTest(change_id=change_id):
                rs._SECRETS.clear()
                result, _ = self.approve_and_fetch(self.queued(change_id), state=state_fixture(), discard_staged=True)
                self.assertFalse(result['ok'])
                self.assertIn('done-', result['message'])
                self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_with_the_marks_turned_off_the_prefix_is_not_reserved(self):
        self.write_config(markCompleted=False)
        result, _ = self.approve_and_fetch(self.queued('done-anything-else'), state=state_fixture())
        self.assertTrue(result['ok'], result['message'])

    def test_a_plan_of_completions_nobody_approved_does_not_block_rotating_the_markers(self):
        result, _ = self.only_completions()
        self.assertTrue(result['ok'], result['message'])
        rotated = self.run_op('rotate-markers')
        self.assertTrue(rotated['ok'], rotated)
        stale = self.run_op('apply', Transport())
        self.assertFalse(stale['ok'])                       # the old plan carries the old markers: it is finished
        again = self.fetch_again(NO_CHANGES, done_state(), discard_staged=True)
        self.assertTrue(again['ok'], again['message'])
        self.assertEqual(again['completed']['new'], 1)

    def test_a_plan_with_queued_changes_still_blocks_rotating_the_markers(self):
        result, _ = self.approve_and_fetch(state=done_state())
        self.assertTrue(result['ok'], result['message'])
        refused = self.run_op('rotate-markers')
        self.assertFalse(refused['ok'])
        self.assertIn('not been acknowledged', refused['message'])


class ExistingFlowsTests(CompletedTestCase):
    def test_nothing_pending_without_a_done_item_is_unchanged(self):
        result, _ = self.approve_and_fetch({'asOf': None, 'changes': []})
        self.assertTrue(result['ok'])
        self.assertEqual(result['pending'], 0)
        self.assertEqual(result['completed']['new'], 0)
        self.assertFalse((self.sync_dir / 'plan.json').exists())

    def test_the_queue_alone_still_produces_the_same_plan(self):
        result, _ = self.approve_and_fetch()
        plan = result['plan']
        self.assertEqual(len(plan['pending']), 4)
        self.assertEqual(plan['completed'], {'enabled': True, 'new': 0, 'alreadyRecorded': 0,
                                             'completedOn': '2026-09-28', 'completedOnMeans': 'sync date'})
        self.assertFalse(any(c['synthetic'] for c in plan['changes']))
        self.assertTrue(all(c['id'] in (ADD_ID, MODIFY_ID, REMOVE_ID, MOVE_ID) for c in plan['changes']))

    def test_the_move_and_remove_links_to_sprints_are_untouched_by_a_completion(self):
        result, _ = self.approve_and_fetch(state=done_state((0, 2)))
        by_id = {c['id']: c for c in result['plan']['changes']}
        self.assertEqual(by_id[MOVE_ID]['sprintTargets'], [CURRENT])
        self.assertEqual(by_id[REMOVE_ID]['sprintTargets'], [])
        self.assertEqual(by_id[ADD_ID]['sprintTargets'], [])


class ReferenceTests(unittest.TestCase):
    """The route the session follows (in English, as every skill) says what the helper now does."""

    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'references' / 'roadmap-sync.md'
        self.route = re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))

    def test_the_route_explains_the_completions_and_their_limits(self):
        for promise in ('`completed`', '`synthetic`', 'done-<itemId>', '`roadmapSync.markCompleted: false`', '`completedOn`',
                        '`sync date`', 'never the delivery date', 'concluída', '`plan.completed.new`',
                        '`plan.completed.alreadyRecorded`', '`not_needed`', '`declinedCompletions`', 'no `--confirm-declined`',
                        'is not in the RoadS queue', 'the state of its GitHub issue'):
            with self.subTest(promise=promise):
                self.assertIn(promise, self.route)

    def test_the_route_keeps_the_flow_and_the_existing_promises(self):
        for promise in ('go straight to step 7', '`apply`', '`--confirm-declined`', '`--allow-shrink`', 'AskUserQuestion',
                        'Write only into the staged files named in the plan', 'paste `change.marker` or `change.declinedMarker`',
                        'Never create issues automatically.'):
            with self.subTest(promise=promise):
                self.assertIn(promise, self.route)
        self.assertLess(self.route.index('3. **Fetch.**'), self.route.index('4. **Draft.**'))
        self.assertLess(self.route.index('5. **Approve the diff.**'), self.route.index('6. **Write, verify, acknowledge.**'))


if __name__ == '__main__':
    unittest.main()
