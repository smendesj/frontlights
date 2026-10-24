"""Achados de revisão viram critério da issue de origem ou issue de topo; filhas já publicadas continuam no plano,
sem cartão avulso no quadro (#17, revisto pela issue 23: nenhuma sub-issue nova).

Seams: a CLI `validate-plan`, a escada de destinos em `references/issues.md`
(o script não publica issues) e o manifesto (skill, referências e modelo de issue).
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
SKILL = ROOT / 'skills' / 'frontlights'


def issue(number, parent=None, **extra):
    item = dict(id=number, title=f'Deliver outcome {number}',
                outcome='User can save and retrieve an observation',
                acceptance=['Saved observation appears after reload'],
                tests=['Save through API then fetch and assert the value'],
                ownership=[f'src/area{number}'], dependencies=[],
                vertical_check='Save in UI, reload, observe persisted value',
                non_goals=['Bulk import'], risks=['Concurrent updates'],
                session_sized=True, status='ready',
                url=f'https://github.com/example/project/issues/{number}')
    if parent is not None:
        item['parent'] = parent
    item.update(extra)
    return item


def top(number, **extra):
    """Issue de topo com todos os campos do quadro escolhidos."""
    return issue(number, project_fields={'Area': 'Backend'}, **extra)


def board():
    return {'owner': 'example-org', 'number': 3, 'assignee': '@me', 'issue_type': 'Task',
            'fields': {'Status': 'Open', 'Area': None}}


def validate(plan, project=...):
    """Roda a CLI como o usuário roda; `project=...` usa o quadro padrão, None roda sem config."""
    with tempfile.TemporaryDirectory() as d:
        plan_path = Path(d) / 'plan.json'
        plan_path.write_text(json.dumps(plan), encoding='utf-8')
        argv = [sys.executable, str(SCRIPT), 'validate-plan', '--plan', str(plan_path)]
        if project is not None:
            config = Path(d) / 'config.json'
            config.write_text(json.dumps({'repository': 'example/project',
                                          'project': board() if project is ... else project}),
                              encoding='utf-8')
            argv += ['--config', str(config)]
        result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
    return result


def plan(*issues):
    return {'repository': 'example/project', 'issues': list(issues)}


class SubIssuePlanTests(unittest.TestCase):
    def assertValid(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'semantic_review_required': True})

    def assertRefused(self, result, *fragments):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        error = json.loads(result.stderr)['error']
        for fragment in fragments:
            self.assertIn(fragment, error)
        return error

    def test_sub_issue_needs_no_board_fields(self):
        self.assertValid(validate(plan(top(1), issue(2, parent=1))))

    def test_top_level_issue_without_board_fields_is_still_refused(self):
        self.assertRefused(validate(plan(issue(1), issue(2, parent=1))), 'Area')

    def test_sub_issue_cannot_carry_board_fields(self):
        error = self.assertRefused(validate(plan(top(1), top(2, parent=1))), 'project_fields')
        self.assertIn('pai', error)

    def test_parent_equal_to_own_id_is_refused(self):
        error = self.assertRefused(validate(plan(top(1), issue(2, parent=2))), '2')
        self.assertIn('própria', error)

    def test_parent_missing_from_the_plan_is_refused(self):
        error = self.assertRefused(validate(plan(top(1), issue(2, parent=7))), '7')
        self.assertIn('plano', error)

    def test_parent_must_be_a_positive_integer(self):
        for bad in ('1', 0, True, '#1', 'https://github.com/example/project/issues/1'):
            with self.subTest(bad=bad):
                self.assertRefused(validate(plan(top(1), issue(2, parent=bad))), 'parent')

    def test_more_than_one_hundred_children_per_parent_is_refused(self):
        # O plano aceita no máximo 24 issues, então a CLI não chega a 101 filhas:
        # o limite é exercido direto em `sub_issues`, que o `validate-plan` chama.
        sys.path.insert(0, str(SCRIPT.parent))
        import frontlights
        self.assertEqual(frontlights.SUB_ISSUES_MAX, 100)
        family = lambda n: [{'id': 1}] + [{'id': k, 'parent': 1} for k in range(2, n + 2)]
        frontlights.sub_issues(family(100))
        with self.assertRaises(ValueError) as refused:
            frontlights.sub_issues(family(101))
        self.assertIn('101 filhas', str(refused.exception))
        self.assertIn('100', str(refused.exception))

    def test_nesting_deeper_than_eight_levels_is_refused(self):
        chain = [top(1)] + [issue(n, parent=n - 1) for n in range(2, 10)]
        self.assertValid(validate(plan(*chain)))  # 8 níveis abaixo da issue de topo
        deeper = chain + [issue(10, parent=9)]
        error = self.assertRefused(validate(plan(*deeper)), '8')
        self.assertIn('níveis', error)

    def test_parent_cycle_is_refused(self):
        error = self.assertRefused(validate(plan(top(1), issue(2, parent=3), issue(3, parent=2))), 'ciclo')
        self.assertIn('parent', error)

    def test_parent_rules_apply_without_a_board_too(self):
        self.assertValid(validate(plan(issue(1), issue(2, parent=1)), project=None))
        self.assertRefused(validate(plan(issue(1), issue(2, parent=2)), project=None), 'parent')


class WithoutParentNothingChangesTests(unittest.TestCase):
    def test_example_plan_still_validates_and_schedules(self):
        result = subprocess.run([sys.executable, str(SCRIPT), 'validate-plan', '--plan',
                                 str(ROOT / 'skills' / 'frontlights' / 'examples' / 'plan.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'semantic_review_required': True,
                          'waves': {'1': [['S1'], ['S2']], '3': [['S1'], ['S2']]}})
        result = subprocess.run([sys.executable, str(SCRIPT), 'schedule', '--plan',
                                 str(ROOT / 'skills' / 'frontlights' / 'examples' / 'plan.json'), '--limit', '2'],
                                capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), {'start': [1, 2]})

    def test_example_plan_shows_one_sub_issue(self):
        example = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'plan.json').read_text(encoding='utf-8'))
        children = [i for i in example['issues'] if 'parent' in i]
        self.assertEqual(len(children), 1)
        self.assertNotIn('project_fields', children[0])

    def test_plan_without_parent_keeps_the_board_rules(self):
        three = plan(top(1), top(2), top(3, dependencies=[1]))
        self.assertEqual(validate(three).returncode, 0)
        three['issues'][1].pop('project_fields')
        result = validate(three)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Area', result.stderr)


def section(text, heading):
    match = re.search(rf'^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match.group(1) if match else None


class FollowUpsManifestTests(unittest.TestCase):
    def setUp(self):
        self.issues = (SKILL / 'references' / 'issues.md').read_text(encoding='utf-8')
        self.followups = section(self.issues, 'Follow-ups') or ''

    def test_issues_reference_has_a_follow_ups_section(self):
        self.assertRegex(self.issues, r'(?m)^## Follow-ups$')

    def test_follow_ups_section_holds_the_ladder_decided_in_one_question(self):
        text = self.followups
        positions = [text.find(step) for step in ('same PR', 'A new slice of the source issue', 'top-level issue')]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn('single `AskUserQuestion`', text)
        self.assertIn('three destinations', ' '.join(text.split()))

    def test_no_sub_issue_recipe_remains_and_no_board_command_either(self):
        text = self.followups
        self.assertNotRegex(text, r'gh issue create [^`]*--parent')
        self.assertNotIn('item-add', text)
        self.assertNotIn('item-edit', text)
        self.assertNotIn('--project', text)

    def test_existing_families_are_still_read_and_closed_as_before(self):
        # redesenho, issue 3: o SKILL.md lê a família pela regra "The issue is the unit"; "a family that already
        # exists" (lida, trabalhada e fechada como antes, nunca crescida) vive em references/issues.md
        unit = skilltext.flat(skilltext.rule('The issue is the unit'))
        self.assertIn('subIssuesSummary', unit)
        self.assertIn('The scope is the issue and all its open sub-issues', unit)
        issues = ' '.join(self.issues.split())
        self.assertIn('A family that already exists (a parent with sub-issues published before the no-new-sub-issue rule)',
                      issues)
        self.assertIn('a family that already exists is never grown', issues)
        self.assertIn('parentTicks', (SKILL / 'references' / 'closeout.md').read_text(encoding='utf-8'))

    def test_follow_ups_section_covers_late_findings_and_closing(self):
        text = self.followups
        self.assertIn('reopen', text)
        self.assertIn('never reopen', text)
        self.assertIn('closed', text)

    def test_skill_and_development_point_to_the_section(self):
        for path in (SKILL / 'SKILL.md', SKILL / 'references' / 'development.md'):
            with self.subTest(path=path.name):
                self.assertRegex(path.read_text(encoding='utf-8'), r'Follow-ups')

    def test_skill_board_rule_is_top_level_only(self):
        # redesenho, issue 3: a regra do quadro saiu da etapa 5 do SKILL.md, que só aponta para "Project board";
        # ela vive em references/issues.md
        text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('"Project board" before an issue write', skilltext.pointers())
        # o campo do quadro vai na mesma escrita aprovada da issue (etapa 5)
        self.assertIn('one write per issue, board fields included', skilltext.flat(skilltext.stage(5)))
        board = ' '.join(section(self.issues, 'Project board').split())
        for phrase in ('every top-level issue this stage creates or adopts belongs on that board; never publish one outside it',
                       'A sub-issue joins only through its parent and takes none of the board writes below',
                       '`validate-plan --config` refuses the plan while any field is still open'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, board)
        self.assertNotIn('including follow-ups proposed after delivery', text)

    def test_issue_template_has_depends_on_without_a_parent_line(self):
        text = (ROOT / 'skills' / 'frontlights' / 'templates' / 'issue.md').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^Depends on: none$')
        self.assertNotIn('Parent: none', text)

    def test_docs_say_top_level_issues_join_the_board(self):
        for path in (ROOT / 'skills' / 'frontlights' / 'docs' / 'protocol.md',):  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
            with self.subTest(path=path.name):
                self.assertIn('toda issue de topo entra no quadro; sub-issue entra só pelo pai',
                              path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
