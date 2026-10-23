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
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(SKILL / 'scripts'))
import frontlights

sys.path.insert(0, str(ROOT / 'tests'))
import skilltext  # noqa: E402

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
                 seams=['POST /observations'], layers=['Tela', 'API', 'Testes'], depends_on=list(depends_on),
                 depends_why={dep: f'usa o que {dep} entrega' for dep in depends_on},
                 files=[f'src/slice{number}.py'], walkthrough=walkthrough())
    value.update(extra)
    return value


def walkthrough(**extra):
    value = dict(persona='conta 1', steps='abrir a observação, salvar e recarregar',
                 before='a observação some ao recarregar', after='a observação aparece depois de recarregar')
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

    def test_a_slice_without_a_walkthrough_is_refused(self):
        """Issue 65, S3: cada fatia nasce com roteiro (persona, passos, antes, depois); sem ele, o plano é inválido."""
        bare = slice_(1)
        del bare['walkthrough']
        with self.assertRaisesRegex(ValueError, r'1: slice S1: falta walkthrough'):
            frontlights.validate_plan(plan(issue(1, [bare])))
        for value in ('conta 1 · salvar', ['conta 1'], None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, r'slice S1: falta walkthrough'):
                frontlights.validate_plan(plan(issue(1, [slice_(1, walkthrough=value)])))

    def test_a_walkthrough_with_an_empty_before_is_refused(self):
        for before in ('', '   ', None):
            with self.subTest(before=before), self.assertRaisesRegex(ValueError, r'slice S1: falta walkthrough\.before'):
                frontlights.validate_plan(plan(issue(1, [slice_(1, walkthrough=walkthrough(before=before))])))
        missing = walkthrough()
        del missing['before']
        with self.assertRaisesRegex(ValueError, r'slice S1: falta walkthrough\.before'):
            frontlights.validate_plan(plan(issue(1, [slice_(1, walkthrough=missing)])))

    def test_every_field_of_the_walkthrough_is_a_non_empty_string(self):
        for field in ('persona', 'steps', 'after'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, rf'slice S2: falta walkthrough\.{field}'):
                frontlights.validate_plan(plan(issue(1, [slice_(1), slice_(2, walkthrough=walkthrough(**{field: ''}))])))

    def test_a_complete_walkthrough_is_valid_and_the_persona_is_only_a_label(self):
        for persona in ('conta 1', 'conta 2', 'sem tela', 'usuário de teste criado'):
            with self.subTest(persona=persona):
                frontlights.validate_plan(plan(issue(1, [slice_(1, walkthrough=walkthrough(persona=persona))])))

    def test_the_cli_refuses_a_plan_whose_slice_has_no_walkthrough(self):
        example = json.loads(read('skills', 'frontlights', 'examples', 'plan.json'))
        del example['issues'][0]['slices'][0]['walkthrough']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plan.json'
            path.write_text(json.dumps(example, ensure_ascii=False), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), 'validate-plan', '--plan', str(path)],
                                    capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('slice S1: falta walkthrough', result.stdout + result.stderr)
        self.assertIn('walkthrough.before', result.stdout + result.stderr)

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

    def test_an_issue_holds_at_most_five_slices(self):
        """Issue curta (issue 31, S1): até cinco caixas S<n>; a sexta é recusada com o teto na mensagem, e o
        excedente vira issue de topo ligada por blocked-by (regra de texto, abaixo)."""
        five = [slice_(1)] + [slice_(n, ['S1']) for n in range(2, 6)]
        frontlights.validate_plan(plan(issue(1, five)))
        self.assertEqual(frontlights.SLICES_MAX, 5)
        with self.assertRaisesRegex(ValueError, r'1: .*6 slices.*no máximo 5.*issues de topo'):
            frontlights.validate_plan(plan(issue(1, five + [slice_(6, ['S1'])])))

    def test_the_example_plan_carries_slices_and_still_schedules(self):
        example = json.loads(read('skills', 'frontlights', 'examples', 'plan.json'))
        sliced = [i for i in example['issues'] if i.get('slices')]
        self.assertGreaterEqual(len(sliced), 2)
        self.assertTrue(any(any(s['depends_on'] for s in i['slices']) for i in sliced))
        for item in (s for i in sliced for s in i['slices']):
            with self.subTest(slice=item['id']):
                self.assertEqual(set(item['walkthrough']), {'persona', 'steps', 'before', 'after'})
        frontlights.validate_plan(copy.deepcopy(example))
        result = subprocess.run([sys.executable, str(SCRIPT), 'validate-plan', '--plan',
                                 str(SKILL / 'examples' / 'plan.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'valid': True, 'semantic_review_required': True,
                          'waves': {'1': [['S1'], ['S2']], '3': [['S1'], ['S2']]}})
        self.assertEqual(frontlights.schedule(copy.deepcopy(example), 2), [1, 2])


class SlicesTextTests(unittest.TestCase):
    def test_stage_5_cuts_the_body_into_slices_and_asks_the_quiz_before_the_body(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        # redesenho, issue 3: a etapa 5 virou um item da lista numerada, em palavras mais curtas
        body = flat(skilltext.stage(5))
        self.assertNotEqual(body, '')
        for phrase in ('Read `references/issues.md`', 'tracer-bullet slices', 'each a box with',
                       'blockers first', 'Entrega, Seams, Camadas and Depende de', 'red at the base commit',
                       'Show the numbered list', 'granularity', 'merge or split', 'one write per issue',
                       'then reread GitHub', 'after reading every layer'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertNotIn('## 5. Issue-plan approval', skill)
        # redesenho, issue 3: o prefactoring, o corte expand/migrate/contract e o "what can be demoed" vivem em
        # issues.md, "Slices as acceptance criteria", para onde a etapa 5 aponta
        reference = flat(section(read('skills', 'frontlights', 'references', 'issues.md'),
                                 'Slices as acceptance criteria') or '')
        for phrase in ('Prefactoring', 'is the first slice and blocks the others', 'expand (add the new form beside the old)',
                       'contract', 'what can be demoed'):
            with self.subTest(where='issues.md', phrase=phrase):
                self.assertIn(phrase, reference)

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

    def test_the_reference_gives_each_box_its_walkthrough(self):
        """Issue 65, S3: a caixa traz o roteiro em duas linhas; o antes vem do reconhecimento; no plano é
        `walkthrough`, exigido pelo validate-plan; uma issue antiga ganha roteiro nas caixas abertas ao ser retomada."""
        text = read('skills', 'frontlights', 'references', 'issues.md')
        raw = section(text, 'Slices as acceptance criteria') or ''
        self.assertRegex(raw, r'(?m)^  - Roteiro: <persona> · <steps>$')
        self.assertRegex(raw, r'(?m)^    → antes: <[^>]+>; depois: <[^>]+>$')
        body = flat(raw)
        for phrase in ('`Roteiro: <persona> · <passos>`', '`→ antes: …; depois: …`', 'a label', 'never a login',
                       '`conta 1`', '`conta 2`', '`sem tela`', '`references/grilling.md`, "Reconnaissance"',
                       '`walkthrough`', '`persona`, `steps`, `before` and `after`',
                       'without `walkthrough` or with an empty `before`',
                       'An old issue', 'enters the grilling or stage 6', 'its open boxes', 'append only',
                       'the approval of the plan', 'Ticked boxes stay as they are'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_the_issue_template_box_carries_the_walkthrough(self):
        criteria = section(read('skills', 'frontlights', 'templates', 'issue.md'), 'Critérios de aceitação') or ''
        self.assertRegex(criteria, r'(?m)^  - Depende de: [^\n]*\n  - Roteiro: <[^>]+> · <[^>]+>\n'
                                   r'    → antes: <[^>]+>; depois: <[^>]+>$')
        self.assertIn('nunca login', flat(criteria))
        self.assertIn('reconhecimento', flat(criteria))

    def test_the_protocol_lists_the_walkthrough_of_a_slice(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('`walkthrough` (`persona`, `steps`, `before` e `after`: o roteiro da caixa', protocol)
        self.assertIn('sem `walkthrough` ou com `before` vazio', protocol)

    def test_the_cap_of_five_slices_is_written_where_the_cut_is_made(self):
        """Issue 31, S1: o teto de cinco CAs por issue, o corte do excedente em issues de topo com blocked-by e as
        caixas de pendência fora da conta aparecem na etapa 5, na referência, no modelo, no protocolo, no README e
        no ensaio."""
        skill = flat(skilltext.stage(5))
        for phrase in ('At most five tracer-bullet slices', 'the sixth becomes a top-level issue', '`--blocked-by`',
                       'leftover boxes do not count'):
            with self.subTest(where='SKILL.md', phrase=phrase):
                self.assertIn(phrase, skill)
        reference = flat(section(read('skills', 'frontlights', 'references', 'issues.md'),
                                 'Slices as acceptance criteria') or '')
        for phrase in ('at most five slices', 'sixth', 'top-level issues', '`--blocked-by`', 'Leftover boxes do not count',
                       '`validate-plan` refuses the sixth'):
            with self.subTest(where='issues.md', phrase=phrase):
                self.assertIn(phrase, reference)
        template = flat(section(read('skills', 'frontlights', 'templates', 'issue.md'), 'Critérios de aceitação') or '')
        for phrase in ('no máximo cinco', 'issues de topo', 'pendência não conta'):
            with self.subTest(where='templates/issue.md', phrase=phrase):
                self.assertIn(phrase, template)
        self.assertIn('até cinco por issue', flat(read('skills', 'frontlights', 'docs', 'protocol.md')))
        self.assertIn('até cinco caixas', flat(read('README.md')))  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        self.assertIn('more than five slices', flat(read('evals', 'vertical-slices.md')))

    def test_the_protocol_the_readme_and_the_evals_follow(self):
        protocol = read('skills', 'frontlights', 'docs', 'protocol.md')
        self.assertIn('| Slices |', protocol)
        for phrase in ('`slices`', 'bloqueadoras primeiro', 'delivers'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat(protocol))
        readme = flat(read('README.md'))
        for phrase in ('até 5 caixas na issue',):  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        evals = flat(read('evals', 'vertical-slices.md'))
        for phrase in ('numbered list', 'base commit', 'what can be demoed'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, evals)


class WavesTests(unittest.TestCase):
    """23/10/2026: fatias desenhadas para o paralelismo; arquivos por fatia, dependência com fato, ondas."""

    def test_a_slice_without_files_is_refused(self):
        bare = slice_(1)
        del bare['files']
        with self.assertRaisesRegex(ValueError, r'slice S1: falta files'):
            frontlights.validate_plan(plan(issue(1, [bare])))

    def test_a_dependency_without_its_fact_is_refused(self):
        second = slice_(2, depends_on=['S1'])
        second['depends_why'] = {}
        with self.assertRaisesRegex(ValueError, r'slice S2 depende de S1 sem fato'):
            frontlights.validate_plan(plan(issue(1, [slice_(1), second])))

    def test_waves_follow_dependencies_and_shared_files(self):
        slices = [slice_(1), slice_(2), slice_(3, files=['src/slice1.py/parte']), slice_(4, depends_on=['S2'])]
        self.assertEqual(frontlights.slice_waves(slices), [['S1', 'S2'], ['S3', 'S4']])

    def test_independent_slices_on_their_own_files_share_the_first_wave(self):
        self.assertEqual(frontlights.slice_waves([slice_(1), slice_(2), slice_(3)]), [['S1', 'S2', 'S3']])

    def test_the_box_names_the_fact_of_each_dependency(self):
        text = frontlights.depends_text(slice_(2, depends_on=['S1']))
        self.assertEqual(text, 'S1 (usa o que S1 entrega)')
        self.assertEqual(frontlights.depends_text(slice_(1)), 'nenhuma')

    def test_the_rule_lives_in_issues_md(self):
        rule = flat(section(read('skills', 'frontlights', 'references', 'issues.md'), 'Waves'))
        for phrase in ('Cut for parallelism: the most in the first wave, a wait only where a fact forces it',
                       'two slices sharing a file never run together', 'a dependency without one is removed',
                       '`validate-plan` prints them', 'a shared file is asked before code',
                       'Each slice crosses every layer its behavior needs and is demonstrable alone'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        self.assertIn('quiz (waves, granularity, real dependencies, merge or split)',
                      flat(read('skills', 'frontlights', 'SKILL.md')))


if __name__ == '__main__':
    unittest.main()
