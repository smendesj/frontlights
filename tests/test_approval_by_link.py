"""Issue 61, S2: a aprovação de um documento, lista ou tabela é por link e carimbo, não pelo texto colado na conversa.

A regra vive num lugar só, "Show before approval" do `SKILL.md`: o documento vai para um arquivo em `.frontlights/`,
enviado pela ferramenta de envio do ambiente e com link clicável; `frontlights.py stamp` dá a revisão, o sha256 de 12
caracteres e os bytes, que a pergunta nomeia; ao lado do link, no máximo cinco linhas (r1: as seções e as decisões;
de r2 em diante: o diff real entre as revisões guardadas); `--approve` grava a resposta literal e `--check` roda antes
da escrita coberta. Comandos (o SQL dos dados de teste e as operações negadas) seguem por inteiro na pergunta. Os
outros textos apontam para a regra em vez de pedir o texto integral na conversa.

Seam: o texto dos arquivos, achatado pelos espaços (`flat`), como nos outros testes de texto.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / 'skills' / 'frontlights'
POINTER = 'Show before approval'

# frases antigas que pediam o documento inteiro na conversa
OLD = ('shown in full', 'show the plan in full', 'Show the complete revision', 'full text in the conversation',
       'complete text in the conversation', 'in full and in the user', 'as much as fits', 'the full body',
       'Print the whole draft text in the conversation', 'na íntegra', 'texto integral', 'texto completo',
       'mostrados por inteiro', 'o texto se repete no `preview`', 'corpo completo', 'corpos mostrados')

POINTER_FILES = (
    ('skills', 'frontlights', 'references', 'issue.md'),
    ('skills', 'frontlights', 'references', 'issues.md'),
    ('skills', 'frontlights', 'references', 'closeout.md'),
    ('skills', 'frontlights', 'references', 'progress-report.md'),
    ('skills', 'frontlights', 'docs', 'protocol.md'),
    ('skills', 'frontlights', 'docs', 'security.md'),
    ('README.md',),
    ('evals', 'runbook.md'),
    ('evals', 'family-conversion.md'),
    ('evals', 'merge-wait-and-cleanup.md'),
    ('evals', 'leftovers-as-criteria.md'),
    ('evals', 'vertical-slices.md'),
)


def flat(*parts):
    return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())


def skill():
    return flat('skills', 'frontlights', 'SKILL.md')


def rule():
    return ' '.join(skilltext.rule('Show before approval').split())


class TheRuleTests(unittest.TestCase):
    # redesenho, issue 3: a regra virou um item de "Rules in every stage", mais curto; a enumeração dos documentos
    # cobertos virou "A document, list or table" e a das escritas cobertas, "the write it covers"
    def test_the_document_goes_to_a_file_sent_and_linked(self):
        text = rule()
        for phrase in ('A document, list or table', 'never as pasted text',
                       'approved as a stamped file under `.frontlights/`', 'host file card, which reaches the phone',
                       'clickable link'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('pasting the full text into the conversation', text)

    def test_the_file_is_stamped_and_the_question_names_the_stamp(self):
        text = rule()
        for phrase in ('frontlights.py stamp <file> --revision rN', 'the revision',
                       'a 12-character sha256 and the bytes', 'for the question', '"Aprova r2 · 6c29ce70c2c7?"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_at_most_five_lines_next_to_the_link_and_the_real_diff_from_r2(self):
        text = rule()
        for phrase in ("at most five lines, also in the approve option's `preview`", 'for r1 the sections and their decisions',
                       'the real diff from the kept revision', 'git diff --no-index --stat', 'changed lines',
                       'never a summary written by the session',
                       'Keep the previous revision as `<name>-r<N>.<ext>`'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_approval_is_recorded_and_checked_before_the_write(self):
        text = rule()
        for phrase in ('--approve --answer "<literal>"', '--stage N', 'right before the write it covers',
                       '--check', 'exit 1: show the new stamp and what changed, ask again'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertLess(text.index('--approve'), text.index('--check'))

    def test_the_scope_keeps_commands_in_full_and_the_cleanup_asks_nothing(self):
        text = rule()
        for phrase in ('Commands (test-data SQL, denied operations) go in full inside the question',
                       'the text (stage 4) and the GitHub write (stage 5) are separate'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        # redesenho, issue 3: "the cleanup of merged work asks nothing" mudou para a etapa 7
        self.assertIn('The cleanup of the merged work (closeout.md, step 5) runs first, without a question',
                      ' '.join(skilltext.stage(7).split()))

    def test_a_summary_or_a_path_is_still_not_approval(self):
        text = rule()
        for phrase in ('The approval is of the file with that stamp; a summary or a path is not',
                       'each revision is a new one',
                       'Without the stamp or a link, record the approval as pending and stop'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('shown in full in this session', text)
        self.assertNotIn('the host cannot send files', text)
        # redesenho, issue 3: "a decision that is not in the stamped file is not approved" vive na etapa 4
        self.assertIn('a decision written into a local revision that is not in the stamped file is not approved',
                      flat('skills', 'frontlights', 'references', 'issue.md'))

    def test_the_file_card_is_sent_when_the_host_has_the_tool(self):
        # redesenho, issue 3: o passo 1 numerado virou "Send the file (host file card, …, and a clickable link)"
        self.assertIn('Send the file (host file card, which reaches the phone, and a clickable link)', rule())

    def test_the_approve_passes_the_stamp_shown_in_the_question(self):
        text = rule()
        self.assertIn('--approve --answer "<literal>" --expect <stamp>', text)
        # redesenho, issue 3: a recusa do --expect e o "pergunte de novo" moraram no script
        script = ' '.join((SKILL_DIR / 'scripts' / 'stamp.py').read_text(encoding='utf-8').split())
        for phrase in ('--expect with the stamp shown in the question', 'nothing is written and it exits 1',
                       'the file changed since the question: ask the approval again'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, script)

    def test_the_rule_lives_once_in_skill_md(self):
        files = sorted(SKILL_DIR.rglob('*.md')) + [ROOT / 'README.md', ROOT / 'CLAUDE.md'] + sorted(
            (ROOT / 'evals').glob('*.md'))
        for fragment in ('never a summary written by the session', '--approve --answer "<literal>"'):
            with self.subTest(fragment=fragment):
                homes = [path.relative_to(ROOT).as_posix() for path in files
                         if fragment in ' '.join(path.read_text(encoding='utf-8').split())]
                self.assertEqual(homes, ['skills/frontlights/SKILL.md'])


class TheRecordsTreeTests(unittest.TestCase):
    def tree(self):
        text = flat('skills', 'frontlights', 'docs', 'protocol.md')
        return text.split('## Registros', 1)[1].split('```', 2)[1]

    def test_the_tree_lists_the_approvals_file(self):
        tree = self.tree()
        self.assertIn('approvals.json', tree)
        for phrase in ('frontlights.py stamp --approve', 'path', 'revision', 'sha256 de 12 caracteres', 'bytes',
                       'answer literal', 'stage', '-03:00'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, tree.split('approvals.json', 1)[1])

    def test_the_tree_names_the_kept_revisions(self):
        tree = self.tree()
        for phrase in ('<documento>-r<N>.md', '`issue-r1.md` ao lado de `issue.md`', '"Show before approval"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, tree)


class TheStagesPointToTheRuleTests(unittest.TestCase):
    def test_issue_and_protocol_point_to_the_rule_without_restating_its_steps(self):
        for parts in (('skills', 'frontlights', 'references', 'issue.md'),
                      ('skills', 'frontlights', 'docs', 'protocol.md')):
            # a árvore dos registros de protocol.md descreve o approvals.json e nomeia quem o grava
            text = flat(*parts).split('## Registros', 1)[0]
            with self.subTest(file=parts[-1]):
                self.assertIn('`SKILL.md`, "Show before approval"', text)
                self.assertNotIn('--approve', text)
                self.assertNotIn('git diff --no-index', text)

    def test_the_stage_texts_of_skill_md_point_to_the_rule(self):
        # redesenho, issue 3: as etapas 4, 5 e 7 apontam para a regra por "by link and stamp"; o Short da etapa 1 não
        # pede mais texto integral
        short = ' '.join(skilltext.stage(1).split()).split('**Short**', 1)[1].split('**Full**', 1)[0]
        parts = [('Short', short, False)] + [(str(n), ' '.join(skilltext.stage(n).split()), True) for n in (4, 5, 7)]
        for name, part, points in parts:
            with self.subTest(stage=name):
                self.assertNotEqual(part, '')
                if points:
                    self.assertIn('by link and stamp', part)
                for old in OLD:
                    self.assertNotIn(old, part)

    def test_each_pointer_file_names_the_rule_and_drops_the_full_text(self):
        for parts in POINTER_FILES:
            # a pasta oferecida como opção no progress-report não é documento aprovado
            text = flat(*parts).replace('the folder shown in full', '')
            with self.subTest(file=parts[-1]):
                self.assertIn(POINTER, text)
                self.assertIn('SKILL.md', text)
                for old in OLD:
                    self.assertNotIn(old, text)

    def test_the_progress_report_has_no_full_draft_rule_of_its_own(self):
        text = flat('skills', 'frontlights', 'references', 'progress-report.md')
        self.assertNotIn('**Show the complete draft.**', text)
        self.assertNotIn('the complete draft', text)
        self.assertIn('**Show the draft by link.**', text)
        step7 = text.split('**Show the draft by link.**', 1)[1].split('**Approve and push.**', 1)[0]
        self.assertIn(f'(`SKILL.md`, "{POINTER}")', step7)

    def test_commands_stay_in_full_in_the_browser_testing_reference(self):
        text = flat('skills', 'frontlights', 'references', 'browser-testing.md')
        self.assertIn('statement shown in full', text)
        # issue 74, S2: os dados de teste ficam para reuso, e a lista de resíduo com `DELETE` saiu
        self.assertNotIn('the statements shown in full with `AskUserQuestion`', text)


if __name__ == '__main__':
    unittest.main()
