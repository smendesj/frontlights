# Discovery interview

On entering, read `docs/security.md`, "Artefato do grilling".

Stress-test the request until the user and you share one understanding of what
will be built and how. Walk the decision tree branch by branch, answer from the
code whatever the code can answer, and ask the user only what is theirs to
decide.

Use only within the coordinating `/frontlights` session. Read approved decisions,
the issue body when the work comes from an issue, and current planning input
before asking anything. Use `AskUserQuestion` for every question, in the user's
language, each with two to four concrete options and the recommended one first;
never ask an open question in prose. Workers without the tool return questions
to the coordinator.

An issue settles *what* is wanted. It almost never settles *how*. Starting from
an issue shortens the problem round; it never removes the solution round.

## The artifact: the picture of each round

Text alone makes the user imagine a screen, a flow or a set of layers from the options.
So there is one **artifact** per grilling: a private page published with the host's artifact
tool (`Artifact` in Claude Code, a claude.ai page that also opens on the phone), created at
the problem round with the **before** and then updated **on the same URL**, never one page per
round. With a screen, the before is a **print of the system running at the base** (`origin/<base>`),
taken with a test account and test data in the disposable Chrome window of the watched run
(`references/browser-testing.md`), never a screen rebuilt from the template or redrawn in the style of
the page; without a screen, it is a diagram of the flow, of the layers or of the current rule. The
print follows the clean-print rule of `references/browser-testing.md`, "Prints kept for the progress
summary", item "Clean", and enters the page as an image of the artifact: an asset of the host's
artifact tool, or embedded in the page when the host has nowhere to keep assets.

The page then gains **one section per decision question**: the solution round and every branch
of the decision tree, the pre-mortem included. Confirmation questions and the
closing "Seguimos?" get no section. Sections are numbered in that order, the before first, then the
decision questions, and titled by the question (so "seção 3" is the second decision question); in
stage 5 the slices' sections follow them (`references/issues.md`, the quiz).

A section explains more than the question, never repeats it: the question and its option previews
are in the session already, and the section answers "what does this imply". Every section follows
`templates/grilling-section.html`, in its fixed order: why we are asking; the visual; one concrete
scenario per option, with made-up data; the consequences (the cost of getting it wrong, whether it
is reversible and what each option prevents); the concepts in plain words; where the project already
does this (path:line and an excerpt of the project's real code); the recommendation, labelled as
opinion; and the choice, recorded after the answer. Visual, Cenário por opção and Consequências are
always present (one sentence each is enough for a simple question); among the others, a field
with nothing to say is omitted. The model applies to the three kinds of section: the
before of the problem round (its visual is the before, and its "why" says why it is a problem), each
decision question, and each slice section of the stage 5 quiz.

The visual follows the kind of question:

| The question is about | The visual |
| --- | --- |
| A screen | the before print and, per option, the **same print with markings** overlaid in HTML (boxes, arrows and texts on top), never a redrawn screen; the **after** for each approach of the solution round with the screen states of "Reconnaissance" |
| A flow or an order of steps | a timeline per option, side by side |
| A rule | a table of cases: made-up input and the result under each option |
| Layers, files or where something lives | a layers diagram per option, showing what each touches |
| A name or a text | a side-by-side comparison of where it appears |

**One local source, small edits.** The page source lives in `.frontlights/artifact.html`
(untracked; for a published issue, in its records folder, `.frontlights/issues/<n>/artifact.html`).
Each section is added with a small edit of that file and published on the same URL: never rewrite
the whole page each round. The discovery log records the URL and the source path at the first
publication (`templates/discovery.md`, "Artifact URL and source path"), and neither changes
afterwards. When the local file is missing (a new session, a compaction), read the published page
back with the artifact tool's read and go on editing that copy.

**Code, never data.** The page lives outside the machine. A real excerpt of the project's code (up
to 15 lines, with its path) may enter it, with the value of any secret (password, token, key,
connection string) replaced by `***`; real records, people's data, real endpoints and client or
organization names stay out of the page, code excerpts included: real data never enters, not even in
a print, which shows only test data, and the scenarios use made-up names, numbers and texts.

The question cites its section ("artefato, seção 2"; without a screen, "seção 1: fluxo e camadas,
antes"); the option `preview` stays the text of the option, so "artefato" is the page, "preview" is
the field. Never an inline widget: the page is the only visual. When the host has no artifact tool, say so in
one line, go on in text, and record "artefato indisponível" in the log.

## 1. Problem round

1. Summarize the observation or issue, source/timestamp, affected users and the
   observed pain. Publish the artifact with the **before** (above) before the problem is
   confirmed, so the user confirms what they see, not what they imagine, and the
   confirmation question cites its section. With a screen, the before print needs a test account
   and the base up: any test account that already exists (those of `browserTest.users` or any other)
   serves, and the session may create one on demand; when there is no test account or the base does
   not come up, the grilling stops there and goes on only once the account exists and the base is up,
   never with a rebuilt screen in place of the print.
2. Separate evidence from inference and untested assumptions. Read relevant code
   and existing issues; identify duplicates, contradictions and missing context.
3. When an issue already answers outcome, users, success measure and boundaries,
   show what it settles and confirm it in a single question ("A issue #<n> já
   define isto; confirmamos?"). Do not re-ask those points one by one.
4. Otherwise batch at most four related decisions per question round: desired
   outcome, success measure, boundaries, constraints, priority, compatibility.
5. The challenge of the issue comes after the reconnaissance, when it finds
   something (below).

## 2. Project conventions (read before proposing)

Before proposing any approach, read the code around the change and record its
established conventions, each with one or two example paths: module and file
structure, naming, error handling, configuration, persistence, dependencies and
libraries already in use, test layout and style, and documentation language.
Read `CONTEXT.md`, ADRs and project instructions when they exist. Fan the reading out: one
read-only subagent per area the change touches (front end, API, persistence, tests,
documentation), launched in one message, each reporting the conventions it found with example
paths; the interview itself stays in this session.

The existing pattern is the default. It may be broken only when it is concretely
worse for this problem (it cannot express the need, it causes a known defect, or
it costs clearly more than the alternative), and the approach that breaks it
must say so, why, and what the divergence costs: inconsistency, migration of
existing code, or debt left behind.

## Reconnaissance (verify before asking)

Before any approach is proposed, gather with evidence the facts the options will rest on, so the
user answers only what is theirs to decide. What runs is decided by the minimum below and by
triggers, never asked.

**Always.** Read the project's pitfalls first: `.frontlights/pitfalls.md`, when it exists (its
line format: `references/issues.md`, "Follow-ups"). With a screen, also: the **before** in the
running app, the origin of each text on the screen and its states; and the environment and the
personas: the app and the API up, one login attempt per persona, never a password asked, written
or shown.

**By trigger.** Each trigger the work turns on runs its probe:

| Trigger | Probe |
| --- | --- |
| Rule or data of more than one actor | actors × the controller's endpoints × the guard and the claim it reads, the inverse operation included |
| Consumes an existing endpoint | live HTTP probe on the local API: search, ordering, empty page and another account |
| Rule over existing data, or a migration | count `SELECT` of the states that contradict the premise |
| Shared contract, route, field or text | its writers and its consumers |
| Multi-step flow | the endings of the flow: each exit per step, retry, double click and partial failure |

The decision tree (section 4) names where to look; these probes bring the facts for its branches:
edge cases from the endings of the flow, compatibility and migration from the count and from the
writers and consumers, permissions from the actors.

**Fact before option.** Each probe runs in a subagent, the probes launched together in one
message, and each returns a short fact table (up to about 20 lines, each fact with its evidence by
path, command or query); the raw output stays in the subagent. An unverified fact never becomes an
option.

A family runs one reconnaissance, as it has one grilling: each sub-issue turns on its own triggers
in the same table, and the probes of the whole family go out together.

The discovery log records every trigger as "ligado" or "não se aplica, porque…"
(`templates/discovery.md`, "Reconnaissance"), with the fact table of each probe that ran.

**What the facts change.** The pre-mortem (section 5) runs by trigger. Whenever the reconnaissance
finds something (a fact that contradicts the issue, its premise or the code it assumes),
challenge the issue: gaps in the acceptance criteria, forgotten edge cases, conflicts with the
current code or with other issues. A change of scope is a divergence from GitHub: report it and
propose updating the issue under the approvals of stage 5; never treat the local record as the new
scope.

**Screen states in the artifact.** With a screen, the **after** of each approach in the artifact
shows the empty state, no image, error, loading, dark theme and 1366 px, plus the states the
project's pitfalls list, as notes on its one marked print (where each state shows and what it
says), never one print per state; the evidence of the after still comes from the watched run.

## 3. Solution round (mandatory)

Propose **at least three genuinely different approaches**, and up to four, in one
`AskUserQuestion`, one per option (the tool adds free text). Variations of
one idea do not count: differ in strategy, for example minimal change,
structural refactor, a different architecture or an existing library, or
configuration instead of code. When the problem truly admits fewer than three
sensible approaches, say why in the question text and offer the real ones plus
"Investigar mais antes de decidir".

For every approach, the option `preview` shows:

- files and modules touched, with a short sketch (signature, pseudo-diff or flow);
- **pattern fit:** follows the convention (cite the example path) or breaks it
  (why, and the cost of the divergence);
- effort, risk, reversibility and compatibility;
- how it would be tested, at which public seam;
- the section of the artifact that shows what this approach changes and, when there is a
  screen, its **after** (the artifact, above).

Recommend first, with the reason in one line. Prefer the approach that follows
the project's pattern unless section 2 justifies breaking it. Record rejected
approaches with the reason.

## 4. Decision tree

After the approach is chosen, walk its branches in order. Each relevant branch
is one question with at least three concrete options when three sensible ones
exist, up to four real options, batched at most four per call.
Pick the branches by kind of work:

| Kind | Branches |
| --- | --- |
| Feature | interface/API, data model, validation and errors, edge cases, compatibility/migration, tests and seams, observability, rollout |
| Bug | reproduction, root cause vs. symptom, fix location, regression test, similar occurrences elsewhere, compatibility |
| Refactor | target boundary, migration order, behavior preservation evidence, pattern it converges to, rollback |
| Integration | contract and versioning, authentication (never secrets in the repository), failure and retry, test doubles vs. live verification, rate and cost |
| Document | audience, structure, sources of truth, maintenance owner |

Every branch that is asked cites its section of the artifact, added for that question on the
same URL (the artifact, above).

When the user asks for more detail in free text ("não entendi", "detalhe no artefato"),
the session expands that question's section of the artifact on the same URL and asks the
same question again; that is the only re-ask besides new evidence.

The tree asks the user only product, scope and visual: a technical branch the evidence settles is
not asked; it becomes an assumption shown in the plan with its evidence (the fact table of
"Reconnaissance"). A technical branch the evidence cannot settle is asked like a product one, with
the fact table its probe brought and what stayed unproven. Every branch ends answered, an assumption with its evidence, or marked "não se
aplica, porque…" in the discovery log.

## 5. Pre-mortem (by trigger)

Runs when the reconnaissance turned on the actor, the existing-data or the migration trigger. Ask: "Supondo que isto falhe em produção, o motivo mais provável é <Z>. Como
tratamos?" with three options, for example mitigate now, accept and monitor, or
change the approach. Like every decision question, it cites its section of the
artifact (the artifact, above).

## Sub-issues of the issue (same session)

When the work comes from an issue with open sub-issues (`SKILL.md`, "An issue and
its sub-issues move together") and the user declined the conversion offered before the
grilling (`references/issues.md`, "Converting a family"), they are grilled in this session, after the
parent's problem and solution rounds. Never leave one out to "decide later". A converted
family has no sub-issues left: its boxes are grilled as the slices of one issue.

- Triage each by reading its body and the code. **Decided:** the body names an
  approach and its conventions, and they fit the parent's chosen approach.
  **Pending:** labelled `needs-decision`, no approach in the body, or an approach
  the code or the parent's approach contradicts.
- Decided ones are confirmed together in one question ("As filhas #a, #b já
  definem a abordagem; confirmamos?"), with each one's approach in one line in
  the `preview`. Any the user questions becomes pending.
- Pending ones each get their own solution round (section 3: at least three
  genuinely different approaches, pattern fit, recommended first) and the
  decision-tree branches that change their implementation. Batch the questions of
  up to four sub-issues per call. The parent's chosen approach and the decisions
  already taken are inputs: offer approaches consistent with them, and when a
  sub-issue's decision would change the parent's approach, say so and ask.
- When a round settles a `needs-decision` sub-issue, propose removing the label
  and filling its approach as part of the stage 5 update of that issue (a write on
  an existing issue, under the stage 5 approval); never change it on the spot.

## 6. Closing

Never decide alone that the interview is over. The open branches of sub-issues
count as open branches. End with one question whose
options are "Seguir para a issue", "Aprofundar <the most uncertain open
branch>" and "Aprofundar <the next one>". Keep going while the user chooses to
deepen, and do not re-ask settled decisions unless new evidence invalidates them
(or the user asked for more detail, section 4); explain such changes.

## Recording

Record everything in `templates/discovery.md`: conventions
with example paths, the trigger table and the fact tables of the reconnaissance, the URL of the artifact and its source path (or "artefato indisponível"), approaches considered (chosen and rejected, with reasons and pattern fit),
branch decisions, pre-mortem, unresolved questions, approval
references and evidence. If a small research/prototype step
is needed, bound it and obtain permission for any changes beyond existing
authority. For a family, record the approaches and decisions of each sub-issue in the
same tables, naming the issue number in the first column. Do not start product
implementation here.

Carry approved decisions, the chosen approach, the recorded conventions and
unresolved items into stage 4 (the issue) as the input. A decision log is
planning evidence, never an issue status database.
