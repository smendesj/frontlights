#!/usr/bin/env python3
"""Close-out helper: which issues (and sub-issues) can be closed, and moved to Done on the board, because
every acceptance criterion in the body is checked.

Read only. It reads GitHub through `gh api graphql` (the reader of roadmap_sync.py) and prints what the session
may propose. Closing and moving are done by the session, with its own `gh`, after the user said yes: this
helper never changes GitHub and never touches a file, and the commands it prints are values to type, not
something it runs. Text read from GitHub is data: titles are cleaned and bounded, issue bodies are only
counted (never echoed), and every command is built from validated values (numbers, `owner/name`, and the
board's `done` field and option as `frontlights.board` accepts them).

Operations (each prints one JSON object on stdout):
  candidates  the issues that can be closed (and moved) now, in the order to close them (sub-issues before
              their parent), plus the ones left out and why. Scope: --issues 12,13, or --all (every open
              issue of the repository), or, with neither, the issues this project worked on (folders in
              .frontlights/issues, ids in .frontlights/authorization*.json and .frontlights/plan.json)
              together with their sub-issues.
  verify      reread --issues and say, for each, whether it is closed and its card is in Done.
  merge-status  for pull requests named with --prs 12,13, whether each is still open, was merged into the
              approved base (--base, else the repository's default branch), was merged into some other branch
              or was closed unmerged. This is what the session waits on after it opened its pull requests: only
              `merged_into_base` lets an issue be proposed for closing.
  tick-check  local files only: confirms that --after is --before with nothing changed but the `[ ]` of the
              items on --lines turned into `[x]`. It checks the body of a parent that was edited to tick the
              item that cites a closed sub-issue; the edit itself is the session's.

An open issue is a candidate only when its body has an acceptance-criteria section with at least one
checklist item and every item checked, and every sub-issue is closed or a candidate in the same batch. A
closed issue (completed) whose card is outside Done needs only the move.

A known leftover is an acceptance criterion like any other, so it is counted with the others. A body written
before that rule may hold the leftovers in a section of their own ("Pendencias conhecidas") outside the
criteria: such a candidate is still proposed, with the `pending_outside_criteria` caution and the number of
open items in `pendingOutside`, so the user is told before closing it. The caution informs and never blocks.

A sub-issue candidate also carries `parentTicks`: the line numbers of the unchecked items of its open parent's
body that cite it and no other issue (`lines`), and those that cite it together with other issues (`shared`,
never offered for ticking). Only line numbers are reported; the session reads the lines from its own copy of the
body, so no body text is ever echoed here.

Exit codes: 0 done; 1 refusal (bad usage or configuration, a failed read) or, for verify, an issue that is not
finished yet (`ok` is false and `issues` says which). A refusal is JSON, never a traceback.
"""

import argparse
import heapq
import json
from pathlib import Path
import os
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import frontlights  # noqa: E402  (the board rules live there; this helper only reads them)
import roadmap_sync as rs  # noqa: E402  (its reader of GitHub: graphql, board_layout, clean, card_text)

Refusal = rs.Refusal
require = rs.require

MAX_SCOPE = 200            # issues one run reads when it walks from records down through sub-issues
MAX_ALL = 1000             # open issues --all reads, and the longest --issues list
MAX_DEPTH = 8              # levels of sub-issues GitHub allows
PAGE = 100
MAX_RECORD_BYTES = 2 * 1024 * 1024
HINT = 'gh auth refresh -s project'
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

VIEW = '''number state stateReason title url body
  parent { number repository { nameWithOwner } }
  subIssuesSummary { total completed }
  subIssues(first: 100) { totalCount nodes { number state repository { nameWithOwner } } }
  closedByPullRequestsReferences(first: 20, includeClosedPrs: true) { totalCount nodes { number state merged url repository { nameWithOwner } } }
  timelineItems(last: 50, itemTypes: [CROSS_REFERENCED_EVENT]) { totalCount nodes {
    ... on CrossReferencedEvent { source { ... on PullRequest { number state merged url repository { nameWithOwner } } } } } }'''
CARDS = '''
  projectItems(first: 20) { totalCount nodes { id
    project { number owner { ... on Organization { login } ... on User { login } } }
    fieldValues(first: 50) { totalCount nodes {
      ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
    } }
  } }'''
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


def scan(body):
    """(criteria, pending): `criteria` as `criteria()` returns it, and `pending`, the number of unchecked items
    in the sections the body keeps outside the criteria for known leftovers (a heading starting with
    `pendencias conhecidas` or `known pending`, read like the criteria section). A heading nested inside the
    criteria section belongs to it and is already counted there, so it is never counted twice."""
    if not isinstance(body, str):
        return None, 0
    checked = total = pending = 0
    found = False
    level = None      # depth of the section being read; None outside one
    kind = None       # what that section holds: 'criteria' or 'pending'
    for _, line in visible_lines(body):
        heading = HEADING.match(line)
        if heading:
            depth = len(heading.group(1))
            name = plain(heading_text(heading.group(2) or ''))
            # deeper headings belong to the section being read, except a criteria heading under a legacy
            # section: that one still opens the criteria, exactly as it did before the legacy sections existed
            if level is not None and depth > level and not (kind == 'pending' and name.startswith(PHRASES)):
                continue
            level = kind = None
            if name.startswith(PHRASES):
                level, kind, found = depth, 'criteria', True
            elif name.startswith(LEGACY_PHRASES):
                level, kind = depth, 'pending'
            continue
        item = ITEM.match(line) if level is not None else None
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
    try:
        authorizations = sorted(base.glob('authorization*.json'))
    except OSError:
        authorizations = []
    for path in authorizations:
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

def read_views(gh, repository, numbers, board, with_cards):
    """What the rules need from each issue number: state, parent, sub-issues, linked pull requests, the
    acceptance-criteria counts and, with `with_cards`, its card on the configured board. A number GitHub does
    not know comes back as None. A list that did not fit one page is named in `truncated`, because a value cut
    off would read as absent. The body is counted, never kept."""
    nodes = read_aliases(gh, repository, numbers, VIEW + (CARDS if with_cards else ''))
    return {n: None if node is None else parse_view(n, node, repository, board, with_cards) for n, node in nodes.items()}


def parse_view(number, node, repository, board, with_cards):
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
    # The pull requests of this plugin carry no closing keyword, so GitHub does not list them above: they show up as
    # cross references (a pull request that merely cites the issue; an issue that cites it has no number here).
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
    card = None
    if with_cards:
        items, short = page(node.get('projectItems'))
        if short:
            truncated.append('cards')
        for item in items:
            project = item.get('project')
            owner = project.get('owner') if isinstance(project, dict) else None
            login = owner.get('login') if isinstance(owner, dict) else None
            if (isinstance(login, str) and type(project.get('number')) is int and project['number'] == board['number']
                    and login.casefold() == board['owner'].casefold()):
                card = {}
                values, short = page(item.get('fieldValues'))
                if short:
                    truncated.append('card_values')
                for value in values:
                    field = value.get('field')
                    field = field.get('name') if isinstance(field, dict) else None
                    text = rs.card_text(value)
                    if isinstance(field, str) and field and text:
                        card[field] = text
                break
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
            'prs': linked, 'card': card, 'cardsRead': with_cards, 'truncated': truncated}


def unread_board(board):
    """The `board` block for a run that found nothing to read: only what the configuration says."""
    if board is None:
        return {'status': 'unconfigured', 'owner': None, 'number': None, 'done': None}
    return {'status': 'not_read', 'owner': board['owner'], 'number': board['number'], 'done': dict(board['done'])}


def board_state(gh, board):
    """The `board` block of the answer, and the board's layout when GitHub could tell. `available`: the done
    field and option exist; `done_option_missing`: they do not (the real fields are shown) and no move is
    proposed; `unavailable`: the board could not be read (usually the project scope)."""
    if board is None:
        return unread_board(None), None
    done = board['done']
    info = {'status': 'available', 'owner': board['owner'], 'number': board['number'], 'done': dict(done)}
    try:
        layout = rs.board_layout(gh, board)
    except Refusal as refusal:
        return mark_unavailable(info, str(refusal)), None
    field = layout.get(done['field'])
    shown = f'"{rs.clean(done["field"])}"'
    if field is None:
        reason = f'the board has no field named {shown}'
    elif field['type'] != 'single_select':
        reason = f'the board field {shown} is not a single select'
    elif done['value'] not in field['options']:
        reason = f'the board field {shown} has no option "{rs.clean(done["value"])}"'
    else:
        return info, layout
    info.update(status='done_option_missing', reason=reason + '; fix project.done in the configuration',
                fields={rs.clean(name): rs.shown_field(entry) for name, entry in layout.items()})
    return info, layout


def mark_unavailable(info, reason):
    info.pop('fields', None)
    info.update(status='unavailable', reason=reason, hint=HINT)
    return info


def read_board_views(gh, repository, numbers, board, info):
    """The views, with the cards when the board could be read. A card read the project scope refuses is
    tried again without cards (the board turns `unavailable`); a read that fails either way is a refusal."""
    if info['status'] in ('available', 'done_option_missing'):
        try:
            return read_views(gh, repository, numbers, board, True)
        except Refusal as refusal:
            mark_unavailable(info, str(refusal))
    return read_views(gh, repository, numbers, board, False)


# ---------------------------------------------------------------- eligibility

def issue_url(repository, number):
    return f'https://github.com/{repository}/issues/{number}'


def assess(views, repository, board, info):
    """Split the scope: the candidates (in closing order), the issues left out with the reason, how many
    closed issues need nothing, and how many closed ones could not be checked for the move."""
    status = info['status']
    cards_known = status in ('available', 'done_option_missing')
    done_field, done_value = (board['done']['field'], board['done']['value']) if board else (None, None)
    memo = {}

    def cuts(view):
        names = view['truncated']
        return [n for n in names if n in ('cards', 'card_values')] if view['state'] == 'CLOSED' else list(names)

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
            else:
                result = ('ok', {})
        memo[number] = result
        return result

    def candidate(view):
        number = view['number']
        closed = view['state'] == 'CLOSED'
        card = view['card']
        current = card.get(done_field) if card is not None else None
        move = status == 'available' and card is not None and current != done_value
        level = 'top' if view['parent'] is None else 'sub'
        cautions = []
        if not closed:
            if any(pr['state'] == 'OPEN' for pr in view['prs']):
                cautions.append('open_pr')
            elif not view['prs']:
                cautions.append('no_pr')
            if cards_known and card is None and level == 'top':
                cautions.append('not_on_board')
            if card is not None and current == done_value:
                cautions.append('already_done_card')
            if view['pendingOutside']:
                cautions.append('pending_outside_criteria')
        url = issue_url(repository, number)
        commands = []
        if not closed:
            commands.append({'kind': 'close', 'argv': ['gh', 'issue', 'close', str(number), '--repo', repository,
                                                       '--reason', 'completed']})
        if move:
            commands.append({'kind': 'move', 'argv': ['gh', 'project', 'item-edit', str(board['number']), '--owner',
                                                      board['owner'], '--url', url, '--field', done_field,
                                                      '--value', done_value]})
        return {'number': number, 'title': view['title'], 'url': url, 'level': level, 'parent': view['parent'],
                'criteria': view['criteria'], 'pendingOutside': 0 if closed else view['pendingOutside'],
                'parentTicks': None,
                'children': {key: view['children'][key] for key in ('total', 'completed', 'open')},
                'state': view['state'], 'action': 'move_only' if closed else 'close_and_move' if move else 'close',
                'prs': view['prs'],
                'card': None if card is None else {'status': rs.clean(current) if current is not None else None},
                'onBoard': (card is not None) if cards_known else (False if status == 'unconfigured' else None),
                'moveToDone': move, 'cautions': cautions, 'commands': commands}

    found, excluded, already, unchecked = {}, [], 0, 0
    for number in sorted(views):
        view = views[number]
        kind, detail = verdict(number)
        if kind == 'ok':
            found[number] = candidate(view)
        elif kind != 'closed':
            excluded.append({'number': number, 'title': view['title'] if view else None, 'reason': kind, **detail})
        elif view['stateReason'] != 'COMPLETED' or board is None:
            already += 1
        elif status == 'unavailable' or (status == 'done_option_missing' and view['card'] is not None):
            unchecked += 1
        elif view['card'] is not None and view['card'].get(done_field) != done_value:
            found[number] = candidate(view)
        else:
            already += 1
    ordered = [found[n] for n in closing_order(found, views)]
    for position, record in enumerate(ordered, 1):
        record['order'] = position
    return ordered, excluded, already, unchecked


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


# ---------------------------------------------------------------- operations

def load_project(config):
    """(repository, normalised board or None) from the project's configuration file."""
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
    return repository, frontlights.board(data.get('project'), repository)


def board_note(info):
    if info['status'] == 'unavailable':
        return f'The board could not be read, so no move to Done is proposed (try: {HINT}).'
    if info['status'] == 'done_option_missing':
        return 'The board has no Done option as configured, so no move is proposed (see board).'
    return ''


def op_candidates(config, root='.', explicit=None, all_flag=False, gh=None):
    """Read only: the issues that can be closed (and moved to Done) now, with the commands to type once the
    user approves, in closing order; the issues left out and why."""
    gh = gh or rs.gh_default
    repository, board = load_project(config)
    numbers = None if explicit is None else parse_numbers(explicit)
    require(not (all_flag and numbers is not None), '--issues and --all cannot be used together; choose one')
    scope = scope_numbers(root, numbers, all_flag, gh, repository)
    result = {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'scope': scope,
              'board': unread_board(board), 'candidates': [], 'excluded': [], 'alreadyDone': 0, 'closedUnchecked': 0,
              'ask': False}
    if not scope['numbers']:
        result['message'] = ('The repository has no open issue, so there is nothing to close.' if scope['mode'] == 'all' else
                             'No issue was worked on in this project (no folder in .frontlights/issues, no id in an '
                             'authorization or plan record), so there is nothing to close. Name issues with '
                             '--issues 12,13 or read every open issue with --all.')
        return result
    info, _ = board_state(gh, board)
    result['board'] = info
    views = read_board_views(gh, repository, scope['numbers'], board, info)
    ordered, excluded, already, unchecked = assess(views, repository, board, info)
    add_parent_ticks(gh, repository, ordered, views)
    result.update(candidates=ordered, excluded=excluded, alreadyDone=already, ask=bool(ordered))
    result['closedUnchecked'] = unchecked
    moves = sum(c['action'] == 'move_only' for c in ordered)
    parts = [f'{len(ordered)} issue(s) can be closed or moved to Done ({len(ordered) - moves} to close, {moves} only to move).'
             if ordered else 'No issue is ready to close.']
    pending = [c['number'] for c in ordered if c['pendingOutside']]
    if pending:
        parts.append('Open leftovers outside the acceptance criteria in ' + ', '.join(f'#{n}' for n in pending)
                     + ' (pendingOutside): tell the user before closing them.')
    ticks = [c['number'] for c in ordered if c['parentTicks'] and c['parentTicks']['lines']]
    if ticks:
        parts.append('Sub-issue(s) ' + ', '.join(f'#{n}' for n in ticks)
                     + ' have an item to tick in their parent (parentTicks): show the lines and ask.')
    if excluded:
        parts.append(f'{len(excluded)} excluded (see excluded for the reason of each).')
    if already:
        parts.append(f'{already} closed issue(s) need nothing.')
    if unchecked:
        parts.append(f'{unchecked} closed issue(s) could not be checked for the move to Done.')
    if scope['truncated']:
        parts.append('The scope was cut (scope.truncated); name issues with --issues to see the rest.')
    parts.append(board_note(info))
    if ordered:
        parts.append('Nothing was written. Ask the user, then run the commands in order; verify afterwards.')
    result['message'] = ' '.join(part for part in parts if part)
    return result


def op_verify(config, root='.', explicit=None, gh=None):
    """Read only: for each issue, whether it is closed and, when it has a card on the board, whether the card
    is in Done."""
    gh = gh or rs.gh_default
    repository, board = load_project(config)
    require(explicit is not None and explicit != '' and explicit != [],
            'verify needs the issues to check: pass --issues 12,13')
    numbers = parse_numbers(explicit)
    require(len(numbers) <= MAX_ALL, f'name at most {MAX_ALL} issues')
    info, _ = board_state(gh, board)
    views = read_board_views(gh, repository, numbers, board, info)
    done_field, done_value = (board['done']['field'], board['done']['value']) if board else (None, None)
    entries = []
    for number in numbers:
        view = views[number]
        if view is None:
            entries.append({'number': number, 'state': None, 'stateReason': None, 'status': None, 'closed': False,
                            'done': None, 'ok': False, 'reason': 'not_found'})
            continue
        closed = view['state'] == 'CLOSED'
        card = view['card']
        current = card.get(done_field) if card is not None else None
        done = (current == done_value) if info['status'] == 'available' and card is not None else None
        entry = {'number': number, 'state': view['state'], 'stateReason': view['stateReason'],
                 'status': rs.clean(current) if current is not None else None, 'closed': closed, 'done': done,
                 'ok': closed and done is not False}
        if any(name in ('cards', 'card_values') for name in view['truncated']):
            entry.update(status=None, done=None, ok=False, reason='truncated')
        entries.append(entry)
    waiting = [e['number'] for e in entries if not e['ok']]
    result = {'ok': not waiting, 'exitCode': 0 if not waiting else 1, 'project': repository, 'repository': repository,
              'board': info, 'issues': entries}
    parts = [f'All {len(entries)} issue(s) are closed' + (' and in Done.' if info['status'] == 'available' else '.')
             if not waiting else
             f'{len(waiting)} of {len(entries)} issue(s) are not finished yet: ' + ', '.join(f'#{n}' for n in waiting) + '.']
    parts.append(board_note(info))
    result['message'] = ' '.join(part for part in parts if part)
    return result


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
    lets an issue be proposed for closing), `merged_elsewhere` (merged into another branch, such as a stacked
    parent), `closed_unmerged`, `not_found` or `unknown`."""
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
    repository, _ = load_project(config)
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
    open checklist item turned into `[x]`. Line endings are not compared, only the lines."""
    require(before and after, 'tick-check needs the saved body and the new one: pass --before and --after')
    require(lines is not None and lines != '' and lines != [], 'tick-check needs the lines that were ticked: pass --lines 14,22')
    wanted = parse_numbers(lines, 'line numbers must be positive integers, as in --lines 14,22')
    old = re.split(r'\r\n|\r|\n', read_body_file(before))
    new = re.split(r'\r\n|\r|\n', read_body_file(after))
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


def run(operation, config=None, root='.', issues=None, all_flag=False, gh=None, **options):
    try:
        if operation == 'candidates':
            result = op_candidates(config, root, issues, all_flag, gh)
        elif operation == 'verify':
            result = op_verify(config, root, issues, gh)
        elif operation == 'merge-status':
            result = op_merge_status(config, options.get('prs'), options.get('base'), gh)
        elif operation == 'tick-check':
            result = op_tick_check(options.get('before'), options.get('after'), options.get('lines'))
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


class JsonParser(argparse.ArgumentParser):
    """A usage mistake is a JSON refusal like any other."""

    def error(self, message):
        raise Refusal(f'usage: {message}')


def build_parser():
    parser = JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('candidates', 'verify'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--config', required=True, help="the project's .frontlights/config.json")
        command.add_argument('--root', default='.', help='project whose .frontlights records name the issues worked on')
        command.add_argument('--issues', help='issue numbers, such as 12,13' + ('' if name == 'candidates' else ' (required)'))
        if name == 'candidates':
            command.add_argument('--all', action='store_true', dest='all_flag', help='every open issue of the repository')
    status = sub.add_parser('merge-status', allow_abbrev=False)
    status.add_argument('--config', required=True, help="the project's .frontlights/config.json")
    status.add_argument('--prs', help='pull request numbers, such as 12,13 (required)')
    status.add_argument('--base', help="the approved base branch; without it, the repository's default branch")
    ticks = sub.add_parser('tick-check', allow_abbrev=False)
    ticks.add_argument('--before', help='the saved body of the parent (required)')
    ticks.add_argument('--after', help='the body about to be written, or read back after the write (required)')
    ticks.add_argument('--lines', help='the line numbers that were ticked, such as 14,22 (required)')
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        result = run(args.operation, getattr(args, 'config', None), getattr(args, 'root', '.'), getattr(args, 'issues', None),
                     getattr(args, 'all_flag', False), prs=getattr(args, 'prs', None), base=getattr(args, 'base', None),
                     before=getattr(args, 'before', None), after=getattr(args, 'after', None),
                     lines=getattr(args, 'lines', None))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
