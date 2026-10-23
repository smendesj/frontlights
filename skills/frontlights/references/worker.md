# Worker

Read when: writing a brief for a subagent (any stage), and by the subagent that receives one. A worker reference is
read by whoever runs that work: the implementer reads `references/tdd.md`, the driver of the watched run the brief
`serve.py window brief` fills, a reader its notes.

The coordinating session is one: it alone asks the user, approves, writes GitHub, merges into the branch of an issue
or the local main, runs a denied operation and records the handoff (`SKILL.md`, "Fan out"). A worker does one bounded
piece of work and reports.

## Brief shape

Every brief carries, in this order, and nothing the worker can read for itself:

1. **Outcome.** One observable result (a box `S<k>` with its `Entrega:` and `depois:`, a question to answer, a file to
   read) and when it is done.
2. **Where.** The worktree path, the branch, and the owned paths; the base it was cut from.
3. **Tests.** The seams of the box and the command that proves it (for an implementer: `references/tdd.md`; a run "só
   com teste assistido": no tests).
4. **Notes.** The paths of the exploration notes that bear on it (`.frontlights/notes/` before the issue has a
   number, `.frontlights/issues/<n>/notes/` after; format in `docs/protocol.md`, "Registros"), never a retelling.
5. **Stage rules.** Only those that apply: test data (create what the flow needs through the product's own endpoints,
   or use a test account that exists, and keep it for reuse), secrets masked before printing, Portuguese for any text
   the user will read.
6. **Return.** At most 20 lines: what changed, the commands run with exit codes and counts, the paths of the files
   with the rest (test output, diffs, long reports), and the question or write it needs.

A reader's brief (reconnaissance, a probe, the preparation of the next slice) names the question, the area and the
note it writes, in the main worktree's `.frontlights`; it edits nothing else. A note is a map, not evidence: whoever
reads one confirms each `file:line` and runs their own red test before fixing.

## What a worker never does

A worker never calls `AskUserQuestion`, edits outside its paths, writes GitHub, merges another branch into an issue
branch or the local main, runs a denied operation or widens the scope. It stops and reports instead: the question, the
file outside its paths, the write it needs. The one merge it makes is in its own worktree: the branch it was cut from,
or the slice it depends on, brought into its own branch (`git merge <source>`, never a rebase or a force-push).

Workers share the codebase and must preserve others' changes: only one worker edits a worktree at a time, and only it
commits there; never discard, reset or stash work that is not yours. Ports, databases and test data are isolated as
well as Git; a test that shares one runs alone.

## The report is a claim

What a worker returns counts as evidence only after the coordinator reads the diff and reruns the commands it names.
A worker says what did not run as not run, labels a fixture test as a fixture test, and never invents an output.
