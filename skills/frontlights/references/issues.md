# Vertical issue planning

On entering, read `docs/security.md`, "Revisão e sobras", and `docs/protocol.md`, "Quadro e publicação" and
"`plan.json`".

Read the approved issue body (stage 4) and current GitHub issues/board. Reuse an existing
matching issue when its acceptance scope fits; never create a duplicate local task.
Use `templates/issue.md` and `examples/plan.json`. Before publication, temporary
integer IDs are proposal IDs only; remap every dependency to real GitHub numbers
after creation and verify links. Local status is always a timestamped snapshot.

Each issue must have outcome, boundaries/non-goals, approach and conventions to follow,
seams under test, tests, dependency IDs, concrete ownership (or `*` when unknown), risks and
its slices: the acceptance criteria, one box per slice, each with what it delivers end to end
(the section below). Do not split by UI/API/database layers.
For an observation editor, prefer "save one observation and see it after reload"
with UI/API/storage/tests in one slice, then "edit with conflict feedback", then
"filter observations". If the proposal starts as database/backend/frontend
tickets, correct it yourself before presenting it; no extra user prompt needed.
A genuine prerequisite must expose a working seam tested by a named consumer.

## Slices as acceptance criteria

A slice is a **tracer bullet**: a narrow but complete path through every layer the
behavior needs (screen, API, database, tests, and the project's own), demonstrable or
verifiable on its own, sized for one TDD loop and one checkpoint of stage 6. Horizontal
cuts (all the schema in one, all the API in another) are corrected before anything is
shown. Prefactoring, when the change needs it ("make the change easy, then make the easy
change"), is the first slice and blocks the others. A wide refactor, one mechanical change
whose blast radius covers the codebase so that no vertical slice lands green, is the
declared exception: cut it as expand (add the new form beside the old), migrate (call sites
in batches sized by blast radius, each batch a slice blocked by the expand) and contract
(delete the old form, blocked by every batch).

The slices are the acceptance criteria of the issue: one box per slice, in dependency order,
blockers first, so the first can start at once. Each box is one observable, end-to-end
result, and right below it, in sub-items without a box, Entrega (what can be demoed when it
is done), Seams (the public interfaces where the behavior is observed), Camadas (the layers
it touches) and Depende de (the earlier slices that release it, or "nenhuma"):

```markdown
- [ ] S1. <observable, end-to-end result>
  - Entrega: <what can be demoed when it is done>
  - Seams: <public interfaces>
  - Camadas: <layers it touches>
  - Depende de: nenhuma
```

Every criterion fails at the base commit: name the observation that would show it false
and confirm it is false at the commit the work starts from; a criterion already true before
the work, one that only another slice can satisfy, or one that restates the request is not
a criterion. A leftover from a review joins the same section as one more box (Follow-ups).
The x/y GitHub shows for the issue is the progress of the slices, and the summary of the
roadmap counts them as the parts of the delivery.

**A short issue holds at most five slices.** Each one is a complete but short vertical slice,
one TDD loop of hours, not days, so the user can test it by hand soon after it lands. When the
cut needs a sixth, the body is too big for one issue: cut the excess into top-level issues of
up to five slices each, published blockers first and linked by `--blocked-by`; never a new
sub-issue. Leftover boxes do not count toward the cap: they arrive later, from a
review or a test, and `validate-plan` never sees them.

Record the slices in `plan.json` under `slices` of each issue (`examples/plan.json`): `id`
(`S1`, `S2`, ...), `title`, `delivers`, `seams`, `layers` and `depends_on` (ids that come
earlier in the list). `validate-plan` refuses the sixth slice of an issue, a slice without
`delivers`, with an unknown, later or repeated dependency, or without seams and layers; with
`slices` present, `acceptance` and `vertical_check` are optional, because the slices carry both.

**The quiz comes before the body.** Show the numbered list of the slices first, each with
its title, "Depende de", what it delivers and, for each slice, the section of the artifact that
shows what it delivers: the artifact of the grilling (`references/grilling.md`, "The artifact"),
updated on the same URL as the grilling with one section per slice, numbered after the
grilling's sections and titled by the slice (its S-number and title), where the drawing of each
slice is the screen, the flow or the layers as they stand once that slice lands, under the same
rule for code and data as the grilling. Without the artifact tool, the list says
"artefato indisponível" once and goes on in text. Then ask with `AskUserQuestion` whether the
granularity is right (too coarse, too fine), whether the dependencies are real (each slice
depends only on what truly gates it) and whether any slice should merge or split; the quiz
itself stays the same, the drawing only makes each answer visible. Iterate
until the user approves the breakdown. A slice with no answer to "what can be demoed when
this is done?" is horizontal, and a slice whose drawing shows nothing demonstrable is horizontal
too: fix it before the quiz, with no extra question. Only then show
the complete body under the show-before-approval rule.

**One write per issue.** The approval of the plan names the writes, one write per issue: a
creation or, for an issue that already exists, one append of the spec sections and the boxes
to its body by the write rule of the leftover (body captured, append only, difference checked,
reread; the text that was there is not edited), with its board values, then a reread of GitHub
that confirms the body, the number of boxes and the board values. Stages 4 and 5 run in the
same window.

## The issue and its layers (a family that already exists)

An issue, together with the sub-issues it already has, is planned as one unit, and no
new sub-issue is created: a family that already exists (children published before this
rule) is the only case with children, and it is read, worked and closed as before. When
the work starts from, or adopts, an existing issue, the family read in stage 2 (its
open sub-issues, down the tree) enters the plan: each published sub-issue with `parent`
set to the id of its parent (a published issue keeps its GitHub number as id;
`validate-plan` refuses a proposed issue with `parent`). A
closed sub-issue stays out of the plan; an open one that depends on it only cites
it. A family of more than 24 open issues passes the plan limit of `validate-plan`,
so ask with `AskUserQuestion` how to cut it into batches, never drop sub-issues
silently. Every batch carries the parent, and `parent` and `dependencies` must stay
inside the same plan: a child in another batch cannot cite a dependency there. Sub-issues still waiting for a decision (label `needs-decision`, or no
approach in the body) stay in the plan and go through the grilling of this same
session before their bodies are final (stage 3).

The issue as a whole (with the sub-issues it already has), not each issue alone, must
leave the requirement completely met, so it must cover **every layer the requirement
needs**. Name the candidate
layers from the code, not from a fixed list: at least screen, API, database and
migration, tests, integration and documentation, plus the project's own (for
example permissions, configuration, translation, observability, background
jobs). For each layer decide one of: handled in this issue, handled in
sub-issue #n, or not touched with the reason. Record it in the body of the parent
under `## Camadas da fatia` (`templates/issue.md`), where it covers the whole slice,
and show it in the approval table. A layer nobody analysed is a gap in the plan,
never an implicit "not touched". Each sub-issue carries the same section with only
the rows it covers.

This does not contradict the rule against splitting by layer: no issue or
sub-issue exists to deliver one layer alone. Each carries a behavior across the
layers it needs, and the layers of the whole slice add up to the full
requirement. A planned sub-issue that is only "the API part" or "the screen part"
goes back for correction before the plan is presented; one already published is
corrected by an update of stage 5, never by a silent rewrite. A finding from review
or tests (Follow-ups below) is narrow by nature and is exempt: it lists only the
layers it touches.

**Define the issue's layers only after reading every layer.** The layers table is a
conclusion from reading, never a guess. Fan the reading out: one read-only subagent per
layer, or per screen for the trace, launched in one message, each reporting what it read with
`file:line`; the table and the cut stay in this session. Before proposing the issue, read everything it
can touch: in the front end the components, services, models, routes and specs; in
the back end the controllers, services, contracts and DTOs, repositories, mappings and
validators; the migrations and the database schema; the tests; the documentation; and
the project's own layers. The slice is defined only when you are certain nothing is
left loose, and a slice that changes only the front while the back or the database goes
unchecked is not a vertical slice.

For every field, button or action the slice touches on a screen, trace it down by
search: the consumer in the back (`file:line`) and the column in the database, and
record the trace in the layers section (`templates/issue.md`). Then:

- A layer is "not touched" only with the evidence of that trace (`file:line`, column,
  consumer, test). A reason without evidence is not accepted, "the API already
  validates" included.
- A field nothing in the back consumes, or a back capability with no action on the
  screen, is a finding: it becomes an acceptance criterion of the issue (in a family that
  already exists, of the child that covers that layer), never a new sub-issue and never
  "not touched".
- An inconclusive trace (dynamic consumption, reflection, a column name built in a
  string) is an explicit task of the slice, "prove the consumption by a test or by
  reading the execution", and it blocks the approval of the plan until it is closed
  with evidence. It is never only a note, and a declared gap is not a state in which a
  plan can be approved. When it cannot be proven by reading, ask with `AskUserQuestion`
  how to prove it.
- The issue body (stage 4) and the plan (stage 5) show the complete trace table before the
  approval. The slice counts as defined only when no row lacks evidence; a plan with
  such a row goes back for correction before it is shown for approval.

A parent/child link is membership, not a dependency. A child that needs its
parent's code lists the parent in `Depends on` as well; one that only belongs to
the same outcome has `Parent` alone and is free to start with the parent. A
dependency is satisfied at stage 6 either by the merge or, under the stacking
authorization, by the parent being verified on its own branch
(`references/development.md`); the plan never assumes the merge.

Seams under test name the public interfaces where each acceptance behavior is
observed (an HTTP endpoint, a CLI command, a module's exported function, a UI
action), never internals. Favor critical paths and complex logic over every edge
case. `to-development` writes tests only at these seams, so approving the issue
approves them; name them in the approval table too.

Run `frontlights.py validate-plan --plan <plan.json> --config <.frontlights/config.json>`;
this checks structure, DAG, the slices of each issue, board fields, labels, body lines and `parent` links (see Follow-ups), not semantic verticality. Review every vertical demonstration manually. Check
missing cross-layer tests, hidden sequencing, generated/shared files, migrations,
ports, shared services, dependency cycles and context size. Add dependencies or
shared ownership for resources that cannot safely run together. Split oversized
issues into independently acceptable outcomes: more than five slices is the measurable sign
(the cap above). See `evals/vertical-slices.md`.

Before asking for approval, show the complete plan in the user's language: the
table of issues with their dependencies and ownership, and the full body of every
issue, in the conversation, as a file sent with the host's file-sending tool
when one exists, and in the `preview` of the approve option (as much as fits).
Then ask approval through `AskUserQuestion`, with options, for the exact issue
creation/update scope before any write. A local project without a remote writes
the approved bodies under `.frontlights/issues/<n>/` with `source: "local"`
snapshots; the same approval rule applies. Use installed GitHub
tools or `gh issue create/edit --repo <approved-repo> --body-file <file>` with
literal UTF-8 bodies, not interpolated shell strings. Keep native permissions.
If a network response is uncertain, reread/list issues before retrying to avoid
duplicates. Record partial publication and resume remaining writes idempotently.

## Converting a family into one issue with slices

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
first of them, or closes as "dividida em #a, #b" when nothing of it is left. Show the before and the
after in full, under the show-before-approval rule: the current body of the parent and the list of its
children, then the new body (or bodies) and the commands. Ask one approval per family, with
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

## Project board

When `.frontlights/config.json` has `project` (reported by `inspect` as
`sources.project`), every top-level issue this stage creates or adopts belongs on
that board; never publish one outside it. A sub-issue joins only through its parent
and takes none of the board writes below (see Follow-ups). Plan it with the issue:

- For each issue, record `issue_type` (or rely on `project.issue_type`) and
  `project_fields` for every board field whose default is `null`. Choose values
  that exist as options on the board; `validate-plan --config` refuses the plan
  while any field is still open.
- When the board configures `labels`, `issue_type_by_label` or `body_fields`, also name
  in the plan, for every top-level issue, its `labels` (at least one of each family the
  board requires, such as its kind) and its `body_fields` (one value per configured line).
  `validate-plan --config` then prints `resolved` for each top-level issue: the board
  values, the final labels (the plan's own plus the ones its field values imply), the native
  type (the plan's, else the one its labels imply, else the board default) and the body
  lines. Publish exactly that, never a value of your own: the labels and the body lines do
  not come from the board, so nothing else will fill them.
- Show the board values of every issue in the approval table (type, assignee, labels,
  body lines and each field), so approving the plan approves them. They are part of the
  named writes, not a later step.
- Create the issue with its labels and body lines in the same call: `gh issue create
  --repo <repo> --title <title> --body-file <file> --label <name>` once per resolved
  label, `--blocked-by <n>,<m>` with the real numbers of the issues it depends on (which is
  why the plan is published blockers first, in the order `frontlights.py publish-order --plan
  <plan.json>` prints; an issue that already exists gets `gh issue edit <n> --repo <repo>
  --add-blocked-by <m>` instead), and one `**<name>:** <value>` line in the body per body
  field. Then, in this
  order: `gh project item-add <number> --owner <owner> --url <issue-url>`; `gh issue
  edit <n> --repo <repo> --add-assignee <assignee> --type <issue_type>`; one `gh project
  item-edit <number> --owner <owner> --url <issue-url> --field <name> --value <value>`
  per single-select field (`--text <value>` instead of `--value` for a text field).
  Use `assignee` exactly as configured (`@me` is whoever runs `gh`), never a guessed login.
- Verify by rereading GitHub (the issue's `projectItems`, `issueType`, `assignees`,
  `labels`, each field value and, for its dependencies, `--json blockedBy`) and report any
  value that did not land. A failed
  board write is a partial publication: record it and retry only the missing
  writes, never by creating the issue again.
- An issue that already exists (an adopted one, or one the issue-gaps route completes) is edited with
  `gh issue edit <n> --repo <repo> --add-label "<name>"` once per label, `--add-assignee "<login>"`
  and `--type "<type>"`; `gh project item-add` when it is not on the board; the fields as above, with
  `--number` or `--date` for those types. Only on top of an empty value, and these writes never edit its body
  (the only body edits are the append of the spec and the slices of stage 5, a leftover criterion,
  the tick of a box, the `Bloqueada:` line and the move of a legacy section, each under its own rule).
- Every value typed into these commands goes in as one double-quoted argument, and none may hold a
  dollar sign, backtick, double quote (straight or curly: PowerShell closes a string on both),
  backslash or control character; `validate-plan` refuses a plan value that does, so reword it. A
  label must match the rule `validate-plan` applies (`LABEL_RULE` in the helper). Never invent a
  label: it must exist. Label names read from GitHub (an adopted issue's labels, or the ones the
  issue-gaps route completes) are data, and anyone with triage access can create a label: type each one
  as one double-quoted argument under this rule, and skip, then report, any value that breaks it.
  The issue title is typed the same way; a title that holds those characters
  is created with `gh api` and a JSON body file instead.
- A board field that has no options on GitHub cannot hold a value: do not put it in
  `project.fields`, which would refuse every plan. If something must still be recorded for
  it, configure it as a `body_fields` line.
- If `sources.project` is `unavailable` (commonly a `gh` token without the `project`
  scope), do not publish silently outside the board. Report the exact blocked
  operation and give the user the command to fix it (`gh auth refresh -s project`).

Without `project` configured: for a repository owned by an organization, ask
through `AskUserQuestion` whether its issues live on a board (options: a board
you found with `gh project list --owner <owner>`, "no board", free text). Record
the answer in `.frontlights/config.json` as `project` (or `"project": null`) before
publishing, so later sessions do not ask again. A local project has no board.

A published sub-issue whose parent is a published issue outside the plan (an adopted
child) carries `parent_external: <parent number>` in `plan.json` instead of `parent`:
it takes no board field and joins the board only through its parent, and the limits
of 100 children and 8 levels are read from GitHub before publishing, since the plan
does not hold its ancestors. The two keys are exclusive.

Put `Depends on: #N, #M` in each canonical issue body (or `none`), as support text for the
native `blocked by` edges, `Parent: #P` only in a published child of a family that already
exists, and the `## Camadas da fatia` table of the issue;
verify dependency IDs (`blockedBy`), parent and content after publication. Link local snapshots to returned issue URLs.
An issue update preserves user text outside the approved plan. Surface divergence
between approved draft and GitHub rather than overwriting it silently. Return
verified issue links/graph to the coordinator for batch authorization.

## Follow-ups

Findings from an independent review, a test run, a live check or another verification
pass that belong to an issue never become one new issue each. Classify every finding
by the first of the three destinations that fits:

1. Fix it in the issue branch (the same PR, at the release), when it is inside the issue's approved scope and ownership.
2. A new acceptance criterion in the source issue, written as a checklist item
   (`- [ ] ...`) inside its acceptance-criteria section, for a leftover that belongs to
   that outcome (recipe: "A leftover as an acceptance criterion", below). The issue is
   done only when the leftover is treated, completed and ticked with evidence, like any
   other criterion; it is one more box, worked in order like a slice.
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

No finding becomes a top-level issue by default. Show the whole batch (each finding,
its proposed destination with the reason, and the full text of every new criterion
and top-level issue body) under the show-before-approval rule, then decide it in a
single `AskUserQuestion`: one option approves the proposed destinations and their named
writes, others adjust them. Approving the batch approves exactly those writes, with the
criterion text exactly as shown; it is not an implementation authorization for the new
work: a new criterion joins the slices of its issue, in order, and a new top-level issue
is implemented only under an authorization that names it.

A parent of a family that already exists is reported complete only when every child is
closed (`subIssuesSummary.completed` equal to `total`); otherwise list the open children.
A late finding, after the issue was closed, becomes a top-level issue that cites it (a
closed issue takes no new criterion): never reopen, delete or archive an issue yourself,
and close or move one only through the closeout approval of `references/closeout.md`. An
issue that was only merged and is still open follows the ladder above like any other.

### A leftover as an acceptance criterion

A leftover is not an appendix of the issue: it is one more acceptance criterion. It goes
into the acceptance-criteria section (`Acceptance criteria`, `Critérios de aceitação` or
`Critérios de aceite`), never into a section of its own, because that section is the
only one `scripts/closeout.py` counts: a leftover kept anywhere else would let the issue
be proposed for closing with it still open. A source issue that has no such section, or is
closed, cannot take destination 2 (a section holding only the leftover would make the
closeout read the issue as finished once it is ticked, and an unticked criterion
contradicts a closed issue): use a top-level issue that cites it and say why.

- **Text.** One objective, observable item that names the evidence that will close it
  (a test at a seam, a measured result, a reviewed diff), in the user's language and
  prefixed with where it came from: `- [ ] Pendência (achado da revisão): <what must be
  true>. Evidência que fecha: <evidence>` (`do teste ao vivo`, `dos testes` or `da
  conferência` for the other origins). Several leftovers are several items. A leftover box
  has no `S<n>` id, so give it a label for `checkpoint --slice` (`P1`, `P2`, in order) and keep
  that mapping in the handoff.
- **Approval.** It changes the issue's scope, so, like any update of a published issue, it
  keeps what is there and is shown before it is written (the update rule at the end of
  the Project board section): the exact text, the issue and its place in the section go
  in the batch above and are approved in that single question. Nothing is written before
  the answer.
- **Capture.** Save the body exactly as GitHub holds it, with this command and never with
  a shell redirect (Windows PowerShell re-encodes redirected output, and `--jq .body`
  adds a newline): `python -c "import json,subprocess,pathlib; b=json.loads(subprocess.run(['gh','issue','view','<n>','--repo','<repo>','--json','body'],capture_output=True,check=True).stdout)['body']; pathlib.Path(r'<file>').write_bytes(b.encode('utf-8'))"`.
  The first copy is `.frontlights/issues/<n>/body-before-<YYYYMMDDTHHMMSSZ>.md` (UTC, no
  colon: a colon is not valid in a Windows file name; create the folder first when it
  does not exist) and each later one, with its own stamp, `body-now-<stamp>.md`. Run
  `python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" candidates --config <config> --root
  <project> --issues <n>` (read only) once now: its `criteria.total`, under `candidates`
  or `excluded`, is the baseline.
- **Write.** Build the new body as a copy of the saved one with only the new items
  inserted right after the last item of the section, by an exact-replace edit of the
  copy and never by retyping the whole body; the file tool writes UTF-8 without a
  byte-order mark, and mixed line endings are harmless to GitHub and to the closeout.
  Check the new file against the saved copy before writing: `git diff --no-index
  --ignore-cr-at-eol --numstat <before> <new>` must show no deleted line. Capture the
  body once more right before writing and compare it with the saved copy (`git diff
  --no-index --ignore-cr-at-eol --exit-code <before> <now>`): any difference means
  someone edited the issue meanwhile, so stop and show it instead of overwriting. Then
  write it with `gh issue edit <n> --repo <repo> --body-file <file>`, a literal UTF-8
  file, never an interpolated string. GitHub offers no compare-and-swap, so an edit
  landing between that last comparison and the write is a known limit.
- **Verify.** Run the same closeout command again: `criteria.total` must have grown by
  the number of items added, and the issue stays out of the list as `unchecked_criteria`
  (or `open_children` while a child is open) until they are ticked. Capture the body
  again and compare it with the saved copy with the same flag (`--ignore-cr-at-eol`): the
  only differences are the added lines, inside the section (in a legacy migration, also
  the removed legacy lines). Anything else is a divergence to show and ask about;
  restoring the saved body is a write of its own and needs its own approval.
- **Record.** Put the approved text, the user's literal answer with a reference, the
  saved copies and the verified difference in the handoff, and note the write in the
  authorization's record of GitHub writes when the session has one.
- **Treat it.** The leftover is worked like any other criterion of the family. Tick it
  only with evidence, under the authorization for routine issue updates
  (`references/development.md`), and never to get the issue closed. While one is open,
  the PR cites the issue without a closing keyword (`Closes`, `Fixes`, `Resolves`), in
  its body and in the commit messages, because the merge would close the issue with the
  criterion unticked.

A leftover already kept in a section of its own (a body written before this rule) is
moved into the criteria only when the user asks for it, as a write of this recipe with
its own approval: the open items are added to the criteria (text shown first) and the
same items are removed from the old section, so the only differences are those added
lines and those removed ones. Until then the closeout only warns about it
(`pending_outside_criteria`).

### The gate: no open finding without a destination

Before an issue is reported as reviewed or complete, and before a PR is opened or
updated, and before the merge into the local main, list every open finding of the review, the tests, the live check and any other
verification pass, the ones of earlier rounds included, each with its destination: fixed
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
