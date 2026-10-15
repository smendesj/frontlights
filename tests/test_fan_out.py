"""Paralelismo em toda etapa: a skill lança ao mesmo tempo tudo o que não depende de outra coisa, um subagente
por parte, e só espera aprovação, `Depende de`, arquivo ou recurso compartilhado; as slices de uma issue continuam
em ordem, a sessão coordenadora é uma só e o relato de um subagente é conferido antes de virar evidência.

Seam: o texto de `SKILL.md`, `references/development.md`, `references/grilling.md`, `references/issues.md`,
`README.md`, `docs/protocol.md`, `docs/security.md`, `docs/acceptance.md`, `evals/runbook.md` e `evals/fan-out.md`.
É regra da skill, não barreira: nenhum script muda.
"""
import re
import unittest
from pathlib import Path

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
        rules = flat(section(skill, 'Rules that hold in every stage'))
        for phrase in ('**Fan out.**', 'one subagent per piece and as many as there are pieces',
                       'launched in one message', 'the read-only helpers of stages 0 to 2',
                       'one subagent per area or layer', 'the highest safe number of independent issues',
                       'the legwork around the open slice', 'Waiting is for a real dependency only',
                       'an approval not yet given', '`Depende de`', 'a file two pieces would both edit',
                       'a shared resource', 'run one at a time', 'A piece of a couple of tool calls stays inline',
                       'report the capacity limit', 'This session is the only coordinator',
                       'it alone asks (`AskUserQuestion`)', 'Each brief is bounded',
                       "A worker's report is a claim"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        self.assertLess(skill.index('**Fan out.**'), skill.index('## 0. Update check'))

    def test_slices_stay_in_order_while_the_work_around_them_fans_out(self):
        skill = read('skills', 'frontlights', 'SKILL.md')
        stage6 = flat(section(skill, '6. Bounded development'))
        self.assertIn('independent slices (no `Depende de` between them and no file in common) run at once', stage6)
        self.assertIn('the legwork around each open slice fans out', stage6)
        self.assertNotIn('slice parallelism only between issues', stage6)
        development = read('skills', 'frontlights', 'references', 'development.md')
        slices = flat(section(development, 'Slices in order'))
        self.assertIn('in dependency order: independent slices run at once', slices)
        self.assertIn('Slices run in parallel inside an issue and between issues', slices)
        dispatch = flat(section(development, 'Dispatch and ownership'))
        for phrase in ('all launched in one message', 'A worker never calls `AskUserQuestion`',
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
                       'nunca serializa em silêncio', 'A sessão coordenadora é uma só',
                       'afirmação, não evidência', 'o revisor nunca é o autor'):
            with self.subTest(file='protocol', phrase=phrase):
                self.assertIn(phrase, protocol)
        self.assertIn('slices independentes em paralelo dentro da issue e entre issues', protocol)
        self.assertNotIn('slices em paralelo só entre issues', protocol)
        security = flat(read('skills', 'frontlights', 'docs', 'security.md'))
        for phrase in ('**Subagentes.**', 'não cria autoridade', 'nunca para um agente que a execute por ela',
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
