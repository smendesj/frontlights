# Vertical issue planning

Read when: entering stage 5; "Follow-ups" when a finding needs a destination; "Converting a family" when an
issue has open sub-issues or on the Conversion path; "Project board" before any issue write.

On entering, read `docs/security.md`, "Revisão e sobras", and `docs/protocol.md`, "Quadro e publicação" and
"`plan.json`".

Read the approved issue body (stage 4) and current GitHub issues/board. Reuse a matching issue; never a duplicate
local task. Use `templates/issue.md` and `examples/plan.json`. Do not split by UI/API/database layers. "Save one
observation and see it after reload" carries screen, API, storage and tests in one slice; correct a horizontal
proposal before showing it, with no extra question.

## Slices as acceptance criteria

A slice is a **tracer bullet**: a narrow, complete path through every layer the behavior needs, demonstrable on its
own, one TDD loop. Prefactoring is the first slice and blocks the others. A wide refactor that leaves no vertical slice
green is the declared exception: expand (add the new form beside the old), migrate in batches, contract.

The slices are the acceptance criteria: one box per slice, blockers first, each one observable, end-to-end result
with Entrega (what can be demoed when it is done), Seams (public interfaces), Camadas, Depende de and the walkthrough,
`Roteiro: <persona> · <passos>` and `→ antes: …; depois: …`:

```markdown
- [ ] S1. <observable, end-to-end result>
  - Entrega: <what can be demoed when it is done>
  - Seams: <public interfaces>
  - Camadas: <layers it touches>
  - Depende de: nenhuma
  - Roteiro: <persona> · <steps>
    → antes: <what the steps show at the base>; depois: <what they show once the slice lands>
```

The persona is a label (`conta 1`, `conta 2`, a test user the run creates, `sem tela`), never a login; the before is
recorded by the reconnaissance (`references/grilling.md`, "Reconnaissance"). Every criterion fails at the base commit.
**A short issue holds at most five slices**: the sixth goes into top-level issues linked by `--blocked-by`, never a
sub-issue. Leftover boxes do not count. In `plan.json`, `slices` carry `id`, `title`, `delivers`, `seams`, `layers`,
`depends_on` and `walkthrough` (`persona`, `steps`, `before` and `after`); `validate-plan` refuses the sixth slice, a
missing field, a later dependency, and a slice without `walkthrough` or with an empty `before`. `frontlights.py
render-criteria --plan <plan.json> --issue <id>` prints the boxes. An old issue gets its walkthrough when it enters
the grilling or stage 6: its open boxes gain the two lines by `closeout.py append --walkthrough <plan>` (append only,
under the approval of the plan). Ticked boxes stay as they are.

**The quiz comes before the body.** Show the numbered list of the slices with "Depende de", what each delivers and, for
each slice, the section of the artifact that shows what it delivers (`references/grilling.md`, "The artifact"): the
same URL as the grilling, sections numbered after the grilling's sections and titled by the slice, the same rule for
code and data as the grilling, the same model (`templates/grilling-section.html`); each opens with what can be demoed
when the slice is done, and the drawing of the slice is its Visual (with a screen, the same before print with the
markings of what that slice changes). Without the tool, say "artefato indisponível" once. Ask whether the granularity
is right, each dependency real, and any slice should merge or split; the quiz itself stays the same, the drawing of
each slice only makes the answers visible; a slice whose drawing shows nothing demonstrable is horizontal: fix it
first. Then ask approval by link and stamp (`SKILL.md`, "Show before approval").

**One write per issue.** The approved file names one write per issue: a creation, or for an existing issue one append
of the boxes (`closeout.py append --spec <plan>`), with its board values. `frontlights.py publish-issue --plan
<plan.json> --approved <stamped file>` runs `stamp --check`, refuses template instructions in a body (`issue-lint`),
publishes blockers first and rereads GitHub: body, boxes and board. `--dry-run` prints the writes for the approved
file; `--resume` rereads GitHub by title before any creation. When the plan itself is the approved file, its
approval records the stamp of each `body_file` it cites, and a body changed after it is refused (`body_not_approved`).
Stages 4 and 5 run in the same window.

## The issue and its layers

An issue, together with the sub-issues it already has, is planned as one unit, and no new sub-issue is created: a
family that already exists is read and worked by `family.md`, in this folder (a parent/child link is membership, not a
dependency; a child still `needs-decision` is grilled first).

The issue must cover **every layer the requirement needs**, named from the code (screen, API, database and migration,
tests, integration, documentation, plus the project's own): handled, or not touched with the reason, under
`## Camadas da fatia`. A layer nobody analysed is a gap in the plan. This does not contradict the rule against
splitting by layer: no issue delivers one layer alone.

**Define the issue's layers only after reading every layer.** Fan the reading out: one read-only subagent per layer,
or per screen for the trace, each reporting `file:line`; the table and the cut stay in this session. For every field,
button or action on a screen, trace the consumer in the back (`file:line`) and the column in the database. A layer is
"not touched" only with the evidence of that trace: A reason without evidence is not accepted. A field nothing
consumes becomes an acceptance criterion, never a new sub-issue and never "not touched". An inconclusive trace is the
task "prove the consumption by a test or by reading the execution" and blocks the approval of the plan: a declared gap
is not a state in which a plan can be approved. The issue body (stage 4) and the plan (stage 5) carry the complete
trace table, and no row lacks evidence.

Seams under test are public interfaces, never internals. `frontlights.py validate-plan --plan <plan.json> --config
<.frontlights/config.json>` checks structure, DAG, slices, board fields, labels and `parent` links, not verticality
(`evals/vertical-slices.md`). The file of the approval holds the table of issues, every body whole and the writes
(`publish-issue --dry-run`); a project without a remote gets `.frontlights/issues/<n>/issue.json`, `source: "local"`.

## Converting a family into one issue with slices

A family that already exists (a parent with sub-issues published before the no-new-sub-issue rule) is converted by
`family.md`, in this folder: the only write that replaces a body, one approval per family.

## Project board

When `.frontlights/config.json` has `project`, every top-level issue this stage creates or adopts belongs on that
board; never publish one outside it. A sub-issue joins only through its parent and takes none of the board writes
below.

- `project_fields` for every field whose default is `null`: `validate-plan --config` refuses the plan while any field is
  still open. With `labels`, `issue_type_by_label` or `body_fields` configured, the plan names them and `validate-plan`
  prints `resolved`, the only values published. The approval table shows them all.
- `publish-issue` creates with the labels and `--blocked-by` (the order of `publish-order --plan`), then the board, the
  assignee, the type and each field; an adopted issue gets labels, `--add-blocked-by` and the board, never a body edit.
  Before the first write it reads the repository's issue types and refuses `issue_type_unavailable`, naming the ones
  that exist (a personal account's repository has none: drop `issue_type` and `issue_type_by_label` from the config's
  `project`); `inspect` warns the same. A `write_failed` carries gh's stderr, masked.
  The reread checks `projectItems`, `issueType`, `labels` and `--json blockedBy`; a failed write is resumed, never
  recreated.
- A value with `$`, a backtick, a quote or a backslash is refused: reword it. Never invent a label. A field with no
  options goes as a `body_fields` line. `sources.project` `unavailable`: report the fix (`gh auth refresh -s project`).

Without `project`, for an organization's repository, ask whether its issues live on a board and record the answer as
`project` (or `null`). Each body carries `Depends on: #N` (or `none`) as support text for the native edges.

## Follow-ups

Findings from an independent review, a test run, a live check or another verification
pass that belong to an issue never become one new issue each. Classify every finding
by the first of the three destinations that fits:

1. Fix it in the issue branch (the same PR, at the release), when it is inside the issue's approved scope and ownership.
2. A new acceptance criterion in the source issue, written as a checklist item
   (`- [ ] ...`) inside its acceptance-criteria section, for a leftover that belongs to
   that outcome (recipe: "A leftover as an acceptance criterion", below). The issue is
   done only when the leftover is treated, completed and ticked with evidence, like any
   other criterion; it is one more box, worked in order like a slice. It also leaves
   one line in the project's pitfalls (`.frontlights/pitfalls.md`), in the same approval as the
   batch and with no question of its own ("A pitfall line", below).
3. A top-level issue only for new scope or for a problem that crosses several issues;
   it cites the issues it crosses in its body and, when one of them must land first,
   depends on it (`--blocked-by`).

The baixos left by a review that ends at 0 sérios and 0 médios (`development.md`, "When the review is done") take
destination 2 as the proposed default, with destination 1 offered in the same batch as "Corrigir os baixos agora";
every other finding takes the first destination that fits.

Never a new sub-issue: the destination of a finding is a criterion of its source issue or
a top-level issue, and a family that already exists is never grown. Every finding that is
not fixed in the PR leaves with a destination GitHub tracks (destination 2 or 3); text in
the PR body is never a destination (the gate, below).

No finding becomes a top-level issue by default. Write the whole batch (each finding,
its proposed destination with the reason, and the whole text of every new criterion
and top-level issue body) to the file of the approval (`SKILL.md`, "Show before
approval"), then decide it in a single `AskUserQuestion`: one option approves the proposed destinations and their named
writes, others adjust them. Approving the batch approves exactly those writes, with the
criterion text exactly as in the stamped file; it is not an implementation authorization for the new
work: a new criterion joins the slices of its issue, in order, and a new top-level issue
is implemented only under an authorization that names it.

A parent of a family that already exists is reported complete only when every child is
closed (`subIssuesSummary.completed` equal to `total`); otherwise list the open children.
A late finding, after the issue was closed, becomes a top-level issue that cites it (a
closed issue takes no new criterion): never reopen, delete or archive an issue yourself,
and close one only through the closeout approval of `references/closeout.md`. An
issue that was only merged and is still open follows the ladder above like any other.

### A leftover as an acceptance criterion

A leftover is not an appendix: it is one more acceptance criterion, never into a section of its own, because the
criteria section is the only one `scripts/closeout.py` counts: kept anywhere else, the issue could be proposed for
closing with it still open. A source issue that has no such section, or is closed, cannot take destination 2: use a
top-level issue that cites it and say why.

- **Text.** One objective, observable item that names the evidence that will close it, in the user's language:
  `- [ ] Pendência (achado da revisão): <what must be true>. Evidência que fecha: <evidence>` (`do teste ao vivo`,
  `dos testes` or `da conferência`). It has no `S<n>`: label it `P1`, `P2` for `checkpoint --slice`, in the handoff.
- **Approval.** Like any update of a published issue, it keeps what is there and is approved before it is written:
  the exact text, in the stamped file of the batch, approved in that single question. Nothing is written before the answer.
- **Write.** `closeout.py append --issue <n> --items <stamped file> [--pitfall <file>]`: it captures the body byte for
  byte, inserts after the last item of the section, captures again right before writing (someone edited it: it stops),
  rereads and prints `criteria.total` before and after. A divergence is shown; restoring the saved body is a write of
  its own and needs its own approval. The handoff keeps the text, the literal answer and the files `append` printed.
- **Treat it.** Tick it only with evidence, never to get the issue closed. While one is open the issue is not in the
  `closes` of `release-plan`, so the PR cites it without a closing keyword (`Closes`, `Fixes`, `Resolves`), in its body
  and in the commit messages, because the merge would close the issue with the criterion unticked.

A leftover kept in a section of its own (an old body) moves into the criteria only when the user asks for it, with its
own approval; until then the closeout only warns (`pending_outside_criteria`).

### A pitfall line

Every criterion that enters a source issue after its approval (destination 2) is a fact the
planning missed, so it leaves one line in `.frontlights/pitfalls.md` of the destination project,
the file the next reconnaissance reads first (`references/grilling.md`, "Reconnaissance").

- **Format.** One line per criterion, in Portuguese:
  `- <AAAA-MM-DD> · #<n> · <fato> · sonda: <sonda>`: the date, the source issue, the fact that
  was missed, written without real data (no login, name, endpoint or customer data: a generic
  description of the case), and the probe that would have caught it, one of the minimum or of the
  triggers of `references/grilling.md`, "Reconnaissance" (a screen state goes in the fact, so the
  next artifact shows it).
- **Approval.** The line goes in the stamped file of the batch, next to the text of its criterion,
  and is approved by the same answer; it is written only after the answer, together with the
  criterion (`append --pitfall`). A finding fixed in the branch or sent to a top-level issue writes no line.
- **File.** Outside version control, like the other records; created on first use, append-only:
  never rewrite, reorder or remove a line.
- **Measure.** The lines per issue are the success measure of the planning: the criteria that
  entered after the approval, which the stage-6 report counts (`references/development.md`).

### The gate: no open finding without a destination

Before an issue is reported as reviewed or complete, and before a PR is opened or
updated, and before the merge into the local main, list every open finding that came up (the watched run, a review the user asked for, the tests
that ran, the live check and any other verification pass), the ones of earlier rounds included, each with its destination: fixed
(the commit), new criterion (the issue and the exact text), top-level issue (its number),
not a defect, or dropped by the user. The report shows that list.

- A finding with none of these stops the report and the PR: say how many are open and
  run the ladder above for them, as one batch.
- A mention in the PR body, in a comment, in the chat or in the handoff is never a
  destination: none of them is tracked, and the PR text is out of sight after the merge. The
  PR body may repeat an item as context, but only when it also has its destination, which
  the body then cites.
- Only noise that is not a defect may stay as text: a 404 for a file that is only missing
  from the local disk, test data left behind, an error line of the tool itself. Say "não
  é defeito" and give the evidence that shows it (the command and what it returned). When
  in doubt it is a finding.
- Only the user can drop a finding that has no destination, by an explicit answer to the
  batch question (its adjust option): record the answer verbatim in the handoff and
  report the finding as "descartado pelo usuário". Never offer it as the default and
  never infer it from silence.
- The handoff keeps the list: "Achados sem correção e destino de cada um"
  (`templates/handoff.md`).
