"""Uma issue e as sub-issues andam juntas, empilhadas na branch do pai, e o teste de navegador é assistido.

Seams: o planejador (`frontlights.schedule`) e a validação do plano com filhas, mais o texto
da skill, das referências, do modelo de issue e da documentação (o script não executa as
etapas, então as regras de fluxo só se provam pelo texto e pela revisão manual de `evals/runbook.md`).
"""
import copy
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import frontlights


def member(number, paths, dependencies=(), parent=None):
    item = dict(id=number, title=f'Deliver outcome {number}',
                outcome='User can save and retrieve an observation',
                acceptance=['Saved observation appears after reload'],
                tests=['Save through API then fetch and assert the value'],
                ownership=paths, dependencies=list(dependencies),
                vertical_check='Save in UI, reload, observe persisted value',
                non_goals=['Bulk import'], risks=['Concurrent updates'],
                session_sized=True, status='ready',
                url=f'https://github.com/example/project/issues/{number}')
    if parent is not None:
        item['parent'] = parent
    return item


def family():
    """Pai 1; filhas 2, 3 e 4 dependem dele e não se sobrepõem; a 5 sobrepõe a 2; a 6 só pertence ao pai."""
    return {'repository': 'example/project', 'issues': [
        member(1, ['src/feature']),
        member(2, ['src/feature/a'], [1], parent=1),
        member(3, ['src/feature/b'], [1], parent=1),
        member(4, ['src/feature/c'], [1], parent=1),
        member(5, ['src/feature/a/deep'], [1], parent=1),
        member(6, ['src/other'], parent=1)]}


def stacked_view(plan, parent):
    """Cópia descartável em que o pai conta como `verified`, para medir a onda empilhada."""
    view = copy.deepcopy(plan)
    next(i for i in view['issues'] if i['id'] == parent)['status'] = 'verified'
    return view


class StackedWaveTests(unittest.TestCase):
    def test_the_family_validates_with_children_that_depend_on_the_parent(self):
        frontlights.validate_plan(family())

    def test_children_wait_for_the_parent_but_a_member_without_dependency_starts_with_it(self):
        self.assertEqual(frontlights.schedule(family(), 24), [1, 6])

    def test_the_stacked_wave_is_the_independent_children_with_disjoint_files(self):
        self.assertEqual(frontlights.schedule(stacked_view(family(), 1), 24), [2, 3, 4, 6])

    def test_overlapping_children_never_share_a_wave(self):
        for limit in range(1, 7):
            with self.subTest(limit=limit):
                wave = frontlights.schedule(stacked_view(family(), 1), limit)
                self.assertLessEqual(len(wave), limit)
                self.assertFalse({2, 5} <= set(wave))

    def test_the_planner_does_not_edit_the_plan_it_measures(self):
        plan = stacked_view(family(), 1)
        before = copy.deepcopy(plan)
        frontlights.schedule(plan, 24)
        self.assertEqual(plan, before)

    def test_the_overlapping_child_runs_once_the_other_one_is_done(self):
        plan = stacked_view(family(), 1)
        by_id = {i['id']: i for i in plan['issues']}
        by_id[2]['status'] = 'running'
        self.assertEqual(frontlights.schedule(plan, 24), [3, 4, 6])
        by_id[2]['status'] = 'verified'
        self.assertEqual(frontlights.schedule(plan, 24), [3, 4, 5, 6])

    def test_a_running_child_needs_the_parent_verified(self):
        plan = family()
        next(i for i in plan['issues'] if i['id'] == 2)['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'dependency'):
            frontlights.schedule(plan, 24)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(rf'^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match.group(1) if match else None


def labels(text, pattern):
    match = re.search(pattern, flat(text))
    assert match, pattern
    return match.groups()


class FamilyRulesTextTests(unittest.TestCase):
    def test_the_skill_moves_an_issue_with_all_its_open_sub_issues(self):
        text = flat(read('skills', 'frontlights', 'SKILL.md'))
        for phrase in ('An issue and its sub-issues move together', 'all its open sub-issues',
                       'subIssuesSummary', 'Work the parent and every open child together',
                       'only an explicit choice of the user narrows the work',
                       'does not serialize the work behind a merge', 'the issue has open sub-issues'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_stage_three_five_and_six_carry_the_family_rules(self):
        text = read('skills', 'frontlights', 'SKILL.md')
        stage3 = flat(text.split('## 3.')[1].split('## 4.')[0])
        stage5 = flat(text.split('## 5.')[1].split('## 6.')[0])
        stage6 = flat(text.split('## 6.')[1])
        self.assertIn('needs-decision', stage3)
        self.assertIn('own solution round', stage3)
        self.assertIn('every layer', stage5)
        self.assertIn('layers analysed', stage5)
        self.assertIn('The scope is the whole family', stage6)
        development = flat(read('skills', 'frontlights', 'references', 'development.md'))
        for phrase in ('no stacking question', 'independent children', 'without waiting for the merge'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)

    def test_issues_reference_defines_the_slice_and_its_layers(self):
        issues = read('skills', 'frontlights', 'references', 'issues.md')
        body = flat(section(issues, 'The issue and its layers (a family that already exists)') or '')
        for phrase in ('An issue, together with the sub-issues it already has',
                       'every layer the requirement needs', '## Camadas da fatia',
                       'not touched with the reason', 'a gap in the plan',
                       'does not contradict the rule against splitting by layer',
                       'membership, not a dependency', 'needs-decision'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)
        self.assertIn('Do not split by UI/API/database layers.', issues)

    def test_issue_template_has_the_layers_table(self):
        template = section(read('skills', 'frontlights', 'templates', 'issue.md'), 'Camadas da fatia') or ''
        self.assertNotEqual(template, '')
        for layer in ('Tela', 'API', 'Banco e migração', 'Testes', 'Integração', 'Documentação'):
            with self.subTest(layer=layer):
                self.assertRegex(template, rf'(?m)^\| {layer} \|')
        self.assertIn('lacuna do plano', template)

    def test_the_slice_is_defined_only_after_tracing_every_screen_field_to_the_back_and_the_database(self):
        issues = flat(section(read('skills', 'frontlights', 'references', 'issues.md'),
                              'The issue and its layers (a family that already exists)') or '')
        for phrase in ("Define the issue's layers only after reading every layer",
                       'the consumer in the back (`file:line`) and the column in the database',
                       'only with the evidence of that trace', 'A reason without evidence is not accepted',
                       'never "not touched"', 'prove the consumption by a test or by reading the execution',
                       'blocks the approval of the plan', 'a declared gap is not a state in which a plan can be approved',
                       'no row lacks evidence'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, issues)
        skill = read('skills', 'frontlights', 'SKILL.md')
        self.assertIn('field-by-field trace', flat(section(skill, '4. Issue') or ''))
        self.assertIn('only after reading every layer', flat(section(skill, '5. Slices and publication') or ''))
        self.assertIn('trace table', flat(read('skills', 'frontlights', 'references', 'issue.md')))
        self.assertIn('effect in the back and the database', flat(read('skills', 'frontlights', 'references', 'browser-testing.md')))

    def test_issue_template_asks_for_evidence_and_the_field_trace(self):
        template = section(read('skills', 'frontlights', 'templates', 'issue.md'), 'Camadas da fatia') or ''
        self.assertRegex(template, r'(?m)^\| Camada \| Situação \| Onde ou motivo \| Evidência \|')
        self.assertRegex(template, r'(?m)^\| Campo ou ação \| Consumidor no back \(arquivo:linha\) \| Coluna no banco \| Teste \|')
        flat_template = flat(template)
        for phrase in ('motivo sem evidência não é aceito', 'bloqueia a aprovação do plano',
                       'provar o consumo por teste ou por leitura da execução'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat_template)
        self.assertIn('o efeito no back e no banco depois de salvar', read('skills', 'frontlights', 'templates', 'issue.md'))
        evals = flat(read('evals', 'vertical-slices.md'))
        self.assertIn('Trace case (manual)', evals)
        self.assertIn('a layer "not touched" with a reason but no evidence', evals)

    def test_grilling_takes_sub_issues_into_the_same_session(self):
        body = flat(section(read('skills', 'frontlights', 'references', 'grilling.md'),
                            'Sub-issues of the issue (same session)') or '')
        for phrase in ('grilled in this session', 'needs-decision', 'own solution round',
                       '**Decided:**', '**Pending:**', 'confirmed together in one question'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_development_offers_stacked_branches_with_the_safe_mechanics(self):
        body = flat(section(read('skills', 'frontlights', 'references', 'development.md'),
                            'Stacked branches: parent and children without waiting for the merge') or '')
        for phrase in ('"Como as filhas se apoiam no pai?"', '"Empilhadas no pai (Recomendada)"',
                       '"Esperar o merge do pai"', 'schedule --limit 24', 'throwaway copy',
                       'git merge-base --is-ancestor', 'Stack on one dependency only',
                       'unless one already contains the other',
                       "A verified child is merged into its parent's branch", 'the family enters the local main as one',
                       'never a rebase or a force-push', 'conflicts on the hunks the child shares',
                       'which are the only merges it allows; merging a PR, writing the remote main, deploying and '
                       'releasing stay on the denied list',
                       'Only the branch of each issue of the family is pushed, by the same rule as any issue',
                       'no pull request is opened for the parent or a child',
                       '`gh issue develop <child> --repo <repo> --base <parent branch> --name <branch_prefix>issue-<child>`',
                       'only `"base": "<dependency-branch>"`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_option_labels_in_the_docs_fit_the_five_word_limit(self):
        stacking = labels(read('skills', 'frontlights', 'references', 'development.md'),
                          r'with "([^"]+)" first .*? and "([^"]+)" second')
        watching = labels(read('skills', 'frontlights', 'references', 'browser-testing.md'),
                          r'Options: "([^"]+)" first and recommended; "([^"]+)" \(.*?\); "([^"]+)" \(')
        no_move = labels(read('skills', 'frontlights', 'references', 'browser-testing.md'),
                         r'a fourth option, "([^"]+)"')
        self.assertEqual(len(stacking) + len(watching) + len(no_move), 6)
        for label in (*stacking, *watching, *no_move):
            with self.subTest(label=label):
                self.assertLessEqual(len(label.split()), 5)

    def test_the_covered_merges_are_one_list_in_development(self):
        """The covered merges are listed once, in development.md ("Standing authorization and the denied
        operations"); the other texts point there (tests/test_single_source.py catches a copy)."""
        body = flat(section(read('skills', 'frontlights', 'references', 'development.md'),
                            'Standing authorization and the denied operations') or '')
        for phrase in ('**Covered merges.** The run makes these merges on its own, and only these:',
                       "a base into an issue's own branch;",
                       "a slice's branch into the branch of its own issue when its loop closes;",
                       "the branch of the issue (or of the slice it depends on) into a slice's branch, to bring it "
                       "up to date;",
                       "a verified child's branch into its parent's branch;",
                       "a family's or batch's verified branches into a local integration branch that stays local;",
                       "`origin/<base>` into the local main by `homolog sync` at the start of stage 6 (a conflict is "
                       "undone and becomes a question);",
                       'the local main and the branches of the issues in progress into the preview branch by '
                       '`serve preview refresh` (a conflict is undone and becomes a question);',
                       'the branch of the issue into the local main once its watched run is answered or not needed',
                       'the push of the branch of the issue after each slice merge',
                       'the branches of the slices, the preview branch and the local main stay local'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_example_authorization_shows_a_stacked_worktree_base(self):
        import json
        charter = json.loads(read('skills', 'frontlights', 'examples', 'authorization.json'))
        stacked = [w for w in charter['worktrees'] if 'base' in w]
        self.assertEqual(len(stacked), 1)
        self.assertEqual(stacked[0]['base'], 'claude/issue-1')
        self.assertTrue(stacked[0]['branch'].startswith(charter['branch_prefix']))


class FamilyConversionTextTests(unittest.TestCase):
    """Issue 31, S4: uma família existente (pai com sub-issues) vira issue + CAs, por pedido em lote ("arrume as
    issues do MVP") ou por oferta quando a sessão vai agir numa família: o antes e o depois mostrados por inteiro,
    uma aprovação por família, o corpo do pai substituído (única exceção ao só-acréscimo, com o anterior guardado),
    as filhas fechadas como convertidas com o "Sim", o quadro ajustado com o "Sim", e mais de cinco filhas viram
    issues de topo ligadas por blocked-by. Nunca uma sub-issue nova."""

    def test_the_skill_offers_the_conversion_and_takes_the_batch_request(self):
        skill = flat(read('skills', 'frontlights', 'SKILL.md'))
        for phrase in ('offers its conversion into one issue with slices', 'a request to tidy a set of issues',
                       'one approval per family', '"Converting a family"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_the_reference_defines_the_procedure(self):
        text = read('skills', 'frontlights', 'references', 'issues.md')
        body = section(text, 'Converting a family into one issue with slices') or ''
        self.assertNotEqual(body, '')
        flat_body = flat(body)
        for phrase in ('one approval per family', 'the only exception to the append-only rule', 'body-before-<ts>.md',
                       'Convertida em CA S<k> da #<n>', '--reason "not planned"', 'more than five open children',
                       'up to five slices each', '`--blocked-by`', 'dividida em #a, #b', 'the before and the after',
                       'gh project item-archive', 'closed sub-issues are history', '**In batch.**', '**Offered.**',
                       'never as nested boxes', 'dividida em #a, #b") and changing the board are denied operations'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat_body)
        self.assertNotRegex(body, r'gh issue create [^`]*--parent')
        self.assertNotIn('sub_issues --method POST', body)

    def test_the_other_documents_follow(self):
        self.assertIn('declined the conversion', flat(read('skills', 'frontlights', 'references', 'grilling.md')))
        self.assertIn('closed by conversion', flat(read('skills', 'frontlights', 'references', 'closeout.md')))
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('conversão de uma família', 'única exceção', 'corpo anterior fica guardado'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn('conversão de família', flat(read('skills', 'frontlights', 'docs', 'protocol.md')))
        readme = flat(read('README.md'))
        for phrase in ('**Conversão de famílias.**', 'uma aprovação por família', 'arrume as issues'):
            with self.subTest(file='README', phrase=phrase):
                self.assertIn(phrase, readme)
        case = flat(read('evals', 'family-conversion.md'))
        for phrase in ('one approval per family', 'Reject:', 'more than five'):
            with self.subTest(file='eval', phrase=phrase):
                self.assertIn(phrase, case)
        self.assertIn('family-conversion.md', flat(read('evals', 'runbook.md')))
        self.assertIn('conversão de famílias', flat(read('docs', 'acceptance.md')))


class WatchedRunTextTests(unittest.TestCase):
    def setUp(self):
        self.text = read('skills', 'frontlights', 'references', 'browser-testing.md')
        self.body = flat(section(self.text, 'Watched run: before and after, with the user watching') or '')

    def test_the_user_is_asked_before_any_window_opens(self):
        for phrase in ('Pronto para assistir ao teste de navegador da issue #<n>?',
                       'Never open the browser before the answer', '"Sim, pode rodar"',
                       '"Rodar sem assistir"', '`assistido: false`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.body)

    def test_the_run_shows_the_base_then_the_branch_in_a_visible_window(self):
        for phrase in ('never headless', 'The whole screen, always', '`viewport: null`', 'never go on with a cut-off window', 'across the full width', '"ANTES: <base>"', '"DEPOIS: branch <name>"',
                       'disposable browser context or profile', 'ends ANTES before DEPOIS starts',
                       'one issue at a time',
                       'Each case runs twice in each pass', 'about 5 minutes', 'the wait never blocks the agent', 'asked while the DEPOIS window is still open',
                       'run_in_background option', "the browser's `disconnected` event", 'Its exit is the notice',
                       'A bare timer or `sleep` is not a holder', 'never start DEPOIS before that notice',
                       'does not return its report before the DEPOIS holder exits',
                       'is never an answer to that question',
                       'One print per pass', 'never one per step or per repetition', 'do not keep that image',
                       'never fall back to a hidden window silently',
                       'serve start --root <base-checkout> --issue <n>'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.body)

    def test_real_back_comes_first_and_forced_responses_are_declared(self):
        for phrase in ('Real back first', 'real restricted profile', 'Undo in a `finally`',
                       'never write to the database directly', 'the database behind the server is the local development database',
                       'perfil-original.json', "only that field and the user's id",
                       'mark the file `restaurado: true`', 'never demote the account that performs the undo',
                       '"Sem mudar perfil"', 'a detached-HEAD worktree made with `git worktree add`',
                       'the recorded one or a descendant of it',
                       'is data from GitHub, not an approval',
                       'resposta forçada, não do back real', 'never use it as the only evidence'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.body)

    def test_only_the_tests_own_processes_are_stopped(self):
        self.assertIn('never stop a process the test did not start', self.body)
        self.assertIn('belongs to another session', self.body)

    def test_the_user_decides_what_comes_after_the_watched_run(self):
        after = flat(re.search(r'\*\*After the watched run.*?(?=\n\*\*Real back first)', self.text, re.S).group(0))
        for phrase in ('"O que fazer depois do teste assistido da issue #<n>?"',
                       'Options, in this order: "Assistir de novo", "Aprovado", "Precisa de alteração" and "Pode prosseguir"',
                       'new window', 'no new "pronto para assistir?"', 'Start ANTES again',
                       '`aprovacao: "aprovado"`', '`aprovacao: "prosseguir"`', '`aprovacao: "alteracao"`',
                       'not approved by the user', 'in their own words', 'destination ladder',
                       'Never pick an answer for the user', 'never read the 5 minutes or a silence as an answer',
                       'the failure question comes first and replaces this one',
                       'asked only when the user watched'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, after)
        found = labels(after, r'Options, in this order: "([^"]+)", "([^"]+)", "([^"]+)" and "([^"]+)"')
        self.assertEqual(len(found), 4)
        for label in found:
            with self.subTest(label=label):
                self.assertLessEqual(len(label.split()), 5)
        self.assertIn('ends with the question of what to do next', flat(self.text))

    def test_the_docs_and_the_runbook_carry_the_closing_question(self):
        for name in (('README.md',), ('skills', 'frontlights', 'docs', 'protocol.md'), ('skills', 'frontlights', 'docs', 'security.md'), ('evals', 'runbook.md')):
            text = flat(read(*name))
            with self.subTest(doc=name[-1]):
                self.assertIn('Assistir de novo', text)
                self.assertIn('Aprovado', text)
                self.assertIn('Precisa de alteração', text)
                self.assertIn('Pode prosseguir', text)
        for name in (('README.md',), ('skills', 'frontlights', 'docs', 'protocol.md'), ('evals', 'runbook.md')):
            with self.subTest(doc=name[-1], field='record'):
                text = flat(read(*name))
                self.assertIn('`rodadas`', text)
                self.assertIn('`aprovacao`', text)
        self.assertIn('never write `aprovacao: "aprovado"` on your own', flat(self.text))
        self.assertIn('nunca grava `aprovacao: "aprovado"` por conta própria', flat(read('skills', 'frontlights', 'docs', 'security.md')))

    def test_the_run_is_part_of_the_order_the_evidence_and_the_docs(self):
        evidence = flat(section(self.text, 'Evidence') or '')
        self.assertIn('A watched run adds `assistido`', evidence)
        self.assertIn('`rodadas`', evidence)
        self.assertIn('`aprovacao` (`aprovado`, `prosseguir` or `alteracao`)', evidence)
        self.assertIn('exactly one per pass and issue, named `antes-<n>` and `depois-<n>`', evidence)
        self.assertIn('only the profile field before and after the undo', evidence)
        self.assertIn('the watched-run question below', flat(self.text))
        self.assertIn('"pronto para assistir?"', flat(read('skills', 'frontlights', 'references', 'development.md')))
        for doc in (('skills', 'frontlights', 'docs', 'protocol.md'), ('skills', 'frontlights', 'docs', 'security.md'), ('README.md',)):
            with self.subTest(doc=doc[-1]):
                self.assertIn('assistir', flat(read(*doc)))


class PublicRepositoryTests(unittest.TestCase):
    def test_the_new_rules_carry_no_machine_path(self):
        names = [SKILL / 'SKILL.md', *(SKILL / 'references').glob('*.md'), ROOT / 'README.md',
                 ROOT / 'skills' / 'frontlights' / 'templates' / 'issue.md', *(ROOT / 'docs').glob('*.md'),
                 ROOT / 'evals' / 'runbook.md', ROOT / 'evals' / 'vertical-slices.md',
                 ROOT / 'skills' / 'frontlights' / 'examples' / 'authorization.json']
        for path in names:
            text = path.read_text(encoding='utf-8')
            with self.subTest(path=path.name):
                self.assertNotRegex(text, r'[A-Za-z]:[\\/]+(Users|Software)\b|/(home|Users)/[A-Za-z]')


if __name__ == '__main__':
    unittest.main()
