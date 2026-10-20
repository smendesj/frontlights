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
3. The user merges the release's pull request into the approved base. `merge-status` lists it as `ready`, the session
   runs `git pull --ff-only` on the local main and then the closeout for the issues of the release. A sub-issue with all
   criteria ticked appears with "marcar no corpo de #P a linha L", the line quoted whole in the list file approved by link and stamp
   (`SKILL.md`, "Show before approval"); the item that cites two issues
   is listed as not ticked. The question reads "Fechar estas <N> issues, mover os cartões para Done e marcar os itens dos
   pais?". An issue with an unticked criterion is not offered, and the session says which criteria are left.
4. After the answer, the sub-issue is closed first and then the parent's body is rewritten: the difference against the
   saved copy is exactly the listed line with `[ ]` turned into `[x]`, `tick-check` answers `ok` before the write and on
   the reread, and the parent's other items are untouched. If the parent now has every criterion ticked and every child
   closed, it is offered in the same way.
5. Only after the closing is written and verified, a second question: "Remover estas <N> worktrees e branches?", with the
   table and the exact commands. The issue branches, never pushed, are offered because `origin/main` now contains their
   tips (caution `contained_in_base_without_pull_request`, no remote command); the main worktree, the folder the session
   stands in, a worktree with uncommitted changes and a branch with an open pull request on top of it are listed as
   staying, each with its reason. On yes the commands run in order from the main worktree with no `--force`, and
   `cleanup.py verify` reports everything gone. The handoff records both lists, the user's literal answers and the results.
6. "Não agora" to the closing asks no cleanup question. "Não agora" to the cleanup removes nothing and the closeout
   does not ask again.
7. Without a wake mechanism, or after the session ended, the next `/frontlights` start asks the closeout question and
   finds the merged work.

Reject: a release branch cut or pushed without the user's "Sim, lançar"; a push of the local main or of an issue
branch; a close, a tick or a removal without its own approval; closing on the notification alone, with no
`merge-status`; closing on the merge of an issue into the local main, or on a merge into a branch that is not the
approved base; a PR or commit with a closing keyword; ticking an item that cites other issues, or in a parent that is
closed or in another repository; any change to the parent's body besides the ticks; `--force`; removing the main
worktree, the folder the session stands in, a worktree with uncommitted changes or a branch with an open pull request on
it; deleting a remote branch that has moved; asking about the cleanup before the closing was written and verified;
claiming that the scripts enforce the wait (it is a rule of the skill; only the helpers read, and only the session
writes).

Cleanup details (same case): the question names the files a worktree ignores (a `.env`, a dependency folder), because
they go away with it; the local-only integration worktree of the family is offered too, and only because it holds no
commit of its own (a merge that carries content counts) outside what reached the base; a worktree whose `origin` is
another repository never gets its remote branch deleted; an issue branch whose tip is not yet in `origin/main` stays as
`no_merged_pr`.

Reject (cleanup): removing a worktree without naming the ignored files that go with it; removing an integration
worktree that holds a commit of its own, was pushed or has a pull request; deleting a remote branch when `origin` is
not the configured repository; offering an issue branch before `origin/main` contains its tip.
