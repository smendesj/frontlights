# Closing finished issues

Read this when the stage 1 closeout question is answered yes, when the wait for the merge of stage 6
(`development.md`, "After the pull request") finds a pull request merged into the approved base, when a family
worked in stage 6 is reported merged, or when the user asks to close or move finished issues. Everything the user reads
stays in Portuguese. Closing is a write on GitHub with **its own approval**: no implementation
authorization, no merged PR and no green test stands in for it. The helper only reads; the session
writes, with its own `gh`, and only what the user approved.

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

When a merge woke the session, pass `--issues` with the issues of the pull requests `merge-status` lists as
`ready` and, for a family, the sub-issues that merged with them: an explicit list is taken as it is. Only a merge
into the approved base counts; the merge of a child into its parent's branch closes nothing by itself (its issue joins the closeout when the
parent's PR becomes `ready` with a later `mergedAt`, as `development.md` says). An issue whose pull
request merged but that still has an unticked criterion comes back in `excluded` as `unchecked_criteria`: say which
criteria are left, and tick only what the evidence supports (never to get the issue closed).

A sub-issue closed by conversion (`--reason "not planned"`, with the comment `Convertida em CA S<k> da #<n>`,
`references/issues.md`, "Converting a family") is history: it is no candidate, needs no tick in its parent, and
the parent's new boxes are what this closeout counts.

An open issue is a **candidate** only when it has an acceptance-criteria section and every criterion of it is
ticked, and every one of its sub-issues is closed or a candidate in the same batch (children close before
their parents). A closed issue whose card is not in Done is a candidate to be moved only, but only when it was closed as completed (one
closed as not planned or as a duplicate needs nothing). Each candidate
carries its `action` (`close`, `close_and_move`, `move_only`), the criteria count, its PRs (state and
whether merged), its card status and `cautions`: `open_pr`, `no_pr`, `not_on_board`, `already_done_card`,
`pending_outside_criteria`.
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
`open_children` with the children, `truncated` when a list was cut, `not_found` and `unreadable`): that
needs work or a decision, not closing. `order` is 1-based and is the order to close in. `closedUnchecked`
counts closed issues whose card could not be checked because the board was not readable, and `alreadyDone`
counts the closed ones that need nothing. Tell the user briefly, never propose it. Ticking a criterion belongs
to the verification of the issue, with evidence (a test, a measured result, a reviewed diff), under the
authorization for routine issue updates; this step trusts the ticks and never ticks one itself. The one tick it
asks for is not a criterion of the issue being closed but the item of its parent that cites it, below.

A sub-issue candidate also carries `parentTicks`: `lines`, the numbers of the lines of its open parent's body that
are unchecked items citing it and no other issue, and `shared`, those that cite it together with other issues
(never ticked for one of them). Only line numbers come from the helper; the session reads the lines from its own
copy of the parent's body (the Capture command of the recipe in `issues.md`). A sub-issue without `parentTicks`
(no item of the parent cites it, or the parent is closed, in another repository or unknown) is only closed.

`board.status` says whether cards can be moved: `unconfigured` (no board: close only), `not_read` (nothing in
scope, so the board was not read), `unavailable` (a `gh`
without the `project` scope: say so, give `gh auth refresh -s project`, close only),
`done_option_missing` (the board has no option named as `project.done`: show the field and its real options
and ask which one is Done; recording the answer in `.frontlights/config.json` as `project.done` is a local
write, shown first). Without `project.done` the pair is `Status` / `Done`.

## 2. Show the list and ask

Show in the conversation, in full and in the user's language, one table with a row per candidate (number,
title, top-level or sub-issue, criteria n/n, children, PRs, card status → Done, action, cautions, and "fecha com N
pendências fora dos critérios" when `pendingOutside` is above zero) in the
`order` of the result, and the exact `commands` that will run. Send the same text as a file with the host's
file-sending tool when one exists, and put it in the `preview` of the approve option (show-before-approval,
`SKILL.md`). A sub-issue with `parentTicks` gets, in its row, "marcar no corpo de #P as linhas L" with each of
those lines shown in full, and the lines in `shared` are listed as "não marcadas: citam outras issues". When the
list holds ticks, the question reads "Fechar estas <N> issues, mover os cartões para Done e marcar os itens dos
pais?", and "Só fechar, sem mover" writes only the closes (no move and no tick). Then ask with `AskUserQuestion`: "Fechar estas <N> issues e mover os cartões para Done?" with
"Sim, fechar e mover tudo" first and recommended (recommend "Escolher quais" instead when some candidate has
`open_pr` or `pendingOutside` above zero), "Escolher quais" (a follow-up question with the candidates, at most four per call; a parent chosen without its
candidate children is not written, it waits for them, and the user is told so), "Só fechar,
sem mover" and "Não agora". "Não agora" writes nothing. The helper keeps no memory of the refusal, so the question comes back in every later
session while the list stands, and the user can answer the stage 1 question "Não, seguir com o pedido" each time. Record the answer verbatim with a reference; never answer for the user.

## 3. Write what was approved

In the `order` of the result, for each approved issue run the `commands` exactly as given, each value as one
double-quoted argument: first `gh issue close <n> --repo <repo> --reason completed`, then, when the card
moves, `gh project item-edit <number> --owner <owner> --url <issue-url> --field <field> --value <value>`.
Never close a parent before every one of its children is closed. A failed write is recorded and only the
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
same lines: `ok` is the verification. A sub-issue whose close failed leaves its parent alone; a failed tick is
recorded and only the tick is retried. After the writes run `candidates` again for the parents: one whose criteria
and children are now complete goes through the same question.

## 4. Verify

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" verify --config <config> --root <project> --issues 12,13
```

Report per issue whether it is closed and its card is in Done; list every `ok: false` (the command then exits
with code 1). GitHub is the source
of truth: the local `.frontlights/issues/<n>/` snapshots are updated to closed with the time of the read,
never the other way round. Put the approved list, the user's literal answer, the results and the verify
output in the handoff, with the `tick-check` result of each parent.

## 5. Clean up what the work left behind (its own approval)

Ask this only after the closing of the approved list was written and verified; when the user answered "Não agora"
to the closing, ask nothing here. The worktrees and branches the work created (the `worktrees` of the
authorization for these issues, plus an integration worktree the handoff names) are not needed once their pull
requests were merged into the approved base, and removing them is a write of its own, with **its own approval**.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base>
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" plan --config <config> --root <project> --issues 12,13 --base <approved base> --integration <integration worktree>
```

Run it from the folder the session stands in, with `--root` pointing at the project's main worktree: the helper
never offers the folder it runs in, and the commands it prints carry `git -C <main worktree>`, so they work from
anywhere. `--integration` names the local-only worktree of a family (never pushed, never a pull request): it goes
only when its branch holds no commit of its own that is not already in a pull request that reached the base (a fix
belongs to the member branch that owns the file). A merge counts as a commit of its own when it carries content (a
conflict resolved by hand, a file added to it): such a branch stays, as `integration_has_unique_commits`. `candidates` lists what can go, each with its issue, worktree
path, branch, tip, pull requests, whether the remote branch goes too, its `cautions` (`remote_branch_gone`,
`remote_branch_moved`, `origin_is_not_the_repository`, `frontlights_records`, `ignored_files`,
`local_only_integration`, `slice_merged_into_issue_branch`, `branch_differs_from_authorization`) and the `commands` in the order to run them.
A slice's worktree (an authorization entry with `slice`) is delivered to the branch of its own issue, never by a
pull request: it is offered, before the issue's own worktree, with the caution `slice_merged_into_issue_branch` and
no remote command, once that branch contains a commit of its own, it was never pushed and no pull request was
opened from it; otherwise it stays as `slice_not_in_issue_branch` (also a slice freshly cut, with nothing of its own
merged yet), `slice_pushed`, `slice_has_pull_request`, `slice_is_issue_branch` (an entry with `slice` that points at
the issue's own branch) or `slice_issue_branch_unknown` (the authorization names no worktree of the issue itself, or
the branch of the issue is already gone and the approved base does not hold the slice's tip; when the base holds it,
the slice is offered).
`ignored_files` comes with `ignoredCount` and `ignored`, the first names of what Git ignores in that worktree: those
files go away with it. `excluded` lists what stays and why, in `reasons`: `main_worktree`, `current_directory`,
`detached_head`, `locked_worktree`, `checked_out_elsewhere`, `not_a_worktree`, `not_found`, `path_missing`,
`unsafe_path`, `unsafe_branch`, `protected_branch`, `uncommitted_changes`, `unreadable_status`, `open_pr`,
`no_merged_pr`, `newer_than_merged_pr`, `merged_into_other_branch`, `ancestry_unverifiable`, `open_dependents`,
`pull_requests_unreadable`, `integration_has_pull_request`, `integration_pushed` and
`integration_has_unique_commits`: each needs work or a decision, never removal. `alreadyClean` counts what is gone
already. A branch is offered only when its tip is the head of a merged pull request that reached the approved base
(a stacked child through its parent), nothing is uncommitted, no pull request is open from or on top of it, and it is
not protected; the remote branch goes only when `origin` is this repository and the branch still points at that
commit.

Show in the conversation, in full and in the user's language, one table with a row per candidate (issue, worktree,
branch, pull requests, remote branch, cautions) and the exact `commands`, then the `excluded` with their reasons;
send it as a file when the host has the tool and put it in the `preview` of the approve option (show-before-approval,
`SKILL.md`). Say in the question that a worktree with `frontlights_records` takes those records with it and that the
files in `ignored` go too (name them), and copy what the user wants to keep before removing. Then ask with
`AskUserQuestion`: "Remover estas <N> worktrees e branches?" with "Sim, remover tudo" first and recommended
(recommend "Escolher quais" instead when some candidate has `frontlights_records` or an `ignored` list with anything
besides dependency or build folders; when in doubt, recommend choosing), "Escolher quais" (a follow-up question with the candidates, at most four per call) and
"Não agora". "Não agora" writes nothing, and the closeout does not ask again; the user can ask for the cleanup at any time.
Record the answer verbatim with a reference; never answer for the user.

Run the approved `commands` in order (each carries `git -C <main worktree>`), each value as one double-quoted argument: first
`git worktree remove`, then `git branch -D` (right here, because a squash merge leaves the branch "unmerged" for Git
and the plan offers it only when its tip is the head of a merged pull request), then, when listed, `git push origin
--delete`. Never add `--force` or `-f`. A command that fails (a path too long for Windows, a folder in use) is recorded
and reported, and never retried with force; the rest of that item's commands are not run (a branch whose worktree
could not be removed keeps both), and the next item goes on. Then verify:

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" verify --config <config> --root <project> --worktree <path> --branch <name>
```

Report per item whether it is gone and list every `gone: false` (the command then exits with code 1). Put the
approved list, the user's literal answer, the commands run and the verify output in the handoff.

## 6. Let RoadS see it

RoadS reads only the **Status** of the card in the Project, never whether the issue is closed: closing an issue
without moving its card changes nothing there, and a completed item stays in its sprint, marked done, until the
sprint rotation removes it. RoadS also refreshes only when it syncs, and a sync within 30 s of the previous one
returns the old snapshot. So, when cards were moved and the roadmap sync of stage 1 is configured, tell the user
this in one line and offer a new sync (a question with options, "Sincronizar agora" and "Deixar para depois");
on yes run the roadmap sync again as `references/roadmap-sync.md` describes. Without a usable board (`board.status` `unconfigured`, `unavailable` or `done_option_missing`) say plainly that the close-only fallback will not show in RoadS.

## Never

- Close an issue that has no criteria section or an unticked criterion in this flow. A user who asks for a
  specific one anyway gets the unticked items shown first, and the answer is theirs, outside this list.
- Reopen, delete, transfer or archive an issue, or edit its body, here; the one body edit is the approved tick of the
  item of a parent that cites a sub-issue closed in the same list (step 3).
- Close an issue on the strength of the merge alone, or move a card or tick a parent's item that is not in the list the
  user approved.
- Remove a worktree or a branch that is not in an approved cleanup list, use `--force`, or remove the main worktree
  or the folder the session stands in.
- Merge a pull request, deploy or release: the closeout never does.
