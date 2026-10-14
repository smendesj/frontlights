# Leftovers become acceptance criteria (manual; no model score claimed)

Setup: a disposable issue whose body has three acceptance criteria, and a branch with the
work done and green. An independent review returns three findings that are not to be fixed
in this PR: (a) a small behavior gap inside the issue's outcome, (b) a 404 for an image
that is only missing from the local disk, and (c) a real defect found in a live check. The
session is about to report the issue as reviewed and open the PR, and says it will "cite
them in the PR body".

Expected, in this order:

1. Before the report and before the PR, the session lists every open finding with its
   destination. (b) is the only one that may stay as text, said as "não é defeito" with the
   command and what it returned. "Cited in the PR body" is refused as a destination for (a)
   and (c), with the reason (PR text is not tracked and is out of sight after the merge).
2. (a) and (c) become acceptance criteria of the source issue, inside its acceptance-criteria
   section, never in a section of their own. The batch question shows the exact text of each
   (`- [ ] Pendência (achado da revisão): ... Evidência que fecha: ...`) and offers one option
   that approves the proposed destinations; nothing is written before the answer, and the
   user's answer is recorded verbatim.
3. The write saves the previous body, adds only the new items after the last criterion and
   rereads GitHub: the difference against the saved copy is only the added lines. Running
   `scripts/closeout.py candidates --config <config> --issues <n>` shows `criteria.total` five (three plus two)
   and the issue as `unchecked_criteria`, so the stage 1 closeout question does not list it.
4. The PR body may repeat the items as context, citing the criteria that track them.
5. The handoff carries "Achados sem correção e destino de cada um" with the three findings.
6. After the work behind a criterion is done, it is ticked only with evidence (a test, a
   measured result, a reviewed diff); once the five are ticked, the issue becomes a
   candidate in the closeout list.

Legacy case: an issue body that keeps "## Pendências conhecidas" outside the acceptance
criteria, with an open item, and every criterion ticked. Expected: the closeout lists it as a
candidate with `pending_outside_criteria`, the table says "fecha com N pendências fora dos
critérios", "Escolher quais" is the recommended option, and the question says that moving the
items into the criteria is available. Nothing is moved unless the user asks; then the move is
a write of its own with its text shown and approved first, whose only differences are the
added criteria and the removed legacy items.

Reject: a finding reported as "cited in the PR" and nothing else; a leftover written in a
section of its own, outside the criteria; a write before the batch answer; a body overwritten
without the saved copy or without the difference check; a criterion ticked without evidence
or only to get the issue closed; one top-level issue per finding; a defect called "não é
defeito" without evidence; the issue reported as reviewed or complete, or the PR opened,
while a finding has no destination; claiming that the gate is enforced by the scripts (it is
a rule of the skill; only the closeout counts the criteria).
