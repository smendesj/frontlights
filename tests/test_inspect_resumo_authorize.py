"""Economia nos utilitários: `inspect --summary` e um `authorize` mais flexível.

O modo resumido do `inspect` mostra, por fonte, o status e a contagem e, por issue, só número, título, estado e
caixas de critério; a saída padrão não muda. O `authorize` lê a operação da entrada padrão (`--operation -`) e não
exige que as outras worktrees do charter já existam. Só marcadores genéricos (repositório público).
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

SCRIPT = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'

BODY = ('Contexto longo que não deve aparecer no resumo.\n\n'
        '## Critérios de aceitação\n\n'
        '- [x] S1. Primeira fatia\n'
        '  - Entrega: algo\n'
        '- [ ] S2. Segunda fatia\n'
        '- [ ] S3. Terceira fatia\n')

PAGES = [[{'number': 1, 'title': 'Fatia com critérios', 'state': 'open', 'body': BODY,
           'labels': [{'name': 'enhancement'}], 'user': {'login': 'pessoa-ficticia'}},
          {'number': 2, 'title': 'Pull request', 'state': 'open', 'body': 'x', 'pull_request': {}}],
         [{'number': 3, 'title': 'Sem seção de critérios', 'state': 'closed', 'body': None}]]


def inspect(config, summary):
    with tempfile.TemporaryDirectory() as root, \
            patch.object(frontlights, 'run', return_value=json.dumps(PAGES).encode()):
        return frontlights.inspect(config, root, summary=summary)


class InspectSummaryTests(unittest.TestCase):
    def test_summary_keeps_only_number_title_state_and_boxes_of_each_issue(self):
        github = inspect({'repository': 'example/project'}, True)['sources']['github']
        self.assertEqual(github, {
            'status': 'available', 'source': 'https://github.com/example/project/issues', 'count': 2, 'open': 1,
            'issues': [{'number': 1, 'title': 'Fatia com critérios', 'state': 'open',
                        'boxes': {'checked': 1, 'total': 3}},
                       {'number': 3, 'title': 'Sem seção de critérios', 'state': 'closed', 'boxes': None}]})

    def test_summary_is_marked_and_keeps_the_other_keys_of_the_output(self):
        full, short = inspect({'repository': 'example/project'}, False), inspect({'repository': 'example/project'}, True)
        self.assertTrue(short.pop('summary'))
        self.assertNotIn('summary', full)
        self.assertEqual(sorted(short), sorted(full))
        self.assertNotIn('Contexto longo', json.dumps(short, ensure_ascii=False))
        self.assertIn('Contexto longo', json.dumps(full, ensure_ascii=False))

    def test_default_output_still_carries_the_whole_issue(self):
        issues = inspect({'repository': 'example/project'}, False)['sources']['github']['issues']
        self.assertEqual(issues, [i for page in PAGES for i in page if 'pull_request' not in i])

    def test_a_configured_board_changes_nothing_without_the_flag(self):
        """Com `project` configurado, a saída padrão segue inteira e o quadro sai igual nos dois modos."""
        project = {'owner': 'example-org', 'number': 3, 'assignee': '@me', 'issue_type': 'Task',
                   'fields': {'Status': 'Open', 'Area': None}}

        def gh(argv):
            if argv[:2] == ['gh', 'project']:
                return json.dumps({'title': 'Quadro fictício',
                                   'url': 'https://github.com/orgs/example-org/projects/3'}).encode()
            return json.dumps(PAGES).encode()
        results = {}
        for summary in (False, True):
            with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=gh):
                results[summary] = frontlights.inspect({'repository': 'example/project', 'project': project}, root,
                                                       summary=summary)
        self.assertNotIn('summary', results[False])
        self.assertEqual(results[False]['sources']['github']['issues'],
                         [i for page in PAGES for i in page if 'pull_request' not in i])
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
            plain = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                   capture_output=True, text=True, encoding='utf-8')
            short = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root,
                                    '--summary'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(short.returncode, 0, short.stderr)
        self.assertNotIn('summary', json.loads(plain.stdout))
        output = json.loads(short.stdout)
        self.assertIs(output['summary'], True)
        self.assertEqual(output['sources']['github'], {'status': 'unconfigured'})


def charter(root, *extra):
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
        result = frontlights.authorize(charter(self.root, self.slice), self.op)
        self.assertEqual(result['scope_check'], 'pass')

    def test_an_operation_on_a_worktree_that_does_not_exist_is_refused_by_name(self):
        op = dict(self.op, worktree=str(self.missing), branch='claude/issue-1-s2', slice='S2',
                  path=str(self.missing / 'src' / 'app.py'))
        with self.assertRaisesRegex(ValueError, 'worktree of the operation does not exist'):
            frontlights.authorize(charter(self.root, self.slice), op)

    def test_once_it_is_cut_the_declared_worktree_is_accepted(self):
        (self.missing / 'src').mkdir(parents=True)
        op = dict(self.op, worktree=str(self.missing), branch='claude/issue-1-s2', slice='S2',
                  path=str(self.missing / 'src' / 'app.py'))
        self.assertEqual(frontlights.authorize(charter(self.root, self.slice), op)['scope_check'], 'pass')

    def test_entries_of_the_issue_are_still_validated(self):
        for bad in ({'issue': 1, 'branch': 'claude/issue-1-s3'}, {'issue': 1, 'path': ''}, 'issue-1'):
            with self.subTest(entry=bad), self.assertRaisesRegex(ValueError, 'worktree entry'):
                frontlights.authorize(charter(self.root, bad), self.op)


class AuthorizeStdinTests(unittest.TestCase):
    def run_cli(self, operation, charter_data, stdin=None):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'charter.json'
            path.write_text(json.dumps(charter_data), encoding='utf-8')
            return subprocess.run([sys.executable, str(SCRIPT), 'authorize', '--charter', str(path),
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
        run = self.run_cli('-', charter(self.root), json.dumps(self.op))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['scope_check'], 'pass')

    def test_operation_from_a_file_still_works(self):
        operation = self.root / 'op.json'
        operation.write_text(json.dumps(self.op), encoding='utf-8')
        run = self.run_cli(str(operation), charter(self.root))
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_invalid_json_on_standard_input_is_a_clean_error(self):
        run = self.run_cli('-', charter(self.root), '{nao e json')
        self.assertEqual(run.returncode, 1)
        self.assertNotIn('Traceback', run.stderr)
        self.assertIn('error', json.loads(run.stderr))


if __name__ == '__main__':
    unittest.main()
