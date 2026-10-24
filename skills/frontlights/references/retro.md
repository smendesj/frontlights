# Retro after the release

Read when: the user accepts the offer after the merge of a release, or asks for a retro.

## The offer

Once per release, after `release landed` and the closeout: "Fazer a retro desta release?", options "Sim, fazer a
retro" and "Agora não". "Agora não" ends it with nothing written and is never asked again for that release. The
retro is never a gate: nothing waits on its answer.

## What it reads

The records of each issue of the release, never the transcript: `.frontlights/issues/<n>/` (the handoff and its
rounds, `checkpoint*.json`, `browser/result.json`, `review.json` when a review ran, `walkthroughs/`, `notes/`), the
charter in `.frontlights/authorization/<n>.json`, the `merge-local-main*.json`, the summaries under `.frontlights/out/`,
the issue on GitHub (criteria that entered after the approval) and the release PR. A fact the records do not hold
is not a finding.

## Findings and their destinations

A finding is something that cost turns, a question or a wrong step in this release, with the record that shows it
(path, and the line or field). Each one gets exactly one destination:

- **A script check:** a test that reports or a warning a script prints, so the next run sees it without prose.
  Never a hook that blocks: a guard is a test or a warning.
- **A pitfall line:** one line in the project's `.frontlights/pitfalls.md`, in the format of `references/issues.md`,
  "A pitfall line", with no real data.
- **A rule in its single home:** the one file that owns that rule (`CLAUDE.md` of the Frontlights repository names
  them); every other text points to it.
- **A no-op to delete:** a rule or step that never fired in the records, or that a script already enforces; the
  finding is its deletion.

A finding with no destination is dropped, said in one line. Two findings with one cause are one.

## The batch

The findings go in one stamped file under `.frontlights/retro/` (`retro-<AAAA-MM-DD>.md`), one block per finding:
the fact, the record that shows it, the destination and, for the three destinations outside the project, the title
and body of the issue it becomes. It is approved by link and stamp as one batch. Approved, the pitfall lines are
written in the project, and each other finding becomes one issue in the Frontlights repository (the `origin` of the
clone `frontlights.py update-check` reads), each write named in the batch. The retro never edits the skill while
it runs in a consumer project: the change lands later, through that issue, in a Frontlights session.
