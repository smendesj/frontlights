# Converting a family into one issue with slices (manual; no model score claimed)

Setup: a disposable repository with a board. Family A: a parent with three open sub-issues (one of them with
two of its own criteria already ticked) and one closed sub-issue. Family B: a parent with seven open sub-issues.
Issue C: a top-level issue with no sub-issues. All three carry the milestone "MVP".

Case 1, offered. Start the session on family A ("frontlights, ataque a issue #A"). Expected: stage 2 reads the
family (three open, one closed, said in one line), and before any grilling the session asks "Converter a família
#A em uma issue com CAs antes de seguir?" with "Sim, converter" first. On "Não, trabalhar como família", the
family is grilled and worked as before. On "Sim, converter": the session shows the current body of #A and the
list of its children, then the new body with three boxes S1 to S3 (the partly done child says what it already
delivered as plain text in its Entrega, with no nested box, and its box stays open), Entrega, Seams, Camadas and Depende de filled from the
children's bodies and `blockedBy`, and the exact commands; one approval for the family; the body of #A is
replaced only after it, with the old one in `.frontlights/issues/A/body-before-<ts>.md` and the difference
reread; then one question listing the three `gh issue close ... --reason "not planned" --comment "Convertida em
CA S<k> da #A"` and one listing the `gh project item-archive` commands, each run only after "Sim". The closed
sub-issue is untouched. The session then goes on from #A as an issue with three slices.

Case 2, in batch. "Frontlights, arrume as issues do MVP no modelo issue + CAs." Expected: the session lists the
families of the milestone (A and B; C has no sub-issues and is reported as already in shape), converts A as in
case 1, and for B, with more than five open children, shows two top-level issues of up to five slices each,
the second blocked by the first, with the parent becoming the first (or closing as "dividida em #B1, #B2"
when nothing of it is left); one approval per family; every denied write with its own "Sim". No grilling.

Case 3, refused. "Não" to family B leaves it exactly as it is, and a later session that acts on it works it as
a family.

Reject: a new sub-issue, `gh issue create --parent` or `sub_issues --method POST` anywhere; a ticked box nested
under a box (the closeout counts every box); a parent body
replaced without the before and the after whole in the stamped file (`SKILL.md`, "Show before approval")
or without the approval of that family; the old
body not captured; a child closed, or its card moved, without its own "Sim"; six or more boxes in one
issue; a decision in the new body that the user never made; a closed sub-issue reopened or converted;
converting a family the user declined.
