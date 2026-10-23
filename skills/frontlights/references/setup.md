# Setup

Read when: `inspect` reports `config_missing` or a setup warning (`browser_test_missing`, `project_unresolved`,
`branch_prefix_missing`).

## The first config

`frontlights.py init-config` writes `.frontlights/config.json` in the main worktree, `repository` from the remote,
never the `project` key, and returns the `boards`. Ask the board with those boards and "Sem quadro" (`project: null`)
before any issue write (`references/issues.md`, "Project board"). A missing prefix becomes `branchPrefix`, asked.

## The browserTest block

Absent, ask once whether the project has a screen. "Sem tela" writes `browserTest: null`; the block itself is
proved by `serve.py start` and `stop` at the first opening of stage 6, never here.

`browserTest: null` with a visible file in the diff (`browser-gate` says `unconfigured`) is one question, never a
skipped gate, the closing inside its options (`references/browser-testing.md`, "One watched run per issue"):
"Configurar o `browserTest` agora" comes back here for the draft, then the watched run.

## The draft

The new block is approved by link and stamp as a draft under `.frontlights/`, every
`browserTest.users[].password` shown as `***`. The real value goes only into the final config, after the approval,
and is never printed.
