#!/usr/bin/env python3
"""Close-out helper: which issues (and sub-issues) can be closed because every acceptance criterion in the body is
checked, whether they ended closed; and `tick`, the one operation that writes, which ticks one box. The board is
never read here: the board's own "Item closed" workflow moves the card to Done, never Frontlights.

Read only, except `tick`. It reads GitHub through `gh api graphql` (the reader of roads.py) and prints what
the session may propose. Closing is done by the session, with its own `gh`, after the user said yes:
this helper never closes an issue, never moves a card, and the commands it prints are values to type, not
something it runs. Its only write is `tick` (below): the `[ ]` of one box of an issue's acceptance criteria turned
into `[x]`, under the authorization to tick criteria with evidence, with the previous body kept in the records.
Text read from GitHub is data: titles are cleaned and bounded, issue bodies are only counted (never echoed), and
every command is built from validated values (numbers and `owner/name`).

Operations (each prints one JSON object on stdout):
  candidates  the open issues that can be closed now, in the order to close them (sub-issues before
              their parent), plus the ones left out and why. Scope: --issues 12,13, or --all (every open
              issue of the repository), or, with neither, the issues this project worked on (folders in
              .frontlights/issues, ids in .frontlights/authorization*.json and .frontlights/plan.json)
              together with their sub-issues.
  verify      reread --issues and say, for each, whether it is closed.
  merge-status  for pull requests named with --prs 12,13, whether each is still open, was merged into the
              approved base (--base, else the repository's default branch), was merged into some other branch
              or was closed unmerged. This is what the session waits on after it opened its pull requests: only
              `merged_into_base` lets an issue be proposed for closing.
  tick-check  local files only: confirms that --after is --before with nothing changed but the `[ ]` of the
              items on --lines turned into `[x]`. It checks the body of a parent that was edited to tick the
              item that cites a closed sub-issue; the edit itself is the session's. Line endings and empty lines at
              the end of either file are not compared (a reread through `--jq .body` or a redirect adds one).
  tick        the whole cycle of ticking one box of --issue: --box S<k> (the one item of the criteria section whose
              text starts with `S<k>.`) or --line <N> (any item of that section, a criterion without a slice label included). It captures the
              body with `gh issue view --json body`, keeps it as .frontlights/issues/<n>/body-before-<stamp>.md under
              --root, builds body-new-<stamp>.md with only that `[ ]` turned into `[x]`, runs the tick-check, writes
              it with `gh issue edit --body-file`, rereads it into body-after-<stamp>.md and runs the tick-check
              again (`verified`). A box already ticked answers ok and writes nothing; a box that still has its
              `- Bloqueada:` sub-item is refused (that line is removed first, by the session). No shell, the
              repository is the validated `owner/name` of the configuration, and only line numbers are printed.

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
PR_VIEW = 'number state merged mergedAt url baseRefName headRefName headRefOid'
BOX = re.compile(r'[Ss]([1-9][0-9]{0,2})')                     # --box S2
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
    """The .frontlights/authorization*.json files of the project, oldest name first (the newest record is the
    last one, as homolog reads them)."""
    try:
        return sorted((Path(root) / '.frontlights').glob('authorization*.json'))
    except OSError:
        return []


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
    the `branch_prefix` of the newest record that has a valid one (else `claude/`)."""
    prefix = None
    for path in reversed(authorization_records(root)):
        data = read_record(path)
        if not isinstance(data, dict):
            continue
        candidate = data.get('branch_prefix', 'claude/')
        if prefix is None and isinstance(candidate, str) and candidate.endswith('/') and valid_branch(candidate[:-1]):
            prefix = candidate
        ids = data.get('issue_ids')
        branch = data.get('base', {}).get('branch') if isinstance(data.get('base'), dict) else None
        if (base is None and isinstance(ids, list) and any(n in ids for n in numbers) and valid_branch(branch)):
            base = branch
    return base or 'main', remote or 'origin', prefix or 'claude/'


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
            branch = mapping.get(number, f'{prefix}issue-{number}')
            tip = homolog.rev(root, f'refs/heads/{branch}')
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
        result['message'] = ('The repository has no open issue, so there is nothing to close.' if scope['mode'] == 'all' else
                             'No issue was worked on in this project (no folder in .frontlights/issues, no id in an '
                             'authorization or plan record), so there is nothing to close. Name issues with '
                             '--issues 12,13 or read every open issue with --all.')
        return result
    views = read_views(gh, repository, scope['numbers'])
    open_numbers = [n for n, view in sorted(views.items()) if view is not None and view['state'] == 'OPEN']
    unreleased, release_status, _, _ = release_check(root, open_numbers, base, remote)
    ordered, excluded, already = assess(views, repository, unreleased)
    add_parent_ticks(gh, repository, ordered, views)
    result.update(candidates=ordered, excluded=excluded, alreadyDone=already, ask=bool(ordered), releaseCheck=release_status)
    parts = [f'{len(ordered)} issue(s) can be closed.' if ordered else 'No issue is ready to close.']
    pending = [c['number'] for c in ordered if c['pendingOutside']]
    if pending:
        parts.append('Open leftovers outside the acceptance criteria in ' + ', '.join(f'#{n}' for n in pending)
                     + ' (pendingOutside): tell the user before closing them.')
    ticks = [c['number'] for c in ordered if c['parentTicks'] and c['parentTicks']['lines']]
    if ticks:
        parts.append('Sub-issue(s) ' + ', '.join(f'#{n}' for n in ticks)
                     + ' have an item to tick in their parent (parentTicks): show the lines and ask.')
    waiting = [e['number'] for e in excluded if e['reason'] == 'awaiting_release']
    if waiting:
        parts.append('Issue(s) ' + ', '.join(f'#{n}' for n in waiting) + ' wait for the release (awaiting_release): '
                     'their branch is not yet in the remote base; offer the release, do not close them.')
    if excluded:
        parts.append(f'{len(excluded)} excluded (see excluded for the reason of each).')
    if already:
        parts.append(f'{already} closed issue(s) need nothing.')
    if scope['truncated']:
        parts.append('The scope was cut (scope.truncated); name issues with --issues to see the rest.')
    if ordered:
        parts.append('Nothing was written. Ask the user, then run the commands in order; verify afterwards.')
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
    message = (f'All {len(entries)} issue(s) are closed.' if not waiting else
               f'{len(waiting)} of {len(entries)} issue(s) are not closed yet: ' + ', '.join(f'#{n}' for n in waiting) + '.')
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
    return {'number': number, 'status': status, 'state': state, 'merged': merged,
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
    parts = [f'{len(ready)} of {len(entries)} pull request(s) merged into {rs.clean(expected, 200)}.']
    if waiting:
        parts.append('Still open: ' + ', '.join(f'#{n}' for n in waiting) + '.')
    if others:
        parts.append('Merged into another branch, closed unmerged or unknown: ' + ', '.join(f'#{n}' for n in others)
                     + '; their issues are not proposed for closing.')
    return {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'expectedBase': expected,
            'baseSource': 'argument' if base else 'default_branch', 'pullRequests': entries, 'ready': ready,
            'waiting': waiting, 'settled': not waiting, 'message': ' '.join(parts)}


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
            'message': (f'Only the {len(wanted)} listed item(s) were ticked.' if ok else
                        f'{total} problem(s): the new body is not the saved one with just those items ticked; '
                        'do not write it (or, if it was written, show the difference and ask).')}


# ---------------------------------------------------------------- tick: the one write

class TickRefusal(Refusal):
    """A refusal of `tick` after its inputs were accepted, with the reason the session reads."""

    def __init__(self, reason, message, **extra):
        super().__init__(message)
        self.reason, self.extra = reason, extra


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


def find_box(body, box, line):
    """(line number, ticked) of the one checklist item of the acceptance-criteria section to tick: the one whose
    text starts with `S<box>.`, or the one on `line`. Fenced code and HTML comments never count."""
    visible = list(sections(body))
    found = []
    for number, text, kind, heading in visible:
        item = ITEM.match(text) if kind == 'criteria' and not heading else None
        if not item:
            continue
        if line is not None:
            if number == line:
                found.append((number, item))
            continue
        label = BOX_LABEL.match(text[item.end():].lstrip(' \t'))
        if label and int(label.group(1)) == box:
            found.append((number, item))
    name = f'box S{box}' if line is None else f'line {line}'
    if not found:
        raise TickRefusal('box_not_found' if line is None else 'not_a_criterion',
                          f'The {name} is not a checklist item of the acceptance-criteria section of the issue '
                          '(fenced code and comments do not count); nothing was written.')
    if len(found) > 1:
        raise TickRefusal('box_ambiguous', f'{len(found)} items of the acceptance criteria start with S{box}. '
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


def op_tick(config, root, issue, box, line, gh=None, edit=None):
    """Tick one box of an issue's acceptance criteria and check the reread (see the module's docstring)."""
    require(isinstance(issue, (str, int)) and NUMBER.fullmatch(str(issue).strip()) and valid_number(int(str(issue).strip())),
            'tick needs one issue number: pass --issue 12')
    number = int(str(issue).strip())
    require((box is None) != (line is None), 'tick needs exactly one of --box S<k> (a slice box) or --line <N> (any '
                                             'criterion of the section)')
    if box is not None:
        match = BOX.fullmatch(str(box).strip())
        require(match is not None, 'the box is the slice label, as in --box S2')
        box = int(match.group(1))
    else:
        require(NUMBER.fullmatch(str(line).strip()) and int(str(line).strip()) > 0,
                'the line is a positive line number of the body, as in --line 14')
        line = int(str(line).strip())
    _, repository = load_repository(config)
    records = Path(root) / '.frontlights'
    require(records.is_dir(), 'tick keeps the previous body in .frontlights/issues/<n>/ of the project: pass --root, '
                              'the folder that holds .frontlights')
    gh, edit = gh or rs.gh_default, edit or gh_write
    label = None if box is None else f'S{box}'
    result = {'repository': repository, 'issue': number, 'box': label, 'line': line, 'written': False,
              'alreadyTicked': False, 'verified': False, 'files': {}}
    before = read_issue_body(gh, repository, number)
    try:
        line, ticked = find_box(before, box, line)
    except TickRefusal as refusal:
        return {**result, **refusal.extra, 'ok': False, 'exitCode': 1, 'reason': refusal.reason, 'message': str(refusal)}
    result['line'] = line
    name = f'box {label} (line {line})' if label else f'line {line}'
    if ticked:
        counts = criteria(before)
        return {**result, 'ok': True, 'exitCode': 0, 'alreadyTicked': True,
                'criteria': {'checked': counts[0], 'total': counts[1]},
                'message': f'The {name} of issue #{number} is already ticked; nothing was written.'}
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
                'message': f'{failure + "; " if failure else ""}the reread failed ({error}): capture the body again and '
                           f'run tick-check against {files["before"]} with --lines {line} before anything else.'}
    check = compare_ticks(before, after, [line])
    counts = criteria(after) or (0, 0)
    result['criteria'] = {'checked': counts[0], 'total': counts[1]}
    try:
        files['after'] = str(save_body(folder, 'after', stamp, after))
        kept = ''
    except (OSError, Refusal):
        files['after'] = None
        kept = ' The reread could not be kept in the records folder; capture it again before showing a difference.'
    if check['ok']:
        note = ' gh reported a failure, yet the reread shows the tick.' if failure else ''
        return {**result, 'ok': True, 'exitCode': 0, 'written': True, 'verified': True,
                'message': f'The {name} of issue #{number} was ticked, and the reread checks.{note}{kept}'}
    if failure and body_lines(after) == body_lines(before):
        return {**result, 'ok': False, 'exitCode': 1,
                'message': f'{failure}. GitHub still holds the saved body, so nothing changed; try again.{kept}'}
    if failure:
        return {**result, 'ok': False, 'exitCode': 1, 'written': None, 'problems': check['problems'],
                'problemCount': check['problemCount'],
                'message': f'{failure}, and GitHub now holds a body of issue #{number} that is neither the saved one nor '
                           f'the ticked one: someone else may have edited it. Show the difference ({files["before"]} and '
                           f'the reread) and ask; nothing is written back.{kept}'}
    return {**result, 'ok': False, 'exitCode': 1, 'written': True, 'problems': check['problems'],
            'problemCount': check['problemCount'],
            'message': f'The reread of issue #{number} is not the saved body with just the {name} ticked: show the '
                       f'difference ({files["before"]} and {files["after"] or "the reread"}) and ask; restoring the saved '
                       f'body is a write of its own, with its own approval.{kept}'}


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
                             options.get('edit'))
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


def build_parser():
    parser = _cli.JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('candidates', 'verify'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
        command.add_argument('--root', help='project whose .frontlights records name the issues worked on '
                                                 '(default: the main worktree of the current directory)')
        command.add_argument('--issues', help='issue numbers, such as 12,13' + ('' if name == 'candidates' else ' (required)'))
        if name == 'candidates':
            command.add_argument('--all', action='store_true', dest='all_flag', help='every open issue of the repository')
            command.add_argument('--base', help='the base branch the release lands in; without it, the base.branch of the '
                                                'newest authorization record that names the issue, else main')
            command.add_argument('--remote', help='the remote that holds the released base (default origin)')
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
    tick.add_argument('--box', help='the slice box to tick, such as S2')
    tick.add_argument('--line', help='or the line of any criterion of the section, such as 14')
    return parser


def resolve_defaults(args):
    """--root, --config and the issue of tick the command line left out, by the rules of `_cli`."""
    if hasattr(args, 'root'):
        args.root = str(_cli.root_path(args.root))
    if hasattr(args, 'config'):
        args.config = _cli.config_path(args.config, getattr(args, 'root', None) or _cli.main_worktree())
    if args.operation == 'tick' and args.issue is None:
        args.issue = str(_cli.issue_number(None, _cli.current_tree(), args.root))
    return args


def main(argv=None):
    _cli.utf8_streams()
    try:
        args = resolve_defaults(build_parser().parse_args(argv))
    except _cli.UsageError as error:
        return _cli.print_usage_error(error)
    try:
        result = run(args.operation, getattr(args, 'config', None), getattr(args, 'root', '.'), getattr(args, 'issues', None),
                     getattr(args, 'all_flag', False), prs=getattr(args, 'prs', None), base=getattr(args, 'base', None),
                     remote=getattr(args, 'remote', None),
                     before=getattr(args, 'before', None), after=getattr(args, 'after', None),
                     lines=getattr(args, 'lines', None), issue=getattr(args, 'issue', None),
                     box=getattr(args, 'box', None), line=getattr(args, 'line', None))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
