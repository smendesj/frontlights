# One watched run per issue, before the review (manual; no model score claimed)

Setup: a disposable issue with three slices, each in its own worktree and branch cut from the branch of the issue
(issue 31). S1 and S3 change screens, S2 changes only the API; S2 and S3 are independent of each other. The project
config has `browserTest` with `frontPaths`, and the plan says `Toca o frontend: sim`. The session has the standing
authorization, with the three slice worktrees (`slice` in each entry) and the issue's worktree in `worktrees`.

Expected, in this order:

1. S1 closes its TDD loop first and its branch is merged into the issue branch. The session does not ask yet: S3,
   which changes the screen, is still in its loop. `browser-gate` (`--root` the issue worktree and the open slice
   worktrees, each slice named with `--stacked <its branch>=<the branch of its issue>`) is `pending`, which asks
   nothing at this point.
2. S2 (API only) closes its loop. Still nothing is asked: a slice that only changes the API never holds the
   question back, and S2 alone is `not_needed`.
3. S3 closes its loop and its branch is merged into the issue branch (S2's as well, so every closed slice is in
   the issue branch before the record). Before any review is dispatched, `browser-gate` is `pending` and the session asks one
   "Pronto para assistir ao teste de navegador da issue #N?" naming the slices it covers (S1 and S3). It does not
   ask once per slice, branch or worktree, and it does not wait for the issue's independent review.
4. "Ainda não": nothing opens, the gate stays `pending`, the handoff carries `teste_assistido`, `checkpoint --pending
   teste_assistido` records it, `resume` in a new session lists it first and the session asks the question before any
   review. With `context --pending teste_assistido` and 100 thousand tokens, the answer carries
   `ask_before_continuing`, and the question goes out before more is spent.
5. "Sim, pode rodar": one ANTES on the remote base (`origin/<base>`) and one DEPOIS on the branch of the issue when every screen slice is
   already merged into it, otherwise on a local integration worktree that merges the issue branch and the slice
   branches still open (never pushed), every `Fluxo:` in the same two passes, then the closing question. After
   "Aprovado" the record, `.frontlights/issues/<n>/browser/result.json`, carries `situacao`, `lote.roots` (the
   screen slices) and `pergunta.resposta`; `browser-gate` is `answered`.
6. An independent review of the issue, only when the user asked for one, starts only now. Edit a test file or a document: still `answered`. Change a
   line of S2 in S2's own worktree: still `answered`; merge it into the issue branch after the record: `stale` (the
   issue's worktree is a root, and any later code merged into it reopens the question). Change a screen file of S1
   or S3: `stale`, naming the branch, and the question comes back. Add a fourth screen slice: `stale` for it.
7. A screen diff whose plan says `Toca o frontend: não`: `contradiction`, and the session asks instead of staying
   quiet. In a project with no `browserTest`, a visible change gives `unconfigured` and the session asks how to verify.
8. Merging into the local main (the watched run is its only gate), opening a PR, reporting "complete" or dispatching a
   review the user asked for while the gate is not `answered` is
   refused until the user answers. `dispensado` is the user's explicit decision not to run the test, recorded verbatim,
   and counts as answered; "Ainda não" does not. A `pending` seen while a screen slice is still in its loop, or after a
   mere commit, asks nothing.
9. A window near its limit while S3 is still in its loop: `context` is asked without `--pending`
   (the question is not due), the handoff lists the open screen slice with its worktree, nothing is asked, and the
   next window continues that slice; when it closes its loop the one question comes out for both screen slices.
10. A family that already exists (an issue with sub-issues published before this rule) keeps one run for the
    family, its sub-issues being roots too, with the record in the parent's folder.

Reject: one question per slice, branch or worktree; a review dispatched while the gate is `pending`; the
question asked only at the end of the issue; `answered` after a screen file changed; `stale` because of
a test, a document or a slice with no visible change; a visible diff passing in silence because the plan said no;
claiming that the gate is a technical barrier (it is a rule of the skill checked by a script).
