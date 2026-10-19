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
        for name in ('grilling', 'issue', 'issues', 'development', 'issue-gaps', 'learning'):
            self.assertFalse((ROOT / 'skills' / 'frontlights' / 'references' / 'roadmap-sync.md').exists())
            self.assertIn(f'references/{name}.md', text)
            self.assertTrue((ROOT / 'skills' / 'frontlights' / 'references' / f'{name}.md').is_file())

    def test_every_session_asks_about_the_issue_gaps_before_the_request(self):
        text = (ROOT / 'skills' / 'frontlights' / 'SKILL.md').read_text(encoding='utf-8')
        stage1 = text.split('## 1.')[1].split('## 2.')[0]
        self.assertIn('every session', stage1)
        self.assertIn('Completar no GitHub as issues que o RoadS mostra?', stage1)
        self.assertLess(stage1.index('roads.py" status'), stage1.index('Then choose the lightest path'))
        self.assertIn('say `message` in one line', ' '.join(stage1.split()))
        self.assertNotIn('Atualizar a sprint e o roadmap', text)
        self.assertNotIn('roadmap_sync', text)

    def test_session_start_never_looks_for_remote_control(self):
        skill = ROOT / 'skills' / 'frontlights'
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        stage0 = text.split('## 0.')[1].split('## 1.')[0]
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
        stage3 = (skill / 'SKILL.md').read_text(encoding='utf-8').split('## 3.')[1].split('## 4.')[0]
        self.assertIn('still runs the solution round', stage3)
        for template, heading in (('discovery.md', 'onventions'), ('issue.md', 'Decisões de implementação')):
            with self.subTest(template=template):
                self.assertIn(heading, (ROOT / 'skills' / 'frontlights' / 'templates' / template).read_text(encoding='utf-8'))

    def test_learning_reference_defines_when_to_explain_how_to_check_and_what_to_record(self):
        text = (ROOT / 'skills' / 'frontlights' / 'references' / 'learning.md').read_text(encoding='utf-8')
        headings = ('## What every explanation must have', '## When to explain',
                    '## Understanding check', '## Record')
        for heading in headings:
            self.assertIn(heading, text)
        positions = [text.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        flat = ' '.join(text.split())
        self.assertIn('Read this file before writing the first explanation', flat.split(headings[0])[0])
        bodies = {}
        for heading, following in zip(headings, headings[1:] + (None,)):
            body = flat.split(heading)[1]
            bodies[heading] = body.split(following)[0] if following else body
        expected = {
            headings[0]: ('mark the comments as yours', "never inside an option's `preview`",
                          'Never include secrets', 'short enough to read on a phone'),
            headings[1]: ('"Explicar antes de decidir"', 'at most three real options',
                          'a question asked again never carries the explain option',
                          'The other answers given in that call stand',
                          'never holds more than four questions',
                          'when the call carries the check and four decisions are pending',
                          'that next call carries a check only if an explanation was written '
                          'since the last check',
                          'is never permission to decide for them'),
            headings[2]: ('one "Ficou claro?" covering every concept explained in the round',
                          'up to three decisions', '"Entendi"', '"Explicar de outro jeito"',
                          'no limit on re-explanations', 'are not final',
                          'This is the learning-mode exception to not re-asking settled decisions',
                          'After two re-explanations of the same round have been given',
                          'to every later check of that round',
                          '"Seguir a recomendação"',
                          'its description says the decision is marked "a revisar"',
                          'tell the user which option was taken for each decision',
                          'tomada pela recomendação, a revisar'),
            headings[3]: ('Concepts explained', 'each change of it', 'Never record secrets'),
        }
        for heading, phrases in expected.items():
            for phrase in phrases:
                with self.subTest(section=heading, phrase=phrase):
                    self.assertIn(phrase, bodies[heading])

    def test_follow_recommendation_label_fits_the_five_word_limit_everywhere(self):
        old = 'Seguir com a recomendação e marcar a revisar'
        learning = (ROOT / 'skills' / 'frontlights' / 'references' / 'learning.md').read_text(encoding='utf-8')
        runbook = (ROOT / 'evals' / 'runbook.md').read_text(encoding='utf-8')
        for name, text in (('learning.md', learning), ('runbook.md', runbook)):
            flat = ' '.join(text.split())
            with self.subTest(file=name):
                self.assertNotIn(old, flat)
                self.assertIn('"Seguir a recomendação"', flat)
        label = re.search(r'add "([^"]+)" to every later check', ' '.join(learning.split())).group(1)
        self.assertLessEqual(len(label.split()), 5)

    def test_readme_describes_learning_mode(self):
        flat = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
        for phrase in ('modo aprendizado', 'desligado por padrão', '"Explicar antes de decidir"',
                       '"Ficou claro?"', '"Seguir a recomendação"', '"a revisar"',
                       'suposição, não como decisão aprovada'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_grilling_offers_learning_mode_with_depth_and_keeps_three_approaches(self):
        skill = ROOT / 'skills' / 'frontlights'
        flat = ' '.join((skill / 'references' / 'grilling.md').read_text(encoding='utf-8').split())
        depth = flat.split('## 0. Depth')[1].split('## The artifact')[0]
        for phrase in ('"Qual profundidade de grilling?"', '"Ativar o modo aprendizado?"',
                       'in the same `AskUserQuestion` call', '"Desligado"',
                       'Read `references/learning.md` before writing the first explanation',
                       'or the conversation has been compacted',
                       'read the mode back from the discovery log',
                       "update the log's learning-mode line whenever the mode changes",
                       "add the change, with the question where it happened, to the log's "
                       'learning-mode changes line',
                       'turn the mode on or off at any time', 'Record both choices.'):
            with self.subTest(section='depth', phrase=phrase):
                self.assertIn(phrase, depth)
        self.assertLess(depth.index('"Ativar o modo aprendizado?"'), depth.index('Read `references/learning.md`'))
        solution = flat.split('## 3. Solution round')[1].split('## 4. Decision tree')[0]
        for phrase in ('at least three genuinely different approaches',
                       'With learning mode off, the fourth option is "Explicar antes de decidir", '
                       'so the round has exactly three approaches'):
            with self.subTest(section='solution', phrase=phrase):
                self.assertIn(phrase, solution)
        tree = flat.split('## 4. Decision tree')[1].split('## 5. Pre-mortem')[0]
        for phrase in ('batched at most four per call', 'the learning-mode check counts as one',
                       'every branch except scope, priority and other product questions',
                       'the last option is "Explicar antes de decidir" (at most three real options)',
                       'its `preview` only lists what will be explained',
                       'one "Ficou claro?" check in the same call as up to three decisions'):
            with self.subTest(section='tree', phrase=phrase):
                self.assertIn(phrase, tree)
        closing = flat.split('## 6. Closing')[1].split('## Recording')[0]
        for phrase in ('asked for another explanation in the same call', 'marked "a revisar"'):
            with self.subTest(section='closing', phrase=phrase):
                self.assertIn(phrase, closing)
        recording = flat.split('## Recording')[1]
        self.assertIn('concepts explained', recording)
        self.assertIn('as assumptions to be shown, never as approved decisions', recording)
        skill_text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('`references/learning.md` is read only when the user turns learning mode on '
                      'in the grilling or asks for an explanation there.', ' '.join(skill_text.split()))
        stage3 = ' '.join(skill_text.split('## 3.')[1].split('## 4.')[0].split())
        self.assertIn('together with the learning mode (off by default', stage3)

    def test_discovery_template_records_learning_mode_and_concepts_explained(self):
        text = (ROOT / 'skills' / 'frontlights' / 'templates' / 'discovery.md').read_text(encoding='utf-8')
        self.assertIn('- Learning mode (ligado / desligado):', text)
        self.assertLess(text.index('- Grilling depth'), text.index('- Learning mode'))
        self.assertIn('- Learning mode changes (nenhuma, ou cada troca e a pergunta em que ocorreu):', text)
        self.assertLess(text.index('- Learning mode ('), text.index('- Learning mode changes'))
        self.assertLess(text.index('- Learning mode changes'), text.index('## Project conventions'))
        self.assertIn('## Concepts explained', text)
        self.assertIn('| Concept | Summary | Where it came up |', text)
        self.assertLess(text.index('## Decisions'), text.index('## Concepts explained'))
        self.assertLess(text.index('## Concepts explained'), text.index('## Pre-mortem'))

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
        self.assertIn('Never mint `GT-NNNN`', text)
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
        with self.assertRaisesRegex(ValueError, 'issue_type'):
            frontlights.validate_plan(p, board(issue_type=None))
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
    GATES = {'suite_gate': 'current', 'review_gate': 'current', 'browser_gate': 'not_needed'}

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
        with self.assertRaisesRegex(ValueError, 'gate review_gate is not green'):
            frontlights.authorize(direct_charter(self.root), dict(self.merge, gates=dict(self.GATES, review_gate='stale')))
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
