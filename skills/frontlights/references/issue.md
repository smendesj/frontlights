# The issue: the spec written from the discovery

Stage 4 turns the decisions of stage 3 into the body of one GitHub issue: read the discovery log, the repository
instructions and the relevant code, then write, do not interview. A decision missing from the log is not invented
and not asked here: it goes back to stage 3. A statement in the body that the user never made is a defect.

## The only question: the seams

Before writing, sketch the seams the delivery will be tested at: existing ones first, the highest possible, a new one
only where nothing existing can observe the behavior. The ideal number of seams is one. Confirm them with
`AskUserQuestion` (the proposal first, recommended; the behavior each observes in the `preview`). Stage 6 tests only
at these seams; one found missing or wrong comes back to the user.

## The body

Fill `templates/issue.md` in the user's language, with no new question beyond the seams: its placeholders say what
goes where (Problema, Solução, Decisões de implementação, Decisões de teste, Fora de escopo before the criteria), and
the instructions stay here, never in the body. The decisions go without file paths or code snippets in the prose
(the paths live in Propriedade and the trace table), except a prototype snippet that records a decision better.
Mark a section that does not apply with the reason instead of inventing content. Do not write user stories. A trivial
change on the Short path may keep one compact body. With a screen field, button or action, the trace table of
`references/issues.md` goes whole in the approved file; a row without evidence is not approvable. Trace every
criterion to an approved decision; the criteria themselves are cut in stage 5.

## Approval

Ask approval of the revision by link and stamp (`SKILL.md`, "Show before approval"); the file is
`.frontlights/issue.md` until stage 5 publishes it. This approval publishes nothing and does not authorize code.
Every revision of an approved body (r2, r2.1) is a new approval of the exact file with its stamp; a decision written
into a local revision that is not in the stamped file is not approved.
