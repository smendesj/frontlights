"""Um título trocado no GitHub chega como `modify`: a entrada se acha pelo número da issue que a mudança traz.

Seams: `roadmap_sync.board_result` (o resumo do `sync-board` que o usuário lê, com o `retitled` opcional),
`roadmap_sync.normalise_changes` (a mudança que a sessão recebe) e o texto de `references/roadmap-sync.md`, `README.md`
e `docs/roads-contract.md`. Como o resto da sincronização, a regra de achar a entrada é da sessão (o helper só entrega a
mudança, com o título novo em `item.title`): ela só se prova pelo texto.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import roadmap_sync as rs

ISSUE = 'https://github.com/OWNER/REPOSITORY/issues/12'


def flat(*parts):
    return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())


def answer(**roadmap):
    return rs.board_result(json.dumps({'schemaVersion': 1, 'ok': True, 'ran': True, 'syncedAt': '2026-10-06T12:00:00Z',
                                       'roadmap': {'added': 2, 'removed': 1, 'issuesCreated': 0, **roadmap}}))


def titled(item=None, **extra):
    change = {'id': 'c1', 'action': 'modify', 'itemId': 'item-1', 'createdAt': '2026-10-06T11:00:00Z',
              'item': {'title': 'Exportar o relatório de amostras em CSV', 'githubIssueUrl': ISSUE},
              'payload': {'title': 'Exportar o relatório de amostras em CSV', 'reason': 'title follows the issue on GitHub'}, **extra}
    if item is not None:
        change['item'] = item
    return rs.normalise_changes({'schemaVersion': 1, 'asOf': '2026-10-06T12:00:00Z', 'changes': [change]})[0]


class BoardSummaryTests(unittest.TestCase):
    def test_retitled_is_reported_when_the_service_sends_it(self):
        result = answer(retitled=19)
        self.assertEqual((result['ok'], result['added'], result['removed'], result['issuesCreated'], result['retitled']),
                         (True, 2, 1, 0, 19))

    def test_zero_is_a_count_too(self):
        self.assertEqual(answer(retitled=0)['retitled'], 0)

    def test_without_it_nothing_changes_for_the_summary_the_plugin_already_gave(self):
        result = answer()
        self.assertNotIn('retitled', result)
        self.assertEqual({k: result[k] for k in ('ok', 'ran', 'added', 'removed', 'issuesCreated')},
                         {'ok': True, 'ran': True, 'added': 2, 'removed': 1, 'issuesCreated': 0})

    def test_a_value_that_is_not_a_count_is_reported_as_unknown_never_as_a_number(self):
        for value in (-1, '3', True, None, 2.5, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(answer(retitled=value)['retitled'])

    def test_other_additive_fields_the_service_sends_are_ignored(self):
        result = answer(retitled=1, sprint={'pulled': 1, 'released': 2, 'written': 0, 'wouldWrite': 3, 'failed': 0, 'stuck': 0})
        self.assertNotIn('sprint', result)
        self.assertEqual(result['retitled'], 1)

    def test_a_failed_board_sync_is_still_reported_as_before(self):
        result = rs.board_result(json.dumps({'schemaVersion': 1, 'ok': False, 'reason': 'no_access', 'message': 'texto curto'}))
        self.assertEqual((result['ok'], result['ran'], result['reason']), (False, False, 'no_access'))
        self.assertNotIn('retitled', result)


class TitleOnlyModifyTests(unittest.TestCase):
    def test_the_change_carries_the_new_title_the_reason_and_the_issue_the_session_finds_the_entry_by(self):
        change = titled()
        self.assertEqual((change['action'], change['itemId'], change['knownAction'], change['needsIssue']),
                         ('modify', 'item-1', True, False))
        self.assertEqual((change['item']['title'], change['item']['githubIssueUrl']), ('Exportar o relatório de amostras em CSV', ISSUE))
        self.assertIn('title follows the issue on GitHub', change['payload'])

    def test_an_item_without_an_issue_still_needs_one_and_keeps_the_lane_the_lookup_by_title_uses(self):
        change = titled(item={'title': 'Exportar o relatório de amostras em CSV', 'lane': 'Atual'}, payload={'title': 'Exportar o relatório de amostras em CSV'})
        self.assertEqual((change['needsIssue'], change['item']['githubIssueUrl'], change['item']['lane']), (True, None, 'Atual'))


class RuleTextTests(unittest.TestCase):
    def setUp(self):
        self.reference = flat('skills', 'frontlights', 'references', 'roadmap-sync.md')

    def test_the_entry_is_found_by_the_issue_number_and_never_by_the_title_alone(self):
        for phrase in ('Find the existing entry of a `modify`, `move_lane`, `remove`, `completed` or `add` (when the file already has one;',
                       'by the issue number the change carries (the `#N` of `item.githubIssueUrl`, or its URL, as the files cite it)',
                       'tell them apart by the repository in the URL (and `item.produto`), and ask if that does not settle it',
                       'never by title alone, because the title in the files may be older than the one in the change',
                       "A `modify` that only changes `item.title`", 'replaces the old title with the new one in the entry',
                       'in the roadmap and in the file of every sprint in `change.sprintTargets`, and touches nothing else (the change\'s marker aside)',
                       'the old title is not in the change, so read it from the entry found by number'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_a_change_without_a_number_is_found_by_title_and_lane_and_an_unclear_lookup_is_asked(self):
        for phrase in ('A change without an issue number (a `remove` whose payload has no `github_issue_url`, an item with no issue yet)',
                       'or the `modify` that only adds the link (the files cannot cite it yet) is found by title and by the lane the item was in '
                       '(`payload.from_lane_id` for a `move_lane`, `payload.lane_id` for a `remove`, `item.lane` otherwise;',
                       'Ask with `AskUserQuestion` when a `modify` or `move_lane` finds no entry in the roadmap and when an `add` finds an entry of its `#N`. '
                       'Ask also when any change this rule finds (a `modify`, `move_lane`, `remove`, `completed` or `add`) finds more than one',
                       "Ask once, listing every such change and proposing the closest candidate in the item's lane (for an `add`, the entry of its `#N` wherever it is), and never open a second entry on your own (for an `add`, only when the user chooses it)",
                       'when the lane is missing, by title alone, asking if more than one entry matches'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_the_lookup_says_where_to_look_and_which_misses_are_expected(self):
        for phrase in ('Look in the roadmap and, for a `modify`, a `move_lane`, a `remove`, a `completed` and an `add`, in the file of each sprint in `change.sprintTargets`',
                       'a `modify` with no entry in a sprint file that exists leaves that file as it is and says so',
                       'A missing entry is expected, and handled by the rules above, for a `move_lane` into a sprint where the item has no entry yet (its entry is written in the sprint it joined)',
                       'for a sprint file that does not exist yet',
                       'for a `remove` (recorded in the roadmap even for an item never written) and for a `completed` (its line goes into a new entry)',
                       'A row of a table and the section of the same item are one entry; a mention inside another entry is not'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_the_renamed_count_is_the_plans_and_may_differ_from_the_board_syncs(self):
        for phrase in ('Tell the user how many title-only `modify` changes the plan holds',
                       "it may differ from `syncBoard.retitled`, which counts only what this run's board sync renamed",
                       'how many are title-only renames, and which items are `outOfLimit`',
                       'and `retitled` itens renomeados when `retitled` is present and above zero'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_the_older_rules_the_new_one_has_to_live_with_are_still_there(self):
        for phrase in ('a modify whose only news is `item.githubIssueUrl` adds the issue link to the entry, it never duplicates it',
                       '`remove` (`itemMissing` true, identified by `itemId` and `item.title`)',
                       'the file already has an entry for the item, add the line to it; do not open a second entry'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_the_readme_and_the_contract_say_the_same(self):
        readme = flat('README.md')
        for phrase in ('e quantos foram renomeados, quando o RoadS informa', 'O Frontlights acha a entrada pelo número da issue que a mudança traz',
                       'e não pelo título', 'e diz quantos `modify` de título o plano tem', 'Sem número (um item ainda sem issue, por exemplo), acha pelo título e pela lane',
                       'Se um `modify` ou `move_lane` não achar entrada no roadmap, se um `add` achar entrada do mesmo `#N`, ou se qualquer '
                       'mudança achar mais de uma, ele pergunta antes de abrir uma segunda'):
            with self.subTest(doc='README', phrase=phrase):
                self.assertIn(phrase, readme)
        contract = flat('docs', 'roads-contract.md')
        for phrase in ('`retitled` (inteiro: itens cujo título acompanhou uma issue renomeada no GitHub', 'O Frontlights relata `retitled` e ignora `sprint`',
                       'e, opcionalmente, `error`', 'a entrada se acha pelo número da issue e não pelo título',
                       'um `move_lane` com `payload.origin` `project`', 'nunca volta ao Project',
                       'A fila de mudanças (`fetch`, `apply` e `ack`) não escreve no Project, e o Frontlights só escreve nele em passos próprios que o usuário aprova, como o `gaps` e o fechamento',
                       'o RoadS tirou do Dashboard os blocos "Em paralelo" e "Próxima semana" e o card "Resumo"'):
            with self.subTest(doc='contract', phrase=phrase):
                self.assertIn(phrase, contract)

    def test_the_contract_no_longer_says_the_plugin_never_writes_to_the_project(self):
        self.assertNotIn('O Frontlights continua sem escrever no Project', flat('docs', 'roads-contract.md'))

    def test_the_stale_dashboard_counters_are_gone_from_the_contract(self):
        contract = flat('docs', 'roads-contract.md')
        self.assertNotIn('"Concluídas na sprint X de Y"', contract)
        self.assertNotIn('"Em paralelo" (em desenvolvimento fora da sprint atual) e "Próxima sprint"', contract)


if __name__ == '__main__':
    unittest.main()
