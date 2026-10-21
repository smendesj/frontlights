"""A prévia no fluxo (issue 34, S3): sobe logo depois da aprovação do plano, antes da primeira CA, abre numa aba do
Claude in Chrome, é refeita a cada CA pronta pelo `serve preview refresh` e só para a pedido; a aba é do usuário e fica
fora da regra da janela descartável; a ordem fixa do teste assistido deixa de terminar no stop da prévia.

Seam: o texto de `SKILL.md` (etapas 5 e 6), `references/development.md`, `references/browser-testing.md`,
`docs/protocol.md`, `docs/security.md` e `README.md`. É regra da skill, não barreira: nenhum script abre a aba.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def between(text, start, end):
    return flat(text.split(start)[1].split(end)[0])


class PreviewInTheFlowTests(unittest.TestCase):
    """Issue 34, S3."""

    def test_stage_five_hands_the_preview_to_the_start_of_stage_six(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage5 = between(skill, '## 5.', '## 6.')
        self.assertIn('the preview comes up right after the plan is approved, before the first slice', stage5)

    def test_stage_six_brings_the_preview_up_refreshes_it_and_stops_it_only_on_request(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage6 = between(skill, '## 6.', '## 7.')
        for phrase in ('2. **The preview** (same section)', 'a `preview` block', 'before the first slice',
                       'refreshed after each slice is merged into the branch of its issue'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage6)
        self.assertLess(stage6.index('**Sync**'), stage6.index('**The preview**'))
        self.assertLess(stage6.index('**The preview**'), stage6.index('**Slices in order**'))
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
                       'stops only when the user asks'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, start)
        slices = between(development, '## Slices in order', '## Dispatch and ownership')
        self.assertIn('then `serve preview refresh` with the branches of the issues in progress', slices)
        self.assertLess(slices.index('the slice branch is merged into the branch of the issue'),
                        slices.index('then `serve preview refresh`'))

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
        for phrase in ('a prévia sobe logo depois da aprovação do plano, antes da primeira CA',
                       'numa aba do Claude in Chrome', 'é refeita a cada CA pronta', 'só para a pedido',
                       '`serve stop` da issue (nunca o da prévia)', 'preview/registry.json'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('A aba da prévia é do usuário', 'fica fora dessa regra',
                       'o teste assistido nunca usa a prévia nem as portas dela'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        readme = flat(read('README.md'))
        self.assertIn('**Prévia ao vivo.**', readme)
        self.assertIn('numa aba do Claude in Chrome', readme)
        self.assertRegex(readme, r'prévia ao vivo[^→]*→ desenvolvimento orientado a testes')
        runbook = read('evals', 'runbook.md')
        self.assertIn('30. Live preview (issue 34).', runbook)
        self.assertLess(runbook.index('29. Pull request template'), runbook.index('30. Live preview (issue 34).'))
        self.assertIn('| 30. Prévia ao vivo (issue 34) |', read('docs', 'acceptance.md'))

    def test_the_branches_given_to_the_refresh_come_from_the_records_and_the_preview(self):
        """Revisão da issue 34 (M3): a lista de --branch vem dos registros de autorização e do que a prévia já tem."""
        development = between(read('skills', 'frontlights', 'references', 'development.md'),
                              '## The start of stage 6', '## Slices in order')
        for name, text in (('development.md', development),):
            for phrase in ('`.frontlights/authorization*.json`', 'whose issue is not closed', 'slice branches',
                           'the `merged` of `serve preview status`', '`git merge-base --is-ancestor <branch> main`',
                           "never takes another issue's work in progress out of the preview",
                           'only those that exist locally (`git rev-parse --verify --quiet refs/heads/<branch>`)'):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)
            for stale in ('none yet', 'none at the very start'):
                with self.subTest(file=name, stale=stale):
                    self.assertNotIn(stale, text)



class PreviewPortRulesTextTests(unittest.TestCase):
    """5ª revisão da issue 34: as listas de recusas da prévia citam o {port} no argv e no cwd dos processos."""

    def test_every_list_of_preview_refusals_names_the_port_placeholder_of_a_process(self):
        sources = {
            'serve.py': (read('skills', 'frontlights', 'scripts', 'serve.py'), 'no `{port}` in the `argv` or the `cwd` of a process'),
            'browser-testing.md': (read('skills', 'frontlights', 'references', 'browser-testing.md'),
                                   'no `{port}` in the `argv` or the `cwd` of its processes'),
            'README.md': (read('README.md'), '`{port}` no argv ou no `cwd` dos processos dela'),
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
                       'ANTES and DEPOIS run one after the other in that instance',
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


if __name__ == '__main__':
    unittest.main()
