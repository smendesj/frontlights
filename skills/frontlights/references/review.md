# The independent reviewer's standard

This file is the standard of the independent reviewer of stage 6. The brief that dispatches the reviewer names it;
the implementer works from the issue, its seams and its tests, so the code is written to the issue and judged by
a standard its author did not aim at. Write the report in the user's language.

## What a finding is

A finding is a defect: something in the diff that makes what is delivered differ from the issue, its acceptance
criteria, the project's rules or the user's safety. Every finding carries a **failure scenario**: the input or
state, and the wrong result, crash, leak or misleading instruction it produces. What has no failure scenario is
not a finding.

## Severity

- **Sério:** data lost or corrupted; a secret or personal data exposed; an operation the authorization denies (a
  push to the remote main, a merge, a deletion) made reachable; a crash on the main path; a security check
  bypassed; an acceptance criterion the diff claims and does not deliver.
- **Médio:** wrong behaviour on a path the issue covers that is not the main one (an edge case, an error path, a
  platform the project supports); a regression of existing behaviour; a test that passes without exercising what
  it claims (tautological, or at a seam the issue did not agree); text an agent or a user follows that leads to a
  different action than the issue decided (two instructions that contradict each other, a command that does not
  run, a missing step).
- **Baixo:** a real defect with a small blast radius: a misleading message or comment, a name that says the
  opposite of what it holds, a missing case in a rarely reached branch, documentation that names a stale file,
  section or count, a rule duplicated in two places that may drift apart.

Torn between two severities, take the higher one and say why in one line.

## Style

Style is what the reader understands the same way whichever form it takes. It stays out of the report, at every
severity:

- line width, line breaks, blank lines, paragraph breaks and indentation;
- punctuation and parentheses, the order of clauses, a synonym, the length of a sentence;
- the order of a list whose order carries no meaning;
- another way of writing code that behaves the same (a loop for a comprehension, a helper's name).

A formatter, linter or test the project runs owns its own rules: when it fails, report the failing check with its
command and output, as a defect of the severity its failure scenario has.

## Rounds

A round is one dispatch of the reviewer on the current tip. The first round reviews the whole diff of the issue
against its base (`git diff <base>...HEAD`) and the test evidence. Each later round reviews the delta since the tip
of the previous round (`git diff <previous tip>..HEAD`), the code that delta touches, and each finding of the
earlier rounds, marked fixed or open. A new finding in a later round comes from that delta or from what it touches;
text the earlier rounds read and left unchanged raises one only as a sério or médio they missed, said so.

## The report

First the line of counts, `sérios/médios/baixos: s/m/b`, then one block per finding, the most severe first:

- **Gravidade** and a short title;
- **Onde:** `path:line` at the head of the diff;
- **O que está errado:** one sentence;
- **Cenário de falha:** input or state → wrong result;
- **Evidência:** the command and its output, or the lines quoted;
- **Correção sugerida:** one sentence, when one is obvious.

From the second round on, add the list of the earlier findings, each `corrigido` (with the commit) or `aberto`.
Close with the HEAD the round covers and what it left uncovered (a module not run, a platform not available). The
reviewer reports and stops there: the coordinating session reads the counts, decides the destinations and applies
the stop criterion (`development.md`, "When the review is done").
