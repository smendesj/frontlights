"""`docs/roads-contract.md` descreve o que o Frontlights realmente faz: os conjuntos fechados e a regra de versão
do texto batem com o código, e o documento só traz marcadores genéricos (repositório público).

Seam: o texto do contrato contra as constantes e as funções públicas de `roadmap_sync` e `progress_report`.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import progress_report as pr
import roadmap_sync as rs

DOC = (ROOT / 'docs' / 'roads-contract.md').read_text(encoding='utf-8')


def table_row(label):
    """The cells of the table row that starts with `label` (backticks stripped)."""
    for line in DOC.splitlines():
        cells = [cell.strip().replace('`', '') for cell in line.strip().strip('|').split('|')]
        if line.startswith('|') and cells and cells[0].replace('`', '').startswith(label):
            return cells
    raise AssertionError(f'a linha {label!r} não está no contrato')


class ClosedSetsTests(unittest.TestCase):
    def test_item_statuses_match_the_code_and_an_unknown_one_is_refused(self):
        cells = table_row('status de item')
        self.assertEqual(set(re.findall(r'[a-z_]+', cells[1])), set(rs.ITEM_STATUSES))
        self.assertIn('recusado', cells[2])

    def test_actions_match_the_code_and_an_unknown_one_is_tolerated(self):
        cells = table_row('action de uma mudança')
        self.assertEqual(set(re.findall(r'[a-z_]+', cells[1])), set(rs.ACTIONS))
        self.assertIn('tolerado', cells[2])
        change = {'id': 'c1', 'action': 'archive', 'item': {'title': 'T'}}
        self.assertFalse(rs.normalise_changes({'changes': [change]})[0]['knownAction'])

    def test_the_version_is_one_and_the_table_covers_every_route_that_carries_it(self):
        self.assertEqual(rs.STATE_SCHEMA_VERSION, 1)
        self.assertIn('versão deste contrato é **1**', DOC)
        for route, expected in (('GET roadmap-state', 'obrigatório'), ('GET pending-changes', 'opcional'),
                                ('POST sync-board', 'opcional'), ('POST ack', 'opcional')):
            with self.subTest(route=route):
                self.assertEqual(table_row(route)[1], expected)

    def test_the_documented_version_rules_are_the_ones_the_code_applies(self):
        for payload in ({'changes': [], 'schemaVersion': 1}, {'changes': []}):
            self.assertEqual(rs.normalise_changes(payload), [])
        with self.assertRaisesRegex(rs.Refusal, 'schemaVersion'):
            rs.normalise_changes({'changes': [], 'schemaVersion': 2})
        self.assertEqual(rs.board_result('{"ok": true, "ran": true, "schemaVersion": 1}')['ok'], True)
        self.assertEqual(rs.board_result('{"ok": true, "ran": true, "schemaVersion": 2}')['reason'], 'invalid_response')

    def test_only_proximo_does_not_need_a_print(self):
        facts = {'entries': [{'issue': 1, 'status': 'proximo'}, {'issue': 2, 'status': 'novo-valor'}]}
        missing = pr.deliveries_without_prints(facts, {'entries': []}, [])
        self.assertEqual(missing, [2])
        self.assertIn('só `proximo` dispensa print', DOC)


class DocumentShapeTests(unittest.TestCase):
    def test_the_user_agent_is_the_one_the_skill_sends(self):
        self.assertRegex(rs.user_agent(), r'^frontlights-roadmap-sync/[0-9a-f]{12}$')
        self.assertIn('frontlights-roadmap-sync/<commit da skill>', DOC)
        self.assertIn('não prova', DOC)

    def test_the_week_folder_rule_is_the_one_the_code_applies(self):
        import datetime as dt
        self.assertEqual(pr.presentation_monday(dt.date(2026, 10, 7)), dt.date(2026, 10, 12))
        self.assertEqual(pr.presentation_monday(dt.date(2026, 10, 4)), dt.date(2026, 10, 5))
        for phrase in ('weekMeeting', 'apenas a janela devolvida', '<dd_MM do último dia do período>',
                       'nunca dividem arquivo'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, DOC)

    def test_the_break_rule_names_the_order_and_forbids_two_versions(self):
        for phrase in ('abra uma issue neste repositório', 'depois** que o Frontlights que a entende estiver publicado',
                       'não serve\nduas versões ao mesmo tempo'.replace('\n', ' ')):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, ' '.join(DOC.split()))

    def test_the_contract_states_what_the_service_really_sends(self):
        flat = ' '.join(DOC.split())
        for phrase in ('`from_lane_id` (a de origem)', '`lane_id` (a lane de destino)', 'Compare instantes, nunca textos',
                       '`concluido`, `em_validacao`, `em_andamento`, `bloqueado`, `proximo`', 'conjunto fechado',
                       'o dia do **último instante** da janela', 'unsupported_schema_version',
                       'O Frontlights envia `"schemaVersion": 1` no corpo de `POST ack`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_the_contract_describes_the_sprints_as_weeks_by_date(self):
        flat = ' '.join(DOC.split())
        for phrase in ('`laneId` e `sprintId` são os dois `sprint-DD-MM-AAAA`', 'na ordem de `startDate`, nunca pelo texto do id',
                       'aceita as duas formas', 'nunca as duas na mesma resposta', 'pode vir semana com `items: []`',
                       'Semana sem mudança não ganha arquivo', 'só a semana que termina mexe',
                       'itens de semanas futuras não recebem `move_lane` de virada', 'issue closed before its sprint',
                       'a ordem que o scrum master arrastou', '"Acima do limite de N:"',
                       'Decisão de 15/10/2026 (exceção à regra de quebra)', 'continua 1',
                       'toda semana citada por uma mudança ainda sem ack', 'só quando há excedente',
                       'o `from_lane_id` (de `move_lane`)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)
        for gone in ('`laneId` é posicional', 'Item acima do limite fica fora da sprint', 'passam para a nova sprint atual',
                     'a próxima e a terceira sprint existem só no RoadS', '"sprintId": "sprint-2026-01-05", "laneId": "proxima"'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, flat)
        acceptance = ' '.join((ROOT / 'docs' / 'acceptance.md').read_text(encoding='utf-8').split())
        self.assertIn('As semanas identificadas pela data (issue 39) só têm cobertura simulada', acceptance)

    def test_the_contract_records_what_the_service_does_with_the_project_status(self):
        flat = ' '.join(DOC.split())
        for phrase in ('Só o Status do Project conta', 'não é lido** para itens de sprint', 'Item de sprint concluído fica',
                       'Só a **rotação** das sprints o remove', 'sprint ended, issue done', 'Grupos são diferentes',
                       'nunca do GitHub ao vivo', 'até 30 s depois de outra',
                       'Fechar uma issue sem mover o cartão para Done não muda nada no RoadS',
                       'o Frontlights a registra como "concluída", com a data da sincronização', '`roadmapSync.markCompleted`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_the_completed_marks_are_described_where_users_and_maintainers_look(self):
        for name in ('README.md', 'skills/frontlights/docs/protocol.md', 'skills/frontlights/docs/security.md'):
            with self.subTest(name=name):
                self.assertIn('markCompleted', ' '.join((ROOT / name).read_text(encoding='utf-8').split()))
        for name in ('README.md', 'skills/frontlights/docs/protocol.md'):
            with self.subTest(name=name):
                self.assertIn('not_needed', ' '.join((ROOT / name).read_text(encoding='utf-8').split()))
        reference = ' '.join((ROOT / 'skills' / 'frontlights' / 'references' / 'roadmap-sync.md').read_text(encoding='utf-8').split())
        for phrase in ('completed', 'markCompleted'):
            self.assertIn(phrase, reference)

    def test_the_move_lane_keys_in_the_contract_are_the_ones_the_code_reads(self):
        change = {'id': 'm1', 'action': 'move_lane', 'item': {'title': 'T'},
                  'payload': {'from_lane_id': 'origem', 'lane_id': 'destino', 'reason': 'x', 'title': 'T'}}
        self.assertEqual(rs.normalise_changes({'changes': [change]})[0]['_move'], ('origem', 'destino'))

    def test_only_generic_placeholders_appear(self):
        hosts = set(re.findall(r'https?://([^/\s"`)]+)', DOC))
        self.assertEqual(hosts, {'roads.example.test'})
        self.assertNotRegex(DOC, r'[A-Za-z]:[\\/]+(Users|Software)\b|/(home|Users)/[A-Za-z]')
        self.assertNotRegex(DOC, r'(?i)bearer [a-z0-9]{12,}')

    def test_the_contract_is_linked_from_the_readme_and_the_protocol(self):
        for name in ('README.md', 'skills/frontlights/docs/protocol.md'):
            with self.subTest(name=name):
                self.assertIn('roads-contract.md', (ROOT / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
