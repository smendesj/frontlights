# Closing finished issues

On entering, read `docs/security.md`, "Fechamento e limpeza", and `docs/protocol.md`, "Fechamento e release".

Read this when the stage 1 closeout question is answered yes, when the release of stage 6
(`development.md`, "The release") finds its pull request merged into the approved base and the local main brought
up to it, or when the user asks to close finished issues. Everything the user reads
stays in Portuguese. At the merge of the release and at stage 1, step 5 (the cleanup of the merged work, without a
question) runs first, before the closing question of step 1. Closing is a write on GitHub with **its own
approval**: no implementation authorization, no merged PR and no green test stands in for it. The helper only
reads; the session writes, with its own `gh`, and only what the user approved. The card goes to Done by the
board's own workflow ("Item closed" → Status Done), when the issue closes: this flow only closes and checks, and never
moves a card.

## 1. Find the candidates (read only)

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" candidates --config <config> --root <project>
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" candidates --config <config> --root <project> --issues 12,13
```

By default the scope is the issues this project worked on with Frontlights (the folders of
`.frontlights/issues/`, the `issue_ids` of the authorizations and the ids of the issues of `plan.json` that are already published in this
repository: a plan still in proposal does not count) plus all
their sub-issues, down the tree. `--issues` names an explicit list. `--all` sweeps every open issue of the
repository and is used only when the user asks for it. With no repository or no `gh`, say in one line that
the check could not run and go on.

When the release's merge woke the session, the issues of the `closes` of its `release-plan` were closed by the
`Closes #n` lines of the merged pull request (`development.md`, "The release"): they skip this step and the
question, and only step 4 confirms them (`verify --issues <closes>`). Pass `--issues` with the other issues
`release-plan` listed for that release (the sub-issues of a family included): an explicit list is taken as it is;
an issue of `closes` that GitHub still shows open right after the merge stays out of this list too, and the verify
reads it again. Only the release merged into the approved
base counts; the merge of an issue into the local main, or of a child into its parent's branch, closes nothing by
itself (the issue closes with the release that carries it, as `development.md` says): `candidates` keeps such an
issue out as `awaiting_release` until `origin/<base>` holds its branch (`--base` and `--remote`, defaulting to the
`base.branch` of the authorization records and `origin`; the branch comes from the `worktrees` of those records or
from `<branch_prefix>issue-<n>`), reading Git only with `rev-parse` and `merge-base` through `homolog.py`, and never
excludes on a doubt: a branch already gone, no remote-tracking ref or a root that is not a repository leave the
issue as it is, and `releaseCheck` says `checked`, `skipped` or `unavailable`. An issue that reached the base
but still has an unticked criterion comes back in `excluded` as `unchecked_criteria`: say which
criteria are left, and tick only what the evidence supports (never to get the issue closed).

A sub-issue closed by conversion (`--reason "not planned"`, with the comment `Convertida em CA S<k> da #<n>`,
`references/issues.md`, "Converting a family") is history: it is no candidate, needs no tick in its parent, and
the parent's new boxes are what this closeout counts.

An open issue is a **candidate** only when it has an acceptance-criteria section and every criterion of it is
ticked, and every one of its sub-issues is closed or a candidate in the same batch (children close before
their parents). A closed issue is never a candidate, whatever its card: it is counted in `alreadyDone`. Each
candidate carries its `action` (always `close`), the criteria count, its PRs (state and whether merged), its card
status and `cautions`: `open_pr`, `no_pr`, `not_on_board`, `pending_outside_criteria`.
The cautions inform; they never block, and an `open_pr` is called out in the question.

A known leftover is an acceptance criterion like any other (`issues.md`, Follow-ups), so an open one keeps its
issue out of this list as `unchecked_criteria`. `pending_outside_criteria` is for a body written before that rule,
which kept its leftovers in a section of their own (`Pendências conhecidas`) outside the criteria, where this
step cannot count them: the candidate carries the number of open items in `pendingOutside`. Show it in the table
as "fecha com N pendências fora dos critérios" and call it out in the question like an `open_pr`; it is the
user's call whether to close with them open. Say in the question that moving them into the criteria is available:
it is a write of the Follow-ups recipe in `issues.md`, done only when the user asks for it, with its own approval
and outside this list. This step never moves them.

`excluded` lists what is not ready and why (`unchecked_criteria` and `no_criteria` with the counts,
`open_children` with the children, `awaiting_release` with the branch, its tip, the base and the remote when every
box is ticked but the branch of the issue is not yet in `origin/<base>`, `truncated` when a list was cut, `not_found`
and `unreadable`): that needs work, a decision or the release, not closing. An `awaiting_release` is said to the
user in one line (the issue closes with the release that carries it) and never proposed. `order` is 1-based and is the order to close in. `alreadyDone`
counts the closed ones, which need nothing. Tell the user briefly, never propose it. Ticking a criterion belongs
to the verification of the issue, with evidence (a test, a measured result, a reviewed diff), under the
authorization for routine issue updates; this step trusts the ticks and never ticks one itself. The one tick it
asks for is not a criterion of the issue being closed but the item of its parent that cites it, below.

A sub-issue candidate also carries `parentTicks`: `lines`, the numbers of the lines of its open parent's body that
are unchecked items citing it and no other issue, and `shared`, those that cite it together with other issues
(never ticked for one of them). Only line numbers come from the helper; the session reads the lines from its own
copy of the parent's body (the Capture command of the recipe in `issues.md`). A sub-issue without `parentTicks`
(no item of the parent cites it, or the parent is closed, in another repository or unknown) is only closed.

`board.status` says whether the cards could be read, for the table and for the verify: `unconfigured` (no board:
no card is shown or checked), `not_read` (nothing in scope, so the board was not read), `unavailable` (a `gh`
without the `project` scope: say so, give `gh auth refresh -s project`; the closing goes on),
`done_option_missing` (the board has no option named as `project.done`: show the field and its real options
and ask which one is Done; recording the answer in `.frontlights/config.json` as `project.done` is a local
write, shown first). Without `project.done` the pair is `Status` / `Done`.

## 2. Show the list and ask

Write to a file, in the user's language, one table with a row per candidate (number, title, top-level or
sub-issue, criteria n/n, children, PRs, card status, action, cautions, and "fecha com N pendências fora dos
critérios" when `pendingOutside` is above zero) in the `order` of the result, and the exact `commands` that will
run, and ask its approval by link and stamp (`SKILL.md`, "Show before approval"). A sub-issue with `parentTicks`
gets, in its row, "marcar no corpo de #P as linhas L" with each of those lines quoted whole, and the lines in `shared` are listed as "não marcadas: citam outras issues". Then ask with `AskUserQuestion`: "Fechar estas <N> issues?" with
"Sim, fechar tudo" first and recommended (recommend "Escolher quais" instead when some candidate has
`open_pr` or `pendingOutside` above zero), "Escolher quais" (a follow-up question with the candidates, at most four per call; a parent chosen without its
candidate children is not written, it waits for them, and the user is told so) and "Não agora". When the list holds
ticks, the question reads "Fechar estas <N> issues e marcar os itens dos pais?", and "Só fechar, sem marcar" comes
before "Não agora" and writes only the closes (no tick). "Não agora" writes nothing. The helper keeps no memory of the refusal, so the question comes back in every later
session while the list stands, and the user can answer the stage 1 question "Não, seguir com o pedido" each time. Record the answer verbatim with a reference; never answer for the user.

## 3. Write what was approved

Run the stamp check of the approved list first (`SKILL.md`, "Show before approval"): when it exits 1, nothing is
written and the list is asked again. In the `order` of the result, for each approved issue run the `commands` exactly as given, each value as one
double-quoted argument: `gh issue close <n> --repo <repo> --reason completed`. Never close a parent before every one of its children is closed. A failed write is recorded and only the
missing ones are retried, never by repeating a close that already landed; a child that fails to close holds
its parent back and both are reported. Pause a few seconds between writes when the batch is large, to stay
under the secondary rate limit. Add no comment: the closing is already on the issue.

**The tick in a parent.** After a sub-issue is closed, for each of its parents in `parentTicks` (once per parent,
with all its lines, and before that parent is closed when it is in the same list): capture the parent's body with
the Capture command of the recipe in `issues.md` and check that each listed line of that copy is still an unticked
item that cites the sub-issue and no other issue, and is the line the user was shown (otherwise stop and show the
difference). Build the new body as a copy of it in which only the `[ ]` of those lines became `[x]`, by an
exact-replace edit, and run `python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" tick-check --before <saved> --after
<new> --lines <lines>`: it must answer `ok` before anything is written. Capture the body once more right before the
write and compare it with the saved copy (the compare step of the same recipe), then write it with `gh issue edit
<parent> --repo <repo> --body-file <file>`. Capture it again and run `tick-check` against the saved copy with the
same lines: `ok` is the verification. `python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" tick --config <config>
--root <project> --issue <parent> --line <L>` runs this capture, check, write and reread for one line at a time when
that line lies in the parent's acceptance-criteria section (a line outside it follows the recipe above by hand), while
the check that the line still cites only the sub-issue and is the line the user was shown stays the session's, made
on the `body-before` file it keeps, after the write (it detects a wrong line but cannot prevent it: a difference is
shown and asked about, and undoing it is a write of its own, with its own approval). A sub-issue whose close failed leaves its parent alone; a failed tick is
recorded and only the tick is retried. After the writes run `candidates` again for the parents: one whose criteria
and children are now complete goes through the same question.

## 4. Verify

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" verify --config <config> --root <project> --issues 12,13
```

At the merge of a release, `--issues` takes the `closes` of its `release-plan` together with the issues closed in
step 3. Report per issue whether it is closed; list every `ok: false` (the command then exits with code 1). A card that
did not reach Done is in `cardsOutsideDone` and in one line of the message: say that line (the board's "Item
closed" workflow did not move it; suggest turning it on in the board's Workflows screen). It never makes an issue
fail, and the session does not move the card. GitHub is the source
of truth: the local `.frontlights/issues/<n>/` snapshots are updated to closed with the time of the read,
never the other way round. Put the approved list, the user's literal answer, the results and the verify
output in the handoff, with the `tick-check` result of each parent.

## 5. Clean up the merged work (first, without a question)

This step runs first, before the closing question of step 1: at the merge of the release, right after `git pull
--ff-only origin <base>` (`development.md`, "At the merge"), with `--issues` the issues `release-plan` listed for
that release, and at stage 1 of a new session when the closeout read finds merged work (`SKILL.md`, the closeout
question), with `--issues` the `issue_ids` of the authorization records. It is the written exception to "deleting
anything" of the denied operations (`development.md`): the worktrees and branches the work created (the
`worktrees` of the authorization for these issues, plus an integration worktree the handoff names, plus the local
release branch once merged) are not needed once the release that carries them was merged into the approved base
(for a branch with no pull request, once `origin/<base>` contains its tip), so the session removes them **without
a question**, whatever the user answers to the closing afterwards. The remote branch is GitHub's job: the head
branch of a merged pull request is deleted by GitHub itself ("Automatically delete head branches", a setting of the
repository), so no command of the cleanup ever runs `git push origin --delete`.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base>
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base> --integration <integration worktree>
```

Run it from the folder the session stands in, with `--root` pointing at the project's main worktree: the helper
never offers the folder it runs in, and the commands it prints carry `git -C <main worktree>`, so they work from
anywhere. `--integration` names the local-only worktree of a family (never pushed, never a pull request): it goes
only when its branch holds no commit of its own that is not already in a pull request that reached the base (a fix
belongs to the member branch that owns the file). A merge counts as a commit of its own when it carries content (a
conflict resolved by hand, a file added to it): such a branch stays, as `integration_has_unique_commits`.

`commands` is the whole list, in the order to run it: `git fetch --prune origin` first (`fetch_prune`, which drops
the remote-tracking refs of the branches GitHub deleted; absent without an `origin`), then the commands of every
candidate that does not ask. `candidates` lists what can go, each with its issue, its slice (null outside a slice's
worktree), `release` (true for a release branch), worktree path, branch, tip, pull requests, `recordsTo`, `ask`, its
`cautions` (`frontlights_records`, `ignored_files`, `local_only_integration`, `slice_merged_into_issue_branch`,
`contained_in_base_without_pull_request`, `merged_release_branch`, `branch_differs_from_authorization`) and its own
`commands`. A worktree with `frontlights_records` (a non-empty `.frontlights` folder inside it) gets `copy_records`
before `git worktree remove`: `cleanup.py archive --from <worktree>/.frontlights --to <recordsTo>` copies its
records to the main worktree's `.frontlights/issues/<n>/worktrees/<worktree folder>/` (one folder per worktree;
`.frontlights/worktrees/<worktree folder>/` for a worktree named without an issue), keeping what is already there.
A failed copy stops that item, so the worktree keeps its records.
A slice's worktree (an authorization entry with `slice`) is delivered to the branch of its own issue, never by a
pull request: it is offered, before the issue's own worktree, with the caution `slice_merged_into_issue_branch`,
once that branch contains a commit of its own, it was never pushed and no pull request was
opened from it; otherwise it stays as `slice_not_in_issue_branch` (also a slice freshly cut or merged fast-forward, with nothing of its own
merged yet; the rule's `git merge --no-ff` keeps the issue's tip ahead of the slice's), `slice_pushed`, `slice_has_pull_request`, `slice_is_issue_branch` (an entry with `slice` that points at
the issue's own branch) or `slice_issue_branch_unknown` (the authorization names no worktree of the issue itself, or
the branch of the issue is already gone and the approved base does not hold the slice's tip; when the base holds it,
the slice is offered).
A local release branch (`<branch_prefix>release-<date>[-N]`, the prefixes of the authorization records) is offered
last, with `merged_release_branch` and only `git branch -D`, by the rule of an issue branch below and when no
worktree has it checked out (`checked_out_elsewhere` otherwise); one not merged yet is left alone and not listed.
`ignored_files` comes with `ignoredCount` and `ignored`, the first names of what Git ignores in that worktree: those
files go away with it. A candidate whose `ignored` has anything besides dependency or build folders
(`node_modules`, `.venv`, `__pycache__`, `dist`, `build`, caches and the like) carries `ask: true`, `askReason`
`ignored_files_besides_dependencies` and `askIgnored` (those names), and its commands are not in `commands`: it is
the only candidate asked about. `excluded` lists what stays and why, in `reasons`: `main_worktree`, `current_directory`,
`detached_head`, `locked_worktree`, `checked_out_elsewhere`, `not_a_worktree`, `not_found`, `path_missing`,
`unsafe_path`, `unsafe_branch`, `protected_branch`, `uncommitted_changes`, `unreadable_status`, `open_pr`,
`no_merged_pr`, `newer_than_merged_pr`, `merged_into_other_branch`, `ancestry_unverifiable`, `open_dependents`,
`pull_requests_unreadable`, `integration_has_pull_request`, `integration_pushed` and
`integration_has_unique_commits`: each needs work or a decision, never removal. `alreadyClean` counts what is gone
already. A branch is offered only when its tip is the head of a merged pull request that reached the approved base
(a stacked child through its parent) or, with no pull request at all, when the approved base (`origin/<base>` when
the remote-tracking ref exists, the local base otherwise) already contains its tip, the caution
`contained_in_base_without_pull_request`: the branch of an issue that reached GitHub through a release, never
pushed itself; in both cases nothing is uncommitted, no pull request is open from or on top of
it, and it is not protected.

Run `commands` in order, without a question (each carries `git -C <main worktree>`), each value as one
double-quoted argument: `git fetch --prune origin`, then per item the `copy_records`, `git worktree remove` and
`git branch -D` (right here, because a squash merge leaves the branch "unmerged" for Git and the plan offers it only
when its tip is the head of a merged pull request or already contained in the approved base). Never add `--force`
or `-f`. A command that fails (a path too long for Windows, a folder in use) is recorded
and reported, and never retried with force; the rest of that item's commands are not run (a branch whose worktree
could not be removed keeps both), and the next item goes on. For each candidate with `ask: true`, ask with
`AskUserQuestion` (at most four per call) "Remover a worktree <pasta> com os arquivos ignorados <nomes>?", with
"Sim, remover" first and "Não, manter" second, naming the files of `askIgnored`; on "Sim", run that candidate's own
`commands` in order; on "Não" or any other answer, nothing of it runs. Record the answer verbatim with a reference;
never answer for the user. The `excluded` stay where they are: say them in one line (how many, and the reasons).
Then verify:

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" verify --config <config> --root <project> --worktree <path> --branch <name> --records <recordsTo>
```

Report per item whether it is gone (the worktree unregistered and its folder absent, the local branch absent) and
whether each `--records` folder holds the copied files (`copied`), and list every `gone: false` or `copied: false`
(the command then exits with code 1). Put the plan, the commands run, any answer to an `ask` and the verify output
in the handoff.

## 6. Let RoadS see it

RoadS reads only the **Status** of the card in the Project, never whether the issue is closed: the board's "Item
closed" workflow moves the card to Done when the issue closes, and a card the verify reported outside Done stays
where it is for RoadS until it is moved on the board. A completed item stays in its sprint, marked done, until the
sprint rotation removes it. RoadS also refreshes only when it syncs, and a sync within 30 s of the previous one
returns the old snapshot. So, after the closing, tell the user in one line that RoadS shows it after its next sync
(the board's own "Sincronizar" there); Frontlights does not sync RoadS. Without a usable board (`board.status`
`unconfigured`, `unavailable` or `done_option_missing`) say plainly that the closing could not be checked against
the cards RoadS reads.

## Never

- Close an issue that has no criteria section or an unticked criterion in this flow. A user who asks for a
  specific one anyway gets the unticked items shown first, and the answer is theirs, outside this list.
- Reopen, delete, transfer or archive an issue, or edit its body, here; the one body edit is the approved tick of the
  item of a parent that cites a sub-issue closed in the same list (step 3).
- Close an issue on the strength of the merge alone, or tick a parent's item that is not in the list the user
  approved.
- Move a card (`gh project item-edit`): the board's "Item closed" workflow moves it to Done.
- Remove a worktree or a branch that `cleanup.py plan` did not offer (or, with `ask: true`, that the user did not
  approve), delete a remote branch (`git push origin --delete`: GitHub deletes the merged head branch), use
  `--force`, or remove the main worktree or the folder the session stands in.
- Merge a pull request, deploy or release: the closeout never does.
