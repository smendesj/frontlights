"""Etapa 5 por comando, S1 (redesenho, issue 7): `frontlights.py publish-issue --plan --approved` confere o carimbo,
publica as bloqueadoras primeiro com labels e `--blocked-by`, põe no quadro com os campos, relê o GitHub, confere a
conta e o repositório antes de cada escrita, adota uma issue que já existe só com labels e quadro, e retoma uma
publicação parcial relendo o GitHub pelo título.

Seams: `frontlights.publish_issue` e a entrada `frontlights.py publish-issue`. O `gh` é simulado (um GitHub em
memória): estes testes não homologam o GitHub real. Marcadores genéricos (OWNER/REPOSITORY).
"""
import copy
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import frontlights  # noqa: E402
import stamp  # noqa: E402
import _cli  # noqa: E402

REPO = 'OWNER/REPOSITORY'
BOARD = {'owner': 'OWNER', 'number': 7, 'assignee': '@me', 'issue_type': 'Task', 'fields': {'Priority': None}}
BODY_A = '# Salvar uma observação\n\n## Critérios de aceitação\n\n- [ ] S1. Salvar e ver depois de recarregar\n'
BODY_B = '# Editar uma observação\n\n## Critérios de aceitação\n\n- [ ] S1. Editar\n- [ ] S2. Ver o conflito\n'


class FakeGitHub:
    """`gh` in memory: create, edit, project item-add/item-edit, view, list, api user and repo view."""

    def __init__(self, login='OWNER-LOGIN', repo=REPO, fail=None, lose_url=False, issue_types=('Task', 'Bug'),
                 stderr=''):
        self.issues, self.calls, self.next = {}, [], 101
        self.login, self.repo, self.fail, self.lose_url = login, repo, fail or set(), lose_url
        self.issue_types, self.stderr = issue_types, stderr   # issue_types None: a personal account's repository
        self.now = dt.datetime.now(dt.timezone.utc)

    def add(self, number, title, body, labels=()):
        self.issues[number] = {'number': number, 'title': title, 'body': body, 'labels': list(labels),
                               'assignees': [], 'issueType': None, 'projectItems': [], 'blockedBy': [],
                               'fields': {}, 'createdAt': '2020-01-01T00:00:00Z'}

    def __call__(self, argv):
        self.calls.append(list(argv))
        head = tuple(argv[:2])
        if head in self.fail:
            return 1, '', self.stderr
        if head == ('api', 'graphql') and any('issueTypes' in part for part in argv):
            types = None if self.issue_types is None else {'nodes': [{'name': n} for n in self.issue_types]}
            return 0, json.dumps({'data': {'repository': {'issueTypes': types}}})
        if head == ('api', 'user'):
            return 0, json.dumps({'login': self.login})
        if head == ('repo', 'view'):
            return 0, json.dumps({'nameWithOwner': self.repo, 'viewerPermission': 'WRITE'})
        if head == ('issue', 'create'):
            options = self.options(argv[2:])
            number, self.next = self.next, self.next + 1
            self.add(number, options['--title'][0], Path(options['--body-file'][0]).read_bytes().decode('utf-8'),
                     options.get('--label', []))
            self.issues[number]['createdAt'] = self.now.isoformat().replace('+00:00', 'Z')
            for value in options.get('--blocked-by', []):
                self.issues[number]['blockedBy'] += [{'number': int(n)} for n in value.split(',')]
            url = f'https://github.com/{REPO}/issues/{number}\n'
            return 0, '' if self.lose_url else url
        if head == ('issue', 'edit'):
            issue = self.issues[int(argv[2])]
            options = self.options(argv[3:])
            issue['labels'] += options.get('--add-label', [])
            issue['assignees'] += [{'login': self.login if a == '@me' else a} for a in options.get('--add-assignee', [])]
            if '--type' in options:
                issue['issueType'] = {'name': options['--type'][0]}
            for value in options.get('--add-blocked-by', []):
                issue['blockedBy'] += [{'number': int(n)} for n in value.split(',')]
            if '--body-file' in options:
                issue['body'] = Path(options['--body-file'][0]).read_text(encoding='utf-8')
            return 0, ''
        if head == ('project', 'item-add'):
            number = int(self.options(argv[3:])['--url'][0].rsplit('/', 1)[1])
            self.issues[number]['projectItems'] = [{'title': 'Board'}]
            return 0, ''
        if head == ('project', 'item-edit'):
            options = self.options(argv[3:])
            number = int(options['--url'][0].rsplit('/', 1)[1])
            self.issues[number]['fields'][options['--field'][0]] = options['--value'][0]
            return 0, ''
        if head == ('issue', 'view'):
            issue = self.issues[int(argv[2])]
            view = {k: v for k, v in issue.items() if k != 'fields'}
            view['labels'] = [{'name': n} for n in issue['labels']]
            view['url'] = f'https://github.com/{REPO}/issues/{issue["number"]}'
            return 0, json.dumps(view)
        if head == ('issue', 'list'):
            title = self.options(argv[2:])['--search'][0].rsplit(' in:title', 1)[0]
            return 0, json.dumps([{'number': i['number'], 'title': i['title'], 'createdAt': i['createdAt'],
                                   'url': f'https://github.com/{REPO}/issues/{i["number"]}'}
                                  for i in self.issues.values() if title in i['title']])
        raise AssertionError(f'gh inesperado: {argv}')

    @staticmethod
    def options(argv):
        found, index = {}, 0
        while index < len(argv):
            found.setdefault(argv[index], []).append(argv[index + 1])
            index += 2
        return found

    def writes(self):
        return [c for c in self.calls if tuple(c[:2]) in {('issue', 'create'), ('issue', 'edit'),
                                                          ('project', 'item-add'), ('project', 'item-edit')}]


class PublishCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / '.frontlights').mkdir()
        self.config = self.root / '.frontlights' / 'config.json'
        self.write_config(project=BOARD)

    def write_config(self, **extra):
        self.config.write_text(json.dumps({'repository': REPO, **extra}), encoding='utf-8')

    def issue(self, ident, title, body_file, deps=(), **extra):
        data = {'id': ident, 'title': title, 'outcome': title, 'acceptance': ['ok'], 'vertical_check': 'ver',
                'tests': ['t'], 'ownership': ['src'], 'dependencies': list(deps), 'non_goals': ['n'], 'risks': ['r'],
                'session_sized': True, 'status': 'ready', 'project_fields': {'Priority': 'Medium'}}
        if body_file:
            data['body_file'] = body_file
        data.update(extra)
        return data

    def write_plan(self, issues, repository=REPO):
        plan = self.root / '.frontlights' / 'plan.json'
        plan.write_text(json.dumps({'repository': repository, 'issues': issues}, ensure_ascii=False), encoding='utf-8')
        return plan

    def standard(self, approve=True):
        (self.root / '.frontlights' / 'a.md').write_bytes(BODY_A.encode('utf-8'))
        (self.root / '.frontlights' / 'b.md').write_bytes(BODY_B.encode('utf-8'))
        plan = self.write_plan([self.issue(2, 'Editar uma observação', 'b.md', deps=[1]),
                                self.issue(1, 'Salvar uma observação', 'a.md')])
        approved = self.root / '.frontlights' / 'plano-r1.md'
        approved.write_text('| 1 | Salvar uma observação |\n| 2 | Editar uma observação |\n\n' + BODY_A + '\n'
                            + BODY_B, encoding='utf-8')
        if approve:
            self.approve(approved)
        return plan, approved

    def approve(self, path):
        sha = stamp.run(stamp.build_parser().parse_args([str(path), '--root', str(self.root)]))['sha256']
        args = stamp.build_parser().parse_args([str(path), '--root', str(self.root), '--approve', '--answer',
                                                'Aprovar', '--expect', sha, '--revision', 'r1'])
        self.assertTrue(stamp.run(args)['ok'])

    def publish(self, plan, approved, gh, **options):
        options.setdefault('account', lambda data: _cli.gh_account(data, frontlights.gh_reader(gh)))
        return frontlights.publish_issue(plan, approved, self.root, str(self.config), gh=gh, **options)


class ApprovalTests(PublishCase):
    def test_without_the_approval_nothing_is_written(self):
        plan, approved = self.standard(approve=False)
        gh = FakeGitHub()
        result = self.publish(plan, approved, gh)
        self.assertEqual(result['reason'], 'not_approved')
        self.assertEqual(gh.calls, [])

    def test_a_file_changed_after_the_approval_is_refused(self):
        plan, approved = self.standard()
        approved.write_text(approved.read_text(encoding='utf-8') + '\nmais uma linha\n', encoding='utf-8')
        gh = FakeGitHub()
        self.assertEqual(self.publish(plan, approved, gh)['reason'], 'not_approved')
        self.assertEqual(gh.calls, [])

    def test_a_body_that_is_not_in_the_approved_file_is_refused(self):
        plan, approved = self.standard()
        (self.root / '.frontlights' / 'b.md').write_text(BODY_B + '- [ ] S3. Outra coisa\n', encoding='utf-8')
        gh = FakeGitHub()
        self.assertEqual(self.publish(plan, approved, gh)['reason'], 'body_not_approved')
        self.assertEqual(gh.calls, [])

    def test_the_plan_as_the_approved_file_covers_its_body_files(self):
        plan, _ = self.standard(approve=False)
        self.approve(plan)
        gh = FakeGitHub()
        result = self.publish(plan, plan, gh)
        self.assertTrue(result['ok'], result)
        self.assertEqual(gh.issues[102]['body'], BODY_B)

    def test_a_body_file_changed_after_the_plan_was_approved_is_refused(self):
        plan, _ = self.standard(approve=False)
        self.approve(plan)
        (self.root / '.frontlights' / 'b.md').write_text(BODY_B + '- [ ] S3. Outra coisa\n', encoding='utf-8')
        gh = FakeGitHub()
        result = self.publish(plan, plan, gh)
        self.assertEqual(result['reason'], 'body_not_approved', result)
        self.assertEqual(gh.calls, [])
        self.assertFalse((self.root / frontlights.PUBLISH_FOLDER).exists())

    def test_the_plan_must_pass_validate_plan(self):
        plan, approved = self.standard()
        data = json.loads(plan.read_text(encoding='utf-8'))
        del data['issues'][0]['risks']
        plan.write_text(json.dumps(data), encoding='utf-8')
        result = self.publish(plan, approved, FakeGitHub())
        self.assertEqual(result['reason'], 'plan_invalid')
        self.assertEqual(result['path'], 'issues[0].risks')


class PublishTests(PublishCase):
    def test_blockers_first_with_labels_blocked_by_board_and_reread(self):
        plan, approved = self.standard()
        gh = FakeGitHub()
        result = self.publish(plan, approved, gh)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['order'], [1, 2])
        creates = [c for c in gh.calls if c[:2] == ['issue', 'create']]
        self.assertEqual([c[c.index('--title') + 1] for c in creates], ['Salvar uma observação', 'Editar uma observação'])
        self.assertNotIn('--blocked-by', creates[0])
        self.assertEqual(creates[1][creates[1].index('--blocked-by') + 1], '101')   # the real number, not the plan id
        self.assertEqual([p['number'] for p in result['published']], [101, 102])
        self.assertTrue(all(p['verified'] for p in result['published']))
        self.assertEqual(result['published'][1]['criteria'], {'checked': 0, 'total': 2})
        issue = gh.issues[102]
        self.assertEqual(issue['body'], BODY_B)
        self.assertEqual(issue['fields'], {'Priority': 'Medium'})
        self.assertEqual(issue['issueType'], {'name': 'Task'})
        self.assertTrue(issue['projectItems'])

    def test_the_account_and_the_repository_are_checked_before_every_write(self):
        plan, approved = self.standard()
        gh = FakeGitHub()
        self.publish(plan, approved, gh)
        for index, call in enumerate(gh.calls):
            if call in gh.writes():
                self.assertEqual(gh.calls[index - 2][:2], ['api', 'user'], call)
                self.assertEqual(gh.calls[index - 1][:2], ['repo', 'view'], call)

    def test_a_wrong_account_stops_before_any_write_with_the_question(self):
        plan, approved = self.standard()
        self.write_config(project=BOARD, github={'account': 'OTHER-LOGIN'})
        gh = FakeGitHub()
        result = self.publish(plan, approved, gh)
        self.assertEqual(result['reason'], 'account_mismatch')
        self.assertIn('gh auth switch --user OTHER-LOGIN', result['question'])
        self.assertEqual(gh.writes(), [])

    def test_a_wrong_repository_stops_before_any_write(self):
        plan, approved = self.standard()
        gh = FakeGitHub(repo='OWNER/OTHER')
        self.assertEqual(self.publish(plan, approved, gh)['reason'], 'repository_mismatch')
        self.assertEqual(gh.writes(), [])

    def test_never_a_sub_issue(self):
        plan, approved = self.standard()
        gh = FakeGitHub()
        self.publish(plan, approved, gh)
        for call in gh.calls:
            self.assertNotIn('--parent', call)
            self.assertFalse(any('sub_issues' in part for part in call))

    def test_an_adopted_issue_takes_only_labels_blocked_by_and_the_board(self):
        (self.root / '.frontlights' / 'a.md').write_bytes(BODY_A.encode('utf-8'))
        url = f'https://github.com/{REPO}/issues/40'
        plan = self.write_plan([self.issue(1, 'Salvar uma observação', 'a.md'),
                                self.issue(40, 'Issue que já existe', None, deps=[1], url=url, labels=['area: x'])])
        approved = self.root / '.frontlights' / 'plano-r1.md'
        approved.write_text('Salvar uma observação · Issue que já existe\n\n' + BODY_A, encoding='utf-8')
        self.approve(approved)
        gh = FakeGitHub()
        gh.add(40, 'Issue que já existe', 'corpo de antes\n')
        result = self.publish(plan, approved, gh)
        self.assertTrue(result['ok'], result)
        edits = [c for c in gh.calls if c[:3] == ['issue', 'edit', '40']]
        self.assertTrue(edits)
        self.assertFalse(any('--body-file' in c for c in edits))
        self.assertEqual(gh.issues[40]['body'], 'corpo de antes\n')
        self.assertEqual(gh.issues[40]['blockedBy'], [{'number': 101}])
        self.assertIn('area: x', gh.issues[40]['labels'])
        self.assertTrue(result['published'][1]['adopted'])

    def test_the_reread_that_differs_exits_2_and_says_what(self):
        plan, approved = self.standard()
        gh = FakeGitHub()
        original = gh.__call__

        class Drifting(FakeGitHub):
            def __call__(self, argv):
                code, out = original(argv)
                if argv[:2] == ['issue', 'view'] and argv[2] == '102':
                    data = json.loads(out)
                    data['body'] += '\nalguém editou\n'
                    out = json.dumps(data)
                return code, out
        drifting = Drifting()
        drifting.__dict__ = gh.__dict__
        result = self.publish(plan, approved, drifting)
        self.assertEqual(result['exitCode'], 2)
        self.assertIn('corpo diferente do aprovado', result['published'][1]['problems'])

    def test_the_reread_accepts_blocked_by_as_a_connection_with_nodes(self):
        """gh 2.97 returns blockedBy as {"nodes": [...], "totalCount": n}, not a list."""
        plan, approved = self.standard()
        gh = FakeGitHub()
        original = gh.__call__

        class Connection(FakeGitHub):
            def __call__(self, argv):
                code, out = original(argv)
                if argv[:2] == ['issue', 'view']:
                    data = json.loads(out)
                    data['blockedBy'] = {'nodes': data['blockedBy'], 'totalCount': len(data['blockedBy'])}
                    out = json.dumps(data)
                return code, out
        connection = Connection()
        connection.__dict__ = gh.__dict__
        result = self.publish(plan, approved, connection)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['exitCode'], 0)

    def test_dry_run_prints_the_writes_and_runs_nothing(self):
        plan, approved = self.standard(approve=False)
        gh = FakeGitHub()
        result = self.publish(plan, approved, gh, dry_run=True)
        self.assertTrue(result['dryRun'])
        self.assertEqual(gh.calls, [])
        second = result['issues'][1]['commands']
        self.assertIn('<#1>', second[0])
        self.assertEqual(second[0][:3], ['gh', 'issue', 'create'])
        body_file = Path(second[0][second[0].index('--body-file') + 1])
        self.assertEqual(body_file, (self.root / '.frontlights' / 'b.md').resolve())   # never relative to the cwd
        self.assertIn(['gh', 'project', 'item-edit', '7', '--owner', 'OWNER', '--url', '<url #2>', '--field',
                       'Priority', '--value', 'Medium'], second)
        self.assertIn('ainda não tem aprovação', result['message'])


class ResumeTests(PublishCase):
    def test_a_failed_board_write_is_partial_and_resume_writes_only_what_is_missing(self):
        plan, approved = self.standard()
        gh = FakeGitHub(fail={('project', 'item-add')})
        first = self.publish(plan, approved, gh)
        self.assertEqual(first['reason'], 'write_failed')
        again = self.publish(plan, approved, gh)
        self.assertEqual(again['reason'], 'partial_publication')
        gh.fail = set()
        done = self.publish(plan, approved, gh, resume=True)
        self.assertTrue(done['ok'], done)
        self.assertEqual(len([c for c in gh.calls if c[:2] == ['issue', 'create']]), 2)
        self.assertEqual(sorted(gh.issues), [101, 102])

    def test_resume_finds_by_title_an_issue_whose_creation_answer_was_lost(self):
        plan, approved = self.standard()
        gh = FakeGitHub(lose_url=True)
        first = self.publish(plan, approved, gh)
        self.assertEqual(first['reason'], 'create_unclear')
        gh.lose_url = False
        done = self.publish(plan, approved, gh, resume=True)
        self.assertTrue(done['ok'], done)
        self.assertTrue(done['published'][0]['recovered'])
        self.assertEqual(sorted(gh.issues), [101, 102])   # the first issue was not created twice

    def test_resume_ignores_an_old_issue_with_the_same_title(self):
        plan, approved = self.standard()
        gh = FakeGitHub(lose_url=True)
        gh.add(9, 'Salvar uma observação', 'antiga\n')   # created in 2020, before the publication started
        self.publish(plan, approved, gh)
        gh.lose_url = False
        done = self.publish(plan, approved, gh, resume=True)
        self.assertEqual(done['published'][0]['number'], 101)


class IssueTypeTests(PublishCase):
    """Teste real do quadro (23/10/2026): num repositório de conta pessoal não há tipos de issue, e a publicação
    criava a issue para só falhar no `gh issue edit --type`, com "o gh recusou". Agora os tipos são lidos antes da
    primeira escrita, e toda recusa `write_failed` traz o stderr do gh, mascarado."""

    def test_a_repository_without_issue_types_refuses_before_any_write(self):
        plan, approved = self.standard()
        gh = FakeGitHub(issue_types=None)
        result = self.publish(plan, approved, gh)
        self.assertEqual(result['reason'], 'issue_type_unavailable', result)
        self.assertEqual(gh.writes(), [])
        self.assertEqual(result['available'], [])
        self.assertIn('issue_type', result['hint'])
        self.assertIn('issue_type_by_label', result['hint'])
        self.assertIn('config', result['hint'])

    def test_a_type_the_repository_lacks_is_refused_naming_the_ones_it_has(self):
        plan, approved = self.standard()
        gh = FakeGitHub(issue_types=('Bug', 'Feature'))
        result = self.publish(plan, approved, gh)
        self.assertEqual(result['reason'], 'issue_type_unavailable', result)
        self.assertEqual(gh.writes(), [])
        self.assertEqual(result['available'], ['Bug', 'Feature'])
        self.assertIn('Task', result['message'])
        self.assertIn('Bug, Feature', result['message'])

    def test_a_board_without_a_type_publishes_without_type(self):
        board = {k: v for k, v in BOARD.items() if k != 'issue_type'}
        self.write_config(project=board)
        plan, approved = self.standard()
        gh = FakeGitHub(issue_types=None)
        result = self.publish(plan, approved, gh)
        self.assertTrue(result['ok'], result)
        self.assertFalse(any('--type' in call for call in gh.calls))

    def test_write_failed_carries_the_masked_stderr_of_gh(self):
        plan, approved = self.standard()
        token = 'gho_' + 'A1b2C3d4' * 5
        gh = FakeGitHub(fail={('project', 'item-add')},
                        stderr=f'GraphQL: Could not resolve to a ProjectV2 (token {token})')
        result = self.publish(plan, approved, gh)
        self.assertEqual(result['reason'], 'write_failed', result)
        self.assertIn('Could not resolve to a ProjectV2', result['message'])
        self.assertNotIn(token, json.dumps(result))

    def test_inspect_warns_when_the_repository_lacks_the_configured_type(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'api', 'graphql'] and any('issueTypes' in a for a in argv):
                return json.dumps({'data': {'repository': {'issueTypes': None}}}).encode()
            if argv[:3] == ['gh', 'project', 'view']:
                return json.dumps({'title': 'Board', 'url': 'https://github.com/users/OWNER/projects/7'}).encode()
            return b'[]'
        with tempfile.TemporaryDirectory() as root, mock.patch.object(frontlights, 'run', side_effect=fake):
            result = frontlights.inspect({'repository': REPO, 'project': BOARD}, root)
        found = [w for w in result.get('warnings', []) if w.startswith('issue_type_unavailable')]
        self.assertEqual(len(found), 1, result.get('warnings'))
        self.assertIn('Task', found[0])

    def test_inspect_says_nothing_when_the_type_exists(self):
        def fake(argv, cwd=None):
            if argv[:3] == ['gh', 'api', 'graphql'] and any('issueTypes' in a for a in argv):
                return json.dumps({'data': {'repository': {'issueTypes': {'nodes': [{'name': 'Task'}]}}}}).encode()
            if argv[:3] == ['gh', 'project', 'view']:
                return json.dumps({'title': 'Board', 'url': 'https://github.com/users/OWNER/projects/7'}).encode()
            return b'[]'
        with tempfile.TemporaryDirectory() as root, mock.patch.object(frontlights, 'run', side_effect=fake):
            result = frontlights.inspect({'repository': REPO, 'project': BOARD}, root)
        self.assertFalse([w for w in result.get('warnings', []) if w.startswith('issue_type_unavailable')])


class LocalTests(PublishCase):
    def test_a_project_without_remote_writes_the_local_records(self):
        self.config.write_text(json.dumps({'repository': None}), encoding='utf-8')
        (self.root / '.frontlights' / 'a.md').write_bytes(BODY_A.encode('utf-8'))
        issue = self.issue(1, 'Salvar uma observação', 'a.md')
        del issue['project_fields']
        plan = self.write_plan([issue], repository=None)
        approved = self.root / '.frontlights' / 'plano-r1.md'
        approved.write_text('Salvar uma observação\n' + BODY_A, encoding='utf-8')
        self.approve(approved)
        gh = FakeGitHub()
        result = frontlights.publish_issue(plan, approved, self.root, str(self.config), gh=gh)
        self.assertTrue(result['ok'], result)
        record = json.loads((self.root / '.frontlights' / 'issues' / '1' / 'issue.json').read_text(encoding='utf-8'))
        self.assertEqual(record['source'], 'local')
        self.assertEqual(record['body'], BODY_A)
        self.assertEqual(gh.calls, [])


class NotesTests(PublishCase):
    """Redesenho, issue 10 (proposta, seção 11): as notas de antes do número vão para a pasta da primeira issue."""

    def notes(self, **files):
        folder = self.root / '.frontlights' / 'notes'
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (folder / f'{name}.md').write_text(text, encoding='utf-8')
        return folder

    def test_the_notes_move_to_the_first_issue_published(self):
        source = self.notes(sonda='mapa da sonda', leitor='mapa do leitor')
        plan, approved = self.standard()
        result = self.publish(plan, approved, FakeGitHub())
        self.assertTrue(result['ok'], result)
        target = self.root / '.frontlights' / 'issues' / '101' / 'notes'
        self.assertEqual(sorted(p.name for p in target.iterdir()), ['leitor.md', 'sonda.md'])
        self.assertEqual((target / 'sonda.md').read_text(encoding='utf-8'), 'mapa da sonda')
        self.assertFalse(source.exists())
        self.assertEqual(result['notes'], {'to': '.frontlights/issues/101/notes', 'moved': ['leitor.md', 'sonda.md'],
                                           'kept': []})
        self.assertIn('Notas de exploração movidas', result['message'])

    def test_a_note_already_there_is_never_overwritten(self):
        self.notes(sonda='nova')
        target = self.root / '.frontlights' / 'issues' / '101' / 'notes'
        target.mkdir(parents=True)
        (target / 'sonda.md').write_text('antiga', encoding='utf-8')
        plan, approved = self.standard()
        result = self.publish(plan, approved, FakeGitHub())
        self.assertEqual(result['notes']['kept'], ['sonda.md'])
        self.assertEqual((target / 'sonda.md').read_text(encoding='utf-8'), 'antiga')
        self.assertTrue((self.root / '.frontlights' / 'notes' / 'sonda.md').is_file())

    def test_without_notes_nothing_changes_and_a_dry_run_never_moves(self):
        plan, approved = self.standard()
        self.assertIsNone(self.publish(plan, approved, FakeGitHub())['notes'])
        source = self.notes(sonda='mapa')
        plan, approved = self.standard()
        self.publish(plan, approved, FakeGitHub(), dry_run=True)
        self.assertTrue((source / 'sonda.md').is_file())


class CommandLineTests(PublishCase):
    def test_the_entry_point_refuses_without_approval_in_json(self):
        plan, approved = self.standard(approve=False)
        done = subprocess.run([sys.executable, str(SCRIPTS / 'frontlights.py'), 'publish-issue', '--plan', str(plan),
                               '--approved', str(approved), '--root', str(self.root), '--config', str(self.config)],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)['reason'], 'not_approved')


if __name__ == '__main__':
    unittest.main()
