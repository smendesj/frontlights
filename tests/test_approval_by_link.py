"""Issue 61, S2: a aprovação de um documento, lista ou tabela é por link e carimbo, não pelo texto colado na conversa.

A regra vive num lugar só, "Show before approval" do `SKILL.md`: o documento vai para um arquivo em `.frontlights/`,
enviado pela ferramenta de envio do ambiente e com link clicável; `frontlights.py stamp` dá a revisão, o sha256 de 12
caracteres e os bytes, que a pergunta nomeia; ao lado do link, no máximo cinco linhas (r1: as seções e as decisões;
de r2 em diante: o diff real entre as revisões guardadas); `--approve` grava a resposta literal e `--check` roda antes
da escrita coberta. Comandos (o SQL dos dados de teste e as operações negadas) seguem por inteiro na pergunta. Os
outros textos apontam para a regra em vez de pedir o texto integral na conversa.

Seam: o texto dos arquivos, achatado pelos espaços (`flat`), como nos outros testes de texto.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / 'skills' / 'frontlights'
POINTER = 'Show before approval'

# frases antigas que pediam o documento inteiro na conversa
OLD = ('shown in full', 'show the plan in full', 'Show the complete revision', 'full text in the conversation',
       'complete text in the conversation', 'in full and in the user', 'as much as fits', 'the full body',
       'Print the whole draft text in the conversation', 'na íntegra', 'texto integral', 'texto completo',
       'mostrados por inteiro', 'o texto se repete no `preview`')

POINTER_FILES = (
    ('skills', 'frontlights', 'references', 'issue.md'),
    ('skills', 'frontlights', 'references', 'issues.md'),
    ('skills', 'frontlights', 'references', 'closeout.md'),
    ('skills', 'frontlights', 'references', 'issue-gaps.md'),
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
    return skill().split('**Show before approval.**', 1)[1].split('**Fan out.**', 1)[0]


class TheRuleTests(unittest.TestCase):
    def test_the_document_goes_to_a_file_sent_and_linked(self):
        text = rule()
        for phrase in ('a document, a list or a table', 'never by pasting the full text into the conversation',
                       'Write it to a file under `.frontlights/`', "the host's file-sending tool",
                       'the card reaches the phone', 'a clickable link to the file'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_file_is_stamped_and_the_question_names_the_stamp(self):
        text = rule()
        for phrase in ('frontlights.py stamp <file> --root <project> --revision rN', 'the revision',
                       'a 12-character sha256', 'the bytes', '"Aprova r2 · 6c29ce70c2c7?"'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_at_most_five_lines_next_to_the_link_and_the_real_diff_from_r2(self):
        text = rule()
        for phrase in ('at most five lines', 'in the `preview` of the approve option',
                       'for r1, the sections of the document and the decisions it fixes, each with its section of the artifact',
                       'from r2 on, the real diff between the stored revisions', 'git diff --no-index --stat',
                       'never a summary written by the session', 'Keep each previous revision as a file'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_approval_is_recorded_and_checked_before_the_write(self):
        text = rule()
        for phrase in ('--approve --answer "<literal answer>"', '--check', 'exit 1',
                       'the file changed since the approval', 'nothing is written and the approval is asked again',
                       'showing the new stamp and what changed', 'the GitHub write', 'the tick', 'the summary push'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertLess(text.index('--approve'), text.index('--check'))

    def test_the_scope_names_every_document_and_keeps_commands_in_full(self):
        text = rule()
        for phrase in ('the issue body of stage 4 and its revisions', 'the plan and the bodies of stage 5',
                       'the conversion of a family', 'the findings batch and its leftover criteria',
                       'the closeout list and the cleanup list', 'the issue-gaps table', 'the RoadS progress-report draft',
                       'Commands are not documents', 'references/browser-testing.md', 'the denied operations',
                       'stay in full inside the question'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_a_summary_or_a_path_is_still_not_approval(self):
        text = rule()
        for phrase in ('A summary or a path alone is not approval', 'the approval is of the file with that stamp',
                       'a decision that is not in the stamped file is not approved', 'every revision is a new approval',
                       'If the host cannot send files or the stamp cannot run, record the approval as pending and stop'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn('shown in full in this session', text)

    def test_the_rule_lives_once_in_skill_md(self):
        files = sorted(SKILL_DIR.rglob('*.md')) + [ROOT / 'README.md', ROOT / 'CLAUDE.md'] + sorted(
            (ROOT / 'evals').glob('*.md'))
        for fragment in ('never a summary written by the session', '--approve --answer "<literal answer>"'):
            with self.subTest(fragment=fragment):
                homes = [path.relative_to(ROOT).as_posix() for path in files
                         if fragment in ' '.join(path.read_text(encoding='utf-8').split())]
                self.assertEqual(homes, ['skills/frontlights/SKILL.md'])


class TheStagesPointToTheRuleTests(unittest.TestCase):
    def test_the_stage_texts_of_skill_md_point_to_the_rule(self):
        text = skill()
        short = text.split('- **Short.**', 1)[1].split('- **Full.**', 1)[0]
        stage4 = text.split('## 4. Issue', 1)[1].split('## 5.', 1)[0]
        stage5 = text.split('## 5. Slices and publication', 1)[1].split('Every issue the session creates', 1)[0]
        stage7 = text.split('## 7.', 1)[1]
        for name, part in (('Short', short), ('4', stage4), ('5', stage5), ('7', stage7)):
            with self.subTest(stage=name):
                self.assertIn(f'"{POINTER}"', part)
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
        self.assertIn('the statements shown in full with `AskUserQuestion`', text)


if __name__ == '__main__':
    unittest.main()
