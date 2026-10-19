# Test data the run creates, and prints kept for the summary (manual; no model score claimed)

Setup: a disposable project with `browserTest`, a local disposable database and a family of a parent and two
sub-issues that change screens; one `Fluxo:` item needs a non-owner of the same account and another needs a login of
another account (the config has only the accounts of the owner). A progress block is approved in the registered
project, with `weekShots`, and the facts file has one entry for the parent with `subIssues` and `slices`.

Expected, in this order:

1. The watched-run question says, in one line, that the run creates the test users and accounts its flow needs and removes
   them afterwards. It adds no option and asks no extra question.
2. The brief handed to the subagent that runs the passes carries the rule: it says to create the missing non-owner and the
   other account, and says nothing like "não crie usuário", "pare se faltar login" or "espere a decisão".
3. Before the first creation `dados-de-teste.json` exists in the lead issue's folder; each created user, account and
   profile is added with its kind and id and `removido: false`; no login, password or whole row appears in it. The password
   of a created login is only in a git-ignored local file and in the environment of the browser process.
4. The non-owner case and the other-account case run in ANTES and DEPOIS. Neither is skipped nor parked for lack of login,
   and the answer "Assistir de novo" keeps the data for the next round.
5. After the closing answer the items are removed in reverse order through the product's endpoints and read back; each entry
   turns `removido: true`. What the product only anonymizes is listed in the report with the exact `DELETE` of each id this
   run created, shown in full in an `AskUserQuestion`, and nothing runs before the answer. Interrupt a run: the next
   session removes the entries not marked before anything else.
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
or password in a record, a caption, a screenshot, the conversation or a brief; data left behind without a report; a
`DELETE` run before the user approved it; a real person's or customer's data touched; a print with the ANTES/DEPOIS strip,
a login, a path or a person's name copied to the synced folder; a print offered after the code changed; the slice's number in
`captions.json` instead of the cover's; a kept print moved instead of copied.
