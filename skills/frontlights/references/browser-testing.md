# Browser, checks and cross-account testing

On entering, read `docs/security.md`, "`serve`, `checks` e o teste no navegador", and `docs/protocol.md`,
"Teste no navegador".

Read this in stage 6 whenever anything the session delivers changes what the user
sees: the plan has the section `## Navegador e testes ligados` (`templates/issue.md`)
with `Toca o frontend: sim`, or `browser-gate` (below) finds a visible change in the
diff. It decides what runs, with which helper, what to ask and what to record. Everything the user reads stays in
Portuguese. `checks integration` and `checks smoke` refuse a non-local host
before any request; `serve start` does not check the `health` host, so keep
`health` and `baseUrl` on `127.0.0.1`, `localhost` or `::1`, on the branch under test
(a watched run also serves the base, see below); never point a test at a real, staging or production environment. Installing Playwright or a browser in the target project is out of
scope: use what the session and the project already have. A run never stops or skips a case
for lack of test data: it uses the test accounts that exist, creates what the `Fluxo:` needs and keeps it for
reuse (section "Test data the run creates").

## What the plan turns on

Read the four fields of that section and restate them in the handoff before
running anything:

- `Toca o frontend:` `sim` turns the browser test on; `não` skips it.
- `Conta:` `conta 1` (the default) or `contas 1 e 2`.
- `Fluxo:` the order in which the watched run walks the walkthroughs of the boxes (the `Roteiro:` lines of each
  box, with its persona, steps, before and after: `references/issues.md`), the screens and actions to exercise,
  with the expected result, and the
  effect in the back and the database after saving (what changes in the row or in the
  behavior), checked through the product's own read path or a read-only query the
  project already permits, never only what the screen shows.
- `Testes ligados:` any of `navegador`, `integração`, `regressão`,
  `permissões entre contas`, `smoke`, plus extra cases.

A missing section on an issue that changes screens, or a field that contradicts the
diff, parks the issue and goes to `AskUserQuestion` (`browser-gate` finds that
contradiction from the diff); never turn tests on or off alone. Run only what is on, in this order: `checks regression`, `serve start`,
`checks integration`, browser and cross-account steps (the DEPOIS pass: its ANTES already ran from the grilling,
"Watched run" below; the browser step opens with
the watched-run question below and, when the user watched, ends with the question of
what to do next), `checks smoke` (it reuses the running serve),
`serve stop` of the issue (never `preview stop`: the preview stays up). The commands below read `browserTest` and `checks` from the project's
`.frontlights/config.json` (main worktree included, as stage 2 says).

## One watched run per issue

There is one watched run per issue, never one per slice, branch or worktree. In this reference a
slice is a box of an issue's acceptance criteria (stage 5), each slice has its own worktree and
branch cut from the branch of the issue (`development.md`, "Slices in order"), and each `--root`
is the worktree of an issue or of one of its slices. The batch of the run is the issue with its
slices; a family that already exists (an issue with the sub-issues it already has) keeps one run
for the family, its sub-issues being roots too. A slice that only changes tests or only the API
does not hold the question back.

**When the question comes out.** The question of DEPOIS (the ANTES window has its own, in the grilling: "Watched
run", below; ANTES evidence never answers the gate) comes out only at these points, each one after `browser-gate`: (a) when the
last slice that changes the screen has closed its TDD loop and every slice already closed is merged
into the branch of the issue (the issue's worktree is a root: a merge after the record changes its
code and turns the gate `stale`, like any later code change), the normal moment, which comes before
an independent review of any of them, when the user asked for one (a review of work the user then asks to change is wasted);
(b) before an independent review of a slice that changes the screen is dispatched, once no other
slice that changes the screen is still in its loop (otherwise that review waits for (a)); (c) before an
issue that changes the screen (a visible file in its `by_root`, or a plan that says `sim`) is
reported as reviewed or complete; (d) before such an issue is merged into the local main, and before a PR is opened or updated; (e) when a session
resumes with `teste_assistido` pending (it exists only once the question is due). At any other moment a `pending` is expected and asks nothing:
a commit in a slice, or a screen slice still in its loop, is no reason to ask. A screen slice
that is parked or dropped leaves the batch, and the question names the slices it covers; one that
comes back later is a new decision (`stale`). The session does not
wait for the sibling slices, their reviews or the family integration.

**What runs.** The ANTES of the batch, on its approved base, already ran while the slices were worked ("The ANTES
window, from the grilling", below), so at this point the run is only DEPOIS, on the delivered state of
the slices that have closed their loop at that moment: the branch of the issue itself when every such
slice is already merged into it, otherwise a local integration worktree (never pushed) that merges
the issue branch and the slice branches still open, the one the family
integration of `development.md` reuses and redoes after a fix. Every `Fluxo:` of the batch runs in
that same pass, at the same place as its ANTES. A slice that closes its loop after the run and changes what a `Fluxo:`
exercises (the same screen or route) makes the session ask again by hand, with the options of `stale`, because the gate cannot see
that; until it is answered the report says "implementada, aguardando teste assistido", never "completa".

**The gate.** `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" browser-gate --config <config>
--base <base> --root <worktree> [--root <worktree> ...] [--stacked <branch>=<target> ...] --toca
<sim|nao|ausente> --record <result.json>`. `--base` is the approved base of the batch, the same for
every `--root`; each `--root` is the worktree of an issue or of one of its slices; a slice's worktree is
named with `--stacked <its branch>=<the branch of its issue>` (or the branch of the slice it is
stacked on), and each issue stacked on another branch (the base
the stacking authorization records for it, in a family that already exists) is named with
`--stacked <its branch>=<the branch it is stacked on>`, so only its own changes count (an API-only
slice or child stacked on a branch that changes the screen is then no visible root); without `--stacked`
every root is measured from `--base`; `--toca` is `sim` when any issue's plan says `Toca o
frontend: sim`, else what the plans say (`by_root` lists the visible files of each root, so compare
each issue with its own plan);
`--record` is the batch record below and may not exist yet. It reads the Git diff, not the plan's
text, and prints `status`, `reason` and `action`. Exit code 0 means `not_needed` or `answered`, 2
anything else, 1 an error such as an unreadable file or a base that does not exist (a `--config`
path that does not exist is an error: leave `--config` out only when the project has none). On exit
code 1 say the error in one line and fix the call; it is never `answered`.

- `pending` (action `ask`): nobody has decided (`sem-registro`, `pendente`, `ainda-nao` or
  `alteracao`). For `alteracao` the change comes first and the run then repeats with no new
  "pronto para assistir?"; for the others ask the question of the next section, at the points above.
- `contradiction` (`ask-plan`): the diff changes what the user sees and the plan says `não` or says
  nothing. Tell them and ask with `AskUserQuestion`; options: "Rodar o teste assistido" (and fix
  `Toca o frontend:` in the local plan with their answer; the issue body is an external write that
  needs its own approval), "Dispensar o teste" (record `dispensado`: the
  right answer when the change is not really visible) and "Ainda não".
- `stale` (`ask-again`): the user decided, then code that is not a test or a document changed in a
  slice that changes the screen (`changed_roots` names it), or the record has no `lote.roots`
  (`sem-vinculo`). Ask with options "Assistir de novo" (a new run), "Manter a decisão anterior" (copy
  the new `roots` into the record and write the answer verbatim in `pergunta.resposta`) and
  "Ainda não"; in a project with no `browserTest` only the last two make sense.
- `unconfigured` (`ask-how`): something visible changed and the project has no `browserTest`, so the
  run cannot happen. Ask with options "Verificar à mão e dispensar" (record `dispensado` and the risk
  in the report), "Configurar o `browserTest` agora" and "Ainda não". Never call the change checked.

The visible paths are `browserTest.frontPaths` of the project's config (globs from the repository
root: `*` stays inside one folder, so say `**/*.html` for every page; tests and documents never count
and a screen file never counts as a test); without it the gate guesses from file names, and `inspect`
warns about that. Limits: a script or an image inside a test or documentation folder stays out even
when `frontPaths` names it, markdown pages never count, and an HTML fixture inside a test folder is
asked about (answer `dispensado`).

**The record.** The issue has one `result.json`, in its own folder, `.frontlights/issues/<n>/browser/result.json`,
whatever the number of its slices; a family that already exists keeps the one record of the family in the
folder of its lead issue (the parent): `.frontlights/issues/<lead>/browser/result.json`.
Besides the fields of the Evidence section it carries `situacao` (`pendente`, `ainda-nao`,
`aprovado`, `prosseguir`, `sem-assistir`, `dispensado` or `alteracao`), `lote` with `issues` (the
numbers) and `roots` (copied from the `browser-gate` output taken when the answer was recorded,
which is what `stale` compares with) and `pergunta.resposta`, the user's answer verbatim. "Ainda não"
is `ainda-nao`: the run stays owed, as the `teste_assistido` pending of `checkpoint --pending` and
`context --pending` (so `resume` reports it and a window near its limit asks before spending more),
and the question comes back at the points above, not at every commit. It is carried that way only
once the question is due: the last slice that changes the screen has closed its loop and the user has
not answered, or said "Ainda não" (a slice that reopens its loop after that does not undo it: the handoff
carries both, and the question comes out again when that slice closes). A slice of the batch that has not
started yet counts as open. While a screen slice is still in its loop the handoff lists the open screen
slices instead, a window near its limit just renews, and the next window continues that
slice. "Rodar sem assistir" is
`sem-assistir` once it ran; the user's explicit decision not to run it is `dispensado`; the closing
question gives `aprovado`, `prosseguir` and `alteracao`. `answered` (any of `aprovado`, `prosseguir`,
`sem-assistir` or `dispensado`) is what an independent review of a slice that changes the screen,
"reviewed", "complete", the merge into the local main and a PR require; there is no other way around it.

A Direct change with no issue has no plan and no lead issue. Ask with `AskUserQuestion`, options "Informar a
issue" (the issue the work belongs to, which the user names: its number serves the record, `serve` and
`checks`), "Dispensar o teste" (record `dispensado`) and "Ainda não". Never run `serve` or `checks` with an
invented number, and open no issue for it. `--toca` is `ausente`, so a visible diff is a `contradiction`
(in a project with no `browserTest` it is `unconfigured`), which this same question answers. A dispensed
Direct change keeps its record in `.frontlights/direct/<branch, slashes as dashes>/browser/result.json`
(`--record` points there; the answer verbatim and the risk go in the handoff and the report too).

## Environment: `serve`

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" start --config <config> --root <worktree> --issue <n>
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" status --config <config> --root <worktree> --issue <n>
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" stop --config <config> --root <worktree> --issue <n>
```

`serve start` brings up every process of `browserTest.processes` in the issue's
worktree, waits for each health URL and records pids in
`.frontlights/serve/<n>.json`; `serve stop` kills the process trees and releases
the ports. Exit `0` done, `1` refused or failed; the JSON `category` says:

- `uso`: invalid config or a busy lock;
- `infraestrutura`: everything else, an unreadable or missing config included.

Either way, ask (see below).

A project whose `browserTest` declares only the accounts (`inspect` warns about it) starts its own
environment: skip `serve start` and `serve stop`, confirm with the user that the environment is up and on the branch under test, and never start or stop a process this session did not start.

Ports. A process with `"port": "auto"` gets a free port reserved per process in the
repository's Git common directory, shared by every worktree, and receives it in
`PORT`, `FRONTLIGHTS_PORT_<NAME>` and `{port}` in its argv. Its health must carry
`{port}` in place of the host's port (`http://127.0.0.1:{port}/health`); `{port}`
only in the path is refused as `uso`. The output reports
`reservas_compartilhadas`. Use `auto` only when the process really accepts the
port by variable or argument. A dev server that pins its own ports keeps a fixed
`port`, and then only one issue at a time can run it: say so when recommending
parallelism. A process that ignores the reserved port fails the start as
infrastructure, naming the process.

Stop what this session started before reporting the issue, and say in one line
which processes are still up when the user chose to keep them.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" preview start --config <config> --root <main worktree>
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" preview refresh --config <config> --root <main worktree> [--base main] [--branch <issue branch> ...]
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" preview status --config <config> --root <main worktree>
python "${CLAUDE_SKILL_DIR}/scripts/serve.py" preview stop --config <config> --root <main worktree>
```

The preview is the long-running mode, one per project, declared in the `preview`
block of the config (`worktree`, `branch`, `baseUrl`, `processes`). `serve preview`
runs its processes in the preview worktree; each one's output goes through
`serve relay` (spawned by `preview start`, never by hand) into a log saved and
masked in `.frontlights/preview/log/`, its branch named in
`.frontlights/preview/branch.json` (kept by `preview stop`), and its record in
`.frontlights/preview/registry.json` survives the `serve stop` of an issue and a
change of session (`preview status` finds the processes through it and returns the
tail of each log). `preview start` is refused while the preview is alive: run
`preview refresh` instead. Run `preview stop` only when the user asks.

The preview uses fixed ports, so its tab stays valid across every refresh: it is
opened once and only reloaded. No process of the `preview` block takes
`"port": "auto"`, there is no `{port}` in the `argv` or the `cwd` of its processes
(a fixed port is written as is), its `baseUrl` takes no `{port}`, and the port of that
`baseUrl` (explicit, or 80/443 by the scheme) is the fixed port of one of its
processes (integer `port`, or else the port of the health); anything else is
refused as `uso`, by `serve preview` and by `inspect`. With the `preview` block
present, `inspect` also refuses a fixed port of `browserTest.processes` or of
`browserTest.baseUrl` that is a port of the preview: the watched run never runs on
the ports of the preview.

`preview refresh` redoes the preview branch from the local main (`git checkout -B`
inside the preview worktree, or `git worktree add` when it is missing; never the
local main nor the branches of the issues, which do not move), merges the branches
of the issues in progress given in `--branch`, in order, brings the processes up
again and checks health and log. The preview branch is never pushed and nothing is
edited in the preview worktree: one with tracked changes is refused as `uso`, like
a branch that does not exist locally. A conflict is undone (`conflict: true`, the
branch and the files) and nothing comes up: ask the user. A broken build (a
process that exits before its health, or a health that never answers) is torn down
and refused with `build: "quebrado"`, the process, the `log` and its last lines
(`tail`); say it in one line with the log file and the error, then ask.

## Checks: `checks`

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/checks.py" regression --config <config> --root <worktree> `
  --base <base-checkout> --issue <n>
python "${CLAUDE_SKILL_DIR}/scripts/checks.py" integration --config <config> --root <worktree> `
  --issue <n> --base <base-checkout>
python "${CLAUDE_SKILL_DIR}/scripts/checks.py" smoke --config <config> --root <worktree> `
  --issue <n> --base <base-checkout>
```

- `checks regression` runs the suite on the base and then on the branch; only a
  new failure blocks, a failure already on the base is reported apart.
- `checks integration` runs `checks.integration.argv` against the backend that
  `serve start` brought up; it never starts anything itself.
- `checks smoke` starts the serve when none is up, requests the declared paths and
  stops only what it started; a warning "Rode `serve stop`" means an orphan was
  left: tell the user and offer to run `serve stop`.

Exit codes: `0` passed, `1` product failure, `2` config or usage refused (nothing
ran), `3` infrastructure. Records go to `.frontlights/issues/<n>/checks/`; those
of `integration` and `smoke` carry `simulacao: false`. A login or password of `browserTest.users` shorter than four
characters makes `integration` and `smoke` refuse; both values are masked in every
output and record.

## Browser

Explore with Chrome driven by Playwright (a visible window, maximized, in a disposable
profile), never Claude's built-in browser nor Claude in Chrome, which only opens the
user's preview tab; run the project's own Playwright specs when it already has them. Open the
`browserTest.baseUrl` of the branch, log in with account 1 and walk the `Fluxo:`
step by step, comparing each screen with the expected result. Collect console
errors, failed network requests and a screenshot per step. Type credentials only
into the login form; never repeat them in the conversation, a record or a
screenshot caption.

Without a browser or network the test did not run: report the reason, record it,
and the issue never counts as passed on that test.

## Watched run: before and after, with the user watching

Whenever the plan turns the browser test on (`Toca o frontend: sim`) or `browser-gate`
finds a visible change, the watched run has two passes of the same scenario: ANTES on the base, whose window
opens in the grilling and stays open while the slices are worked ("The ANTES window, from the grilling", below),
and, at the end, DEPOIS on the delivered state (the section above). Before each of the two windows opens (the
first ANTES window, at the problem round of the grilling, and the DEPOIS window, at the points of the section
above; the servers may already be up), ask with `AskUserQuestion`: "Pronto para
assistir ao teste de navegador da issue #<n>?" (for a family that already exists, "das issues #<n>, #<m> e #<k>",
each one named in the text). The text says what comes: for ANTES, the screens of the base for the artifact and,
once the plan is approved, the `Fluxo:` of each criterion on the base, one print per criterion, the window
staying open until the last ANTES print; for DEPOIS, the delivered state, each case twice, one print per
criterion, and the window stays open for about 5 minutes at the end; that the run uses the test accounts that
exist and creates the test data the `Fluxo:` needs (users, accounts and
the like), which stays on the local development database for reuse; and, when the `Fluxo:` moves a test user to a restricted
profile, that this changes data of the test database through the product's endpoint
and that it will be undone. Options: "Sim, pode rodar" first and recommended;
"Ainda não" (park the browser test and go on with other work, run nothing; the user
says when ready; in the grilling, the problem round waits for the before print, `references/grilling.md`);
"Rodar sem assistir" (a hidden window is acceptable; record
`assistido: false`). When the `Fluxo:` moves a profile, a fourth option, "Sem mudar
perfil", runs the pass without the move and declares in the report that the
permission behavior was not checked against the real back. Never open the browser
before the answer. A reopened ANTES window asks nothing (below). Passes never overlap while one is running: one issue at a time (a batch counts as one),
never several passes at once on the same account and database; an ANTES window that is open but idle holds no other issue back.

When the user will watch:

- **Visible window.** Chrome driven by Playwright with a visible window, never headless
  (`headless: false`), never Claude's built-in browser nor Claude in Chrome, in a disposable browser
  context or profile, never the user's personal one. If the session cannot open
  one, the watched run did not happen: report the reason and ask; never fall back to
  a hidden window silently. The tab of the preview is the user's and stays outside
  this rule: the watched run never drives it and runs never on the ports of the preview.
- **The whole screen, always.** The user must see the whole page and the strip without
  scrolling or resizing anything. Size the window to the screen's available area (start
  maximized, or read the screen size and open the window at it) and let the page
  viewport follow the window (`viewport: null` in Playwright), never a fixed viewport
  larger than the screen: a page that overflows the window hides its edges and the
  strip. Before the first case of each pass, take a screenshot and check that the strip and
  every edge of the page are inside it; when something is cut off, resize and check
  again, and never go on with a cut-off window.
- **Two passes, same scenario and same account.** ANTES runs the `Fluxo:` on the
  remote base of the batch (`origin/<base>`, the base the branch of the issue was created from),
  never on the local main (`development.md`, "Slices in order"); an issue stacked on a
  parent that is not part of the batch uses that parent's branch.
  Serve it from a checkout of that
  base, a detached-HEAD worktree made with `git worktree add` at `origin/<base>`; for that stacked issue the
  parent's own worktree can serve as ANTES. It gets its own record (`serve start --root <base-checkout>
  --issue <n>`). Before the issue exists (a grilling that starts from a request), the base checkout is named after the discovery log
  and serves on a provisional record, `serve start --root <base-checkout> --issue 0`, unique to that checkout; once the issue is published, its prints move to the evidence folder of the issue and the record stays until the window closes. DEPOIS runs the same `Fluxo:`, same account, same data, on the
  delivered state (the branch of the issue, or the local integration of it with the slices that
  closed their loop and are not merged yet), served from its worktree, at the end; both passes run on the local
  development database. The base server takes an `auto` port of its own, so it stays up beside the servers
  of the slices and of the issue. In a project whose processes have only fixed ports, the servers of the slices and of the issue wait for the ANTES window to close, and `serve stop --root <base-checkout> --issue <n>` ends ANTES before DEPOIS
  starts. A watched run never serves from the main worktree (the
  free test is the only exception, "The free test window"). After each `serve start`
  confirm that the process answering on the port is the recorded one or a descendant
  of it (`serve status` and the owning pid of `Get-NetTCPConnection -LocalPort
  <port>`), or DEPOIS could be answered by the base. Stop the ANTES record once no ANTES capture is due, and in
  every case before reporting.
- **The ANTES window, from the grilling.** In an issue with a screen, the ANTES window (the visible window above,
  with the strip "ANTES: <base>", a test account and the base served from its detached checkout) opens at the problem
  round of the grilling (`references/grilling.md`), after the question above, and stays open: first it takes the
  prints of the screens for the before of the artifact (that rule is the grilling's); then, once the plan is approved
  with the `Fluxo:` of each criterion written (stage 5), the same window runs the `Fluxo:` of each criterion on the
  base and keeps the ANTES evidence of each one, while the slices go on in parallel (`development.md`, "Slices in
  order"). It closes when the last ANTES evidence is taken or when the user closes it; the session closes it itself
  after the last one. Its holder has no time limit, like the free test's: the 5 minutes of "Pace" apply only to
  DEPOIS. A window closed before the last ANTES evidence (by the user, a crash or the end of a session) reopens on the
  base, with no question, when the next capture is due; `result.json` says which criteria still lack their ANTES.
  Each ANTES evidence records the `head` of the base it ran on. When the base receives, before DEPOIS, another
  change in the screen files of a criterion (after `git fetch`, a file of its slice's `by_root` in `browser-gate`
  that differs between that `head` and `origin/<base>`), the ANTES of that criterion runs again at the end, on the
  new base, before DEPOIS, in a reopened window.
- **The isolated instance.** When the project declares `browserTest.isolated` (which
  `inspect` validates), the watched run runs on processes and ports of its own and never touches
  the preview. The database is the local development database itself, which is the homologation database, never a copy:
  the block has no database step, and `inspect` refuses one that still declares a copy or a drop
  of the database (`docs/security.md`). ANTES and DEPOIS never run at once in that instance:
  bring up the processes of `browserTest.isolated.processes` from the checkout of the
  base, check each health and keep them up while the ANTES window is open, stop them when it closes, then, at
  the end, bring them up from the delivered
  state for DEPOIS, and open `browserTest.isolated.baseUrl` in the disposable window
  each time; never on the ports of the preview. The session (or the driver of the run)
  starts those processes itself, from their argv, without a shell, and stops only what it started. A
  process with `"port": "auto"` gets a free port the session picks before starting it,
  passed in `PORT` and in place of `{port}` in its argv, its health and the `baseUrl`,
  as `serve` does for its own; a fixed `port` is used as declared. The data the `Fluxo:`
  needs is created on that database and kept, as section "Test data the run creates" says.
  Without the block, the passes run on the issue's own serve as above.
- **A strip on every page.** The test injects a fixed strip into the page, pinned to the
  top edge across the full width, thin, above every other element and never
  covered by a popup, toast or dialog (an init script or a DOM node, visible in the screenshots): "ANTES: <base>" ("ANTES: origin/main"
  on the remote main, the base's own name otherwise) in the first pass and
  "DEPOIS: branch <name>" in the second, with the branch name as Git has it. No
  login, password or local path ever goes into the strip.
- **Pace.** Each case runs twice in each pass. Hold every popup, toast and dialog
  on screen long enough to be read (a few seconds), not the instant the assertion
  passes. After the last step of DEPOIS leave the window open for
  about 5 minutes, held by a background process so that the wait never blocks the agent; the ANTES window is
  held the same way, with no time limit ("The ANTES window, from the grilling").
  The holder is started in the background (the shell tool's run_in_background option) by whoever drives the pass, and it
  exits when the user closes the window (the browser's `disconnected` event) or when the 5
  minutes end, whichever comes first; at the 5 minutes it closes the window itself before
  exiting, and it prints which of the two ended it. Its exit is the
  notice: the harness wakes the one who started it, so nobody polls and nobody waits for
  a report that never comes. A bare timer or `sleep` is not a holder, because nothing
  wakes the driver when the user closes the window early. The holder of the free test has no time limit ("The
  free test window", below).
- **Window closed, next step.** The notice is the same whether the user closed the window
  or the 5 minutes ended it: the session goes on without waiting for anyone. When the ANTES holder exits, stop the ANTES
  server once no ANTES capture is still due (otherwise the window reopens when the next one is), and only after that
  start DEPOIS; never start DEPOIS before that notice. When the DEPOIS holder
  exits, the pass is over and the driver reports at once. When a subagent drives the
  passes, it does not return its report before the DEPOIS holder exits, so that the
  session waiting for the report is woken by the window closing. The closing question
  below is asked while the DEPOIS window is still open, as soon as the results are in the
  text and any restricted profile is already restored, when the session itself drives the
  passes; with a subagent it is asked once the report arrives, with the window already
  closed. Closing the window or the 5 minutes ending is never an answer to that question.
- **One print per criterion.** Each pass keeps exactly one print per criterion (the box `S<n>` whose `Fluxo:`
  it walks), never one per step or per repetition: the single screen that shows best what that criterion changes,
  taken at the same place in ANTES and DEPOIS so the two can be compared. The files are
  `antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png` (`<cover>` the top-level issue, `S<n>` the criterion),
  with a hyphen because `#` breaks a URL and the check of the push; where it is text (a caption, the report, a
  label) it is `antes#<cover>-S<n>` and `depois#<cover>-S<n>`. Console errors and failed requests go to the text,
  and the result of each step stays in text, only in `result.json`, never in an image. The check that the strip and
  every edge of the page are inside the
  window is only a look: do not keep that image. A case that fails may keep its one failure image, named
  `falha-<caso>`, beside them; a passing case never does.
- **Migrations wait for ANTES.** No slice applies a migration to the local development database while ANTES is
  still owed: the condition and what the report says when it is broken are those of the covered operation of
  running migrations (`development.md`, "Standing authorization and the denied operations").

At the end the watched run runs only DEPOIS; compare it with the ANTES evidence case by case, criterion by
criterion, in the report. ANTES failing where the issue
fixes something is expected; DEPOIS differing from the `Fluxo:` is a product
failure.

**After the watched run: ask what comes next.** Asked only when the user watched
(`assistido: true`); a run with "Rodar sem assistir" has no one to answer it. Once the
last step of DEPOIS has run and the result of each case is in the text (ANTES and DEPOIS side
by side, with the evidence folder), with the window still open for its 5 minutes (or already closed,
when a subagent drove the passes) and the
original profile already restored and read back, ask with `AskUserQuestion`: "O que fazer depois do
teste assistido da issue #<n>?" (for a batch, "das issues #<n>, #<m> e #<k>", as in the first question)
Options, in this order: "Assistir de novo", "Aprovado",
"Precisa de alteração" and "Pode prosseguir", each saying what it does:

- "Assistir de novo": closes the open window and runs only DEPOIS again as above, in a new window, with no new
  "pronto para assistir?" (the batch already answered it); the ANTES evidence stays. When
  the `Fluxo:` moves a profile, save the original value again, move and undo it again (the
  previous round's undo was already read back). Ask this question again at the end;
  each round adds one to `rodadas`.
- "Aprovado": close the window. The user confirms that DEPOIS did what the `Fluxo:` expects. Record
  `aprovacao: "aprovado"`, `situacao: "aprovado"`, the `lote` of the gate output and the answer
  verbatim, then go on with the order
  (`checks smoke`, `serve stop`, and the review when the user asked for one). The answer confirms each box whose
  walkthrough the run walked: it is the evidence of the tick of that box, which is ticked now by the tick cycle of
  `development.md`, "Slices in order".
- "Precisa de alteração": the user wants something changed. Ask what with
  `AskUserQuestion` and record it in their own words, record `aprovacao: "alteracao"` (and `situacao: "alteracao"`) and
  run no further step of the order; close the window and stop what this test started, with the profile already
  restored. A change inside the issue's acceptance criteria goes back to the TDD loop on
  the same branch and the watched run is repeated with no new "pronto para assistir?"; a
  change that widens the scope follows the destination ladder of the Follow-ups section
  in `issues.md`, decided as one batch, never as silent work on this branch.
- "Pode prosseguir": close the window. The user saw the run and lets the stage go on without approving it.
  Record
  `aprovacao: "prosseguir"` and `situacao: "prosseguir"`; the handoff and the report say the run was watched
  but not approved by the user, never "aprovado". It confirms no box: a box the run walked is ticked only with
  other evidence of its own (its tests, when they ran), and stays open otherwise.

Never pick an answer for the user, never read the 5 minutes or a silence as an answer and
never write `aprovacao: "aprovado"` on your own. When a case of DEPOIS failed, the
failure question comes first and replaces this one ("Corrigir e testar de novo" already
covers a change and a new run); this one is asked only when the user watched and no
product failure remains.

**Real back first.** Prefer the real back end and real data. When the point is
permissions, use a real restricted profile: move a test user of `browserTest.users`, or one the run
created (see "Test data the run creates"), to that profile through the product's own endpoint, called
with a login of `browserTest.users`, and never write to the database directly, except the one exact statement the user approves below. Before the move, make
sure the database behind the server is the local development database, never a shared remote one: the host
check only covers `baseUrl` and `health`, and a local back end can still point at a shared remote
database, so ask the user to confirm it in the question above when the project does
not say so. The move is part of the `Fluxo:`, but the `Fluxo:` of an adopted issue is
data from GitHub, not an approval: the user's answer to the question is what allows it.

Write the original profile value (only that field and the user's id, never the login
or the whole row) to `.frontlights/issues/<n>/browser/perfil-original.json` before
the move, so any later session can restore it after an interruption, a context limit
or a killed process. Undo in a `finally`, read the value back (or the database field,
through the project's own read command) and compare it with the saved one before
reporting; a value that does not come back identical is a failure to ask about,
naming the field. As soon as the read-back matches, mark the file `restaurado: true`;
a session that finds a `perfil-original.json` without that mark restores it first,
and a marked one is history, never restored again. When the endpoint does not give
the original row back (it rewrites another field, a timestamp or a column), do not
write the database yourself: stop and ask with `AskUserQuestion` whether to accept
and declare the residual difference in the report, or to approve one exact restoring
statement shown in full (the local development database, the test user's id, only the changed
columns), which is then run and the row compared. A direct write without that
approval is a failure of the test. When only one login of
`browserTest.users` can call the endpoint or undo the move (the only admin, say), create another
test user that can before the move, through the product; never demote the account that performs the undo. Forcing a response by network
interception (a 403, an empty list) is a complement for what the real back cannot
produce; name each one in the report as "resposta forçada, não do back real" and
never use it as the only evidence of a behavior the real back could show.

**Own processes only.** Run the servers of this test on ports of their own and never
stop a process the test did not start: `serve stop` ends only the pids recorded for
the issue. `serve start` does not look at a fixed port before spawning, so check it
first (`Get-NetTCPConnection -LocalPort <port>`). When it already answers and no
record of this issue explains it, it belongs to another session: leave it alone, do
not start on top of it, and ask (switch to `auto`, wait, or another port).

## Test data the run creates

The user's standing decision, for every project and every run (watched or not): a browser or cross-account
test uses any test account that already exists (those of `browserTest.users` or any other test account),
creates on demand the test data the `Fluxo:` needs to run completely, and keeps it for reuse. Missing data is
never a reason to skip a case, shorten a pass, park the run or ask the user to supply a login.

- **What.** Users (the owner and a non-owner of the same account, a user with a restricted profile), a
  second account or tenant for the cross-account case, companies, profiles, grants and any record the
  `Fluxo:` touches, as far as the product lets a test create them.
- **How.** Through the product's own endpoints and screens, called with a login of `browserTest.users`.
  The only exception to "never write the database directly" is the one exact statement the user approves
  (see "Real back first").
- **Where.** Only on the local development database (the homologation one) that "Real back first" already requires. Never
  production, staging or a shared remote database. Never read, change or reuse a real person's or customer's
  user, profile or data: the run touches only test accounts and test data (what a run created, the logins of
  `browserTest.users` or another test account).
- **Kept for reuse.** On the local development database (the homologation one), the test data of the `Fluxo:`
  is not removed at the end of a pass: the same accounts and data serve ANTES and DEPOIS, the next round and
  later runs, and the accounts a session creates stay for reuse. The profile a `Fluxo:` moved is still undone
  ("Real back first", `perfil-original.json`). Deleting data stays a denied operation (`development.md`,
  "Standing authorization and the denied operations").
- **Record.** Before the first creation write `.frontlights/issues/<n>/browser/dados-de-teste.json` (the
  issue's folder; the lead issue's for a family that already exists) and add each item as it is created: its
  kind and id, for reuse. Never the
  login, the password or a whole row. The password of a created login goes only into a git-ignored local
  file of the project and reaches the browser through an environment variable of the process; never into
  a record, a caption, the strip, a screenshot, the conversation or a brief.
- **Briefs.** Every brief handed to a subagent or another session that runs the test carries this
  section's rule. A brief never says "não crie usuário", "pare se faltar login" or "espere a decisão";
  a brief that runs the test says to create what is missing, or to use a test account that exists, and to keep it
  for reuse.
- **Not a question.** This is not asked per run; the watched-run question only says that it happens.
  Ask only about what this section does not settle: a statement outside the product's endpoints.

## The free test window

The free test on the local main comes after the merge into the local main and the bundle of an issue whose watched
run was answered; the order is in `development.md`, "The free test on the local main". Without a screen there is no window: the free
test happens in the terminal (`development.md`, "The free test on the local main"). This section is only the window,
which follows the watched run's rules unless it says otherwise:

- **The product.** Start it with `python "${CLAUDE_SKILL_DIR}/scripts/serve.py" start --config <config> --root <main
  worktree> --issue <n>` (`<n>` the homologated issue; the issue's own serve is already stopped by the order of the
  watched run), so the processes of `browserTest.processes` run from the main worktree, on the local main, on the
  local development database (the homologation one), never on the ports of the preview. This is the only exception
  to the rule that a watched run never serves from the main worktree, and it holds only for the free test. A project
  that starts its own environment (no `browserTest.processes`) is asked to bring it up on the local main, as in
  "Environment: `serve`".
- **The window.** Chrome driven by Playwright, visible (`headless: false`), never Claude's built-in browser nor
  Claude in Chrome, in a disposable profile, never the user's personal one, sized to the screen with `viewport:
  null`, as in "The whole screen, always". It opens on `browserTest.baseUrl` already logged in with account 1 of
  `browserTest.users`, typed only into the login form and never repeated in the conversation or a record.
- **The strip.** On every page, a fixed strip pinned to the top edge across the full width, by an init script,
  above every other element, with the text "MAIN LOCAL: teste livre" and nothing else (no login, password or local
  path).
- **The holder.** Started in the background by whoever opens the window, as in "Pace". The holder has no time limit:
  the 5 minutes of the watched run do not apply, and it exits only on the browser's `disconnected` event, when the
  user closes the window, and its exit wakes the session, which runs `serve stop` for what it started (`python
  "${CLAUDE_SKILL_DIR}/scripts/serve.py" stop --config <config> --root <main worktree> --issue <n>`) and goes on with the order of `development.md`.
- **Help on request.** The user leads: no script, no ANTES/DEPOIS and no print is required, and the test creates no
  test data of its own. While the window is open the session helps on request: it reads the screen, the console and
  the network and explains what it sees; it clicks or types only when the user asks, and it never writes to the
  database on its own. A fix the user asks for is the one case in which the session edits code while the window is
  open, on the branch of the issue and merged again into the local main (`development.md`, "The free test on the
  local main"); even then it never writes to the database on its own.

## Cross-account permissions

Account 1 is the first entry of `browserTest.users`, account 2 the second.
Account 1 runs every browser test. Account 2 enters only when `Conta:` names it or
`Testes ligados:` includes `permissões entre contas`. Then:

1. With account 1, create or open the data the issue touches and note its
   identifiers and URLs.
2. Log out, log in with account 2 and try to reach that data: lists, search,
   direct URL, edit and delete actions, and the API calls the screens make.
3. Repeat the other way when the plan says the data is private to both.

Any data of one account visible to, or changeable by, the other is a
product failure. A missing account 2, or an account 2 that is the same account or tenant as account 1 when the
case is cross-tenant, is test data the run creates (previous section): use another test account that exists or
create it, never reuse account 1 as both.

## Every failure is a question

Classify each failure before asking:

- **infrastructure failure**: `serve` category `infraestrutura`, `checks` code
  `3`, no browser or network, login page unreachable.
- **product failure**: `checks` code `1`, a new regression failure, a wrong
  screen, console or network error caused by the issue, failed login with valid
  test accounts, data crossing accounts.
- **config refusal**: `serve` category `uso` or `checks` code `2`.

Report the three kinds separately, then ask with `AskUserQuestion`, one question
per failure (batched when several), with the evidence path in the text and options
such as "Bloquear a issue", "Corrigir e testar de novo", "Seguir e registrar o
risco". Never decide alone to retry, ignore or continue; an issue with a failure
is reported as passed only when every test passed or the user chose to go on, and
the answer is recorded verbatim.

## Evidence

Before each browser run, take `python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" evidence --root <worktree>`
and `python "${CLAUDE_SKILL_DIR}/scripts/progress_report.py" evidence-dir --root <worktree> --issue <n>` (`<n>` as
below). The second prints `evidenceDir`, the folder of the run's prints, and `summaryDir`, the folder of the prints
kept for the summary. When the `roadmapSync` block of the project's config names `scrumRoot` and `weekFolderPattern`, the folder is
the one of the sprint the run happens in (the Monday of that week, Sao Paulo time) under scrumRoot, in
`evidencias/<repository>/<n>` (the name after the slash of `repository`), so the prints outlive the cleanup of the
worktrees and stay at hand for the summary; without them it is `.frontlights/issues/<n>/browser/` as before. That
sprint folder is synced and shared with the company: every print saved there follows the rules of the watched run
(test data only, never production, no password, no real person's data and no local path on screen) and is looked at
before it is kept. A run that crosses midnight into another week keeps the folder it started with.
Write `.frontlights/issues/<n>/browser/result.json` (for a family that already exists, `<n>` is its lead
issue and the file is the family's) with `pastaDosPrints` (the `evidenceDir` of the run), timestamp, branch,
`head`, `diff_sha256`, the account used (`conta 1` or `conta 2`, never the login),
each step and its result, console and network errors, screenshot file names, the
failure kind and the user's answer. A watched run adds `assistido` (true or
false), `rodadas` (how many times the user watched DEPOIS), `aprovacao` (`aprovado`,
`prosseguir` or `alteracao`) with the answer to the closing question verbatim, one entry
per pass (`ANTES`/`DEPOIS`, with the branch and `head` served and `repeticoes: 2`; ANTES with the `head` of the
base each criterion ran on and the criteria that still lack their ANTES), the
source of each response (`back real` or `interceptada`) and,
when a profile was moved, only the profile field before and after the undo (never
the whole row, which can hold a login or a password hash); its screenshots are
exactly one per pass and criterion, named `antes-<cover>-S<n>.png` and `depois-<cover>-S<n>.png` ("One print per
criterion", above), plus `falha-<caso>` for a failed
case. Screenshots go to `evidenceDir`, named by file name in `result.json`; `perfil-original.json` and
`dados-de-teste.json` stay beside `result.json`. The
records of `.frontlights/issues/<n>/checks/` sit beside it. The records are
tied to the `head` they ran on: for the watched run `browser-gate` says whether the record still covers the
code (`stale` asks again), and the `checks` records are stale after any later commit, so rerun them before
reporting. Link both folders in the
handoff.

A summary comment on the GitHub issue is text only (no screenshots, no login,
no password, no local path) and is posted only when the recorded authorization
allows routine issue updates; otherwise keep it in the handoff as pending.

## Prints kept for the progress summary

The DEPOIS pass of a watched run is also the cheapest moment to take the prints the "Resumo para a
diretoria" will need (`progress-report.md` step 6 offers them). The summary shows a single print per
delivery, so this costs at most one extra capture per delivery.

- **Which.** A single print per delivery (the top-level issue of the family), taken in DEPOIS: the one
  screen, message or list a person would recognise as what changed, taken right after the case passes. It is
  normally the `depois-<cover>-S<n>` print of the watched run, cleaned as below; take a second one only when
  that print cannot be cleaned. When the delivery has one, its ANTES print of the same criterion, `antes-<cover>-S<n>`, goes with it as its `before`
  (`progress-report.md`, step 6), cleaned the same way.
- **Clean.** Without the ANTES/DEPOIS strip, without the browser chrome, with no login, no person's name or
  data and no local path: crop, or choose another view of the same result, or take no print for that case. Test
  data only. JPEG or PNG, at most 1 MB and about 1920 px wide. Look at every image yourself and retake the
  blurry, empty or error ones.
- **Where.** The `summaryDir` that `evidence-dir` printed for the run (section "Evidence"): `resumo/` of the issue's
  folder (the lead issue's for a family) in the sprint folder, or, in a project without a sprint folder,
  `.frontlights/issues/<n>/browser/resumo/` of the project's **main worktree** (the first one `git worktree list`
  shows), never of a linked one: the cleanup of the delivered worktrees removes them (their `.frontlights` records survive
  only as a copy under `.frontlights/issues/<n>/worktrees/`), and the summary comes days later. A `candidates.json` lists each print:
  `[{"file": "<image in this folder>", "caption": "<one plain sentence in Portuguese>", "issue": <slice>,
  "cover": <delivery>, "repository": "<OWNER/REPOSITORY>", "takenAt": "<ISO 8601 instant with its offset>", "head": "<DEPOIS head>",
  "visibleFiles": {"<visible file>": "<git blob id>"}}]`.
  `issue` is the slice the print shows; `cover` is the top-level issue of its family (the issue itself when it
  has no parent), the one the summary lists as the delivery; `visibleFiles` maps each visible file of the
  slice (the `by_root` of `browser-gate`) to its Git blob id as served in DEPOIS, so the summary can tell
  whether the code the print shows is still the code that was delivered. Write `candidates.json` from
  scratch on each run of the watched test and keep only what DEPOIS just produced.
- **Never sent from here.** The watched run never commits nor sends these files. In the sprint folder they are
  already in the company's synced, shared folder, so they are cleaned before they are saved, as above; they go
  to the folder of the summary only when the user chooses them in the summary step.
