"""O fechamento de issues é uma etapa com aprovação própria: o texto da skill, da referência, dos docs e do
README diz o mesmo que o script `closeout.py` faz.

Seam: o texto de `SKILL.md`, `references/closeout.md`, `references/development.md`, `references/issues.md`,
`docs/protocol.md`, `docs/security.md` e `README.md`; o script tem os próprios testes (`test_closeout.py`).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def flat(*parts):
    return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())


def section(text, heading):
    match = re.search(rf'^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match.group(1) if match else ''


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')

    def test_stage_one_asks_after_the_progress_question_and_only_when_there_is_something_to_close(self):
        stage1 = ' '.join(self.text.split('## 1.')[1].split('## 2.')[0].split())
        self.assertIn('**Closeout question, right after the progress question.**', stage1)
        self.assertIn('closeout.py" candidates', stage1)
        self.assertIn('Only when `candidates` reports `ask` true', stage1)
        # review r1 of issue 63 (R1-1): an issue closed by `Closes #n` only counts in `alreadyDone`, so the cleanup
        # cannot wait for a candidate; and `origin/<base>` is fetched before anything is judged
        self.assertNotIn('When it finds merged work', stage1)
        for phrase in ('When the `.frontlights/authorization*.json` records list issue ids, first run '
                       '`git -C <main worktree> fetch --prune origin`',
                       'before `closeout.py candidates` and `cleanup.py plan`',
                       'then always run the cleanup of `references/closeout.md`, step 5, without a question',
                       '`cleanup.py plan` with `--issues` the `issue_ids` of the authorization records',
                       'the plan alone judges what is merged'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage1)
        self.assertLess(stage1.index('fetch --prune origin'), stage1.index('`cleanup.py plan` with'))
        self.assertLess(stage1.index('`cleanup.py plan` with'), stage1.index('closeout.py" candidates'))
        self.assertIn('"Fechar as issues que já têm todos os critérios marcados?"', stage1)
        self.assertIn('When `ask` is false, say nothing and go on exactly as before, except when an issue is excluded as `awaiting_release`', stage1)
        # 20/10/2026: the closeout never reads the board, so no board remedy is offered at stage 1
        self.assertIn('The closeout never reads the board.', stage1)
        for word in ('board.status', 'done_option_missing', 'project.done', 'gh auth refresh -s project'):
            with self.subTest(gone=word):
                self.assertNotIn(word, stage1)
        question = stage1.split('**Closeout question, right after the progress question.**')[1]
        for word in ('mover', 'closedUnchecked', 'item-edit'):
            with self.subTest(word=word):
                self.assertNotIn(word, question)
        self.assertLess(stage1.index('Progress question'), stage1.index('Closeout question'))
        self.assertLess(stage1.index('Closeout question'), stage1.index('Then choose the lightest path'))

    def test_stage_seven_is_its_own_approval_and_never_merges_or_reopens(self):
        stage7 = ' '.join(self.text.split('## 7.')[1].split())
        for phrase in ('Closeout of finished issues (its own approval)', 'references/closeout.md',
                       'Closing (with the tick in a parent, in the same approval) waits for its own '
                       'approval of the list by link and stamp', 'no implementation authorization, merged PR or green test covers it',
                       'the cleanup of the merged work (closeout.md, step 5) runs first, without a question'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage7)
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        for phrase in ('no implementation authorization, no merged PR and no green test stands in for it',
                       'Never close a parent before every one of its children is closed', '**The tick in a parent.**',
                       'cleanup.py', 'Frontlights does not sync RoadS'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)

    def test_the_description_and_the_reference_list_mention_the_closeout(self):
        self.assertIn('`references/closeout.md` (stage 7 and the closeout question of stage 1)', ' '.join(self.text.split()))
        self.assertTrue((SKILL / 'references' / 'closeout.md').is_file())

    def test_the_charter_still_forbids_closing_and_points_to_the_closeout(self):
        stage6 = ' '.join(self.text.split('## 6.')[1].split('## 7.')[0].split())
        self.assertIn('An operation on the denied list', stage6)
        self.assertIn('closing an issue', flat('skills', 'frontlights', 'references', 'development.md'))


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / 'references' / 'closeout.md').read_text(encoding='utf-8')
        self.flat = ' '.join(self.text.split())

    def test_the_candidate_rule_and_the_order(self):
        for phrase in ('every criterion of it is ticked', 'every one of its sub-issues is closed or a candidate in the same batch',
                       '(children close before their parents)', 'A closed issue is never a candidate: it is counted in `alreadyDone`',
                       '`excluded` lists what is not ready and why', '`unchecked_criteria` and `no_criteria` with the counts',
                       'never ticks one itself'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_writes_are_the_documented_commands_in_order_and_verified(self):
        for phrase in ('gh issue close <n> --repo <repo> --reason completed',
                       'Never close a parent before every one of its children is closed',
                       'never by repeating a close that already landed', 'Add no comment',
                       'closeout.py" verify', 'GitHub is the source of truth'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_approval_is_a_question_with_options_of_at_most_five_words(self):
        for phrase in ('"Fechar estas <N> issues?"', '"Fechar estas <N> issues e marcar os itens dos pais?"', '"Show before approval"',
                       'Record the answer verbatim', 'never answer for the user'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)
        asking = ' '.join(section(self.text, '2. Show the list and ask').split())
        labels = re.findall(r'"([^"]+)"', asking.split('with `AskUserQuestion`:', 1)[1].split('Record')[0])
        options = list(dict.fromkeys(x for x in labels if not x.startswith('Fechar estas')))
        self.assertEqual(options, ['Sim, fechar tudo', 'Escolher quais', 'Não agora', 'Só fechar, sem marcar', 'Não, seguir com o pedido'])
        self.assertTrue(all(len(label.split()) <= 5 for label in options), options)

    def test_the_list_and_the_writes_never_move_a_card(self):
        # Issue 63: the board's "Item closed" workflow moves the card; since 20/10/2026 the closeout never reads it.
        for title in ('2. Show the list and ask', '3. Write what was approved'):
            text = ' '.join(section(self.text, title).split())
            for word in ('mover', 'move', 'item-edit', 'Done'):
                with self.subTest(section=title, word=word):
                    self.assertNotIn(word, text)
        self.assertIn('The card goes to Done by the board\'s own workflow ("Item closed" → Status Done)', self.flat)
        self.assertIn('Move or read a card (`gh project item-edit`, a board read): the board\'s "Item closed" workflow '
                      'moves it to Done', self.flat)
        self.assertIn('this flow never reads the board and never moves a card', self.flat)
        self.assertIn('The verify reads only the issues, never the board', self.flat)
        for word in ('cardsOutsideDone', 'board.status', 'done_option_missing', 'not_on_board', 'project.done',
                     'gh auth refresh -s project', 'card status'):
            with self.subTest(gone=word):
                self.assertNotIn(word, self.flat)

    def test_every_reason_the_script_produces_is_documented(self):
        source = (ROOT / 'skills' / 'frontlights' / 'scripts' / 'closeout.py').read_text(encoding='utf-8')
        for code in ('unchecked_criteria', 'no_criteria', 'open_children', 'truncated', 'not_found', 'unreadable',
                     'open_pr', 'no_pr', 'pending_outside_criteria', 'awaiting_release'):
            with self.subTest(code=code):
                self.assertIn(f"'{code}'", source, 'the script no longer produces it')
                self.assertIn(code, self.flat, 'the reference does not explain it')
        for code in ('not_on_board', 'done_option_missing', 'cardsOutsideDone', 'board_state', 'project.done', 'projectItems'):
            with self.subTest(gone=code):
                self.assertNotIn(code, source, 'the closeout reads the board again')

    def test_the_reference_tells_that_roads_reads_only_the_card_status_and_shows_it_after_its_sync(self):
        for phrase in ('RoadS reads only the **Status** of the card in the Project, never whether the issue is closed',
                       'the board\'s "Item closed" workflow moves the card to Done when the issue closes',
                       'a sync within 30 s of the previous one returns the old snapshot',
                       'RoadS shows it after its next sync', 'Frontlights does not sync RoadS and does not read the board'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_closing_is_never_implied(self):
        for phrase in ('with **its own approval**', 'no merged PR and no green test stands in for it',
                       'Reopen, delete, transfer or archive an issue, or edit its body, here',
                       'Merge a pull request, deploy or release: the closeout never does'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)


class RulesInOtherDocsTests(unittest.TestCase):
    def test_development_ticks_only_with_evidence_and_leaves_closing_to_the_closeout(self):
        text = flat('skills', 'frontlights', 'references', 'development.md')
        self.assertIn('tick an acceptance criterion in the issue body only with evidence for it', text)
        self.assertIn('Closing an issue is never part of this: it has its own approval', text)
        self.assertNotIn('moving its card', text)

    def test_follow_ups_close_only_through_the_closeout(self):
        text = flat('skills', 'frontlights', 'references', 'issues.md')
        self.assertIn('never reopen, delete or archive an issue yourself, and close one only through the closeout approval',
                      text)

    def test_the_documents_describe_the_step(self):
        self.assertIn('| Fechamento |', (ROOT / 'skills' / 'frontlights' / 'docs' / 'protocol.md').read_text(encoding='utf-8'))
        self.assertIn('scripts/closeout.py', flat('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('só lê', flat('skills', 'frontlights', 'docs', 'security.md'))
        readme = flat('README.md')
        for phrase in ('### Fechar o que terminou', 'todos os critérios de aceitação marcados', 'sub-issues antes dos pais',
                       'o fechamento do Frontlights não lê o quadro', 'scripts/closeout.py candidates|verify'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        for phrase in ('`done` é opcional', '"Status", "value": "Done"', 'não chegou a Done'):
            with self.subTest(gone=phrase):
                self.assertNotIn(phrase, readme)


if __name__ == '__main__':
    unittest.main()
