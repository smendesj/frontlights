"""As slices são os critérios de aceitação da issue: uma caixa por slice, em ordem de dependência, lista numerada
e quiz antes do corpo, uma escrita por issue.

Seams: `frontlights.validate_plan` com o campo `slices` de cada issue (e o CLI `validate-plan` sobre o exemplo), e os
manifestos de texto da skill, da referência da etapa 5, do modelo de issue, do protocolo, do README e dos ensaios.
"""
import copy
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

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


def slice_(number, depends_on=(), **extra):
    value = dict(id=f'S{number}', title=f'Slice {number}', delivers=f'Demo of behaviour {number} end to end',
                 seams=['POST /observations'], layers=['Tela', 'API', 'Testes'], depends_on=list(depends_on))
    value.update(extra)
    return value


def issue(number, slices=None, **extra):
    value = dict(id=number, title=f'Deliver outcome {number}', outcome='User can save and retrieve an observation',
                 tests=['Save through API then fetch and assert the value'], ownership=[f'src/part{number}'],
                 dependencies=[], non_goals=['Bulk import'], risks=['Concurrent updates'], session_sized=True,
                 status='ready', url=f'https://github.com/example/project/issues/{number}')
    if slices is None:
        value.update(acceptance=['Saved observation appears after reload'],
                     vertical_check='Save in UI, reload, observe persisted value')
    else:
        value['slices'] = slices
    value.update(extra)
    return value


def plan(*issues):
    return {'repository': 'example/project', 'issues': list(issues)}


class SlicesInThePlanTests(unittest.TestCase):
    def test_an_issue_with_slices_needs_no_acceptance_list_nor_vertical_check(self):
        frontlights.validate_plan(plan(issue(1, [slice_(1), slice_(2, ['S1'])])))

    def test_an_issue_without_slices_keeps_the_old_rules(self):
        frontlights.validate_plan(plan(issue(1)))
        broken = plan(issue(1))
        del broken['issues'][0]['acceptance']
        with self.assertRaises(ValueError):
            frontlights.validate_plan(broken)

    def test_a_slice_without_what_it_delivers_is_refused(self):
        with self.assertRaisesRegex(ValueError, r'S1.*delivers'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, delivers='')])))

    def test_a_dependency_on_an_unknown_or_later_slice_is_refused(self):
        with self.assertRaisesRegex(ValueError, r'S1.*depende de S9'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, ['S9'])])))
        with self.assertRaisesRegex(ValueError, r'S1.*depende de S2.*bloqueadoras primeiro'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, ['S2']), slice_(2)])))
        with self.assertRaisesRegex(ValueError, r'S1.*depende de S1'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, ['S1'])])))

    def test_slice_ids_are_unique_and_simple(self):
        with self.assertRaisesRegex(ValueError, r'repetid'):
            frontlights.validate_plan(plan(issue(1, [slice_(1), slice_(1)])))
        with self.assertRaisesRegex(ValueError, r'id'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, id='S 1')])))

    def test_a_slice_names_its_seams_and_layers(self):
        for field in ('seams', 'layers', 'title'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                frontlights.validate_plan(plan(issue(1, [slice_(1, **{field: [] if field != 'title' else ''})])))

    def test_slices_must_be_a_non_empty_list(self):
        for value in ([], 'S1', [{'id': 'S1'}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                frontlights.validate_plan(plan(issue(1, value)))

    def test_the_example_plan_carries_slices_and_still_schedules(self):
        example = json.loads(read('skills', 'frontlights', 'examples', 'plan.json'))
        sliced = [i for i in example['issues'] if i.get('slices')]
        self.assertGreaterEqual(len(sliced), 2)
        self.assertTrue(any(any(s['depends_on'] for s in i['slices']) for i in sliced))
        frontlights.validate_plan(copy.deepcopy(example))
        result = subprocess.run([sys.executable, str(SCRIPT), 'validate-plan', '--plan',
                                 str(SKILL / 'examples' / 'plan.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'semantic_review_required': True})
        self.assertEqual(frontlights.schedule(copy.deepcopy(example), 2), [1, 2])


class SlicesTextTests(unittest.TestCase):
    def test_stage_5_cuts_the_body_into_slices_and_asks_the_quiz_before_the_body(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        body = flat(section(skill, '5. Slices') or '')
        self.assertNotEqual(body, '')
        for phrase in ('Read `references/issues.md`', 'tracer bullet', 'one acceptance-criteria box of the issue',
                       'blockers first', 'Entrega, Seams, Camadas and Depende de', 'every criterion fails at the base commit',
                       'Prefactoring', 'expand, migrate in batches and contract', 'the numbered list of the slices',
                       'granularity', 'merge or split', 'what can be demoed', 'one write per issue',
                       'rereading GitHub', 'only after reading every layer'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertNotIn('## 5. Issue-plan approval', skill)

    def test_the_reference_defines_the_box_of_a_slice_and_the_quiz(self):
        text = read('skills', 'frontlights', 'references', 'issues.md')
        body = flat(section(text, 'Slices as acceptance criteria') or '')
        self.assertNotEqual(body, '')
        for phrase in ('tracer bullet', 'one box per slice', '- [ ] S1.', 'Entrega:', 'Seams:', 'Camadas:', 'Depende de:',
                       'blockers first', 'Prefactoring', 'expand', 'contract', 'fails at the base commit',
                       'numbered list', 'granularity', 'merge or split', 'what can be demoed', 'one write per issue',
                       '`slices`', 'validate-plan'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_the_issue_template_shows_one_box_per_slice_with_its_sub_items(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        criteria = section(template, 'Critérios de aceitação') or ''
        for line in ('- [ ] S1.', '  - Entrega:', '  - Seams:', '  - Camadas:', '  - Depende de:'):
            with self.subTest(line=line):
                self.assertRegex(criteria, r'(?m)^' + re.escape(line))
        for phrase in ('uma caixa por slice', 'bloqueadoras primeiro', 'falha no commit de partida', 'Prefactoring',
                       'expandir', 'contrair', 'Pendência (achado da revisão)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat(criteria))
        self.assertNotIn('## Verificação da fatia vertical', template)

    def test_the_protocol_the_readme_and_the_evals_follow(self):
        protocol = read('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('| Slices |', protocol)
        for phrase in ('`slices`', 'bloqueadoras primeiro', 'delivers'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat(protocol))
        readme = flat(read('README.md'))
        for phrase in ('uma caixa por slice', 'lista numerada'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        evals = flat(read('evals', 'vertical-slices.md'))
        for phrase in ('numbered list', 'base commit', 'what can be demoed'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evals)


if __name__ == '__main__':
    unittest.main()
