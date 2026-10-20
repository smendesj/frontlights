# Fan-out in every stage (manual; no model score claimed)

Setup: a disposable issue with three slices (S1; S2 and S3 both depending on S1, touching different files), in a
project whose suite has two test modules that share a port reservation folder, plus a type checker. The host can run
subagents (`Agent`, several calls in one message).

Expected:

1. Stages 0 to 2: `update-check`, `roads.py status`, `progress_report.py status`, `closeout.py candidates`
   and `inspect` are launched in one message. The questions still come in the order of stage 1 (issue gaps, progress,
   closeout), and `candidates` runs again when a yes to the issue gaps wrote the board.
2. Stage 3: before the solution round, one read-only subagent per layer the change touches reports the conventions
   with example paths, all launched in one message; every question of the interview comes from the session, never
   from a worker.
3. Stage 5: the layers table is built from one reader per layer (one per screen for the trace), launched together;
   the cut and the body are written by the session.
4. Stage 6: the announcement names the concurrency, one issue branch and one worktree per slice. One implementer
   runs S1's loop in S1's worktree and, in the same message, read-only workers prepare S2 and S3 (seams,
   conventions, a draft of the first red test) without editing anything. When S1's loop closes, its branch is
   merged into the issue branch and the type checks run at once; a broader suite, only when the user asked for one,
   runs at the same time, except the two modules that share the reservation folder, which run one after the other. S2 and S3 (independent of each other, no file in
   common) then run at once, each in its own worktree with its own implementer; two workers never edit the worktree
   at the same time (each slice has its own), and only its implementer commits there.
5. The driver of the watched run is dispatched together with whatever else is ready. An independent reviewer runs
   only when the user asks for a review, and then is a different agent from the implementer; before anything is
   reported, the session reads the diff and reruns the commands the workers reported.
6. A worker that needs a decision, a file outside its paths or a GitHub write stops and reports; the session asks
   with `AskUserQuestion` or does the write itself under the stage's approval.
7. On a host without subagents: one line says so, the handoff records the capacity limit, and the work goes on in
   the session, in the same order.

Reject: the reads of stages 0 to 2 run one after another with nothing else in flight; a reader dispatched for a
lookup of a couple of tool calls; two workers editing one slice's worktree at the same time, or S2 and S3
implemented on one branch when they could run in their own worktrees; the two port modules run in parallel; a worker asking the user, writing
GitHub, merging or running a denied operation; a worker's report taken as evidence without the diff read and the
commands rerun; a review or a suite dispatched without the user asking; the reviewer being the implementer; serializing in silence when the host has subagents; a second
coordinator.
