# Bounded implementation

Read the recorded authorization, current GitHub issues and `docs/security.md`.
Stage 6 runs under the standing authorization (`SKILL.md`, stage 6): the session
fills the issue IDs, concurrency, stacking, worktree base, verification commands,
monitoring arrangement and stop conditions itself, announces them in one block and
records the charter without asking. A decision the standing authorization does not
cover (a new product decision, an operation on its denied list, a scope change)
goes back to the coordinator's `AskUserQuestion`. Never infer permission for any
other external write from local shell access. Run structured authorization checks
where applicable; they are advisory preflight, not sandbox enforcement.

## Standing authorization and the denied operations

The user decided, permanently and for every project, that the opening question of
stage 6 (concurrency, stacking and the bounded implementation authorization) is not
asked. Covered, for the issues of the family or batch at hand: editing, testing,
committing, pushing the work branches, opening and retargeting draft PRs (stacked ones
included), the merges the stacking authorization names, running migrations on the
local development database, creating and removing test data through the product's own
endpoints, commenting on the issues and ticking acceptance criteria with evidence.

Never covered, and asked one operation at a time with `AskUserQuestion` ("Sim" first,
"Não" second, the exact operation and command in the question): merging a pull
request, closing an issue, changing the board, deploying or publishing to production,
editing a migration already registered (on the base branch or applied anywhere but the
local development database), writing the base branch or a protected branch, turning on
a setting, key or flag in production, and deleting anything but the test data the run
created. Run it only after "Sim" and record the answer verbatim in the handoff. A
"Sim" covers that one operation, never another one, another PR or a later moment; "Não",
silence or another answer leaves it undone and the work goes on without it. The host's
own permission prompts are not Frontlights' to remove and still apply.

## Slices in order: one branch and one PR per issue

An issue is worked on one branch, in one worktree, and delivered in one PR; its slices (the
boxes of its acceptance criteria, stage 5) are worked in dependency order, one at a time. Each
slice is one TDD loop at its own seams (the `Seams:` under its box), one checkpoint
(`checkpoint --slice <id>` of `frontlights.py`, which `resume` echoes so the next window starts
at that slice) and, when its loop closes with evidence (the affected test modules green, the
measured commands), the tick of its box: capture the body, tick that line only, run
`closeout.py tick-check` before and after the write, and leave a short comment on the issue with
the commit and the commands. The session may end in the middle of an issue: the handoff names
the slice in progress and the slices already ticked, and a fresh session resumes at the first
open box, in order. Parallelism is between issues only. The watched run stays one per batch,
when the last slice that changes the screen closes its loop; the independent review stays one
per issue, of the whole diff, before the PR, and the full suite runs once there. Stacking, the
stacked wave and the family integration below apply only to a family that already exists (an
issue with sub-issues published before this rule), never to the slices of one issue.

**A parked slice.** When a slice is parked (it waits for something the session cannot do: a
decision, a credential, another team's endpoint), write right below its open box, as the last
sub-item of its box and more indented than it, the line `- Bloqueada: <what is missing and from
whom>`, by the write rule of the leftover (body captured, append only, difference checked,
reread); the RoadS reads that sub-item as the reason of a blocked part of the delivery. When
the slice is released, remove exactly that line before the box is ticked: the only removal
allowed in a body, checked by the difference (nothing else added or removed). The closeout
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
subagents or separate supported sessions. Give each a bounded outcome, owned
paths, tests, checkpoint path and no authority to expand scope. Tell workers they
share the codebase and must preserve others' changes. Hide internal worker names.
If concurrent sessions/tools are unavailable, report the capacity limitation.
Do not silently serialize for convenience. Isolate ports, databases and test data
as well as Git. Recompute readiness and refill free slots after each completion.

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

Making children wait for the parent's merge serializes the family behind a human
step. So, in a family that already exists, whenever an issue of the family depends on another one (a child that
lists its parent in `Depends on`, or a sibling chain), stage 6 **stacks** the
dependent on its dependency's branch. Under the standing authorization this is not
asked: the announcement says it. The choice "Como as filhas se apoiam no pai?" comes
back as a question only when the user asks to change it, with "Empilhadas no pai (Recomendada)" first (each child branches from the
parent's branch and its PR targets that branch) and "Esperar o merge do pai" second
(each child starts from the approved base once the parent is merged). The announcement warns
that a squash-merge of the parent makes the later merge of the base conflict on the
hunks the child shares with it, and that merging the parent PR with a merge commit
avoids that. Record the stacking in the
authorization, with the repository operations it needs: branch from a branch that is
not the base, push it (and the dependency's branch), open a draft PR whose base is the
dependency's branch, retarget that PR, `git merge` of a base into the issue's own branch, and `git merge` of a family's or batch's verified
branches into a local integration branch that is never pushed. Those are the only merges it allows: it never covers merging a PR, writing
the base branch, deploying or releasing. When the user chose to wait, a dependent
stays parked until its dependency is in the approved base.

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
- Push the dependency's branch before the child's PR: the base must exist on the
  remote and be current, or the child's diff would carry the dependency's unpushed
  commits. The child's draft PR has that branch as base (`gh pr create --draft --base
  <dependency-branch>`) and names in its body the PR it is stacked on, so the review
  sees only the child's own diff. Draft PRs keep the permission and native approval of
  the charter.
- When the dependency's branch moves after the child started (review fixes), the
  child brings it in with `git merge <dependency-branch>`, reruns its tests and
  refreshes the evidence; the new hashes invalidate the earlier review. Check
  `git merge-base --is-ancestor` at each material boundary.
- After a human merges the parent PR (the wait below is how the session learns it), run `git fetch origin` and retarget each child
  PR to the base the parent's PR merged into (`<parent-pr-base>`, which is the
  approved base branch and not always the default one). GitHub usually does it when
  the parent branch is deleted on merge; reread the PR's base to confirm, otherwise
  `gh pr edit <child-pr> --base <parent-pr-base>`. Then bring the base in with `git
  merge origin/<parent-pr-base>` and rerun the tests. Use a merge, never a rebase or a
  force-push. A merge commit of the parent merges cleanly; a squash or rebase merge
  rewrites its commits, so conflicts on the hunks the child shares with the parent are
  expected: resolve them in the merge commit, keeping the child's own changes on top of
  the parent's content that the base already has, and show those hunks to the reviewer.
  The merge changes HEAD, so refresh the evidence and have the reviewer look again; what
  remains to review is the child's own diff.
- A conflict on anything beyond the parent's own content already in the base, or a
  dependency closed without being merged, is a stop condition: park the child and ask.

## Integrating a family before its PRs

Each branch passing alone does not prove the family works together: a test of one child
can assert the very behavior another child changes on purpose, and a clean Git merge
does not make a green suite. Before any PR of a family with more than one branch is
opened, integrate it locally: an integration worktree from the parent's branch that
merges every verified child branch (local only: never pushed, never a PR), then run
the full relevant suite and the type checks. The watched browser run already happened, once
for the batch and before the reviews; `browser-gate` says whether its record still covers this
code, and `stale` asks again. When a local integration worktree already served that run, this
integration is the same one: reuse it and redo it after a fix. Findings follow the destination ladder; a fix goes to the branch that owns
the file, never to the integration branch, and the integration is redone after it.
A batch of independent issues watched together (no parent) gets the same kind of local
integration worktree, cut from the approved base; the stage 6 authorization names that merge even
when no stacking question is asked. The PRs open only after an integration with a green suite, and each branch still needs
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
whole batch, not to this issue alone: [browser-testing.md](browser-testing.md) asks "pronto
para assistir?" once the last slice of the batch that changes the screen has closed its loop,
before the independent review of any of them, and ends with the user's choice of watching
again, approving, asking for a change or going on; its records join the evidence below. Any brief that hands the
run to a subagent carries that reference's rule on test data: create what the flow needs, remove it afterwards.
Once the question is due and until the user has answered, the run is the `teste_assistido` pending of the checkpoint;
while a screen slice is still in its loop it is not (the handoff lists the open slice).

## Review, checkpoints and renewal

A slice that changes what the user sees waits for the batch's watched run, and the review of the
first screen slice waits until the last one has closed its loop and the user has answered:
`browser-gate` has to say `answered` (exit code 0) before its independent reviewer is dispatched, (the points where
the question comes out are listed in browser-testing.md); exit code 2 at those points is a question to
the user, never a skip.

Require an independent reviewer to inspect the current diff and test evidence.
They must not author the changes under review. Bind review to `frontlights.py
evidence --root <worktree>` hashes/HEAD and save that output with the review result
(`.frontlights/issues/<n>/review.json`). Run `frontlights.py review-gate --root
<worktree> --review <review.json>` before reporting an issue as reviewed, before
opening or updating a PR and after every commit: exit code 0 means the review still
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
a PR is opened or updated, every open finding (review, tests, live check, any other
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
their own approval (`references/closeout.md`). Draft PRs are covered by the standing authorization and still go through
the host's native approval. Never
merge a pull request, write the base branch, deploy, release, delete data or close
issues as routine AFK work; the only merges allowed are the ones the stacking authorization names: of a base into an issue's own
branch, and of a family's or batch's verified branches into a local integration branch that is never pushed. Anything
else on the denied list runs only after the user's "Sim" to its own question (above). Park
blocked issues with the precise pending question and continue independent ones.
Report each issue's state, branch/PR, exact tests/results, review evidence,
the findings left unfixed with the destination of each, remaining risk and next
action. Leave worktrees and evidence intact for recovery.

## After the pull request: waiting for the merge

Opening a PR does not end the work on an issue, and the session does not expect to be told that it was merged.
By default, as soon as a PR of the family is open, the session waits for the user's merge. The user can say
"não aguardar" at any time: the wait ends and the closeout question of the next session picks the work up.

- **Say it and record it.** One line to the user, in their language: which PRs the session waits for and what
  happens at the merge. In the handoff (`Aguardando o merge`): each PR number with its issue, head and base
  branch, the approved base, and when the wait began.
- **No closing keyword.** A PR opened by Frontlights never carries `Closes`, `Fixes`, `Resolves` or a variant of
  them, in its body or in its commits: closing an issue has its own approval, and a merge that closed it would skip
  that approval and ignore the criteria still unticked. Cite the issue by number instead.
- **Offer the merge when the PR is ready.** A PR is ready when its review is current (`review-gate` exit code 0),
  the family's integration suite is green, `browser-gate` says `answered` (or `not_needed`) and no finding lacks a
  destination. Then ask, under the denied-operations rule, "Mesclar a PR #<n> em <base>?" with "Sim, mesclar" first
  and "Não, aguardar o merge" second; one question per PR, up to four in one call, a stacked parent before its
  children. The question names the commands: `gh pr ready <n>` and `gh pr merge <n> --merge` (a merge commit, so the
  stacked children merge cleanly; never `--admin`, `--auto` or `--delete-branch`, since the cleanup has its own
  approval). On "Sim", run them, then `merge-status` as below; a child PR is offered only once it has been
  retargeted to the base its parent merged into. On "Não", the wait goes on unchanged.
- **What wakes the session.** Whatever the host offers: a subscription to the PR's activity, or a background
  monitor that runs `python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" merge-status --config <config> --prs 12,13
  --base <approved base>` every few minutes. Either is only a trigger. On every wake run `merge-status` and act only
  on its answer, never on the notification. A subscription to the PR's activity may not report a merge at all, so the
  monitor is the dependable trigger: it prints one short line only when the set of `ready` or `settled` PRs changes
  (never the whole JSON every cycle) and uses the skill's resolved path, because `${CLAUDE_SKILL_DIR}` may be unset
  in a background shell. The user can also say "mesclei", and the session runs `merge-status` at once. A monitor must run with the same GitHub account as the session's `gh`
  for that repository. When the host offers neither, say so in the handoff and stop waiting: nothing is lost, the
  closeout question of the next session finds the merged work.
- **What counts as merged.** `ready` lists the PRs merged into the approved base. A PR merged into another
  branch (a stacked parent), closed without a merge, or not found is never ready: its issue is not proposed for
  closing, and the session says why. With stacked branches a child's PR targets its parent's branch and, merged
  there, shows as `merged_elsewhere`: its work reaches the base through the parent, so its issue enters the closeout
  together with the parent's, once the parent's PR is `ready` with a `mergedAt` later than the child's (both are in
  `merge-status`). A child PR not merged yet is retargeted when the parent merges (rule above), and the wait goes on
  for it.
- **At the merge.** When at least one PR is ready, read `references/closeout.md` and run it for the issues of the
  ready PRs: the closing (with the tick in a parent, for a sub-issue) and the cleanup of worktrees and branches are two
  separate approvals, in that order. An issue whose criteria are not all ticked is not offered: say which are left, and tick only what
  the evidence supports. The PRs still open keep waiting.
- **Other work goes on.** The wait never blocks independent issues. It ends when every PR is merged or closed, or
  when the user ends it.
