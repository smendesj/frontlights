# Discovery interview

Read when: entering stage 3; "Reconnaissance" also on the Direct path.

On entering, read `docs/security.md`, "Artefato do grilling".

Stress-test the request until the user and you share one understanding of what will be built and how: the code
answers what it can, the user only what is theirs. Only the coordinating `/frontlights` session asks
(`AskUserQuestion`, in the user's language). Starting from an issue shortens the problem round;
it never removes the solution round.

**One interview at a time.** A second grilling only runs its reconnaissance until the user closes the first.

## The artifact: the picture of each round

One **artifact** per grilling: a private page of the host's artifact tool, created at the problem round with the
**base** and then updated **on the same URL**, never one page per round. With a screen, the base is a **print of
the system running at the base** (`origin/<base>`), taken with a test account and test data in the disposable Chrome
window of the watched run (`references/browser-testing.md`), its ANTES window, which opens here and stays open
(`serve.py window open --strip "ANTES: origin/main"`, then `serve.py window shot --pass antes --name base`); never a
screen rebuilt from the template or redrawn in the style of the page. Without a screen, it is a diagram of the flow,
of the layers or of the current rule. The print follows `references/browser-testing.md`, "Prints kept for the
progress summary", item "Clean", and enters as an image of the artifact: an asset of the host's artifact tool, or
embedded in the page when the host has nowhere to keep assets.

Then **one section per decision question**: the solution round and every branch of the decision tree, the
pre-mortem included. Confirmation questions and the closing "Seguimos?" get no section. Numbered the base first,
then the decision questions, titled by the question; in stage 5 the slices' sections follow them. A section explains
more than the question, never repeats it: it answers "what does this imply". Every section follows
`templates/grilling-section.html`; Visual, Cenário por opção and Consequências are always present, and a field with
nothing to say is omitted. The model covers the base of the problem round (its "why" says why it is a problem),
each decision question and each slice section of the stage 5 quiz. The visual follows the kind of question: a
screen, the base print and, per option, the **same print with markings** overlaid in HTML (boxes, arrows and texts
on top), never a redrawn screen, which for each approach carries the screen states of "Reconnaissance"; a
flow, a timeline per option, side by side; a rule, a table of cases; layers, a layers diagram per option; a name or a
text, a side-by-side comparison of where it appears. **Base and com a opção.** The page, its labels and the
questions that cite it say "base" and "com a opção", never antes/depois nor before/after: ANTES and DEPOIS name the
windows of the watched run.

**The script builds the skeleton; the session writes, publishes and keeps the URL.** `frontlights.py artifact init`
writes `.frontlights/artifact.html` (untracked; for a published issue `.frontlights/issues/<n>/artifact.html`) with
the base as section 1. Each round, the fields go in a small file per section, then `frontlights.py artifact section
--n <k> --kind tela|fluxo|regra|camadas|texto --title "<pergunta>" --option "<opção>" --content <file>` (several
`--n` in one call; the same number replaces a section), and once the user answers `frontlights.py artifact choose --n <k>
--answer "<literal>"`. Publish the whole source once per round, on the same URL, never by `edits`. The discovery log
records the URL and the source path at the first publication (`templates/discovery.md`, "Artifact URL and source
path"). Source missing (new session, compaction): the script refuses; read the published page back with the
artifact tool's read into that path.

**Code, never data:** `docs/security.md`, "Artefato do grilling".

The question cites its section ("artefato, seção 2"); "artefato" is the page, "preview" is the field. Never an
inline widget. Without an artifact tool, say so in one line, go on in text and record "artefato indisponível".

## 1. Problem round

1. Summarize the observation or issue, its source and date, who it hurts and how. Publish the artifact with the
   **base** before the problem is confirmed; the confirmation question cites its section. With a screen,
   any test account that already exists (those of `browserTest.users` or any other) serves, and the session may
   create one on demand; when there is no test account or the base does not come up, the grilling stops and goes on
   only once the account exists and the base is up.
2. When the issue already settles outcome, users, success measure and boundaries, one question confirms it ("A
   issue #<n> já define isto; confirmamos?"); otherwise ask the open points, at most four per call.

## 2. Project conventions (read before proposing)

Record the conventions around the change, each with an example path (structure, naming, errors, configuration,
persistence, libraries, tests, documentation language; `CONTEXT.md` and ADRs when they exist), by `SKILL.md`, "Fan
out": one read-only subagent per area the change touches, launched in one message; the interview itself stays in
this session. The existing pattern is the default. Break it only when it is concretely worse here, saying why and
what the divergence costs.

## Reconnaissance (verify before asking)

Before any approach, the facts the options rest on, with evidence. What runs is decided by the minimum below and by
triggers, never asked.

**Always.** Read the project's pitfalls first: `.frontlights/pitfalls.md`, when it exists (its line format:
`references/issues.md`, "Follow-ups"). With a screen, also the **before** in the running app, the origin of each
text and its states, and the environment and the personas: the app and the API up, one login attempt per persona,
never a password asked, written or shown.

| Trigger | Probe |
| --- | --- |
| Rule or data of more than one actor | actors × the controller's endpoints × the guard and the claim it reads, the inverse operation included |
| Consumes an existing endpoint | live HTTP probe on the local API: search, ordering, empty page and another account |
| Rule over existing data, or a migration | count `SELECT` of the states that contradict the premise |
| Shared contract, route, field or text | its writers and its consumers |
| Multi-step flow | each exit per step, retry, double click and partial failure |

The decision tree (section 4) names where to look; these probes bring the facts for its branches.

**Fact before option.** Each probe runs in a subagent, launched together in one message; each returns a short fact
table (up to about 20 lines, each fact with its evidence by path, command or query), kept as a note beside the
discovery log. An unverified fact never becomes an option. A family runs one reconnaissance, all its probes at once.
The discovery log records every trigger as "ligado" or "não se aplica, porque…" (`templates/discovery.md`,
"Reconnaissance").

**What the facts change.** Whenever the reconnaissance finds something that contradicts the issue, challenge the
issue. A change of scope is a divergence from GitHub: report it and propose the update under stage 5.

**Screen states in the artifact.** With a screen, each approach **com a opção** in the artifact shows the empty
state, no image, error, loading, dark theme and 1366 px, plus the states the project's pitfalls list, as notes on its
one marked print, never one print per state; the evidence of DEPOIS still comes from the watched run.

## 3. Solution round (mandatory)

Propose **at least three genuinely different approaches**, and up to four, in one `AskUserQuestion`, one per option.
They differ in strategy (minimal change, refactor, another architecture or library, configuration instead of code),
never variations of one idea; with fewer than three sensible ones, say why and add "Investigar mais antes de
decidir". Each `preview`: files touched with a sketch; **pattern fit** (the convention followed, with its path, or
the break and its cost); effort, risk, reversibility; the public seam it would be tested at; the section of the
artifact that shows what this approach changes. Recommend first, in one line; record the rejected ones with the
reason.

## 4. Decision tree

After the approach is chosen, the branches go by frontier: every decision whose prerequisites are settled is asked
in the same call, batched at most four per call, up to four real options each, the recommended one first, in plain
words without jargon, the fact it rests on written inside the question. A dependent decision waits for the next
round; a verified fact is never an option; an empty frontier ends the tree. Branches by kind: feature (interface,
data, errors, edge cases, migration, rollout); bug (root cause, fix location, regression test, similar occurrences);
refactor (boundary, order, preservation evidence, rollback); integration (contract, authentication, failure, cost);
document (audience, sources of truth, owner). The seams stay in stage 4.

Every branch that is asked cites its section of the artifact. When the user asks for more detail in free text
("não entendi", "detalhe no artefato"), the session expands that question's section of the artifact on the same URL
and asks the same question again; that is the only re-ask besides new evidence.

The tree asks the user only product, scope and visual: a technical branch the evidence settles is not asked; it
becomes an assumption shown in the plan with its evidence. A technical branch the evidence cannot settle is asked
like a product one, with its fact table. Every branch ends answered, assumed with evidence, or "não se aplica,
porque…" in the log.

## 5. Pre-mortem (by trigger)

Runs when the reconnaissance turned on the actor, the existing-data or the migration trigger: "Supondo que isto
falhe em produção, o motivo mais provável é <Z>. Como tratamos?", three options (mitigate now, accept and monitor,
change the approach), citing its section.

## Sub-issues of the issue (same session)

When the issue has open sub-issues (`SKILL.md`, "The issue is the unit") and the user declined the conversion
(`references/issues.md`, "Converting a family"), they are grilled in this session, after the parent's problem and
solution rounds, none left for later.

- **Decided:** the body names an approach that fits the parent's. **Pending:** `needs-decision`, no approach, or one
  the code or the parent contradicts.
- Decided ones are confirmed together in one question ("As filhas #a, #b já definem a abordagem; confirmamos?").
- Each pending one gets its own solution round and the branches that change it, up to four sub-issues per call; one
  that would change the parent's approach says so.
- A settled `needs-decision` loses the label in the stage 5 update, never on the spot.

## 6. Closing

Never decide alone that the interview is over. The open branches of sub-issues count as open branches. End with
"Seguir para a issue", "Aprofundar <the most uncertain open branch>" and "Aprofundar <the next one>"; do not re-ask
settled decisions unless new evidence invalidates them (or the user asked for more detail).

## Recording

Record everything in `templates/discovery.md`: conventions, the trigger and fact tables, the URL of the artifact and
its source path (or "artefato indisponível"), approaches (chosen and rejected, with reasons), decisions, pre-mortem,
open questions and approvals; for a family, the issue number in the first column. No product implementation here.
Carry it into stage 4 (the issue) as the input; the log is planning evidence, never a status database.
