"""Etapa 6 por comando, S4 (redesenho, issue 4): `homolog release plan|body-check|go|status|landed` e o
`closeout.py merge-status` que lê `reviewDecision`, `mergeStateStatus` e `mergeable`. Gitfixture com origin bare e
`gh` simulado; nenhum script faz push, `gh pr create` ou `gh pr merge`: eles voltam como argv em `commands`.

Seams: `homolog.op_release`, `homolog.main` (o monitor `--since --quiet`) e `closeout.op_merge_status`.
"""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import closeout  # noqa: E402
import homolog  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closeout import FakeGh, node, pr  # noqa: E402
from test_merge_local import HomologMergeTests, git  # noqa: E402

GOOD_BODY = ('Closes #12\n\n## Resumo\n\n### Issue #12: entrega\n\nO que muda.\n\n## Evidência\n\n### Issue #12\n\n'
             'Roteiro sem tela S1, walkthroughs/S1.md.\n\n## Risco do merge\n\nPorta de duas vias.\n')


def blocked_pr(number, **fields):
    data = pr(number, head='PREFIX/release-x')
    data.update(fields)
    return data


class ReleaseCase(HomologMergeTests):
    """A local main with issue #12 merged through `homolog merge` (watched run not needed, walkthrough written)."""

    def setUp(self):
        super().setUp()
        self.walk()
        merged = self.homolog_merge()
        self.assertEqual(merged['exitCode'], 0, merged)
        self.gh = FakeGh({12: node(12)})
        self.green_suite()

    def green_suite(self):
        """The whole suite of the release green at the tip of the local main (`homolog suite --release`)."""
        fake = self.tmp / 'fake_suite.py'
        fake.write_text('raise SystemExit(0)\n', encoding='utf-8')
        done = homolog.op_suite(str(self.root), str(self.config), None, 'full', 'main', False,
                                json.dumps([sys.executable, str(fake)]), release=True)
        self.assertEqual(done['exitCode'], 0, done)

    def release(self, action, **options):
        options.setdefault('gh', self.gh)
        options.setdefault('update_check', lambda: {'status': 'current'})
        try:
            return homolog.op_release(action, str(self.root), config_path=str(self.config), **options)
        except homolog.Refusal as error:
            return {'exitCode': 1, 'message': str(error)}

    def body(self, text=GOOD_BODY):
        path = self.tmp / 'corpo.md'
        path.write_text(text, encoding='utf-8')
        return str(path)

    def go_and_record(self, number=77):
        self.assertEqual(self.release('go', body=self.body())['exitCode'], 0)
        recorded = self.release('go', record=True, pr=number)
        self.assertEqual(recorded['exitCode'], 0, recorded)
        return recorded


class ReleasePlanTests(ReleaseCase):
    # the tests of HomologMergeTests run again here through inheritance; keep only this class's own
    def test_the_plan_is_ready_with_the_watched_run_recorded(self):
        result = self.release('plan')
        self.assertEqual((result['exitCode'], result['ready'], result['closes']), (0, True, [12]), result)

    def test_an_issue_of_closes_without_the_watched_run_recorded_is_exit_1(self):
        for path in self.records.glob('merge-local-main*.json'):
            path.unlink()
        result = self.release('plan')
        self.assertEqual((result['exitCode'], result['reason'], result['missing']), (1, 'watched_run_missing', [12]))


class ProtectedGh(FakeGh):
    """FakeGh that also answers the read of the review rule of the base."""

    def __init__(self, *args, reviews=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.reviews = reviews

    def __call__(self, argv):
        query = next((a for a in argv if a.startswith('query=')), '')
        if 'branchProtectionRule' in query:
            self.calls.append(list(argv))
            rules = [{'type': 'PULL_REQUEST', 'parameters': {'requiredApprovingReviewCount': self.reviews}}]
            return {'data': {'repository': {'ref': {'branchProtectionRule': None, 'rules': {'nodes': rules}}}}}
        return super().__call__(argv)


class BaseProtectionTests(ReleaseCase):
    """Retro 1123/1124, item 8: o plano já diz quando a regra de revisão da base obriga o merge manual."""

    def test_a_required_review_says_upfront_that_the_merge_is_manual(self):
        result = self.release('plan', gh=ProtectedGh({12: node(12)}))
        self.assertEqual(result['exitCode'], 0, result)
        self.assertEqual((result['baseProtection']['requiredReviews'], result['baseProtection']['manualMerge']),
                         (1, True))
        self.assertIn('merge será manual', result['message'])

    def test_no_required_review_and_an_unread_rule(self):
        result = self.release('plan', gh=ProtectedGh({12: node(12)}, reviews=0))
        self.assertEqual(result['baseProtection']['manualMerge'], False)
        result = self.release('plan')   # FakeGh does not answer the rule: unknown, never a refusal
        self.assertEqual((result['exitCode'], result['baseProtection']['manualMerge']), (0, None))


class BodyCheckTests(ReleaseCase):
    def test_a_body_by_the_model_with_the_closes_of_the_plan_passes(self):
        result = self.release('body-check', body=self.body())
        self.assertEqual((result['exitCode'], result['problems']), (0, []))

    def test_each_departure_from_the_model_is_named(self):
        cases = {
            '(#13) não são as de `closes` (#12)': GOOD_BODY.replace('Closes #12', 'Closes #13'),
            'palavra de fechamento': GOOD_BODY + '\nFixes #14\n',
            'Risco do merge': GOOD_BODY.replace('## Risco do merge', '## Outro'),
            'marcador': GOOD_BODY.replace('entrega', '<título>'),
            'antes de ## Resumo': GOOD_BODY.replace('Closes #12\n\n', '') + '\nCloses #12\n',
            'caminho absoluto': GOOD_BODY + '\nPrint em C:\\pasta\\x.png\n',
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                result = self.release('body-check', body=self.body(text), closes='12')
                self.assertEqual(result['exitCode'], 1)
                self.assertTrue(any(expected in p for p in result['problems']), result['problems'])


class GoTests(ReleaseCase):
    def test_go_prints_the_refspec_push_and_the_pull_request_and_runs_neither(self):
        result = self.release('go', body=self.body())
        self.assertEqual(result['exitCode'], 0, result)
        push, create = result['commands']
        name = result['release']['branch']
        self.assertRegex(name, r'^PREFIX/release-\d{4}-\d{2}-\d{2}$')
        self.assertEqual(push, ['git', '-C', str(self.root), 'push', 'origin', f'main:refs/heads/{name}'])
        self.assertEqual(create[:9], ['gh', 'pr', 'create', '--repo', 'OWNER/REPOSITORY', '--base', 'main', '--head',
                                      name])
        self.assertIn('issues #12', create[create.index('--title') + 1])
        self.assertEqual(git(self.root, 'ls-remote', 'origin', name), '')
        self.assertTrue((self.root / '.frontlights' / 'release' / 'pending.json').is_file())
        self.assertEqual(result['skillUpdate'], {'status': 'current'})

    def test_go_refuses_without_the_whole_suite_green_at_the_tip_it_releases(self):
        self.commit(self.root, 'src/depois.py', message='a main local andou depois da suíte')
        result = self.release('go', body=self.body())
        self.assertEqual((result['exitCode'], result['reason']), (1, 'full_suite'), result)
        self.assertIn('--release', result['commands'][0])
        self.assertFalse((self.root / '.frontlights' / 'release' / 'pending.json').exists())

    def test_a_relative_root_becomes_absolute_in_the_returned_git_commands(self):
        # Reverificação real (23/10/2026): `release go --root .` imprimia `git -C .`, que depende da pasta.
        import os
        before = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, before)
        result = homolog.op_release('go', '.', config_path=str(self.config), body=self.body(), gh=self.gh,
                                    update_check=lambda: {'status': 'current'})
        self.assertEqual(result['exitCode'], 0, result)
        push = result['commands'][0]
        self.assertTrue(Path(push[2]).is_absolute(), push)

    def test_the_returned_commands_do_not_depend_on_the_current_folder(self):
        import os
        self.body()
        before = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, before)
        result = self.release('go', body='corpo.md')
        self.assertEqual(result['exitCode'], 0, result)
        create = result['commands'][-1]
        body_file = Path(create[create.index('--body-file') + 1])
        self.assertTrue(body_file.is_absolute(), create)
        self.assertEqual(body_file, (self.tmp / 'corpo.md').resolve())
        self.assertEqual(create[create.index('--repo') + 1], 'OWNER/REPOSITORY')

    def test_a_body_that_fails_the_check_is_refused(self):
        result = self.release('go', body=self.body(GOOD_BODY.replace('Closes #12', 'Closes #99')))
        self.assertEqual((result['exitCode'], result['reason']), (1, 'body'))

    def test_the_legacy_branch_only_with_the_literal_sim(self):
        self.assertEqual(self.release('go', body=self.body(), legacy=True)['exitCode'], 1)
        result = self.release('go', body=self.body(), legacy=True, answer='Sim')
        name = result['release']['branch']
        self.assertEqual(result['commands'][:2], [['git', '-C', str(self.root), 'branch', name, 'main'],
                                                  ['git', '-C', str(self.root), 'push', '-u', 'origin', name]])

    def test_record_writes_current_json(self):
        recorded = self.go_and_record()
        current = json.loads((self.root / '.frontlights' / 'release' / 'current.json').read_text(encoding='utf-8'))
        self.assertEqual((current['pr'], current['issues'], current['closes']), (77, [12], [12]))
        self.assertIn('--since pending', recorded['monitor'])   # the PR GitHub does not list yet waits as pending

    def test_record_prints_the_monitor_since_the_current_state_of_the_pull_request(self):
        """Teste real do monitor (23/10/2026): com a PR já `ready`, o `--since pending` acordava o laço na hora."""
        cases = (('ready', {'reviewDecision': 'APPROVED', 'mergeStateStatus': 'CLEAN', 'mergeable': 'MERGEABLE'}),
                 ('pending', {'mergeStateStatus': 'UNKNOWN', 'mergeable': 'UNKNOWN'}),
                 ('blocked', {'reviewDecision': 'REVIEW_REQUIRED', 'mergeStateStatus': 'BLOCKED',
                              'mergeable': 'MERGEABLE'}))
        for state, fields in cases:
            with self.subTest(state=state):
                current = self.root / '.frontlights' / 'release' / 'current.json'
                if current.exists():
                    current.unlink()
                self.gh.pull_requests = {77: blocked_pr(77, **fields)}
                recorded = self.go_and_record()
                self.assertEqual(recorded['state'], state)
                self.assertIn(f'--since {state} ', recorded['monitor'])


class StatusTests(ReleaseCase):
    def status(self, data, **options):
        self.gh.pull_requests = {77: data}
        return self.release('status', **options)

    def test_a_blocked_pull_request_is_never_offered_for_merging(self):
        self.go_and_record()
        for fields in ({'reviewDecision': 'REVIEW_REQUIRED', 'mergeStateStatus': 'BLOCKED', 'mergeable': 'MERGEABLE'},
                       {'reviewDecision': 'CHANGES_REQUESTED', 'mergeStateStatus': 'CLEAN', 'mergeable': 'MERGEABLE'},
                       {'reviewDecision': None, 'mergeStateStatus': 'DIRTY', 'mergeable': 'CONFLICTING'}):
            with self.subTest(fields=fields):
                result = self.status(blocked_pr(77, **fields))
                self.assertEqual((result['state'], result['offerMerge']), ('blocked', False))
                self.assertNotIn('question', result)

    def test_a_clean_pull_request_gets_the_merge_question_with_its_commands(self):
        self.go_and_record()
        result = self.status(blocked_pr(77, reviewDecision='APPROVED', mergeStateStatus='CLEAN', mergeable='MERGEABLE'))
        self.assertEqual((result['state'], result['offerMerge']), ('ready', True))
        self.assertEqual(result['question'], 'Mesclar a PR #77 em main?')
        self.assertEqual(result['options'], ['Sim, mesclar', 'Não, aguardar o merge'])
        # not a draft (isDraft false): `gh pr ready` is not offered, only the merge (teste real, 23/10/2026)
        self.assertEqual(result['commands'], [['gh', 'pr', 'merge', '77', '--merge', '--repo', 'OWNER/REPOSITORY']])

    def test_a_draft_pull_request_gets_gh_pr_ready_before_the_merge(self):
        self.go_and_record()
        result = self.status(blocked_pr(77, reviewDecision='APPROVED', mergeStateStatus='DRAFT', mergeable='MERGEABLE',
                                        isDraft=True))
        self.assertEqual((result['state'], result['offerMerge']), ('ready', True))
        self.assertEqual(result['commands'], [['gh', 'pr', 'ready', '77', '--repo', 'OWNER/REPOSITORY'],
                                              ['gh', 'pr', 'merge', '77', '--merge', '--repo', 'OWNER/REPOSITORY']])

    def test_since_wakes_only_on_a_change(self):
        self.go_and_record()
        data = blocked_pr(77, reviewDecision='REVIEW_REQUIRED', mergeStateStatus='BLOCKED', mergeable='MERGEABLE')
        self.assertEqual(self.status(data, since='blocked')['exitCode'], homolog.UNCHANGED)
        self.assertEqual(self.status(data, since='pending')['exitCode'], 0)

    def test_merge_status_carries_the_block(self):
        self.gh.pull_requests = {77: blocked_pr(77, reviewDecision='REVIEW_REQUIRED', mergeStateStatus='BLOCKED',
                                                mergeable='MERGEABLE')}
        result = closeout.op_merge_status(str(self.config), '77', 'main', self.gh)
        entry = result['pullRequests'][0]
        self.assertEqual((entry['reviewDecision'], entry['mergeStateStatus'], entry['blocked']),
                         ('REVIEW_REQUIRED', 'BLOCKED', True))
        self.assertEqual(result['blocked'], [77])


class LandedTests(ReleaseCase):
    def land(self, **options):
        options.setdefault('planner', lambda root, config, issues, base: {'commands': [
            {'kind': 'remove_worktree', 'item': 12, 'argv': ['git', 'worktree', 'remove', 'x']}], 'issues': issues})
        return self.release('landed', **options)

    def test_landed_waits_for_the_merge(self):
        self.go_and_record()
        self.gh.pull_requests = {77: pr(77)}
        self.assertEqual(self.land()['exitCode'], 2)

    def test_landed_fast_forwards_prunes_and_prints_the_cleanup(self):
        self.go_and_record()
        git(self.root, 'push', '-q', 'origin', 'main')   # GitHub's merge of the release, played by the test
        self.gh.pull_requests = {77: pr(77, state='MERGED')}
        result = self.land()
        self.assertEqual(result['exitCode'], 0, result)
        self.assertEqual([c['argv'] for c in result['commands']], [['git', 'worktree', 'remove', 'x']])
        self.assertEqual(result['verify'][-2:], ['--issues', '12'])
        release = self.root / '.frontlights' / 'release'
        self.assertFalse((release / 'current.json').exists())
        self.assertEqual(len(list(release.glob('landed-*.json'))), 1)

    def test_landed_updates_the_handoff_of_every_issue_and_lists_the_leftover_worktrees(self):
        """Retro 1123/1124, item 8: depois do merge nenhum handoff ainda pede o closeout, e as worktrees de cada
        issue que o plano não remove são listadas."""
        handoff = self.records / 'handoff.md'
        handoff.write_text('# Passagem\n\n- Release: aguardando\n- Próximo passo: closeout\n', encoding='utf-8')
        leftover = self.tmp / 'base-12'
        git(self.root, 'worktree', 'add', '-q', '-b', 'PREFIX/base-12', str(leftover), 'main')
        self.go_and_record()
        git(self.root, 'push', '-q', 'origin', 'main')
        self.gh.pull_requests = {77: pr(77, state='MERGED')}
        result = self.land()
        self.assertEqual(result['exitCode'], 0, result)
        self.assertEqual(result['handoffs'], [str(handoff)])
        text = handoff.read_text(encoding='utf-8')
        self.assertIn('- Release: PR #77 mesclada em main', text)
        self.assertNotIn('closeout', text)
        paths = [Path(item['path']).name for item in result['leftoverWorktrees']]
        self.assertIn('base-12', paths)
        self.assertTrue(all(item['issue'] == 12 for item in result['leftoverWorktrees']))

    def test_landed_lists_the_delete_of_the_remote_release_branch_when_github_kept_it(self):
        recorded = self.go_and_record()
        name = recorded['release']['branch']
        git(self.root, 'push', '-q', 'origin', f'main:refs/heads/{name}')   # the release push; GitHub keeps the branch
        git(self.root, 'push', '-q', 'origin', 'main')
        self.gh.pull_requests = {77: pr(77, state='MERGED')}
        result = self.land()
        self.assertEqual(result['exitCode'], 0, result)
        self.assertEqual(result['commands'][-1], {'kind': 'delete_remote_branch', 'item': name,
                                                  'argv': ['git', '-C', str(self.root), 'push', 'origin', '--delete',
                                                           name]})
        # one format only: every item of `commands` is {kind, argv}, as the cleanup plan writes them
        for command in result['commands']:
            self.assertIsInstance(command, dict, command)
            self.assertTrue({'kind', 'argv'} <= set(command), command)

    def test_a_pull_that_does_not_fast_forward_stops_and_asks(self):
        self.go_and_record()
        other = self.tmp / 'outro'
        subprocess.run(['git', 'clone', '-q', str(self.folder / 'origin.git'), str(other)], check=True)
        for key, value in (('user.email', 'x@example.invalid'), ('user.name', 'X')):
            git(other, 'config', key, value)
        (other / 'divergente.txt').write_text('x', encoding='utf-8')
        git(other, 'add', '.')
        git(other, 'commit', '-q', '-m', 'divergente')
        git(other, 'push', '-q', 'origin', 'main')
        before = git(self.root, 'rev-parse', 'main')
        self.gh.pull_requests = {77: pr(77, state='MERGED')}
        result = self.land()
        self.assertEqual((result['exitCode'], result['reason']), (2, 'not_fast_forward'))
        self.assertEqual(git(self.root, 'rev-parse', 'main'), before)


class MonitorTests(unittest.TestCase):
    def run_main(self, answer):
        out = io.StringIO()
        with mock.patch.object(homolog, 'op_release', return_value=answer), contextlib.redirect_stdout(out):
            code = homolog.main(['release', 'status', '--root', '.', '--since', 'blocked', '--quiet'])
        return code, out.getvalue()

    def test_the_monitor_is_silent_until_the_state_changes(self):
        code, text = self.run_main({'exitCode': homolog.UNCHANGED, 'pr': 77, 'state': 'blocked'})
        self.assertEqual((code, text), (homolog.UNCHANGED, ''))
        code, text = self.run_main({'exitCode': 0, 'pr': 77, 'state': 'ready', 'message': 'pronta'})
        self.assertEqual(code, 0)
        self.assertEqual(len(text.strip().splitlines()), 1)
        self.assertIn('PR #77 ready', text)


for name in [n for n in dir(HomologMergeTests) if n.startswith('test_')]:
    for case in (ReleaseCase, ReleasePlanTests, BaseProtectionTests, BodyCheckTests, GoTests, StatusTests, LandedTests):
        if name not in case.__dict__:
            setattr(case, name, None)   # inherited only for its fixture, never run twice
del ReleaseCase, HomologMergeTests   # loaded here only as bases


if __name__ == '__main__':
    unittest.main()
