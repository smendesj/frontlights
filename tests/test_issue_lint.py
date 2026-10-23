"""Etapa 5 por comando, S3 (redesenho, issue 7): `frontlights.py render-criteria` imprime as caixas de uma issue do
plano para o corpo, e `frontlights.py issue-lint` recusa um corpo com texto de instrução do modelo ou marcador
`<...>` sem preencher (também os corpos locais que uma triagem diária propõe, por `--body`); o `publish-issue` passa
todo corpo por ele antes de publicar.

Seams: `frontlights.render_criteria`, `frontlights.issue_lint`, `frontlights.publish_issue` e as entradas da CLI. O
`gh` é simulado: estes testes não homologam o GitHub real. Marcadores genéricos (OWNER/REPOSITORY).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
SCRIPTS = SKILL / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import frontlights  # noqa: E402

REPO = 'OWNER/REPOSITORY'
FILLED = ('# Salvar uma observação\n\n## Problema\n\nHoje nada fica salvo (pedido de 20/10/2026).\n\n'
          '## Critérios de aceitação\n\nAchado não corrigido no PR: `- [ ] Pendência (achado da revisão): <resultado '
          'observável>`, nunca numa seção à parte.\n\n- [ ] S1. Salvar e ver depois de recarregar\n'
          '  - Roteiro: conta 1 · abrir e salvar\n    → antes: nada fica; depois: o texto fica\n\n'
          '<details><summary>Detalhe</summary>\n\nVeja <https://example.com/x> ou escreva a <dev@example.com>.<br/>\n'
          '</details>\n\n<!-- <comentário> -->\n\n```text\n<saída do comando>\n```\n')


def run(*args):
    done = subprocess.run([sys.executable, str(SCRIPTS / 'frontlights.py'), *args], capture_output=True, text=True,
                          encoding='utf-8')
    return done.returncode, json.loads(done.stdout or done.stderr)


class LintTests(unittest.TestCase):
    def test_the_old_template_is_refused_for_its_instructions_and_placeholders(self):
        findings = frontlights.lint_body((SKILL / 'templates' / 'issue.md').read_text(encoding='utf-8'))
        self.assertIn('placeholder', {f['kind'] for f in findings})
        self.assertIn('<Um resultado observável>', [f['text'] for f in findings])
        self.assertEqual(next(f for f in findings if f['text'] == '<Um resultado observável>')['line'], 1)

    def test_a_filled_body_is_clean(self):
        self.assertEqual(frontlights.lint_body(FILLED), [])

    def test_each_instruction_sentence_is_found_even_across_lines(self):
        for phrase in frontlights.INSTRUCTION_PHRASES:
            with self.subTest(phrase=phrase):
                words = phrase.split()
                body = FILLED + '\n' + ' '.join(words[:3]) + '\n' + ' '.join(words[3:]) + '\n'
                self.assertEqual([f['kind'] for f in frontlights.lint_body(body)], ['instruction'])

    def test_an_unfilled_placeholder_outside_code_is_found(self):
        findings = frontlights.lint_body(FILLED + '| Tela | tratada | #<filha> | |\n- Toca o frontend: <sim | não>\n')
        self.assertEqual([f['text'] for f in findings], ['<filha>', '<sim | não>'])

    def test_local_bodies_and_the_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            clean, dirty = Path(folder) / 'a.md', Path(folder) / 'b.md'
            clean.write_bytes(FILLED.encode('utf-8'))
            dirty.write_bytes((FILLED + '\n<o que dá para demonstrar>\n').encode('utf-8'))
            code, out = run('issue-lint', '--body', str(clean), '--root', folder)
            self.assertEqual((code, out['ok']), (0, True))
            code, out = run('issue-lint', '--body', str(clean), '--body', str(dirty), '--root', folder)
            self.assertEqual(code, 1)
            self.assertEqual([len(b['findings']) for b in out['bodies']], [0, 1])

    def test_an_issue_is_read_with_gh(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps({'repository': REPO}), encoding='utf-8')
            calls = []

            def gh(argv):
                calls.append(argv)
                return 0, json.dumps({'body': FILLED + '<persona>\n'})
            result = frontlights.issue_lint('12', (), str(config), gh)
        self.assertEqual(calls, [['issue', 'view', '12', '--repo', REPO, '--json', 'body']])
        self.assertEqual(result['exitCode'], 1)


class RenderTests(unittest.TestCase):
    def test_the_boxes_of_the_example_plan(self):
        result = frontlights.render_criteria(SKILL / 'examples' / 'plan.json', '3')
        self.assertEqual(result['boxes'], 2)
        lines = result['markdown'].splitlines()
        self.assertEqual(lines[:6], ['- [ ] S1. Editar uma observação salva',
                                     '  - Entrega: Editar o texto salvo, recarregar e ver o texto novo',
                                     '  - Seams: PUT /observations/{id}; o formulário de observação',
                                     '  - Camadas: Tela, API, Banco e migração, Testes', '  - Depende de: nenhuma',
                                     '  - Roteiro: conta 1 · abrir uma observação salva, mudar o texto, salvar e recarregar'])
        self.assertTrue(lines[6].startswith('    → antes: a observação salva não tem como ser editada; depois: '))
        self.assertIn('  - Depende de: S1', lines)
        self.assertEqual(frontlights.lint_body(result['markdown']), [])

    def test_an_issue_without_slices_renders_its_acceptance(self):
        result = frontlights.render_criteria(SKILL / 'examples' / 'plan.json', '2')
        self.assertEqual(result['markdown'], '- [ ] O arquivo baixado traz o nome e o dono atuais do projeto\n')

    def test_the_command_line_writes_the_markdown_and_refuses_an_unknown_issue(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'caixas.md'
            code, result = run('render-criteria', '--plan', str(SKILL / 'examples' / 'plan.json'), '--issue', '1',
                               '--out', str(out))
            self.assertEqual(code, 0)
            self.assertEqual(out.read_bytes().decode('utf-8'), result['markdown'])
            code, result = run('render-criteria', '--plan', str(SKILL / 'examples' / 'plan.json'), '--issue', '99')
            self.assertEqual((code, result['reason']), (1, 'issue_missing'))

    def test_the_example_plan_names_the_board_fields(self):
        plan = json.loads((SKILL / 'examples' / 'plan.json').read_text(encoding='utf-8'))
        top = [i for i in plan['issues'] if 'parent' not in i]
        self.assertTrue(all('project_fields' in i for i in top))


class PublishLintTests(unittest.TestCase):
    def test_publish_issue_refuses_a_body_with_instructions_before_any_write(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import test_publish_issue as tp  # noqa: PLC0415
        case = tp.PublishCase('setUp')
        case.setUp()
        try:
            plan, approved = case.standard(approve=False)
            body = tp.BODY_A + '\n- Toca o frontend: <sim | não>\n'
            (case.root / '.frontlights' / 'a.md').write_bytes(body.encode('utf-8'))
            approved.write_bytes((approved.read_text(encoding='utf-8') + '\n' + body).encode('utf-8'))
            case.approve(approved)
            gh = tp.FakeGitHub()
            result = case.publish(plan, approved, gh)
            self.assertEqual(result['reason'], 'lint_failed')
            self.assertEqual(result['findings'][0]['text'], '<sim | não>')
            self.assertEqual(gh.calls, [])
        finally:
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
