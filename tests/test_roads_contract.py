"""`docs/roads-contract.md` descreve o que o Frontlights realmente faz: os conjuntos fechados e a regra de versão
do texto batem com o código, e o documento só traz marcadores genéricos (repositório público).

Seam: o texto do contrato contra as constantes e as funções públicas de `roads` e `progress_report`.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'frontlights' / 'scripts'))
import progress_report as pr
import roads as rs

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

    def test_the_version_is_one_and_the_table_covers_the_route_the_skill_reads(self):
        self.assertEqual(rs.STATE_SCHEMA_VERSION, 1)
        self.assertIn('versão deste contrato é **1**', DOC)
        self.assertEqual(table_row('GET roadmap-state')[1], 'obrigatório')
        for route in ('GET pending-changes', 'POST sync-board', 'POST ack'):
            with self.subTest(route=route), self.assertRaises(AssertionError):
                table_row(route)

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
        for phrase in ('Compare instantes, nunca textos',
                       '`concluido`, `em_validacao`, `em_andamento`, `bloqueado`, `proximo`', 'conjunto fechado',
                       'o dia do **último instante** da janela', 'other_draft_pending'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_the_contract_describes_the_sprints_as_weeks_by_date(self):
        flat = ' '.join(DOC.split())
        for phrase in ('`laneId` e `sprintId` são os dois `sprint-DD-MM-AAAA`', 'na ordem de `startDate`, nunca pelo texto do id',
                       'aceita as duas formas', 'nunca as duas na mesma resposta', 'uma semana pode vir com `items: []`',
                       'Decisão de 15/10/2026 (exceção à regra de quebra)', 'continua 1'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

    def test_the_contract_says_the_skill_stopped_calling_the_queue_routes(self):
        flat = ' '.join(DOC.split())
        for phrase in ('Rotas que o Frontlights deixou de chamar (19/10/2026)',
                       'não chama `POST sync-board`, `GET pending-changes` nem `POST ack`',
                       'é decisão do dono do RoadS', 'são ignorados'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)
        for gone in ('### `POST sync-board`', '### `GET pending-changes', '### `POST ack`', '"Acima do limite de N:"',
                     'markCompleted', 'Semana sem mudança não ganha arquivo'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, flat)

    def test_the_contract_records_what_the_service_does_with_the_project_status(self):
        flat = ' '.join(DOC.split())
        for phrase in ('Só o Status do Project conta', 'não é lido** para itens de sprint', 'Item de sprint concluído fica',
                       'quando a **rotação** das sprints o retira', 'Grupos são diferentes',
                       'nunca do GitHub ao vivo', 'até 30 s depois de outra',
                       'Fechar uma issue só muda o RoadS quando o fluxo "Item closed" do quadro leva o cartão a Done'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, flat)

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
