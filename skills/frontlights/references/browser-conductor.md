# Conducting a pass of the watched run

You conduct the {{PASS_NAME}} pass of the watched run of issue {{ISSUE}}. `serve.py window brief` filled this
page; follow it as written and read nothing else unless a step fails. **Portuguese.** Everything the user reads
(the strip, the captions, the records' text, your report) is in Portuguese, even though this page is in English.

You drive the window and record what happened. You never decide whether the pass passed: passed or failed is the
session's and the user's, looking at the screen together. Report facts, never a verdict.

## The window

- Pass: {{PASS}}. Strip: "{{STRIP}}". Base URL: {{BASE_URL}}. Account: {{ACCOUNT}}.
- Criteria of this pass, in the order of the `Fluxo:`: {{CRITERIA}}.
- Prints go to {{EVIDENCE_DIR}}; the record is {{RECORD}}.
- Window now: {{WINDOW}}.

Chrome driven by Playwright, visible, disposable profile, never Claude's built-in browser nor Claude in Chrome.
The window comes from the script, never from memory:

1. Open it, or reuse the one that is open (attach reopens a dead window on the same base, with no question):
   `python "{{SCRIPTS}}/serve.py" window attach --issue {{ISSUE}}` and, when it says no window is recorded,
   `python "{{SCRIPTS}}/serve.py" window open --issue {{ISSUE}} --strip "{{STRIP}}" --base-url {{BASE_URL}} --account {{ACCOUNT_NUMBER}}`.
2. Start the holder at once, in the background (the shell tool's run_in_background option), so the strip follows
   every new page and its exit wakes you: `python "{{SCRIPTS}}/serve.py" window hold --issue {{ISSUE}} --minutes {{HOLD}}`.
   A bare timer or `sleep` is not a holder.
3. Look at `checkShot` (never keep it). With `fits: false`, or the strip or an edge of the page cut off, resize and
   look again; never go on with a cut-off window. With `ambiente: ambiente_do_usuario`, stop and tell the session:
   the user starts the environment and confirms it is up on the branch under test.
4. Drive the page with the Playwright the script found ({{PLAYWRIGHT}}): `chromium.connectOverCDP("<cdpUrl>")`, then
   `browser.contexts()[0].pages()`. Without Playwright (`driver: cdp`), drive it over the CDP port yourself, put the
   strip on every page and log in through the form.

Credentials go only into the login form, through environment variables; never into the conversation, a record,
a caption, the strip or a print.

## Each criterion

For each criterion, in order:

1. Walk its `Fluxo:` step by step on {{BASE_URL}}, comparing each screen with the expected result, and check the
   effect in the back and the database through the product's own read path, never only what the screen shows.
2. Run each case twice. Hold every popup, toast and dialog on screen long enough to be read (a few seconds), not the instant
   the assertion passes.
3. Take exactly one print for the criterion, the single screen that shows best what it changes, at the same place in
   ANTES and DEPOIS: `python "{{SCRIPTS}}/serve.py" window shot --issue {{ISSUE}} --pass {{PASS}} --criterion S<n>`.
   Never one per step or per repetition. A failed case may keep one image of its own, named `falha-<caso>`.
4. Record it in one line: `python "{{SCRIPTS}}/frontlights.py" browser-gate record --issue {{ISSUE}} --pass {{PASS}}
   --criterion S<n> --head <served commit> --case <id>=ok` (or `--case <id>=falha:<what happened>`, with
   `--failure-kind infraestrutura|produto|config`); `--account conta1|conta2`, never the login; `--origin
   interceptada` for a response forced by network interception, which is never the only evidence of a behavior the
   real back could show.

Console errors and failed requests go to the text of your report, never into an image.

## Test data

Use any test account that exists and create, through the product's own endpoints and screens, every user,
account, profile or record the `Fluxo:` needs to run completely; keep it for reuse and add each item to
`dados-de-teste.json` beside the record (kind and id; never a login, a password or a whole row). Missing data is
never a reason to skip a case or stop. Only the local development database; never a real person's data. Never write
the database directly, except one exact statement the user approved in the session.

When the `Fluxo:` moves a test user to a restricted profile: save only that field and the user's id in
`perfil-original.json` before the move, undo it in a `finally`, read it back and compare, mark `restaurado: true`,
and record the field with `--profile-field "<campo>=<antes>-><depois>"`. A value that does not come back identical
is a failure to report, naming the field.

## Ending the pass

{{ENDING}}

Closing the window or the 5 minutes ending is never an answer to the question the session asks next. Stop only what
you started: `serve.py window close` stops only the Chrome the script opened.

## Your report

At most 20 lines, in Portuguese: per criterion, ANTES and DEPOIS side by side (the print names, the cases with `ok`
or what failed), console and network errors, each failure classified as infrastructure, product or config, the
evidence folder, the line "preparo: N s" from `window open`, and what is still owed (criteria without their ANTES).
Nothing in it says the pass was approved.
