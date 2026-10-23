"""Etapa 5 por comando, S2 (redesenho, issue 7): `closeout.py capture` guarda o corpo byte a byte e `closeout.py append`
acrescenta linhas aprovadas sem editar o que está lá (--items depois do último item da seção de critérios, com a linha
de armadilha no mesmo lote; --spec as caixas do plano; --walkthrough as duas linhas do roteiro), relê e recusa
divergência.

Seams: `closeout.run('capture'|'append', ...)` e a entrada `closeout.py append`. O `gh` é simulado: estes testes não
homologam o GitHub real. Marcadores genéricos (OWNER/REPOSITORY).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import closeout  # noqa: E402
import roads as rs  # noqa: E402
import stamp  # noqa: E402
import _cli  # noqa: E402

REPO = 'OWNER/REPOSITORY'
BODY = ('# Uma issue\n\n## Critérios de aceitação\n\n- [x] S1. Salvar\n  - Entrega: salvar\n'
        '- [ ] S2. Editar\n  - Entrega: editar\n  - Depende de: S1\n\nSlice estacionada: último sub-item.\n\n'
        '## Camadas da fatia\n\n| Camada | Situação |\n')
ITEMS = '- [ ] Pendência (achado da revisão): o erro diz o campo. Evidência que fecha: teste do formulário\n'
PITFALL = '- 2026-10-23 · #12 · campo vazio salvo sem aviso · sonda: estados da tela\n'


class FakeGh:
    """`gh issue view --json body,state`, `gh issue edit --body-file`, and the account reads."""

    def __init__(self, body=BODY, state='OPEN', stored=None, login='OWNER-LOGIN'):
        self.body, self.state, self.stored, self.login = body, state, stored or (lambda text: text), login
        self.reads, self.edits, self.on_read = 0, [], None

    def __call__(self, argv):
        if argv == ['api', 'user']:
            return {'login': self.login}
        if argv[:2] == ['repo', 'view']:
            return {'nameWithOwner': REPO, 'viewerPermission': 'WRITE'}
        assert argv == ['issue', 'view', '12', '--repo', REPO, '--json', 'body,state'], argv
        self.reads += 1
        if self.on_read:
            self.on_read(self)
        return {'body': self.body, 'state': self.state}

    def edit(self, argv):
        assert argv[:6] == ['issue', 'edit', '12', '--repo', REPO, '--body-file'], argv
        self.edits.append(argv)
        self.body = self.stored(Path(argv[6]).read_bytes().decode('utf-8'))


class AppendCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / '.frontlights').mkdir()
        self.config = self.root / '.frontlights' / 'config.json'
        self.config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')

    def file(self, name, text, approve=True, answer='Aprovar o lote'):
        path = self.root / '.frontlights' / name
        path.write_bytes(text.encode('utf-8'))
        if approve:
            sha = stamp.run(stamp.build_parser().parse_args([str(path), '--root', str(self.root)]))['sha256']
            self.assertTrue(stamp.run(stamp.build_parser().parse_args(
                [str(path), '--root', str(self.root), '--approve', '--answer', answer, '--expect', sha]))['ok'])
        return path

    def append(self, gh, **options):
        account = options.pop('account', lambda data: _cli.gh_account(data, gh))
        return closeout.run('append', str(self.config), str(self.root), gh=gh, edit=gh.edit, issue='12',
                            account=account, **options)

    def pitfalls(self):
        path = self.root / '.frontlights' / 'pitfalls.md'
        return path.read_text(encoding='utf-8') if path.is_file() else None


class CaptureTests(AppendCase):
    def test_capture_keeps_the_bytes_of_a_crlf_body(self):
        gh = FakeGh(body=BODY.replace('\n', '\r\n'))
        result = closeout.run('capture', str(self.config), str(self.root), gh=gh, issue='12')
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(result['path']).read_bytes(), BODY.replace('\n', '\r\n').encode('utf-8'))
        self.assertTrue(Path(result['path']).name.startswith('body-before-'))
        self.assertEqual(result['criteria'], {'checked': 1, 'total': 2})


class ItemsTests(AppendCase):
    def test_the_item_goes_after_the_last_item_and_its_sub_items(self):
        gh = FakeGh()
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)))
        self.assertTrue(result['ok'], result)
        self.assertEqual(gh.body, BODY.replace('  - Depende de: S1\n', '  - Depende de: S1\n' + ITEMS))
        self.assertEqual(result['criteria'], {'before': {'checked': 1, 'total': 2}, 'after': {'checked': 1, 'total': 3}})
        self.assertEqual(len(gh.edits), 1)
        self.assertEqual(sorted(Path(p).name.split('-')[1] for p in result['files'].values()),
                         ['after', 'before', 'new', 'now'])

    def test_crlf_is_kept(self):
        gh = FakeGh(body=BODY.replace('\n', '\r\n'))
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)))
        self.assertTrue(result['ok'], result)
        self.assertIn('S1\r\n- [ ] Pendência', gh.body)
        self.assertNotIn('\n', gh.body.replace('\r\n', ''))

    def test_without_the_approval_nothing_is_read_or_written(self):
        gh = FakeGh()
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS, approve=False)))
        self.assertEqual(result['reason'], 'not_approved')
        self.assertEqual((gh.reads, gh.edits), (0, []))

    def test_a_closed_issue_or_one_without_the_section_is_refused(self):
        lote = str(self.file('lote-r1.md', ITEMS))
        closed = FakeGh(state='CLOSED')
        self.assertEqual(self.append(closed, items=lote)['reason'], 'issue_closed')
        bare = FakeGh(body='# Sem seção\n\nTexto.\n')
        self.assertEqual(self.append(bare, items=lote)['reason'], 'no_criteria_section')
        self.assertEqual(closed.edits + bare.edits, [])

    def test_an_edit_between_the_captures_stops_before_writing(self):
        gh = FakeGh()

        def someone_edits(fake):
            if fake.reads == 2:
                fake.body = BODY + 'linha de outra pessoa\n'
        gh.on_read = someone_edits
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)))
        self.assertEqual(result['reason'], 'diverged')
        self.assertEqual(gh.edits, [])

    def test_a_reread_that_is_not_the_written_body_is_a_divergence(self):
        gh = FakeGh(stored=lambda text: text + 'mudança no meio\n')
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)))
        self.assertEqual(result['reason'], 'diverged_after')
        self.assertIsNone(self.pitfalls())

    def test_a_wrong_account_writes_nothing(self):
        gh = FakeGh(login='OTHER')
        self.config.write_text(json.dumps({'repository': REPO, 'github': {'account': 'OWNER-LOGIN'}}), encoding='utf-8')
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)))
        self.assertEqual(result['reason'], 'account_mismatch')
        self.assertEqual(gh.edits, [])

    def test_an_items_file_with_a_ticked_box_or_prose_is_refused(self):
        for text in ('- [x] já marcada\n', 'Um parágrafo\n', '- [ ] uma\n\n- [ ] outra\n'):
            with self.subTest(text=text):
                gh = FakeGh()
                result = self.append(gh, items=str(self.file('lote-r1.md', text)))
                self.assertFalse(result['ok'])
                self.assertEqual(gh.edits, [])


class PitfallTests(AppendCase):
    def test_the_pitfall_line_is_written_after_the_checked_write(self):
        gh = FakeGh()
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)),
                             pitfall=str(self.file('armadilha-r1.md', PITFALL)))
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['pitfalls'], self.pitfalls()), (1, PITFALL))
        again = FakeGh()
        self.append(again, items=str(self.root / '.frontlights' / 'lote-r1.md'),
                    pitfall=str(self.root / '.frontlights' / 'armadilha-r1.md'))
        self.assertEqual(self.pitfalls(), PITFALL * 2)   # append-only

    def test_a_pitfall_approved_by_another_answer_is_refused(self):
        gh = FakeGh()
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)),
                             pitfall=str(self.file('armadilha-r1.md', PITFALL, answer='Outra resposta')))
        self.assertEqual(result['reason'], 'pitfall_not_in_batch')
        self.assertEqual(gh.edits, [])

    def test_a_pitfall_out_of_format_is_refused_before_any_write(self):
        gh = FakeGh()
        result = self.append(gh, items=str(self.file('lote-r1.md', ITEMS)),
                             pitfall=str(self.file('armadilha-r1.md', '- fato solto\n')))
        self.assertEqual(result['reason'], 'pitfall_format')
        self.assertEqual(gh.edits, [])


def plan(slices=True):
    issue = {'id': 12, 'url': f'https://github.com/{REPO}/issues/12', 'title': 'Uma issue', 'outcome': 'o',
             'tests': ['t'], 'ownership': ['src'], 'dependencies': [], 'non_goals': ['n'], 'risks': ['r'],
             'session_sized': True, 'status': 'ready'}
    if slices:
        walk = {'persona': 'conta 1', 'steps': 'abrir e salvar', 'before': 'nada salva', 'after': 'salva'}
        issue['slices'] = [{'id': 'S1', 'title': 'Salvar', 'delivers': 'salvar', 'seams': ['POST /x'],
                            'layers': ['Tela', 'API'], 'depends_on': [], 'walkthrough': walk},
                           {'id': 'S2', 'title': 'Editar', 'delivers': 'editar', 'seams': ['PUT /x'],
                            'layers': ['Tela'], 'depends_on': ['S1'], 'walkthrough': dict(walk, after='editada')}]
    return json.dumps({'repository': REPO, 'issues': [issue]}, ensure_ascii=False)


class SpecAndWalkthroughTests(AppendCase):
    def test_spec_appends_the_boxes_of_an_adopted_issue(self):
        gh = FakeGh(body='# Uma issue\n\nTexto que já estava.\n')
        result = self.append(gh, spec=str(self.file('plan-r1.json', plan())))
        self.assertTrue(result['ok'], result)
        self.assertTrue(gh.body.startswith('# Uma issue\n\nTexto que já estava.\n\n## Critérios de aceitação\n\n'))
        self.assertIn('- [ ] S2. Editar\n  - Entrega: editar\n  - Seams: PUT /x\n  - Camadas: Tela\n'
                      '  - Depende de: S1\n  - Roteiro: conta 1 · abrir e salvar\n    → antes: nada salva; depois: editada',
                      gh.body)
        self.assertEqual(result['criteria']['after']['total'], 2)

    def test_spec_refuses_an_issue_that_already_has_boxes(self):
        gh = FakeGh()
        self.assertEqual(self.append(gh, spec=str(self.file('plan-r1.json', plan())))['reason'], 'boxes_present')

    def test_walkthrough_adds_the_two_lines_under_each_open_box_only(self):
        gh = FakeGh()
        result = self.append(gh, walkthrough=str(self.file('plan-r1.json', plan())))
        self.assertTrue(result['ok'], result)
        self.assertEqual(gh.body, BODY.replace('  - Depende de: S1\n', '  - Depende de: S1\n  - Roteiro: conta 1 · '
                                               'abrir e salvar\n    → antes: nada salva; depois: editada\n'))
        self.assertEqual(result['criteria']['after']['total'], 2)


class CommandLineTests(AppendCase):
    def test_append_and_capture_are_in_the_help(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'closeout.py'), '--help'], capture_output=True,
                              text=True, encoding='utf-8')
        for verb in ('capture', 'append'):
            self.assertIn(verb, done.stdout)


if __name__ == '__main__':
    unittest.main()
