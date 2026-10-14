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
        for phrase in ('**Standing authorization.**', 'permanently and for every project',
                       'there is no concurrency question, no stacking question and no implementation authorization question',
                       'announce in one short block', '"autorização permanente (docs/security.md)"',
                       'an `expires_at` at most 24 hours ahead',
                       'It never covers the questions of the work itself'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('ask the concurrency question and one bounded implementation authorization', text)

    def test_the_covered_operations_are_the_same_everywhere(self):
        skill = stage(6)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('running migrations on the local development database',
                       "creating and removing test data through the product's own endpoints",
                       'ticking acceptance criteria with evidence', 'pushing the work branches'):
            for name, text in (('SKILL.md', skill), ('development.md', development)):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase, text)
        for name in (('skills', 'frontlights', 'docs', 'protocol.md'), ('skills', 'frontlights', 'docs', 'security.md'), ('README.md',)):
            text = flat(*name)
            for phrase in ('rodar a migration' if name == ('README.md',) else 'migrations no banco de desenvolvimento local',
                           'endpoints do produto', 'PRs rascunho'):
                with self.subTest(file=name[-1], phrase=phrase):
                    self.assertIn(phrase, text)

    def test_every_denied_operation_is_listed_in_every_document(self):
        english = ('merging a pull request', 'closing an issue', 'changing the board',
                   'deploying or publishing to production', 'editing a migration already registered',
                   'writing the base branch or a protected branch', 'turning on a setting, key or flag in production')
        portuguese = ('merge de PR', 'fechar issue', 'mexer no quadro', 'produção', 'migration já registrada',
                      'branch base ou protegida', 'chave ou flag em produção')
        skill = stage(6)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in english:
            for name, text in (('SKILL.md', skill), ('development.md', development)):
                with self.subTest(file=name, phrase=phrase):
                    self.assertIn(phrase.casefold(), text.casefold())
        for name in (('skills', 'frontlights', 'docs', 'protocol.md'), ('skills', 'frontlights', 'docs', 'security.md'), ('README.md',)):
            text = flat(*name).casefold()
            for phrase in portuguese:
                with self.subTest(file=name[-1], phrase=phrase):
                    self.assertIn(phrase.casefold(), text)

    def test_a_denied_operation_runs_only_after_its_own_yes(self):
        skill = stage(6)
        for phrase in ('**Denied operations are asked one at a time.**', 'with "Sim" first and "Não" second',
                       'naming the exact operation and the exact command', 'run it only after "Sim"',
                       'never extend a "Sim" to another operation, another PR or a later moment',
                       '"Não", silence or any other answer leaves it undone'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)
        development = flat('skills', 'frontlights', 'references', 'development.md')
        self.assertIn('## Standing authorization and the denied operations', read('skills', 'frontlights', 'references', 'development.md'))
        self.assertIn('A "Sim" covers that one operation, never another one, another PR or a later moment', development)

    def test_the_approvals_with_their_own_stage_keep_them(self):
        self.assertIn("The approvals that have their own stage (the issue's text, issue plan and publication, closeout, cleanup, roadmap and summary) keep them",
                      stage(6))
        self.assertIn('fechamento, limpeza, roadmap e resumo', flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('da limpeza, do roadmap e do resumo', flat('README.md'))

    def test_the_merge_is_offered_when_the_pr_is_ready(self):
        development = flat('skills', 'frontlights', 'references', 'development.md')
        for phrase in ('**Offer the merge when the PR is ready.**', '"Mesclar a PR #<n> em <base>?"',
                       '"Sim, mesclar" first and "Não, aguardar o merge" second', '`gh pr merge <n> --merge`',
                       "never `--admin`, `--auto` or `--delete-branch`", 'On "Não", the wait goes on unchanged'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, development)
        self.assertIn('never merge without the user\'s "Sim"', stage(6))
        self.assertIn('"Mesclar a PR #<n> em <base>?"', flat('README.md'))
        options = re.search(r'with "([^"]+)" first and "([^"]+)" second; one question per PR', development)
        self.assertIsNotNone(options)
        for label in options.groups():
            with self.subTest(label=label):
                self.assertLessEqual(len(label.split()), 5)

    def test_the_grant_lives_in_the_plugin_and_native_prompts_remain(self):
        security = flat('skills', 'frontlights', 'docs', 'security.md')
        for phrase in ('**Autorização permanente.**', 'não no `.frontlights/config.json`',
                       'um repositório clonado não consiga ligá-la nem ampliá-la',
                       'os pedidos de permissão nativos do Claude Code continuam valendo'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertIn("the host's own permission prompts still apply", stage(6))
        self.assertNotIn('standing', read('skills', 'frontlights', 'examples', 'config.json').casefold())

    def test_acceptance_and_runbook_track_it_as_pending(self):
        self.assertIn('| 23. Autorização permanente da etapa 6 e negados com "Sim" | Pendente |', flat('docs', 'acceptance.md'))
        self.assertIn('23. Standing authorization and slices in order.', flat('evals', 'runbook.md'))


if __name__ == '__main__':
    unittest.main()
