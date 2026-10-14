"""Regras do quadro vindas do config do projeto: labels, tipo nativo por label e linhas no corpo.

Seams: `frontlights.validate_plan` com `project`, `frontlights.resolve_board` e o CLI
`validate-plan --config`. Os nomes de campo, label e valor são marcadores genéricos: o
vocabulário real de um projeto vive no `.frontlights/config.json` dele, nunca neste repositório.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import frontlights

SCRIPT = Path(frontlights.__file__)


def project(**overrides):
    value = {
        'owner': 'example-org', 'number': 3, 'assignee': '@me', 'issue_type': 'Task',
        'fields': {'Status': 'Open', 'Area': None, 'Priority': None},
        'labels': {
            'require_prefix': ['kind:'],
            'by_field': {
                'Area': {'Backend': ['area:backend'], 'Frontend': ['area:frontend'],
                         'Both': ['area:frontend', 'area:backend']},
                'Priority': {'High': ['priority:high'], 'Critical': ['priority:high']},
            },
        },
        'issue_type_by_label': {'kind:bug': 'Bug', 'kind:feature': 'Feature'},
        'body_fields': {'Effort': ['Low', 'Medium', 'High']},
    }
    value.update(overrides)
    return value


def issue(number, **extra):
    base = dict(id=number, title=f'Deliver outcome {number}', outcome='User saves an observation',
                acceptance=['Saved observation appears after reload'], tests=['Save then fetch'],
                ownership=[f'src/part{number}'], dependencies=[], vertical_check='Save, reload, observe',
                non_goals=['Bulk import'], risks=['Concurrent updates'], session_sized=True, status='ready',
                project_fields={'Area': 'Backend', 'Priority': 'Medium'}, labels=['kind:feature'],
                body_fields={'Effort': 'Medium'})
    base.update(extra)
    return base


def plan(*issues):
    return {'repository': 'example/project', 'issues': list(issues) or [issue(1)]}


def normalised(**overrides):
    return frontlights.board(project(**overrides), 'example/project')


class RefusalMixin:
    def assertRefused(self, plan_, regex, board=None):
        with self.assertRaisesRegex(ValueError, regex):
            frontlights.validate_plan(plan_, board or project())


class LabelRuleTests(RefusalMixin, unittest.TestCase):
    def test_labels_follow_the_field_values_the_plan_chose(self):
        resolved = frontlights.resolve_board(normalised(), issue(
            1, project_fields={'Area': 'Both', 'Priority': 'Critical'}, labels=['kind:bug']))
        self.assertEqual(resolved['labels'], ['kind:bug', 'area:frontend', 'area:backend', 'priority:high'])

    def test_a_field_value_without_a_rule_adds_no_label(self):
        resolved = frontlights.resolve_board(normalised(), issue(1, project_fields={'Area': 'General', 'Priority': 'Low'}))
        self.assertEqual(resolved['labels'], ['kind:feature'])

    def test_a_label_named_twice_is_kept_once(self):
        resolved = frontlights.resolve_board(normalised(), issue(
            1, labels=['kind:feature', 'area:backend', 'area:backend']))
        self.assertEqual(resolved['labels'], ['kind:feature', 'area:backend'])

    def test_a_required_label_family_missing_is_refused(self):
        self.assertRefused(plan(issue(1, labels=['area:backend'])), 'kind:')
        self.assertRefused(plan(issue(1, labels=[])), 'kind:')
        self.assertRefused(plan(issue(1, labels=None)), 'labels must be a list')

    def test_a_derived_label_does_not_satisfy_the_required_family(self):
        # `kind:` has to be chosen by the plan, never inferred from a field value.
        board = project(labels={'require_prefix': ['kind:'], 'by_field': {'Area': {'Backend': ['kind:feature']}}})
        self.assertRefused(plan(issue(1, labels=[])), 'kind:', board)
        frontlights.validate_plan(plan(issue(1, labels=['kind:feature'])), board)

    def test_a_label_a_field_implies_cannot_double_a_family_the_plan_already_named(self):
        # Area=Backend implies area:backend; the plan names area:frontend: two labels of one family.
        self.assertRefused(plan(issue(1, labels=['kind:feature', 'area:frontend'])), 'clashes')
        self.assertRefused(plan(issue(1, labels=['kind:feature', 'Area:Frontend'])), 'clashes')

    def test_two_fields_implying_labels_of_one_family_are_refused(self):
        board = project(labels={'require_prefix': ['kind:'],
                                'by_field': {'Area': {'Backend': ['area:backend']}, 'Priority': {'Low': ['area:frontend']}}})
        with self.assertRaisesRegex(ValueError, 'of one family'):
            frontlights.resolve_board(frontlights.board(board, 'example/project'), issue(
                1, project_fields={'Area': 'Backend', 'Priority': 'Low'}, labels=['kind:bug']))

    def test_naming_one_of_the_labels_a_field_implies_is_not_a_clash(self):
        both = project(labels={'require_prefix': ['kind:'], 'by_field': {'Area': {'Both': ['area:frontend', 'area:backend']}}})
        resolved = frontlights.resolve_board(frontlights.board(both, 'example/project'), issue(
            1, project_fields={'Area': 'Both', 'Priority': 'Low'}, labels=['kind:bug', 'area:frontend']))
        self.assertEqual(resolved['labels'], ['kind:bug', 'area:frontend', 'area:backend'])

    def test_label_names_are_compared_without_regard_to_case_as_github_does(self):
        resolved = frontlights.resolve_board(normalised(), issue(1, labels=['Kind:Feature', 'AREA:BACKEND']))
        self.assertEqual(resolved['labels'], ['Kind:Feature', 'AREA:BACKEND'])
        resolved = frontlights.resolve_board(normalised(), issue(1, labels=['KIND:bug']))
        self.assertEqual(resolved['issue_type'], 'Bug')

    def test_labels_must_be_a_list_of_plain_names(self):
        # The plan always names `kind:feature` too, so each refusal below can only come from the bad entry.
        for bad in ('a,b', 'x' * 51, 'kind:\nfeature', ' kind:bug', 'kind:bug ', '   ', 'kind:$(touch pwned)', 'kind:`id`',
                    'kind:x"; rm -rf ~; "', "kind:x'y", 'kind:a;b', 'kind:a&b', 'kind:a|b', 'kind:a<b', 'kind:\\x', '',
                    'kind:bug --repo other/victim', 'a -b', 'ends-in-dash-', 'ends.', 'ends:', 'ends/'):
            with self.subTest(bad=bad):
                self.assertRefused(plan(issue(1, labels=['kind:feature', bad])), 'must be a list of label names|label names')
        for bad in ('kind:feature', [3], None):
            with self.subTest(bad=bad):
                self.assertRefused(plan(issue(1, labels=bad)), 'labels')

    def test_plain_names_with_the_usual_punctuation_are_accepted(self):
        for good in ('kind:feature', 'team:back-end', 'good first issue', 'epic:single-view', 'C++', 'v1.2', 'a/b', 'Á:ç', 'a_b'):
            with self.subTest(good=good):
                frontlights.validate_plan(plan(issue(1, labels=['kind:feature', good])), project())


class IssueTypeTests(RefusalMixin, unittest.TestCase):
    def test_the_type_comes_from_the_plan_then_the_label_then_the_board_default(self):
        board = normalised()
        self.assertEqual(frontlights.resolve_board(board, issue(1, issue_type='Epic'))['issue_type'], 'Epic')
        self.assertEqual(frontlights.resolve_board(board, issue(1, labels=['kind:bug']))['issue_type'], 'Bug')
        self.assertEqual(frontlights.resolve_board(board, issue(1, labels=['kind:feature']))['issue_type'], 'Feature')
        self.assertEqual(frontlights.resolve_board(board, issue(1, labels=['area:backend', 'kind:chore']))['issue_type'], 'Task')

    def test_a_label_implied_type_makes_the_board_default_optional(self):
        board = project(issue_type=None)
        frontlights.validate_plan(plan(issue(1, labels=['kind:bug'])), board)
        self.assertRefused(plan(issue(1, labels=['kind:chore'])), 'issue_type', board)

    def test_the_first_implying_label_wins(self):
        resolved = frontlights.resolve_board(normalised(), issue(1, labels=['kind:feature', 'kind:bug']))
        self.assertEqual(resolved['issue_type'], 'Feature')


class BodyFieldTests(RefusalMixin, unittest.TestCase):
    def test_every_configured_line_must_be_chosen_from_its_options(self):
        self.assertEqual(frontlights.resolve_board(normalised(), issue(1))['body_fields'], {'Effort': 'Medium'})
        self.assertRefused(plan(issue(1, body_fields={})), 'choose body field')
        self.assertRefused(plan(issue(1, body_fields={'Effort': 'Huge'})), 'must be one of')
        self.assertRefused(plan(issue(1, body_fields={'Effort': 'Low', 'Typo': 'x'})), 'not on the board')
        self.assertRefused(plan(issue(1, body_fields=['Effort'])), 'body_fields must map')

    def test_a_project_without_body_fields_asks_for_none(self):
        board = project(body_fields=None)
        frontlights.validate_plan(plan(issue(1, body_fields={})), board)
        self.assertRefused(plan(issue(1, body_fields={'Effort': 'Low'})), 'not on the board', board)


class SubIssueTests(RefusalMixin, unittest.TestCase):
    def child(self, **extra):
        child = issue(2, parent=1, url='https://github.com/example/project/issues/2', **extra)
        for key in ('project_fields', 'labels', 'body_fields'):
            if key not in extra:
                child.pop(key)
        return child

    def test_a_sub_issue_takes_nothing_from_the_rules(self):
        self.assertIsNone(frontlights.resolve_board(normalised(), self.child()))
        frontlights.validate_plan(plan(issue(1), self.child()), project())

    def test_a_sub_issue_cannot_carry_labels_or_body_lines_when_the_board_has_rules(self):
        self.assertRefused(plan(issue(1), self.child(labels=['kind:bug'])), 'sub-issue')
        self.assertRefused(plan(issue(1), self.child(body_fields={'Effort': 'Low'})), 'sub-issue')

    def test_a_sub_issue_still_cannot_carry_board_fields(self):
        self.assertRefused(plan(issue(1), issue(2, parent=1, url='https://github.com/example/project/issues/2')),
                           'project_fields')

    def test_a_board_without_rules_does_not_look_at_labels_or_body_lines_of_a_sub_issue(self):
        board = project(labels=None, issue_type_by_label=None, body_fields=None)
        frontlights.validate_plan(plan(issue(1, labels=[], body_fields={}), self.child(labels=['x'])), board)


class AdoptedIssueTests(RefusalMixin, unittest.TestCase):
    def test_an_issue_that_already_exists_needs_no_body_line(self):
        existing = issue(5, body_fields={}, url='https://github.com/example/project/issues/5')
        frontlights.validate_plan(plan(existing), project())

    def test_a_body_line_it_does_carry_is_still_checked(self):
        existing = issue(5, body_fields={'Effort': 'Huge'}, url='https://github.com/example/project/issues/5')
        self.assertRefused(plan(existing), 'must be one of')

    def test_a_new_issue_still_needs_it(self):
        self.assertRefused(plan(issue(5, body_fields={})), 'choose body field')


class ConfigShapeTests(RefusalMixin, unittest.TestCase):
    def test_malformed_rules_are_refused_before_any_plan(self):
        bad = (
            project(labels=[]),
            project(labels={'unknown': 1}),
            project(labels={'require_prefix': 'kind:'}),
            project(labels={'require_prefix': ['']}),
            project(labels={'by_field': {'Missing': {'x': ['a']}}}),
            project(labels={'by_field': {'Area': {'Backend': []}}}),
            project(labels={'by_field': {'Area': {'Backend': 'area:backend'}}}),
            project(labels={'by_field': {'Area': {'Backend': ['a,b']}}}),
            project(labels={'by_field': {'Area': {'Backend': [' padded']}}}),
            project(issue_type_by_label=['kind:bug']),
            project(issue_type_by_label={'kind:bug': ''}),
            project(body_fields=['Effort']),
            project(body_fields={'Effort': []}),
            project(body_fields={'Effort': ['a\nb']}),
            project(body_fields={'bad:name': ['a']}),
            project(body_fields={'': ['a']}),
        )
        for config in bad:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, 'project'):
                frontlights.board(config, 'example/project')

    def test_a_board_without_the_new_keys_resolves_like_before(self):
        board = frontlights.board({'owner': 'example-org', 'number': 3, 'issue_type': 'Task',
                                   'fields': {'Status': 'Open', 'Area': None}}, 'example/project')
        resolved = frontlights.resolve_board(board, issue(1, labels=[], body_fields={}, project_fields={'Area': 'X'}))
        self.assertEqual(resolved, {'fields': {'Status': 'Open', 'Area': 'X'}, 'labels': [],
                                    'issue_type': 'Task', 'body_fields': {}})

    def test_a_board_without_the_new_keys_accepts_whatever_the_plan_carried_before(self):
        # Plans written before these rules existed may carry anything under these keys; it was never read.
        board = {'owner': 'example-org', 'number': 3, 'issue_type': 'Task', 'fields': {'Status': 'Open', 'Area': None}}
        for extra in ({'labels': None}, {'labels': 'bug'}, {'labels': ['a,b']}, {'labels': [3]},
                      {'body_fields': {'Effort': 'Low'}}, {'body_fields': ['x']}):
            with self.subTest(extra=extra):
                frontlights.validate_plan(plan(issue(1, project_fields={'Area': 'X'}, **extra)), board)

    def test_an_unknown_project_setting_is_refused_so_a_typo_cannot_switch_a_rule_off(self):
        for key in ('label_rules', 'issue_type_by_labels', 'bodyFields', 'labels ', 'Labels'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'unknown setting'):
                frontlights.board(project(**{key: {}}), 'example/project')

    def test_text_that_is_typed_into_gh_commands_is_checked_in_the_config(self):
        curly = 'x”; calc; “y'  # PowerShell closes a string on these, as it does on a straight quote
        bad = (project(issue_type='Task"; echo pwned; "'), project(issue_type='Bug $(id)'), project(issue_type='x`id`'),
               project(issue_type=curly), project(issue_type='a“b'), project(issue_type='a„b'), project(issue_type='a‟b'),
               project(issue_type='a″b'), project(issue_type='a＂b'),
               project(issue_type_by_label={'kind:bug': 'Bug --repo evil/x\n'}), project(issue_type_by_label={'kind:bug': curly}),
               project(issue_type_by_label={'kind:bug': 'x' * 101}), project(issue_type_by_label={'bad label;': 'Bug'}),
               project(assignee='$(id)'), project(assignee='a b'), project(assignee='x' * 40), project(assignee='@someone'),
               project(fields={'Status': 'x`id`', 'Area': None, 'Priority': None}),
               project(fields={'Status': curly, 'Area': None, 'Priority': None}),
               project(fields={'Sta"tus': 'Open', 'Area': None, 'Priority': None}),
               project(fields={'Status': 'a\\b', 'Area': None, 'Priority': None}),
               project(fields={'Status': 'x' * 101, 'Area': None, 'Priority': None}),
               project(labels={'require_prefix': ['x$(touch pwned)']}), project(labels={'require_prefix': ['x"; echo pwned; "']}),
               project(labels={'require_prefix': [curly]}), project(labels={'require_prefix': ['x`id`']}),
               project(labels={'require_prefix': ['']}))
        for config in bad:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, 'project'):
                frontlights.board(config, 'example/project')

    def test_the_refusal_names_the_field_and_the_real_reason(self):
        with self.assertRaisesRegex(ValueError, r'project\.fields\.Status default must be text of up to 100 characters'):
            frontlights.board(project(fields={'Status': 'x' * 101, 'Area': None, 'Priority': None}), 'example/project')

    def test_ordinary_values_that_a_quoted_argument_keeps_inert_are_accepted(self):
        config = project(issue_type="Task (small)", fields={'Status': "Don't start", 'Progress %': '50%', 'Urgent': 'Now!',
                                                            'Area': None, 'Priority': None}, assignee='some_login',
                         labels={'require_prefix': ['kind:']})
        frontlights.board(config, 'example/project')
        for login in ('@me', '@copilot', 'octocat', 'jdoe_acme', 'copilot-swe-agent[bot]', 'a-b-c', 'A1'):
            with self.subTest(login=login):
                frontlights.board(project(assignee=login), 'example/project')

    def test_plan_values_that_are_typed_into_gh_are_checked_too(self):
        curly = 'x”; calc; “y'
        for bad in ('Backend$(touch pwned)', 'x"; calc; "', 'x`id`', curly, 'a\\b', 'two\nlines'):
            with self.subTest(bad=bad):
                self.assertRefused(plan(issue(1, project_fields={'Area': bad, 'Priority': 'Medium'})), 'project_fields Area must not contain')
        # free text a board field holds is fine as long as a shell could not read it: no length limit here
        frontlights.validate_plan(plan(issue(1, project_fields={'Area': 'Backend', 'Priority': 'A long sentence. ' * 40})), project())
        for bad in ('Bug$(id)', 'x"; calc; "', curly, 'x' * 101):
            with self.subTest(issue_type=bad):
                self.assertRefused(plan(issue(1, issue_type=bad)), 'issue_type')

    def test_a_plan_naming_two_labels_of_a_family_the_fields_imply_only_one_of_is_refused(self):
        self.assertRefused(plan(issue(1, labels=['kind:feature', 'area:backend', 'area:frontend'])), 'clashes')
        frontlights.validate_plan(plan(issue(1, labels=['kind:feature', 'area:backend'])), project())

    def test_the_slash_style_label_families_are_recognised_too(self):
        slash = project(labels={'require_prefix': ['kind/'], 'by_field': {'Area': {'Backend': ['area/backend']}}})
        self.assertRefused(plan(issue(1, labels=['kind/bug', 'area/frontend'])), 'clashes', slash)
        resolved = frontlights.resolve_board(frontlights.board(slash, 'example/project'), issue(1, labels=['kind/bug']))
        self.assertEqual(resolved['labels'], ['kind/bug', 'area/backend'])
        self.assertEqual((frontlights.family('Area:Backend'), frontlights.family('area/x'), frontlights.family('plain')),
                         ('area:', 'area/', None))

    def test_a_hostile_label_in_the_config_is_refused_before_any_plan(self):
        for name in ('kind:$(touch x)', 'a`b', 'a;b', 'a"b', 'a\nb', 'a,b'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'project.labels'):
                frontlights.board(project(labels={'by_field': {'Area': {'Backend': [name]}}}), 'example/project')

    def test_inspect_shows_the_rules_it_read(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'project', 'view']:
                return json.dumps({'title': 'Board', 'url': 'https://github.com/orgs/example-org/projects/3'}).encode()
            return b'[]'
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=fake):
            result = frontlights.inspect({'repository': 'example/project', 'project': project()}, root)
        shown = result['sources']['project']
        self.assertEqual(shown['labels']['require_prefix'], ['kind:'])
        self.assertEqual(shown['issue_type_by_label'], {'kind:bug': 'Bug', 'kind:feature': 'Feature'})
        self.assertEqual(shown['body_fields'], {'Effort': ['Low', 'Medium', 'High']})


class DoneSettingTests(unittest.TestCase):
    """`project.done`: o campo e a opção em que o cartão fica quando a issue é fechada."""

    def test_a_board_without_done_gets_status_done(self):
        self.assertEqual(frontlights.board(project(), 'example/project')['done'], {'field': 'Status', 'value': 'Done'})

    def test_a_custom_done_is_kept(self):
        board = frontlights.board(project(done={'field': 'Situação', 'value': 'Concluído'}), 'example/project')
        self.assertEqual(board['done'], {'field': 'Situação', 'value': 'Concluído'})

    def test_the_default_is_a_fresh_copy_each_time(self):
        first = frontlights.board(project(), 'example/project')
        first['done']['value'] = 'Changed'
        self.assertEqual(frontlights.board(project(), 'example/project')['done']['value'], 'Done')

    def test_done_is_a_known_setting(self):
        self.assertIn('done', frontlights.BOARD_KEYS)
        with self.assertRaisesRegex(ValueError, 'known: .*done'):
            frontlights.board(project(finished={}), 'example/project')

    def test_done_must_be_an_object_with_field_and_value(self):
        for bad in (None, 'Done', ['Status', 'Done'], 3, {}, {'field': 'Status'}, {'value': 'Done'},
                    {'field': '', 'value': 'Done'}, {'field': 'Status', 'value': '   '},
                    {'field': 5, 'value': 'Done'}, {'field': 'Status', 'value': None}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, r'project\.done'):
                frontlights.board(project(done=bad), 'example/project')

    def test_an_unknown_key_inside_done_is_refused(self):
        for extra in ({'field': 'Status', 'value': 'Done', 'option': 'x'}, {'field': 'Status', 'valeu': 'Done'}):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, r'project\.done has unknown setting'):
                frontlights.board(project(done=extra), 'example/project')

    def test_done_text_is_typeable_like_the_other_board_fields(self):
        curly = 'x”; calc; “y'
        for bad in ('Done$(id)', 'Do`ne`', 'Do"ne', 'Do\\ne', 'Do\nne', curly, 'a“b', 'x' * 101):
            with self.subTest(value=bad), self.assertRaisesRegex(ValueError, r'project\.done\.value'):
                frontlights.board(project(done={'field': 'Status', 'value': bad}), 'example/project')
            with self.subTest(field=bad), self.assertRaisesRegex(ValueError, r'project\.done\.field'):
                frontlights.board(project(done={'field': bad, 'value': 'Done'}), 'example/project')
        frontlights.board(project(done={'field': 'x' * 100, 'value': "Won't fix (later)"}), 'example/project')

    def test_done_without_a_board_is_ignored(self):
        self.assertIsNone(frontlights.board(None, 'example/project'))

    def test_inspect_shows_done(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'project', 'view']:
                return json.dumps({'title': 'Board', 'url': 'https://github.com/orgs/example-org/projects/3'}).encode()
            return b'[]'
        for configured, shown in ((None, {'field': 'Status', 'value': 'Done'}),
                                  ({'field': 'Phase', 'value': 'Shipped'}, {'field': 'Phase', 'value': 'Shipped'})):
            extra = {} if configured is None else {'done': configured}
            with self.subTest(done=configured), tempfile.TemporaryDirectory() as root,                     patch.object(frontlights, 'run', side_effect=fake):
                result = frontlights.inspect({'repository': 'example/project', 'project': project(**extra)}, root)
            self.assertEqual(result['sources']['project']['done'], shown)


class CliTests(unittest.TestCase):
    def run_cli(self, plan_, config):
        with tempfile.TemporaryDirectory() as d:
            plan_path, config_path = Path(d) / 'plan.json', Path(d) / 'config.json'
            plan_path.write_text(json.dumps(plan_), encoding='utf-8')
            config_path.write_text(json.dumps({'repository': 'example/project', 'project': config}), encoding='utf-8')
            return subprocess.run([sys.executable, str(SCRIPT), 'validate-plan', '--plan', str(plan_path),
                                   '--config', str(config_path)], capture_output=True, text=True)

    def test_validate_plan_prints_the_resolved_values_for_a_configured_board(self):
        result = self.run_cli(plan(issue(1, labels=['kind:bug'], project_fields={'Area': 'Frontend', 'Priority': 'High'})),
                              project())
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = json.loads(result.stdout)
        self.assertEqual(printed['resolved']['1'], {
            'fields': {'Status': 'Open', 'Area': 'Frontend', 'Priority': 'High'},
            'labels': ['kind:bug', 'area:frontend', 'priority:high'],
            'issue_type': 'Bug', 'body_fields': {'Effort': 'Medium'}})
        self.assertTrue(printed['valid'])

    def test_a_sub_issue_has_no_resolved_entry(self):
        child = issue(2, parent=1, url='https://github.com/example/project/issues/2')
        for key in ('project_fields', 'labels', 'body_fields'):
            child.pop(key)
        printed = json.loads(self.run_cli(plan(issue(1), child), project()).stdout)
        self.assertEqual(list(printed['resolved']), ['1'])

    def test_output_is_unchanged_when_the_board_has_no_rules(self):
        board = {'owner': 'example-org', 'number': 3, 'issue_type': 'Task', 'fields': {'Status': 'Open', 'Area': None}}
        result = self.run_cli(plan(issue(1, project_fields={'Area': 'Backend'}, body_fields={})), board)
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'semantic_review_required': True})

    def test_a_refusal_is_a_clean_error_not_a_traceback(self):
        result = self.run_cli(plan(issue(1, labels=['area:backend'])), project())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('kind:', result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
