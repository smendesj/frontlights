"""A prévia no fluxo (issue 34, S3): sobe logo depois da aprovação do plano, antes da primeira CA, abre numa aba do
Claude in Chrome, é refeita a cada CA pronta pelo `serve preview refresh` e só para a pedido; a aba é do usuário e fica
fora da regra da janela descartável; a ordem fixa do teste assistido deixa de terminar no stop da prévia.

Seam: o texto de `SKILL.md` (etapas 5 e 6), `references/development.md`, `references/browser-testing.md`,
`docs/protocol.md`, `docs/security.md` e `README.md`. É regra da skill, não barreira: nenhum script abre a aba.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctext
import skilltext


read, flat = doctext.read, doctext.flat  # redesenho, issue 10: o helper único


def between(text, start, end):
    return flat(text.split(start)[1].split(end)[0])


class PreviewInTheFlowTests(unittest.TestCase):
    """Issue 34, S3."""

    def test_stage_five_hands_the_preview_to_the_start_of_stage_six(self):
        # redesenho, issue 3: a etapa 5 diz que a prévia sobe agora e aponta a seção; "antes da primeira slice"
        # vive em development.md, "The start of stage 6" (fixado em test_development_says_when_the_preview_is_refreshed).
        stage5 = flat(skilltext.stage(5))
        self.assertIn('With a `preview` block the preview comes up now (`references/development.md`, "The start of '
                      'stage 6")', stage5)

    def test_stage_six_brings_the_preview_up_refreshes_it_and_stops_it_only_on_request(self):
        # redesenho, issue 3: a lista de passos da etapa 6 virou orações com o ponteiro da seção; quando a prévia
        # sobe e é atualizada vive em development.md ("The start of stage 6" e "Slices in order", abaixo).
        stage6 = flat(skilltext.stage(6))
        self.assertIn('`homolog sync` and the preview ("The start of stage 6")', stage6)
        self.assertLess(stage6.index('`homolog sync`'), stage6.index('the preview'))
        self.assertLess(stage6.index('the preview'), stage6.index('slices in order'))
        development = read('skills', 'frontlights', 'references', 'development.md')
        start = between(development, '## The start of stage 6', '## Slices in order')
        for phrase in ('`serve preview refresh`', 'a tab of Claude in Chrome', 'stops only when the user asks',
                       'The tab belongs to the user', 'outside the rule of the disposable window',
                       'never uses the preview nor its ports', 'without the block, nothing of this runs'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, start)

    def test_development_says_when_the_preview_is_refreshed(self):
        development = read('skills', 'frontlights', 'references', 'development.md')
        start = between(development, '## The start of stage 6', '## Slices in order')
        for phrase in ('**The preview.**', 'before the first slice', 'a tab of Claude in Chrome',
                       'stops only when the user asks', 'without the block, nothing of this runs'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, start)
        # redesenho, issue 5: `slice merge` refaz a prévia depois do merge da slice (`frontlights.refresh_preview`).
        slices = between(development, '## Slices in order', '## Dispatch and ownership')
        self.assertIn('then the slice is merged into the branch of the issue and the preview refreshed', slices)

    def test_the_watched_run_order_never_stops_the_preview_and_its_tab_is_the_users(self):
        reference = read('skills', 'frontlights', 'references', 'browser-testing.md')
        order = flat(reference.split('Run only what is on, in this order:')[1].split('The commands below read')[0])
        self.assertIn('`serve stop` of the issue (never `preview stop`: the preview stays up)', order)
        window = flat(reference.split('**Visible window.**')[1].split('**The whole screen, always.**')[0])
        self.assertIn('never the user\'s personal one', window)
        self.assertIn('The tab of the preview is the user\'s', window)
        self.assertIn('never on the ports of the preview', window)

    def test_the_docs_and_the_readme_follow(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        # redesenho, issue 10: o protocolo era cópia de development.md sobre a prévia; agora aponta para lá
        doctext.assertPointsTo(self, protocol, 'references/development.md', 'The start of stage 6')
        for phrase in ('`serve stop` da issue (nunca o da prévia)', 'preview/registry.json'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('A aba da prévia é do usuário', 'fica fora dessa regra',
                       'o teste assistido nunca usa a prévia nem as portas dela'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        runbook = read('evals', 'runbook.md')
        self.assertIn('30. Live preview (issue 34).', runbook)
        self.assertLess(runbook.index('29. Pull request template'), runbook.index('30. Live preview (issue 34).'))
        self.assertIn('| 30. Prévia ao vivo (issue 34) |', read('docs', 'acceptance.md'))

    def test_the_branches_given_to_the_refresh_come_from_the_records_and_the_preview(self):
        """Revisão da issue 34 (M3): a lista de --branch vem dos registros de autorização e do que a prévia já tem."""
        development = between(read('skills', 'frontlights', 'references', 'development.md'),
                              '## The start of stage 6', '## Slices in order')
        # redesenho, issue 5: a lista vem de `frontlights.preview_branches`, a mesma que `slice merge` usa.
        self.assertIn('(the list `slice merge` builds)', development)
        self.assertIn("never takes another issue's work in progress out of the preview", development)
        source = ' '.join(read('skills', 'frontlights', 'scripts', 'frontlights.py').split())
        for phrase in ('the branch of every issue (and work without an issue) of the authorization records, plus the '
                       "`merged` of the preview's record, minus each one the local main already holds",
                       'and only those that exist locally', 'every issue in progress stays in the preview'):
            with self.subTest(file='frontlights.py', phrase=phrase):
                self.assertIn(phrase, source)
        for name, text in (('development.md', development),):
            for stale in ('none yet', 'none at the very start'):
                with self.subTest(file=name, stale=stale):
                    self.assertNotIn(stale, text)



class PreviewPortRulesTextTests(unittest.TestCase):
    """5ª revisão da issue 34: as listas de recusas da prévia citam o {port} no argv e no cwd dos processos."""

    def test_every_list_of_preview_refusals_names_the_port_placeholder_of_a_process(self):
        sources = {
            'serve.py': (read('skills', 'frontlights', 'scripts', 'serve.py'), 'no `{port}` in the `argv` or the `cwd` of a process'),
            # redesenho, issues 5 e 12: a recusa vive no --help do serve, que a aplica
            'serve.py': (read('skills', 'frontlights', 'scripts', 'serve.py'),
                         'there is no `{port}` in the `argv` or the `cwd` of a process'),
            'security.md': (read('skills', 'frontlights', 'docs', 'security.md'), 'sem `{port}` no argv nem no `cwd`'),
        }
        for name, (text, phrase) in sources.items():
            with self.subTest(file=name):
                self.assertIn(phrase, flat(text))

class IsolatedWatchedRunTests(unittest.TestCase):
    """Issue 34, S4, e issue 69, S2: o teste assistido numa instância isolada, no banco de desenvolvimento local."""

    def test_the_reference_runs_both_passes_in_the_isolated_instance(self):
        reference = read('skills', 'frontlights', 'references', 'browser-testing.md')
        watched = flat(reference.split('## Watched run: before and after')[1].split('## Test data the run creates')[0])
        rule = watched.split('**The isolated instance.**')[1].split('- **A strip on every page.**')[0]
        for phrase in ('`browserTest.isolated`', 'the local development database itself',
                       'which is the homologation database, never a copy',
                       'ANTES and DEPOIS never run at once in that instance',
                       'never on the ports of the preview', '"Test data the run creates"',
                       'without a shell', 'stops only what it started', 'Without the block'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        for field in ('copyDatabase', 'dropDatabase'):
            with self.subTest(field=field):
                self.assertNotIn(field, reference)
        self.assertLess(watched.index('**Two passes, same scenario and same account.**'),
                        watched.index('**The isolated instance.**'))

    def test_security_says_the_watched_run_uses_the_local_development_database(self):
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        rule = security.split('**Instância isolada do teste assistido (`browserTest.isolated`):**')[1].split('- **')[0]
        for phrase in ('no próprio banco de desenvolvimento local, que é o de homologação, nunca numa cópia',
                       'nunca produção', 'sem shell', 'nunca nas portas da prévia', 'o `inspect` recusa',
                       'o bloco que ainda declare `copyDatabase` ou `dropDatabase`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        self.assertNotIn('descartada no fim pelo `dropDatabase`', security)

    def test_the_watched_run_uses_only_chrome_driven_by_playwright(self):
        """Issue 69, S2: nunca o navegador embutido do Claude nem o Claude in Chrome, que só abre a aba da prévia."""
        reference = flat(read('skills', 'frontlights', 'references', 'browser-testing.md'))
        self.assertNotIn("Chrome or Claude's browser", reference)
        self.assertNotIn("the session's browser on screen", reference)
        browser = reference.split('## Browser')[1].split('## Watched run')[0]
        window = reference.split('**Visible window.**')[1].split('- **The whole screen, always.**')[0]
        for where, text in (('Browser', browser), ('Visible window', window)):
            for phrase in ('Chrome driven by Playwright', "never Claude's built-in browser nor Claude in Chrome"):
                with self.subTest(section=where, phrase=phrase):
                    self.assertIn(phrase, text)
        self.assertIn("which only opens the user's preview tab", browser)



class FreeTestWindowTests(unittest.TestCase):
    """Issue 69, S3: a janela do teste livre na main local, regra de `references/browser-testing.md`."""

    def setUp(self):
        self.text = read('skills', 'frontlights', 'references', 'browser-testing.md')
        self.free = between(self.text, '## The free test window', '## Cross-account permissions')

    def test_the_strip_text_lives_once_in_the_free_test_rule(self):
        references = ROOT / 'skills' / 'frontlights' / 'references'
        counts = {path.name: path.read_text(encoding='utf-8').count('MAIN LOCAL: teste livre')
                  for path in sorted(references.glob('*.md'))}
        self.assertEqual({name: count for name, count in counts.items() if count}, {'browser-testing.md': 1})
        self.assertIn('"MAIN LOCAL: teste livre"', self.free)

    def test_the_window_is_chrome_by_playwright_on_the_whole_screen_logged_in_with_account_one(self):
        for phrase in ('Chrome driven by Playwright', "never Claude's built-in browser nor Claude in Chrome",
                       '`headless: false`', '`viewport: null`', "a disposable profile, never the user's personal one",
                       'account 1 of `browserTest.users`', 'typed only into the login form',
                       'a fixed strip pinned to the top edge across the full width, by an init script',
                       'the order is in `development.md`, "The free test on the local main"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.free)

    def test_the_product_runs_from_the_main_worktree_only_for_the_free_test(self):
        for phrase in ('`python "${CLAUDE_SKILL_DIR}/scripts/serve.py" start --config <config> --root <main worktree> '
                       '--issue <n>`',
                       'on the local development database (the homologation one)',
                       'This is the only exception to the rule that a watched run never serves from the main '
                       'worktree, and it holds only for the free test'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.free)
        passes = between(self.text, '- **Two passes, same scenario and same account.**', '- **The isolated instance.**')
        self.assertIn('A watched run never serves from the main worktree (the free test is the only exception, '
                      '"The free test window")', passes)
        self.assertEqual(flat(self.text).count('the only exception to the rule that a watched run never serves from '
                                               'the main worktree'), 1)

    def test_the_holder_has_no_time_limit_and_its_exit_wakes_the_session(self):
        for phrase in ('The holder has no time limit', 'the 5 minutes of the watched run do not apply',
                       "it exits only on the browser's `disconnected` event",
                       'its exit wakes the session, which runs `serve stop` for what it started',
                       '`python "${CLAUDE_SKILL_DIR}/scripts/serve.py" stop --config <config> --root <main worktree> '
                       '--issue <n>`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.free)
        pace = between(self.text, '- **Pace.**', '- **Window closed, next step.**')
        self.assertIn('The holder of the free test has no time limit ("The free test window", below)', pace)

    def test_the_user_leads_and_the_session_helps_on_request(self):
        for phrase in ('The user leads: no script, no ANTES/DEPOIS and no print is required',
                       'the session helps on request', 'reads the screen, the console and the network and explains',
                       'clicks or types only when the user asks', 'never writes to the database on its own'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.free)

    def test_a_fix_request_is_the_one_case_the_session_edits_code_in_the_free_test(self):
        """Issue 69, S4: um pedido de correção é o único caso em que a sessão edita código com a janela aberta."""
        for phrase in ('A fix the user asks for is the one case in which the session edits code while the window is '
                       'open', '`development.md`, "The free test on the local main"',
                       'even then it never writes to the database on its own'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.free)

    def test_without_a_screen_there_is_no_window(self):
        """Issue 69, S5: sem tela, o teste livre não abre janela; a regra é a de `development.md`."""
        self.assertIn('Without a screen there is no window: the free test happens in the terminal (`development.md`, '
                      '"The free test on the local main")', flat(self.free))

if __name__ == '__main__':
    unittest.main()
