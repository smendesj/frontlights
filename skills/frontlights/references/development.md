# Bounded implementation

Read the recorded authorization and the current GitHub issues, and from `docs/security.md` the sections
"Hooks e escritas em `.git/`", "Autorização permanente", "Subagentes", "`authorize` e a main local",
"`homolog sync` e `homolog bundle`", "Registro de autorização e `branch_prefix`", "Permissões do host e
AFK", "Revisão e sobras" and "`serve`, `checks` e o teste no navegador"; from `docs/protocol.md`,
"Registros" (`plan.json`), "Ponto de retomada e continuação" and "Contexto e conclusão". Stage 6 runs under
the standing authorization (below): the session fills the run itself, announces it in one block and records
the charter without asking. A decision the standing authorization does not cover (a new product decision, an
operation on its denied list, a scope change) goes back to the coordinator's `AskUserQuestion`. Each external
write needs its own authority; local shell access grants none. Run structured authorization checks where
applicable; they are advisory preflight, not sandbox enforcement.

## Standing authorization and the denied operations

This section is the single source of what stage 6 may do on its own and what it asks first; `SKILL.md`,
`docs/security.md`, `docs/protocol.md` and the README point here.

The user decided, permanently and for every project, that stage 6 opens without a question: there is no
concurrency question, no stacking question and no implementation authorization question. The session fills the
run itself and announces it in one short block, in the user's language: the issue IDs, repository, concurrency,
the branch and the order of the slices of each issue, stacking when a family exists, worktree base and branch
prefix, the verification argv and the stop conditions. The user may change any of it at any time, and a change
goes back through `AskUserQuestion`.

**The charter.** Record it in `.frontlights/authorization.json` with the user in `approved_by` and
`confirmed_by`, `"autorização permanente (docs/security.md)"` in `approval_reference` and an `expires_at` at
most 24 hours ahead. Its `monitoring` block is `mode: "local"`; `phone_connected: true` only when the user
states, unprompted in this session, that the phone received and answered. Local files record consent but cannot
enforce it.

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
- the branch of the issue into the local main once its three gates are green ("Into the local main").

**Denied operations, asked one at a time** with `AskUserQuestion`, "Sim" first and "Não" second, naming the
exact operation and the exact command: merging a pull request, closing an issue, changing the board (adding an
item, moving a card, editing a field), deploying or publishing to production, editing a migration already
registered (on the base branch or applied anywhere but the local development database), writing the remote main
(`origin/main`, the base branch on GitHub) or a protected branch (the local main is written only by the covered
merge, with its three gates green), turning on a setting, key or flag in production, and deleting anything but
the test data the run created. Run it only after "Sim" and record the answer verbatim in the handoff. A "Sim"
covers that one operation; another operation, another PR or a later moment gets its own question. "Não",
silence or any other answer leaves it undone, and the work goes on without it. The approvals that have their
own stage (the issue's text, issue plan and publication, closeout, cleanup, roadmap and summary) keep them. The
host's own permission prompts are not Frontlights' to remove and still apply.

## The start of stage 6: the pre-push hook and the sync of the local main

Both run in the main worktree of the project (where the local main is checked out), in a project with a
remote, before the first branch of the run is cut; a project without a remote (`repository: null`, no
`origin`) gets neither, and the session says so in one line. The helper is `scripts/homolog.py`, reached as
`python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog <operation> ...`; it prints one JSON object with
`ok`, `exitCode`, `operation` and `message`: exit code 0 done, 1 refused or failed, 2 a question for the user.

**The hook.** `homolog hook --root <main worktree> --base <base>` checks the `pre-push` hook at the path Git
resolves (`core.hooksPath` included) and answers `installed`, `ours`, `foreign`, `path` and `script`, the
exact text `--install` would write, plus `current` (ours and equal to that text) and `outsideRepository`. Exit
code 0: installed, Frontlights' (a marker line names it) and current. Exit code 2 with `current: false` (ours,
but another base baked in or an edited body): say so and offer `--install`, which rewrites it. Exit code 2 with
`outsideRepository: true` and `current: false` (`core.hooksPath` sends the hooks outside the repository's Git dir
and no current hook of ours is there): nothing is written in either mode, say so in one line and go on; a hook of
ours that is current in that folder (installed by hand) answers exit code 0. Exit
code 2 with `installed: false`: show `script` in a code block and ask "Instalar o hook `pre-push` que recusa
enviar a main local?" ("Sim, instalar" / "Não, seguir sem o hook"); on "Sim", `homolog hook --install --root
<main worktree> --base <base>` writes it (idempotent when it is already ours), the check is rerun and the
answer goes verbatim to the handoff; on "Não", the run goes on and the handoff says the hook is absent. Exit
code 2 with `foreign: true`: a `pre-push` of another origin exists; it is never overwritten (`--install`
refuses with exit code 1), the session says so in one line, shows `script` for the user to merge by hand and
goes on. The hook is POSIX `sh`: it reads the refs Git hands a `pre-push` and exits 1, with a message in the
user's language, when a line pushes `refs/heads/<base>` from the local side or into the remote side (`git
push origin main` and `git push origin x:main` alike, and `git push --all` or `--mirror`, which carry that ref);
everything else passes. It is the only hook the skill
installs, a guard and not a barrier: `--no-verify` and GitHub's own interface pass it, and the rule that the
local main is never pushed stays a rule of the skill.

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
of this runs, said in one line), and after the hook and the sync: before the first slice, run `serve preview refresh` in the main worktree with every branch of an issue
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
which stays local and is never pushed, and delivered by one merge into the local main once its three
gates are green ("Into the local main", below); each of its slices (the boxes
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
the issue's worktree, committed there, and shown to the independent reviewer as part of the diff. Each
slice is one TDD loop at its own seams (the `Seams:` under its box), one checkpoint
(`checkpoint --slice <id>` of `frontlights.py`, saved as `checkpoint-<id>.json` in the issue's records,
one per slice worktree, which `resume` echoes so the next window starts at that slice, in that
worktree) and, when its loop closes with evidence (the affected test modules green, the
measured commands), the slice branch is merged into the branch of the issue (`git merge --no-ff
<branch_prefix>issue-<n>-s<k>` in the issue's worktree, one of the covered merges, "Stacking" below)
and then comes the tick of its box: capture the body, tick that line only, run
`closeout.py tick-check` before and after the write, and leave a short comment on the issue with
the commit and the commands; then `serve preview refresh` with the branches of the issues in progress, in a
project with a preview ("The start of stage 6"), so the slice reaches the user's tab; a conflict is a question
and a broken build goes back to the slice that owns the file before the next one starts. The session may end in the middle of an issue: the handoff names
the slice in progress with its worktree, and the slices already ticked, and a fresh session resumes at the first
open box, in order, in that slice's worktree. Slices run in parallel inside an issue and between issues; the fan-out rule of
`SKILL.md` keeps the agents busy around each open slice (Dispatch and ownership, below). The watched
run stays one per issue, when the last slice that changes the screen closes its loop; the independent review stays one
per issue, of the whole diff, before the merge into the local main, and the full suite runs once there. The stacked wave
and the family integration below (children merged into the parent's branch, and the family entering
the local main as one) apply only to a family that already exists (an issue with
sub-issues published before this rule); a slice stacked on another slice uses only the branch cut,
the `base` of its worktree entry and `--stacked`, as said above.

**Which tests run when.** Per slice, run the test modules the slice touches and the type checks;
the fast suite is how the whole is checked between slices, when the project has one. In the
Frontlights repository the fast suite runs through `python tests/suite.py` with
`FRONTLIGHTS_SUITE=rapida` (Windows only). The variable lives in each module's `load_tests`, so
it works the same for the runner and for `python -m unittest discover -s tests`: both skip the
modules that start real processes and ports (`tests.test_serve_ports`,
`tests.test_checks_integration` and `tests.test_serve_preview`), each one reported as skipped with a reason that names the
variable; any other value, or no variable, runs everything. The runner runs the safe modules in
parallel and the six sensitive ones in a serial queue, one at a time; `--report <file>` writes
the JSON of the run as evidence. Before the independent review and before the merge into the local main, run the whole
suite without the variable, once, through `python -m unittest discover -s tests -v`, with or
without CI in the project: the runner does not make the whole suite faster than `discover`, a
project without CI has no other net, and the CI of this repository runs the same `discover` and
never sets the variable either.

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
run at once the broader suite, the type checks and the other measured commands that share no
resource (a test module that shares a port, a database or a reservation folder with another
runs one at a time, as the project's own rules say). The independent reviewer and the driver
of the watched run are workers of their own, dispatched together with whatever else is ready;
the reviewer is never the implementer. Only one worker edits a slice's worktree at a time,
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
through the parent's branch, once its three gates are green ("Into the local main", below), and reaches
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
  (acceptance evidence current for that branch's HEAD, tests green); an independent
  review still pending does not hold it back. Create the child's worktree from that
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
- When the dependency's branch moves after the child started (review fixes), the
  child brings it in with `git merge <dependency-branch>`, reruns its tests and
  refreshes the evidence; the new hashes invalidate the earlier review. Check
  `git merge-base --is-ancestor` at each material boundary. Use a merge, never a rebase or a
  force-push.
- A verified child is merged into its parent's branch (`git merge --no-ff <child-branch>` in the
  parent's worktree, a covered merge) once its review is current and its tests are green. The merge
  changes the parent's HEAD, so the parent's evidence is refreshed and its reviewer looks again at what
  the child brought. A child merged into the parent while a sibling is still open is brought into that
  sibling with `git merge <parent-branch>`: conflicts on the hunks the child shares with the sibling are
  resolved in that merge commit, keeping the sibling's own changes on top of what the parent already has,
  and shown to the reviewer.
- The family enters the local main through the parent's branch, with every verified child merged into
  it, by the three gates of "Into the local main": the full suite at the parent's tip, a review current
  for each branch and the watched run answered for the family. A child not verified yet keeps the family
  out: it is parked with its question and the parent waits, unless the user chooses to let the parent go
  alone (then the child starts over from the local main once the parent is in it, as in "Esperar o merge
  do pai").
- A conflict on anything beyond the parent's own content, or a dependency closed without being
  merged, is a stop condition: park the child and ask.

## Integrating a family before the local main

Each branch passing alone does not prove the family works together: a test of one child
can assert the very behavior another child changes on purpose, and a clean Git merge
does not make a green suite. Before a family with more than one branch enters the local
main, integrate it locally: an integration worktree from the parent's branch that
merges every verified child branch (local only: never pushed, never a PR), then run
the full relevant suite and the type checks. The watched browser run already happened, once
for the batch and before the reviews; `browser-gate` says whether its record still covers this
code, and `stale` asks again. When a local integration worktree already served that run, this
integration is the same one: reuse it and redo it after a fix. Findings follow the destination ladder; a fix goes to the branch that owns
the file, never to the integration branch, and the integration is redone after it.
A batch of independent issues watched together (no parent) gets the same kind of local
integration worktree, cut from the local main; the stage 6 authorization names that merge even
when no stacking question is asked. The family enters the local main only after an integration with a green suite, and each branch still needs
its own current review (`review-gate`). Record the integration worktree, the merged
HEADs and the results in the handoff. The integration branch is evidence, never delivered.

## Test-driven development

TDD is the red → green loop. This section is the reference that makes that loop
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
- **Refactoring is not part of the loop.** It belongs to the review stage below,
  not the red → green implementation cycle.
- **Evidence is real.** Preserve commands, exit codes, counts and output paths.
  Never invent failure evidence for a nontestable documentation change; state the
  exception and verify the relevant behavior another way.

### After the loop

Run relevant broader tests and actual type checks discovered from repository/CI;
do not assume npm scripts. If no type checker exists, say so and record applicable
syntax/build checks. Inspect the full vertical behavior, diff, regressions and
acceptance coverage. Tests may execute arbitrary code; native permission and
sandbox controls still apply. Unexpected effects stop the affected issue.

When anything the issue changes is visible on the screen (its `## Navegador e testes ligados`
says so, or `frontlights.py browser-gate` finds it in the diff), the watched run belongs to the
issue as a whole, not to this slice alone: [browser-testing.md](browser-testing.md) asks "pronto
para assistir?" once the last slice of the issue that changes the screen has closed its loop and every closed slice is merged into the branch of the issue,
before the independent review of any of them, and ends with the user's choice of watching
again, approving, asking for a change or going on; its records join the evidence below. Any brief that hands the
run to a subagent carries that reference's rule on test data: create what the flow needs, remove it afterwards.
Once the question is due and until the user has answered, the run is the `teste_assistido` pending of the checkpoint;
while a screen slice is still in its loop it is not (the handoff lists the open slice).

## Review, checkpoints and renewal

A slice that changes what the user sees waits for the issue's watched run, and the review of the
first screen slice waits until the last one has closed its loop and the user has answered:
`browser-gate` has to say `answered` (exit code 0) before its independent reviewer is dispatched, (the points where
the question comes out are listed in browser-testing.md); exit code 2 at those points is a question to
the user, never a skip.

Require an independent reviewer to inspect the current diff and test evidence.
They must not author the changes under review. Bind review to `frontlights.py
evidence --root <worktree>` hashes/HEAD and save that output with the review result
(`.frontlights/issues/<n>/review.json`). Run `frontlights.py review-gate --root
<worktree> --review <review.json>` before reporting an issue as reviewed, before
the merge into the local main, before opening or updating a PR and after every commit: exit code 0 means the review still
covers the code, exit code 2 means it is stale. Any commit, edit or new file after the
review makes it stale (bringing a base into the branch included), whatever its size:
rerun the suite, take new evidence and have the independent reviewer look again. A
stale review is never reported as reviewed. If no
independent reviewer is available, report "implemented, awaiting independent
review", not completed. Do not manufacture reviewer identities or approvals.
Classify the review's findings, and those of tests and live checks, by the
destination ladder of the Follow-ups section in `issues.md` (same PR, a new
acceptance criterion in the source issue, top-level issue only for new scope; never a
new sub-issue), decided as one batch.

**Gate on the findings.** Before an issue is reported as reviewed or complete, and before
the merge into the local main and before a PR is opened or updated, every open finding (review, tests, live check, any other
verification pass) has a destination GitHub tracks, or is fixed, or is shown as not a
defect with its evidence, or is dropped by the user's explicit answer: the gate of the
Follow-ups section. A line in the PR body, a comment or the chat is never a
destination, so "cited in the PR" does not pass the gate. A finding
left unfixed leaves by the ladder: most often as an acceptance criterion of the source
issue, which keeps the issue open until the leftover is treated, completed and ticked
with evidence; or as a top-level issue. The PR cites the issue without a
closing keyword, in its body and in the commit messages, while such a criterion is open.

Refactoring happens here. The reviewer may recommend refactors of the green code;
the author applies them without changing behavior or adding tests at new seams,
reruns the full relevant suite and type checks, and records fresh evidence. The
new hashes invalidate the earlier review, so the independent reviewer reviews
again before the issue can be reported as reviewed.

Save compact `templates/handoff.md` and a machine-readable checkpoint before each
session renewal. Include the issue URL and acceptance snapshot, repository map,
decisions, changed files, commands/results, review evidence, blockers and next
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
`ask_before_continuing`, and the question goes out before more is spent on reviews. The helper
checks reported numbers, not the host's actual token meter. If the host cannot
enforce renewal, explicitly report that hard-cap AFK acceptance is unproven.

Update GitHub checkpoints/status only if authorized and supported by current
evidence; tick an acceptance criterion in the issue body only with evidence for it
(a test, a measured result, a reviewed diff), because the closeout of stage 7 trusts
the ticks; a criterion born from a finding is ticked the same way, once the work it
names is done and its evidence exists. Closing an issue and moving its card are never part of this: they have
their own approval (`references/closeout.md`). The release's pull request is covered by the standing authorization and still goes through
the host's native approval; the branches of issues and slices stay local. The run merges only by the covered
merges, and anything on the denied list runs only after the user's "Sim" to its own question ("Standing
authorization and the denied operations", above). Park
blocked issues with the precise pending question and continue independent ones.
Report each issue's state, branch/PR, exact tests/results, review evidence,
the findings left unfixed with the destination of each, remaining risk and next
action. Leave worktrees and evidence intact for recovery.

## Into the local main: the three gates

The local main of the project (the base branch of the charter, checked out in the main worktree) is the
homologation bench: it accumulates every issue that passed its three gates, and nothing of it reaches
GitHub before the release. The remote main (`origin/main`) is never written outside the release's pull
request, and `authorize` tells the two apart: the local main is the only target of the covered merge
below, and a target with a slash (`origin/main`, `upstream/main`) is refused as the remote main.

When the last slice of the issue is merged into the branch of the issue, in this order:

1. **Bring the local main in first.** In the issue's worktree, `git merge main` (one of the covered merges,
   a base into the issue's own branch), so the tip of the branch already contains the local main and the
   merge below cannot conflict. A conflict is resolved here, in the issue's worktree, committed there and
   shown to the reviewer as part of the diff.
2. **Gate 1, the full suite.** Run the whole suite at that tip (`python -m unittest discover -s tests -v` in
   this repository, the project's equivalent elsewhere; never the fast suite), and record the command, the
   count and the exit code in the handoff. Red means the issue is not homologated: the failure goes back
   to its slice's loop, or to the user as a question.
3. **Gate 2, the review.** The independent review of the whole diff (Review, checkpoints and renewal, above)
   is bound to that tip, and `frontlights.py review-gate --root <issue-worktree> --review <review.json>`
   answers `current` (exit code 0). `stale` means a review again, never the merge.
4. **Gate 3, the watched run.** `frontlights.py browser-gate` answers `answered` (the user approved or said
   to go on) or `not_needed` (nothing on the screen changed), exit code 0; `pending`, `stale`,
   `contradiction` or `unconfigured` is the question of `browser-testing.md`, never the merge.
5. **The check and the merge.** Write the operation and run `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py"
   authorize --charter .frontlights/authorization.json --operation .frontlights/issues/<n>/merge-local-main.json`,
   with `kind` `merge_into_local_main`, the issue's worktree and branch, `target` the base branch of the
   charter and `gates` `{"full_suite": "green", "review_gate": "current", "browser_gate": "answered"}` (or
   `not_needed`); `examples/operation-merge-local-main.json` shows the shape. With `scope_check: pass`, in the
   main worktree and on the local main: `git merge --no-ff <branch_prefix>issue-<n>`. A refusal names the gate
   or the target, and the session asks the user with `AskUserQuestion` instead of merging; it never edits the
   gates to make them pass.
6. **Back it up.** Weeks of homologated work may live only in this clone, so right after the merge run
   `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" homolog bundle --root <main worktree> --config
   .frontlights/config.json` (covered; the only write the run makes outside the project, and only into that folder): it writes `<project>-<date>-<time>.bundle`, the local main and the work
   branches of every `branch_prefix` in the authorization records (`.frontlights/authorization*.json`; `claude/`
   when there is none; `--prefix` names one prefix alone), into the folder named by `homolog.backupDir` in `.frontlights/config.json`
   (an absolute path of the user's, typically a synced folder; `inspect` refuses a relative path, `..` or `~`,
   and the real path never enters a repository), verifies it with `git bundle verify` and reports `path`,
   `refs`, `bytes`, `prefixes`, `prefixSource` and `skipped`; say in one line how many records `skipped` counts
   when it is above zero (a broken record may leave its branches out of the backup). The folder must already exist; nothing else is written there and old bundles are never
   deleted. Exit code 1 with `configured: false` means no folder is configured: say so in one line, name the
   key, ask nothing and go on; any other refusal (a missing folder, a junction in its path, a Git failure) is
   said in one line and recorded in the handoff as a backup not taken.
7. **Record it.** The handoff's line "Merge na main local" takes the three gates with the evidence of each,
   the output of `authorize`, the commit of the merge and the bundle's path (or "sem backup configurado");
   the branch of the issue stays local, never pushed.

`authorize` is a preflight, not a barrier: it reads no Git and proves neither that the suite ran nor that the
review is current (the commands, `review-gate` and `browser-gate` do), the host's own permission prompts still
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
  lists the issues whose branch is in the local main and not yet in `origin/<base>` (`release`), the commits
  `ahead` and `behind`, and names the branch `<branch_prefix>release-<date>`: the prefix of the newest authorization
  record by `issued_at` (without `issued_at`, the last record by file name; `claude/` when there is none;
  `--prefix` names it alone; `prefix` and `prefixSource` say which), the date in São Paulo, and `-2`, `-3` when the name is taken. Exit code 2 says there is nothing to release, or that the local main is behind and
  must be synced first: say so in one line. It only reads.
- **Offer it.** Show the issues of the release (number and title) and ask with `AskUserQuestion` "Lançar a release
  com as issues #a, #b agora?", with "Sim, lançar" first and "Agora não" second; one question per release.
- **Branch and pull request (covered).** On "Sim", in the main worktree: `git branch <release branch> <base>`,
  `git push -u origin <release branch>` (the release branch is the only branch of the flow that is pushed, and the
  hook lets it through), then `gh pr create --base <base> --head <release branch> --title "Release <date>: issues
  #a, #b" --body-file <file>`. The body follows `templates/pr.md` (the model of the pull request), in the user's
  language, with the project's domain vocabulary: **Resumo** and **Evidência** once per issue (what it delivers with the smallest visual that makes its
  point clear; before and after, from the prints of each issue's watched run, the tests of its checkpoints, the
  independent review and its three gates, records that already exist, never invented; a print is cited by its file
  name and its folder in the issue's worktree (the lead issue's for a family), with one sentence of what it shows, never an absolute path, an
  attached or committed image, a login or a person's data) and the **Risco do merge**
  once, consolidated for the whole release (a one-way door when a migration or deleted data is in it, a two-way
  door otherwise, and the blast radius); it cites the issues by number, and the body of the pull request is never
  the destination of a finding (the gate on the findings, above). **No closing keyword.** A pull request opened by Frontlights never
  carries `Closes`, `Fixes`, `Resolves` or a variant of them, in its body or in its commits: closing an issue has
  its own approval, and a merge that closed it would skip that approval and ignore the criteria still unticked.
- **Wait for the merge.** Opening the pull request does not end the work, and the session does not expect to be
  told that it was merged. By default, as soon as the release's pull request is open, the session waits for the
  user's merge. The user can say "não aguardar" at any time: the wait ends and the closeout question of the next
  session picks the work up. One line to the user, in their language: which pull request the session waits for
  and what happens at the merge. In the handoff (the `Release` line): the pull request number with its issues,
  head and base branch, the approved base, and when the wait began.
- **Offer the merge when the PR is ready.** The release's pull request is ready when the three gates of every
  issue in it are recorded, the pull request has no conflict with the base and no finding lacks a destination.
  Then ask, under the denied-operations rule, "Mesclar a PR #<n> em <base>?" with "Sim, mesclar" first and "Não,
  aguardar o merge" second; one question per PR. The question names the commands: `gh pr ready <n>` and `gh pr
  merge <n> --merge` (a merge commit; never `--admin`, `--auto` or `--delete-branch`, since the cleanup has its
  own approval). On "Sim", run them, then `merge-status` as below. On "Não", the wait goes on unchanged.
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
  `references/closeout.md` and run it for the issues of the release: the closing (with the tick in a parent, for
  a sub-issue) and the cleanup of worktrees and branches are two separate approvals, in that order. An issue whose
  criteria are not all ticked is not offered: say which are left, and tick only what the evidence supports. The
  cleanup now offers the issue branches that `origin/<base>` contains, pull request or not
  (`contained_in_base_without_pull_request`).
- **Other work goes on.** The wait never blocks independent issues. It ends when the release's pull request is
  merged or closed, or when the user ends it.
