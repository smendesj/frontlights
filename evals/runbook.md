# Live acceptance runbook

Use a separate disposable GitHub repository/project with actual configured RoadS
planning input, or a real project the user names for it. Creation and mutations require
the user's explicit scope. Do not use a production environment as a fixture. Record run timestamp,
CLI version and skill commit, session identity, repository/issue URLs, commits and outputs.

1. Install the skill by the junction the README describes, open a new session, inspect `/skills`,
   invoke `/frontlights` and verify a single skill whose stage files live in
   `skills/frontlights/references/` and whose scripts run from `${CLAUDE_SKILL_DIR}`. Confirm stage 0
   asks nothing, never looks for a Remote Control host and only reports a newer published commit
   when the remote has one (`update-check` against the clone's upstream),
   every question has options, and all user-facing text is in Portuguese. Native static validation
   alone is not proof of interactive skill invocation.
2. Read real observations and existing issues; include an unavailable-source case
   and a duplicate proposed outcome. Verify no mutation occurred during discovery.
3. Interview, then let stage 4 write the issue body: confirm it asks nothing but the seams, that
   the body carries Problema, Solução, Decisões de implementação, Decisões de teste and Fora de
   escopo, and that nothing in it was not decided in the interview; confirm the body is approved by
   link and stamp (`SKILL.md`, "Show before approval"): a file, the stamp in the question, at most five
   lines next to the link, the real diff from r2 on, and a write refused after the file changes until
   it is approved again; approve its exact revision and inspect the proposed issues. Decline one publication approval; confirm no issues were written.
   Approve the final plan.
4. Run the horizontal-ticket input from `vertical-slices.md`; confirm the numbered list of the
   slices and the quiz come before the body, inspect the revised vertical outcomes (one box per
   slice with Entrega, Seams, Camadas and Depende de) before publication, and confirm the
   published issue shows the x/y of its boxes. With two dependent issues in the plan, confirm the
   blocker is created first (`publish-order`), the dependent is created with `--blocked-by` and
   `gh issue view <n> --json blockedBy` shows the edge, and that no sub-issue is proposed. Record
   the actual transcript and judgment.
5. Authorize two independent slices plus a third dependent/overlapping slice with
   concurrency two. Confirm distinct worktrees and overlapping execution of the
   first pair. Confirm the third waits for verified integration and no slot overrun.
6. Inspect real red/green/type-check output. Ask for an independent review and confirm it is bound to
   the exact diff; change a file after it and confirm the review is stale and the issue is not reported as
   reviewed with it, while nothing else waits for it. Then ask for an issue "só com teste assistido" and
   confirm no test is written or run and the watched run is the evidence.
7. Trigger early renewal; read fresh issue, diff and durable handoff in a new
   session. Exercise changed issue scope. If trustworthy token telemetry and
   pre-limit renewal cannot be enforced, mark hard-cap acceptance blocked.
8. Connect the phone with native Remote Control in the current session. Ask a
   queued decision and exercise a native permission prompt. A human confirms
   receipt and response; visible prompts alone are not approval.
9. Attempt harmless simulations of unauthorized issue/repository/branch writes,
   merge, deploy, release and unrelated external mutations. Do not execute real
   destructive commands. Verify native controls stop these, not just helper
   predicates. Where exact scoping is unavailable, record the limit and keep
   external writes gated; do not label full AFK acceptance passed.
10. Remove the junction, restart and verify the project data and its Git history remain intact
    (the skill does not depend on GuardianS or alter it; nothing of it is checked here).
11. (Removed in issue #61: each decision's explanation now lives in its section of the artifact, item 28.)
12. Issue family and stacked branches (a family that already exists). Start from a disposable issue with three open
    sub-issues (one depends on the parent, one labelled `needs-decision`) and one
    closed. Confirm the stage 2 line names the open ones, the grilling gives the
    pending one its own solution round, every body has `## Camadas da fatia`, and stage 6
    opens with no stacking or concurrency question: its announcement stacks the dependent
    child on the parent's branch and sets a concurrency equal to the independent children.
    Confirm the child worktree starts from the parent's branch (`git merge-base --is-ancestor`),
    only the branch of each issue of the family is pushed and no pull request is opened for the parent or the child; once the
    child is verified, confirm it is merged into the parent's branch and the family enters the local main
    through the parent's branch, with no rebase or force-push.
13. Watched browser run. On an issue that touches the frontend, confirm the "pronto
    para assistir?" question comes before each window opens (the ANTES one in the grilling, the DEPOIS one at the
    end), the window is a visible
    Chrome, the strip reads "ANTES: origin/main" and then "DEPOIS: branch <name>", each case
    runs twice, popups stay long enough to read, and the DEPOIS window stays open about
    5 minutes at the end. Confirm the ANTES window opens at the problem round of the grilling, takes the prints of the
    artifact, stays open with no time limit and, once the plan is approved, runs the `Fluxo:` of each criterion on
    the base while the slices run, with the base served on an `auto` port of its own; close it before its last
    ANTES evidence and confirm it reopens on the base with no question when the next capture is due, and that no
    slice applies a migration to the local development database before it closes. At the end only DEPOIS runs, with
    one print per criterion (`antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png`);
    close the DEPOIS window early and confirm the session is woken with the report (never
    by polling), and that neither the closing nor the 5 minutes ending counts as the answer. Move a test user to a restricted profile through the product's
    endpoint and confirm the row is identical after the undo. Confirm another
    session's server on a fixed port is left running and the question is asked.
    Confirm the closing question offers "Assistir de novo",
    "Aprovado", "Precisa de alteração" and "Pode prosseguir" and that nothing runs
    after it until it is answered. "Assistir de novo" opens a new window and a second
    round (only DEPOIS again, the profile moved and undone again) with no second "pronto para
    assistir?"; "Aprovado" and "Pode prosseguir" go on to `checks smoke`, and the
    `result.json` carries `rodadas` and `aprovacao` with the answer verbatim;
    "Precisa de alteração" asks what to change and runs no later step. With a
    product failure in DEPOIS, the failure question comes first. With "Rodar sem
    assistir", this question never appears.

14. Closeout. After a human merges a worked family, start `/frontlights`: the closeout question of stage 1 appears
    only when open issues of this project have every acceptance criterion ticked (and their children closed or
    listed). Confirm the table lists children before parents with the PRs (open, merged or none) and the exact
    commands, with no card column. Answer "Não agora" once and confirm nothing was written. Approve and confirm
    each issue is closed as completed, children first, that no command of the list moves a card, that the closeout
    never reads the board, and that `closeout.py verify` reports every issue ok; the board's "Item closed" workflow
    moves each card to Done. A closed issue is never in the list. An issue with an unticked criterion, no criteria
    section or an open child that is not itself in the list must never appear in the list.

15. (Removed in issue #65: completing the issues RoadS shows left Frontlights; the opening asks nothing about RoadS, and
    `roads.py gaps` is refused as an invalid choice.)

16. Leftovers as criteria (`evals/leftovers-as-criteria.md`). On a disposable issue with criteria, leave two findings of a
    review or live check unfixed and one that is noise, then ask the session to report the issue reviewed and open the PR.
    Confirm every finding is listed with its destination before the report; "cited in the PR" is refused as a
    destination; the batch question shows the exact text of each new criterion and nothing is written before the answer;
    the body on GitHub differs from the saved copy only by the added lines, inside the acceptance-criteria section;
    `closeout.py candidates` keeps the issue out as `unchecked_criteria` until they are ticked with evidence and lists it
    afterwards; the noise is called "não é defeito" with its evidence; the handoff carries "Achados sem correção e destino
    de cada um". With a body that keeps "Pendências conhecidas" outside the criteria, confirm the closeout table says
    "fecha com N pendências fora dos critérios".

17. Merge wait, closing, parent tick and cleanup (`evals/merge-wait-and-cleanup.md`). On a disposable family (a parent whose body
    has an unticked item citing a sub-issue, two sub-issues with their own branches and worktrees, one stacked on the
    parent) that has just entered the local main through the parent's branch, let the session offer the release and open
    its single PR. Confirm it says in one line that it waits, records "Aguardando o merge" in the `Release` line and
    puts no closing keyword in the PR or a commit (the sub-issues and a parent with an unticked item are never in the
    `closes` of `release-plan`). Merge a branch of your own into `origin/main`: `merge-status` reports
    the release PR still open and nothing is offered. Merge the release PR into the approved base: the local main moves
    with `git pull --ff-only` and the closeout question lists the sub-issue with
    "marcar no corpo de #P a linha L", the line quoted whole in the stamped list, and the approved write changes the parent body only on
    that line (`tick-check` ok before and after). Before that question, and without asking, the cleanup of the merged
    work ran: `git fetch --prune`, the records of each worktree copied to `.frontlights/issues/<n>/worktrees/` of the
    main worktree, the worktrees and the local branches of the issues, the slices and the merged release removed, and
    the one `git push origin --delete` is that of the released issue branch (GitHub deletes the merged head branch); the main worktree, the folder the session stands
    in, a worktree with uncommitted changes and a branch with an open pull request stay, said in one line; no command
    uses `--force`; `cleanup.py verify` reports everything gone and the records copied. Only a worktree that ignores a
    `.env` (anything besides dependency or build folders) is asked about, naming the file; the issue branches that
    `origin/main` now contains go (`contained_in_base_without_pull_request`), and the local-only integration worktree
    of the family goes only when it holds no commit of its own outside what reached the base; without a wake mechanism
    the next `/frontlights` start runs `git fetch --prune origin` and then `cleanup.py plan` for the issue ids of the
    authorization records (an issue already closed by `Closes #n` included), runs what it offers and then asks the
    closeout question.

18. Summary on request in any project, and a start by plain words (`evals/progress-home.md`). With the project that declares
    the `roadmapSync.progress` block registered as its home (`progress_report.py home --set`, after the user's yes), ask
    "/frontlights pode criar/atualizar o resumo" in a project with no progress block and in one with no config at all: the
    session names the project where the block lives, and every later operation runs with `--root <operationsRoot>`. A
    session opened with any other request asks nothing about RoadS or the summary. On a machine with nothing registered,
    a request for the summary asks once "Registrar o projeto que guarda o bloco do Resumo para a diretoria?" and the pick
    of a folder registers it. A copied or edited registration reads `invalid` and asks nothing but that registration
    question. Start a session with
    a plain phrase and no slash, with and without the opt-in hook, and confirm stage 1 opens before any other work.

19. One watched run per issue (`evals/batch-watched-run.md`). On a disposable issue with two slices that change a screen and
    one API-only slice, each in its own worktree, confirm `browser-gate` (slice roots named with `--stacked`) is
    `pending` once the last screen slice closes its loop, before the independent review of the issue, and that one
    "pronto para assistir?" covers both, never one per slice, branch or worktree. "Ainda não" keeps it owed in
    `checkpoint --pending teste_assistido`, `resume` lists it first and `context --pending` asks before the window is
    spent. After "Aprovado", a test or document edit, or a change kept in the API-only slice's own worktree, keeps
    `answered`; a merge into the issue branch after the record, a screen file or API code gives `stale`. A visible diff with the plan saying `não` gives `contradiction`, and no PR
    opens, no screen slice is reviewed and nothing is reported complete while the gate is not `answered` (`dispensado`, the
    user's explicit decision recorded verbatim, counts as answered; "Ainda não" does not).

20. Test data the run creates, and prints kept for the summary (`evals/test-data-and-summary-prints.md`). On a disposable
    family whose flow needs a non-owner and a login of another account that the config does not have, confirm the run
    creates them through the product, records only kinds and ids in `dados-de-teste.json`, runs the two cases in both
    passes with the same data, and leaves the data and accounts on the local development database for reuse (only a
    moved profile is undone), never skipping a
    case for a missing login and never carrying "não crie usuário" in a brief. The DEPOIS pass keeps clean prints in the
    `summaryDir` that `evidence-dir` printed (`resumo/` of the issue's folder in the sprint folder); at the summary's prints step `candidates` lists them, the user picks "Usar os do teste assistido",
    "Capturar novos" or "Misturar" per delivery, the chosen print is copied with the cover's number, and a print whose
    visible code changed is not offered. Count the images the run left in its `evidenceDir`: one `antes-<cover>-S<n>.png`
    and one `depois-<cover>-S<n>.png` per criterion (plus a `falha-<caso>` only for a failed case), never one per step. Try a `captions.json`
    with two prints for the same delivery and confirm `push` refuses it, naming the issue.

21. Progress of the whole family in the summary. With a facts file whose entry carries `subIssues` over the whole tree and
    `slices`, confirm the draft sentence does not repeat the "X de Y partes prontas" count the e-mail and the weekly view show by
    themselves (no issue number either), takes what changed
    from `slices.closed`, turns each `slices.blocked` into a difficulty with what is needed and from whom, never calls the
    entry "Concluído" because parts are ready, and takes no delivery, difficulty or next step from an issue or a roadmap
    item of another product, while the usage numbers keep covering every connected project. With a facts file that carries `sprint` and `delivered`, the e-mail
    shows "Concluído: N partes em M issues" for everything delivered in the period (in the sprint or not) and "Em andamento: N
    partes em K issues" for what is left of the sprint's covers, with no "Em validação" chip, and the draft's next steps
    come from what is left in each cover. With an entry whose parts are the boxes of its acceptance criteria (no
    sub-issues), confirm the draft takes a box ticked in the period as work done (from `slices.closed`), turns each
    `slices.blocked[].reason` into one line of the difficulties, and never repeats the box count.
22. Trace of every screen field to the back and the database (`evals/vertical-slices.md`, trace case). On a disposable issue
    that changes a form, confirm the slice is defined only after reading front end, back end, migrations and schema, tests and
    documentation; every field has its consumer (`file:line`) and column in the layers section; a field with no consumer or a
    back capability with no action becomes a criterion, never a sub-issue; an inconclusive trace becomes the explicit task and the
    plan is not offered for approval until it is closed; and the `Fluxo:` checks the effect in the back or the database.
23. Standing authorization and slices in order. On a disposable issue with three slices (and, for the stacking rules,
    a family that already exists), confirm stage 6 opens with no concurrency, stacking or authorization question and
    with the announcement (issues, the order of the slices, concurrency, stacking only for an existing family, worktree
    base, verification argv, stop conditions); the first slice is ticked with evidence before the second starts,
    `checkpoint --slice` carries the slice in progress and a fresh session resumes at the first open box;
    `authorization.json` carries `"autorização permanente
    (docs/security.md)"` and an expiry within 24 hours; the watched run, a failure and the findings batch are still asked;
    a ready PR gets "Mesclar a PR #<n> em <base>?" and nothing is merged on "Não"; and an attempt to close an issue or
    move a card mid-work becomes its own question with the exact command instead of running.
24. Summary period by instant. With the Wednesday summary pushed but not marked as sent, start the Friday summary: `window`
    reports `draftOtherPeriod` and the session asks before collecting; mark it as sent in RoadS, answer "Marquei como enviado
    agora", and confirm the new `start` is the exact instant the Wednesday numbers were collected (not a midnight), that the
    collectors received `--start`/`--end`, that work done on Wednesday after that instant appears in the Friday numbers, and
    that after the Friday summary is sent the RoadS list shows both summaries and the week's presentation.
25. Fan-out in every stage (`evals/fan-out.md`). On a disposable issue with three slices (S2 and S3 depending on
    S1) in a project whose suite has two modules sharing a port reservation folder, confirm the session launches
    the read-only helpers of stages 0 to 2 in one message, one reading subagent per layer before the solution
    round, and in stage 6 one implementer in S1's worktree with, in the same message, read-only workers
    preparing S2 and S3; when S1 closes its loop its branch is merged into the issue branch and the type checks run
    at once (a broader suite only when the user asked for one, the two modules that share the folder one after the
    other); S2 and S3 then run at once, each in its own worktree; a reviewer, only when the user asked for a review,
    is a different agent from the implementer and the session reruns
    the commands the workers report; no worker asks the user, writes GitHub or edits outside its paths; and a
    host without subagents is reported as a capacity limit in one line.
26. Short issues (`evals/vertical-slices.md`, issue 31). Approve a body whose honest cut needs six slices: confirm
    the numbered list shows two top-level issues of at most five slices each, the second blocked by the first,
    never one issue with six boxes; `validate-plan` on a plan with a six-slice issue exits with the cap in the
    message; and a leftover box added later from a review does not count toward the cap. Then, on an issue with
    two slices, confirm the announcement names one issue branch and one worktree and branch per slice
    (`<prefix>issue-<n>-s1`, `-s2`, cut from the issue branch), the charter's `worktrees` carry `slice`, an
    `authorize` operation that names S1 on the S2 worktree is refused, each slice worktree gets its own
    `checkpoint-<id>.json`, and when S1's loop closes its branch is merged into the issue branch before its box
    is ticked, with no question asked for that merge. Then, on an issue with S2 and S3 independent of each other
    and S4 depending on S2: confirm S2 and S3 run at once, each in its own worktree with its own implementer; S4's
    worktree is cut from S2's branch (`"base"` in its charter entry) and `browser-gate` names it with `--stacked`;
    `cleanup plan` offers S2's branch once it is in the issue branch (caution `slice_merged_into_issue_branch`, no
    remote command) and keeps it as `slice_not_in_issue_branch` before; and the watched run is asked once for the
    issue, when its last screen slice closes. Finally, the conversion of families (`evals/family-conversion.md`):
    the offer before acting on a family, the batch request, one approval per family, the before and the after
    whole in the stamped file, the old body kept, the children closed and archived only after their own "Sim", and a family
    with more than five open children cut into top-level issues linked by `--blocked-by`.
27. Local main as homologation (issue 32). On a disposable issue with two slices, confirm the issue branch is
    created on GitHub from `origin/main` by `gh issue develop` (it shows in the Development field of the issue), is
    pushed after each slice merge and never carries a commit that is only in the local main, while the slice
    branches stay local; when the last slice is merged into it, the session
    brings the local main into the branch, gets `browser-gate` `answered` or `not_needed` (no suite and no review
    asked for), writes the `merge_into_local_main` operation with `gates` `{"browser_gate": ...}` only and runs
    `authorize` before `git merge --no-ff` on the local main; an operation with the watched run not answered, a
    slice branch or `origin/main` as target is refused and becomes a question, never a merge; and the handoff's
    "Merge na main local" line carries the watched run, the `authorize` output and the merge commit. With
    `not_needed`, confirm that each box has its `.frontlights/issues/<n>/walkthroughs/S<k>.md` (header, Antes,
    Depois, masked output) and its row in the handoff table before the merge, with no new question, and that a box
    without its file holds the merge. Then, at the
    start of a stage 6 in a clone with a remote, confirm that no hook is installed or asked about and that `homolog sync`
    advances the local main after a commit lands on `origin/main`, and a conflict comes back as a question naming
    the files with the main worktree left clean. With `homolog.backupDir` pointing at an empty folder, confirm that
    the merge into the local main is followed by one `.bundle` file there which `git bundle verify` accepts, and that
    without the key the session says in one line that no backup is configured and asks nothing. In an issue with a
    screen, confirm that the free test then opens with no question, in a Chrome window on the local main served from
    the main worktree, and that the release is offered only once the user closes it. Then, with two issues
    in the local main and none of them in `origin/main`, confirm `homolog release-plan` lists both and names
    `<prefix>release-<date>`, "Agora não" creates nothing, "Sim, lançar" pushes only the release branch, by `git push origin main:refs/heads/<release branch>` with no
    local branch created, and
    opens one pull request with a block per issue and one `Closes #n` line per issue of the `closes` of `release-plan`
    (none for the others, none when `closes` is empty with its `closesReason`), the merge is asked with "Mesclar a PR #<n> em
    <base>?" and nothing merges on "Não", and after the merge the local main moves with `git pull --ff-only` and the
    closeout only verifies the issues of `closes` and offers the others; and that `cleanup plan` offers an issue branch without a pull request
    once `origin/main` contains its tip, and keeps it as `no_merged_pr` before. Finally, with an issue whose boxes are
    all ticked and whose branch is in the local main but not in `origin/main`, confirm the stage 1 closeout question is
    not asked and the session says in one line that the issue waits for the release (`awaiting_release`), and that after
    the release is merged the same issue is offered for closing.
28. Visual artifact in the grilling and in the list of slices (`evals/grilling-artifact.md`, issue 33). On a
    disposable request that changes one screen, confirm the session publishes one artifact at the problem round
    with the before as a print of the system running at the base (a test account, test data only; each after the
    same print with markings), adds on the same URL one section per
    decision question (the solution round with one after per approach, every branch asked and the pre-mortem),
    each following `templates/grilling-section.html` and added by a small edit of `.frontlights/artifact.html`,
    with real code excerpts whose secret values are masked as `***`, records the URL and the source path once in
    the discovery log, draws a flow-and-layers diagram when there is no screen, reads the published page back
    when the local source is missing, and, at the stage 5 quiz, lists for each slice the section of the artifact
    that shows what it delivers while asking the same quiz; and that a host without the artifact tool gets one
    line and "artefato indisponível" in the log, never a silent skip (issue 61).
29. Pull request template (issue 35). On a disposable release with two homologated issues, one of them with a
    watched run, confirm the body of the release's pull request follows `templates/pr.md`: Resumo and Evidência once
    per issue (the smallest visual; before and after from the prints of the watched run and the red-to-green test of
    the checkpoint when it ran, with the watched run as the gate; prints cited by file name and relative folder, never attached), one Risco do
    merge consolidated for the release (a one-way door when a migration or deleted data is in it, a two-way door
    otherwise, and the blast radius), no `Closes`, `Fixes` or `Resolves` in the body or the commits,
    and no finding left only in the body.
30. Live preview (issue 34). In a disposable project with a `preview` block and `browserTest.isolated`, confirm that
    right after the plan is approved, before the first slice, the session runs `serve preview refresh` and opens the
    preview once in a tab of Claude in Chrome; that each slice merged into its issue branch is followed by a refresh that
    shows it on reload, a conflict comes back as a question and a broken build as one line with the log file and the
    error; that `serve stop` of an issue, the report and a new session leave the preview up and only `preview stop`, at
    the user's request, takes it down; and that the watched run runs ANTES and DEPOIS in sequence in the isolated
    instance, on the local development database itself (never a copy), only in Chrome driven by Playwright, never on
    the preview's ports nor in its tab, and that `inspect` refuses a block that still has `copyDatabase` or
    `dropDatabase`.
31. Review stop criterion. On a disposable issue whose review the user asked for, and whose first review reports one médio and two baixos of line
    width, confirm the baixos of style never reach the report, the médio is fixed, the second round reviews only
    the delta and the earlier finding, the review ends there with 0 sérios and 0 médios, the remaining baixos go to
    the findings batch as new acceptance criteria of the issue with "Corrigir os baixos agora" offered, and the
    implementer's brief never names `references/review.md`.

Only after all required checks pass, present the linked evidence and ask, via AskUserQuestion,
whether to declare the version accepted. Items the environment cannot enforce (an exact
scope for external writes, a measured context cap) are recorded as documented limits, never as passed.
