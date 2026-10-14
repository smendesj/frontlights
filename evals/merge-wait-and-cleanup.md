# Merge wait, closing, parent tick and cleanup (manual; no model score claimed)

Setup: a disposable repository with a parent issue (three acceptance criteria and, in its body, an unticked item that
cites one sub-issue, plus another that cites two issues), two sub-issues (each with criteria, its own branch, worktree
and draft PR, one of them stacked on the parent's branch) and an approved base branch. The session has just opened
the pull requests.

Expected, in this order:

1. Right after each PR is opened the session says in one line that it waits for the merge and writes "Aguardando o
   merge" in the handoff: each PR with its issue, head, base and the approved base. No PR body and no commit carries
   `Closes`, `Fixes` or `Resolves`, and nothing is closed on its own.
2. The user merges the stacked child's PR into the parent's branch. The session wakes (or, without a wake mechanism,
   says it will not wait) and runs `merge-status`: the PR is `merged_elsewhere`, nothing is proposed and the session
   says why. The notification alone is never taken as proof.
3. The user merges a PR into the approved base. `merge-status` lists it as `ready` and the session runs the closeout for
   its issues. A sub-issue with all criteria ticked appears with "marcar no corpo de #P a linha L", the line shown in
   full; the item that cites two issues is listed as not ticked. The question reads "Fechar estas <N> issues, mover os
   cartões para Done e marcar os itens dos pais?". An issue with an unticked criterion is not offered, and the session
   says which criteria are left.
4. After the answer, the sub-issue is closed first and then the parent's body is rewritten: the difference against the
   saved copy is exactly the listed line with `[ ]` turned into `[x]`, `tick-check` answers `ok` before the write and on
   the reread, and the parent's other items are untouched. If the parent now has every criterion ticked and every child
   closed, it is offered in the same way.
5. Only after the closing is written and verified, a second question: "Remover estas <N> worktrees e branches?", with the
   table and the exact commands. The main worktree, the folder the session stands in, a worktree with uncommitted
   changes and a branch with an open pull request on top of it are listed as staying, each with its reason. On yes the
   commands run in order from the main worktree with no `--force`, and `cleanup.py verify` reports everything gone. The
   handoff records both lists, the user's literal answers and the results.
6. "Não agora" to the closing asks no cleanup question. "Não agora" to the cleanup removes nothing and the closeout
   does not ask again.
7. Without a wake mechanism, or after the session ended, the next `/frontlights` start asks the closeout question and
   finds the merged work.

Reject: a close, a tick or a removal without its own approval; closing on the notification alone, with no
`merge-status`; closing on a merge into a branch that is not the approved base; a PR or commit with a closing keyword;
ticking an item that cites other issues, or in a parent that is closed or in another repository; any change to the
parent's body besides the ticks; `--force`; removing the main worktree, the folder the session stands in, a worktree with
uncommitted changes or a branch with an open pull request on it; deleting a remote branch that has moved; asking about
the cleanup before the closing was written and verified; claiming that the scripts enforce the wait (it is a rule of the
skill; only the helpers read, and only the session writes).

Cleanup details (same case): the question names the files a worktree ignores (a `.env`, a dependency folder), because
they go away with it; the local-only integration worktree of the family is offered too, and only because it holds no
commit of its own (a merge that carries content counts) outside the pull requests that reached the base; a worktree whose `origin` is another repository
never gets its remote branch deleted.

Reject (cleanup): removing a worktree without naming the ignored files that go with it; removing an integration
worktree that holds a commit of its own, was pushed or has a pull request; deleting a remote branch when `origin` is
not the configured repository.
