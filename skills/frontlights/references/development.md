# Bounded implementation

Read when: entering stage 6, one section per step from the index below; again on resume, or when `update-check`
reports a newer skill.

Stage 6 runs under the standing authorization (below): the session announces the run in one block and records the
charter without asking. A decision it does not cover (a new product decision, a denied operation, a scope change)
goes back to the coordinator's `AskUserQuestion`. Each external write needs its own authority; local shell access
grants none. When a hook, a permission or a script refuses a step, read `docs/security.md` by its headings; record
formats live in `docs/protocol.md`, "Desenvolvimento e release" and "Registros". Each command answers JSON with `ok`
and `message` (a refusal adds `reason` and `hint`); its flags are in its `--help`.

| Section | Read when |
|---|---|
| Standing authorization and the denied operations | first, before the charter; before any denied operation |
| Work without an issue | the Direct path, or a Short one that publishes no issue |
| The start of stage 6 | the sync of the local main and the preview, before the first slice |
| Slices in order | opening, merging and ticking each slice |
| Which tests run when | choosing what a slice's loop runs |
| Dispatch and ownership | dispatching implementers and helpers (their brief: `references/worker.md`) |
| Integrating a family before the local main | a family that already exists (`references/family.md`) |
| Review, checkpoints and renewal | findings, the review the user asks for, a checkpoint, the final report |
| When the review is done | a review round ends |
| Into the local main | the issue's slices are merged and the watched run is answered or not needed |
| The free test on the local main | the issue is in the local main |
| The release | after the free test |

## Standing authorization and the denied operations

The user decided, permanently and for every project, that stage 6 opens without a question: there is no
concurrency question, no stacking question and no implementation authorization question. `frontlights.py charter
new --issue <n> --ownership <paths>` records the charter after a dry run of `authorize` (the user in
`approved_by`, `confirmed_by` and `monitoring.confirmed_by`, `"autorização permanente (docs/security.md)"` in
`approval_reference`, an `expires_at` at most 24 hours ahead, the previous charter kept), and the session announces
it in one short block, in the user's language: its `announcement`, with the branch and the order of the slices;
`charter add` brings in an issue, `charter renew` extends it. Its `monitoring` block is `mode: "local"`;
`phone_connected: true` only when the user states,
unprompted in this session, that the phone received and answered. A change the user asks for goes back through
`AskUserQuestion`. The questions of the work itself (the watched run, failures, the findings batch, a new product
decision) are still asked.

**Covered**, for the issues at hand: editing, testing, committing, the covered merges below, creating the branch of
the issue on GitHub, the push of the branch of the issue after each slice merge and after a fix of the free test, running migrations on the
local development database, never before the ANTES window of the issue has closed (else the report says that ANTES
is not faithful), creating test data through the product's own endpoints and keeping it for reuse, commenting on the
issues and ticking acceptance criteria with evidence. Before the release GitHub receives only the branch of each
issue: the branches of the slices, the preview branch and the local main stay local and are never pushed.

**Covered merges.** The run makes these merges on its own, and only these:

- a base into an issue's own branch or into its local integration branch (`<branch_prefix>issue-<n>-integra`);
- the branch of the issue into its local integration branch, after a fix of the free test;
- a slice's branch into the branch of its own issue when its loop closes;
- the branch of the issue (or of the slice it depends on) into a slice's branch, to bring it up to date;
- a verified child's branch into its parent's branch;
- a family's or batch's verified branches into a local integration branch that stays local;
- `origin/<base>` into the local main by `homolog sync` at the start of stage 6 (a conflict is undone and
  becomes a question);
- the local main and the branches of the issues in progress into the preview branch by `serve preview
  refresh` (a conflict is undone and becomes a question);
- the local integration branch of the issue into the local main once its watched run is answered or not needed.

**Denied operations, asked one at a time** with `AskUserQuestion`, "Sim" first and "Não" second, naming the
exact operation and the exact command: merging a pull request, closing an issue (but a `Closes #n` line of the
release, through its approved merge), changing the board, deploying or publishing to production, editing a
migration already registered, writing the remote main (`origin/main`, the base branch on GitHub) or a protected
branch, turning on a setting, key or flag in production, and deleting anything (the test data the run created
included: it stays for reuse) but the cleanup of merged work (`references/closeout.md`, step 5). Run it only after "Sim" and record the
answer verbatim in the handoff. A "Sim" covers that one operation; another operation, another PR or a later moment
gets its own question. "Não", silence or any other answer leaves it undone, and the work goes on without it. The
approvals that have their own stage (the issue's text, issue plan and publication, closeout and summary) keep them,
and the host's own permission prompts still apply.

### Work without an issue

The Direct path, or a Short one that publishes no issue: `charter new --direct <slug>` lists it in `direct_ids`. In
the rules of this stage "the issue" reads as that work and "the branch of the issue" as its branch; its records live
in `.frontlights/direct/<branch, slashes as dashes>/`. Its branch has no issue to link: it is cut from the local main
and stays local, never pushed, until the release. Its merge into the local main is by hand ("Into the local main").

## The start of stage 6

In the main worktree of a project with a remote, before the first branch is cut, `homolog sync` is the covered merge of
`origin/<base>` into the local main; it never uses `--force`, `reset` or `rebase`, and runs again before the release. A conflict
is undone and asked: "Resolver o conflito agora na worktree principal" or "Seguir sem sincronizar". The local main is
never pushed to the remote main: its content leaves only by the refspec push of the release.

**The preview.** Only with a `preview` block in the config (without the block, nothing of this runs), before the first
slice: `serve preview refresh` in the main worktree with every issue branch in progress as `--branch` (the list
`slice merge` builds), then its `baseUrl` once in a tab of Claude in Chrome. The session never takes another issue's
work in progress out of the preview; it follows the work and stops only when the user asks. The tab belongs to the
user, outside the rule of the disposable window, and the watched run never uses the preview nor its ports. A conflict
or a broken build is one line, then a question.

## Slices in order

One issue branch, one worktree per slice, one merge into the local main per issue.

An issue is worked on one issue branch, created on GitHub when its work starts, and delivered by one merge into the
local main. `frontlights.py slice open --issue <n> --slice S1 [S2 …]` cuts the branch of the issue from the remote
base (`origin/<base>`, never the local main), and each slice gets its own worktree and branch,
`<branch_prefix>issue-<n>-s<k>`, cut from the branch of the issue and named in the charter with its `slice`. Run at
once the `gh issue develop <n> --repo <repo> --base <base> --name <branch_prefix>issue-<n>` of its `commands`, which
creates the branch on GitHub and links it to the issue; the slices are worked in dependency order: independent slices
run at once (no `Depende de` between them and no file in common); a slice that depends on one still open is cut from
that slice's branch instead (stacked: `--stacked-on`, `"base": "<slice-branch>"`, `--stacked` to `browser-gate`) and
merged into the branch of the issue after the slice it depends on.

Each slice is one TDD loop at its own seams and one `checkpoint --slice <id>` (`checkpoint-<id>.json`). When its loop
closes, `frontlights.py slice merge --issue <n> --slice S<k>` reruns its tests, then the slice is merged into the
branch of the issue and the preview refreshed; run the push in its `commands`. A conflict (`files`) is resolved in the
issue's worktree and shown in its diff. A box without a screen runs the walkthrough of its box ("Into the local
main"), and the `.md` is the evidence of the tick; a box with a screen waits for the "Aprovado" of the watched run;
then comes the tick of its box: the `next.tick` argv (`closeout.py tick --box S<k>`, with `closeout.py tick-check`
before and after the write) and a short comment with the commit and the commands.

The handoff names the slice in progress and its worktree; a fresh session resumes at the first open box. Slices run in
parallel inside an issue and between issues. Meanwhile the ANTES window, open since the grilling, runs the `Fluxo:` of
each criterion on the base; the watched run stays one per issue, when the last slice that changes the screen closes its
loop, and it is the only gate of the merge into the local main; a broader suite and an independent review run only
when the user asks for them. Stacking children on a parent applies only to a family that already exists
(`references/family.md`).

### Which tests run when

TDD per slice is the default practice: its own tests at its seams, plus the test modules the slice touches and the
type checks. These tests are evidence, never a gate: no suite holds back the merge into the local main or the
release. When the user asks to implement "só com teste assistido", the session writes and runs no tests in that run
(`slice merge --watched-only`), and the watched run is the evidence. A broader suite runs only when the user asks for
one, through the optional tools (`homolog suite --mode impact|full`, judged by `homolog suite-gate`); its command, count and exit code go to the
handoff, and a red one is a finding. No whole check is required anywhere: a project's CI, when there is one, is
neither expected nor a gate, and the watched run of each issue is the evidence.

**A parked slice.** When a slice waits for something the session cannot do (a decision, a credential, another team's
endpoint), write the line `- Bloqueada: <what is missing and from whom>` as the last sub-item of its box, more
indented, by the write rule of the leftover (body captured, append only, difference checked, reread); the RoadS reads
it as the reason of a blocked part. When the slice is released, remove exactly that line before the box is ticked:
the only removal allowed in a body besides the move of a legacy section. The closeout counts the box as open
meanwhile: a sub-item without a box is never a criterion.

### After the loop

Run the type checks the repository really has (never assume npm scripts; without a type checker, say so and record the
syntax or build checks), and inspect the vertical behavior, the diff and the acceptance coverage; an unexpected effect
stops the issue. When anything the issue changes is visible on the screen (its `## Navegador e testes ligados` says so,
or `browser-gate` finds it in the diff), the watched run belongs to the issue as a whole: its ANTES ran from the
grilling, and its DEPOIS ("pronto para assistir?", `references/browser-testing.md`) comes once the last slice that
changes the screen has closed its loop and every closed slice is merged into the branch of the issue, and before an
independent review of any of them. Once that question is due and until it is answered, it is the `teste_assistido`
pending of the checkpoint.

## Dispatch and ownership

For a family that already exists, the scope of a dispatch is the issue and all its open sub-issues; the parent never
goes alone unless the user chose that. `frontlights.py schedule --plan <file> --limit <approved-limit>` recommends;
start all eligible non-conflicting issues up to the ceiling, all launched in one message, each with a brief by
`references/worker.md`. Without concurrent agents, report the capacity limitation. Do not silently serialize for
convenience. With a `path_risk` of `inspect` other than `ok`, give `slice open` a short `--dir`. A worker's report is a
claim: read the diff and rerun the commands it names.

**Fan out inside an issue.** The independent slices go at once, one implementer per open slice, in its own worktree, and the agents around them do not
wait: dispatch in the same message read-only workers that prepare the next slice, and the checks that share no
resource (one that shares a port or a database runs one at a time). When the user asked for a review, the reviewer is never the implementer. Only one
worker edits a slice's worktree at a time; the readers edit nothing; the merge is this session's.

## Integrating a family before the local main

A family that already exists (a parent with sub-issues) stacks its children on the parent's branch and is integrated
locally before the local main; the family enters the local main as one, through the parent's branch, once its watched
run is answered or not needed: `references/family.md`, "Stacking" and "Integrating before the local main".

## Review, checkpoints and renewal

The independent review runs only when the user asks for one: it is not dispatched by default and is not a gate of
the merge into the local main nor of the release. With a screen it waits until `browser-gate` says `answered`.
`references/review.md` stays its standard; the reviewer never authored the changes. Bind it to `frontlights.py
evidence` in `.frontlights/issues/<n>/review.json` and run `frontlights.py review-gate` before reporting an issue as
reviewed. Any commit, edit or new file after the review makes it stale, and whether to review again is the user's
call. Findings (the watched run, a requested review, tests and checks that ran) take the destination ladder of the
Follow-ups section in `issues.md` (same PR, a new acceptance criterion in the source issue, a top-level issue only for
new scope), decided as one batch (the baixos of a finished review take the default of "When the review is done",
below).

**The reviewer's brief.** It names `references/review.md`, the issue, its base and, from the second round on, the
previous tip and its findings. The standard belongs to the reviewer: the implementer's brief names the issue, its
seams and its tests, and leaves `review.md` out.

### When the review is done

A round is one dispatch of the reviewer on the current tip. The review is done at the first round that reports 0
sérios and 0 médios; the baixos still open go to the findings batch, each as a new acceptance criterion of the source
issue, and the batch also offers "Corrigir os baixos agora". There is no limit of rounds to keep: after a round with a
sério or médio, ask "Mais uma rodada" or "Dar destino pela escada"; a sério or médio without a destination keeps the
issue out of the local main by the gate on the findings. The handoff records each round: its HEAD and its counts.

**Gate on the findings.** Before an issue is reported as reviewed or complete, and before the merge into the local
main and before a PR is opened or updated, every open finding that came up (the watched run, a review the user asked
for, tests that ran, a live check, any other verification pass) has a destination GitHub tracks, or is fixed, or is
shown as not a defect with its evidence, or is dropped by the user's explicit answer: the gate of the Follow-ups
section. A line in the PR body, a comment or the chat is never a destination, so "cited in the PR" does not pass the
gate. Most often a finding left unfixed becomes an acceptance criterion of the source issue. While such a criterion
is open the issue is not in the `closes` of `release-plan`, so the PR cites it without a closing keyword, in its body
and in the commit messages.

Before each renewal, `templates/handoff.md` and `frontlights.py checkpoint` (`--pending teste_assistido` while a
watched run is due, `--slice <id>`); `frontlights.py resume` lists those first. Renew near 100k; stop before 150k.

The session may tick an acceptance criterion in the issue body only with evidence for it, because the closeout trusts the ticks; a
criterion born from a finding is ticked the same way. Closing an issue is never part of this: it has its own approval.
Report each issue's state, branch/PR, the watched run, the walkthroughs run without a screen, the tests and the review
when they ran, the findings left unfixed with the destination of each, the count of its lines in
`.frontlights/pitfalls.md` (criteria that entered after the approval: `references/issues.md`, "A pitfall line"), and
the next action.

## Into the local main

The local main is the homologation bench: it accumulates every issue whose watched run was answered (or was not
needed) and reaches GitHub only with the release; `authorize` refuses `origin/main` as the remote main. The watched run
is the only gate of stage 6: no impact suite and no review is required. Once the last slice is merged, `homolog.py
merge --issue <n>`:

1. **The checks.** Refuses a dirty main worktree, a slice outside the branch of the issue, an open box.
2. **The gate, the watched run.** `browser-gate` not green is exit code 2 with its question, never the merge.
3. **Without a screen, the walkthroughs.** When `browser-gate` says `not_needed`, and for each `sem tela` box, running
   the walkthrough of each box (its `Roteiro:` lines, `references/issues.md`) is a condition of the merge into the
   local main, with no new question. It runs when its slice closes: `.frontlights/issues/<n>/walkthroughs/S<k>.md`,
   with a header (the issue, the box, the persona, the date, the steps, the base and the commit it ran on), `## Antes`
   and `## Depois`, the output masked in a code block, one row of the handoff table each. A `## Depois` that differs
   from the box's `depois:` sends the slice back; a box without its file keeps the issue out of the local main.
4. **The check and the merge.** Merges the branch of the issue and the local main into a local
   `<branch_prefix>issue-<n>-integra` (the branch of the issue never receives the local main; a conflict stays there,
   `files`: resolve, commit, rerun), records the operation with `gates` `{"browser_gate": "answered"}` (or
   `not_needed`), the only gate, runs `authorize` and merges into the local main. On a refusal the session asks the
   user with `AskUserQuestion` instead of merging; it never edits the gates to make them pass.
5. **Back it up.** `homolog bundle` and `update-check`; `configured: false` is one line, "sem backup configurado".
6. **Record it.** The handoff's "Merge na main local" takes the watched run, or the walkthroughs run without a screen,
   the record and the bundle.

Work without an issue: `git merge main` in its worktree, an operation naming its `direct` for `authorize`, `git merge
--no-ff` in the main worktree, `homolog bundle`. `authorize` is a preflight, not a barrier.

## The free test on the local main

The watched run tests the branch; the free test lets the user test the local main before anything goes to GitHub. In
an issue whose `browser-gate` was `answered`, right after the merge into the local main and the bundle, the session
runs `serve.py free-test start --issue <n>` without a question, then its `window.commands`: a window on the local main
and the local development database (the homologation one), already logged in (`references/browser-testing.md`, "The
free test window"). One line says the window is theirs until they close it.

- **Without a screen, in the terminal.** When `browser-gate` said `not_needed`, no window opens and no product is
  served: give the commands of `serve.py free-test commands`, each in its own code block, then ask
  "Terminou de testar a main local?", "Sim, terminei" first and "Ainda testando", which leaves it pending; never answer
  it for the user.
- **The user leads.** No script, no print and no time limit; the session helps on request.
- **One free test per homologated issue.** After an "Agora não" to the release, the next issue's free test covers
  everything accumulated in the local main. Closing the window right away is how the user skips it.
- **A fix asked in the free test.** Fix it at once on the branch of the issue, TDD by default, push it (covered), then
  `homolog.py merge --issue <n> --free-test-fix`: the free test itself is the evidence of the fix, and the watched run
  is not rerun. When the product needs a restart, the user reloads the page and the window stays open. Each fix is a box of `teste-livre-cas.md`, a leftover box
  (`references/issues.md`, "A leftover as an acceptance criterion"), ticked only when the user checked it, otherwise
  with `Evidência que fecha:`.
- **Window closed, next step.** On the holder's exit (or "Sim, terminei") run `serve.py free-test stop`. With fixes,
  the batch before the release: the draft approved by link and stamp (`SKILL.md`, "Show before approval"), one
  approval for the whole file, and written by the write rule of the leftover (body captured, append only, difference
  checked, reread). Without fixes, the release comes directly: the release question comes only after the window is
  closed.

## The release

From the local main to GitHub. The release is offered by the session at the end of each homologated issue, once the
window of its free test is closed; on "Agora não" the work stays in the local main, and the next homologated issue
offers the release again with everything accumulated.

- **Plan it.** `homolog sync`, then `homolog.py release plan`: the issues and slugs to release, the branch name, and
  `closes` (every box ticked, no open sub-issue). No suite is required for the release (no whole check is: the watched
  run of each issue is its evidence).
- **Offer it.** "Lançar a release com as issues #a, #b agora?", "Sim, lançar" first and "Agora não" second.
- **Branch and pull request (covered).** The body follows `templates/pr.md` (the model of the pull request), checked
  by `release body-check`: **Resumo** and **Evidência** once per issue, from records that exist (a print by its file
  name and folder, never an absolute path, an attached image, a login or a person's data), **Risco do merge** once for
  the release. **`Closes #n` only from `closes`.** One line per issue of `closes`, copied from that list, never counted
  by hand; every other issue is cited by number without a closing keyword, in the body and in the commits; the body of
  the pull request is never the destination of a finding. `release go --body <file>` prints the refspec push and `gh
  pr create`: run them, then `release go --record --pr <n>`. A refused refspec push asks "Lançar pelo caminho antigo,
  com a branch local <release branch>?" (`--legacy-branch`).
- **Wait for the merge.** The merge is the user's step. One line to the user says which pull request the session
  waits for; the handoff's `Release` line records it. A background monitor runs `release status --since <state>
  --quiet` and wakes the session once; act only on `release status` ("mesclei" runs it at once). "não aguardar" ends
  the wait, and the closeout question of the next session picks the work up. The wait never blocks independent issues.
- **Offer the merge when the PR is ready.** The merge itself stays a denied operation: `blocked` never offers it;
  `ready` carries "Mesclar a PR #<n> em <base>?" with "Sim, mesclar" first and "Não, aguardar o merge" second; one
  question per PR, with the argv of `gh pr ready <n>` and `gh pr merge <n> --merge` (never `--admin`, `--auto` or `--delete-branch`: the remote
  branch goes by GitHub's automatic deletion of merged head branches). On "Não", the wait goes on unchanged.
- **At the merge.** `release landed` pulls the local main (if it does not fast-forward, stop and ask instead of
  merging or resetting) and lists the cleanup of `references/closeout.md`, step 5, run without a question. A PR merged
  into another branch, closed without a merge, or not found is never ready.
