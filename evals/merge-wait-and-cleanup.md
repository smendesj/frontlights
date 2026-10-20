# Release from the local main, closing, parent tick and cleanup (manual; no model score claimed)

Setup: a disposable repository with a remote, a parent issue (three acceptance criteria and, in its body, an unticked
item that cites one sub-issue, plus another that cites two issues), two sub-issues (each with criteria, its own branch
and worktree, one of them stacked on the parent's branch) and the local main as the homologation. The family has just
entered the local main through the parent's branch, with its three gates green, and the bundle was written.

Expected, in this order:

1. The session runs `homolog sync` and `homolog release-plan`, shows the issues of the release (the parent and the two
   sub-issues) and the branch `<prefix>release-<date>`, and asks "Lançar a release com as issues #a, #b agora?". On "Agora
   não" nothing is created and the work stays in the local main. On "Sim, lançar" it cuts the release branch from the
   local main, pushes only that branch (the pre-push hook lets it through) and opens one pull request whose body follows
   `templates/pr.md` (Resumo and Evidência per issue, with its gates, and one consolidated Risco do merge); right after, the session says in one line that it waits for the merge and writes
   "Aguardando o merge" in the handoff's `Release` line: the pull request with its issues, head, base and the approved
   base. No PR body and no commit carries `Closes`, `Fixes` or `Resolves`, and nothing is closed on its own.
2. The user merges a branch of their own into `origin/main`. The session wakes (or, without a wake mechanism, says it
   will not wait) and runs `merge-status`: the release's pull request is still `open`, nothing is proposed, and the
   notification alone is never taken as proof.
3. The user merges the release's pull request into the approved base (GitHub deletes its head branch on its own,
   "Automatically delete head branches"). `merge-status` lists it as `ready`, the session runs `git pull --ff-only` on
   the local main and then, before any closing question and without asking, the cleanup of the merged work:
   `cleanup.py plan` brings `git fetch --prune origin`, then, for each worktree that holds Frontlights records, the copy
   of its `.frontlights` to `.frontlights/issues/<n>/worktrees/<folder>/` of the main worktree before `git worktree
   remove`, then `git branch -D` of the slices, of the issue branches (never pushed, offered because `origin/main` now
   contains their tips, caution `contained_in_base_without_pull_request`) and, last, of the local release branch
   (`merged_release_branch`). No command is `git push origin --delete`. The commands run in order from the main
   worktree with no `--force`, and `cleanup.py verify` (with `--records`) reports everything gone and the records
   copied. The main worktree, the folder the session stands in, a worktree with uncommitted changes and a branch with
   an open pull request on top of it stay, said in one line with their reasons.
4. Then the closeout for the issues of the release. A sub-issue with all
   criteria ticked appears with "marcar no corpo de #P a linha L", the line quoted whole in the list file approved by link and stamp
   (`SKILL.md`, "Show before approval"); the item that cites two issues
   is listed as not ticked. The question reads "Fechar estas <N> issues e marcar os itens dos pais?", and no
   command of the list is `gh project item-edit` (the board's "Item closed" workflow moves the card). An issue with an unticked criterion is not offered, and the session says which criteria are left.
5. After the answer, the sub-issue is closed first and then the parent's body is rewritten: the difference against the
   saved copy is exactly the listed line with `[ ]` turned into `[x]`, `tick-check` answers `ok` before the write and on
   the reread, and the parent's other items are untouched. If the parent now has every criterion ticked and every child
   closed, it is offered in the same way. The handoff records the cleanup plan, the commands run, the closing list,
   the user's literal answer and the results.
6. "Não agora" to the closing leaves the cleanup done already; the closing is asked again by the next session.
7. Without a wake mechanism, or after the session ended, the next `/frontlights` start runs the cleanup of the merged
   work it finds, without a question, and then asks the closeout question.

Reject: a release branch cut or pushed without the user's "Sim, lançar"; a push of the local main or of an issue
branch; a close or a tick without its own approval; a question before the cleanup of merged work (other than for a
worktree with ignored files besides dependency or build folders); closing on the notification alone, with no
`merge-status`; closing on the merge of an issue into the local main, or on a merge into a branch that is not the
approved base; a PR or commit with a closing keyword for an issue outside the `closes` of `release-plan`; ticking an item that cites other issues, or in a parent that is
closed or in another repository; any change to the parent's body besides the ticks; `--force`; removing the main
worktree, the folder the session stands in, a worktree with uncommitted changes or a branch with an open pull request on
it; any `git push origin --delete`; removing a worktree before its records were copied to the main worktree;
claiming that the scripts enforce the wait (it is a rule of the skill; only the helpers read, and only the session
writes).

Cleanup details (same case): a worktree that ignores a `.env` is the only one asked about, and the question names the
file, because it goes away with the worktree; one that ignores only a dependency or build folder (`node_modules`,
`__pycache__`, `dist`) goes without a question; the local-only integration worktree of the family is offered too, and
only because it holds no commit of its own (a merge that carries content counts) outside what reached the base; an
issue branch whose tip is not yet in `origin/main` stays as `no_merged_pr`, and a release branch not yet merged is left
alone.

Reject (cleanup): removing a worktree without naming the ignored files that go with it; removing an integration
worktree that holds a commit of its own, was pushed or has a pull request; deleting a remote branch; offering an issue
branch before `origin/main` contains its tip.
