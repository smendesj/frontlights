"""O fechamento de issues é uma etapa com aprovação própria: o texto da skill, da referência, dos docs e do
README diz o mesmo que o script `closeout.py` faz.

Seam: o texto de `SKILL.md`, `references/closeout.md`, `references/development.md`, `references/issues.md`,
`docs/protocol.md`, `docs/security.md` e `README.md`; o script tem os próprios testes (`test_closeout.py`).
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext

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

    def test_stage_one_opens_with_the_closeout_question_only_when_there_is_something_to_close(self):
        # redesenho, issue 3: a sequência à mão (`git fetch --prune`, `cleanup.py plan --issues`, `closeout.py
        # candidates`) virou `frontlights.py open` (busca, planeja a limpeza pelos registros de autorização e lista os
        # candidatos, sem remover nada) e `cleanup.py run --from-authorizations`, sem pergunta, antes da pergunta.
        stage1 = skilltext.flat(skilltext.stage(1))
        self.assertTrue(stage1.startswith('1. **Open and right-size.**'))
        for phrase in ("With a config naming a `repository`, `frontlights.py open` (slow; failure: one line) fetches, "
                       'plans the cleanup from the authorization records and lists closeout candidates, removing nothing',
                       'Then `cleanup.py run --from-authorizations`, unasked',
                       'a `cleanup.ask` candidate is asked first, then rerun with `--yes <branch>`',
                       'If `closeout.ask`, the only opening question',
                       'with the count and numbers, options "Sim, mostrar a lista" and "Não, seguir com o pedido"',
                       'otherwise silent', 'yes runs stage 7, then back', '`awaiting_release` in one line'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage1)
        # review r1 of issue 63 (R1-1): an issue closed by `Closes #n` only counts in `alreadyDone`, so the cleanup
        # cannot wait for a candidate; and `origin/<base>` is fetched before anything is judged. The cleanup now takes
        # its issues from the authorization records (`--from-authorizations`), never from the candidates.
        self.assertNotIn('When it finds merged work', stage1)
        self.assertLess(stage1.index('`frontlights.py open`'), stage1.index('`cleanup.py run --from-authorizations`'))
        self.assertLess(stage1.index('`cleanup.py run --from-authorizations`'),
                        stage1.index('"Fechar as issues que já têm todos os critérios marcados?"'))
        self.assertIn('at stage 1, right after `frontlights.py open`, when the authorization records list issue ids',
                      flat('skills', 'frontlights', 'references', 'closeout.md'))
        self.assertIn('a closed issue counts in `alreadyDone`', flat('skills', 'frontlights', 'references', 'closeout.md'))
        for gone in ('closeout.py" candidates', 'cleanup.py plan', 'fetch --prune origin'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, stage1)
        # 20/10/2026: the closeout never reads the board, so no board remedy is offered at stage 1
        self.assertIn('The closeout never reads the board.', stage1)
        for word in ('board.status', 'done_option_missing', 'project.done', 'gh auth refresh -s project'):
            with self.subTest(gone=word):
                self.assertNotIn(word, stage1)
        question = stage1.split('If `closeout.ask`, the only opening question')[1].split('The closeout never reads')[0]
        for word in ('mover', 'closedUnchecked', 'item-edit'):
            with self.subTest(word=word):
                self.assertNotIn(word, question)
        self.assertNotIn('Progress question', stage1)  # issue 65: the summary runs on request, never at the opening
        self.assertLess(stage1.index('the only opening question'), stage1.index('Choose the lightest path'))

    def test_stage_seven_is_its_own_approval_and_never_merges_or_reopens(self):
        # redesenho, issue 3: a etapa 7 virou um item da lista; a marcação no pai na mesma aprovação vive em
        # closeout.md (a pergunta "Fechar estas <N> issues e marcar os itens dos pais?")
        stage7 = skilltext.flat(skilltext.stage(7))
        for phrase in ('7. **Closeout.**', 'references/closeout.md',
                       'closing waits for its own approval by link and stamp',
                       'no implementation authorization, merged PR or green test covers it',
                       'The cleanup of the merged work (closeout.md, step 5) runs first, without a question',
                       '`closeout.py run` writes the stamped list',
                       '`closeout.py apply --expect <stamp> --answer "<literal>"` checks the stamp itself'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage7)
        closeout = flat('skills', 'frontlights', 'references', 'closeout.md')
        for phrase in ('no implementation authorization, no merged PR and no green test stands in for it',
                       'Never close a parent before every one of its children is closed', '**The tick in a parent.**',
                       '"Fechar estas <N> issues e marcar os itens dos pais?"',
                       'cleanup.py', 'Frontlights does not sync RoadS'):
            with self.subTest(file='closeout.md', phrase=phrase):
                self.assertIn(phrase, closeout)

    def test_the_description_and_the_reference_list_mention_the_closeout(self):
        # redesenho, issue 3: a lista de referências virou a tabela `## Pointers`
        self.assertIn('| references/closeout.md | stage 7; the stage-1 closeout question |', skilltext.pointers())
        self.assertTrue((SKILL / 'references' / 'closeout.md').is_file())

    def test_the_charter_still_forbids_closing_and_points_to_the_closeout(self):
        # redesenho, issue 3: "An operation on the denied list" virou a última frase da etapa 6
        stage6 = skilltext.flat(skilltext.stage(6))
        self.assertIn('A denied operation runs only after the "Sim" of its own question naming the exact command', stage6)
        self.assertIn('closing an issue', flat('skills', 'frontlights', 'references', 'development.md'))


class ReferenceTests(unittest.TestCase):
    """Issue 2 do redesenho: a referência encolheu (3.907 → ~1.150 palavras) porque `closeout.py run`/`apply` e
    `cleanup.py run` fazem o que ela descrevia passo a passo; os pins seguem as regras, não a prosa antiga."""

    def setUp(self):
        self.text = (SKILL / 'references' / 'closeout.md').read_text(encoding='utf-8')
        self.flat = ' '.join(self.text.split())

    def test_the_reference_is_short(self):
        self.assertLess(len(self.text.split()), 1400)

    def test_the_candidate_rule_and_the_order(self):
        for phrase in ('every criterion of it is ticked', 'every sub-issue is closed or in the same batch',
                       '(children close before their parents)', 'a closed issue counts in `alreadyDone`',
                       '`excluded` says why', '`unchecked_criteria` and `no_criteria` with the counts',
                       'this step never ticks one'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_writes_are_the_documented_commands_in_order_and_verified(self):
        for phrase in ('closeout.py" run [--issues 12,13]',
                       'closeout.py" apply --expect <stamp> --answer "<literal answer>" [--only 12,13]',
                       'gh issue close <n> --repo <repo> --reason completed',
                       'Never close a parent before every one of its children is closed',
                       'never a close that already landed', 'adding no comment',
                       '`lista mudou: …`', 'when `--only` leaves a chosen parent without its child',
                       'with the `gh` account checked before each write',
                       '`closeout-<…>.result.json` keeps the commands, exit codes, reread state and literal answer',
                       '`apply` ends with the `verify` of what it closed', 'GitHub is the source of truth'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_the_approval_is_a_question_with_options_of_at_most_five_words(self):
        for phrase in ('"Fechar estas <N> issues?"', '"Fechar estas <N> issues e marcar os itens dos pais?"', '"Show before approval"',
                       '`.frontlights/closeout-<AAAAMMDD-HHMMSS>.md`', 'prints `stamp`, `question`, `options` and `recommended`',
                       'Record the answer verbatim', 'never answer for the user'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)
        asking = ' '.join(section(self.text, '2. Show the list and ask').split())
        labels = re.findall(r'"([^"]+)"', asking.split('with `AskUserQuestion`:', 1)[1].split('Record')[0])
        options = list(dict.fromkeys(x for x in labels if not x.startswith('Fechar estas')))
        self.assertEqual(options, ['Sim, fechar tudo', 'Escolher quais', 'Só fechar, sem marcar', 'Não agora',
                                   'Não, seguir com o pedido'])
        self.assertTrue(all(len(label.split()) <= 5 for label in options), options)

    def test_the_options_of_the_reference_are_the_ones_the_script_prints(self):
        source = (ROOT / 'skills' / 'frontlights' / 'scripts' / 'closeout.py').read_text(encoding='utf-8')
        for label in ('Sim, fechar tudo', 'Escolher quais', 'Só fechar, sem marcar', 'Não agora'):
            with self.subTest(label=label):
                self.assertIn(f"'{label}'", source)
                self.assertIn(f'"{label}"', self.flat)

    def test_the_list_and_the_writes_never_move_a_card(self):
        # Issue 63: the board's "Item closed" workflow moves the card; since 20/10/2026 the closeout never reads it.
        for title in ('2. Show the list and ask', '3. Write what was approved'):
            text = ' '.join(section(self.text, title).split())
            for word in ('mover', 'move', 'item-edit', 'Done'):
                with self.subTest(section=title, word=word):
                    self.assertNotIn(word, text)
        self.assertIn('The card goes to Done by the board\'s own workflow ("Item closed" → Status Done)', self.flat)
        self.assertIn('Move or read a card (`gh project item-edit`, a board read)', self.flat)
        self.assertIn('this flow never reads the board and never moves a card', self.flat)
        self.assertIn('The verify reads only the issues', self.flat)
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
                       'a sync within 30 s returns the old snapshot',
                       'RoadS shows it after its next sync', 'Frontlights does not sync RoadS and does not read the board'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_closing_is_never_implied(self):
        for phrase in ('with **its own approval**', 'no merged PR and no green test stands in for it',
                       'Reopen, delete, transfer or archive an issue, or edit its body, here',
                       'Merge a pull request, deploy or release: the closeout never does'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_a_new_session_past_the_context_threshold_starts_with_run(self):
        self.assertIn('Past ~300k of context, open a new session whose first command is `closeout.py run`', self.flat)


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
        self.assertIn('`closeout.py run`, `closeout.py apply`', readme)  # issue 12 do redesenho: o README virou guia curto; a regra vive na skill
        for phrase in ('`done` é opcional', '"Status", "value": "Done"', 'não chegou a Done'):
            with self.subTest(gone=phrase):
                self.assertNotIn(phrase, readme)


if __name__ == '__main__':
    unittest.main()
