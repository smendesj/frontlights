# Browser, checks and cross-account testing

Read when: before any pass of the watched run is run or dispatched, and at the first non-zero exit of
`browser-gate`; an exit 0 needs nothing from here.

On entering, read `docs/security.md`, "`serve`, `checks` e o teste no navegador", and `docs/protocol.md`,
"Teste no navegador" (the fields of `result.json` live only there).

It applies whenever anything the session delivers changes what the user sees: the
plan has the section `## Navegador e testes ligados` (`templates/issue.md`) with `Toca o frontend: sim`, or
`browser-gate` finds a visible change in the diff (the browser step opens with the watched-run question below and,
when the user watched, ends with the question of what to do next). **Portuguese.** Everything the user reads stays in Portuguese,
including what the browser tools print. Never point a test at a real, staging or production environment. A run never stops or skips a case for lack of test
data (section "Test data the run creates"). No script judges a pass: passed or failed is the session's and the
user's, looking at the screen together.

## What the plan turns on

Read the four fields of that section and restate them in the handoff before running anything:

- `Toca o frontend:` `sim` turns the browser test on; `não` skips it.
- `Conta:` `conta 1` (the default) or `contas 1 e 2`.
- `Fluxo:` the order in which the watched run walks the walkthroughs of the boxes (the `Roteiro:` lines of each box:
  `references/issues.md`), with the expected result and the effect in the back and the database after saving,
  checked through the product's own read path or a read-only query the project already permits, never only what
  the screen shows.
- `Testes ligados:` any of `navegador`, `integração`, `regressão`, `permissões entre contas`, `smoke`, plus extra cases.

A missing section on an issue that changes screens, or a field that contradicts the diff, parks the issue and goes
to `AskUserQuestion`; never turn tests on or off alone. Run only what is on, in this order: `checks regression`,
`serve start`, `checks integration`, browser and cross-account steps (the DEPOIS pass: its ANTES already ran from the
grilling), `checks smoke`, `serve stop` of the issue (never `preview stop`: the preview stays up). The commands below
read `browserTest` and `checks` from the project's `.frontlights/config.json`.

## One watched run per issue

There is one watched run per issue, never one per slice, branch or worktree. Here a slice is a box of the issue with its own worktree, and each `--root` is the worktree of an issue or of one
of its slices. A family that already exists keeps one run for the family, its
sub-issues being roots too. A slice that only changes tests or only the API does not hold the question back.

**When the question comes out.** The question of DEPOIS (ANTES evidence never answers the gate) comes out only at
these points, each one after `browser-gate`: (a) when the last slice that changes the screen has closed its TDD loop
and every slice already closed is merged into the branch of the issue, which comes before an independent review of
any of them, when the user asked for one; (b) before such a review is dispatched, once no other screen slice is in
its loop; (c) before an issue that changes the screen is reported as reviewed or complete; (d) before such an issue is merged
into the local main, and before a PR is opened or updated; (e) when a session resumes with `teste_assistido`
pending. At any other moment a `pending` is expected and asks nothing. A screen slice that is parked or dropped
leaves the batch; one that comes back later is a new decision (`stale`).

**What runs.** The ANTES of the batch already ran while the slices were worked, so at this point the run is only
DEPOIS, on the delivered state: the branch of the issue when every closed slice is merged into it, otherwise a local
integration worktree (never pushed) that merges it with the slice branches still open. A slice that closes its loop
after the run and changes what a `Fluxo:` exercises makes the session ask again by hand, with the options of
`stale`; until then the report says "implementada, aguardando teste assistido", never "completa".

**The gate.** `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" browser-gate --base <base> --root <worktree> ...
--toca <sim|nao|ausente> --record <result.json>`; flags and statuses: its `--help`. A slice's worktree is
named with `--stacked <its branch>=<the branch of its issue>`. `--toca` is `sim` when any issue's plan says so
(`by_root` lists the visible files of each root). Exit 0 is `not_needed` or `answered`, 1 an error, 2 asks:

- `pending` (`ask`): for `alteracao` the change comes first and the run repeats with no new "pronto para assistir?";
  otherwise ask the question of the watched run, at the points above.
- `contradiction` (`ask-plan`): options "Rodar o teste assistido" (fix `Toca o frontend:` in the local plan; the
  issue body needs its own approval), "Dispensar o teste" and "Ainda não".
- `stale` (`ask-again`): options "Assistir de novo", "Manter a decisão anterior" and "Ainda não".
- `unconfigured` (`ask-how`): something visible changed and the project has no `browserTest` (also `browserTest:
  null`): options "Verificar à mão e dispensar", "Configurar o `browserTest` agora" and "Ainda não". Never call the
  change checked, never skip the question.

**The record.** The issue has one `result.json`, `.frontlights/issues/<n>/browser/result.json` (a family's lives in
the folder of its lead issue). Record every answer in the same call of the gate, never by hand: `browser-gate ...
--answer "<the option, verbatim>"` (a custom option adds `--option "<the gate's option>"`) writes
`situacao`, `lote.roots` and `pergunta.resposta` and reads the gate again.
"Ainda não" (`ainda-nao`) leaves the run owed as the `teste_assistido` pending of `checkpoint --pending` and `context --pending`,
carried only once the question is due; while a screen slice is still in its loop the handoff lists the open screen
slices instead. `answered` (`aprovado`, `prosseguir`, `sem-assistir` or `dispensado`) is what an independent review of
a screen slice, "reviewed", "complete", the merge into the local main and a PR require; there is no other way around it.

A Direct change with no issue has no plan: ask "Informar a issue", "Dispensar o teste" or "Ainda não"; never run
`serve` or `checks` with an invented number, and open no issue for it. A dispensed Direct change keeps its record in
`.frontlights/direct/<branch, slashes as dashes>/browser/result.json`.

## Environment and checks

`serve start|status|stop` brings up `browserTest.processes` in a worktree, records pids and ports and kills only the
trees it started; `checks regression|integration|smoke` run the suites. Their flags, exit codes and categories are
in `python "${CLAUDE_SKILL_DIR}/scripts/serve.py" --help` and `checks.py --help`, the outputs are JSON, and every
failure is a question ("Every failure is a question"). A project whose `browserTest` declares only the accounts has
no `serve start`: the session itself brings up the API and the web of the tree under test (`window open` says
`sessao_sobe`), checks they answer, stops them before reporting, never asks the user to bring them up, and offers to
declare those commands in `browserTest.processes`; it never stops a process it did not start. A dev server that pins its own ports keeps a fixed `port`, and then only one issue at a time can run it:
say so when recommending parallelism. The preview is not part of the watched run (`development.md`, "The start of
stage 6").

**Per-issue resources.** `serve.py --help` gives `{port:<name>}`, `runtimeConfig`, `setup` and `teardown`. When
`browserTest.setup` clones the database per issue, the free test and the watched run write to that clone, never to the
shared database: here, "the local development database" is that clone.

## Browser

Chrome driven by Playwright, visible, disposable profile, never Claude's built-in browser nor Claude in Chrome, which
only opens the user's preview tab; run the project's own Playwright specs when it already has them. The window comes
from `serve.py window` (below), never from a driver written from memory. Without a browser or network the test did not
run: report the reason, record it, and the issue never counts as passed on that test.

## Watched run: before and after, with the user watching

The watched run has two passes of the same scenario: ANTES on the base, whose window opens in the grilling and stays
open while the slices are worked, and, at the end, DEPOIS on the delivered state. Before each of the two windows
opens (the first ANTES window, at the problem round of the grilling, and the DEPOIS window, at the points above), ask
with `AskUserQuestion`: "Pronto para assistir ao teste de navegador da issue #<n>?" (for a family that already exists,
"das issues #<n>, #<m> e #<k>"). The text says what comes: for ANTES, the screens of the base for the artifact and,
once the plan is approved, the `Fluxo:` of each criterion on the base, the window closing by itself after the last ANTES
print; for DEPOIS, each case once, one print per criterion, and the window closing by itself at the end; that
the run uses the test accounts that exist and creates the test data the `Fluxo:` needs, which stays on the local
development database for reuse; that the database behind the server is the local development database (ask the user
to confirm it when the project does not say so); and, when the `Fluxo:` moves a test user to a restricted profile,
that it will be undone. Options: "Sim, pode rodar" first and recommended; "Ainda não" (run nothing; in the grilling,
the problem round waits for the before print, `references/grilling.md`); "Rodar sem assistir" (record `assistido:
false`). When the `Fluxo:` moves a profile, a fourth option, "Sem mudar perfil", runs the pass without the move and
declares that the permission behavior was not checked against the real back. Never open the browser before the answer. A
reopened ANTES window asks nothing. Passes never overlap while one is running: one issue at a time (a batch counts as
one) on the same account and database; an ANTES window that is open but idle holds no other issue back.

The pass is driven by whoever conducts it, a subagent or the session itself, from the brief the script fills:
`python "${CLAUDE_SKILL_DIR}/scripts/serve.py" window brief --issue <n> --pass antes|depois --criteria S1,S2` prints the
path of `brief-<pass>.md`; dispatch "read it and follow it", never its text. `--role <role>` picks the persona of
`browserTest.users`. The brief opens the window (`window open`
or `window attach`), starts the holder (`window hold`, in the background), takes the prints (`window shot`) and records
each criterion (`browser-gate record`). What the window must be:

- **Visible window.** Chrome driven by Playwright with a visible window, never headless (`headless: false`), never
  Claude's built-in browser nor Claude in Chrome, in a disposable browser context or profile, never the user's personal
  one. If the window cannot open, the watched run did not happen: report the reason and ask; never fall back to a
  hidden window silently. The tab of the preview is the user's
  and stays outside this rule: the watched run never drives it and runs never on the ports of the preview.
- **The whole screen, always.** Maximized, with `viewport: null`; `window open` answers `fits` and a `checkShot` to
  look at (do not keep that image): with the strip or an edge cut off, resize and look again, and never go on with a
  cut-off window.
- **Two passes, same scenario and same account.** ANTES runs the `Fluxo:` on the remote base of the batch (`origin/<base>`, the base the branch of the issue was created from),
  never on the local main, served from a detached-HEAD worktree made with `git worktree add` at `origin/<base>`
  (`serve start --root <base-checkout> --issue <n>`), and after each `serve start` the process answering on the port is
  the recorded one or a descendant of it (`serve status`), or DEPOIS could be answered by the base; an issue stacked on a parent outside the batch uses that parent's branch. Before the
  issue exists (a grilling that starts from a request), the base checkout is named after the discovery log and serves
  on a provisional record, `serve start --root <base-checkout> --issue 0`; the window and its prints wait in
  `.frontlights/evidencias-pendentes/`, and once the issue is published, its prints move to the evidence folder of
  the issue at the first window command with its number. DEPOIS runs the same `Fluxo:`, same account, same data, on
  the delivered state, at the end; both on the local development database. The base server takes an `auto` port of
  its own; in a project with only fixed ports, the servers of the slices and of the issue wait for the ANTES window to
  close, and `serve stop --root <base-checkout> --issue <n>` ends ANTES before DEPOIS starts. A watched run never serves from the main worktree (the free test is the only exception, "The free test
  window").
- **The ANTES window, from the grilling.** It opens at the problem round of the grilling, after the question above,
  with the strip "ANTES: <base>", and stays open: first it takes the prints of the screens for the before of the
  artifact; then, once the plan is approved, the same window runs the `Fluxo:` of each criterion on the base while
  the slices go on in parallel. It closes when the last ANTES evidence is taken or when the user closes it. Its holder
  has no time limit (`window hold --minutes none`). A window closed before the last ANTES evidence reopens on the base,
  with no question, when the next capture is due (`window attach`); `result.json` says which criteria still lack their
  ANTES. When the base receives another change in the screen files of a criterion before DEPOIS, the ANTES of that
  criterion runs again at the end, on the new base, before DEPOIS.
- **The isolated instance.** With `browserTest.isolated`, both passes run on processes and ports of their own, on
  the local development database itself, which is the homologation database, never a copy. ANTES and DEPOIS never
  run at once in that instance; never on the ports of the preview. Its processes start from their argv, without a
  shell, and the driver stops only what it started; the data follows "Test data the run creates". Without the block,
  the passes run on the issue's own serve.
- **A strip on every page.** A fixed strip pinned to the top edge across the full width, by an init script: "ANTES:
  origin/main" (the base's own name otherwise) and "DEPOIS: branch <name>". No login, password or local path ever goes
  into the strip; `window open` refuses one.
- **Pace.** Each case runs once in each pass, never repeated: one ANTES, one DEPOIS. Hold every popup, toast and dialog on screen long enough to be read.
  The holder, `window hold --minutes none`, started with the shell tool's run_in_background option by whoever drives
  the pass, keeps the strip on new pages; it exits when the window closes (the browser's `disconnected` event) and prints `ended_by`. **No wait at the
  end:** once the last criterion of a pass has its print and its record, whoever drives it runs `window close` at
  once, in ANTES and in DEPOIS. The holder of the free test has no time limit ("The free test window", below). A bare
  timer or `sleep` is not a holder.
- **Window closed, next step.** When the ANTES window closes, stop the ANTES server once no ANTES capture is due, and
  only then start DEPOIS; never start DEPOIS before that notice. When the DEPOIS window closes, the pass is over and
  the conductor reports at once. The closing question below comes after it, from the prints. Closing the window is
  never an answer to that question.
- **One print per criterion.** Each pass keeps exactly one print per criterion, taken at the same place in ANTES and
  DEPOIS, never one per step or per repetition: `antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png` (`window shot`
  names them, with a hyphen because `#` breaks a URL and the check of the push; in text, `antes#<cover>-S<n>` and
  `depois#<cover>-S<n>`); the result
  of each step stays in text, only in `result.json`, never in an image. A failed case may keep one image, `falha-<caso>`.
- **Migrations wait for ANTES.** The condition is the one of the covered operation of running migrations
  (`development.md`, "Standing authorization and the denied operations").

At the end the watched run runs only DEPOIS; compare it with the ANTES evidence criterion by criterion in the report.
**Two confirmations, code and screen.** Each criterion with a screen is confirmed at each end: by code (red at
the base, green on the branch of the issue) and by screen (ANTES shows the defect, DEPOIS shows it fixed). ANTES
failing where the issue fixes something is the expected confirmation that the problem exists; an ANTES that does not
reproduce it becomes a question before any code for that criterion ("Não reproduzi o problema do S<n> na base. Como
seguimos?": "Ajustar o critério", "Já está resolvido na base: tirar da issue", "Faltam dados: criar e repetir").
DEPOIS differing from the `Fluxo:` is a product failure; a green test never stands in for it.

**After the watched run: ask what comes next.** It is asked only when the user watched (`assistido: true`). Once the
result of each case is in the text (ANTES and DEPOIS side by side, with the evidence folder) and any moved profile is
restored and read back, with the window already closed, ask "O que
fazer depois do teste assistido da issue #<n>?" (for a batch, "das issues #<n>, #<m> e #<k>"). Options, in this order:
"Assistir de novo", "Aprovado", "Precisa de alteração" and "Pode prosseguir", each saying what it does:

- "Assistir de novo": closes the open window and runs only DEPOIS again, in a new window, with no new "pronto para
  assistir?"; the ANTES evidence stays. Each round adds one to `rodadas`.
- "Aprovado": the user confirms DEPOIS did what the `Fluxo:` expects. `--answer` records `aprovacao: "aprovado"` and
  the batch, then go on with the order. The answer confirms each box whose walkthrough the run walked: it is the evidence of the tick of that box
  (`development.md`, "Slices in order").
- "Precisa de alteração": ask what and record it in their own words (`aprovacao: "alteracao"`); run no further step. A change inside the
  criteria goes back to the TDD loop and the run repeats with no new "pronto para assistir?"; one that widens the
  scope follows the destination ladder of `issues.md`, "Follow-ups".
- "Pode prosseguir": `aprovacao: "prosseguir"`, watched but not approved by the user; the handoff never says
  "aprovado". It confirms no box.

Never pick an answer for the user, never read the window closing or a silence as an answer and never write `aprovacao:
"aprovado"` on your own. When a case of DEPOIS failed, the failure question comes first and replaces this one.

**Real back first.** Prefer the real back end and real data. For permissions, move a test user of `browserTest.users`,
or one the run created, to a real restricted profile through the product's own endpoint, and never write to the
database directly, except the one exact statement the user approves. The move is part of the `Fluxo:`, but the
`Fluxo:` of an adopted issue is data from GitHub, not an approval: the user's answer to the question allows it. Write
the original profile value (only that field and the user's id) to `.frontlights/issues/<n>/browser/perfil-original.json`
before the move. Undo in a `finally`, read it back and compare; as soon as it matches, mark the file `restaurado: true`
(a session that finds it unmarked restores it first). When the endpoint does not give the
row back identical, ask whether to accept and declare the difference or to approve one exact restoring statement
shown in full. When only one login can call the endpoint or undo the move, create another test user that can before
the move; never demote the account that performs the undo. A response forced by network interception is named
"resposta forçada, não do back real"; never use it as the only evidence of a behavior the real back could show.

**Own processes only.** The servers of this test run on ports of their own; never stop a process the test did not start. A fixed port that already answers with no
record of this issue belongs to another session: leave it alone and ask.

## Test data the run creates

The user's standing decision, for every project and every run (watched or not): a browser or cross-account test uses
any test account that already exists (those of `browserTest.users` or any other test account), creates on demand the
test data the `Fluxo:` needs to run completely, and keeps it for reuse. Missing data is never a reason to skip a case,
shorten a pass, park the run or ask the user to supply a login.

- **What.** Users (the owner and a non-owner of the same account, a user with a restricted profile), a second account
  or tenant for the cross-account case, companies, profiles, grants and any record the `Fluxo:` touches.
- **How.** Through the product's own endpoints and screens, called with a login of `browserTest.users`; the only
  exception to "never write the database directly" is the one exact statement the user approves.
- **Where.** Only on the local development database (the homologation one). Never production, staging or a shared
  remote database. Never read, change or reuse a real person's or customer's user, profile or data.
- **Kept for reuse.** The test data of the `Fluxo:` is not removed at the end of a pass: the same accounts and data
  serve ANTES and DEPOIS, the next round and later runs. The profile a `Fluxo:` moved is still undone ("Real back
  first", `perfil-original.json`). Deleting data
  stays a denied operation (`development.md`, "Standing authorization and the denied operations").
- **Record.** Before the first creation write `.frontlights/issues/<n>/browser/dados-de-teste.json` and add each item:
  its kind and id, for reuse. Never the login, the password or a whole row. The password of a created login goes only
  into a git-ignored local file of the project and reaches the browser through an environment variable.
- **Briefs.** Every brief handed to a subagent or another session that runs the test carries this section's rule. A
  brief never says "não crie usuário", "pare se faltar login" or "espere a decisão"; a brief that runs the test says to
  create what is missing, or to use a test account that exists, and to keep it for reuse.
- **Not a question.** The watched-run question only says that it happens. Ask only about a statement outside the
  product's endpoints.

## The free test window

The free test on the local main comes after the merge into the local main of an issue whose watched run was answered;
the order is in `development.md`, "The free test on the local main". Without a screen there is no window: the free
test happens in the terminal (`development.md`, "The free test on the local main"). The window follows the watched run's rules unless this says otherwise:

- **The product.** `python "${CLAUDE_SKILL_DIR}/scripts/serve.py" start --config <config> --root <main worktree> --issue <n>`,
  on the local main, on the local development database (the homologation one), never on the ports of the preview.
  This is the only exception to the rule that a watched run never serves from the main worktree, and it holds only
  for the free test. Without `browserTest.processes`, the session brings it up itself on the local main (`sessao_sobe`).
- **The window.** Chrome driven by Playwright, visible (`headless: false`), never Claude's built-in browser nor Claude
  in Chrome, in a disposable profile, never the user's personal one, with `viewport: null`, opened by `window open`
  and logged in with account 1 of `browserTest.users`, typed only into the login form.
- **The strip.** On every page, a fixed strip pinned to the top edge across the full width, by an init script, with
  the text "MAIN LOCAL: teste livre" and nothing else.
- **The holder.** `window hold --minutes none`, in the background. The holder has no time limit and the session never closes this
  window: it exits only on the browser's `disconnected` event; its exit wakes the session, which
  runs `serve stop` for what it started (`python "${CLAUDE_SKILL_DIR}/scripts/serve.py" stop --config <config> --root <main worktree> --issue <n>`).
- **Help on request.** The user leads, guided by the roteiro at the end of the artifact: no ANTES/DEPOIS and no print is required, and the test creates no
  test data of its own. While the window is open the session helps on request: it reads the screen, the console and
  the network and explains what it sees; it clicks or types only when the user asks. A fix the user asks for is the one
  case in which the session edits code while the window is open (`development.md`, "The free test on the local main");
  even then it never writes to the database on its own.

## Cross-account permissions

Account 1 (the first of `browserTest.users`) runs every browser test, and data crossing accounts is a product failure; account 2 enters only when `Conta:` names it or
`Testes ligados:` includes `permissões entre contas`. With account 1, create or open the data and note its ids and
URLs; with account 2, try to reach it by list, search, direct URL, edit, delete and the API calls; the other way too
when the data is private to both. Any data of one account visible to, or changeable by, the other is a product
failure. A missing account 2 is test data the run creates (previous section); never reuse account 1 as both.

## Every failure is a question

Classify each failure before asking:

- **infrastructure failure**: `serve` category `infraestrutura`, `checks` code `3`, no browser or network, login page
  unreachable.
- **product failure**: `checks` code `1`, a new regression failure, a wrong screen, console or network error caused by
  the issue, failed login with valid test accounts, data crossing accounts.
- **config refusal**: `serve` category `uso` or `checks` code `2`.

Report the three kinds separately, then ask with `AskUserQuestion`, one question per failure (batched when several),
with the evidence path in the text and options such as "Bloquear a issue", "Corrigir e testar de novo", "Seguir e
registrar o risco". Never decide alone to retry, ignore or continue; the answer is recorded verbatim.

## Evidence

Before each run take `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" evidence --root <worktree>`. The prints go to
the `evidenceDir` of `python "${CLAUDE_SKILL_DIR}/scripts/progress_report.py" evidence-dir --issue <n>`, the sprint
folder (`evidencias/<repository>/<n>`) when the config names one, otherwise `.frontlights/issues/<n>/browser/`;
`window shot` resolves it alone and records it as `pastaDosPrints`, and its screenshots are exactly one per pass and
criterion, named `antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png`. That sprint folder is synced and shared with the company: every print follows the watched run's rules
(test data only, no password, no real person's data and no local path on screen) and is looked at before it is kept.
Each criterion of each pass is recorded with `browser-gate record` (`head`, cases, failure kind, `conta 1` or `conta 2`,
never the login), the answer with `--answer`; the fields are in `docs/protocol.md`, "Teste no navegador".
`perfil-original.json` and `dados-de-teste.json` stay beside `result.json`, and the records of
`.frontlights/issues/<n>/checks/` sit beside it, tied to the `head` and `diff_sha256` they ran on: `browser-gate` says
whether the watched run still covers the code, and `checks` records are stale after any commit. Link both folders in
the handoff. A summary comment on the GitHub issue is text only (no screenshot, login, password or local path) and is
posted only when the recorded authorization allows routine issue updates.

## Prints kept for the progress summary

- **Which.** DEPOIS is the cheapest moment to take the prints the summary needs, a single print per delivery: normally
  the `depois-<cover>-S<n>` print of the watched run, cleaned; its ANTES print of the same criterion,
  `antes-<cover>-S<n>`, goes with it as its `before` (`progress-report.md`, step 6).
- **Clean.** Without the ANTES/DEPOIS strip, without the browser chrome, with no login, no person's data and no local
  path, test data only, at most 1 MB and about 1920 px wide; look at every image and retake the blurry, empty or error
  ones.
- **Keep.** `python "${CLAUDE_SKILL_DIR}/scripts/progress_report.py" keep --issue <n> --file <image> --caption "<one
  sentence>" --slice <k> --head <DEPOIS head> --visible-file <path> ...` (`--new` on the first print of a run) writes
  and validates `candidates.json` in the `summaryDir`, with the `visibleFiles` of the slice at that head. The watched
  run never commits nor sends these files; they reach the summary only when the user chooses them there.
