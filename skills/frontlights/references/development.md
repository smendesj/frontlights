# Bounded implementation

Read the recorded authorization and the current GitHub issues, and from `docs/security.md` the sections
"Hooks e escritas em `.git/`", "Autorização permanente", "Subagentes", "`authorize` e a main local",
"`homolog sync` e `homolog bundle`", "Registro de autorização e `branch_prefix`", "Permissões do host e
AFK", "Revisão e sobras", "Fechamento e limpeza" (the limits of `closeout.py tick`) and "`serve`, `checks` e o
teste no navegador"; from `docs/protocol.md`,
"Desenvolvimento e release" (the format of the authorization record and of its `monitoring` block), "Registros"
(`plan.json`), "Ponto de retomada e continuação" and "Contexto e conclusão". Stage 6 runs under
the standing authorization (below): the session fills the run itself, announces it in one block and records
the charter without asking. A decision the standing authorization does not cover (a new product decision, an
operation on its denied list, a scope change) goes back to the coordinator's `AskUserQuestion`. Each external
write needs its own authority; local shell access grants none. Run structured authorization checks where
applicable; they are advisory preflight, not sandbox enforcement.

## Standing authorization and the denied operations

The user decided, permanently and for every project, that stage 6 opens without a question: there is no
concurrency question, no stacking question and no implementation authorization question. The session fills the
run itself and announces it in one short block, in the user's language: the issue IDs, repository, concurrency,
the branch and the order of the slices of each issue, stacking when a family exists, worktree base and branch
prefix, the verification argv and the stop conditions. The user may change any of it at any time, and a change
goes back through `AskUserQuestion`.

**The charter.** Record it in `.frontlights/authorization.json` with the user in `approved_by`,
`confirmed_by` and `monitoring.confirmed_by`, `"autorização permanente (docs/security.md)"` in `approval_reference` and an `expires_at` at
most 24 hours ahead. Its `monitoring` block is `mode: "local"`; `phone_connected: true` only when the user
states, unprompted in this session, that the phone received and answered. Local files record consent but cannot
enforce it. Before recording a new charter over one that exists, keep the current one as
`.frontlights/authorization-<YYYY-MM-DD>-issue-<n>.json` (never delete it): `release-plan`, `bundle`, `closeout`
and `cleanup` read every `.frontlights/authorization*.json` to map the issue branches, prefixes and worktrees, and
an issue still waiting for its release loses its mapping when its charter is overwritten.

**Covered**, for the issues of the family or batch at hand: editing, testing, committing, the covered merges
below, running migrations on the local development database, creating and removing test data through the
product's own endpoints, commenting on the issues and ticking acceptance criteria with evidence. Nothing of an
issue goes to GitHub before the release: the branches of the issue and of its slices stay local, the preview
branch stays local too, and the only pull request is the release's, offered at the end of each homologated
issue. The questions of the work itself (the watched run, failures, the findings batch, a new product decision)
are still asked.

**Covered merges.** The run makes these merges on its own, and only these:

- a base into an issue's own branch;
- a slice's branch into the branch of its own issue when its loop closes;
- the branch of the issue (or of the slice it depends on) into a slice's branch, to bring it up to date;
- a verified child's branch into its parent's branch;
- a family's or batch's verified branches into a local integration branch that stays local;
- `origin/<base>` into the local main by `homolog sync` at the start of stage 6 (a conflict is undone and
  becomes a question);
- the local main and the branches of the issues in progress into the preview branch by `serve preview
  refresh` (a conflict is undone and becomes a question);
- the branch of the issue into the local main once its watched run is answered or not needed ("Into the local main").

**Work without an issue.** The Direct path, or a Short one that publishes no issue, is homologated the same way
in a project with a remote. Its charter lists a slug of its own (lower-case letters, digits and hyphens, up to 64
characters) in `direct_ids`, and its `worktrees` entry carries `direct` in place of `issue` (a slice entry adds
`slice`, as for an issue). In the rules of this stage "the issue" reads as that work and "the branch of the issue"
as its branch; its records live in `.frontlights/direct/<branch, slashes as dashes>/`, `authorize` takes an
operation that names that `direct` (never `issue` too), and `release-plan` lists it in `releaseDirect`.

**Denied operations, asked one at a time** with `AskUserQuestion`, "Sim" first and "Não" second, naming the
exact operation and the exact command: merging a pull request, closing an issue (the one exception: a `Closes #n`
line of the release's pull request, for an issue of the `closes` of `release-plan`, closes it only through that
approved merge; "The release", below), changing the board (adding an
item, moving a card, editing a field), deploying or publishing to production, editing a migration already
registered (on the base branch or applied anywhere but the local development database), writing the remote main
(`origin/main`, the base branch on GitHub) or a protected branch (the local main is written only by the covered
merge, with its watched run answered or not needed), turning on a setting, key or flag in production, and deleting anything but
the test data the run created and the cleanup of merged work (`references/closeout.md`, step 5: the worktrees and
local branches of the issues, slices and release already merged into the approved base, removed without a question,
never a remote branch). Run it only after "Sim" and record the answer verbatim in the handoff. A "Sim"
covers that one operation; another operation, another PR or a later moment gets its own question. "Não",
silence or any other answer leaves it undone, and the work goes on without it. The approvals that have their
own stage (the issue's text, issue plan and publication, closeout and summary) keep them. The
host's own permission prompts are not Frontlights' to remove and still apply.

## The start of stage 6: the sync of the local main

The sync runs in the main worktree of the project (where the local main is checked out), in a project with a
remote, before the first branch of the run is cut; a project without a remote (`repository: null`, no
`origin`) has nothing to sync, and the session says so in one line. The helper is `scripts/homolog.py`, reached as
`python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog <operation> ...`; it prints one JSON object with
`ok`, `exitCode`, `operation` and `message`: exit code 0 done, 1 refused or failed, 2 a question for the user.
The local main is never pushed to the remote main: its content leaves only under the release branch name, by the
refspec push of the release ("The release", below), and `origin/<base>` stays a denied write.

**The sync.** `homolog sync --root <main worktree> --base <base> [--remote origin]` is the covered merge of
`origin/<base>` into the local main: it requires the main worktree to have `<base>` checked out, no tracked
change pending and no merge in progress (exit code 1 names what blocks; untracked files are fine), runs
`git fetch <remote>` and `git merge --no-edit <remote>/<base>` (a fast-forward when possible), and answers
`before`, `after`, `advanced`, `fastForward` and `remoteTip`. A conflict is undone on the spot (`git merge
--abort`, the worktree clean again, `HEAD` back at `before`) and comes back as exit code 2 with `conflict:
true` and `files`: the session asks with `AskUserQuestion` ("Resolver o conflito agora na worktree principal"
/ "Seguir sem sincronizar") and never resolves a conflict in the local main silently. The sync never pushes,
never uses `--force`, `reset` or `rebase`, and runs again before the release. Record the result (advanced or
not, the two commits, a conflict and its answer) in the handoff.

**The preview.** Only in a project whose `.frontlights/config.json` has a `preview` block (without the block, nothing
of this runs, said in one line), and after the sync: before the first slice, run `serve preview refresh` in the main worktree with every branch of an issue
in progress as `--branch`, open its `baseUrl` once in a tab of Claude in Chrome and tell the user. The list: each
issue branch in the `worktrees` of the `.frontlights/authorization*.json` records whose issue is not closed (slice
branches stay out), plus each one in the `merged` of `serve preview status`, minus each one the local main already
holds (`git merge-base --is-ancestor <branch> main`), and only those that exist locally (`git rev-parse --verify
--quiet refs/heads/<branch>`); at the very start it may be empty, and the session never takes another issue's work
in progress out of the preview. From then on the preview follows the work (below,
"Slices in order"); it stops only when the user asks, and the session that finds it already up (its record)
refreshes it instead of starting another one. The tab belongs to the user, never to a test: the session opens it once and leaves it
to the user, outside the rule of the disposable window, and the watched run never uses the preview nor its ports. The commands, the
record and the log are in `references/browser-testing.md` ("Environment: `serve`"). Record in the handoff the
preview's branch, the branches merged into it and the last refresh.

## Slices in order: one issue branch, one worktree per slice, one merge into the local main per issue

An issue is worked on one issue branch, cut from the local main (the base branch of the charter,
checked out in the main worktree, never `origin/main`: `git branch <branch_prefix>issue-<n> main`),
which stays local and is never pushed, and delivered by one merge into the local main once its watched
run is answered or not needed ("Into the local main", below); each of its slices (the boxes
of its acceptance criteria, stage 5) gets its own worktree and branch, `<branch_prefix>issue-<n>-s<k>`,
cut from the branch of the issue at its current tip (`git worktree add -b <branch_prefix>issue-<n>-s<k>
<path> <issue-branch>`) and named in the charter's `worktrees` with its `slice`, so that `authorize`
accepts on that worktree only an operation that names the same slice; the slices are worked
in dependency order: independent slices run at once (no `Depende de` between them and no file in
common, judged before their loops from the `Seams:` and `Camadas:` of their boxes, each in its own
worktree with its own implementer; a collision found during a loop stacks the later slice on the
earlier one), and a slice that depends on a slice
still open is cut from that slice's branch instead (stacked: `"base": "<slice-branch>"` in its
worktree entry, named to `browser-gate` with `--stacked`, and merged into the branch of the issue
after the slice it depends on; once that slice is merged, the stacked one brings the branch of the
issue into its own branch, `git merge <issue-branch>` in its worktree, one of the covered merges
below, and its `--stacked` target becomes the branch of the issue, so the earlier slice's branch may
go). A conflict in the merge of a slice into the branch of the issue is resolved by this session in
the issue's worktree, committed there, and shown as part of the diff of the issue (to the independent
reviewer too, when the user asked for a review). Each slice is, by default, one TDD loop at its own seams
(the `Seams:` under its box; "Which tests run when", below), one checkpoint
(`checkpoint --slice <id>` of `frontlights.py`, saved as `checkpoint-<id>.json` in the issue's records,
one per slice worktree, which `resume` echoes so the next window starts at that slice, in that
worktree) and, when its loop closes with evidence (by default, its own tests and the affected test
modules green, and the measured commands; in a run "só com teste assistido", its change done, with no
test written or run), the slice branch is merged into the branch of the issue (`git merge --no-ff
<branch_prefix>issue-<n>-s<k>` in the issue's worktree, one of the covered merges, "Stacking" below);
a box without a screen (its persona `sem tela`, or every box when `browser-gate` says `not_needed`) then
runs the walkthrough of its box and writes its `.md` ("Into the local main", below), and the `.md` is the evidence
of the tick; a box whose walkthrough has a screen waits for the "Aprovado" of the watched run, which walks it
(`browser-testing.md`); then comes the tick of its box: capture the body, tick that line only, run
`closeout.py tick-check` before and after the write (`closeout.py tick --config <config> --root <project>
--issue <n> --box S<k>` does this whole cycle in one command and keeps the previous body in
`.frontlights/issues/<n>/`), and leave a short comment on the issue with
the commit and the commands; then `serve preview refresh` with the branches of the issues in progress, in a
project with a preview ("The start of stage 6"), so the slice reaches the user's tab; a conflict is a question
and a broken build goes back to the slice that owns the file before the next one starts. The session may end in the middle of an issue: the handoff names
the slice in progress with its worktree, and the slices already ticked, and a fresh session resumes at the first
open box, in order, in that slice's worktree. Slices run in parallel inside an issue and between issues; the fan-out rule of
`SKILL.md` keeps the agents busy around each open slice (Dispatch and ownership, below). The watched
run stays one per issue, when the last slice that changes the screen closes its loop, and it is the only gate of the
merge into the local main; a broader suite and an independent review run only when the user asks for them ("Which
tests run when"; "Review, checkpoints and renewal"). The stacked wave
and the family integration below (children merged into the parent's branch, and the family entering
the local main as one) apply only to a family that already exists (an issue with
sub-issues published before this rule); a slice stacked on another slice uses only the branch cut,
the `base` of its worktree entry and `--stacked`, as said above.

**Which tests run when.** TDD per slice is the default practice: each slice's loop writes and runs its own
tests at its seams, plus the test modules the slice touches and the type checks. These tests are evidence, never a
gate: no suite holds back the merge into the local main or the release. When the user asks to implement "só com teste
assistido", the session writes and runs no tests in that run: the slices skip the red → green loop (their seams stay
the place a later test would go), the announcement and the handoff say so, and the watched run is the evidence of the
issue. A broader suite runs only when the user asks for one, through the optional tools: `python
"${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog suite --root <issue-worktree> --config <config> --issue <n>
--mode impact|full --base <base>` (the argv of `homolog.suites` in `.frontlights/config.json`, or `--argv` and
`--timeout-seconds`), judged by `homolog suite-gate`; in the Frontlights repository, `python tests/suite.py`
(`--impact <base>` runs only what the diff touches, by the selection of `tests/pre_commit.py`; with
`FRONTLIGHTS_SUITE=rapida`, Windows only, it skips the modules that start real processes and ports; `--report
<file>` writes the JSON of the run) or `python -m unittest discover -s tests -v` for the whole. `<config>` is always
the main worktree's `.frontlights/config.json`, by its absolute path: it is usually untracked and absent from an
issue's worktree. A suite that ran is recorded in the handoff with its command, count and exit code, and a red one is
a finding (the gate on the findings, below). No whole check is required anywhere: a project's CI, when there is one,
is neither expected nor a gate, and the watched run of each issue is the evidence.

**A parked slice.** When a slice is parked (it waits for something the session cannot do: a
decision, a credential, another team's endpoint), write right below its open box, as the last
sub-item of its box and more indented than it, the line `- Bloqueada: <what is missing and from
whom>`, by the write rule of the leftover (body captured, append only, difference checked,
reread); the RoadS reads that sub-item as the reason of a blocked part of the delivery. When
the slice is released, remove exactly that line before the box is ticked: the only removal
allowed in a body besides the move of a legacy section, checked by the difference (nothing
else added or removed). The closeout
keeps counting the box as open while the line is there, because a sub-item without a box is
never a criterion.

## Dispatch and ownership

Inspect Git status/remotes/worktrees and current issue acceptance criteria. For a family
that already exists, the scope of a dispatch is the family: the issue and all its open
sub-issues (`SKILL.md`, "An issue and its sub-issues move together"), each with its own branch
and worktree; the parent never goes alone unless the user chose that. Create one
isolated branch/worktree per issue from its approved base (the approved base
branch, or its dependency's branch when stacked, see below) using native
Git tooling; verify the resolved path, actual branch and common repository before
editing. Never reuse a dirty shared checkout, discard changes or write a protected
branch. Recheck branch/worktree identity before each mutation boundary.

Branches use the charter's `branch_prefix` (default `claude/`). Choose the
worktree base before recording the charter: when `inspect` reports
`path_risk` other than `ok`, use a short base such as `C:/wt/<project>` and name
it in the announcement instead of discovering a
`'$GIT_DIR' too big` failure afterwards. Any other change of base after
the announcement goes back to the user through `AskUserQuestion`.

Refresh the plan from GitHub and run `frontlights.py schedule --plan <file> --limit
<approved-limit>`. The result is a recommendation, not proof of authority. Start
all eligible non-conflicting issues up to the ceiling with supported generic
subagents or separate supported sessions, all launched in one message. Give each a
bounded outcome, owned paths, tests, checkpoint path, the rules of the stage it serves
(test data, masked secrets, the user's language) and no authority to expand scope. A
worker never calls `AskUserQuestion`, writes GitHub, merges or runs a denied operation:
it reports the question or the write it needs, and this session asks or does it under
the stage's approval. Tell workers they share the codebase and must preserve others'
changes. Hide internal worker names. If concurrent sessions/tools are unavailable,
report the capacity limitation. Do not silently serialize for convenience. Isolate
ports, databases and test data as well as Git. Recompute readiness and refill free
slots after each completion. A worker's report is a claim: read the diff and rerun the
commands it names before it counts as evidence.

**Fan out inside an issue.** The independent slices of one issue go at once, one implementer per open
slice, each in the slice's own worktree (Slices in order, above), and the agents around them do
not wait. While the implementers run the TDD loops of the open slices, dispatch in the same message read-only workers that
prepare the next slice (the code at its seams, the conventions, a draft of its first red
test, reported as text the implementer rewrites in its own loop) and, when a loop closes,
run at once the type checks and the other measured commands that share no resource, and a broader
suite when the user asked for one (a test module that shares a port, a database or a reservation
folder with another runs one at a time, as the project's own rules say). The driver of the watched
run is a worker of its own, dispatched together with whatever else is ready, and so is the
independent reviewer when the user asked for a review; the reviewer is never the implementer. Only one worker edits a slice's worktree at a time,
and only it commits there; the merge of a closed slice into the branch of the issue is this
session's: the readers edit nothing, and a worker that needs a file outside
its owned paths stops and reports.

An issue is `verified` for dependency readiness only when its acceptance evidence
is current and its required changes are present in the dependent issue's approved
base. An unmerged PR alone does not meet this condition, unless the dependent's
approved base is that very branch (stacking, below). Cherry-picks and stacked bases
need the recorded repository-operation authorization; without it, park the
dependents. `schedule` only reads `status`, so it cannot see an issue that depends
on two unmerged branches: that check is manual (below). With many ready issues that
share ownership or use `*`, its exact search can take minutes (about 150 s for 23
issues), so give the command a longer timeout.

## Stacked branches: parent and children without waiting for the merge

Making children wait for the parent to reach the base serializes the family behind a human
step. So, in a family that already exists, whenever an issue of the family depends on another one (a child that
lists its parent in `Depends on`, or a sibling chain), stage 6 **stacks** the
dependent on its dependency's branch. Under the standing authorization this is not
asked: the announcement says it. The choice "Como as filhas se apoiam no pai?" comes
back as a question only when the user asks to change it, with "Empilhadas no pai (Recomendada)" first (each child branches from the
parent's branch and, once verified, is merged into it) and "Esperar o merge do pai" second
(each child starts from the local main once the parent is in it). No branch of the family is
pushed and no pull request is opened for the parent or a child: the family enters the local main as one,
through the parent's branch, once its watched run is answered or not needed ("Into the local main", below), and reaches
GitHub with the release. Record the stacking in the
authorization with the repository operations it needs: a branch cut from a branch that is not the base, and
the covered merges of "Standing authorization and the denied operations" (above), which are the only merges it
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
  alone (then the child starts over from the local main once the parent is in it, as in "Esperar o merge
  do pai").
- A conflict on anything beyond the parent's own content, or a dependency closed without being
  merged, is a stop condition: park the child and ask.

## Integrating a family before the local main

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

## Test-driven development

TDD is the red → green loop, the default practice of every slice and never a gate ("Which tests
run when"; a run "só com teste assistido" skips it). This section is the reference that makes that loop
produce tests worth keeping: what a good test is, where tests go, the
anti-patterns and the rules of the loop. Every subsection applies on every cycle:
consult them before and during the loop, not after.

When exploring the codebase, read `CONTEXT.md` (if it exists) so test names and
interface vocabulary match the project's domain language, and respect ADRs in the
area you're touching.

Follow the conventions recorded in the issue's `## Decisões de implementação` (`## Abordagem e
convenções` in issues published before this section existed, `## Approach and conventions`
before 0.28.1) and
in the discovery log: structure, naming, error handling, libraries and test
style of the surrounding code. Break a convention only where that section names
the approved break. Finding mid-work that the pattern is concretely worse, or
that the approved approach does not fit, parks the issue and returns the
question to the coordinator's `AskUserQuestion`; never switch approach or
pattern silently.

### What a good test is

Tests verify behavior through public interfaces, not implementation details. Code
can change entirely; tests shouldn't. A good test reads like a specification:
"user can checkout with valid cart" tells you exactly what capability exists, and
it survives refactors because it doesn't care about internal structure. See
[tdd-tests.md](tdd-tests.md) for examples and [tdd-mocking.md](tdd-mocking.md) for mocking
guidelines.

### Seams: where tests go

A **seam** is the public boundary you test at: the interface where you observe
behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** The seams under test are part of each issue
(`## Decisões de teste` in `templates/issue.md`, `## Seams sob teste` or `## Seams under test` in
older issues) and
were approved when the issues
were published. You can't test everything; agreeing the seams up front is how
testing effort lands on the critical paths and complex logic instead of every
edge case. Before the first test, restate the issue's seams in the handoff. No
test is written at an unconfirmed seam. If the issue lists none, a listed seam
does not exist or cannot observe the acceptance behavior, or the shape of the
interface is itself in question (how deep the module is, where the seam belongs,
what it should expose), park the issue and return the question "What's the public
interface, and which seams should we test?" to the coordinator's
`AskUserQuestion`. Continue independent issues meanwhile.

### Anti-patterns

- **Implementation-coupled**: mocks internal collaborators, tests private
  methods, or verifies through a side channel (querying the database instead of
  using the interface). The tell: the test breaks when you refactor but behavior
  hasn't changed.
- **Tautological**: the assertion recomputes the expected value the way the code
  does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way,
  a constant asserted equal to itself), so it passes by construction and can
  never disagree with the code. Expected values must come from an independent
  source of truth: a known-good literal, a worked example, the spec.
- **Horizontal slicing**: writing all tests first, then all implementation. Bulk
  tests verify _imagined_ behavior: you test the _shape_ of things rather than
  user-facing behavior, the tests go insensitive to real changes, and you commit
  to test structure before understanding the implementation. Work in **vertical
  slices** instead: one test → one implementation → repeat, each test a **tracer
  bullet** that responds to what the last cycle taught you.

### Rules of the loop

- **Red before green.** Write the failing test first, run it and capture the
  actual expected failure, then write only enough code to pass it and rerun the
  focused tests. Don't anticipate future tests or add speculative features.
- **The red must be behavioral.** An import error or broken harness is not the
  intended red. Fix the harness and obtain a meaningful failing assertion.
- **One slice at a time.** One seam, one test, one minimal implementation per
  cycle, each tied to one acceptance behavior.
- **Refactoring is not part of the loop.** It comes after it ("Review, checkpoints and
  renewal", below), not in the red → green implementation cycle.
- **Evidence is real.** Preserve commands, exit codes, counts and output paths.
  Never invent failure evidence for a nontestable documentation change; state the
  exception and verify the relevant behavior another way.

### After the loop

Run the actual type checks discovered from repository/CI, and the relevant broader tests by default
(outside a run "só com teste assistido"; a whole suite only when the user asks);
do not assume npm scripts. If no type checker exists, say so and record applicable
syntax/build checks. Inspect the full vertical behavior, diff, regressions and
acceptance coverage. Tests may execute arbitrary code; native permission and
sandbox controls still apply. Unexpected effects stop the affected issue.

When anything the issue changes is visible on the screen (its `## Navegador e testes ligados`
says so, or `frontlights.py browser-gate` finds it in the diff), the watched run belongs to the
issue as a whole, not to this slice alone: [browser-testing.md](browser-testing.md) asks "pronto
para assistir?" once the last slice of the issue that changes the screen has closed its loop and every closed slice is merged into the branch of the issue,
and before an independent review of any of them, when the user asked for one, and ends with the user's choice of watching
again, approving, asking for a change or going on; its records join the evidence below. Any brief that hands the
run to a subagent carries that reference's rule on test data: create what the flow needs, remove it afterwards.
Once the question is due and until the user has answered, the run is the `teste_assistido` pending of the checkpoint;
while a screen slice is still in its loop it is not (the handoff lists the open slice).

## Review, checkpoints and renewal

The independent review runs only when the user asks for one: it is not dispatched by default and is not a gate of
the merge into the local main nor of the release. When the user asks for it on an issue that changes the screen, it
waits for the issue's watched run: `browser-gate` has to say `answered` (exit code 0) before the reviewer is
dispatched (the points where the question comes out are listed in browser-testing.md); exit code 2 at those points
is a question to the user, never a skip. `references/review.md` stays its standard.

When a review runs, the reviewer inspects the current diff and the test evidence and must not author the changes
under review. Bind review to `frontlights.py evidence --root <worktree>` hashes/HEAD and save that output with the
review result (`.frontlights/issues/<n>/review.json`). Run `frontlights.py review-gate --root <worktree> --review
<review.json>` before reporting an issue as reviewed: exit code 0 means the review still covers the code, exit code
2 means it is stale. Any commit, edit or new file after the review makes it stale (bringing a base into the branch
included), whatever its size; a stale review is never reported as reviewed, and whether to review again is the
user's call. A review the user asked for that no independent reviewer can do is reported as "implementado,
aguardando revisão independente", never as reviewed. Do not manufacture reviewer identities or approvals.
Classify the findings that do come up (of the watched run, of a review the user asked for, of tests and live checks
that ran) by the destination ladder of the Follow-ups section in `issues.md` (same PR, a new acceptance criterion in
the source issue, top-level issue only for new scope; never a new sub-issue), decided as one batch (the baixos of a
finished review take the default of "When the review is done", below).

**The reviewer's brief.** The brief that dispatches the independent reviewer names `references/review.md`, the
reviewer's standard (what a finding is, its severity, what is only style, the rounds and the report), the issue,
its base and, from the second round on, the tip of the previous round, the base it had and its findings. The standard belongs to
the reviewer: the implementer's brief names the issue, its seams and its tests, and leaves `review.md` out.

**When the review is done.** A round is one dispatch of the reviewer on the current tip. The review of an issue is
done at the first round that reports 0 sérios and 0 médios. The baixos still open then go to the findings batch,
each with the proposed destination of a new acceptance criterion of the source issue (a top-level issue when there
is no source issue with a criteria section, or it is closed; the ladder of `issues.md`), and the batch also offers
"Corrigir os baixos agora". A sério or médio is fixed by the author, and the next round reviews that delta
(`review.md`, "Rounds"). There is no limit of rounds to keep: after a round that still reports a sério or médio,
ask with `AskUserQuestion` "Mais uma rodada" or "Dar destino pela escada" (a new acceptance criterion of the source
issue or a top-level issue, in the findings batch); a sério or médio without a destination keeps the issue out of
the local main by the gate on the findings, below. The handoff records each round: its HEAD and its counts.

**Gate on the findings.** Before an issue is reported as reviewed or complete, and before
the merge into the local main and before a PR is opened or updated, every open finding that came up (the watched run,
a review the user asked for, tests that ran, a live check, any other verification pass) has a destination GitHub tracks, or is fixed, or is shown as not a
defect with its evidence, or is dropped by the user's explicit answer: the gate of the
Follow-ups section. A line in the PR body, a comment or the chat is never a
destination, so "cited in the PR" does not pass the gate. A finding
left unfixed leaves by the ladder: most often as an acceptance criterion of the source
issue, which keeps the issue open until the leftover is treated, completed and ticked
with evidence; or as a top-level issue. While such a criterion is open the issue is not in the `closes` of
`release-plan`, so the PR cites it without a closing keyword, in its body and in the commit messages ("The
release", below).

Refactoring comes after the loop. The author, or a reviewer the user asked for, may propose refactors of the
green code; the author applies them without changing behavior or adding tests at new seams, reruns the slice's
tests (outside a run "só com teste assistido") and the type checks, and records fresh evidence. The new hashes make a
review already done stale, and `browser-gate` says whether the watched run still covers the code.

Save compact `templates/handoff.md` and a machine-readable checkpoint before each
session renewal. Include the issue URL and acceptance snapshot, repository map,
decisions, changed files, commands/results, review evidence when a review ran, blockers and next
concrete step. `frontlights.py checkpoint` records the issue snapshot, handoff and
current Git evidence, carries open obligations with `--pending teste_assistido` (a watched run that is due and unanswered)
and the slice in progress with `--slice <id>`;
`frontlights.py resume` detects drift without overwriting it, lists those obligations
first, so the next window starts by asking the watched run, and echoes the slice, so the
next window continues at that box.
Read both the human handoff and current issue/diff in the fresh session.

Check context using measured accumulated session usage plus a conservative next
step reserve, not remaining context after compaction. Target renewal near 100k;
stop before 150k. Unknown telemetry means no unattended continuation. While a watched run is
due and unanswered, pass `--pending teste_assistido` to `context`: on `handoff` or `stop` it also answers
`ask_before_continuing`, and the question goes out before more is spent. The helper
checks reported numbers, not the host's actual token meter. If the host cannot
enforce renewal, explicitly report that hard-cap AFK acceptance is unproven.

Update GitHub checkpoints/status only if authorized and supported by current
evidence; tick an acceptance criterion in the issue body only with evidence for it
(a test, a measured result, the watched run, a reviewed diff), because the closeout of stage 7 trusts
the ticks; a criterion born from a finding is ticked the same way, once the work it
names is done and its evidence exists. Closing an issue is never part of this: it has
its own approval (`references/closeout.md`), and its card goes to Done by the board's own "Item closed" workflow. The release's pull request is covered by the standing authorization and still goes through
the host's native approval; the branches of issues and slices stay local. The run merges only by the covered
merges, and anything on the denied list runs only after the user's "Sim" to its own question ("Standing
authorization and the denied operations", above). Park
blocked issues with the precise pending question and continue independent ones.
Report each issue's state, branch/PR, changes, the watched run, the walkthroughs run without a screen (the table of
the handoff), the tests and the review when they ran,
the findings left unfixed with the destination of each, the count of its lines in `.frontlights/pitfalls.md` (criteria that entered after the approval: `references/issues.md`, "A pitfall line"), remaining risk and next
action. Leave worktrees and evidence intact for recovery.

## Into the local main: the watched run

The local main of the project (the base branch of the charter, checked out in the main worktree) is the
homologation bench: it accumulates every issue whose watched run was answered (or was not needed), and nothing of it
reaches GitHub before the release. The remote main (`origin/main`) is never written outside the release's pull
request, and `authorize` tells the two apart: the local main is the only target of the covered merge
below, and a target with a slash (`origin/main`, `upstream/main`) is refused as the remote main.

The watched run is the only gate of stage 6: no impact suite and no review is required. When the last slice of the
issue is merged into the branch of the issue, the steps run in this order:

1. **Bring the local main in first.** In the issue's worktree, `git merge main` (one of the covered merges,
   a base into the issue's own branch), so the tip of the branch already contains the local main and the
   merge below cannot conflict. A conflict is resolved here, in the issue's worktree, committed there and
   shown as part of the diff of the issue.
2. **The gate, the watched run.** `frontlights.py browser-gate` answers `answered` (the user approved or said
   to go on) or `not_needed` (nothing on the screen changed), exit code 0; `pending`, `stale`,
   `contradiction` or `unconfigured` is the question of `browser-testing.md`, never the merge.
3. **Without a screen, the walkthroughs.** When `browser-gate` says `not_needed`, and for each box whose persona
   is `sem tela` in an issue with a watched run, running the walkthrough of each box (its `Roteiro:` lines,
   `references/issues.md`) is a condition of the merge into the local main, with no new question. The walkthrough
   runs when the loop of its slice closes ("Slices in order", above): its steps at the base of the issue and at the
   commit of the slice, and one file per box, `.frontlights/issues/<n>/walkthroughs/S<k>.md`, with a header (the
   issue, the box, the persona, the date in São Paulo time, the steps, the base and the commit it ran on), a section
   `## Antes` and a section `## Depois`, each with one line on what the steps showed and their output, masked (no
   login, password, token, real endpoint or local path), in a code block. A `## Depois` that differs from the
   `depois:` of the box is a failure of that slice, which goes back to its loop. Here the session only checks the
   files: a box without its file keeps the issue out of the local main until it is run and written. The summary
   table of the handoff (box · before · after · file) carries one row per file. `authorize` does not read these
   files and its gates stay as below.
4. **The check and the merge.** Write the operation and run `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py"
   authorize --charter .frontlights/authorization.json --operation .frontlights/issues/<n>/merge-local-main.json`,
   with `kind` `merge_into_local_main`, the issue's worktree and branch, `target` the base branch of the
   charter and `gates` `{"browser_gate": "answered"}` (or `not_needed`), the only gate;
   `examples/operation-merge-local-main.json` shows the shape. With `scope_check: pass`, in the
   main worktree and on the local main: `git merge --no-ff <branch_prefix>issue-<n>`. A refusal names the gate
   or the target, and the session asks the user with `AskUserQuestion` instead of merging; it never edits the
   gates to make them pass. Work without an issue (the Direct path, or a Short one that publishes none) goes
   the same way: its charter lists the slug in `direct_ids` and its `worktrees` entry carries `direct` in place
   of `issue`, the operation names that `direct` (never `issue` too) and is kept in
   `.frontlights/direct/<branch, slashes as dashes>/merge-local-main.json`, and the merge is `git merge --no-ff
   <its branch>`.
5. **Back it up.** Weeks of homologated work may live only in this clone, so right after the merge run
   `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog bundle --root <main worktree> --config
   <config>` (covered; the only write the run makes outside the project, and only into that folder): it writes `<project>-<date>-<time>.bundle`, the local main and the work
   branches of every `branch_prefix` in the authorization records (`.frontlights/authorization*.json`; `claude/`
   when there is none; `--prefix` names one prefix alone), into the folder named by `homolog.backupDir` in `.frontlights/config.json`
   (an absolute path of the user's, typically a synced folder; `inspect` refuses a relative path, `..` or `~`,
   and the real path never enters a repository), verifies it with `git bundle verify` and reports `path`,
   `refs`, `bytes`, `prefixes`, `prefixSource` and `skipped`; say in one line how many records `skipped` counts
   when it is above zero (a broken record may leave its branches out of the backup). The folder must already exist; nothing else is written there and old bundles are never
   deleted. Exit code 1 with `configured: false` means no folder is configured: say so in one line, name the
   key, ask nothing and go on; any other refusal (a missing folder, a junction in its path, a Git failure) is
   said in one line and recorded in the handoff as a backup not taken.
6. **Record it.** The handoff's line "Merge na main local" takes the watched run with its evidence, or the walkthroughs run without a screen with their table (and the
   tests or the review, only when they ran), the output of `authorize`, the commit of the merge and the bundle's path (or "sem backup configurado");
   the branch of the issue stays local, never pushed.

`authorize` is a preflight, not a barrier: it reads no Git and does not prove that the watched run was answered
(`browser-gate` does), the host's own permission prompts still
apply, and a model that does not call it is not stopped by it. The issue is homologated once it is in the
local main; it closes only with the release that carries it merged (stage 7).

## The release: from the local main to GitHub

The local main accumulates homologated issues; nothing of them reaches GitHub until the release, offered by the
session at the end of each homologated issue (right after the merge into the local main and the bundle). The user
can decline ("Agora não") as often as they like: the work stays in the local main, and the next homologated issue
offers the release again with everything accumulated.

- **Plan it.** Run `homolog sync` once more (the local main may be behind `origin/<base>`; a conflict is a
  question, as at the start of stage 6), then `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog
  release-plan --root <main worktree> --base <base>`: it reads the issue branches from the authorization records,
  lists the issues whose branch is in the local main and not yet in `origin/<base>` (`release`), the work without
  an issue in the same state (`releaseDirect`, from the entries with `direct`; `directs` has the detail), the commits
  `ahead` and `behind`, and names the branch `<branch_prefix>release-<date>`: the prefix of the newest authorization
  record by `issued_at` (records without a valid `issued_at` rank below those with one, and ties go to the last
  file name; `claude/` when there is none;
  `--prefix` names it alone; `prefix` and `prefixSource` say which), the date in São Paulo, and `-2`, `-3` when the name is taken by a local or remote-tracking branch (GitHub deletes the head branch of a merged pull request, and the name is free again once `git fetch --prune` drops its ref). Exit code 2 says there is nothing to release or that the local main is behind and
  must be synced first: say so in one line; `ready` means there is something to release and the local main is not
  behind. Exit code 1 without `origin/<base>` (or when Git cannot count the commits): run
  `homolog sync` first. It also reads GitHub (read only, with the `repository` of `--config`, default
  `<main worktree>/.frontlights/config.json`) for `closes`: the top-level issues of `release` with every box of
  their acceptance criteria ticked, no open sub-issue and no open leftover outside the criteria (`pendingOutside`
  0); each issue of `release` in `issues` shows `state`, `level`, `parent`, `criteria` (ticked and total),
  `openChildren`, `pendingOutside` and `closing` (true, or the reason). Without a GitHub read (no config, no
  repository, gh failed) or with a base that is not the repository's default branch (GitHub closes by keyword only
  on a merge into it), `closes` is empty and `closesReason` says why: when in doubt, no `Closes`. `closes` never
  changes `ready` or the exit code. It writes nothing.
  No suite is required for the release (no whole check is: the watched run of each issue is its evidence); the
  whole suite on the local main (`homolog suite --release --mode full`, judged by `homolog suite-gate --release`) runs
  only when the user asks for it, and a red one is then a finding with a destination by the ladder.
- **Offer it.** Show the issues of the release (number and title) and the work without an issue (its slug) and ask
  with `AskUserQuestion` "Lançar a release com as issues #a, #b agora?" (naming the slugs too, when there are any),
  with "Sim, lançar" first and "Agora não" second; one question per release.
- **Branch and pull request (covered).** On "Sim", in the main worktree: `git push origin main:refs/heads/<release branch>`
  (one push of the local main's tip to the release branch name on GitHub, `<base>` in place of `main` on the left
  when the base has another name; never to the remote main, and no local release branch is created; the release
  branch is the only branch of the flow that is pushed), then `gh pr create --base <base> --head <release branch> --title "Release <date>: issues
  #a, #b" --body-file <file>` (the title names the slugs of the work without an issue too: "Release <date>: issues
  #a; melhoria-x", or only the slugs when the release has no issue).
  **When the host refuses the refspec push.** The host's permission controls may refuse it (a user rule such as
  "never push to main" may read `main:refs/heads/...` as a push to main): then ask with `AskUserQuestion`
  "Lançar pelo caminho antigo, com a branch local <release branch>?", "Sim" first and "Não" second, and on "Sim" take
  the old path: `git branch <release branch> <base>` and `git push -u origin <release branch>`, then the same
  `gh pr create`; the cleanup removes that local branch once it is merged (`references/closeout.md`, step 5). On
  "Não" nothing is pushed and the work stays in the local main. The body follows `templates/pr.md` (the model of the pull request), in the user's
  language, with the project's domain vocabulary: **Resumo** and **Evidência** once per issue (what it delivers with the smallest visual that makes its
  point clear; before and after, from the prints of each issue's watched run, its gate (the watched run), and the tests of
  its checkpoints and the independent review only when they ran, records that already exist, never invented; a print is cited by its file
  name and its folder in the issue's worktree (the lead issue's for a family), with one sentence of what it shows, never an absolute path, an
  attached or committed image, a login or a person's data) and the **Risco do merge**
  once, consolidated for the whole release (a one-way door when a migration or deleted data is in it, a two-way
  door otherwise, and the blast radius); it cites the issues by number, and the body of the pull request is never
  the destination of a finding (the gate on the findings, above). **`Closes #n` only from `closes`.** The body
  carries one `Closes #n` line per issue of the `closes` of the last `release-plan`, copied from that list, never
  counted by hand (right before `## Resumo`, plain lines outside any code fence, the place `templates/pr.md`
  fixes); every other issue (a sub-issue, an open box, an open sub-issue, a leftover outside the criteria, or every
  issue when `closes` is empty) is cited by number without a closing keyword (`Closes`, `Fixes`,
  `Resolves` or a variant of them), in the body and in the commits, and follows the closing question of stage 7.
  The merge itself stays a denied operation: the `Closes #n` lines close their issues only through the merge the
  user approved, and only issues whose criteria are all ticked.
- **Wait for the merge.** Opening the pull request does not end the work, and the session does not expect to be
  told that it was merged. By default, as soon as the release's pull request is open, the session waits for the
  user's merge. The user can say "não aguardar" at any time: the wait ends and the closeout question of the next
  session picks the work up. One line to the user, in their language: which pull request the session waits for
  and what happens at the merge. In the handoff (the `Release` line): the pull request number with its issues,
  head and base branch, the approved base, and when the wait began.
- **Offer the merge when the PR is ready.** The release's pull request is ready when the watched run of every
  issue in it is recorded (answered or not needed), the pull request has no conflict with the base and no finding
  lacks a destination. Another issue entering the local main does not make the pull request unready.
  Then ask, under the denied-operations rule, "Mesclar a PR #<n> em <base>?" with "Sim, mesclar" first and "Não,
  aguardar o merge" second; one question per PR. The question names the commands: `gh pr ready <n>` and `gh pr
  merge <n> --merge` (a merge commit; never `--admin`, `--auto` or `--delete-branch`: the remote branch goes by
  GitHub's automatic deletion of merged head branches, and the local one by the cleanup of `closeout.md`, step 5). On "Sim", run them, then `merge-status` as below. On "Não", the wait goes on
  unchanged.
- **What wakes the session.** Whatever the host offers: a subscription to the pull request's activity, or a
  background monitor that runs `python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" merge-status --config <config>
  --prs <n> --base <approved base>` every few minutes. Either is only a trigger. On every wake run `merge-status`
  and act only on its answer, never on the notification. A subscription to the PR's activity may not report a
  merge at all, so the monitor is the dependable trigger: it prints one short line only when the set of `ready` or
  `settled` PRs changes (never the whole JSON every cycle) and uses the skill's resolved path, because
  `${CLAUDE_SKILL_DIR}` may be unset in a background shell. The user can also say "mesclei", and the session runs
  `merge-status` at once. A monitor must run with the same GitHub account as the session's `gh` for that
  repository. When the host offers neither, say so in the handoff and stop waiting: nothing is lost, the closeout
  question of the next session finds the merged work.
- **What counts as merged.** `ready` lists the PRs merged into the approved base. A PR merged into another branch,
  closed without a merge, or not found is never ready: its issues are not proposed for closing, and the session
  says why.
- **At the merge.** With the release's pull request `ready`: in the main worktree, on the local main, `git pull
  --ff-only origin <base>` (the local main was already inside the release, so it moves forward without a merge
  commit; if it does not fast-forward, stop and ask instead of merging or resetting). Then read
  `references/closeout.md` and run it for the issues of the release: first the cleanup of the merged work (step 5),
  without approval and before any closing question: `git fetch --prune`, the records of each worktree copied to the
  main worktree, the worktrees and the local branches of the issues, the slices and the merged release removed;
  then `closeout.py verify --issues <closes>` only confirms the issues of `closes` (closed by the merge), and the
  closing of the rest (with the tick in a parent, for a sub-issue) has its own approval. An issue whose
  criteria are not all ticked is not offered: say which are left, and tick only what the evidence supports. The
  cleanup offers the issue branches that `origin/<base>` contains, pull request or not
  (`contained_in_base_without_pull_request`).
- **Other work goes on.** The wait never blocks independent issues. It ends when the release's pull request is
  merged or closed, or when the user ends it.
