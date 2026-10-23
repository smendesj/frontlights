import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import frontlights

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class ReleaseManifestTests(unittest.TestCase):
    """The skill is installed by a junction into its checkout; the session invokes it, so can the model."""

    def test_single_invocable_skill_whose_stage_references_exist(self):
        skills = sorted(p.name for p in (ROOT / 'skills').iterdir() if p.is_dir())
        self.assertEqual(skills, ['frontlights'])
        text = (ROOT / 'skills' / 'frontlights' / 'SKILL.md').read_text(encoding='utf-8')
        head = text.split('---')[1]
        self.assertIn('user-invocable: true', head)
        self.assertIn('disable-model-invocation: false', head)
        self.assertNotIn('CLAUDE_PLUGIN_ROOT', text)
        for folder in ('scripts', 'templates', 'examples', 'docs', 'references'):
            self.assertTrue((ROOT / 'skills' / 'frontlights' / folder).is_dir(), folder)
        self.assertFalse((ROOT / '.claude-plugin').exists())
        for name in ('grilling', 'issue', 'issues', 'development', 'progress-report'):
            self.assertIn(f'references/{name}.md', text)
            self.assertTrue((ROOT / 'skills' / 'frontlights' / 'references' / f'{name}.md').is_file())
        for gone in ('roadmap-sync', 'issue-gaps'):
            with self.subTest(gone=gone):
                self.assertFalse((ROOT / 'skills' / 'frontlights' / 'references' / f'{gone}.md').exists())
                self.assertNotIn(f'references/{gone}.md', text)

    def test_the_opening_asks_only_the_closeout_question(self):
        # issue 65: the session opens with no RoadS question; the summary runs when the user asks for it
        text = (ROOT / 'skills' / 'frontlights' / 'SKILL.md').read_text(encoding='utf-8')
        # redesenho, issue 3: a etapa 1 é um item da lista numerada; a pergunta única se diz "the only opening question"
        stage1 = skilltext.flat(skilltext.stage(1))
        opening = stage1.split('Choose the lightest path')[0]
        self.assertEqual(opening.count('question'), 1)
        self.assertIn('the only opening question: "Fechar as issues que já têm todos os critérios marcados?"', opening)
        for gone in ('roads.py" status', 'Completar no GitHub as issues que o RoadS mostra?',
                     'Atualizar também o Resumo para a diretoria no RoadS?',
                     'Registrar o projeto que guarda o bloco do Resumo para a diretoria?',
                     'Issue-gaps question', 'Progress question', 'every session'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, stage1)
        self.assertNotIn('Atualizar a sprint e o roadmap', text)
        self.assertNotIn('roadmap_sync', text)

    def test_the_summary_runs_when_the_user_asks_for_it_from_any_project(self):
        # redesenho, issue 3: o "**Board summary on request.**" virou uma frase da etapa 1; o "só a pedido" e o
        # `--root <operationsRoot>` vivem em references/progress-report.md
        stage1 = skilltext.flat(skilltext.stage(1))
        rule = '"Resumo para a diretoria", any project: `progress_report.py status`, then `references/progress-report.md`.'
        self.assertIn(rule, stage1)
        self.assertLess(stage1.index(rule), stage1.index('Choose the lightest path'))
        reference = ' '.join((ROOT / 'skills' / 'frontlights' / 'references' / 'progress-report.md')
                             .read_text(encoding='utf-8').split())
        self.assertIn('--root <operationsRoot>`', reference)
        self.assertIn('runs only when the user asks for the summary', reference)
        self.assertIn('Registrar o projeto que guarda o bloco do Resumo para a diretoria?', reference)
        self.assertNotIn('stage 1 question', reference)
        self.assertNotIn('progress question', reference)

    def test_issue_gaps_is_gone_from_the_skill_and_its_documentation(self):
        skill = ROOT / 'skills' / 'frontlights'
        files = (sorted(skill.rglob('*.md')) + sorted(skill.rglob('*.py')) + [ROOT / 'README.md']
                 + sorted((ROOT / 'evals').glob('*.md')) + sorted((ROOT / 'docs').glob('*.md')))
        banned = ('issue-gaps', 'Completar no GitHub as issues que o RoadS mostra', 'roads.py status|approve|gaps',
                  'Atualizar também o Resumo para a diretoria no RoadS', 'da pergunta das issues do RoadS')
        for path in files:
            flat = ' '.join(path.read_text(encoding='utf-8').split())
            for phrase in banned:
                with self.subTest(file=str(path.relative_to(ROOT)), phrase=phrase):
                    self.assertNotIn(phrase, flat)

    def test_session_start_never_looks_for_remote_control(self):
        skill = ROOT / 'skills' / 'frontlights'
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        stage0 = skilltext.stage(0)
        self.assertIn('update-check', stage0)
        for banned in ('monitoring', 'claude rc', 'Remote Control'):
            self.assertNotIn(banned, stage0)
        self.assertNotIn('remote-control', text)
        self.assertFalse((skill / 'references' / 'remote-control.md').exists())
        self.assertFalse(hasattr(frontlights, 'monitoring'))

    def test_grilling_always_proposes_approaches_that_respect_the_code_pattern(self):
        skill = ROOT / 'skills' / 'frontlights'
        grilling = (skill / 'references' / 'grilling.md').read_text(encoding='utf-8')
        self.assertIn('at least three genuinely different approaches', grilling)
        self.assertIn('never removes the solution round', grilling)
        self.assertIn('The existing pattern is the default.', grilling)
        self.assertIn('Never decide alone that the interview is over.', grilling)
        self.assertLess(grilling.index('## 2. Project conventions'), grilling.index('## 3. Solution round'))
        # redesenho, issue 3: a etapa 3 diz "at least three approaches with their pattern fit"; "an issue ... still
        # runs the solution round" vive em grilling.md ("it never removes the solution round", acima)
        stage3 = skilltext.flat(skilltext.stage(3))
        self.assertIn('at least three approaches with their pattern fit', stage3)
        self.assertIn('Starting from an issue shortens the problem round; it never removes the solution round.',
                      ' '.join(grilling.split()))
        for template, heading in (('discovery.md', 'onventions'), ('issue.md', 'Decisões de implementação')):
            with self.subTest(template=template):
                self.assertIn(heading, (ROOT / 'skills' / 'frontlights' / 'templates' / template).read_text(encoding='utf-8'))

    def test_learning_mode_is_gone_from_the_skill_readme_and_runbook(self):
        skill = ROOT / 'skills' / 'frontlights'
        self.assertFalse((skill / 'references' / 'learning.md').exists())
        files = sorted(skill.rglob('*.md')) + [ROOT / 'README.md', ROOT / 'evals' / 'runbook.md']
        banned = ('learning', 'aprendizado', 'Explicar antes de decidir', 'Ficou claro',
                  '"a revisar"', 'Seguir a recomendação', 'Concepts explained', 'conceitos explicados')
        for path in files:
            flat = ' '.join(path.read_text(encoding='utf-8').split())
            for phrase in banned:
                with self.subTest(file=str(path.relative_to(ROOT)), phrase=phrase):
                    self.assertNotIn(phrase.lower(), flat.lower())

    def test_grilling_opens_without_the_depth_and_expands_a_section_on_request(self):
        skill = ROOT / 'skills' / 'frontlights'
        flat = ' '.join((skill / 'references' / 'grilling.md').read_text(encoding='utf-8').split())
        self.assertNotIn('## 0. Depth', flat)
        self.assertNotIn('Ativar', flat.split('## 1. Problem round')[0])
        solution = flat.split('## 3. Solution round')[1].split('## 4. Decision tree')[0]
        for phrase in ('at least three genuinely different approaches',
                       'and up to four, in one `AskUserQuestion`, one per option'):
            with self.subTest(section='solution', phrase=phrase):
                self.assertIn(phrase, solution)
        tree = flat.split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0]
        for phrase in ('batched at most four per call', 'up to four real options',
                       'asks for more detail in free text', '"não entendi"', '"detalhe no artefato"',
                       "expands that question's section of the artifact on the same URL",
                       'asks the same question again',
                       'the only re-ask besides new evidence'):
            with self.subTest(section='tree', phrase=phrase):
                self.assertIn(phrase, tree)
        runbook = ' '.join((ROOT / 'evals' / 'runbook.md').read_text(encoding='utf-8').split())
        self.assertIn('11. (Removed in issue #61', runbook)
        self.assertNotIn('Depth is asked once', flat)
        closing = flat.split('## 6. Closing')[1].split('## Recording')[0]
        self.assertIn('do not re-ask settled decisions unless new evidence invalidates them', closing)
        recording = flat.split('## Recording')[1]
        self.assertIn('Record everything in `templates/discovery.md`: conventions', recording)
        stage3 = skilltext.flat(skilltext.stage(3))
        self.assertIn('Read `references/grilling.md`. One problem question', stage3)

    def test_readme_says_each_decision_question_has_its_explaining_section(self):
        flat = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
        # issue 12 do redesenho: o README virou guia curto, com a mesma promessa em palavras novas
        for phrase in ('uma seção por decisão', 'a recomendada primeiro',
                       'texto livre ("não entendi") amplia a explicação'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_discovery_template_has_the_trigger_table_without_learning_mode(self):
        text = (ROOT / 'skills' / 'frontlights' / 'templates' / 'discovery.md').read_text(encoding='utf-8')
        self.assertNotIn('Learning mode', text)
        self.assertNotIn('Concepts explained', text)
        self.assertNotIn('Grilling depth', text)
        self.assertLess(text.index('## Project conventions'), text.index('## Reconnaissance'))
        self.assertLess(text.index('## Decisions'), text.index('## Pre-mortem'))

    def test_example_config_carries_only_generic_placeholders(self):
        example = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))
        sync = example['roadmapSync']
        self.assertRegex(sync['secretEnvVar'], r'^FRONTLIGHTS_[A-Z0-9_]+$')
        self.assertIn('example', sync['endpoint'])
        self.assertFalse(set(sync) & {'roadmapFile', 'sprintFilePattern', 'maxSprintItems', 'markCompleted', 'issueTargets'})
        self.assertNotIn('guardian', json.dumps(example).lower())

    def test_example_config_browser_and_checks_blocks_load_without_refusal(self):
        import checks
        import serve
        path = ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json'
        example = json.loads(path.read_text(encoding='utf-8'))
        processes = serve.load_block(path)
        self.assertTrue(processes and all(p['port'] == 'auto' for p in processes))
        self.assertTrue(all(p['health'].startswith('http://127.0.0.1:{port}/') for p in processes))
        checks.require_maskable_user_secrets(path)
        checks.require_local_declarations(path)
        for name in ('regression', 'integration'):
            with self.subTest(check=name):
                self.assertTrue(checks.command_settings(path, name)['argv'])
        self.assertTrue(checks.smoke_settings(path)['paths'])
        logins = [user['login'] for user in example['browserTest']['users']]
        self.assertEqual(logins, ['usuario1@exemplo.test', 'usuario2@exemplo.test'])
        self.assertTrue(all(user['password'] == 'senha-ficticia' for user in example['browserTest']['users']))
        hosts = re.findall(r'https?://([^/:"]+)', json.dumps({k: example[k] for k in ('browserTest', 'checks')}))
        self.assertTrue(hosts and set(hosts) <= {'127.0.0.1', 'localhost'})

    def test_work_is_named_by_issue_never_by_retired_gt_ids(self):
        skill = ROOT / 'skills' / 'frontlights'
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('.frontlights/issues/<n>/', text)
        self.assertIn('never mint `GT-NNNN`', skilltext.rule('The issue is the unit'))
        for path in (skill / 'references').glob('*.md'):
            with self.subTest(path=path.name):
                self.assertNotRegex(path.read_text(encoding='utf-8'), r'\bGTs?\b')


def issue(number, paths, dependencies=()):
    return dict(id=number, title=f'Deliver outcome {number}',
                outcome='User can save and retrieve an observation',
                acceptance=['Saved observation appears after reload'],
                tests=['Save through API then fetch and assert the value'],
                ownership=paths, dependencies=list(dependencies),
                vertical_check='Save in UI, reload, observe persisted value',
                non_goals=['Bulk import'], risks=['Concurrent updates'],
                session_sized=True, status='ready',
                url=f'https://github.com/example/project/issues/{number}')


def plan():
    return {'repository': 'example/project', 'issues': [
        issue(1, ['src/save']), issue(2, ['src/export']),
        issue(3, ['src/save/controller.py'], [1])]}


def charter(root):
    return dict(repository='example/project', issue_ids=[1, 2], concurrency=2,
                approved_by='human', approval_reference='session:turn-12',
                expires_at='2099-01-01T00:00:00+00:00',
                monitoring={'mode': 'local', 'confirmed_by': 'human'},
                protected_branches=['main', 'master', 'production'],
                operations=['edit', 'test', 'checkpoint', 'draft_pr', 'issue_update'],
                worktrees=[{'issue': 1, 'path': str(root),
                            'branch': 'claude/issue-1', 'ownership': ['src']}],
                verification_commands=[['python', '-m', 'unittest']],
                stop_conditions=['New product decision', 'Permission prompt'])


class PlanningTests(unittest.TestCase):
    def test_valid_vertical_plan(self):
        frontlights.validate_plan(plan())

    def test_reject_cycle_missing_dependency_duplicate(self):
        for mutation in ('cycle', 'missing', 'duplicate'):
            p = plan()
            if mutation == 'cycle':
                p['issues'][0]['dependencies'] = [3]
            elif mutation == 'missing':
                p['issues'][0]['dependencies'] = [99]
            else:
                p['issues'].append(p['issues'][0])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                frontlights.validate_plan(p)

    def test_horizontal_and_oversized_rejected(self):
        for field, value in [('vertical_check', ''), ('session_sized', False),
                             ('ownership', ['../elsewhere']), ('acceptance', [])]:
            p = plan()
            p['issues'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                frontlights.validate_plan(p)

    def test_refill_respects_dependencies_and_overlap(self):
        p = plan()
        self.assertEqual(frontlights.schedule(p, 2), [1, 2])
        p['issues'][0]['status'] = 'running'
        self.assertEqual(frontlights.schedule(p, 2), [2])
        p['issues'][0]['status'] = 'verified'
        self.assertEqual(frontlights.schedule(p, 2), [2, 3])
        p['issues'][1]['status'] = 'blocked'
        self.assertEqual(frontlights.schedule(p, 2), [3])

    def test_parent_case_and_unknown_ownership_conflict(self):
        for paths in (['SRC'], ['src/save'], ['*']):
            p = plan()
            p['issues'][1]['ownership'] = paths
            self.assertEqual(frontlights.schedule(p, 2), [1])

    def test_selects_maximum_safe_ready_set(self):
        p = plan()
        p['issues'] = [issue(1, ['src']), issue(2, ['src/a']), issue(3, ['src/b'])]
        self.assertEqual(frontlights.schedule(p, 2), [2, 3])

    def test_running_conflict_is_error(self):
        p = plan()
        p['issues'][1]['ownership'] = ['src']
        for i in p['issues'][:2]:
            i['status'] = 'running'
        with self.assertRaises(ValueError):
            frontlights.schedule(p, 2)

    def test_running_dependency_violation_is_error(self):
        p = plan()
        p['issues'][2]['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'dependency'):
            frontlights.schedule(p, 2)

    def test_an_invalid_status_lists_the_valid_ones_and_how_to_map_a_published_issue(self):
        p = plan()
        p['issues'][0]['status'] = 'published'
        with self.assertRaises(ValueError) as caught:
            frontlights.validate_plan(p)
        message = str(caught.exception)
        for name in ('ready', 'running', 'blocked', 'verified', 'proposed', "'published'"):
            self.assertIn(name, message)
        self.assertIn('published', message)
        self.assertIn('"ready" when its dependencies are met', message)

    def test_a_glob_in_ownership_says_what_to_write_instead(self):
        for value in ('src/**', 'src/*.ts', 'src/[ab]'):
            p = plan()
            p['issues'][0]['ownership'] = [value]
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                frontlights.validate_plan(p)
            message = str(caught.exception)
            self.assertIn(value, message)
            self.assertIn('name the folder or file', message)
            self.assertIn('use * for unknown ownership', message)

    def test_a_sub_issue_of_a_published_parent_outside_the_plan(self):
        project = {'owner': 'OWNER', 'number': 1, 'fields': {'Area': None}}
        p = dict(plan(), issues=[issue(1, ['src/save'])])
        p['issues'][0]['parent_external'] = 50
        frontlights.validate_plan(p)
        frontlights.validate_plan(p, project)   # no board field is asked of a sub-issue
        self.assertEqual(frontlights.board_resolution(p, project), None)

    def test_parent_external_cannot_name_an_issue_of_the_plan_and_null_means_absent(self):
        p = plan()
        p['issues'][0]['parent_external'] = 2       # 2 is an issue of this plan: use parent
        with self.assertRaisesRegex(ValueError, 'parent_external'):
            frontlights.validate_plan(p)
        p = plan()
        p['issues'][0]['parent_external'] = None
        frontlights.validate_plan(p)

    def test_parent_external_is_validated_and_exclusive(self):
        bad = {'text': '50', 'zero': 0, 'negative': -1, 'boolean': True, 'self': 1, 'float': 1.5}
        for label, value in bad.items():
            p = plan()
            p['issues'][0]['parent_external'] = value
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'parent_external'):
                frontlights.validate_plan(p)
        p = plan()
        p['issues'][1]['parent'] = 1
        p['issues'][1]['parent_external'] = 50
        with self.assertRaisesRegex(ValueError, 'parent_external'):
            frontlights.validate_plan(p)

    def test_a_sub_issue_of_an_outside_parent_takes_no_project_fields(self):
        project = {'owner': 'OWNER', 'number': 1, 'fields': {'Area': None}}
        p = dict(plan(), issues=[issue(1, ['src/save'])])
        p['issues'][0]['parent_external'] = 50
        p['issues'][0]['project_fields'] = {'Area': 'Backend'}
        with self.assertRaisesRegex(ValueError, 'sub-issue'):
            frontlights.validate_plan(p, project)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        self.c = charter(self.root)
        self.op = dict(repository='example/project', issue=1, kind='edit',
                       branch='claude/issue-1', worktree=str(self.root),
                       path=str(self.root / 'src' / 'app.py'))

    def test_positive_local_edit(self):
        frontlights.authorize(self.c, self.op)

    def test_a_slice_worktree_accepts_only_operations_for_its_slice(self):
        """Issue 31, S2: uma worktree por CA. A entrada do charter leva `slice`, e uma operação nela precisa
        nomear a mesma caixa; a worktree da issue (sem `slice`) continua aceitando operações sem caixa."""
        s2 = self.root / 's2'
        (s2 / 'src').mkdir(parents=True)
        c = dict(self.c, worktrees=self.c['worktrees'] + [
            {'issue': 1, 'path': str(s2), 'branch': 'claude/issue-1-s2', 'slice': 'S2', 'ownership': ['src']}])
        op = dict(self.op, worktree=str(s2), branch='claude/issue-1-s2', path=str(s2 / 'src' / 'app.py'))
        frontlights.authorize(c, dict(op, slice='S2'))
        frontlights.authorize(c, self.op)
        with self.assertRaisesRegex(ValueError, 'slice'):
            frontlights.authorize(c, op)
        with self.assertRaisesRegex(ValueError, "slice 'S1' on the worktree of slice 'S2'"):
            frontlights.authorize(c, dict(op, slice='S1'))
        with self.assertRaisesRegex(ValueError, 'slice'):
            frontlights.authorize(c, dict(self.op, slice='S1'))
        bad = dict(c, worktrees=[dict(c['worktrees'][1], slice='S 2')])
        with self.assertRaisesRegex(ValueError, 'slice'):
            frontlights.authorize(bad, dict(op, slice='S 2'))

    def test_forbidden_operations_repositories_issues_branches(self):
        changes = [('kind', x) for x in ['merge', 'deploy', 'release', 'delete',
                   'shell', 'road_ack', 'push', 'issue_close']]
        changes += [('repository', 'attacker/other'), ('issue', 9),
                    ('branch', 'main'), ('branch', 'production'),
                    ('branch', 'claude/unapproved'), ('issue', True)]
        for key, value in changes:
            op = dict(self.op, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                frontlights.authorize(self.c, op)

    def test_escape_and_policy_files_denied(self):
        for path in ['../escape', 'src/../../escape', '.git/config',
                     '.frontlights/authorization.json', 'CLAUDE.md', 'other/file']:
            op = dict(self.op, path=str(self.root / path))
            with self.subTest(path=path), self.assertRaises(ValueError):
                frontlights.authorize(self.c, op)

    def test_expired_unapproved_or_unmonitored_denied(self):
        for field, value in [('expires_at', '2020-01-01T00:00:00+00:00'),
                             ('approval_reference', ''), ('monitoring', {}),
                             ('concurrency', 0), ('approved_by', '')]:
            c = dict(self.c, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                frontlights.authorize(c, self.op)

    def test_exact_argv_no_shell_syntax(self):
        op = dict(self.op, kind='test', argv=['python', '-m', 'unittest'])
        frontlights.authorize(self.c, op)
        for argv in [['python', '-c', 'print(1)'], ['python -m unittest; git push'],
                     ['python', '-m', 'unittest', ';', 'gh', 'pr', 'merge']]:
            with self.assertRaises(ValueError):
                frontlights.authorize(self.c, dict(op, argv=argv))

    def test_external_writes_always_need_native_permission(self):
        for kind in ['draft_pr', 'issue_update']:
            with self.assertRaisesRegex(ValueError, 'external'):
                frontlights.authorize(self.c, dict(self.op, kind=kind))


class EvidenceTests(unittest.TestCase):
    def test_checkpoint_rejects_missing_handoff_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            handoff = root / 'handoff.md'
            snapshot = {'number': 1, 'title': 'Save', 'body': 'Accept A', 'state': 'OPEN',
                        'html_url': 'https://github.com/example/project/issues/1'}
            evidence = {'head': 'a' * 40, 'branch': 'codex/issue-1',
                        'diff_sha256': 'a', 'files_sha256': 'b', 'files': {}}
            with patch.object(frontlights, 'git_evidence', return_value=evidence):
                with self.assertRaises(ValueError):
                    frontlights.checkpoint(root, snapshot, handoff, 'Run focused tests')
                handoff.write_text('Acceptance: save persists. Next: run focused tests.')
                checkpoint = frontlights.checkpoint(root, snapshot, handoff, 'Run focused tests')
                self.assertEqual(frontlights.resume(root, checkpoint, snapshot, handoff)['state'], 'unchanged')
                changed = dict(snapshot, body='Accept B')
                self.assertEqual(frontlights.resume(root, checkpoint, changed, handoff)['state'], 'reconcile')
                handoff.write_text('Changed next action')
                self.assertEqual(frontlights.resume(root, checkpoint, snapshot, handoff)['state'], 'reconcile')

    def test_context_budget_fail_closed_and_reserves(self):
        self.assertEqual(frontlights.context_action(80000, 10000), 'continue')
        self.assertEqual(frontlights.context_action(99000, 1000), 'handoff')
        self.assertEqual(frontlights.context_action(140000, 10000), 'stop')
        self.assertEqual(frontlights.context_action(None, 1000), 'stop')
        # redesenho, issue 9: o corte duro em 200 mil (docs/protocol.md, "Contexto e conclusão")
        self.assertEqual(frontlights.context_action(190000, 10000), 'cut')
        self.assertEqual(frontlights.context_action(189000, 10000), 'stop')
        with self.assertRaises(ValueError):
            frontlights.context_action(-1, 100)

    def test_snapshot_drift_includes_acceptance_body_and_status(self):
        a = {'number': 1, 'title': 'Save', 'body': 'Accept A', 'state': 'OPEN'}
        self.assertEqual(frontlights.drift(a, dict(a)), [])
        self.assertEqual(frontlights.drift(a, dict(a, body='Accept B')), ['body'])

    def test_checkpoint_binds_git_head_and_dirty_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def git(*args):
                return subprocess.run(['git', '-C', d, *args], check=True,
                                      capture_output=True, text=True)
            git('init', '-b', 'codex/fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'user.name', 'Fixture')
            (root / 'app.txt').write_text('one')
            git('add', '.')
            git('commit', '-m', 'fixture')
            a = frontlights.git_evidence(root)
            (root / 'app.txt').write_text('two')
            b = frontlights.git_evidence(root)
            self.assertEqual(a['head'], b['head'])
            self.assertNotEqual(a['diff_sha256'], b['diff_sha256'])
            (root / 'new.txt').write_text('untracked')
            c = frontlights.git_evidence(root)
            self.assertNotEqual(b['files_sha256'], c['files_sha256'])

    def test_cli_invalid_json_exits_nonzero_without_traceback(self):
        result = subprocess.run([sys.executable, str(Path(frontlights.__file__)),
                                 'schedule', '--plan', 'missing.json', '--limit', '2'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)


class IntegrationReadTests(unittest.TestCase):
    def test_malformed_github_payload_is_unavailable(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', return_value=b'{"message":"error"}'):
            result = frontlights.inspect({'repository': 'example/project'}, root)
        self.assertEqual(result['sources']['github']['status'], 'unavailable')

    def test_github_pagination_filters_prs_roads_unconfigured(self):
        raw = json.dumps([[{'number': 1}], [{'number': 2, 'pull_request': {}}],
                          [{'number': 3}]]).encode()
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', return_value=raw) as run:
            result = frontlights.inspect({'repository': 'example/project'}, root)
        self.assertEqual([i['number'] for i in result['sources']['github']['issues']], [1, 3])
        self.assertIn('--paginate', run.call_args.args[0])
        self.assertEqual(result['sources']['roads']['status'], 'unconfigured')

    def test_unavailable_integrations_do_not_invent_data_or_echo_tokens(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=ValueError('private-secret')):
            result = frontlights.inspect({'repository': 'example/project', 'roads': {
                'observations_url': 'http://unsafe.example', 'token_env': 'MISSING_TOKEN'}}, root)
        self.assertEqual(result['sources']['github']['status'], 'unavailable')
        self.assertEqual(result['sources']['roads']['status'], 'unavailable')
        self.assertNotIn('private-secret', json.dumps(result))


def board(**overrides):
    project = {'owner': 'example-org', 'number': 3, 'assignee': '@me', 'issue_type': 'Task',
               'fields': {'Status': 'Open', 'Area': None}}
    project.update(overrides)
    return project


class ProjectBoardTests(unittest.TestCase):
    """Issues belong on the configured board; a board that is set must never be skipped."""

    def test_inspect_reports_board_unconfigured_when_absent_or_null(self):
        for config in ({'repository': 'example/project'}, {'repository': 'example/project', 'project': None}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as root, \
                    patch.object(frontlights, 'run', return_value=b'[]'):
                result = frontlights.inspect(config, root)
            self.assertEqual(result['sources']['project']['status'], 'unconfigured')

    def test_inspect_reads_the_configured_board(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'project', 'view']:
                return json.dumps({'title': 'Board', 'url': 'https://github.com/orgs/example-org/projects/3'}).encode()
            return b'[]'
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=fake) as run:
            result = frontlights.inspect({'repository': 'example/project', 'project': board()}, root)
        project = result['sources']['project']
        self.assertEqual(project['status'], 'available')
        self.assertEqual((project['owner'], project['number']), ('example-org', 3))
        self.assertEqual(project['defaults'], {'Status': 'Open'})
        self.assertEqual(project['choose_per_issue'], ['Area'])
        self.assertIn(['gh', 'project', 'view', '3', '--owner', 'example-org', '--format', 'json'],
                      [c.args[0] for c in run.call_args_list])

    def test_inspect_reports_an_unreachable_board_without_inventing_it(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'project', 'view']:
                raise ValueError('missing project scope private-token')
            return b'[]'
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=fake):
            result = frontlights.inspect({'repository': 'example/project', 'project': board()}, root)
        self.assertEqual(result['sources']['project']['status'], 'unavailable')
        self.assertNotIn('private-token', json.dumps(result))

    def test_inspect_rejects_a_malformed_board(self):
        for bad in (board(owner='bad owner'), board(number=0), board(number=True), board(number='3'),
                    board(fields={'Status': 7}), board(fields=[]), board(assignee=''), 'example-org/3'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as root, \
                    patch.object(frontlights, 'run', return_value=b'[]'), self.assertRaisesRegex(ValueError, 'project'):
                frontlights.inspect({'repository': 'example/project', 'project': bad}, root)

    def test_a_local_project_cannot_have_a_board(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'project'):
            frontlights.inspect({'repository': None, 'project': board()}, root)

    def test_plan_must_choose_every_open_board_field_per_issue(self):
        p = plan()
        with self.assertRaisesRegex(ValueError, 'Area'):
            frontlights.validate_plan(p, board())
        for i in p['issues']:
            i['project_fields'] = {'Area': 'Backend'}
        checked = frontlights.validate_plan(p, board())
        self.assertEqual(checked['issues'][0]['project_fields'], {'Area': 'Backend'})

    def test_plan_issue_type_comes_from_issue_or_board_default(self):
        p = plan()
        for i in p['issues']:
            i['project_fields'] = {'Area': 'Backend'}
        frontlights.validate_plan(p, board())
        # a board with no type at all (a personal account's repository has none) publishes without a type
        frontlights.validate_plan(p, board(issue_type=None))
        with self.assertRaisesRegex(ValueError, 'issue_type'):
            frontlights.validate_plan(p, board(issue_type=None, issue_type_by_label={'kind:bug': 'Bug'}))
        for i in p['issues']:
            i['issue_type'] = 'Bug'
        frontlights.validate_plan(p, board(issue_type=None))

    def test_plan_rejects_malformed_or_unknown_board_fields(self):
        for bad in ({'Area': ''}, {'Area': 3}, {'Area': 'Backend', 'Typo': 'x'}, ['Area']):
            p = plan()
            for i in p['issues']:
                i['project_fields'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                frontlights.validate_plan(p, board())

    def test_plan_without_board_ignores_nothing_and_still_validates(self):
        frontlights.validate_plan(plan())

    def test_cli_validate_plan_applies_the_board_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            plan_path, config_path = Path(d) / 'plan.json', Path(d) / 'config.json'
            plan_path.write_text(json.dumps(plan()), encoding='utf-8')
            config_path.write_text(json.dumps({'repository': 'example/project', 'project': board()}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(frontlights.__file__)), 'validate-plan',
                                     '--plan', str(plan_path), '--config', str(config_path)],
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Area', result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)


class LocalModeTests(unittest.TestCase):
    """A project without a remote is a supported state, not a missing prerequisite."""

    def test_inspect_without_repository_reports_github_unconfigured(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run') as run:
            result = frontlights.inspect({'repository': None, 'roads': None}, root)
        run.assert_not_called()
        self.assertIsNone(result['repository'])
        self.assertEqual(result['sources']['github']['status'], 'unconfigured')
        self.assertEqual(result['sources']['roads']['status'], 'unconfigured')

    def test_inspect_still_rejects_a_malformed_or_missing_repository(self):
        for config in ({'repository': 'not a repository'}, {'roads': None}, {'repsitory': None}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as root, \
                    self.assertRaisesRegex(ValueError, 'repository'):
                frontlights.inspect(config, root)

    def test_resume_rejects_a_source_change_alone(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            handoff = root / 'handoff.md'
            handoff.write_text('Next.')
            local = {'number': 1, 'body': 'Accept A', 'source': 'local'}
            evidence = {'head': 'a', 'branch': 'claude/i', 'diff_sha256': 'a', 'files_sha256': 'b', 'files': {}}
            with patch.object(frontlights, 'git_evidence', return_value=evidence):
                saved = frontlights.checkpoint(root, local, handoff, 'Next')
                with self.assertRaisesRegex(ValueError, 'different issue'):
                    frontlights.resume(root, saved, dict(local, source=None), handoff)

    def test_local_plan_validates_without_urls(self):
        p = plan()
        p['repository'] = None
        for i in p['issues']:
            i['url'] = None
        frontlights.validate_plan(p)
        p['issues'][0]['url'] = 'https://github.com/example/project/issues/1'
        with self.assertRaisesRegex(ValueError, 'local plan'):
            frontlights.validate_plan(p)

    def test_local_issue_snapshot_checkpoints_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            handoff = root / 'handoff.md'
            handoff.write_text('Next: run focused tests.')
            local = {'number': 1, 'title': 'Save', 'body': 'Accept A', 'state': 'open', 'source': 'local'}
            evidence = {'head': 'a' * 40, 'branch': 'claude/issue-1',
                        'diff_sha256': 'a', 'files_sha256': 'b', 'files': {}}
            with patch.object(frontlights, 'git_evidence', return_value=evidence):
                saved = frontlights.checkpoint(root, local, handoff, 'Run focused tests')
                self.assertEqual(frontlights.resume(root, saved, local, handoff)['state'], 'unchanged')
                with self.assertRaises(ValueError):
                    frontlights.checkpoint(root, dict(local, source='guess'), handoff, 'Run focused tests')
                remote = dict(local, source=None, html_url='https://github.com/example/project/issues/1')
                with self.assertRaisesRegex(ValueError, 'different issue'):
                    frontlights.resume(root, saved, remote, handoff)


class LocalAuthorizationTests(unittest.TestCase):
    def test_local_charter_needs_an_explicit_local_operation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'src').mkdir()
            c = dict(charter(root), repository=None)
            op = dict(repository=None, issue=1, kind='edit', branch='claude/issue-1',
                      worktree=root, path=str(Path(root) / 'src' / 'a.py'))
            frontlights.authorize(c, op)
            missing = {k: v for k, v in op.items() if k != 'repository'}
            for bad in (missing, dict(op, repository='example/project')):
                with self.subTest(op=bad), self.assertRaisesRegex(ValueError, 'repository'):
                    frontlights.authorize(c, bad)


class BranchPrefixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()

    def operation(self, branch):
        return dict(repository='example/project', issue=1, kind='edit', branch=branch,
                    worktree=str(self.root), path=str(self.root / 'src' / 'app.py'))

    def charter_for(self, branch, **extra):
        c = charter(self.root)
        c['worktrees'][0]['branch'] = branch
        c.update(extra)
        return c

    def test_default_prefix_is_claude(self):
        frontlights.authorize(self.charter_for('claude/issue-1'), self.operation('claude/issue-1'))
        with self.assertRaisesRegex(ValueError, 'branch'):
            frontlights.authorize(self.charter_for('codex/issue-1'), self.operation('codex/issue-1'))

    def test_prefix_cannot_open_a_protected_namespace(self):
        for protected, prefix, branch in ((['release/*'], 'release/', 'release/1.0'),
                                          (['Release'], 'release/', 'release/1.0'),
                                          (['MAIN'], 'main/', 'main/x')):
            c = self.charter_for(branch, branch_prefix=prefix, protected_branches=protected)
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, 'branch_prefix'):
                frontlights.authorize(c, self.operation(branch))

    def test_mid_pattern_protection_closes_the_prefix_and_bad_entries_fail_cleanly(self):
        for pattern in ('release/*/hotfix', '*/hotfix', 'rel*/hotfix'):
            c = self.charter_for('release/a/hotfix/x', branch_prefix='release/',
                                 protected_branches=[pattern])
            with self.subTest(pattern=pattern), \
                    self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
                frontlights.authorize(c, self.operation('release/a/hotfix/x'))
        allowed = self.charter_for('release/1.0', branch_prefix='release/',
                                   protected_branches=['release/*/hotfix'])
        frontlights.authorize(allowed, self.operation('release/1.0'))
        for entries in ([None], [5], 'main'):
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, 'protected_branches'):
                frontlights.authorize(self.charter_for('claude/issue-1', protected_branches=entries),
                                   self.operation('claude/issue-1'))

    def test_protected_branch_inside_prefix_is_denied_case_insensitively(self):
        c = self.charter_for('claude/x', protected_branches=['Claude/X'])
        with self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
            frontlights.authorize(c, self.operation('claude/x'))

    def test_one_protected_branch_does_not_block_its_siblings(self):
        c = self.charter_for('claude/issue-2', protected_branches=['claude/issue-1'])
        frontlights.authorize(c, self.operation('claude/issue-2'))
        for branch in ('claude/issue-1', 'claude/issue-1/sub'):
            trailing = self.charter_for(branch, protected_branches=['claude/issue-1/'])
            with self.subTest(branch=branch), \
                    self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
                frontlights.authorize(trailing, self.operation(branch))
        below = self.charter_for('claude/issue-1/sub', protected_branches=['claude/issue-1'])
        with self.assertRaisesRegex(ValueError, 'protected or unapproved branch'):
            frontlights.authorize(below, self.operation('claude/issue-1/sub'))

    def test_null_prefix_and_missing_charter_repository_are_denied(self):
        with self.assertRaisesRegex(ValueError, 'branch_prefix'):
            frontlights.authorize(self.charter_for('claude/issue-1', branch_prefix=None),
                               self.operation('claude/issue-1'))
        c = self.charter_for('claude/issue-1')
        del c['repository']
        with self.assertRaisesRegex(ValueError, 'repository'):
            frontlights.authorize(c, self.operation('claude/issue-1'))

    def test_charter_prefix_is_honoured_and_validated(self):
        c = self.charter_for('codex/issue-1', branch_prefix='codex/')
        frontlights.authorize(c, self.operation('codex/issue-1'))
        for prefix in ('', 'codex', '/', 'main/', 5):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, 'branch_prefix'):
                frontlights.authorize(self.charter_for('codex/issue-1', branch_prefix=prefix),
                                   self.operation('codex/issue-1'))


class VerificationDiscoveryTests(unittest.TestCase):
    def inspect(self, files):
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                path = Path(d, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
            return frontlights.inspect({'repository': None}, d)

    def test_python_unittest_and_pytest_candidates(self):
        self.assertEqual(self.inspect({'tests/test_a.py': ''})['verification_candidates'],
                         [['python', '-m', 'unittest', 'discover', '-s', 'tests', '-v']])
        self.assertEqual(self.inspect({'pyproject.toml': '[tool.pytest.ini_options]\n',
                                       'tests/test_a.py': ''})['verification_candidates'],
                         [['python', '-m', 'pytest']])
        self.assertEqual(self.inspect({'pytest.ini': '[pytest]\n'})['verification_candidates'],
                         [['python', '-m', 'pytest']])

    def test_npm_scripts_kept_and_nothing_invented(self):
        result = self.inspect({'package.json': '{"scripts": {"test": "vitest"}}'})
        self.assertEqual(result['verification_commands'], {'test': 'vitest'})
        self.assertEqual(result['verification_candidates'], [])
        self.assertEqual(self.inspect({})['verification_candidates'], [])


class PathRiskTests(unittest.TestCase):
    def test_long_or_virtualized_windows_root_is_flagged(self):
        short = frontlights.path_risk('C:/wt/app', 'C:/wt/app', 'win32')
        self.assertEqual(short['status'], 'ok')
        deep = 'C:/Users/u/AppData/Roaming/' + 'x' * 170
        self.assertEqual(frontlights.path_risk(deep, deep, 'win32')['status'], 'long_path')
        virtual = frontlights.path_risk('C:/Users/u/AppData/Roaming/App/s',
                                     'C:/Users/u/AppData/Local/Packages/App_x/LocalCache/Roaming/App/s', 'win32')
        self.assertEqual(virtual['status'], 'virtualized')
        self.assertIn('worktree', virtual['advice'])

    def test_other_platforms_are_not_flagged(self):
        deep = '/home/u/' + 'x' * 300
        self.assertEqual(frontlights.path_risk(deep, deep, 'linux')['status'], 'ok')

    def test_inspect_reports_path_risk(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIn(frontlights.inspect({'repository': None}, root)['path_risk']['status'],
                          {'ok', 'long_path', 'virtualized'})


class MonitoringBlockTests(unittest.TestCase):
    def test_phone_mode_requires_a_real_confirmation(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'src').mkdir()
            operation = dict(repository='example/project', issue=1, kind='edit',
                             branch='claude/issue-1', worktree=root,
                             path=str(Path(root) / 'src' / 'a.py'))
            good = charter(root)
            good['monitoring'] = {'mode': 'phone', 'confirmed_by': 'human', 'phone_connected': True}
            self.assertEqual(frontlights.authorize(good, operation)['scope_check'], 'pass')
            for value in ({}, {'phone_connected': False}, {'phone_connected': 'true'},
                          {'phone_connected': 1}):
                with self.subTest(value=value):
                    bad = charter(root)
                    bad['monitoring'] = {'mode': 'phone', 'confirmed_by': 'human', **value}
                    with self.assertRaisesRegex(ValueError, 'physical phone not confirmed'):
                        frontlights.authorize(bad, operation)


class UpdateCheckTests(unittest.TestCase):
    """Warn when the tracked branch moved on, by asking the remote and never pulling."""

    HEAD = 'a' * 40
    REMOTE = 'b' * 40

    def check(self, listed, ancestor=False, fail=None):
        answers = {'rev-parse --show-toplevel': '/skill', 'rev-parse HEAD': self.HEAD,
                   'rev-parse --abbrev-ref --symbolic-full-name @{upstream}': 'origin/main',
                   'ls-remote --heads origin main': listed}
        calls = []

        def git_text(root, *args, timeout=30):
            key = ' '.join(args)
            calls.append(key)
            if fail and key.startswith(fail):
                raise OSError('offline')
            return answers[key]

        with patch.object(frontlights, 'git_text', side_effect=git_text), \
             patch.object(frontlights, 'git_ok', return_value=ancestor) as ok:
            result = frontlights.update_check('/skill')
        return result, calls, ok

    def test_a_newer_published_commit_lists_the_pull_command(self):
        result, calls, ok = self.check(f'{self.REMOTE}\trefs/heads/main')
        self.assertEqual(result['status'], 'update_available')
        self.assertEqual(result['commands'], ['git -C "/skill" pull --ff-only'])
        self.assertEqual((result['installed'], result['published'], result['source']),
                         (self.HEAD[:12], self.REMOTE[:12], 'origin/main'))
        self.assertIn('ls-remote --heads origin main', calls)
        self.assertFalse(any(c.startswith(('pull', 'fetch', 'merge ', 'reset')) for c in calls))
        ok.assert_called_once_with('/skill', 'merge-base', '--is-ancestor', self.REMOTE, self.HEAD)

    def test_the_same_commit_or_a_checkout_ahead_of_it_is_current(self):
        result, _, ok = self.check(f'{self.HEAD}\trefs/heads/main')
        self.assertEqual(result['status'], 'current')
        self.assertNotIn('commands', result)
        ok.assert_not_called()
        result, _, _ = self.check(f'{self.REMOTE}\trefs/heads/main', ancestor=True)
        self.assertEqual(result['status'], 'current')

    def test_no_remote_branch_no_upstream_or_no_network_is_unavailable_not_current(self):
        remote = f'{self.REMOTE}\trefs/heads/main'
        for listed, fail in (('', None), (remote, 'ls-remote'), (remote, 'rev-parse --abbrev-ref'), (remote, 'rev-parse --show')):
            with self.subTest(listed=listed, fail=fail):
                result, _, _ = self.check(listed, fail=fail)
                self.assertEqual(result['status'], 'unavailable')
                self.assertNotIn('offline', json.dumps(result))
                self.assertNotIn('commands', result)

    def test_the_real_checkout_reports_its_own_head_as_installed(self):
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        with patch.object(frontlights, 'git_ok', return_value=True):
            result = frontlights.update_check(ROOT / 'skills' / 'frontlights')
        self.assertEqual(result['installed'], head[:12])
        self.assertIn(result['status'], ('current', 'update_available', 'unavailable'))

class WindowBoundaryTests(unittest.TestCase):
    """Redesenho, issue 9, S1: a janela nova abre na raiz do projeto e retoma pela issue. `checkpoint --issue <n>` acha
    o handoff na worktree principal; `resume --issue <n>` acha o checkpoint mais recente (na worktree da issue, pelo
    charter) e imprime o próximo passo, a slice, as pendências, o drift e a regra de que o GitHub vence o handoff."""

    SNAPSHOT = {'number': 7, 'title': 'Issue de teste', 'body': 'corpo', 'state': 'open', 'labels': [],
                'assignees': [], 'updated_at': '2000-01-01T00:00:00Z',
                'html_url': 'https://github.com/OWNER/REPOSITORY/issues/7'}

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gitfixture
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.main = gitfixture.init(base / 'main')
        (self.main / 'README.md').write_text('fixture\n', encoding='utf-8')
        gitfixture.git(self.main, 'add', '-A')
        gitfixture.git(self.main, 'commit', '-q', '-m', 'base')
        self.tree = base / 'wt-issue-7'
        gitfixture.git(self.main, 'worktree', 'add', '-q', '-b', 'sergio/issue-7', str(self.tree))
        records = self.main / '.frontlights'
        (records / 'issues' / '7').mkdir(parents=True)
        (records / 'config.json').write_text(json.dumps({'repository': 'OWNER/REPOSITORY'}), encoding='utf-8')
        charter = {'issue_ids': [7], 'worktrees': [{'issue': 7, 'path': str(self.tree), 'branch': 'sergio/issue-7'}]}
        (records / 'authorization.json').write_text(json.dumps(charter), encoding='utf-8')
        self.handoff = records / 'issues' / '7' / 'handoff.md'
        self.snapshot = dict(self.SNAPSHOT)

    def gh(self, argv):
        return self.snapshot

    def test_checkpoint_finds_the_handoff_of_the_issue_in_the_main_worktree(self):
        with self.assertRaisesRegex(ValueError, 'sem handoff'):
            frontlights.checkpoint_cli('7', str(self.tree), None, 'etapa 6, S2', gh=self.gh, main=str(self.main))
        self.handoff.write_text('# Passagem\n', encoding='utf-8')
        saved = frontlights.checkpoint_cli('7', str(self.tree), None, 'etapa 6, S2', gh=self.gh, main=str(self.main))
        self.assertTrue(Path(saved['handoff']).samefile(self.handoff))
        self.assertTrue(Path(saved['saved']).samefile(self.tree / '.frontlights' / 'issues' / '7' / 'checkpoint.json'))

    def test_resume_from_the_project_root_finds_the_checkpoint_of_the_issue_worktree(self):
        self.handoff.write_text('# Passagem\n', encoding='utf-8')
        frontlights.checkpoint_cli('7', str(self.tree), None, 'etapa 6, S2: slice merge', ['teste_assistido'], 'S2',
                                   gh=self.gh, main=str(self.main))
        # the slice checkpoint is found by --slice; the issue one (none here) by the issue alone
        resumed = frontlights.resume_cli('7', str(self.main), None, None, gh=self.gh, main=str(self.main),
                                         slice_id='S2')
        self.assertEqual((resumed['state'], resumed['next_step'], resumed['slice'], resumed['pending']),
                         ('unchanged', 'etapa 6, S2: slice merge', 'S2', ['teste_assistido']))
        self.assertTrue(Path(resumed['worktree']).samefile(self.tree))
        self.assertIn('O GitHub vence o handoff', resumed['rule'])
        self.assertNotIn('window', resumed)
        self.snapshot = dict(self.SNAPSHOT, body='corpo novo')
        drifted = frontlights.resume_cli('7', str(self.main), None, None, gh=self.gh, main=str(self.main),
                                         slice_id='S2')
        self.assertEqual((drifted['state'], drifted['issue_drift']), ('reconcile', ['body']))

    def test_the_latest_checkpoint_wins_and_the_antes_window_is_attached(self):
        self.handoff.write_text('# Passagem\n', encoding='utf-8')
        frontlights.checkpoint_cli('7', str(self.main), None, 'etapa 5, publicar', gh=self.gh, main=str(self.main))
        frontlights.checkpoint_cli('7', str(self.tree), None, 'etapa 6, S1', gh=self.gh, main=str(self.main))
        window = self.main / '.frontlights' / 'issues' / '7' / 'browser' / 'window.json'
        window.parent.mkdir()
        window.write_text('{"pid": 1}', encoding='utf-8')
        resumed = frontlights.resume_cli('7', str(self.main), None, None, gh=self.gh, main=str(self.main))
        self.assertEqual(resumed['next_step'], 'etapa 6, S1')
        self.assertEqual(resumed['window']['command'], 'serve.py window attach --issue 7')

    def test_resume_by_the_issue_alone_finds_a_slice_checkpoint(self):
        # Teste com um clone real (23/10/2026): a janela nova só sabe "retome a issue #n", e o checkpoint da fronteira
        # de slice é checkpoint-S2.json; sem --slice o resume procurava só checkpoint.json e parava.
        self.handoff.write_text('# Passagem\n', encoding='utf-8')
        frontlights.checkpoint_cli('7', str(self.tree), None, 'etapa 6, S3', ['teste_assistido'], 'S2',
                                   gh=self.gh, main=str(self.main))
        resumed = frontlights.resume_cli('7', str(self.main), None, None, gh=self.gh, main=str(self.main))
        self.assertEqual((resumed['next_step'], resumed['slice']), ('etapa 6, S3', 'S2'))

    def test_without_any_checkpoint_resume_names_where_it_looked(self):
        with self.assertRaisesRegex(ValueError, 'sem checkpoint da issue #7'):
            frontlights.resume_cli('7', str(self.main), None, None, gh=self.gh, main=str(self.main))

    def test_the_skill_says_the_boundaries_and_the_resume_sentence(self):
        rule = skilltext.flat(skilltext.rule('Windows'))
        for phrase in ('plan published', 'a slice merged into the issue branch, at least every second slice',
                       'the issue in the local main with its bundle', 'the release PR open',
                       '`frontlights.py checkpoint --issue <n> --next-step "<stage, step>"`',
                       '`cwd` the project root, no worktree', 'never asking or stopping for it',
                       'never the earlier conversation', 'Every 50 turns report `frontlights.py context --used`',
                       '"Contexto e conclusão"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        stage1 = skilltext.flat(skilltext.stage(1))
        self.assertIn('`frontlights.py resume --issue <n>` prints the next step, slice, pending and drift; GitHub '
                      'wins over the handoff', stage1)
        protocol = ' '.join((ROOT / 'skills' / 'frontlights' / 'docs' / 'protocol.md').read_text(encoding='utf-8')
                            .split('## Ponto de retomada')[1].split('\n## ')[0].split())
        self.assertIn('O GitHub vence o handoff', protocol)


class HandoffTemplateTests(unittest.TestCase):
    """Redesenho, issue 9, S2: o handoff em português, ~250 palavras, só ponteiros; os limiares numa casa só."""

    def test_the_handoff_is_short_portuguese_and_points(self):
        text = (ROOT / 'skills' / 'frontlights' / 'templates' / 'handoff.md').read_text(encoding='utf-8')
        self.assertLessEqual(len(text.split()), 260)
        flat = ' '.join(text.split())
        for phrase in ('# Passagem da issue #<n>', 'Só ponteiros', 'O GitHub vence esta passagem', '- Issue:',
                       '- Charter: `.frontlights/authorization.json`', '- Checkpoints:',
                       '`frontlights.py resume --issue <n>`', '`.frontlights/issues/<n>/browser/window.json`',
                       '`serve.py window attach`', '- Plano resumido:', '- Slices fechadas:', '- Release:',
                       'Achados sem correção e destino de cada um', '- Pergunta pendente e resposta literal:',
                       '- Próximo passo:'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)
        for english in ('Approved acceptance criteria', 'Next concrete step', 'Resume in a fresh context'):
            with self.subTest(english=english):
                self.assertNotIn(english, flat)

    def test_the_thresholds_live_in_the_protocol(self):
        protocol = ' '.join((ROOT / 'skills' / 'frontlights' / 'docs' / 'protocol.md').read_text(encoding='utf-8')
                            .split('## Contexto e conclusão')[1].split('\n## ')[0].split())
        for phrase in ('casa única dos limiares', '100 mil, 150 mil e 200 mil', 'a cada 50 turnos', '`cut`',
                       '`--pending teste_assistido`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, protocol)
        development = ' '.join((ROOT / 'skills' / 'frontlights' / 'references' / 'development.md')
                               .read_text(encoding='utf-8').split())
        self.assertIn('the thresholds of `docs/protocol.md`, "Contexto e conclusão", their only home', development)


class ContextCadenceAndHostBaseTests(unittest.TestCase):
    """Redesenho, issue 9, S3: `context --used` a cada 50 turnos (`--turn` diz o próximo), `--pending
    teste_assistido` mantido e o aviso da base do host acima de 80 mil no `update-check` e no `open`."""

    def run_script(self, *args):
        done = subprocess.run([sys.executable, str(SUMMARY_SCRIPT), *args], capture_output=True, text=True,
                              encoding='utf-8', timeout=120)
        return json.loads(done.stdout)

    def test_the_next_report_is_the_next_multiple_of_fifty(self):
        self.assertEqual([frontlights.next_report(t) for t in (0, 49, 50, 120)], [50, 50, 100, 150])
        result = self.run_script('context', '--used', '160000', '--reserve', '5000', '--pending', 'teste_assistido',
                                 '--turn', '100')
        self.assertEqual(result, {'action': 'stop', 'pending': ['teste_assistido'],
                                  'ask_before_continuing': ['teste_assistido'], 'next_report_turn': 150})
        self.assertNotIn('next_report_turn', self.run_script('context', '--used', '1000', '--reserve', '10'))

    def test_the_host_base_names_the_connectors_that_are_not_the_projects(self):
        self.assertIsNone(frontlights.host_base(None, ['conector-a']))
        low = frontlights.host_base(80000, ['conector-a'])
        self.assertEqual((low['over'], low['notProject']), (False, []))
        self.assertNotIn('message', low)
        high = frontlights.host_base(120000, ['conector-a', 'Conector-Projeto', 'conector-a'], ['conector-projeto'])
        self.assertEqual((high['over'], high['notProject']), (True, ['conector-a']))
        self.assertIn('120 mil tokens, acima de 80 mil', high['message'])
        self.assertIn('conector-a', high['message'])

    def test_update_check_and_open_carry_the_warning(self):
        result = self.run_script('update-check', '--base', '95000', '--connector', 'conector-a')
        self.assertEqual(result['hostBase']['notProject'], ['conector-a'])
        self.assertNotIn('hostBase', self.run_script('update-check'))
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps({'repository': None, 'connectors': ['conector-projeto']}), encoding='utf-8')
            self.assertEqual(frontlights.project_connectors(config), ['conector-projeto'])
            done = subprocess.run([sys.executable, str(SUMMARY_SCRIPT), 'open', '--config', str(config), '--root',
                                   folder, '--no-fetch', '--base', '90000', '--connector', 'conector-projeto',
                                   '--connector', 'conector-b'], capture_output=True, text=True, encoding='utf-8',
                                  timeout=120)
        self.assertEqual(json.loads(done.stdout)['hostBase']['notProject'], ['conector-b'], done.stderr)


# Economia nos utilitários: `inspect --summary` (por issue só número, título, estado e caixas; a saída
# padrão não muda) e um `authorize` que lê a operação da entrada padrão e não exige que as outras
# worktrees do charter já existam.
SUMMARY_SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'

SUMMARY_BODY = ('Contexto longo que não deve aparecer no resumo.\n\n'
        '## Critérios de aceitação\n\n'
        '- [x] S1. Primeira fatia\n'
        '  - Entrega: algo\n'
        '- [ ] S2. Segunda fatia\n'
        '- [ ] S3. Terceira fatia\n')

SUMMARY_PAGES = [[{'number': 1, 'title': 'Fatia com critérios', 'state': 'open', 'body': SUMMARY_BODY,
           'labels': [{'name': 'enhancement'}], 'user': {'login': 'pessoa-ficticia'}},
          {'number': 2, 'title': 'Pull request', 'state': 'open', 'body': 'x', 'pull_request': {}}],
         [{'number': 3, 'title': 'Sem seção de critérios', 'state': 'closed', 'body': None}]]


def summary_inspect(config, summary):
    with tempfile.TemporaryDirectory() as root, \
            patch.object(frontlights, 'run', return_value=json.dumps(SUMMARY_PAGES).encode()):
        return frontlights.inspect(config, root, summary=summary)


class InspectSummaryTests(unittest.TestCase):
    def test_summary_keeps_only_number_title_state_and_boxes_of_each_issue(self):
        github = summary_inspect({'repository': 'example/project'}, True)['sources']['github']
        self.assertEqual(github, {
            'status': 'available', 'source': 'https://github.com/example/project/issues', 'count': 2, 'open': 1,
            'issues': [{'number': 1, 'title': 'Fatia com critérios', 'state': 'open',
                        'boxes': {'checked': 1, 'total': 3}},
                       {'number': 3, 'title': 'Sem seção de critérios', 'state': 'closed', 'boxes': None}]})

    def test_summary_is_marked_and_keeps_the_other_keys_of_the_output(self):
        config = {'repository': 'example/project'}
        full, short = summary_inspect(config, False), summary_inspect(config, True)
        self.assertTrue(short.pop('summary'))
        self.assertNotIn('summary', full)
        self.assertEqual(sorted(short), sorted(full))
        self.assertNotIn('Contexto longo', json.dumps(short, ensure_ascii=False))
        self.assertIn('Contexto longo', json.dumps(full, ensure_ascii=False))

    def test_default_output_still_carries_the_whole_issue(self):
        issues = summary_inspect({'repository': 'example/project'}, False)['sources']['github']['issues']
        self.assertEqual(issues, [i for page in SUMMARY_PAGES for i in page if 'pull_request' not in i])

    def test_a_configured_board_changes_nothing_without_the_flag(self):
        """Com `project` configurado, a saída padrão segue inteira e o quadro sai igual nos dois modos."""
        project = {'owner': 'example-org', 'number': 3, 'assignee': '@me', 'issue_type': 'Task',
                   'fields': {'Status': 'Open', 'Area': None}}

        def gh(argv):
            if argv[:2] == ['gh', 'project']:
                return json.dumps({'title': 'Quadro fictício',
                                   'url': 'https://github.com/orgs/example-org/projects/3'}).encode()
            return json.dumps(SUMMARY_PAGES).encode()
        results = {}
        for summary in (False, True):
            with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=gh):
                results[summary] = frontlights.inspect({'repository': 'example/project', 'project': project}, root,
                                                       summary=summary)
        self.assertNotIn('summary', results[False])
        self.assertEqual(results[False]['sources']['github']['issues'],
                         [i for page in SUMMARY_PAGES for i in page if 'pull_request' not in i])
        self.assertIs(results[True]['summary'], True)
        self.assertEqual(results[True]['sources']['project'], results[False]['sources']['project'])
        self.assertEqual(results[True]['sources']['project']['title'], 'Quadro fictício')

    def test_an_unavailable_or_unconfigured_source_keeps_its_status_and_reason(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=ValueError('x')):
            sources = frontlights.inspect({'repository': 'example/project', 'roads': None}, root,
                                          summary=True)['sources']
        self.assertEqual(sources['github']['status'], 'unavailable')
        self.assertIn('reason', sources['github'])
        self.assertNotIn('count', sources['github'])
        self.assertEqual(sources['roads'], {'status': 'unconfigured'})
        self.assertEqual(sources['project'], {'status': 'unconfigured'})

    def test_roads_data_is_counted_not_dumped(self):
        roads = {'observations_url': 'https://roads.example/api/obs', 'token_env': 'TOKEN_FICTICIO'}
        for data, count in (([{'id': 1}, {'id': 2}, {'id': 3}], 3), ({'items': [1], 'meta': {}}, None)):
            result = {'repository': None, 'sources': {'github': {'status': 'unconfigured'},
                                                      'roads': {'status': 'available', 'source': roads['observations_url'],
                                                                'data': data}}}
            with self.subTest(data=data):
                short = frontlights.summarize(result)['sources']['roads']
                self.assertNotIn('data', short)
                self.assertEqual(short['count'], count)
                self.assertEqual(short['source'], roads['observations_url'])
                if isinstance(data, dict):
                    self.assertEqual(short['keys'], ['items', 'meta'])

    def test_cli_summary_flag(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'config.json'
            config.write_text(json.dumps({'repository': None}), encoding='utf-8')
            plain = subprocess.run([sys.executable, str(SUMMARY_SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                   capture_output=True, text=True, encoding='utf-8')
            short = subprocess.run([sys.executable, str(SUMMARY_SCRIPT), 'inspect', '--config', str(config), '--root', root,
                                    '--summary'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertNotIn('summary', json.loads(plain.stdout))
        output = json.loads(short.stdout)
        self.assertIs(output['summary'], True)
        self.assertEqual(output['sources']['github'], {'status': 'unconfigured'})


def slice_charter(root, *extra):
    return dict(repository='example/project', issue_ids=[1], concurrency=1,
                approved_by='human', approval_reference='session:turn-12',
                expires_at='2099-01-01T00:00:00+00:00',
                monitoring={'mode': 'local', 'confirmed_by': 'human'},
                operations=['edit', 'test'],
                worktrees=[{'issue': 1, 'path': str(root), 'branch': 'claude/issue-1', 'ownership': ['src']},
                           *extra],
                verification_commands=[['python', '-m', 'unittest']],
                stop_conditions=['New product decision'])


class AuthorizeWorktreesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'issue-1'
        (self.root / 'src').mkdir(parents=True)
        self.missing = Path(temp.name) / 'issue-1-s2'   # a slice declared before it is cut
        self.slice = {'issue': 1, 'path': str(self.missing), 'branch': 'claude/issue-1-s2', 'slice': 'S2',
                      'base': 'claude/issue-1', 'ownership': ['src']}
        self.op = dict(repository='example/project', issue=1, kind='edit', branch='claude/issue-1',
                       worktree=str(self.root), path=str(self.root / 'src' / 'app.py'))

    def test_a_worktree_of_the_charter_not_cut_yet_does_not_block_the_others(self):
        result = frontlights.authorize(slice_charter(self.root, self.slice), self.op)
        self.assertEqual(result['scope_check'], 'pass')

    def test_an_operation_on_a_worktree_that_does_not_exist_is_refused_by_name(self):
        op = dict(self.op, worktree=str(self.missing), branch='claude/issue-1-s2', slice='S2',
                  path=str(self.missing / 'src' / 'app.py'))
        with self.assertRaisesRegex(ValueError, 'worktree of the operation does not exist'):
            frontlights.authorize(slice_charter(self.root, self.slice), op)

    def test_once_it_is_cut_the_declared_worktree_is_accepted(self):
        (self.missing / 'src').mkdir(parents=True)
        op = dict(self.op, worktree=str(self.missing), branch='claude/issue-1-s2', slice='S2',
                  path=str(self.missing / 'src' / 'app.py'))
        self.assertEqual(frontlights.authorize(slice_charter(self.root, self.slice), op)['scope_check'], 'pass')

    def test_entries_of_the_issue_are_still_validated(self):
        for bad in ({'issue': 1, 'branch': 'claude/issue-1-s3'}, {'issue': 1, 'path': ''}, 'issue-1'):
            with self.subTest(entry=bad), self.assertRaisesRegex(ValueError, 'worktree entry'):
                frontlights.authorize(slice_charter(self.root, bad), self.op)


class AuthorizeStdinTests(unittest.TestCase):
    def run_cli(self, operation, charter_data, stdin=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'charter.json'
            path.write_text(json.dumps(charter_data), encoding='utf-8')
            return subprocess.run([sys.executable, str(SUMMARY_SCRIPT), 'authorize', '--charter', str(path),
                                   '--operation', operation], input=stdin, capture_output=True, text=True,
                                  encoding='utf-8')

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'src').mkdir()
        self.op = dict(repository='example/project', issue=1, kind='edit', branch='claude/issue-1',
                       worktree=str(self.root), path=str(self.root / 'src' / 'app.py'))

    def test_operation_from_standard_input(self):
        run = self.run_cli('-', slice_charter(self.root), json.dumps(self.op))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['scope_check'], 'pass')

    def test_operation_from_a_file_still_works(self):
        operation = self.root / 'op.json'
        operation.write_text(json.dumps(self.op), encoding='utf-8')
        run = self.run_cli(str(operation), slice_charter(self.root))
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_invalid_json_on_standard_input_is_a_clean_error(self):
        run = self.run_cli('-', slice_charter(self.root), '{nao e json')
        self.assertEqual(run.returncode, 1)
        self.assertNotIn('Traceback', run.stderr)
        self.assertIn('error', json.loads(run.stderr))


# Trabalho sem issue (caminho Direto, ou Curto sem publicar issue): a entrada de `worktrees` leva `direct`, um slug
# listado em `direct_ids`, e a operação nomeia o mesmo `direct` no lugar de `issue`; as outras regras são as da issue.
def direct_charter(root, *extra, **overrides):
    data = dict(repository='example/project', issue_ids=[1], direct_ids=['melhoria-x'], concurrency=1,
                approved_by='human', approval_reference='session:turn-12',
                expires_at='2099-01-01T00:00:00+00:00',
                monitoring={'mode': 'local', 'confirmed_by': 'human'},
                operations=['edit', 'test', 'merge_into_local_main'], base={'branch': 'main'},
                worktrees=[{'direct': 'melhoria-x', 'path': str(root / 'direct'), 'branch': 'claude/melhoria-x',
                            'ownership': ['src']},
                           {'issue': 1, 'path': str(root / 'issue'), 'branch': 'claude/issue-1', 'ownership': ['src']},
                           *extra],
                verification_commands=[['python', '-m', 'unittest']],
                stop_conditions=['New product decision'])
    data.update(overrides)
    return data


class AuthorizeDirectTests(unittest.TestCase):
    GATES = {'browser_gate': 'not_needed'}

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ('direct', 'issue'):
            (self.root / name / 'src').mkdir(parents=True)
        self.op = dict(repository='example/project', direct='melhoria-x', kind='edit', branch='claude/melhoria-x',
                       worktree=str(self.root / 'direct'), path=str(self.root / 'direct' / 'src' / 'app.py'))
        self.merge = dict(self.op, kind='merge_into_local_main', target='main', gates=self.GATES)
        del self.merge['path']

    def test_an_edit_and_the_merge_into_the_local_main_pass_for_work_without_an_issue(self):
        self.assertEqual(frontlights.authorize(direct_charter(self.root), self.op)['scope_check'], 'pass')
        self.assertEqual(frontlights.authorize(direct_charter(self.root), self.merge)['scope_check'], 'pass')

    def test_the_gates_and_the_target_still_hold(self):
        with self.assertRaisesRegex(ValueError, 'gate browser_gate is not green'):
            frontlights.authorize(direct_charter(self.root), dict(self.merge, gates=dict(self.GATES, browser_gate='pending')))
        with self.assertRaisesRegex(ValueError, 'remote main'):
            frontlights.authorize(direct_charter(self.root), dict(self.merge, target='origin/main'))

    def test_a_direct_outside_the_charter_is_unapproved(self):
        with self.assertRaisesRegex(ValueError, 'unapproved direct'):
            frontlights.authorize(direct_charter(self.root), dict(self.op, direct='outra-coisa'))
        with self.assertRaisesRegex(ValueError, 'unapproved direct'):
            frontlights.authorize(direct_charter(self.root, direct_ids=[]), self.op)

    def test_the_operation_names_an_issue_or_a_direct_never_both_nor_neither(self):
        with self.assertRaisesRegex(ValueError, 'an issue or a direct, never both'):
            frontlights.authorize(direct_charter(self.root), dict(self.op, issue=1))
        neither = dict(self.op)
        del neither['direct']
        with self.assertRaisesRegex(ValueError, 'unapproved issue'):
            frontlights.authorize(direct_charter(self.root), neither)

    def test_a_malformed_slug_is_refused(self):
        for slug in ('Melhoria-X', '', '-x', 'a' * 65, 'com espaco', 1):
            with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, 'direct'):
                frontlights.authorize(direct_charter(self.root, direct_ids=[slug]), dict(self.op, direct=slug))

    def test_the_direct_and_the_issue_never_share_an_entry(self):
        both = {'issue': 1, 'direct': 'melhoria-x', 'path': str(self.root / 'direct'), 'branch': 'claude/melhoria-x',
                'ownership': ['src']}
        with self.assertRaisesRegex(ValueError, 'worktree entry'):
            frontlights.authorize(direct_charter(self.root, both), self.op)
        # the worktree of the issue is never the worktree of the direct work, and the reverse
        with self.assertRaisesRegex(ValueError, 'unapproved or ambiguous worktree'):
            frontlights.authorize(direct_charter(self.root), dict(self.op, worktree=str(self.root / 'issue'),
                                                                  path=str(self.root / 'issue' / 'src' / 'a.py')))
        issue_op = dict(repository='example/project', issue=1, kind='edit', branch='claude/issue-1',
                        worktree=str(self.root / 'direct'), path=str(self.root / 'direct' / 'src' / 'a.py'))
        with self.assertRaisesRegex(ValueError, 'unapproved or ambiguous worktree'):
            frontlights.authorize(direct_charter(self.root), issue_op)

    def test_an_issue_operation_is_unchanged_by_direct_entries(self):
        issue_op = dict(repository='example/project', issue=1, kind='edit', branch='claude/issue-1',
                        worktree=str(self.root / 'issue'), path=str(self.root / 'issue' / 'src' / 'a.py'))
        self.assertEqual(frontlights.authorize(direct_charter(self.root), issue_op)['scope_check'], 'pass')

    def test_a_slice_of_direct_work_follows_the_slice_rules(self):
        (self.root / 's1' / 'src').mkdir(parents=True)
        entry = {'direct': 'melhoria-x', 'path': str(self.root / 's1'), 'branch': 'claude/melhoria-x-s1', 'slice': 'S1',
                 'ownership': ['src']}
        op = dict(self.op, worktree=str(self.root / 's1'), branch='claude/melhoria-x-s1',
                  path=str(self.root / 's1' / 'src' / 'a.py'))
        self.assertEqual(frontlights.authorize(direct_charter(self.root, entry), dict(op, slice='S1'))['scope_check'],
                         'pass')
        with self.assertRaisesRegex(ValueError, 'slice'):
            frontlights.authorize(direct_charter(self.root, entry), op)
        with self.assertRaisesRegex(ValueError, 'never a slice branch'):
            frontlights.authorize(direct_charter(self.root, entry),
                                  dict(self.merge, worktree=str(self.root / 's1'), branch='claude/melhoria-x-s1',
                                       slice='S1'))

    def test_the_example_operation_of_direct_work_passes_against_the_example_charter(self):
        examples = Path(frontlights.__file__).resolve().parents[1] / 'examples'
        charter = json.loads((examples / 'authorization.json').read_text(encoding='utf-8'))
        op = json.loads((examples / 'operation-merge-local-main-direct.json').read_text(encoding='utf-8'))
        entry = next(w for w in charter['worktrees'] if 'direct' in w)
        self.assertEqual((op['direct'], op['branch']), (entry['direct'], entry['branch']))
        self.assertIn(op['direct'], charter['direct_ids'])
        charter = dict(charter, approved_by='usuário', approval_reference='autorização permanente',
                       expires_at='2099-01-01T00:00:00+00:00',
                       monitoring=dict(charter['monitoring'], confirmed_by='usuário'),
                       worktrees=[dict(entry, path=str(self.root / 'direct'))])
        self.assertEqual(frontlights.authorize(charter, dict(op, worktree=str(self.root / 'direct')))['scope_check'],
                         'pass')

    def test_the_slug_rule_is_the_same_in_authorize_and_in_the_release_plan(self):
        import homolog
        self.assertEqual(frontlights.DIRECT_RULE.pattern, homolog.DIRECT.pattern)

    def test_the_merge_of_direct_work_through_the_command_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'charter.json'
            path.write_text(json.dumps(direct_charter(self.root)), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SUMMARY_SCRIPT), 'authorize', '--charter', str(path),
                                  '--operation', '-'], input=json.dumps(self.merge), capture_output=True, text=True,
                                 encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['scope_check'], 'pass')


if __name__ == '__main__':
    unittest.main()
