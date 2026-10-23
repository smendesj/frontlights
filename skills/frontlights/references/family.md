# A family that already exists

Read when: stage 2 finds that the issue has open sub-issues (a parent with children published before the
no-new-sub-issue rule); again in stage 6, before the first branch of such a family.

A family is the old shape of a delivery: a parent issue and its sub-issues. No new sub-issue is ever created
(`references/issues.md`, "Follow-ups"); a family that exists is either converted into one issue with slices or worked
as a family, with the rules below. Stage 6 runs it under the same standing authorization and covered merges as any
issue (`references/development.md`, "Standing authorization and the denied operations"): there is no stacking
question, and the family enters the local main as one.

## Reading the family

The scope is the issue and all its open sub-issues (`gh issue view <n> --json subIssuesSummary`, then each child),
read in stage 2 before choosing the path; closed sub-issues are history. One grilling, one plan, one run; the parent
never goes alone unless the user chose that, and only an explicit choice of the user narrows the work.

## Offering the conversion

Before acting on a family, the session offers its conversion into one issue with slices, and a batch request ("arrume
as issues …") converts a set of families: the question, its options and the procedure are in
"Converting a family", below. A converted family has no sub-issues left: its boxes are the slices of
one issue, and nothing below applies.

## Grilling the children

When the user declines the conversion, the children are grilled in the same session, after the parent's problem and
solution rounds, by `references/grilling.md`, "Sub-issues of the issue"; their layers follow `references/issues.md`,
"The issue and its layers".

## Stacking

Making children wait for the parent to reach the base serializes the family behind a human
step. So, in a family that already exists, whenever an issue of the family depends on another one (a child that
lists its parent in `Depends on`, or a sibling chain), stage 6 **stacks** the
dependent on its dependency's branch. Under the standing authorization this is not
asked: the announcement says it. The choice "Como as filhas se apoiam no pai?" comes
back as a question only when the user asks to change it, with "Empilhadas no pai (Recomendada)" first (each child branches from the
parent's branch and, once verified, is merged into it) and "Esperar o merge do pai" second
(each child starts from the parent's branch once the parent is in the local main). Only the branch of each issue
of the family is pushed, by the same rule as any issue (`references/development.md`, "Slices in order"), and no pull request is opened
for the parent or a child: the branch of a stacked child is created with `gh issue develop <child> --repo <repo>
--base <parent branch> --name <branch_prefix>issue-<child>` once the parent's branch is on GitHub, and the family
enters the local main as one,
through the parent's branch, once its watched run is answered or not needed (`references/development.md`, "Into the local main"), and reaches
GitHub with the release. Record the stacking in the
authorization with the repository operations it needs: a branch cut from a branch that is not the base, and
the covered merges of `references/development.md`, "Standing authorization and the denied operations", which are
the only merges it
allows; merging a PR, writing the remote main, deploying and releasing stay on the denied list. When the user
chose to wait, a dependent stays parked until its dependency is in the local main.

**Concurrency.** Recommend as ceiling the number of independent children whose
`ownership` does not overlap, and never less than the first wave. Read the stacked
wave from `schedule --limit 24` run on a throwaway copy of the plan in which the
parent is marked `verified`; the real plan is not edited. Children whose
ownership overlaps do not run together: `schedule` serializes them, and the
question says so.

**Rules.**

- A child leaves its dependency's branch once the dependency is `verified` on it
  (acceptance evidence current for that branch's HEAD; its tests green, outside a run "só
  com teste assistido"). Create the child's worktree from that
  exact commit (`git worktree add -b <branch_prefix><name> <path> <sha>`), record the
  `<sha>` in the handoff and in the plan, and only `"base": "<dependency-branch>"` in
  its worktree entry of the authorization (the commit does not exist when the
  authorization is approved, so it never goes there). Confirm with `git merge-base
  --is-ancestor <sha> HEAD`.
- Stack on one dependency only. An issue that depends on two unmerged branches, unless
  one already contains the other (a sibling stacked on the parent, say), is
  parked and the question goes to the user; `schedule` does not detect it, so read
  each dependent's `Depends on` yourself. Children of one parent stack on the
  parent, never on each other; a child that needs a sibling's code lists it in
  `Depends on` and stacks on that sibling's branch.
- When the dependency's branch moves after the child started (fixes), the
  child brings it in with `git merge <dependency-branch>`, reruns its tests (outside a
  run "só com teste assistido") and refreshes the evidence; the new hashes make a review
  already done stale. Check
  `git merge-base --is-ancestor` at each material boundary. Use a merge, never a rebase or a
  force-push.
- A verified child is merged into its parent's branch (`git merge --no-ff <child-branch>` in the
  parent's worktree, a covered merge) once it is verified. The merge changes the parent's HEAD, so the
  parent's evidence is refreshed. A child merged into the parent while a sibling is still open is brought into that
  sibling with `git merge <parent-branch>`: conflicts on the hunks the child shares with the sibling are
  resolved in that merge commit, keeping the sibling's own changes on top of what the parent already has,
  and shown in the diff of the family.
- The family enters the local main through the parent's branch, with every verified child merged into
  it, by the gate of "Into the local main": the watched run answered (or not needed) for the family. A child not verified yet keeps the family
  out: it is parked with its question and the parent waits, unless the user chooses to let the parent go
  alone (then the child starts over from the parent's branch once the parent is in the local main, as in
  "Esperar o merge do pai").
- A conflict on anything beyond the parent's own content, or a dependency closed without being
  merged, is a stop condition: park the child and ask.

**Readiness.** An issue is `verified` for a dependent only when its acceptance evidence is current and its changes are
in the dependent's approved base; an unmerged branch meets it only when it is that base. `schedule` reads only
`status`, so an issue that depends on two unmerged branches is a check by hand. With many ready issues that share
ownership, give `schedule` a long timeout.

## Integrating before the local main

Each branch passing alone does not prove the family works together: a test of one child
can assert the very behavior another child changes on purpose, and a clean Git merge
does not prove the family works together. Before a family with more than one branch enters the local
main, integrate it locally: an integration worktree from the parent's branch that
merges every verified child branch (local only: never pushed, never a PR), then run
the type checks (and a suite when the user asked for one). The watched browser run already happened, once
for the batch; `browser-gate` says whether its record still covers this
code, and `stale` asks again. When a local integration worktree already served that run, this
integration is the same one: reuse it and redo it after a fix. Findings follow the destination ladder; a fix goes to the branch that owns
the file, never to the integration branch, and the integration is redone after it.
A batch of independent issues watched together (no parent) gets the same kind of local
integration worktree, cut from the local main; the stage 6 authorization names that merge even
when no stacking question is asked. The family enters the local main only after that integration, with its watched
run answered or not needed for the integrated code. Record the integration worktree, the merged
HEADs and the results in the handoff. The integration branch is evidence, never delivered.

## Converting a family

A family that already exists (a parent with sub-issues published before the no-new-sub-issue rule) is
the old shape of a delivery. The short shape is one issue whose slices are its boxes, each slice its own
worktree (`development.md`, "Slices in order"). The conversion turns the first into the second. It runs
in two situations, with the same procedure:

- **Offered.** Whenever the session is about to act on a family (stage 2 read it: the issue has open
  sub-issues), before the grilling, ask with `AskUserQuestion`: "Converter a família #<n> em uma issue
  com CAs antes de seguir?", options "Sim, converter" (first, recommended) and "Não, trabalhar como
  família". On no, the family is grilled, planned and worked as a family (`grilling.md`, "Sub-issues of
  the issue"). On yes, convert it, then go on from the converted issue.
- **In batch.** When the user asks for a set of issues to be tidied into the short model ("arrume as
  issues do MVP", a milestone, a label, a list of numbers), list the families of that scope (`gh issue
  list` with the filter the user named, then `subIssuesSummary` of each), say how many there are and
  which, and convert them one at a time, in the order the user names or by number; no grilling.

**The procedure, per family.** Read the parent and its open sub-issues (closed sub-issues are history
and stay out). Write the new body of the parent from `templates/issue.md`: the spec sections carry what
the old body and the children's bodies already say (never a decision the user did not make), and each
open child becomes one box `S<k>` with its Entrega (the child's outcome), Seams, Camadas and Depende de
(from its `blockedBy` or `Depends on`), in dependency order; a child already partly done says what it
already delivered as plain text in its Entrega (never as nested boxes: the closeout counts every box,
indented or not), and its box stays open until the rest is done. A child with an open pull request is
not converted while that pull request is open (say so, leave it out of that family's approval, and let the
user merge or close it first); a child whose work is only on a branch keeps that branch as the branch of
its slice, renamed to the slice's name. When the family
has more than five open children, one body is too big: cut them into two or more top-level issues of
up to five slices each, published blockers first and linked by `--blocked-by`; the parent becomes the
first of them, or closes as "dividida em #a, #b" when nothing of it is left. Write the before and the
after whole to the file of the approval (`SKILL.md`, "Show before approval"): the current body of the parent
and the list of its children, then the new body (or bodies) and the commands. Ask one approval per family, with
`AskUserQuestion`; a family the user declines stays as it is.

**The writes, after the approval.** The body of the parent is replaced: this is the only exception to
the append-only rule of the leftover, allowed only here, only after the approval of that exact text. Capture
the old body to `.frontlights/issues/<n>/body-before-<ts>.md`, write the new one with `gh issue edit <n>
--repo <repo> --body-file <file>`, reread it and check the difference against the approved text. A new
top-level issue of a cut family is created as stage 5 creates any issue (board, labels, `--blocked-by`),
never with a parent. Then the converted children: close each one with `gh issue close <c> --repo <repo>
--reason "not planned" --comment "Convertida em CA S<k> da #<n>"`, and take its card off the board with
`gh project item-archive <number> --owner <owner> --id <item-id>`. Closing an issue (the converted
children, and the parent closed as "dividida em #a, #b") and changing the board are denied operations:
ask them with their own questions, one per family (one for the closes, one for the board), each listing
every exact command, and run them only after "Sim". A converted child is history for the closeout
(`closeout.md`): it is no candidate and needs no tick in the parent. Record the conversion in
`.frontlights/issues/<n>/handoff.md` (the children, the boxes they became, the commands and the literal
answers). Until the conversion lands, a session that acts on the family works it as a family.
