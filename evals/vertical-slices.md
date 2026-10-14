# Semantic decomposition evaluation (manual; no model score claimed)

Input: "Let users create, view and edit planning observations. We probably need
three tickets: a database table, backend endpoints, and frontend screens. Existing
project has authentication, an observation list shell and a storage abstraction."

Expected: silently revise the horizontal proposal before the quiz: the numbered list of the
slices (title, depends on, what it delivers) comes first, then the quiz on granularity, real
dependencies and merge or split, then the complete body. Slice 1 creates and retrieves one
observation through UI/API/storage with tests. Slice 2 edits with validation and
concurrent-edit feedback, depends on slice 1. Slice 3 is optional only if independently
requested; do not invent work to hit a ticket count. Each slice is one acceptance-criteria
box with its Entrega, the answer to "what can be demoed when this is done?", and every
criterion fails at the base commit. No extra question asking permission to repair an
obviously horizontal decomposition.

Reject: separate database/backend/frontend issues without a working seam; a slice with no
answer to what can be demoed; a criterion already true at the base commit; the body shown
before the numbered list; acceptance copied verbatim from the whole issue body; hidden
shared-file contention; claiming `validate-plan` semantically proved verticality; creation
before approval.

Prerequisite case: if no storage abstraction exists, a tiny tested persistence
seam may be a prerequisite only with a named consumer and executable demonstration.
Prefer embedding it into the first thin vertical outcome where practical.

Family case (manual): start from an issue that has five open sub-issues, one of them
labelled `needs-decision`, and a closed one. Expected: all five open sub-issues are read
from GitHub in stage 2 and enter the same grilling (the pending one gets its own solution
round, the four decided ones are confirmed together in one question, unless the code shows a
child's approach is still open, which then gets its own round with the reason); the plan holds the
parent and the five children with `parent` set, the closed one stays out; every issue body
carries `## Camadas da fatia` with each layer handled, delegated to a named sub-issue, or
not touched with a reason; stage 6 opens under the standing authorization with no concurrency,
stacking or authorization question, and its announcement stacks each child that depends on the
parent on the parent's branch and sets a concurrency equal to the number of children with
disjoint `ownership`.

Reject: planning only the parent; "children after the parent's merge" as the default; a
concurrency or stacking question when stage 6 opens;
a sub-issue that is only "the API part"; a layer missing from the table; the pending
sub-issue left out of the grilling; claiming `validate-plan` checked the layers.

Trace case (manual): the request is to fix the save of a settings form with four
fields; the proposal marks the API layer "not touched, already validates (400)". Expected:
before any plan is shown, every field is traced to its consumer in the back (`file:line`)
and its database column, found by search. Two fields with no consumer in the back and two
back capabilities with no action on the screen become acceptance criteria of the issue, never
sub-issues and never "not touched". A consumer that cannot be proven by reading (dynamic access,
a column name built in a string) becomes the task "prove the consumption by a test or by
reading the execution" and the plan is not offered for approval until it is closed. The issue
body (stage 4) and the plan show the complete trace table, and the `Fluxo:` of the browser test
also checks the effect in the back or the database after saving, not only what the screen shows.

Reject: a layer "not touched" with a reason but no evidence; a declared gap or a note in
place of the task; approving a plan with a row lacking evidence; a slice defined without
reading front end, back end, migrations and schema, tests and documentation; a `Fluxo:` that
only describes the screen.
