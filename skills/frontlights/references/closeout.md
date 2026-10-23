# Closing finished issues

Read when: stage 7, after the stage 1 yes, the merged release pull request or a request.

On entering, read `docs/security.md`, "Fechamento e limpeza", and `docs/protocol.md`, "Fechamento e release".

The release of stage 6 (`development.md`, "The release") hands over here when it finds its pull request merged into
the approved base and the local main brought up to it. Past ~300k of context, open a new session whose first command is `closeout.py run`. The user
reads Portuguese. Step 5 (the cleanup, without a question) runs first. Closing comes with **its own approval**: no
implementation authorization, no merged PR and no green test stands in for it. The card goes to Done by the board's
own workflow ("Item closed" → Status Done): this flow never reads the board and never moves a card.

## 1. Find the candidates (read only)

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" run [--issues 12,13]
```

`frontlights.py open` reads the same candidates at the opening (`closeout.ask`, `issues`, `awaiting_release`). The
default scope is the issues this project worked on plus their sub-issues; `--all` only when the user asks. Without
a repository or `gh`, say so in one line and go on.

At the release's merge, the `closes` were closed by `Closes #n`: they skip the question. First run `closeout.py
verify --issues <closes>`: one still open is read once more a few seconds later and, still open, joins the question
of step 2 with the reason in one line; pass `--issues` with the rest of what `release-plan` listed. A merge into the
local main closes nothing: the issue closes with the release that carries it. `run` keeps such an issue out as
`awaiting_release` until `origin/<base>` holds its branch, never excludes on a doubt, and `releaseCheck` says
`checked`, `skipped` or `unavailable`.

A **candidate** is open, every criterion of it is ticked and every sub-issue is closed or in the same batch
(children close before their parents); a closed issue counts in `alreadyDone`, one closed by conversion is history.
`cautions` (`open_pr`, `no_pr`, `pending_outside_criteria` with the count in `pendingOutside`, leftovers outside the
criteria of an old body) inform and never block. A leftover is a criterion, so an open one keeps its issue out of
this list as `unchecked_criteria`.

`excluded` says why: `unchecked_criteria` and `no_criteria` with the counts (say which criteria are left; this step
never ticks one), `open_children`, `awaiting_release` with the branch, its tip, the base and the remote,
`truncated`, `not_found`, `unreadable`. An `awaiting_release` is said to the user in one line, never proposed.

A sub-issue carries `parentTicks`: `lines` of its open parent that cite it alone, and `shared`, never ticked. Only
line numbers come from the helper. Without `parentTicks` it is only closed.

## 2. Show the list and ask

`run` writes `.frontlights/closeout-<AAAAMMDD-HHMMSS>.md`, a Portuguese table in closing order ("fecha com N
pendências fora dos critérios", "marcar no corpo de #P as linhas L", "não marcadas: citam outras issues") with the
exact commands, and prints `stamp`, `question`, `options` and `recommended`. Send the link (`SKILL.md`, "Show before
approval") and ask with `AskUserQuestion`: "Fechar estas <N> issues?", or "Fechar estas <N> issues e marcar os itens
dos pais?" when there are ticks, with "Sim, fechar tudo", "Escolher quais", "Só fechar, sem marcar" (only with ticks)
and "Não agora". recommend "Escolher quais" instead when some candidate has `open_pr` or `pendingOutside` above zero.
With `pendingOutside`, it is the user's call whether to close with them open; Say in the question that moving them
into the criteria is available (the Follow-ups recipe of `issues.md`), done only when the user asks for it, with its
own approval.

"Escolher quais" asks a follow-up (at most four per call). "Não agora" writes nothing, and the question returns in a
later session while the list stands, where the stage 1 question also takes "Não, seguir com o pedido". Record the answer verbatim; never answer for the user.

## 3. Write what was approved

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/closeout.py" apply --expect <stamp> --answer "<literal answer>" [--only 12,13]
```

`apply` checks the stamp of the question, recomputes, and writes nothing, not even the approval, when the list
changed (`lista mudou: …`: ask again after a new `run`) or when `--only` leaves a chosen parent without its child; then
it records the approval of the list with that stamp and checks it.
Then, with the `gh` account checked before each write, it runs in order `gh issue close <n> --repo <repo> --reason
completed`, adding no comment; Never close a parent before every one of its children is closed: a child that fails
holds its parent back. Large batches pause between closes, with no new question.

**The tick in a parent.** After a sub-issue closes, and before its parent does, `apply` ticks the parent's `lines` in
one write: capture, check, `tick-check`, `gh issue edit --body-file`, reread, `tick-check` (bodies kept in
`.frontlights/issues/<parent>/`). "Só fechar, sem marcar" skips it.

Retry only what is in `failed`, never a close that already landed. `closeout-<…>.result.json` keeps the commands,
exit codes, reread state and literal answer. Then `run` again: a parent now complete gets the same question.

## 4. Verify

`apply` ends with the `verify` of what it closed; at a release's merge verify the `closes` too. List every `ok:
false`. The verify reads only the issues; GitHub is the source of truth. The handoff gets the list, the answer and
the `apply` result, with the `tick-check` result of each parent.

## 5. Clean up the merged work (first, without a question)

At the merge of the release, right after `git pull --ff-only origin <base>`, with `--issues` from `release-plan`;
and at stage 1, right after `frontlights.py open`, when the authorization records list issue ids. It is the written
exception to "deleting anything" of the denied operations: what the work created (slices, the local integration
worktree of each issue (`<branch_prefix>issue-<n>-integra`), the merged local release branch) goes **without a
question**, whatever the closing answer.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup.py" run --from-authorizations [--issues 12,13] [--integration <worktree>]
```

`run` fetches, plans again and runs only that fresh plan, item by item: archive of the worktree's `.frontlights`,
its junctions undone, `git worktree remove`, `git branch -D`. A failed command stops its item, never retried and
never with `--force`. A branch goes when its work reached the base: a merged pull request, or contained in
`origin/<base>` (`contained_in_base_without_pull_request`); a slice once its issue's branch holds it
(`slice_merged_into_issue_branch`). GitHub deletes merged head branches; the released issue branch is the exception,
and `run` leaves its `git push origin --delete` and the local delete after it in `sessionCommands`, for the session,
in order.

A candidate with `ask: true` (ignored files that are not build output nor a copy of the main worktree's, or `out`,
saved outputs older than 30 days) waits: ask "Remover a worktree <pasta> com os arquivos ignorados <nomes>?" with
"Sim, remover" and "Não, manter"; on "Sim", `run` again with `--yes <key>`. `excluded` (`in_use` included) is said in
one line; reasons and cautions are in `cleanup.py --help`. The `verify` and `.frontlights/cleanup-<…>.json` go to the
handoff.

## 6. Let RoadS see it

RoadS reads only the **Status** of the card in the Project, never whether the issue is closed; a sync within 30 s
returns the old snapshot. Say that RoadS shows it after its next sync; Frontlights does not sync RoadS and does not
read the board.

## Never

- Close an issue with an open criterion, on the strength of the merge alone, or from a list not approved with its
  stamp.
- Reopen, delete, transfer or archive an issue, or edit its body, here; the one body edit is the approved tick of the
  item of a parent that cites a sub-issue closed in the same list.
- Move or read a card (`gh project item-edit`, a board read).
- Remove what `cleanup.py run` did not offer, an `ask: true` without its yes, a remote branch other than the
  released issue's; use `--force`.
- Merge a pull request, deploy or release: the closeout never does.
