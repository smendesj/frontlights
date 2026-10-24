#!/usr/bin/env python3
"""Close-out helper: which issues (and sub-issues) can be closed because every acceptance criterion in the body is
checked, whether they ended closed; `tick`, which ticks one box; and `run`/`apply`, the closing by a stamped list. The board is
never read here: the board's own "Item closed" workflow moves the card to Done, never Frontlights.

Read only, except `tick` and `apply` (and `run`, which writes only its new list file). It reads GitHub through `gh api graphql` (the reader of roads.py) and prints what
the session may propose. Closing is done by the session, with its own `gh`, after the user said yes:
this helper never closes an issue, never moves a card, and the commands it prints are values to type, not
something it runs. Its only write is `tick` (below): the `[ ]` of one box of an issue's acceptance criteria turned
into `[x]`, under the authorization to tick criteria with evidence, with the previous body kept in the records.
Text read from GitHub is data: titles are cleaned and bounded, issue bodies are only counted (never echoed), and
every command is built from validated values (numbers and `owner/name`).

Operations (each prints one JSON object on stdout):
  run         the candidates (below), written to a new `.frontlights/closeout-<AAAAMMDD-HHMMSS>.md` under --root (São
              Paulo time): a Portuguese table in closing order, the exact commands and a machine block that apply
              rereads. Prints `path`, `stamp` (the 12-character sha256 of the file), `question`, `options` and
              `recommended`, for the approval by link and stamp. Nothing is written on GitHub.
  apply       --expect <stamp> --answer "<literal answer>" [--only 12,13]: finds the list with that stamp; "Não agora"
              writes nothing. It recomputes the candidates of the list's scope and refuses (`lista mudou: ...`,
              nothing written, not even the approval) when an issue left or entered, or its `order`, `state` or
              `parentTicks.lines` changed; refuses an --only that leaves a chosen parent without its child of the
              list. Only then it records the approval (`stamp --approve`, stage 7) and runs `stamp --check`. Then, in order and with the account checked before
              each write (`_cli.gh_account`), `gh issue close <n> --repo <repo> --reason completed`; after a sub-issue
              closes, its parent's lines are ticked in one write (capture, tick-check, `gh issue edit --body-file`,
              reread, tick-check), unless the answer is "Só fechar, sem marcar". A failed close holds its parent back;
              nothing is retried. `verify` of the closed issues, and `closeout-<...>.result.json` beside the list keeps
              the commands, their exit codes, the reread state and the literal answer. Never `--force`.
  capture     --issue n: the body exactly as GitHub holds it, in .frontlights/issues/<n>/body-before-<stamp>.md
              (`gh issue view --json body`, bytes, never a shell redirect). Read only on GitHub.
  append      --issue n with one of --items <stamped file> [--pitfall <file>], --spec <stamped plan> or
              --walkthrough <stamped plan>: `stamp --check` of that file (and of the pitfall file, approved by the same
              answer), capture, insert the lines (--items after the last item of the criteria section, refused on a
              closed issue or one without the section; --spec the boxes of the plan's issue, refused when it already
              has S<n> boxes; --walkthrough the two Roteiro lines under each open box that lacks them), check that only
              lines were added, capture again right before the write (a difference: `diverged`, nothing written),
              `gh issue edit --body-file` with the account checked first, reread (`criteria.before`/`after`; a
              difference: `diverged_after`) and only then append the pitfall line to .frontlights/pitfalls.md.
  candidates  the open issues that can be closed now, in the order to close them (sub-issues before
              their parent), plus the ones left out and why. Scope: --issues 12,13, or --all (every open
              issue of the repository), or, with neither, the issues this project worked on (folders in
              .frontlights/issues, ids in .frontlights/authorization*.json and .frontlights/plan.json)
              together with their sub-issues.
  verify      reread --issues and say, for each, whether it is closed.
  merge-status  for pull requests named with --prs 12,13, whether each is still open, was merged into the
              approved base (--base, else the repository's default branch), was merged into some other branch
              or was closed unmerged. This is what the session waits on after it opened its pull requests: only
              `merged_into_base` lets an issue be proposed for closing. Each open one also carries `reviewDecision`,
              `mergeStateStatus`, `mergeable` and `isDraft` as GitHub reports them, and `blocked` (with `blockedBy`)
              when the review asks for changes or a review, the merge state is BLOCKED, DIRTY or BEHIND, or it
              conflicts; `blocked` at the top lists them: a blocked pull request is never offered for merging.
  tick-check  local files only: confirms that --after is --before with nothing changed but the `[ ]` of the
              items on --lines turned into `[x]`. It checks the body of a parent that was edited to tick the
              item that cites a closed sub-issue; the edit itself is the session's. Line endings and empty lines at
              the end of either file are not compared (a reread through `--jq .body` or a redirect adds one).
  tick        the whole cycle of ticking one box of --issue: --box S<k> (also s<k> or <k>: the one item of the criteria
              section whose text starts with `S<k>.`), --box P<k> (the k-th leftover item of that section, the one
              whose text starts with `Pendência`, in order) or --line <N> (any item of that section, a criterion without a slice label included). It captures the
              body with `gh issue view --json body`, keeps it as .frontlights/issues/<n>/body-before-<stamp>.md under
              --root, builds body-new-<stamp>.md with only that `[ ]` turned into `[x]`, runs the tick-check, writes
              it with `gh issue edit --body-file`, rereads it into body-after-<stamp>.md and runs the tick-check
              again (`verified`). A box already ticked answers ok and writes nothing; a box that still has its
              `- Bloqueada:` sub-item is refused (that line is removed first, by the session). No shell, the
              repository is the validated `owner/name` of the configuration, and only line numbers are printed.
              A slice box (`S<k>.`, by --box or by --line) is ticked only with its evidence (redesign, issue 4):
              the record of the watched run approved (`situacao: aprovado` in .frontlights/issues/<n>/browser/
              result.json under --root, or --record for the lead issue of a family) or, for a box without a
              screen, .frontlights/issues/<n>/walkthroughs/S<k>.md in its format (a header, `## Antes` and
              `## Depois`, each with a fenced block); without either it is refused (`no_evidence`) before the
              body is read. A leftover box and a criterion without a label keep the evidence the session cites.
              --comment-file posts that file as a comment on the issue (`gh issue comment --body-file`) once the
              tick checks; `evidence` and `commented` say what happened.

An open issue is a candidate only when its body has an acceptance-criteria section with at least one
checklist item and every item checked, and every sub-issue is closed or a candidate in the same batch. A
closed issue is never a candidate: it is counted in `alreadyDone`.

The local base is the homologation bench of the project (issue 32): an issue's branch reaches GitHub only through
the release. So an issue whose branch still exists locally and is not yet contained in `<remote>/<base>` is kept
out with `awaiting_release` (its `branch`, `tip`, `base` and `remote`), and is a candidate again once the release
is merged. `--base` defaults to the `base.branch` of the newest authorization record that names the issue (else
`main`), `--remote` to `origin`. Git is read through `homolog` (`rev-parse` and `merge-base` only, nothing is
written) and never blocks on a doubt: a branch already deleted, no record and no `<prefix>issue-<n>` branch, no
remote ref or a root that is not a repository mean no exclusion. `releaseCheck` says what happened: `checked`
(at least one branch was compared), `unavailable` (Git could not answer: the root is not a repository) or
`skipped` (nothing to compare, or no remote ref).

A known leftover is an acceptance criterion like any other, so it is counted with the others. A body written
before that rule may hold the leftovers in a section of their own ("Pendencias conhecidas") outside the
criteria: such a candidate is still proposed, with the `pending_outside_criteria` caution and the number of
open items in `pendingOutside`, so the user is told before closing it. The caution informs and never blocks.

A sub-issue candidate also carries `parentTicks`: the line numbers of the unchecked items of its open parent's
body that cite it and no other issue (`lines`), and those that cite it together with other issues (`shared`,
never offered for ticking). Only line numbers are reported; the session reads the lines from its own copy of the
body, so no body text is ever echoed here.

Exit codes: 0 done; 1 refusal (bad usage or configuration, a failed read) or, for verify, an issue that is not
closed yet (`ok` is false and `issues` says which), or, for tick, a write
whose reread does not check (`written` true, `verified` false: show the difference and ask; restoring the saved body is a write of its own) or
whose outcome is unknown (`written` null: gh failed and the reread is neither body, or the reread itself failed).
A refusal is JSON, never a traceback.
"""

import argparse
import datetime as dt
import heapq
import json
from pathlib import Path
import os
import re
import subprocess
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import frontlights  # noqa: E402  (the configuration rules live there; this helper only reads them)
import _cli  # noqa: E402  (defaults of --root, --config and --issue, the parser and UTF-8)
import roads as rs  # noqa: E402  (its reader of GitHub: graphql, clean)

Refusal = rs.Refusal
require = rs.require

MAX_SCOPE = 200            # issues one run reads when it walks from records down through sub-issues
MAX_ALL = 1000             # open issues --all reads, and the longest --issues list
MAX_DEPTH = 8              # levels of sub-issues GitHub allows
PAGE = 100
MAX_RECORD_BYTES = 2 * 1024 * 1024
NUMBER = re.compile(r'[0-9]{1,9}')
CURSOR = re.compile(r'[A-Za-z0-9+/=_-]{1,200}')
PHRASES = ('acceptance criteria', 'criterios de aceitacao', 'criterios de aceite')
LEGACY_PHRASES = ('pendencias conhecidas', 'known pending')   # leftovers kept outside the criteria before they became criteria
HEADING = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*))?$')   # no lazy quantifier: a long line must not make it crawl
LINE_CAP = 2000          # a checklist item or a title never needs more than this of a line
FENCE = re.compile(r'^[ \t]*(`{3,}|~{3,})(.*)$')
ITEM = re.compile(r'^[ \t]*(?:[-*+]|[0-9]{1,9}[.)])[ \t]+\[([ xX])\](?=[ \t]|$)')
FEATURES = 'GraphQL-Features: issue_types'
BRANCH = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}')
PR_VIEW = ('number state merged mergedAt url baseRefName headRefName headRefOid mergeable mergeStateStatus '
           'reviewDecision isDraft')
BLOCKING_REVIEW = ('CHANGES_REQUESTED', 'REVIEW_REQUIRED')   # reviewDecision that keeps a PR from merging
BLOCKING_STATE = ('BLOCKED', 'DIRTY', 'BEHIND')                # mergeStateStatus that keeps a PR from merging
BOX = re.compile(r'([SsPp]?)([1-9][0-9]{0,2})')                # --box S2, s2, 2 or P1 (a leftover box)
LEFTOVER = re.compile(r'(?:\*\*|__)?Pend[eê]ncia\b', re.IGNORECASE)   # the text of a leftover box: `Pendência (...)`
BOX_LABEL = re.compile(r'(?:\*\*|__)?S([1-9][0-9]{0,2})\.')     # the text of a slice box: `S2.`, `**S2.**`
LIST_ITEM = re.compile(r'^[ \t]*(?:[-*+]|[0-9]{1,9}[.)])[ \t]')
BLOCKED = re.compile(r'bloqueada[\W_]*:')               # `Bloqueada:`, `**Bloqueada**:`, `__Bloqueada__:`, `Bloqueada :`

VIEW = '''number state stateReason title url body
  parent { number repository { nameWithOwner } }
  subIssuesSummary { total completed }
  subIssues(first: 100) { totalCount nodes { number state repository { nameWithOwner } } }
  closedByPullRequestsReferences(first: 20, includeClosedPrs: true) { totalCount nodes { number state merged url repository { nameWithOwner } } }
  timelineItems(last: 50, itemTypes: [CROSS_REFERENCED_EVENT]) { totalCount nodes {
    ... on CrossReferencedEvent { source { ... on PullRequest { number state merged url repository { nameWithOwner } } } } } }'''
CHILDREN = 'subIssues(first: 100) { totalCount nodes { number repository { nameWithOwner } } }'


# ---------------------------------------------------------------- acceptance criteria

def plain(text):
    """Lower case, no accents, single spaces, and no leading decoration (emphasis marks, emoji)."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn').casefold()
    return re.sub(r'^[\W_]+', '', ' '.join(text.split()))


def heading_text(text):
    """A heading's text without its optional closing sequence of `#` (which must follow a space)."""
    text = text.rstrip(' \t')
    bare = text.rstrip('#')
    if bare != text and (bare == '' or bare[-1] in ' \t'):
        text = bare.rstrip(' \t')
    return text


def strip_comments(line):
    """The line without its HTML comments, and whether one is still open at its end."""
    while True:
        start = line.find('<!--')
        if start < 0:
            return line, False
        end = line.find('-->', start + 4)
        if end < 0:
            return line[:start], True
        line = line[:start] + line[end + 3:]


def visible_lines(body):
    """(line number, text) of every line of a body that lies outside fenced code and HTML comments, without
    its comments and cut at LINE_CAP. Line numbers count from 1 over the body's own line endings (LF, CRLF or a
    lone CR), the way `tick-check` and the session count them."""
    fence = None      # (character, length) inside fenced code
    comment = False   # inside a multi-line HTML comment
    for number, raw in enumerate(re.split(r'\r\n|\r|\n', body), 1):
        if comment:
            end = raw.find('-->')
            if end < 0:
                continue
            raw, comment = raw[end + 3:], False
        if fence:
            if re.match(r'^[ \t]*' + re.escape(fence[0]) + '{%d,}[ \t]*$' % fence[1], raw):
                fence = None
            continue
        line, comment = strip_comments(raw)
        opened = FENCE.match(line)   # linear, so it reads the whole line: a cut line could look like a fence
        if opened and not (opened.group(1)[0] == '`' and '`' in opened.group(2)):
            fence = (opened.group(1)[0], len(opened.group(1)))
            continue
        yield number, line[:LINE_CAP]


def criteria(body):
    """(checked, total) for the checklist items of the body's acceptance-criteria section, or None when the
    body has no such section. The section is a markdown heading (any level) whose text, without accents and
    in lower case, starts with `acceptance criteria`, `criterios de aceitacao` or `criterios de aceite`; it
    runs to the next heading of the same or a higher level (deeper headings belong to it). Items are
    `- [ ]`, `* [x]`, `+ [X]` (and numbered `1. [ ]`), indented or not. Fenced code and HTML comments are
    skipped, and items outside the section never count. Several matching sections are added up."""
    return scan(body)[0]


def sections(body):
    """(line number, text, kind, heading) of every visible line of a body: `kind` is the section the line lies in,
    'criteria', 'pending' (a section of known leftovers kept outside the criteria) or None, and `heading` says the
    line is a heading. A heading that opens a section carries that section's kind."""
    level = None      # depth of the section being read; None outside one
    kind = None       # what that section holds: 'criteria' or 'pending'
    for number, line in visible_lines(body):
        heading = HEADING.match(line)
        if heading:
            depth = len(heading.group(1))
            name = plain(heading_text(heading.group(2) or ''))
            # deeper headings belong to the section being read, except a criteria heading under a legacy
            # section: that one still opens the criteria, exactly as it did before the legacy sections existed
            if not (level is not None and depth > level and not (kind == 'pending' and name.startswith(PHRASES))):
                level = kind = None
                if name.startswith(PHRASES):
                    level, kind = depth, 'criteria'
                elif name.startswith(LEGACY_PHRASES):
                    level, kind = depth, 'pending'
        yield number, line, kind, heading is not None


def scan(body):
    """(criteria, pending): `criteria` as `criteria()` returns it, and `pending`, the number of unchecked items
    in the sections the body keeps outside the criteria for known leftovers (a heading starting with
    `pendencias conhecidas` or `known pending`, read like the criteria section). A heading nested inside the
    criteria section belongs to it and is already counted there, so it is never counted twice."""
    if not isinstance(body, str):
        return None, 0
    checked = total = pending = 0
    found = False
    for _, line, kind, heading in sections(body):
        if heading:
            found = found or kind == 'criteria'
            continue
        item = ITEM.match(line) if kind is not None else None
        if item and kind == 'criteria':
            total += 1
            checked += item.group(1) in 'xX'
        elif item:
            pending += item.group(1) == ' '
    return ((checked, total) if found else None), pending


REF = re.compile(r'(?<![\w/#&])#([0-9]{1,9})(?![\w-])')
URL_REF = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/([0-9]{1,9})(?![\w-])', re.I)
SHORT_REF = re.compile(r'(?<![\w/.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([0-9]{1,9})(?![\w-])')
LOOSE_REF = re.compile(r'(?<![A-Za-z0-9&])#([0-9]{1,9})|\bGH-([0-9]{1,9})', re.I)


def issue_refs(line, repository):
    """(exact, every): the issues a line cites, as (repository or None for this one, number). `exact` holds what
    unmistakably names an issue: `#12` between plain characters, `owner/name#12` and the full URL of an issue.
    `every` adds each other shape that looks like a reference (`#12/#13`, `_#13_`, `GH-13`), so that an item that
    names one issue plainly and another sloppily is still seen as citing two."""
    exact = {(None, int(n)) for n in REF.findall(line)}
    for name, n in SHORT_REF.findall(line) + URL_REF.findall(line):
        exact.add((None if name.casefold() == repository.casefold() else name.casefold(), int(n)))
    return exact, exact | {(None, int(a or b)) for a, b in LOOSE_REF.findall(line)}


def citing_items(body, child, repository):
    """(lines, shared): the line numbers of the unchecked checklist items of `body` that cite issue `child` and
    no other issue, and of those that cite it together with others (a shared item is never ticked for one of
    them). Fenced code and HTML comments are skipped, as everywhere else."""
    if not isinstance(body, str):
        return [], []
    lines, shared = [], []
    for number, line in visible_lines(body):
        item = ITEM.match(line)
        if not item or item.group(1) != ' ':
            continue
        exact, every = issue_refs(line, repository)
        if (None, child) in exact:
            (lines if every == {(None, child)} else shared).append(number)
    return lines, shared


# ---------------------------------------------------------------- scope

def valid_number(value):
    return type(value) is int and 0 < value <= 999_999_999


def valid_branch(name):
    """A branch name this helper will type into a command: plain characters, no `..`, no empty part, and none
    of the endings Git refuses."""
    return (isinstance(name, str) and BRANCH.fullmatch(name) is not None and '..' not in name and '//' not in name
            and not name.endswith(('/', '.', '.lock')))


def parse_numbers(value, message='issue numbers must be positive integers, as in --issues 12,13'):
    """Issue numbers as typed after --issues (`12, 13`) or given as a list of integers: sorted, no repeats."""
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',')]
        require(all(NUMBER.fullmatch(part) for part in parts), message)
        numbers = {int(part) for part in parts}
    else:
        require(isinstance(value, (list, tuple)) and value and all(valid_number(part) for part in value), message)
        numbers = set(value)
    require(all(valid_number(n) for n in numbers), message)
    return sorted(numbers)


def read_record(path):
    try:
        if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
            return None
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, RecursionError):
        return None


def authorization_records(root):
    """The authorization records of the project (`_cli.record_files`: the .frontlights/authorization*.json files,
    oldest name first, then the per-issue charters), so the newest record is the last one, as homolog reads them."""
    return _cli.record_files(root)


def record_numbers(root, repository=None):
    """The issue numbers this project's records name: folders of .frontlights/issues, `issue_ids` of
    .frontlights/authorization*.json and the `id` of each issue of .frontlights/plan.json that is already
    published in `repository` (its `url` is that repository's issue with that same number) and not still a
    proposal: the ids of a plan before publication are only the proposal's own, never GitHub numbers. A record
    that is missing or unreadable is skipped."""
    base = Path(root) / '.frontlights'
    found = set()
    try:
        with os.scandir(base / 'issues') as entries:
            for entry in entries:
                if NUMBER.fullmatch(entry.name) and int(entry.name) > 0 and entry.is_dir(follow_symlinks=False):
                    found.add(int(entry.name))
    except OSError:
        pass
    for path in authorization_records(root):
        data = read_record(path)
        ids = data.get('issue_ids') if isinstance(data, dict) else None
        if isinstance(ids, list):
            found.update(n for n in ids if valid_number(n))
    plan = read_record(base / 'plan.json')
    issues = plan.get('issues') if isinstance(plan, dict) else None
    if isinstance(issues, list) and isinstance(repository, str):
        for issue in issues:
            if (isinstance(issue, dict) and valid_number(issue.get('id')) and issue.get('status') != 'proposed'
                    and isinstance(issue.get('url'), str)
                    and issue['url'].casefold() == f"https://github.com/{repository}/issues/{issue['id']}".casefold()):
                found.add(issue['id'])
    return sorted(found)


def issue_graphql(gh, query, missing_ok=()):
    """One GraphQL read. The sub-issue fields travel with the feature flag gh already sends for issue types
    (naming it again is harmless once GitHub needs none)."""
    def reader(argv):
        return gh([FEATURES + ',sub_issues' if part == FEATURES else part for part in argv])
    return rs.graphql(reader, query, missing_ok=missing_ok)


def read_aliases(gh, repository, numbers, view):
    """{number: GraphQL node, or None for a number GitHub does not know}, read GAPS_BATCH at a time."""
    owner, name = repository.split('/')
    nodes = {}
    for start in range(0, len(numbers), rs.GAPS_BATCH):
        chunk = numbers[start:start + rs.GAPS_BATCH]
        body = ' '.join(f'i{n}: issue(number: {n}) {{ {view} }}' for n in chunk)
        data = issue_graphql(gh, 'query { repository(owner: "%s", name: "%s") { %s } }' % (owner, name, body),
                             missing_ok={f'i{n}' for n in chunk})
        repo = data.get('repository') or {}
        for n in chunk:
            value = repo.get(f'i{n}')
            nodes[n] = value if isinstance(value, dict) else None
    return nodes


def page(connection):
    """(nodes, short): the object nodes of a GraphQL connection, and whether the page did not hold them all
    (a count above the nodes listed, or a node that is not an object)."""
    connection = connection if isinstance(connection, dict) else {}
    listed = connection.get('nodes') if isinstance(connection.get('nodes'), list) else []
    nodes = [node for node in listed if isinstance(node, dict)]
    total = connection.get('totalCount')
    return nodes, len(nodes) != len(listed) or (isinstance(total, int) and total > len(listed))


def other_repository(node, repository):
    """`owner/name` of a node that lives in another repository, else None."""
    home = node.get('repository')
    name = home.get('nameWithOwner') if isinstance(home, dict) else None
    return name if isinstance(name, str) and name.casefold() != repository.casefold() else None


def open_issue_numbers(gh, repository):
    """Every open issue of the repository, a page at a time, up to MAX_ALL; the flag says it was cut."""
    owner, name = repository.split('/')
    numbers, cursor, truncated = [], None, False
    for _ in range(MAX_ALL // PAGE + 2):
        after = '' if cursor is None else ', after: "%s"' % cursor
        data = rs.graphql(gh, 'query { repository(owner: "%s", name: "%s") { issues(states: OPEN, first: %d%s) '
                              '{ totalCount pageInfo { hasNextPage endCursor } nodes { number } } } }'
                          % (owner, name, PAGE, after))
        connection = (data.get('repository') or {}).get('issues')
        require(isinstance(connection, dict), 'GitHub answered the read with an error; check the repository, the project and the gh scopes')
        listed, _short = page(connection)
        numbers += [node['number'] for node in listed if valid_number(node.get('number'))]
        info = connection.get('pageInfo')
        if not (isinstance(info, dict) and info.get('hasNextPage') is True):
            break
        if len(numbers) >= MAX_ALL:
            truncated = True
            break
        cursor = info.get('endCursor')
        # The cursor is typed back into the next query: only what GitHub's own cursors look like is accepted.
        require(isinstance(cursor, str) and CURSOR.fullmatch(cursor),
                'GitHub answered with a page cursor this helper will not use; name the issues with --issues')
    else:
        truncated = True
    return sorted(set(numbers[:MAX_ALL])), truncated or len(numbers) > MAX_ALL


def expand(gh, repository, seeds):
    """The seeds and, level by level, their sub-issues (of this repository), up to MAX_DEPTH levels and
    MAX_SCOPE issues; the flag says something was left out."""
    seen = set(seeds)
    frontier = sorted(seeds)
    truncated = False
    for _ in range(MAX_DEPTH):
        if not frontier:
            break
        found = set()
        for number, node in sorted(read_aliases(gh, repository, frontier, CHILDREN).items()):
            kids, short = page((node or {}).get('subIssues'))
            truncated = truncated or short
            for kid in kids:
                child = kid.get('number')
                if not valid_number(child) or other_repository(kid, repository) or child in seen:
                    continue
                if len(seen) >= MAX_SCOPE:
                    truncated = True
                    continue
                seen.add(child)
                found.add(child)
        frontier = sorted(found)
    return sorted(seen), truncated or bool(frontier)


def scope_numbers(root, explicit, all_flag, gh, repository):
    """The issues one run looks at: {'mode': 'explicit' | 'all' | 'records', 'numbers': [...], 'truncated': bool}.
    `explicit` (a list or text such as `12,13`) is taken as it is. `all_flag` reads every open issue. With
    neither, the project's records are the seeds and their sub-issues come along."""
    require(not (all_flag and explicit is not None), '--issues and --all cannot be used together; choose one')
    if explicit is not None:
        numbers = parse_numbers(explicit)
        require(len(numbers) <= MAX_ALL, f'name at most {MAX_ALL} issues')
        return {'mode': 'explicit', 'numbers': numbers, 'truncated': False}
    if all_flag:
        numbers, truncated = open_issue_numbers(gh, repository)
        return {'mode': 'all', 'numbers': numbers, 'truncated': truncated}
    seeds = record_numbers(root, repository)
    cut = len(seeds) > MAX_SCOPE
    if cut:
        seeds = seeds[-MAX_SCOPE:]
    numbers, more = expand(gh, repository, seeds) if seeds else ([], False)
    return {'mode': 'records', 'numbers': numbers, 'truncated': cut or more}


# ---------------------------------------------------------------- reading the issues

def read_views(gh, repository, numbers):
    """What the rules need from each issue number: state, parent, sub-issues, linked pull requests and the
    acceptance-criteria counts. The board is never read. A number GitHub does not know comes back as None. A list
    that did not fit one page is named in `truncated`, because a value cut off would read as absent. The body is
    counted, never kept."""
    nodes = read_aliases(gh, repository, numbers, VIEW)
    return {n: None if node is None else parse_view(n, node, repository) for n, node in nodes.items()}


def parse_view(number, node, repository):
    truncated = []
    kids, short = page(node.get('subIssues'))
    children = []
    for kid in kids:
        if not valid_number(kid.get('number')):
            short = True
            continue
        state = kid.get('state')
        children.append({'number': kid['number'], 'state': state if isinstance(state, str) else None,
                         'external': other_repository(kid, repository)})
    if short:
        truncated.append('sub_issues')
    summary = node.get('subIssuesSummary') if isinstance(node.get('subIssuesSummary'), dict) else {}
    total = summary.get('total') if type(summary.get('total')) is int else len(children)
    completed = summary.get('completed') if type(summary.get('completed')) is int else sum(c['state'] == 'CLOSED' for c in children)
    opened = [c['number'] if c['external'] is None else f"{c['external']}#{c['number']}"
              for c in sorted(children, key=lambda c: (c['external'] is not None, c['number'])) if c['state'] != 'CLOSED']
    prs, _ = page(node.get('closedByPullRequestsReferences'))   # a cut list only hides a caution: never a reason to skip
    # Only the release pull request carries a closing keyword, and only for its `closes`; GitHub does not list the
    # other pull requests above: they show up as cross references (a pull request that merely cites the issue; an
    # issue that cites it has no number here).
    mentions, _ = page(node.get('timelineItems'))
    prs = prs + [event['source'] for event in mentions if isinstance(event.get('source'), dict)]
    linked, seen = [], set()
    for pr in prs:
        # a pull request of another repository that cites this issue is no pull request of this one
        if valid_number(pr.get('number')) and pr['number'] not in seen and not other_repository(pr, repository):
            seen.add(pr['number'])
            url = pr.get('url')
            linked.append({'number': pr['number'], 'state': rs.clean(pr['state']) if isinstance(pr.get('state'), str) else None,
                           'merged': pr.get('merged') is True,
                           'url': rs.clean(url) if isinstance(url, str) and url.startswith('https://') else None})
    counts, pending = scan(node.get('body'))
    parent = node.get('parent')
    state = node.get('state')
    reason = node.get('stateReason')
    return {'number': number, 'state': state if isinstance(state, str) else None,
            'stateReason': reason if isinstance(reason, str) else None, 'title': rs.clean(node.get('title') or ''),
            'criteria': None if counts is None else {'checked': counts[0], 'total': counts[1]},
            'pendingOutside': pending,
            'parent': parent['number'] if isinstance(parent, dict) and valid_number(parent.get('number')) else None,
            'parentRepository': other_repository(parent, repository) if isinstance(parent, dict) else None,
            'children': {'total': total, 'completed': completed, 'open': opened, 'nodes': children},
            'prs': linked, 'truncated': truncated}


# ---------------------------------------------------------------- release check

def valid_remote(name):
    """A remote name this helper will type into a ref: a plain branch-like name without a slash."""
    return valid_branch(name) and '/' not in name


def release_defaults(root, numbers, base, remote):
    """(base, remote, prefix) for the release check: the base given, else the `base.branch` of the newest
    authorization record whose `issue_ids` name one of `numbers` (else `main`); the remote given, else `origin`;
    the `branchPrefix` of the config, else the `branch_prefix` of the newest record that has a valid one (the legacy
    prefix of `_cli.branch_prefix` for a record without it), else None."""
    prefix = _cli.config_prefix(Path(root) / '.frontlights' / 'config.json')
    for path in reversed(authorization_records(root)):
        data = read_record(path)
        if not isinstance(data, dict):
            continue
        candidate = _cli.branch_prefix(record=data)[0]
        if prefix is None and isinstance(candidate, str) and candidate.endswith('/') and valid_branch(candidate[:-1]):
            prefix = candidate
        ids = data.get('issue_ids')
        branch = data.get('base', {}).get('branch') if isinstance(data.get('base'), dict) else None
        if (base is None and isinstance(ids, list) and any(n in ids for n in numbers) and valid_branch(branch)):
            base = branch
    return base or 'main', remote or 'origin', prefix


def release_check(root, numbers, base, remote):
    """({number: detail} for the issues whose branch is not yet in `<remote>/<base>`, status). The branch of an
    issue is the one its authorization records name (homolog.issue_branches) or, without one, `<prefix>issue-<n>`
    when that branch exists locally. Only `rev-parse` and `merge-base` run, through homolog, and nothing is
    written. Status: `checked` when at least one branch was compared with the remote ref, `unavailable` when Git
    could not answer at all (the root is not a repository, or Git is missing), `skipped` otherwise (no branch to
    compare, or no remote ref). A doubt never excludes an issue."""
    import homolog  # noqa: PLC0415  (lazy: homolog runs Git; this module itself never runs a command)
    base, remote, prefix = release_defaults(root, numbers, base, remote)
    found = {}
    try:
        homolog.worktree(root)
        remote_ref = f'refs/remotes/{remote}/{base}'
        if homolog.rev(root, remote_ref) is None:
            return found, 'skipped', base, remote
        mapping, _ = homolog.issue_branches(root)
        compared = False
        for number in numbers:
            branch = mapping.get(number, f'{prefix}issue-{number}' if prefix else None)
            tip = homolog.rev(root, f'refs/heads/{branch}') if branch else None
            if tip is None:
                continue   # already cleaned up, or never created: the helper cannot tell and does not block
            contained = homolog.ancestry(root, tip, remote_ref)
            compared = compared or contained is not None
            if contained is False:
                found[number] = {'branch': branch, 'tip': tip, 'base': base, 'remote': remote}
    except homolog.Refusal:
        return {}, 'unavailable', base, remote
    return found, 'checked' if compared else 'skipped', base, remote


# ---------------------------------------------------------------- eligibility

def issue_url(repository, number):
    return f'https://github.com/{repository}/issues/{number}'


def assess(views, repository, unreleased=None):
    """Split the scope: the candidates (in closing order, all open), the issues left out with the reason, and how
    many closed issues need nothing (a closed issue is never a candidate). `unreleased` maps the issues whose
    branch is not yet in the remote base to the detail of the `awaiting_release` reason."""
    unreleased = unreleased or {}
    memo = {}

    def cuts(view):
        return [] if view['state'] == 'CLOSED' else list(view['truncated'])

    def blockers(view, stack):
        """The open sub-issues that are not candidates in this batch."""
        blocking = []
        for child in sorted(view['children']['nodes'], key=lambda c: (c['external'] is not None, c['number'])):
            number = child['number']
            if child['external']:
                if child['state'] != 'CLOSED':
                    blocking.append(f"{child['external']}#{number}")
                continue
            own = views.get(number)
            state = own['state'] if own is not None else child['state']
            if state == 'CLOSED' or (own is not None and number not in stack and verdict(number, stack)[0] == 'ok'):
                continue
            blocking.append(number)
        return blocking

    def verdict(number, stack=()):
        if number in memo:
            return memo[number]
        view = views.get(number)
        if view is None:
            result = ('not_found', {})
        elif view['state'] not in ('OPEN', 'CLOSED'):
            result = ('unreadable', {})
        elif cuts(view):
            result = ('truncated', {'lists': cuts(view)})
        elif view['state'] == 'CLOSED':
            result = ('closed', {})
        else:
            counts = view['criteria']
            blocking = blockers(view, stack + (number,))
            if blocking:
                result = ('open_children', {'openChildren': blocking, 'criteria': counts})
            elif counts is None or counts['total'] == 0:
                result = ('no_criteria', {'criteria': counts})
            elif counts['checked'] < counts['total']:
                result = ('unchecked_criteria', {'criteria': counts})
            elif number in unreleased:
                result = ('awaiting_release', dict(unreleased[number]))
            else:
                result = ('ok', {})
        memo[number] = result
        return result

    def candidate(view):
        """An open issue to close. Its card is never read nor moved: the board's "Item closed" workflow moves it."""
        number = view['number']
        level = 'top' if view['parent'] is None else 'sub'
        cautions = []
        if any(pr['state'] == 'OPEN' for pr in view['prs']):
            cautions.append('open_pr')
        elif not view['prs']:
            cautions.append('no_pr')
        if view['pendingOutside']:
            cautions.append('pending_outside_criteria')
        url = issue_url(repository, number)
        commands = [{'kind': 'close', 'argv': ['gh', 'issue', 'close', str(number), '--repo', repository,
                                               '--reason', 'completed']}]
        return {'number': number, 'title': view['title'], 'url': url, 'level': level, 'parent': view['parent'],
                'criteria': view['criteria'], 'pendingOutside': view['pendingOutside'],
                'parentTicks': None,
                'children': {key: view['children'][key] for key in ('total', 'completed', 'open')},
                'state': view['state'], 'action': 'close',
                'prs': view['prs'], 'cautions': cautions, 'commands': commands}

    found, excluded, already = {}, [], 0
    for number in sorted(views):
        view = views[number]
        kind, detail = verdict(number)
        if kind == 'ok':
            found[number] = candidate(view)
        elif kind == 'closed':
            already += 1
        else:
            excluded.append({'number': number, 'title': view['title'] if view else None, 'reason': kind, **detail})
    ordered = [found[n] for n in closing_order(found, views)]
    for position, record in enumerate(ordered, 1):
        record['order'] = position
    return ordered, excluded, already


def add_parent_ticks(gh, repository, ordered, views):
    """Give every sub-issue that will be closed the `parentTicks` of its open parent: the items of the parent's
    body that cite it. A parent in another repository, a closed one or one GitHub does not know has none."""
    wanted = sorted({c['parent'] for c in ordered
                     if c['level'] == 'sub' and c['state'] == 'OPEN' and not views[c['number']]['parentRepository']})
    nodes = read_aliases(gh, repository, wanted, 'number state body') if wanted else {}
    for candidate in ordered:
        node = nodes.get(candidate['parent'])
        if (candidate['level'] != 'sub' or candidate['state'] != 'OPEN' or views[candidate['number']]['parentRepository']
                or not isinstance(node, dict) or node.get('state') != 'OPEN'):
            continue
        lines, shared = citing_items(node.get('body'), candidate['number'], repository)
        if lines or shared:
            candidate['parentTicks'] = {'parent': candidate['parent'], 'lines': lines, 'shared': shared}


def closing_order(found, views):
    """Sub-issues before their parent, otherwise by number (a stable topological order)."""
    waiting = {n: 0 for n in found}
    parents = {n: [] for n in found}
    for parent in found:
        for child in {c['number'] for c in views[parent]['children']['nodes'] if not c['external']}:
            if child in found and child != parent:
                waiting[parent] += 1
                parents[child].append(parent)
    ready = [n for n, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        number = heapq.heappop(ready)
        order.append(number)
        for parent in parents[number]:
            waiting[parent] -= 1
            if waiting[parent] == 0:
                heapq.heappush(ready, parent)
    return order + sorted(set(found) - set(order))


# ---------------------------------------------------------------- closing keyword of the release

def default_branch(gh, repository):
    """The repository's default branch as GitHub names it, or None when the answer carries no plain name."""
    owner, name = repository.split('/')
    data = rs.graphql(gh, 'query { repository(owner: "%s", name: "%s") { defaultBranchRef { name } } }' % (owner, name))
    branch = (data.get('repository') or {}).get('defaultBranchRef')
    value = branch.get('name') if isinstance(branch, dict) else None
    return value if isinstance(value, str) and valid_branch(value) else None


def keyword_verdict(view):
    """True when the release pull request may carry `Closes #n` for this issue: open, of the top level, every box of
    its acceptance criteria ticked, no open sub-issue and no open leftover outside the criteria; otherwise the
    reason. A sub-issue, an open box or a leftover outside never closes by keyword: it follows the closing question."""
    if view is None:
        return 'not_found'
    if view['state'] != 'OPEN':
        return 'not_open'
    if view['truncated']:
        return 'truncated'
    if view['parent'] is not None:
        return 'sub_issue'
    if view['children']['open']:
        return 'open_children'
    counts = view['criteria']
    if counts is None or counts['total'] == 0:
        return 'no_criteria'
    if counts['checked'] < counts['total']:
        return 'unchecked_criteria'
    if view['pendingOutside']:
        return 'pending_outside'
    return True


def release_keywords(gh, repository, numbers, base):
    """(default branch, {number: what the release plan shows of it}) for the issues of a release into `base`. GitHub
    closes by keyword only on a merge into the default branch, so with another base the issues are not read
    ({}). Read only: one GraphQL read of the default branch and `read_views` of the issues."""
    default = default_branch(gh, repository)
    if default is None or default != base:
        return default, {}
    views = read_views(gh, repository, sorted(numbers))
    found = {}
    for number in sorted(numbers):
        view = views.get(number)
        entry = {'closing': keyword_verdict(view)}
        if view is not None:
            entry.update(state=view['state'], level='top' if view['parent'] is None else 'sub', parent=view['parent'],
                         criteria=view['criteria'], openChildren=view['children']['open'],
                         pendingOutside=view['pendingOutside'])
        found[number] = entry
    return default, found


# ---------------------------------------------------------------- operations

def load_repository(config):
    """The project's configuration as a dict, and its `repository`, which must be `owner/name`."""
    try:
        data = frontlights.load(config)
    except OSError:
        raise Refusal('the configuration file could not be read; pass --config <.frontlights/config.json>')
    except ValueError:
        raise Refusal('the configuration file is not valid JSON')
    require(isinstance(data, dict), 'the configuration file must hold a JSON object')
    repository = data.get('repository')
    require(repository is not None, 'This project has no GitHub repository (repository is null in the configuration), '
                                    'so there are no GitHub issues to close.')
    require(frontlights.repository(repository), 'repository in the configuration must be owner/name')
    return data, repository


def load_project(config):
    """The repository (`owner/name`) of the project's configuration file. The `project` block is still validated,
    so a broken configuration is refused here as everywhere else, but the board is never read."""
    data, repository = load_repository(config)
    frontlights.board(data.get('project'), repository)
    return repository


def op_candidates(config, root='.', explicit=None, all_flag=False, gh=None, base=None, remote=None):
    """Read only: the issues that can be closed now, with the commands to type once the
    user approves, in closing order; the issues left out and why (an issue whose branch is not yet in
    `<remote>/<base>` waits for the release)."""
    gh = gh or rs.gh_default
    repository = load_project(config)
    numbers = None if explicit is None else parse_numbers(explicit)
    require(not (all_flag and numbers is not None), '--issues and --all cannot be used together; choose one')
    require(base is None or valid_branch(base), '--base must be a plain branch name')
    require(remote is None or valid_remote(remote), '--remote must be a plain remote name, such as origin')
    scope = scope_numbers(root, numbers, all_flag, gh, repository)
    result = {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'scope': scope,
              'candidates': [], 'excluded': [], 'alreadyDone': 0,
              'releaseCheck': 'skipped', 'ask': False}
    if not scope['numbers']:
        result['message'] = ('O repositório não tem issue aberta: nada a fechar.' if scope['mode'] == 'all' else
                             'Nenhuma issue foi trabalhada neste projeto (sem pasta em .frontlights/issues, sem id em '
                             'registro de autorização ou de plano): nada a fechar. Nomeie as issues com --issues 12,13 '
                             'ou leia todas as abertas com --all.')
        return result
    views = read_views(gh, repository, scope['numbers'])
    open_numbers = [n for n, view in sorted(views.items()) if view is not None and view['state'] == 'OPEN']
    unreleased, release_status, _, _ = release_check(root, open_numbers, base, remote)
    ordered, excluded, already = assess(views, repository, unreleased)
    add_parent_ticks(gh, repository, ordered, views)
    result.update(candidates=ordered, excluded=excluded, alreadyDone=already, ask=bool(ordered), releaseCheck=release_status)
    parts = [f'{len(ordered)} issue(s) podem ser fechadas.' if ordered else 'Nenhuma issue pronta para fechar.']
    pending = [c['number'] for c in ordered if c['pendingOutside']]
    if pending:
        parts.append('Pendências abertas fora dos critérios de aceitação em ' + ', '.join(f'#{n}' for n in pending)
                     + ' (pendingOutside): avise o usuário antes de fechá-las.')
    ticks = [c['number'] for c in ordered if c['parentTicks'] and c['parentTicks']['lines']]
    if ticks:
        parts.append('Sub-issue(s) ' + ', '.join(f'#{n}' for n in ticks)
                     + ' têm item a marcar no pai (parentTicks): mostre as linhas e pergunte.')
    waiting = [e['number'] for e in excluded if e['reason'] == 'awaiting_release']
    if waiting:
        parts.append('Issue(s) ' + ', '.join(f'#{n}' for n in waiting) + ' esperam a release (awaiting_release): '
                     'a branch ainda não está na base remota; ofereça a release, não as feche.')
    if excluded:
        parts.append(f'{len(excluded)} de fora (o motivo de cada uma em excluded).')
    if already:
        parts.append(f'{already} issue(s) já fechada(s), nada a fazer.')
    if scope['truncated']:
        parts.append('O escopo foi cortado (scope.truncated); nomeie as issues com --issues para ver o resto.')
    if ordered:
        parts.append('Nada foi escrito. Pergunte ao usuário, rode os comandos na ordem e confira depois.')
    result['message'] = ' '.join(part for part in parts if part)
    return result


def op_verify(config, root='.', explicit=None, gh=None):
    """Read only: for each issue, whether it is closed (`ok`). The board is not read: the board's "Item closed"
    workflow moves the card to Done, not this session."""
    gh = gh or rs.gh_default
    repository = load_project(config)
    require(explicit is not None and explicit != '' and explicit != [],
            'verify needs the issues to check: pass --issues 12,13')
    numbers = parse_numbers(explicit)
    require(len(numbers) <= MAX_ALL, f'name at most {MAX_ALL} issues')
    views = read_views(gh, repository, numbers)
    entries = []
    for number in numbers:
        view = views[number]
        if view is None:
            entries.append({'number': number, 'state': None, 'stateReason': None, 'closed': False, 'ok': False,
                            'reason': 'not_found'})
            continue
        closed = view['state'] == 'CLOSED'
        entries.append({'number': number, 'state': view['state'], 'stateReason': view['stateReason'],
                        'closed': closed, 'ok': closed})
    waiting = [e['number'] for e in entries if not e['ok']]
    message = (f'Todas as {len(entries)} issue(s) estão fechadas.' if not waiting else
               f'{len(waiting)} de {len(entries)} issue(s) ainda não estão fechadas: ' + ', '.join(f'#{n}' for n in waiting) + '.')
    return {'ok': not waiting, 'exitCode': 0 if not waiting else 1, 'project': repository, 'repository': repository,
            'issues': entries, 'message': message}


def read_pull_requests(gh, repository, numbers):
    """({number: GraphQL node, or None for a number GitHub does not know}, the repository's default branch)."""
    owner, name = repository.split('/')
    nodes, default = {}, None
    for start in range(0, len(numbers), rs.GAPS_BATCH):
        chunk = numbers[start:start + rs.GAPS_BATCH]
        body = ' '.join(f'p{n}: pullRequest(number: {n}) {{ {PR_VIEW} }}' for n in chunk)
        data = rs.graphql(gh, 'query { repository(owner: "%s", name: "%s") { defaultBranchRef { name } %s } }'
                          % (owner, name, body), missing_ok={f'p{n}' for n in chunk})
        repo = data.get('repository') or {}
        branch = repo.get('defaultBranchRef')
        default = branch.get('name') if isinstance(branch, dict) and isinstance(branch.get('name'), str) else default
        for n in chunk:
            value = repo.get(f'p{n}')
            nodes[n] = value if isinstance(value, dict) else None
    return nodes, default


def pull_request_entry(number, node, expected):
    """What the session needs from one pull request: `status` is `open`, `merged_into_base` (the only one that
    lets an issue be proposed for closing), `merged_elsewhere` (merged into a branch that is not the approved
    base), `closed_unmerged`, `not_found` or `unknown`."""
    if node is None:
        return {'number': number, 'status': 'not_found'}
    state = node.get('state') if isinstance(node.get('state'), str) else None
    base = node.get('baseRefName') if isinstance(node.get('baseRefName'), str) else None
    merged = state == 'MERGED' or node.get('merged') is True
    status = ('open' if state == 'OPEN' else
              ('merged_into_base' if base == expected else 'merged_elsewhere') if merged else
              'closed_unmerged' if state == 'CLOSED' else 'unknown')
    head = node.get('headRefOid')
    url = node.get('url')
    word = lambda key: node[key] if isinstance(node.get(key), str) and re.fullmatch(r'[A-Z_]{1,40}', node[key]) else None
    review, merge_state, mergeable = word('reviewDecision'), word('mergeStateStatus'), word('mergeable')
    reasons = []
    if status == 'open':
        if review in BLOCKING_REVIEW:
            reasons.append(f'reviewDecision {review}')
        if merge_state in BLOCKING_STATE:
            reasons.append(f'mergeStateStatus {merge_state}')
        if mergeable == 'CONFLICTING':
            reasons.append('mergeable CONFLICTING')
    return {'number': number, 'status': status, 'state': state, 'merged': merged,
            'reviewDecision': review, 'mergeStateStatus': merge_state, 'mergeable': mergeable,
            'isDraft': node.get('isDraft') is True, 'blocked': bool(reasons), 'blockedBy': reasons,
            'mergedAt': rs.clean(node['mergedAt'], 40) if isinstance(node.get('mergedAt'), str) else None,
            'base': rs.clean(base, 200) if base else None,
            'head': rs.clean(node['headRefName'], 200) if isinstance(node.get('headRefName'), str) else None,
            'headOid': head if isinstance(head, str) and re.fullmatch(r'[0-9a-f]{40,64}', head) else None,
            'url': rs.clean(url) if isinstance(url, str) and url.startswith('https://') else None}


def op_merge_status(config, prs, base=None, gh=None):
    """Read only: where each named pull request stands, against the approved base."""
    gh = gh or rs.gh_default
    repository = load_project(config)
    require(prs is not None and prs != '' and prs != [], 'merge-status needs the pull requests to check: pass --prs 12,13')
    numbers = parse_numbers(prs, 'pull request numbers must be positive integers, as in --prs 12,13')
    require(len(numbers) <= MAX_ALL, f'name at most {MAX_ALL} pull requests')
    require(base is None or valid_branch(base), '--base must be a plain branch name')
    nodes, default = read_pull_requests(gh, repository, numbers)
    expected = base or default
    require(isinstance(expected, str) and valid_branch(expected),
            'the approved base is unknown: pass --base <branch> (the repository default could not be read)')
    entries = [pull_request_entry(n, nodes[n], expected) for n in numbers]
    by = lambda status: [e['number'] for e in entries if e['status'] == status]
    ready, waiting = by('merged_into_base'), by('open')
    others = [e['number'] for e in entries if e['status'] not in ('merged_into_base', 'open')]
    parts = [f'{len(ready)} de {len(entries)} PR(s) mesclada(s) em {rs.clean(expected, 200)}.']
    if waiting:
        parts.append('Ainda abertas: ' + ', '.join(f'#{n}' for n in waiting) + '.')
    if others:
        parts.append('Mescladas noutra branch, fechadas sem merge ou desconhecidas: ' + ', '.join(f'#{n}' for n in others)
                     + '; as issues delas não são propostas para fechar.')
    blocked = [e['number'] for e in entries if e.get('blocked')]
    if blocked:
        parts.append('Bloqueadas (revisão ou estado de merge): ' + ', '.join(f'#{n}' for n in blocked)
                     + '; uma PR bloqueada nunca é oferecida para mesclar.')
    return {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'expectedBase': expected,
            'baseSource': 'argument' if base else 'default_branch', 'pullRequests': entries, 'ready': ready,
            'waiting': waiting, 'blocked': blocked, 'settled': not waiting, 'message': ' '.join(parts)}


def read_body_file(path):
    """The text of a local file, for tick-check: UTF-8, a regular file, and no larger than a record."""
    file = Path(path) if isinstance(path, (str, os.PathLike)) and str(path) else None
    require(file is not None and file.is_file(), f'tick-check could not read {rs.clean(str(path), 200)}: pass an existing file')
    require(file.stat().st_size <= MAX_RECORD_BYTES, 'tick-check reads files of up to 2 MiB')
    try:
        return file.read_bytes().decode('utf-8')
    except UnicodeDecodeError:
        raise Refusal(f'{rs.clean(file.name, 100)} is not UTF-8 text')


def op_tick_check(before, after, lines):
    """Local files only: `after` must be `before` with, on the listed lines and nowhere else, the `[ ]` of an
    open checklist item turned into `[x]`. Line endings and the empty lines at the end are not compared, only the
    lines."""
    require(before and after, 'tick-check needs the saved body and the new one: pass --before and --after')
    require(lines is not None and lines != '' and lines != [], 'tick-check needs the lines that were ticked: pass --lines 14,22')
    wanted = parse_numbers(lines, 'line numbers must be positive integers, as in --lines 14,22')
    return compare_ticks(read_body_file(before), read_body_file(after), wanted)


def body_lines(text):
    """The lines of a body, whatever its line endings, without the empty lines at its end: a reread through
    `--jq .body` or a redirect adds a final newline, and that is not a change of the body."""
    lines = re.split(r'\r\n|\r|\n', text)
    while len(lines) > 1 and lines[-1] == '':
        lines.pop()
    return lines


def compare_ticks(before, after, wanted):
    """The tick-check of two bodies held in memory: `after` is `before` with only the `[ ]` of the open items on
    the `wanted` lines turned into `[x]`."""
    old, new = body_lines(before), body_lines(after)
    problems = []
    if len(old) != len(new):
        problems.append({'reason': 'line_count', 'before': len(old), 'after': len(new)})
    else:
        for number, (x, y) in enumerate(zip(old, new), 1):
            if number in wanted:
                item = ITEM.match(x)
                if not item or item.group(1) != ' ':
                    problems.append({'line': number, 'reason': 'not_an_open_item'})
                elif y != x[:item.start(1)] + 'x' + x[item.end(1):]:
                    problems.append({'line': number, 'reason': 'not_ticked_exactly'})
            elif x != y:
                problems.append({'line': number, 'reason': 'changed_outside_the_ticks'})
        problems += [{'line': n, 'reason': 'line_out_of_range'} for n in wanted if n > len(old)]
    total = len(problems)
    ok = not problems
    return {'ok': ok, 'exitCode': 0 if ok else 1, 'lines': wanted, 'problems': problems[:20], 'problemCount': total,
            'message': (f'Só os {len(wanted)} item(ns) listado(s) foram marcados.' if ok else
                        f'{total} problema(s): o corpo novo não é o guardado com só esses itens marcados; '
                        'não o escreva (ou, se já foi escrito, mostre a diferença e pergunte).')}


# ---------------------------------------------------------------- tick: the one write

class TickRefusal(Refusal):
    """A refusal of `tick` after its inputs were accepted, with the reason the session reads."""

    def __init__(self, reason, message, hint=None, **extra):
        super().__init__(message)
        self.reason, self.hint, self.extra = reason, hint, extra


def gh_write(argv):
    """Run a `gh` write without a shell: the edit of an issue body, from a literal file. Its output is never
    repeated, because it could carry anything."""
    try:
        done = subprocess.run([*rs.GH_COMMAND, *argv], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=rs.GH_TIMEOUT, stdin=subprocess.DEVNULL, env=rs.gh_environment())
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal('gh could not run the edit (not installed, or it did not answer in time)')
    require(done.returncode == 0, 'gh refused the edit of the issue body; check the active account and the repository access')


def read_issue_body(gh, repository, number):
    """The body of an issue exactly as GitHub holds it (`gh issue view --json body`: no final newline added)."""
    answer = gh(['issue', 'view', str(number), '--repo', repository, '--json', 'body'])
    body = answer.get('body') if isinstance(answer, dict) else None
    require(isinstance(body, str), f'GitHub gave no body text for issue #{number}')
    require(len(body.encode('utf-8')) <= MAX_RECORD_BYTES, f'the body of issue #{number} is larger than 2 MiB')
    return body


def indentation(text):
    expanded = text.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(' '))


def parse_box(value):
    """(kind, number) of --box: `S2`, `s2` and `2` are the slice box S2; `P1` (or `p1`) the first leftover box."""
    match = BOX.fullmatch(str(value).strip())
    require(match is not None, 'the box is the slice label or the leftover label, as in --box S2, 2 or P1')
    return (match.group(1) or 'S').upper(), int(match.group(2))


def find_box(body, box, line, kind='S'):
    """(line number, ticked) of the one checklist item of the acceptance-criteria section to tick: the one whose
    text starts with `S<box>.`, the `box`-th one whose text starts with `Pendência` (kind `P`), or the one on
    `line`. Fenced code and HTML comments never count."""
    visible = list(sections(body))
    found, leftovers = [], 0
    for number, text, section, heading in visible:
        item = ITEM.match(text) if section == 'criteria' and not heading else None
        if not item:
            continue
        if line is not None:
            if number == line:
                found.append((number, item))
            continue
        rest = text[item.end():].lstrip(' \t')
        if kind == 'P':
            if LEFTOVER.match(rest):
                leftovers += 1
                if leftovers == box:
                    found.append((number, item))
            continue
        label = BOX_LABEL.match(rest)
        if label and int(label.group(1)) == box:
            found.append((number, item))
    name = f'box {kind}{box}' if line is None else f'line {line}'
    if not found:
        raise TickRefusal('box_not_found' if line is None else 'not_a_criterion',
                          f'The {name} is not a checklist item of the acceptance-criteria section of the issue '
                          '(fenced code and comments do not count); nothing was written.')
    if len(found) > 1:
        raise TickRefusal('box_ambiguous', f'{len(found)} items of the acceptance criteria start with {kind}{box}. '
                          f'(lines {", ".join(str(n) for n, _ in found)}); tick the right one with --line; nothing was written.')
    number, item = found[0]
    raw = re.split(r'\r\n|\r|\n', body)[number - 1]
    same = ITEM.match(raw)
    # a comment that opens or closes before the box means the raw line's first box may be another one, hidden in
    # the comment: the tick is then refused, never placed on the wrong box
    if (same is None or same.group(1) != item.group(1) or same.start(1) != item.start(1)
            or '-->' in raw[:same.start(1)] or '<!--' in raw[:same.start(1)]):
        raise TickRefusal('not_an_open_item', f'The {name} (line {number}) is not a plain checklist line; nothing was written.')
    if item.group(1) == ' ':
        own = indentation(raw)
        shown = {n: (text, heading) for n, text, _, heading in visible}
        lines = re.split(r'\r\n|\r|\n', body)
        gap = False
        for later in range(number + 1, len(lines) + 1):
            whole = lines[later - 1]
            if not whole.strip():
                gap = True
                continue
            text, heading = shown.get(later, (None, False))
            # the box's sub-items run to the next heading, the next list item that is not deeper than the box, or
            # anything not deeper than the box after an empty line (a paragraph, a table, a rule, a fence); a line
            # glued to the one before it is a continuation of the item (lazy or not) and does not end it
            if heading or (indentation(whole) <= own and (gap or LIST_ITEM.match(whole))):
                break
            gap = False
            if text and LIST_ITEM.match(text) and BLOCKED.match(plain(text)):
                raise TickRefusal('blocked_line', f'The {name} (line {number}) still has its "- Bloqueada:" line (line '
                                  f'{later}): remove that line first (the write rule of the leftover), then tick; '
                                  'nothing was written.', blockedLine=later)
    return number, item.group(1) != ' '


def save_body(folder, kind, stamp, text):
    """A new file `body-<kind>-<stamp>.md` holding the body's exact bytes; an existing name is never overwritten."""
    for attempt in range(1, 100):
        path = folder / (f'body-{kind}-{stamp}' + ('' if attempt == 1 else f'-{attempt}') + '.md')
        try:
            with open(path, 'xb') as file:
                file.write(text.encode('utf-8'))
            return path
        except FileExistsError:
            continue
    raise Refusal(f'tick could not find a free name for body-{kind}-{stamp}.md')


WALKTHROUGH_SECTIONS = ('antes', 'depois')
SLICE_EVIDENCE_APPROVED = ('aprovado',)   # the answer "Aprovado" of the watched run; "Pode prosseguir" does not tick


def walkthrough_problems(text):
    """What a walkthrough file of a box without a screen lacks (references/development.md, "Into the local main",
    step 3): a header before `## Antes`, then `## Antes` and `## Depois` in that order, each with a fenced block."""
    problems, current, found, header, fence = [], None, {}, False, False
    for raw in text.splitlines():
        heading = HEADING.match(raw) if not fence else None
        if heading and len(heading.group(1)) == 2:
            name = plain(heading.group(2) or '')
            current = name if name in WALKTHROUGH_SECTIONS else None
            if current:
                found.setdefault(current, False)
            continue
        if FENCE.match(raw):
            fence = not fence
            if current:
                found[current] = True
            continue
        if current is None and not found and raw.strip():
            header = True
    if not header:
        problems.append('sem cabeçalho (issue, caixa, persona, data, passos, base e commit) antes de ## Antes')
    for name in WALKTHROUGH_SECTIONS:
        if name not in found:
            problems.append(f'sem a seção ## {name.capitalize()}')
        elif not found[name]:
            problems.append(f'a seção ## {name.capitalize()} não tem a saída num bloco de código')
    if list(found)[:2] == ['depois', 'antes']:
        problems.append('## Depois vem antes de ## Antes')
    return problems


ROTEIRO_SEM_TELA = re.compile(r'roteiro\s*:\s*sem tela\b')


def slice_boxes(body):
    """[{'label': 'S<k>', 'line', 'ticked', 'semTela'}] for the slice boxes of the acceptance-criteria section, in
    order: `semTela` when a sub-item of the box says `Roteiro: sem tela` (the persona of a box without a screen)."""
    boxes = []
    for number, text, section, heading in sections(body):
        if heading or section != 'criteria':
            continue
        item = ITEM.match(text)
        label = BOX_LABEL.match(text[item.end():].lstrip(' \t')) if item else None
        if label:
            boxes.append({'label': f'S{int(label.group(1))}', 'line': number, 'ticked': item.group(1) != ' ',
                          'semTela': False})
        elif item:
            boxes.append({'label': None, 'line': number, 'ticked': item.group(1) != ' ', 'semTela': False})
        elif boxes and ROTEIRO_SEM_TELA.search(plain(text)):
            boxes[-1]['semTela'] = True
    return [box for box in boxes if box['label']]


def slice_evidence(root, number, label, record=None):
    """The evidence that lets slice box `label` (S<k>) be ticked, or a TickRefusal: the watched run approved, or the
    walkthrough of the box without a screen in its format."""
    folder = Path(root) / '.frontlights' / 'issues' / str(number)
    result_file = Path(record) if record else folder / 'browser' / 'result.json'
    walkthrough = folder / 'walkthroughs' / f'{label}.md'
    data = read_record(result_file) if result_file.is_file() else None
    seen = None
    if isinstance(data, dict):
        seen = data.get('situacao') if data.get('situacao') is not None else data.get('aprovacao')
        if seen in SLICE_EVIDENCE_APPROVED:
            return {'kind': 'teste assistido', 'path': str(result_file), 'situacao': seen}
    problems = None
    if walkthrough.is_file():
        try:
            problems = walkthrough_problems(walkthrough.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeDecodeError):
            problems = ['ilegível']
        if not problems:
            return {'kind': 'roteiro sem tela', 'path': str(walkthrough)}
    detail = f'; o roteiro {walkthrough.name} está fora do formato: {"; ".join(problems)}' if problems else ''
    raise TickRefusal('no_evidence',
                      f'A caixa {label} da issue #{number} só é marcada com o teste assistido aprovado '
                      f'({result_file.name}: {seen or "sem registro"}) ou, sem tela, com '
                      f'walkthroughs/{label}.md no formato{detail}; nada foi escrito.',
                      hint='caixa com tela: espere o "Aprovado" do teste assistido; sem tela: rode o roteiro da caixa '
                           'e grave walkthroughs/S<k>.md (cabeçalho, ## Antes, ## Depois, cada um com a saída num '
                           'bloco de código)')


def op_tick(config, root, issue, box, line, gh=None, edit=None, account=None, record=None, comment_file=None):
    """Tick one box of an issue's acceptance criteria and check the reread (see the module's docstring). `account`,
    given by the command line, checks the gh login and repository against the config before anything is read
    (`_cli.gh_account`: `account_mismatch` or `repository_mismatch`, with the question to ask)."""
    require(isinstance(issue, (str, int)) and NUMBER.fullmatch(str(issue).strip()) and valid_number(int(str(issue).strip())),
            'tick needs one issue number: pass --issue 12')
    number = int(str(issue).strip())
    require((box is None) != (line is None), 'tick needs exactly one of --box S<k> (a slice box) or --line <N> (any '
                                             'criterion of the section)')
    kind = 'S'
    if box is not None:
        kind, box = parse_box(box)
    else:
        require(NUMBER.fullmatch(str(line).strip()) and int(str(line).strip()) > 0,
                'the line is a positive line number of the body, as in --line 14')
        line = int(str(line).strip())
    data, repository = load_repository(config)
    if account is not None:
        try:
            account(data)
        except _cli.AccountMismatch as mismatch:
            return mismatch.result(repository=repository, issue=number, written=False)
    records = Path(root) / '.frontlights'
    require(records.is_dir(), 'tick keeps the previous body in .frontlights/issues/<n>/ of the project: pass --root, '
                              'the folder that holds .frontlights')
    if comment_file is not None:
        require(Path(comment_file).is_file(), f'--comment-file {rs.clean(str(comment_file), 200)} is not a file')
    gh, edit = gh or rs.gh_default, edit or gh_write
    label = None if box is None else f'{kind}{box}'
    result = {'repository': repository, 'issue': number, 'box': label, 'line': line, 'written': False,
              'alreadyTicked': False, 'verified': False, 'files': {}}
    try:
        if kind == 'S' and box is not None:   # a slice box is ticked only with its evidence, before any read
            result['evidence'] = slice_evidence(root, number, label, record)
        before = read_issue_body(gh, repository, number)
        line, ticked = find_box(before, box, line, kind)
        if box is None:   # a line: the guard holds when that line is a slice box
            raw = re.split(r'\r\n|\r|\n', before)[line - 1]
            item = ITEM.match(raw)
            named = BOX_LABEL.match(raw[item.end():].lstrip(' \t')) if item else None
            if named and not ticked:
                result['evidence'] = slice_evidence(root, number, f'S{named.group(1)}', record)
    except TickRefusal as refusal:
        failure = {**result, **refusal.extra, 'ok': False, 'exitCode': 1, 'reason': refusal.reason,
                   'message': str(refusal)}
        if refusal.hint:
            failure['hint'] = refusal.hint
        return failure
    result['line'] = line
    name = f'caixa {label} (linha {line})' if label else f'linha {line}'
    if ticked:
        counts = criteria(before)
        return {**result, 'ok': True, 'exitCode': 0, 'alreadyTicked': True,
                'criteria': {'checked': counts[0], 'total': counts[1]},
                'message': f'A {name} da issue #{number} já estava marcada; nada foi escrito.'}
    parts = re.split(r'(\r\n|\r|\n)', before)
    raw = parts[2 * (line - 1)]
    item = ITEM.match(raw)
    parts[2 * (line - 1)] = raw[:item.start(1)] + 'x' + raw[item.end(1):]
    new = ''.join(parts)
    check = compare_ticks(before, new, [line])
    require(check['ok'], f'tick built a body that is not the saved one with just the {name} ticked; nothing was written')
    folder = records / 'issues' / str(number)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    files = result['files']
    files['before'] = str(save_body(folder, 'before', stamp, before))
    files['new'] = str(save_body(folder, 'new', stamp, new))
    failure = None
    try:
        edit(['issue', 'edit', str(number), '--repo', repository, '--body-file', files['new']])
    except Refusal as error:
        failure = str(error)
    try:
        after = read_issue_body(gh, repository, number)
    except Refusal as error:
        return {**result, 'ok': False, 'exitCode': 1, 'written': None if failure else True,
                'message': f'{failure + "; " if failure else ""}a releitura falhou ({error}): capture o corpo de novo e '
                           f'rode o tick-check contra {files["before"]} com --lines {line} antes de qualquer outra coisa.'}
    check = compare_ticks(before, after, [line])
    counts = criteria(after) or (0, 0)
    result['criteria'] = {'checked': counts[0], 'total': counts[1]}
    try:
        files['after'] = str(save_body(folder, 'after', stamp, after))
        kept = ''
    except (OSError, Refusal):
        files['after'] = None
        kept = ' A releitura não pôde ser guardada na pasta dos registros; capture-a de novo antes de mostrar uma diferença.'
    if check['ok']:
        note = ' O gh relatou falha, mas a releitura mostra a marcação.' if failure else ''
        result['commented'] = None
        if comment_file is not None:   # the comment goes with the tick (covered: commenting on the issue)
            try:
                edit(['issue', 'comment', str(number), '--repo', repository, '--body-file', str(comment_file)])
                result['commented'] = True
            except Refusal as error:
                result['commented'] = False
                note += f' O comentário não foi publicado ({error}); publique-o de novo com gh issue comment.'
        return {**result, 'ok': True, 'exitCode': 0, 'written': True, 'verified': True,
                'message': f'A {name} da issue #{number} foi marcada, e a releitura confere.{note}{kept}'}
    if failure and body_lines(after) == body_lines(before):
        return {**result, 'ok': False, 'exitCode': 1,
                'message': f'{failure}. O GitHub ainda tem o corpo guardado, nada mudou; tente de novo.{kept}'}
    if failure:
        return {**result, 'ok': False, 'exitCode': 1, 'written': None, 'problems': check['problems'],
                'problemCount': check['problemCount'],
                'message': f'{failure}, e o GitHub tem agora um corpo da issue #{number} que não é o guardado nem '
                           f'o marcado: alguém pode tê-lo editado. Mostre a diferença ({files["before"]} e a releitura) '
                           f'e pergunte; nada é reescrito.{kept}'}
    return {**result, 'ok': False, 'exitCode': 1, 'written': True, 'problems': check['problems'],
            'problemCount': check['problemCount'],
            'message': f'A releitura da issue #{number} não é o corpo guardado com só a {name} marcada: mostre a '
                       f'diferença ({files["before"]} e {files["after"] or "a releitura"}) e pergunte; restaurar o corpo '
                       f'guardado é uma escrita própria, com aprovação própria.{kept}'}


# ---------------------------------------------------------------- run and apply: the closing by a stamped list

LIST_MARK = 'frontlights-closeout'
LIST_BLOCK = re.compile(r'<!-- ' + LIST_MARK + r'\n(.*?)\n-->', re.S)
ANSWERS = ('Sim, fechar tudo', 'Escolher quais', 'Só fechar, sem marcar', 'Não agora')
MAX_LISTS = 200          # closeout-*.md files apply looks at for the stamp


def sha12(data):
    import hashlib  # noqa: PLC0415
    return hashlib.sha256(data).hexdigest()[:12]


def list_path(root):
    """`<root>/.frontlights/closeout-<AAAAMMDD-HHMMSS>[-k].md`, São Paulo time, never an existing name."""
    folder = Path(root) / '.frontlights'
    stamp = _cli.sao_paulo_now().strftime('%Y%m%d-%H%M%S')
    for attempt in range(1, 100):
        path = folder / (f'closeout-{stamp}' + ('' if attempt == 1 else f'-{attempt}') + '.md')
        if not path.exists():
            return path
    raise Refusal('no free name for the closeout list')


def cell(text):
    return rs.clean(str(text), 120).replace('|', '/')


def render_list(found, ticks):
    """The Portuguese table of the stamped list, the commands that will run, and the machine block apply rereads."""
    lines = ['# Fechamento de issues', '',
             f'Lista gerada em {_cli.sao_paulo_now().strftime("%d/%m/%Y %H:%M")} (horário de São Paulo) por '
             '`closeout.py run`. Só o que está aqui é aprovado; `closeout.py apply` recalcula e recusa se a lista mudou.',
             '', '| Ordem | Issue | Título | Nível | Critérios | Filhas | PRs | Avisos |',
             '|---|---|---|---|---|---|---|---|']
    for c in found['candidates']:
        criteria = c['criteria'] or {}
        children = c['children']
        prs = ', '.join(f"#{pr['number']}{' (aberta)' if pr['state'] == 'OPEN' else ''}" for pr in c['prs']) or 'nenhuma'
        notes = [{'open_pr': 'PR aberta', 'no_pr': 'sem PR', 'pending_outside_criteria':
                  f"fecha com {c['pendingOutside']} pendências fora dos critérios"}.get(x, x) for x in c['cautions']]
        if ticks and c['parentTicks'] and c['parentTicks']['lines']:
            notes.append(f"marcar no corpo de #{c['parentTicks']['parent']} as linhas "
                         + ', '.join(str(n) for n in c['parentTicks']['lines']))
        if c['parentTicks'] and c['parentTicks']['shared']:
            notes.append('não marcadas (citam outras issues): linhas ' + ', '.join(str(n) for n in c['parentTicks']['shared']))
        lines.append(f"| {c['order']} | #{c['number']} | {cell(c['title'])} | {'sub-issue' if c['level'] == 'sub' else 'topo'} "
                     f"| {criteria.get('checked', 0)}/{criteria.get('total', 0)} | {children['completed']}/{children['total']} "
                     f"| {prs} | {cell('; '.join(notes)) or '-'} |")
    lines += ['', 'Comandos, na ordem (cada valor um argumento):', '']
    for c in found['candidates']:
        lines.append('- `' + ' '.join(c['commands'][0]['argv']) + '`')
    excluded = [e for e in found['excluded'] if e['reason'] == 'awaiting_release']
    if excluded:
        lines += ['', 'Esperam a release (não entram): ' + ', '.join(f"#{e['number']}" for e in excluded) + '.']
    machine = {'scope': found['scope']['numbers'], 'base': found.get('base'), 'remote': found.get('remote'),
               'candidates': [{'number': c['number'], 'order': c['order'], 'state': c['state'], 'parent': c['parent'],
                               'level': c['level'],
                               'parentTicks': c['parentTicks'] and {'parent': c['parentTicks']['parent'],
                                                                    'lines': c['parentTicks']['lines']}}
                              for c in found['candidates']]}
    lines += ['', f'<!-- {LIST_MARK}', json.dumps(machine, ensure_ascii=True, sort_keys=True), '-->', '']
    return '\n'.join(lines)


def question_of(found):
    """(question, options, recommended) of the closing, in Portuguese, as references/closeout.md asks it."""
    count = len(found['candidates'])
    ticks = any(c['parentTicks'] and c['parentTicks']['lines'] for c in found['candidates'])
    question = f'Fechar estas {count} issues' + (' e marcar os itens dos pais?' if ticks else '?')
    options = ['Sim, fechar tudo', 'Escolher quais'] + (['Só fechar, sem marcar'] if ticks else []) + ['Não agora']
    careful = any('open_pr' in c['cautions'] or c['pendingOutside'] for c in found['candidates'])
    return question, options, 'Escolher quais' if careful else 'Sim, fechar tudo'


def op_run(config, root='.', explicit=None, all_flag=False, gh=None, base=None, remote=None):
    """Read only on GitHub: the candidates, written to a stamped list `.frontlights/closeout-<data>.md` (the one file
    this writes), with the question to ask by link and stamp. Nothing is closed here."""
    found = op_candidates(config, root, explicit, all_flag, gh, base, remote)
    found['base'], found['remote'] = base, remote
    result = {'ok': True, 'exitCode': 0, 'project': found['project'], 'repository': found['repository'],
              'count': len(found['candidates']), 'ask': bool(found['candidates']),
              'awaiting_release': [e['number'] for e in found['excluded'] if e['reason'] == 'awaiting_release'],
              'excluded': found['excluded'], 'alreadyDone': found['alreadyDone'], 'path': None, 'stamp': None}
    if not found['candidates']:
        result['message'] = 'Nenhuma issue pronta para fechar; nenhuma lista foi gravada.'
        return result
    ticks = any(c['parentTicks'] and c['parentTicks']['lines'] for c in found['candidates'])
    text = render_list(found, ticks)
    path = list_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode('utf-8')
    with open(path, 'xb') as file:
        file.write(data)
    question, options, recommended = question_of(found)
    result.update(path=path.as_posix(), stamp=sha12(data), bytes=len(data), question=question, options=options,
                  recommended=recommended,
                  issues=[{'number': c['number'], 'title': c['title'], 'order': c['order'], 'cautions': c['cautions'],
                           'parentTicks': c['parentTicks']} for c in found['candidates']],
                  message=f'Lista de {len(found["candidates"])} issue(s) gravada em {path.as_posix()} com o carimbo '
                          f'{sha12(data)}: envie o link e pergunte "{question}"; depois rode `closeout.py apply --expect '
                          f'{sha12(data)} --answer "<resposta literal>"`.')
    return result


def find_list(root, expect):
    """The newest `.frontlights/closeout-*.md` whose stamp is `expect`, or None."""
    folder = Path(root) / '.frontlights'
    try:
        files = sorted(folder.glob('closeout-*.md'), key=lambda p: p.name, reverse=True)[:MAX_LISTS]
    except OSError:
        return None
    for path in files:
        try:
            if sha12(path.read_bytes()) == expect:
                return path
        except OSError:
            continue
    return None


def list_changes(stored, fresh):
    """What differs between the approved list and the recomputed one: issues gone or new, and for each, `order`,
    `state` and `parentTicks.lines`. [] when they agree."""
    old = {c['number']: c for c in stored}
    new = {c['number']: c for c in fresh}
    changes = [f'#{n} saiu' for n in sorted(set(old) - set(new))] + [f'#{n} entrou' for n in sorted(set(new) - set(old))]
    for number in sorted(set(old) & set(new)):
        a, b = old[number], new[number]
        if a['order'] != b['order']:
            changes.append(f"#{number} ordem {a['order']} → {b['order']}")
        if a['state'] != b['state']:
            changes.append(f"#{number} estado {a['state']} → {b['state']}")
        lines_a = (a.get('parentTicks') or {}).get('lines') or []
        lines_b = (b.get('parentTicks') or {}).get('lines') or []
        if lines_a != lines_b:
            changes.append(f'#{number} linhas do pai {lines_a} → {lines_b}')
    return changes


def tick_parent(repository, root, parent, child, lines, gh, edit):
    """Tick, in one write, the items of `parent` that cite `child` alone (`lines`): capture, check that each line is
    still such an item, build the body with only those `[ ]` turned into `[x]`, tick-check, write with `--body-file`,
    reread and tick-check again. The bodies are kept in .frontlights/issues/<parent>/ (never overwritten)."""
    before = read_issue_body(gh, repository, parent)
    current, _ = citing_items(before, child, repository)
    if not set(lines) <= set(current):
        return {'parent': parent, 'lines': lines, 'ok': False, 'written': False, 'reason': 'lines_changed',
                'message': f'as linhas {lines} de #{parent} já não são itens abertos que citam só #{child}; nada foi escrito'}
    parts = re.split(r'(\r\n|\r|\n)', before)
    for line in lines:
        raw = parts[2 * (line - 1)]
        item = ITEM.match(raw)
        if item is None or item.group(1) != ' ':
            return {'parent': parent, 'lines': lines, 'ok': False, 'written': False, 'reason': 'not_an_open_item',
                    'message': f'a linha {line} de #{parent} não é um item simples; nada foi escrito'}
        parts[2 * (line - 1)] = raw[:item.start(1)] + 'x' + raw[item.end(1):]
    new = ''.join(parts)
    require(compare_ticks(before, new, lines)['ok'], 'the ticked body of the parent did not check; nothing was written')
    folder = Path(root) / '.frontlights' / 'issues' / str(parent)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    files = {'before': str(save_body(folder, 'before', stamp, before)), 'new': str(save_body(folder, 'new', stamp, new))}
    edit(['issue', 'edit', str(parent), '--repo', repository, '--body-file', files['new']])
    after = read_issue_body(gh, repository, parent)
    files['after'] = str(save_body(folder, 'after', stamp, after))
    check = compare_ticks(before, after, lines)
    return {'parent': parent, 'lines': lines, 'ok': check['ok'], 'written': True, 'verified': check['ok'],
            'files': files, 'problems': check['problems']}


def op_apply(config, root='.', expect=None, answer=None, only=None, gh=None, edit=None, account=None, pause=None):
    """Write what the stamped list holds, after the user's answer (see the module's docstring)."""
    import stamp as stamping  # noqa: PLC0415
    gh, edit = gh or rs.gh_default, edit or gh_write
    require(isinstance(expect, str) and re.fullmatch(r'[0-9a-f]{12}', expect.strip().lower() or ''),
            'apply needs --expect <the 12-character stamp of the list shown in the question>')
    expect = expect.strip().lower()
    require(isinstance(answer, str) and answer.strip(), 'apply needs --answer "<the literal answer of the user>"')
    data, repository = load_repository(config)
    path = find_list(root, expect)
    require(path is not None, f'nenhuma lista .frontlights/closeout-*.md tem o carimbo {expect}: rode closeout.py run e '
                              'pergunte de novo')
    match = LIST_BLOCK.search(path.read_text(encoding='utf-8'))
    require(match is not None, f'{path.name} não tem o bloco da lista; rode closeout.py run de novo')
    stored = json.loads(match.group(1))
    outcome = {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'list': path.as_posix(),
               'stamp': expect, 'answer': answer, 'closed': [], 'failed': [], 'ticks': [], 'commands': [], 'verify': None}

    def record(result):
        target = path.with_name(path.stem + '.result.json')
        temporary = target.with_name(target.name + '.tmp')
        temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, target)
        result['result'] = target.as_posix()
        return result

    if answer.strip().casefold().startswith('não agora') or answer.strip().casefold() in ('não', 'nao', 'no'):
        outcome['message'] = 'Resposta "Não agora": nada foi escrito.'
        return record(outcome)
    ticks = not answer.strip().casefold().startswith('só fechar')
    numbers = [c['number'] for c in stored['candidates']]
    chosen = numbers if only is None else parse_numbers(only, '--only takes issue numbers of the list, as in --only 12,13')
    require(set(chosen) <= set(numbers), '--only names an issue that is not in the approved list: ' +
            ', '.join(f'#{n}' for n in sorted(set(chosen) - set(numbers))))
    if answer.strip().casefold().startswith('escolher'):
        require(only is not None, 'a resposta "Escolher quais" pede --only com as issues escolhidas')
    orphans = sorted({c['parent'] for c in stored['candidates'] if c['parent'] in chosen and c['number'] not in chosen})
    require(not orphans, '--only deixa sem filha o pai ' + ', '.join(f'#{n}' for n in orphans)
            + ': escolha também as filhas da lista, ou deixe o pai de fora (ele espera por elas)')
    # the stamp of the question first; the list recomputed; only then the approval, recorded with the literal answer
    # and checked right before the writes: a refused list never leaves an approval behind
    stamp_args = lambda **given: argparse.Namespace(**{'file': str(path), 'root': str(root), 'revision': None,
                                                       'approve': False, 'answer': None, 'stage': None,
                                                       'check': False, 'expect': None, **given})
    try:
        shown = stamping.run(stamp_args(expect=expect))
    except stamping.Refusal as error:
        raise Refusal(f'o carimbo não pôde ser conferido: {error}')
    require(shown['exitCode'] == 0, 'o carimbo da lista não confere com o da pergunta: ' + shown['message'])
    fresh = op_candidates(config, root, stored['scope'] or None, False, gh, stored.get('base'), stored.get('remote'))
    changes = list_changes(stored['candidates'], fresh['candidates'])
    if changes:
        outcome.update(ok=False, exitCode=1, changes=changes,
                       message='lista mudou: ' + '; '.join(changes) + '. Nada foi escrito; rode closeout.py run e '
                               'pergunte de novo.')
        return record(outcome)
    try:
        approval = stamping.run(stamp_args(approve=True, answer=answer, stage=7, expect=expect))
        require(approval['exitCode'] == 0, 'o carimbo da lista não confere com o da pergunta: ' + approval['message'])
        checked = stamping.run(stamp_args(check=True))
    except stamping.Refusal as error:
        raise Refusal(f'o carimbo não pôde ser gravado ou conferido: {error}')
    require(checked['exitCode'] == 0, 'stamp --check recusou a lista: ' + checked['message'])
    def mismatch():
        """The account check before each write through gh (never cached): None, or the result that stops here."""
        if account is None:
            return None
        try:
            account(data)
        except _cli.AccountMismatch as found:
            return found
        return None

    pause = (1.0 if len(chosen) > 5 else 0.0) if pause is None else pause
    blocked = set()
    for candidate in sorted(fresh['candidates'], key=lambda c: c['order']):
        number = candidate['number']
        if number not in chosen:
            continue
        held = [c['number'] for c in fresh['candidates'] if c['parent'] == number and c['number'] in blocked]
        if held:
            blocked.add(number)
            outcome['failed'].append({'number': number, 'reason': 'child_not_closed', 'children': held})
            continue
        argv = candidate['commands'][0]['argv'][1:]
        if outcome['commands'] and pause:
            import time  # noqa: PLC0415
            time.sleep(pause)   # the pace of the batch, under the secondary rate limit; no new question
        step = {'number': number, 'argv': candidate['commands'][0]['argv']}
        wrong = mismatch()
        if wrong is not None:
            stop = wrong.result(repository=repository, written=bool(outcome['closed']))
            return record({**outcome, **stop, 'ok': False, 'exitCode': 1})
        try:
            edit(argv)
            step['exitCode'] = 0
            outcome['closed'].append(number)
        except Refusal as error:
            step.update(exitCode=1, message=rs.clean(str(error), 200))
            blocked.add(number)
            outcome['failed'].append({'number': number, 'reason': 'close_failed', 'message': step['message']})
        outcome['commands'].append(step)
        parent = candidate['parentTicks']
        if ticks and number in outcome['closed'] and parent and parent['lines']:
            wrong = mismatch()
            if wrong is not None:
                stop = wrong.result(repository=repository, written=True)
                return record({**outcome, **stop, 'ok': False, 'exitCode': 1})
            try:
                outcome['ticks'].append(tick_parent(repository, root, parent['parent'], number, parent['lines'], gh, edit))
            except Refusal as error:
                outcome['ticks'].append({'parent': parent['parent'], 'lines': parent['lines'], 'ok': False,
                                         'written': None, 'message': rs.clean(str(error), 200)})
    if outcome['closed']:
        outcome['verify'] = op_verify(config, root, outcome['closed'], gh)
    bad_ticks = [t for t in outcome['ticks'] if not t['ok']]
    outcome['ok'] = not outcome['failed'] and not bad_ticks and (outcome['verify'] is None or outcome['verify']['ok'])
    outcome['exitCode'] = 0 if outcome['ok'] else 1
    parts = [f"{len(outcome['closed'])} issue(s) fechadas: " + ', '.join(f'#{n}' for n in outcome['closed']) + '.'
             if outcome['closed'] else 'Nenhuma issue foi fechada.']
    if outcome['ticks']:
        parts.append(f"{len(outcome['ticks']) - len(bad_ticks)} pai(s) marcados e conferidos.")
    if outcome['failed'] or bad_ticks:
        parts.append(f"{len(outcome['failed'])} fechamento(s) e {len(bad_ticks)} marcação(ões) falharam: só esses se "
                     'repetem, nunca um fechamento que já entrou.')
    outcome['message'] = ' '.join(parts)
    return record(outcome)


# ---------------------------------------------------------------- append and capture: the body writes of stage 5
# (redesign, issue 7). `capture` keeps the body exactly as GitHub holds it; `append` inserts approved lines only,
# never edits what is there: --items after the last item of the criteria section (a leftover, destination 2, with
# its pitfall line in the same stamped batch), --spec the boxes of an adopted issue, --walkthrough the two `Roteiro:`
# lines of each open box of an old issue. Every one: stamp --check, capture, insert, check that only lines were
# added, capture again right before the write (someone edited it: stop), write, reread and count the boxes.

PITFALL_LINE = re.compile(r'- (\d{4}-\d{2}-\d{2}) · #([1-9][0-9]*) · (.+?) · sonda: (.+)')
PITFALLS = Path('.frontlights') / 'pitfalls.md'


def utc_stamp():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def read_issue_state(gh, repository, number):
    """(body, state) exactly as GitHub holds them (`gh issue view --json body,state`)."""
    answer = gh(['issue', 'view', str(number), '--repo', repository, '--json', 'body,state'])
    body = answer.get('body') if isinstance(answer, dict) else None
    require(isinstance(body, str), f'GitHub gave no body text for issue #{number}')
    require(len(body.encode('utf-8')) <= MAX_RECORD_BYTES, f'the body of issue #{number} is larger than 2 MiB')
    return body, str(answer.get('state') or '').upper()


def issue_number_of(issue, verb):
    require(isinstance(issue, (str, int)) and NUMBER.fullmatch(str(issue).strip()) and valid_number(int(str(issue).strip())),
            f'{verb} needs one issue number: pass --issue 12')
    return int(str(issue).strip())


def op_capture(config, root, issue, gh=None):
    """`capture`: the body of --issue, byte for byte, in .frontlights/issues/<n>/body-before-<stamp>.md (read only on
    GitHub)."""
    number = issue_number_of(issue, 'capture')
    _, repository = load_repository(config)
    records = Path(root) / '.frontlights'
    require(records.is_dir(), 'capture keeps the body in .frontlights/issues/<n>/ of the project: pass --root')
    body, state = read_issue_state(gh or rs.gh_default, repository, number)
    folder = records / 'issues' / str(number)
    folder.mkdir(parents=True, exist_ok=True)
    path = save_body(folder, 'before', utc_stamp(), body)
    counts = criteria(body)
    return {'ok': True, 'exitCode': 0, 'repository': repository, 'issue': number, 'state': state, 'path': str(path),
            'sha256': sha12(body.encode('utf-8')), 'bytes': len(body.encode('utf-8')),
            'criteria': None if counts is None else {'checked': counts[0], 'total': counts[1]},
            'message': f'Corpo da issue #{number} guardado byte a byte em {path.name}.'}


def item_end(body, number):
    """The last line of the item on `number` with its sub-items (the rule `find_box` uses for the `Bloqueada:` line)."""
    lines = re.split(r'\r\n|\r|\n', body)
    shown = {n: heading for n, _, _, heading in sections(body)}
    own, end, gap = indentation(lines[number - 1]), number, False
    for later in range(number + 1, len(lines) + 1):
        whole = lines[later - 1]
        if not whole.strip():
            gap = True
            continue
        if shown.get(later) or (indentation(whole) <= own and (gap or LIST_ITEM.match(whole))):
            break
        gap, end = False, later
    return end


def criteria_items(body):
    """[(line, label, ticked, has_walkthrough)] of the top items of the criteria section, and the line of its heading
    (None without a section)."""
    found, heading_line, items = list(sections(body)), None, []
    for number, text, kind, heading in found:
        if kind != 'criteria':
            continue
        if heading and heading_line is None:
            heading_line = number
            continue
        item = ITEM.match(text) if not heading else None
        if item and not any(n < number <= item_end(body, n) for n, *_ in items):
            label = BOX_LABEL.match(text[item.end():].lstrip(' \t'))
            items.append([number, f'S{int(label.group(1))}' if label else None, item.group(1) != ' ', False])
        elif items and not heading and re.match(r'^[ \t]+[-*+][ \t]+Roteiro\s*:', text):
            items[-1][3] = True
    return [tuple(i) for i in items], heading_line


def insert_lines(body, insertions):
    """The body with each (after_line, [lines]) inserted, in the body's own line ending; nothing else changes."""
    ending = re.search(r'\r\n|\r|\n', body)
    newline = ending.group(0) if ending else '\n'
    parts = re.split(r'(\r\n|\r|\n)', body)
    for after, lines in sorted(insertions, key=lambda x: -x[0]):
        index = 2 * (after - 1)
        block = ''.join(line + newline for line in lines)
        if index + 1 < len(parts):
            parts.insert(index + 2, block)
        else:
            parts[index] = parts[index] + newline + block[:-len(newline)]
    return ''.join(parts)


def only_insertions(before, after):
    """[] when `after` is `before` with lines added and none removed or changed (the `numstat` with no deleted line);
    else the problems."""
    import difflib  # noqa: PLC0415
    old, new = body_lines(before), body_lines(after)
    problems = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag in ('replace', 'delete'):
            problems.append({'reason': 'line_removed_or_changed', 'lines': [i1 + 1, i2]})
    return problems


def items_from_file(text):
    """The checklist lines of a stamped items file: open top items `- [ ] ...` with their indented sub-items, nothing
    ticked, no heading; the trailing empty lines dropped."""
    lines = body_lines(text.lstrip('﻿'))
    require(lines and lines != [''], 'the items file is empty')
    tops = 0
    for index, line in enumerate(lines):
        item = ITEM.match(line)
        if item and indentation(line) == 0:
            require(item.group(1) == ' ', f'items file, line {index + 1}: a new criterion starts open (`- [ ]`)')
            tops += 1
            continue
        require(index > 0 and line.strip() and indentation(line) > 0,
                f'items file, line {index + 1}: only `- [ ] ...` items and their indented sub-items, with no empty line')
        require(not (ITEM.match(line) and ITEM.match(line).group(1) != ' '), f'items file, line {index + 1}: ticked')
    return lines, tops


def approval_of(path, root, what):
    """frontlights.stamp_check, as a refusal of append when the file has no approval that matches."""
    try:
        check = frontlights.stamp_check(path, root)
    except frontlights.PublishRefusal as error:
        raise TickRefusal(error.reason, str(error), error.hint)
    if not check['approved']:
        raise TickRefusal('not_approved', f'{check["path"]} ({check["sha256"]}) não confere com a última aprovação '
                          f'registrada ({check["revision"] or "nenhuma"}); nada foi escrito',
                          hint=f'mostre {what} e peça a aprovação por link e carimbo (stamp --approve) de novo')
    return check


def pitfall_lines(path, number):
    lines = [line for line in body_lines(Path(path).read_bytes().decode('utf-8-sig')) if line.strip()]
    require(lines, 'the pitfall file is empty')
    for line in lines:
        match = PITFALL_LINE.fullmatch(line)
        if not match:
            raise TickRefusal('pitfall_format', f'linha de armadilha fora do formato: {line[:120]!r}',
                              hint='- <AAAA-MM-DD> · #<n> · <fato> · sonda: <sonda> (references/issues.md, "A pitfall line")')
        if int(match.group(2)) != number:
            raise TickRefusal('pitfall_issue', f'a linha de armadilha cita #{match.group(2)}, não a issue #{number}')
    return lines


def plan_issue(plan_path, root, number, config):
    """The issue `number` of a stamped plan that passes validate-plan."""
    plan = frontlights.load(plan_path)
    try:
        frontlights.validate_plan(plan, config.get('project') if isinstance(config, dict) else None)
    except ValueError as error:
        raise TickRefusal('plan_invalid', f'o plano não passa no validate-plan: {error}')
    found = [i for i in plan['issues'] if i['id'] == number]
    if not found:
        raise TickRefusal('plan_issue_missing', f'a issue #{number} não está no plano')
    return found[0]


def op_append(config, root, issue, items=None, spec=None, walkthrough=None, pitfall=None, gh=None, edit=None,
              account=None):
    """`append` (see the block comment above): the result dict, `ok: false` with `reason` on a refusal."""
    number = issue_number_of(issue, 'append')
    chosen = [x for x in (items, spec, walkthrough) if x]
    require(len(chosen) == 1, 'append needs exactly one of --items <stamped file>, --spec <plan> or --walkthrough <plan>')
    require(pitfall is None or items, '--pitfall goes with --items (a leftover criterion leaves its pitfall line)')
    data, repository = load_repository(config)
    records = Path(root) / '.frontlights'
    require(records.is_dir(), 'append keeps the bodies in .frontlights/issues/<n>/ of the project: pass --root')
    gh, edit = gh or rs.gh_default, edit or gh_write
    result = {'repository': repository, 'issue': number, 'written': False, 'verified': False, 'files': {},
              'pitfalls': 0}
    try:
        approval = approval_of(chosen[0], root, 'o lote')
        result['approved'] = approval
        mode = 'items' if items else 'spec' if spec else 'walkthrough'
        result['mode'] = mode
        extra = []
        if pitfall:
            pitfall_approval = approval_of(pitfall, root, 'a linha de armadilha')
            if pitfall_approval['answer'] != approval['answer']:
                raise TickRefusal('pitfall_not_in_batch', 'a linha de armadilha não foi aprovada pela mesma resposta '
                                  'do lote; ela não tem pergunta própria', hint='aprove os dois arquivos com a mesma '
                                  'resposta literal (stamp --approve de cada um)')
            extra = pitfall_lines(pitfall, number)
        if items:
            lines, tops = items_from_file(Path(items).read_bytes().decode('utf-8'))
        else:
            source = plan_issue(chosen[0], root, number, data)
        before, state = read_issue_state(gh, repository, number)
        if state == 'CLOSED':
            raise TickRefusal('issue_closed', f'a issue #{number} está fechada: um critério novo vira issue de topo '
                              'que a cita; nada foi escrito')
        boxes, heading = criteria_items(before)
        if mode == 'items':
            if heading is None:
                raise TickRefusal('no_criteria_section', f'a issue #{number} não tem a seção de critérios de aceitação: '
                                  'a sobra vira issue de topo que a cita; nada foi escrito')
            last = item_end(before, boxes[-1][0]) if boxes else heading
            insertions = [(last, lines)]
        elif mode == 'spec':
            if any(label for _, label, _, _ in boxes):
                raise TickRefusal('boxes_present', f'a issue #{number} já tem caixas S<n>; nada foi escrito')
            lines = frontlights.criteria_lines(source)
            tops = sum(1 for line in lines if ITEM.match(line))
            if heading is None:
                end = len(body_lines(before))
                insertions = [(end, ['', '## Critérios de aceitação', '', *lines])]
            else:
                insertions = [(item_end(before, boxes[-1][0]) if boxes else heading, lines)]
        else:
            by_label = {s['id'].upper(): s for s in source.get('slices') or []}
            insertions, tops = [], 0
            for line, label, ticked, has in boxes:
                if label and not ticked and not has and label in by_label:
                    insertions.append((item_end(before, line), frontlights.walkthrough_lines(by_label[label])))
            if not insertions:
                raise TickRefusal('nothing_to_append', f'toda caixa aberta da issue #{number} já tem o roteiro (ou o '
                                  'plano não traz o walkthrough dela); nada foi escrito')
        new = insert_lines(before, insertions)
        problems = only_insertions(before, new)
        require(not problems, 'append built a body that is not the captured one with lines added; nothing was written')
    except TickRefusal as refusal:
        failure = {**result, **refusal.extra, 'ok': False, 'exitCode': 1, 'reason': refusal.reason,
                   'message': str(refusal)}
        if refusal.hint:
            failure['hint'] = refusal.hint
        return failure
    folder = records / 'issues' / str(number)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    files = result['files']
    files['before'] = str(save_body(folder, 'before', stamp, before))
    files['new'] = str(save_body(folder, 'new', stamp, new))
    if account is not None:
        try:
            account(data)
        except _cli.AccountMismatch as mismatch:
            return mismatch.result(**result)
    now, _ = read_issue_state(gh, repository, number)
    files['now'] = str(save_body(folder, 'now', stamp, now))
    if body_lines(now) != body_lines(before):
        return {**result, 'ok': False, 'exitCode': 1, 'reason': 'diverged',
                'message': f'Alguém editou a issue #{number} depois da captura ({files["before"]} e {files["now"]}): '
                           'mostre a diferença e pergunte; nada foi escrito.'}
    try:
        edit(['issue', 'edit', str(number), '--repo', repository, '--body-file', files['new']])
    except Refusal as error:
        return {**result, 'ok': False, 'exitCode': 1, 'reason': 'write_failed',
                'message': f'{error}; capture o corpo de novo antes de repetir.'}
    result['written'] = True
    after, _ = read_issue_state(gh, repository, number)
    files['after'] = str(save_body(folder, 'after', stamp, after))
    old, fresh = criteria(before) or (0, 0), criteria(after) or (0, 0)
    result['criteria'] = {'before': {'checked': old[0], 'total': old[1]},
                          'after': {'checked': fresh[0], 'total': fresh[1]}}
    result['inserted'] = sum(len(lines) for _, lines in insertions)
    if body_lines(after) != body_lines(new) or fresh[1] - old[1] != tops:
        return {**result, 'ok': False, 'exitCode': 1, 'reason': 'diverged_after',
                'message': f'A releitura da issue #{number} não é o corpo escrito ({files["new"]} e {files["after"]}): '
                           'mostre a diferença e pergunte; restaurar o corpo é uma escrita com aprovação própria.'}
    result['verified'] = True
    if extra:
        target = Path(root) / PITFALLS
        current = target.read_bytes().decode('utf-8') if target.is_file() else ''
        with open(target, 'a', encoding='utf-8', newline='') as handle:   # append-only: never rewritten
            handle.write(('' if not current or current.endswith('\n') else '\n') + ''.join(x + '\n' for x in extra))
        result['pitfalls'] = len(extra)
    return {**result, 'ok': True, 'exitCode': 0,
            'message': f'Issue #{number}: {result["inserted"]} linha(s) acrescentada(s), critérios {old[1]} → {fresh[1]}; '
                       'a releitura confere' + (f'; {len(extra)} linha(s) em .frontlights/pitfalls.md' if extra else '')
                       + '.'}


def run(operation, config=None, root='.', issues=None, all_flag=False, gh=None, **options):
    try:
        if operation == 'candidates':
            result = op_candidates(config, root, issues, all_flag, gh, options.get('base'), options.get('remote'))
        elif operation == 'verify':
            result = op_verify(config, root, issues, gh)
        elif operation == 'merge-status':
            result = op_merge_status(config, options.get('prs'), options.get('base'), gh)
        elif operation == 'tick-check':
            result = op_tick_check(options.get('before'), options.get('after'), options.get('lines'))
        elif operation == 'tick':
            result = op_tick(config, root, options.get('issue'), options.get('box'), options.get('line'), gh,
                             options.get('edit'), options.get('account'), options.get('record'),
                             options.get('comment_file'))
        elif operation == 'run':
            result = op_run(config, root, issues, all_flag, gh, options.get('base'), options.get('remote'))
        elif operation == 'capture':
            result = op_capture(config, root, options.get('issue'), gh)
        elif operation == 'append':
            result = op_append(config, root, options.get('issue'), options.get('items'), options.get('spec'),
                               options.get('walkthrough'), options.get('pitfall'), gh, options.get('edit'),
                               options.get('account'))
        elif operation == 'apply':
            result = op_apply(config, root, options.get('expect'), options.get('answer'), options.get('only'), gh,
                              options.get('edit'), options.get('account'), options.get('pause'))
        else:
            raise Refusal(f'Unknown operation: {rs.clean(operation, 40)}')
    except (Refusal, ValueError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    except Exception as error:  # noqa: BLE001  (a refusal in JSON, never a traceback; nothing was written)
        result = {'ok': False, 'exitCode': 1,
                  'message': f'closeout stopped on an unexpected {type(error).__name__}; nothing was written'}
    result['operation'] = rs.clean(operation, 40)
    result.setdefault('ok', result.get('exitCode') == 0)
    return result


# The commands the redesign replaced stay for one cycle as aliases (issue 2): they work as before and say what replaces them.
ALIASES = {'candidates': 'closeout.py candidates segue por um ciclo como alias: a lista carimbada sai de `closeout.py run` '
                         'e o fechamento de `closeout.py apply`; a abertura lê com `frontlights.py open`'}


def build_parser():
    parser = _cli.JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('candidates', 'verify', 'run'):
        command = sub.add_parser(name, allow_abbrev=False,
                                 description=('alias for one cycle: ' + ALIASES[name]) if name in ALIASES else None)
        command.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
        command.add_argument('--root', help='project whose .frontlights records name the issues worked on '
                                                 '(default: the main worktree of the current directory)')
        command.add_argument('--issues', help='issue numbers, such as 12,13' + ('' if name != 'verify' else ' (required)'))
        if name != 'verify':
            command.add_argument('--all', action='store_true', dest='all_flag', help='every open issue of the repository')
            command.add_argument('--base', help='the base branch the release lands in; without it, the base.branch of the '
                                                'newest authorization record that names the issue, else main')
            command.add_argument('--remote', help='the remote that holds the released base (default origin)')
    apply = sub.add_parser('apply', allow_abbrev=False)
    apply.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
    apply.add_argument('--root', help='the project whose .frontlights holds the stamped list (default: the main worktree '
                                      'of the current directory)')
    apply.add_argument('--expect', help='the stamp of the list shown in the question (required)')
    apply.add_argument('--answer', help="the user's answer, verbatim (required)")
    apply.add_argument('--only', help='the issues chosen after "Escolher quais", such as 12,13')
    status = sub.add_parser('merge-status', allow_abbrev=False)
    status.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
    status.add_argument('--prs', help='pull request numbers, such as 12,13 (required)')
    status.add_argument('--base', help="the approved base branch; without it, the repository's default branch")
    ticks = sub.add_parser('tick-check', allow_abbrev=False)
    ticks.add_argument('--before', help='the saved body of the parent (required)')
    ticks.add_argument('--after', help='the body about to be written, or read back after the write (required)')
    ticks.add_argument('--lines', help='the line numbers that were ticked, such as 14,22 (required)')
    tick = sub.add_parser('tick', allow_abbrev=False)
    tick.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
    tick.add_argument('--root', help='the project whose .frontlights/issues/<n>/ keeps the previous body '
                                         '(default: the main worktree of the current directory)')
    tick.add_argument('--issue', help='the issue number, such as 12 (default: the issue of the charter entry of the '
                                      'worktree of the current directory)')
    tick.add_argument('--box', help='the box to tick: the slice box S2 (also s2 or 2), or the leftover box P1')
    tick.add_argument('--line', help='or the line of any criterion of the section, such as 14')
    tick.add_argument('--record', help="the result.json of the watched run (default: .frontlights/issues/<n>/browser/"
                                       "result.json under --root; the lead issue's for a family)")
    tick.add_argument('--comment-file', help='a comment posted on the issue once the tick checks')
    capture = sub.add_parser('capture', allow_abbrev=False,
                             description='the body of --issue, byte for byte, in .frontlights/issues/<n>/body-before-<stamp>.md')
    append = sub.add_parser('append', allow_abbrev=False,
                            description='insert approved lines into the body of --issue, never edit what is there')
    for command in (capture, append):
        command.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
        command.add_argument('--root', help='the project whose .frontlights/issues/<n>/ keeps the bodies (default: the '
                                            'main worktree of the current directory)')
        command.add_argument('--issue', help='the issue number (default: the issue of the charter entry of the worktree)')
    group = append.add_mutually_exclusive_group()
    group.add_argument('--items', help='the stamped file with the new criteria (`- [ ] ...` and sub-items), inserted '
                                       'after the last item of the criteria section')
    group.add_argument('--spec', help='the stamped plan: the boxes of this issue into its criteria section')
    group.add_argument('--walkthrough', help='the stamped plan: the two Roteiro lines of each open box that lacks them')
    append.add_argument('--pitfall', help='with --items: the pitfall line(s), approved by the same answer, appended to '
                                          '.frontlights/pitfalls.md after the write checks')
    return parser


def resolve_defaults(args):
    """--root, --config and the issue of tick the command line left out, by the rules of `_cli`."""
    if hasattr(args, 'root'):
        args.root = str(_cli.root_path(args.root))
    if hasattr(args, 'config'):
        args.config = _cli.config_path(args.config, getattr(args, 'root', None) or _cli.main_worktree())
    if args.operation in ('tick', 'capture', 'append') and args.issue is None:
        args.issue = str(_cli.issue_number(None, _cli.current_tree(), args.root))
    return args


def main(argv=None):
    _cli.utf8_streams()
    try:
        args = resolve_defaults(_cli.output_flags(build_parser()).parse_args(argv))
    except _cli.UsageError as error:
        return _cli.print_usage_error(error)
    try:
        result = run(args.operation, getattr(args, 'config', None), getattr(args, 'root', '.'), getattr(args, 'issues', None),
                     getattr(args, 'all_flag', False), prs=getattr(args, 'prs', None), base=getattr(args, 'base', None),
                     remote=getattr(args, 'remote', None),
                     before=getattr(args, 'before', None), after=getattr(args, 'after', None),
                     lines=getattr(args, 'lines', None), issue=getattr(args, 'issue', None),
                     box=getattr(args, 'box', None), line=getattr(args, 'line', None),
                     expect=getattr(args, 'expect', None), answer=getattr(args, 'answer', None),
                     only=getattr(args, 'only', None),
                     record=getattr(args, 'record', None), comment_file=getattr(args, 'comment_file', None),
                     items=getattr(args, 'items', None), spec=getattr(args, 'spec', None),
                     walkthrough=getattr(args, 'walkthrough', None), pitfall=getattr(args, 'pitfall', None),
                     # checked at every write, never cached: the login and the repository against the config
                     account=((lambda data: _cli.gh_account(data, rs.gh_default))
                              if args.operation in ('tick', 'apply', 'append') else None))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    if args.operation in ALIASES:
        result['alias'] = ALIASES[args.operation]
    _cli.emit(json.dumps(result, indent=2, ensure_ascii=True), args.operation, args.full)
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
