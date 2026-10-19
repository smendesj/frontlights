"""Autorização permanente da etapa 6 e operações negadas com "Sim": o texto da skill, da referência de
desenvolvimento, do README e dos docs diz o mesmo.

Seam: o texto de `SKILL.md`, `references/development.md`, `README.md`, `docs/protocol.md`, `docs/security.md`,
`docs/acceptance.md` e `evals/runbook.md`. É regra da skill, não barreira: nenhum script muda, e o `authorize`
continua com os próprios testes (`test_runtime.py`).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(*parts):
    return ' '.join(read(*parts).split())


def stage(number):
    text = read('skills', 'frontlights', 'SKILL.md')
    return ' '.join(text.split(f'## {number}.')[1].split(f'## {number + 1}.')[0].split())


class StandingAuthorizationTests(unittest.TestCase):
    def test_stage_six_opens_without_the_authorization_question(self):
        text = stage(6)
        for phrase in ('Stage 6 opens without a question, under the **standing authorization** the user gave '
                       'permanently and for every project',
                       '(development.md, "Standing authorization and the denied operations")',
                       'announces the run in one short block, records the charter',
                       'the questions of the work itself (the watched run, failures, the findings batch, a new product '
                       'decision) are still asked'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('ask the concurrency question and one bounded implementation authorization', text)

    def test_development_holds_the_charter(self):
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('stage 6 opens without a question: there is no concurrency question, no stacking question and '
                       'no implementation authorization question',
                       "announces it in one short block, in the user's language",
                       '`"autorização permanente (docs/security.md)"` in `approval_reference`',
                       'an `expires_at` at most 24 hours ahead', 'Its `monitoring` block is `mode: "local"`',
                       '`phone_connected: true` only when the user states, unprompted in this session',
                       'The questions of the work itself (the watched run, failures, the findings batch, a new product '
                       'decision) are still asked',
                       '`approved_by`, `confirmed_by` and `monitoring.confirmed_by`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)

    def test_the_covered_operations_are_the_same_everywhere(self):
        skill = stage(6)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('running migrations on the local development database',
                       "creating and removing test data through the product's own endpoints",
                       'ticking acceptance criteria with evidence',
                       'the branch of the issue into the local main once its three gates are green'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        self.assertIn('The merges the run makes on its own are the covered merges of that section', skill)
        for name in (('skills', 'frontlights', 'docs', 'protocol.md'), ('skills', 'frontlights', 'docs', 'security.md')):
            with self.subTest(file=name[-1]):
                self.assertIn('"Standing authorization and the denied operations"', flat(*name))

    def test_every_denied_operation_is_listed_in_every_document(self):
        english = ('merging a pull request', 'closing an issue', 'changing the board',
                   'deploying or publishing to production', 'editing a migration already registered',
                   'writing the remote main (`origin/main`, the base branch on GitHub) or a protected branch',
                   'turning on a setting, key or flag in production')
        skill = stage(6)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        self.assertIn('An operation on the denied list (development.md, "Standing authorization and the denied '
                      'operations")', skill)
        for phrase in english:
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase.casefold(), development.casefold())
        readme = flat('README.md')
        for phrase in ('Cada operação negada (merge de PR e fechar issue, entre outras) vira uma pergunta própria com '
                       '"Sim" e "Não" e o comando exato',
                       '#standing-authorization-and-the-denied-operations'):
            with self.subTest(file='README.md', phrase=phrase):
                self.assertIn(phrase, readme)

    def test_a_denied_operation_runs_only_after_its_own_yes(self):
        skill = stage(6)
        for phrase in ('**Denied operations are asked one at a time.**',
                       'which names the exact operation and the exact command', 'each "Sim" covers that one operation'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('"Sim" first and "Não" second', 'naming the exact operation and the exact command',
                       'Run it only after "Sim"', '"Não", silence or any other answer leaves it undone'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, development)
        self.assertIn('## Standing authorization and the denied operations', read('skills', 'frontlights', 'references', 'development.md'))
        self.assertIn('A "Sim" covers that one operation; another operation, another PR or a later moment gets its own '
                      'question', development)

    def test_the_approvals_with_their_own_stage_keep_them(self):
        self.assertIn("The approvals that have their own stage (the issue's text, issue plan and publication, closeout, cleanup, issue gaps and summary) keep them",
                      flat('skills', 'frontlights', 'references', 'development.md'))
        self.assertIn('da limpeza, das issues do RoadS e do resumo', flat('README.md'))

    def test_the_merge_is_offered_when_the_pr_is_ready(self):
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('**Offer the merge when the PR is ready.**', '"Mesclar a PR #<n> em <base>?"',
                       '"Sim, mesclar" first and "Não, aguardar o merge" second', '`gh pr merge <n> --merge`',
                       "never `--admin`, `--auto` or `--delete-branch`", 'On "Não", the wait goes on unchanged'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)
        self.assertIn('ele pergunta se pode mesclá-la; só o seu "Sim" faz o merge', flat('README.md'))
        options = re.search(r'with "([^"]+)" first and "([^"]+)" second; one question per PR', development)
        self.assertIsNotNone(options)
        for label in options.groups():
            with self.subTest(label=label):
                self.assertLessEqual(len(label.split()), 5)

    def test_the_grant_lives_in_the_plugin_and_native_prompts_remain(self):
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('## Autorização permanente', 'não no `.frontlights/config.json`',
                       'um repositório clonado não consiga ligá-la nem ampliá-la',
                       'os pedidos de permissão nativos do Claude Code continuam valendo'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn("the host's own permission prompts still apply", flat('skills', 'frontlights', 'SKILL.md'))
        self.assertNotIn('standing', read('skills', 'frontlights', 'examples', 'config.json').casefold())

    def test_acceptance_and_runbook_track_it_as_pending(self):
        self.assertIn('| 23. Autorização permanente da etapa 6 e negados com "Sim" | Pendente |', flat('docs', 'acceptance.md'))
        self.assertIn('23. Standing authorization and slices in order.', flat('evals', 'runbook.md'))


if __name__ == '__main__':
    unittest.main()
