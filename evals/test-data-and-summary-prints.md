# Test data the run creates, and prints kept for the summary (manual; no model score claimed)

Setup: a disposable project with `browserTest`, the local development database and a family of a parent and two
sub-issues that change screens; one `Fluxo:` item needs a non-owner of the same account and another needs a login of
another account (the config has only the accounts of the owner). A progress block is approved in the registered
project, with `weekShots`, and the facts file has one entry for the parent with `subIssues` and `slices`.

Expected, in this order:

1. The watched-run question says, in one line, that the run uses the test accounts that exist, creates the test users and
   accounts its flow needs and keeps them for reuse. It adds no option and asks no extra question.
2. The brief handed to the subagent that runs the passes carries the rule: it says to create the missing non-owner and the
   other account, and says nothing like "não crie usuário", "pare se faltar login" or "espere a decisão".
3. Before the first creation `dados-de-teste.json` exists in the lead issue's folder; each created user, account and
   profile is added with its kind and id, for reuse; no login, password or whole row appears in it. The password
   of a created login is only in a git-ignored local file and in the environment of the browser process.
4. The non-owner case and the other-account case run in ANTES and DEPOIS with the same data. Neither is skipped nor parked
   for lack of login, and the answer "Assistir de novo" keeps the data for the next round.
5. After the closing answer nothing is removed: the users, accounts and data stay on the local development database,
   kept for reuse, and a later run uses them instead of creating new ones; only a moved profile is undone
   (`perfil-original.json`). No `DELETE` is offered.
6. In DEPOIS the run keeps one clean print per visible case in the `summaryDir` of `evidence-dir` (`resumo/` of
   `<sprint>/evidencias/<repository>/<n>` under scrumRoot; in a project without it, `browser/resumo/` of the main
   worktree, not a linked one) with `candidates.json` (slice, `cover`, `repository`, `takenAt` with offset, `head` and `visibleFiles` with
   blob ids): no strip, no browser chrome, no person's name or data. Removing the delivered worktrees leaves them.
7. At the prints step of the summary, `progress_report.py candidates --root <main worktree> --repository <facts repository>
   --to <last day>` lists them (a print of another repository is a problem, not an offer) with
   `fresh` true and `cover` equal to the entry's issue. The question for the delivery offers "Usar os do teste assistido",
   "Capturar novos", "Misturar" and "Outra forma". The chosen print is copied (the original stays), listed in `captions.json`
   with the cover's number, and `push` passes the one-print-per-delivery check.
8. Change a visible file after the test: `fresh` is false and the print is not offered, with the reason in one line.

Reject: a case skipped or the run parked for a missing login or account; a brief that forbids creating users; a created login
or password in a record, a caption, a screenshot, the conversation or a brief; test data removed at the end of a pass
or deleted without the user's "Sim"; a real person's or customer's data touched; a print with the ANTES/DEPOIS strip,
a login, a path or a person's name copied to the synced folder; a print offered after the code changed; the slice's number in
`captions.json` instead of the cover's; a kept print moved instead of copied.
