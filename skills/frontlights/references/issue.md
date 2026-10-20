# The issue: the spec written from the discovery

Stage 4 turns the decisions of stage 3 into the body of one GitHub issue. Read the discovery
log, the repository instructions and the relevant code; then write, do not interview. The
decisions were made in the grilling: a decision that is missing from the log is not invented
and not asked here, it goes back to stage 3 (its solution round or its decision tree). A
statement in the body that the user never made is a defect.

## The only question: the seams

Before writing, sketch the seams at which the delivery will be tested: prefer the seams that
already exist, use the highest one possible, and propose a new one only where nothing existing
can observe the behavior. The ideal number of seams is one. Confirm them with `AskUserQuestion`
(the proposal first, as the recommended option; the alternatives after it), with the behavior
each seam observes in the `preview`. Stage 6 writes tests only at these seams, so confirming
them is part of the approval of the issue, and a seam that turns out missing or wrong during
implementation comes back to the user, never gets invented.

## The body

Use `templates/issue.md`, in the user's language. The sections before the acceptance criteria
are the spec: Problema (the problem from the user's point of view, with the observed pain and
its source), Solução (the solution from the user's point of view, with the measure of success),
Decisões de implementação (the chosen approach, the rejected alternatives with their reasons, the
conventions followed, named by their pattern (paths belong to the ownership and the trace table),
and every approved break with its cost; interfaces,
contracts, schema and architecture decisions, without file paths or code snippets in the prose,
because they go stale; the only exception is a snippet a prototype produced that records a
decision better than prose, trimmed to the decision and said to be from the prototype), Decisões
de teste (what a good test is here, the confirmed seams with the behavior each one observes, the
prior art in the codebase and the real regression, integration and type-check commands) and Fora
de escopo (what was refused and why: the most useful lines of the page). Mark a section that does
not apply with the reason instead of inventing content. Do not write user stories: the kinds of
work of the decision tree already cover features, bugs, refactors, integrations and documents. A
trivial change on the Short path may keep one compact body.

When the work touches a screen field, button or action, include the trace table of
`references/issues.md` (consumer in the back as `file:line`, database column, test) and show it
in full before approval; a row without evidence, or an inconclusive trace, is not an approvable
body. Trace every acceptance criterion to an approved decision, and do not smuggle unresolved
product choices into technical assumptions. The acceptance criteria themselves are cut in stage
5, from this body.

## Approval

Show the complete revision before asking: the full text in the conversation, the file sent with
the host's file-sending tool when one exists, and the text (or as much as fits) in the `preview`
of the approve option. A summary or a path is not showing it. Then ask explicit approval with
`AskUserQuestion`, with options, and preserve the response reference. Keep the approved text in
`.frontlights/issue.md` until stage 5 publishes it: this approval publishes nothing and does not
authorize code, because the GitHub write is the approval of stage 5. Later material changes
invalidate downstream approvals. Every revision of an approved body (r2, r2.1, and so on) is a
new approval of the exact text shown in full; a decision written into a local revision without
being shown is not approved.
