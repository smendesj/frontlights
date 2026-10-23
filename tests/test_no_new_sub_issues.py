"""Nenhuma sub-issue nova: o plano só carrega filhas já publicadas, a escada de achados tem três destinos e as
dependências entre issues do plano nascem como `--blocked-by`, publicadas na ordem das bloqueadoras.

Seams: `frontlights.validate_plan` e `frontlights.publish_order` (e os CLIs `validate-plan` e `publish-order`), mais
os manifestos de texto da skill, da referência da etapa 5, do modelo de issue, do protocolo, do README e da segurança.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(SKILL / 'scripts'))
import frontlights

SCRIPT = SKILL / 'scripts' / 'frontlights.py'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return None
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


def issue(number, dependencies=(), **extra):
    value = dict(id=number, title=f'Deliver outcome {number}', outcome='User can save and retrieve an observation',
                 acceptance=['Saved observation appears after reload'], tests=['Save then fetch'],
                 ownership=[f'src/part{number}'], dependencies=list(dependencies),
                 vertical_check='Save, reload, observe', non_goals=['Bulk import'], risks=['Concurrent updates'],
                 session_sized=True, status='ready', url=f'https://github.com/example/project/issues/{number}')
    value.update(extra)
    return value


def plan(*issues):
    return {'repository': 'example/project', 'issues': list(issues)}


class NoNewSubIssueTests(unittest.TestCase):
    def test_a_published_child_of_an_existing_family_is_still_accepted(self):
        frontlights.validate_plan(plan(issue(1), issue(2, parent=1)))
        frontlights.validate_plan(plan(issue(2, parent_external=9)))

    def test_a_proposed_issue_with_a_parent_is_refused_in_portuguese(self):
        proposed = issue(2, parent=1, status='proposed')
        proposed.pop('url')
        with self.assertRaisesRegex(ValueError, r'2: sub-issue nova .*filhas já publicadas'):
            frontlights.validate_plan(plan(issue(1), proposed))
        with self.assertRaisesRegex(ValueError, r'sub-issue nova'):
            frontlights.validate_plan(plan(issue(1), issue(2, parent=1, status='proposed')))
        with self.assertRaisesRegex(ValueError, r'sub-issue nova'):
            frontlights.validate_plan(plan(issue(2, parent_external=9, status='proposed')))
        unpublished = issue(2, parent=1)   # ready, but without the url that proves the publication
        unpublished.pop('url')
        with self.assertRaisesRegex(ValueError, r'sub-issue nova .*url'):
            frontlights.validate_plan(plan(issue(1), unpublished))

    def test_the_example_plan_proposes_no_sub_issue(self):
        example = json.loads(read('skills', 'frontlights', 'examples', 'plan.json'))
        for item in example['issues']:
            if 'parent' in item or 'parent_external' in item:
                self.assertNotEqual(item['status'], 'proposed', item['id'])
                self.assertIn('url', item)


class PublishOrderTests(unittest.TestCase):
    def test_blockers_come_first_and_ties_follow_the_ids(self):
        ordered = frontlights.publish_order(plan(issue(3, [1, 2]), issue(2), issue(1), issue(4, [3])))
        self.assertEqual(ordered, [1, 2, 3, 4])

    def test_the_order_validates_the_plan_first(self):
        with self.assertRaises(ValueError):
            frontlights.publish_order(plan(issue(1, [99])))

    def test_the_cli_prints_the_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'plan.json'
            path.write_text(json.dumps(plan(issue(2, [1]), issue(1))), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), 'publish-order', '--plan', str(path)],
                                    capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'order': [1, 2]})


class NoNewSubIssueTextTests(unittest.TestCase):
    def test_the_skill_never_creates_a_sub_issue_and_keeps_reading_existing_families(self):
        skill = flat(read('skills', 'frontlights', 'SKILL.md'))
        # redesenho, issue 3: "An issue and its sub-issues move together" virou a regra "The issue is the unit"; "a
        # family that already exists" vive em references/issues.md (Follow-ups e "Converting a family")
        unit = flat(skilltext.rule('The issue is the unit'))
        for phrase in ('No new sub-issue is ever created, on any path and at any stage',
                       'The scope is the issue and all its open sub-issues',
                       'one grilling, one plan, one run; only an explicit choice of the user narrows the work',
                       'a finding becomes a criterion of its source issue or a top-level issue linked by `--blocked-by`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, unit)
        issues = flat(read('skills', 'frontlights', 'references', 'issues.md'))
        for phrase in ('a family that already exists is never grown',
                       'the destination of a finding is a criterion of its source issue or a top-level issue'):
            with self.subTest(file='issues.md', phrase=phrase):
                self.assertIn(phrase, issues)
        self.assertNotIn('a new acceptance criterion of its source issue, a sub-issue or a', skill)

    def test_the_ladder_has_three_destinations_and_no_sub_issue_recipe(self):
        text = read('skills', 'frontlights', 'references', 'issues.md')
        followups = section(text, 'Follow-ups') or ''
        positions = [followups.find(step) for step in ('same PR', 'checklist', 'top-level issue')]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn('three destinations', flat(followups))
        self.assertIn('Never a new sub-issue', flat(followups))
        self.assertNotRegex(followups, r'gh issue create [^`]*--parent')
        self.assertNotIn('sub_issues --method POST', followups)
        self.assertIn('a top-level issue that cites it', flat(followups))

    def test_dependencies_between_issues_are_native_and_published_blockers_first(self):
        text = flat(read('skills', 'frontlights', 'references', 'issues.md'))
        for phrase in ('--blocked-by', '`--json blockedBy`', 'blockers first', 'publish-order --plan', '--add-blocked-by'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        family = flat(section(read('skills', 'frontlights', 'references', 'issues.md'),
                              'The issue and its layers') or '')
        self.assertIn('a family that already exists', family)
        self.assertIn('no new sub-issue is created', family)

    def test_the_issue_template_has_no_parent_line_and_names_the_native_dependency(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        self.assertRegex(template, r'(?m)^Depends on: none$')
        self.assertNotRegex(template, r'(?m)^Parent: none$')
        self.assertIn('--blocked-by', template)

    def test_the_docs_say_three_destinations_and_no_new_sub_issue(self):
        readme = flat(read('README.md'))
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for text, name in ((readme, 'README'), (protocol, 'protocol')):
            for phrase in ('nunca uma sub-issue nova', '--blocked-by', 'blockedBy'):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)
        self.assertIn('nunca uma sub-issue nova', security)
        self.assertIn('toda issue de topo entra no quadro; sub-issue entra só pelo pai', readme)


if __name__ == '__main__':
    unittest.main()
