"""Paralelismo em toda etapa: a skill lança ao mesmo tempo tudo o que não depende de outra coisa, um subagente
por parte, e só espera aprovação, `Depende de`, arquivo ou recurso compartilhado; as slices de uma issue continuam
em ordem, a sessão coordenadora é uma só e o relato de um subagente é conferido antes de virar evidência.

Seam: o texto de `SKILL.md`, `references/development.md`, `references/grilling.md`, `references/issues.md`,
`README.md`, `docs/protocol.md`, `docs/security.md`, `docs/acceptance.md`, `evals/runbook.md` e `evals/fan-out.md`.
É regra da skill, não barreira: nenhum script muda.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return ''
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


class FanOutRuleTests(unittest.TestCase):
    def test_the_rule_holds_in_every_stage(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        # redesenho, issue 3: a regra virou o item `- **Fan out.**` de "Rules in every stage", em palavras novas
        rules = flat(skilltext.rule('Fan out'))
        for phrase in ('**Fan out.**', 'Each stage launches its independent pieces at once',
                       'one subagent each, in one message', 'two tool calls stay inline',
                       'Wait only for a real dependency', 'an approval not given', '`Depende de`',
                       'a file two pieces would edit', 'a shared resource', 'a shared test run',
                       'This session is the only coordinator', 'it alone asks, approves, writes GitHub, merges',
                       'Each brief follows `references/worker.md`', 'a worker returns at most 20 lines',
                       'its report is a claim until this session reads the diff and reruns the measured commands'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        # redesenho, issue 5: o brief tem casa única, references/worker.md
        worker = flat(read('skills', 'frontlights', 'references', 'worker.md'))
        for phrase in ('## Brief shape', 'At most 20 lines', 'A worker never calls `AskUserQuestion`, edits outside its paths, '
                       'writes GitHub', 'or widens the scope', "Workers share the codebase and must preserve others' changes",
                       'only one worker edits a worktree at a time', '## The report is a claim'):
            with self.subTest(file='worker.md', phrase=phrase):
                self.assertIn(phrase, worker)
        self.assertLess(skill.index('**Fan out.**'), skill.index('## Stages'))
        # redesenho, issue 3: o teto de issues, o trabalho em volta da slice aberta, o "um de cada vez" e o limite
        # de capacidade saíram do SKILL.md e vivem em development.md, "Dispatch and ownership"
        dispatch = flat(section(read('skills', 'frontlights', 'references', 'development.md'), 'Dispatch and ownership'))
        for phrase in ('all eligible non-conflicting issues up to the ceiling', 'the agents around them do not wait',
                       'runs one at a time', 'report the capacity limitation', 'Do not silently serialize'):
            with self.subTest(file='development', phrase=phrase):
                self.assertIn(phrase, dispatch)

    def test_slices_stay_in_order_while_the_work_around_them_fans_out(self):
        # redesenho, issue 3: a etapa 6 do SKILL.md só aponta para "Slices in order"; o paralelismo das slices
        # independentes vive em development.md
        stage6 = flat(skilltext.stage(6))
        self.assertIn('slices in order, one issue branch, one worktree per slice', stage6)
        self.assertIn('("Slices in order";', stage6)
        self.assertNotIn('slice parallelism only between issues', stage6)
        development = read('skills', 'frontlights', 'references', 'development.md')
        slices = flat(section(development, 'Slices in order'))
        self.assertIn('in dependency order: independent slices run at once', slices)
        self.assertIn('Slices run in parallel inside an issue and between issues', slices)
        dispatch = flat(section(development, 'Dispatch and ownership'))
        for phrase in ('all launched in one message', 'each with a brief by `references/worker.md`',
                       "A worker's report is a claim", '**Fan out inside an issue.**',
                       'dispatch in the same message read-only workers', 'runs one at a time',
                       'the reviewer is never the implementer', 'one implementer per open slice',
                       "Only one worker edits a slice's worktree at a time", 'the readers edit nothing'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, dispatch)

    def test_the_stage_references_fan_the_reading_out(self):
        grilling = flat(read('skills', 'frontlights', 'references', 'grilling.md'))
        self.assertIn('one read-only subagent per area the change touches', grilling)
        self.assertIn('the interview itself stays in this session', grilling)
        issues = flat(read('skills', 'frontlights', 'references', 'issues.md'))
        self.assertIn('one read-only subagent per layer, or per screen for the trace', issues)
        self.assertIn('the table and the cut stay in this session', issues)

    def test_the_documents_in_portuguese_say_the_same(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        for phrase in ('**Paralelismo.**', 'um subagente por parte', 'lançados numa única mensagem',
                       'slices independentes ao mesmo tempo, cada uma na própria worktree', 'recurso compartilhado',
                       'registra o limite de capacidade', 'A sessão coordenadora é uma só',
                       'afirmação, não evidência', 'o revisor nunca é o autor'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertNotIn('slices em paralelo só entre issues', protocol)
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('## Subagentes', 'um subagente trabalha sob as mesmas permissões nativas da sessão que o lançou',
                       'nunca para um agente que a execute por ela',
                       'continuam valendo para cada agente', 'antes de virar evidência'):
            with self.subTest(file='security', phrase=phrase):
                self.assertIn(phrase, security)
        readme = flat(read('README.md'))
        for phrase in ('**Paralelismo máximo.**', 'em todo projeto', 'tantos subagentes quantas forem as partes',
                       'CAs independentes ao mesmo tempo, cada uma na própria worktree', 'sessão coordenadora, que é uma só',
                       'conferido antes de virar evidência'):
            with self.subTest(file='README', phrase=phrase):
                self.assertIn(phrase, readme)
        self.assertIn('CAs independentes em paralelo dentro da issue e entre issues', readme)
        self.assertNotIn('slices em paralelo só entre issues', readme)

    def test_acceptance_runbook_and_eval_track_it(self):
        self.assertIn('| 25. Paralelismo em toda etapa | Pendente |', flat(read('docs', 'acceptance.md')))
        runbook = flat(read('evals', 'runbook.md'))
        self.assertIn('25. Fan-out in every stage (`evals/fan-out.md`).', runbook)
        self.assertLess(runbook.index('24. Summary period by instant'), runbook.index('25. Fan-out in every stage'))
        self.assertTrue((ROOT / 'evals' / 'fan-out.md').is_file())
        case = flat(read('evals', 'fan-out.md'))
        for phrase in ('launched in one message', 'run one after the other', 'never edit the worktree at the same time',
                       'a different agent from the implementer', 'Reject:', 'a second coordinator'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, case)


if __name__ == '__main__':
    unittest.main()
