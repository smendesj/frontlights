# Discovery interview

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

## 0. Depth

Open the interview with the depth question: "Qual profundidade de grilling?"
Options, recommended first according to the size and risk of the work:

- **Padrão:** problem round, solution round and decision tree (default).
- **Rápida:** confirm the problem in one question, then the solution round only.
- **Exaustiva:** everything, plus the pre-mortem and a critique of the issue.

The depth changes how many branches are explored, never the minimum of three
approaches in the solution round.

Ask the learning-mode question in the same `AskUserQuestion` call as the depth:
"Ativar o modo aprendizado?", with "Desligado" first and recommended (the default)
and "Ligado". It helps a user who is still learning to understand the technical
decisions while making them. Read `references/learning.md` before writing the
first explanation: right away when the mode is on, otherwise the first time the
user picks "Explicar antes de decidir" or asks for an explanation, and again
whenever the user turns the mode on later or the conversation has been compacted,
in which case read the mode back from the discovery log. The user can turn the
mode on or off at any time; apply it from the next question, update the log's
learning-mode line whenever the mode changes and add the change, with the
question where it happened, to the log's learning-mode changes line. Record both
choices.

## The artifact: the picture of each round

Text alone makes the user imagine a screen, a flow or a set of layers from the options.
So there is one **artifact** per grilling: a private page published with the host's artifact
tool (`Artifact` in Claude Code, a claude.ai page that also opens on the phone), created at
the first round that touches a screen, a flow or the layers and updated at every later round
**on the same URL**, never one page per round. It carries one section per question that
touches a screen, a flow or the layers, numbered in the order of those questions and titled
by the question (so "seção 2" is the second question that touched the screen), with:

- the **before** of the screen, built from the real template of the component (its HTML,
  the CSS that styles it and the fields it shows, read from the repository), never a free
  sketch;
- the **after** for each approach of the solution round and, in the decision tree, for each
  option that changes what the user sees;
- without a screen, a diagram of the flow and of the layers, before and after.

The page lives outside the machine, so it carries only fictitious data: made-up names, numbers
and texts; no real record, secret, endpoint, person or client enters it. The question cites
the section ("artefato, seção 2: depois por abordagem"; without a screen, "seção 1: fluxo e
camadas, antes e depois"); the option `preview` stays the text of the
option, so "artefato" is the page, "preview" is the field. The URL is recorded in the
discovery log (`templates/discovery.md`, "Artifact URL") at the first publication and does
not change afterwards. Never a real screenshot of the running product (that belongs to the
watched run) and never an inline widget: the page is the only visual. When the host has no
artifact tool, say so in one line, go on in text, and record "artefato indisponível" in the log.
When no round of the grilling touches a screen, a flow or the layers (a document, say), there
is no artifact, and the log line reads "não se aplica".

## 1. Problem round

1. Summarize the observation or issue, source/timestamp, affected users and the
   observed pain. When the change touches a screen, a flow or the layers, publish the
   artifact with the **before** (above) before the problem is confirmed, so the user
   confirms what they see, not what they imagine, and the confirmation question cites
   its section.
2. Separate evidence from inference and untested assumptions. Read relevant code
   and existing issues; identify duplicates, contradictions and missing context.
3. When an issue already answers outcome, users, success measure and boundaries,
   show what it settles and confirm it in a single question ("A issue #<n> já
   define isto; confirmamos?"). Do not re-ask those points one by one.
4. Otherwise batch at most four related decisions per question round: desired
   outcome, success measure, boundaries, constraints, priority, compatibility.
5. **Challenge the issue** (always at Exaustiva, and at Padrão when you find
   something): gaps in the acceptance criteria, forgotten edge cases, conflicts
   with the current code or with other issues. A change of scope is a divergence
   from GitHub: report it and propose updating the issue under the approvals of
   stage 5; never treat the local record as the new scope.

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

## 3. Solution round (mandatory, every depth)

Propose **at least three genuinely different approaches** in one
`AskUserQuestion` (three or four options; the tool adds free text). Variations of
one idea do not count: differ in strategy, for example minimal change,
structural refactor, a different architecture or an existing library, or
configuration instead of code. When the problem truly admits fewer than three
sensible approaches, say why in the question text and offer the real ones plus
"Investigar mais antes de decidir".

With learning mode off, the fourth option is "Explicar antes de decidir", so the
round has exactly three approaches; it takes a slot and never replaces an
approach below the minimum of three. With learning mode on, explain first (see
`references/learning.md`) and the round may carry four approaches.

For every approach, the option `preview` shows:

- files and modules touched, with a short sketch (signature, pseudo-diff or flow);
- **pattern fit:** follows the convention (cite the example path) or breaks it
  (why, and the cost of the divergence);
- effort, risk, reversibility and compatibility;
- how it would be tested, at which public seam;
- the section of the artifact that shows the **after** of this approach, when the
  approach touches a screen, a flow or the layers (the artifact, above).

Recommend first, with the reason in one line. Prefer the approach that follows
the project's pattern unless section 2 justifies breaking it. Record rejected
approaches with the reason.

## 4. Decision tree

After the approach is chosen, walk its branches in order. Each relevant branch
is one question with at least three concrete options when three sensible ones
exist, batched at most four per call (the learning-mode check counts as one).
Pick the branches by kind of work:

| Kind | Branches |
| --- | --- |
| Feature | interface/API, data model, validation and errors, edge cases, compatibility/migration, tests and seams, observability, rollout |
| Bug | reproduction, root cause vs. symptom, fix location, regression test, similar occurrences elsewhere, compatibility |
| Refactor | target boundary, migration order, behavior preservation evidence, pattern it converges to, rollback |
| Integration | contract and versioning, authentication (never secrets in the repository), failure and retry, test doubles vs. live verification, rate and cost |
| Document | audience, structure, sources of truth, maintenance owner |

A branch that touches a screen, a flow or the layers cites the section of the artifact
that shows it, updated for that round on the same URL (the artifact, above).

Technical branches (every branch except scope, priority and other product
questions) follow the slot rule of `references/learning.md`. With learning mode
off, the last option is "Explicar antes de decidir" (at most three real
options); its `preview` only lists what will be explained. With it on, explain
first and put one "Ficou claro?" check in the same call as up to three decisions.

Every branch ends answered or marked "não se aplica, porque…" in the discovery
log. At Rápida depth, ask only the branches that change the implementation and
record the rest as assumptions to be shown in the plan.

## 5. Pre-mortem (Exaustiva, and whenever the risk is high)

Ask: "Supondo que isto falhe em produção, o motivo mais provável é <Z>. Como
tratamos?" with three options, for example mitigate now, accept and monitor, or
change the approach.

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
- Depth and learning mode are asked once, in section 0, for the whole family.
- When a round settles a `needs-decision` sub-issue, propose removing the label
  and filling its approach as part of the stage 5 update of that issue (a write on
  an existing issue, under the stage 5 approval); never change it on the spot.

## 6. Closing

Never decide alone that the interview is over. The open branches of sub-issues
count as open branches. End with one question whose
options are "Seguir para a issue", "Aprofundar <the most uncertain open
branch>" and "Aprofundar <the next one>". Keep going while the user chooses to
deepen, and do not re-ask settled decisions unless new evidence invalidates them
or the user asked for another explanation in the same call (see
`references/learning.md`); explain such changes. Decisions marked "a revisar"
(taken by recommendation in learning mode) come first among the branches offered
for deepening.

## Recording

Record everything in `templates/discovery.md`: depth, learning mode, conventions
with example paths, the URL of the artifact (or "artefato indisponível", or "não se
aplica"), approaches considered (chosen and rejected, with reasons and pattern fit),
branch decisions, concepts explained, pre-mortem, unresolved questions, approval
references and evidence. If a small research/prototype step
is needed, bound it and obtain permission for any changes beyond existing
authority. For a family, record the approaches and decisions of each sub-issue in the
same tables, naming the issue number in the first column. Do not start product
implementation here.

Carry approved decisions, the chosen approach, the recorded conventions and
unresolved items into stage 4 (the issue) as the input. Decisions marked "a revisar"
go in as assumptions to be shown, never as approved decisions. A decision log is
planning evidence, never an issue status database.
