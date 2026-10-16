#!/usr/bin/env python3
"""Roadmap sync between RoadS and the project's ROADMAP and SPRINT files.

Deterministic helper behind the roadmap-sync route of /frontlights. It owns everything that must
not depend on a model's judgement: the configuration, the credential, the first-use approval, the
HTTP calls, the sprint week, path safety, idempotency markers, backups and the acknowledgement.
The prose that goes into the files is written by the session into staged copies; this helper only
checks and moves those copies into place.

Operations (each prints one JSON object on stdout):
  status          configuration, credential presence, approval, scrumRoot, current week paths and
                  the marker nonce's age. No network, never fails for a missing configuration.
  approve         record the user's approval of the (endpoint URL, secretEnvVar) pair. Run only
                  after the user said yes in the conversation.
  fetch           POST <endpoint>/sync-board (its failure is reported, never fatal), GET
                  <endpoint>/roadmap-state (required: no fallback) and GET <endpoint>/pending-changes,
                  then write the plan and a staged copy of the roadmap and of each sprint file with a
                  pending change (a sprint file that does not exist yet is staged empty). Each item of a
                  sprint that roadmap-state shows as done (`done` true, past the sprint limit too) that is
                  not recorded yet joins the plan as a synthetic `completed` change.
  apply           move the staged copies into place, re-read, verify every marker, then ack
                  (unless --no-ack). A plan that holds only completions needs no ack: `not_needed`.
  ack             verify every marker in the targets, then POST <endpoint>/ack with the plan's asOf.
  rotate-markers  mint a fresh marker nonce and rewrite every marker in the roadmap and the current
                  week's sprint file. No network.
  gaps            read only: GET <endpoint>/roadmap-state again, then read on GitHub (gh api graphql) the
                  issues of the configured repository that RoadS shows, and list what each still lacks
                  against the project's board rules: `fill` is what the configuration settles by itself,
                  `choose` what needs a person. Writes nothing anywhere; --only-sprints skips the backlog
                  groups.

Completions come from the state only: the `done` flag of a sprint item, never the open or closed state
of its issue and never a text. They are not in the RoadS queue, so the ack never covers them and only the
queued changes can be "consumed": a declined completion needs no --confirm-declined. A completion has the
stable id `done-<itemId>` (a hash when that would not fit ID_PATTERN) and `completedOn` is the day of the
sync in Sao Paulo, not the day of the delivery. It is proposed while no marker of the local nonce records it in
the roadmap or in the sprint file; rotate-markers rewrites those markers with the others, and a lost nonce
offers it again, with the diff, like any other change already written. `roadmapSync.markCompleted` (default
true) turns the whole thing off.

Exit codes: 0 done; 1 nothing was acknowledged (apply validates every target before it writes any,
so a refusal from validation wrote nothing; a missing marker or an unconfirmed decline is raised
after writing and says so, with `written` and `backups`); 2 the files are written and verified but
the acknowledgement did not happen (`retryable` says whether running ack again can fix it).

Markers are `<!-- roads:<id> <tag> -->` (or with a trailing ` declined`). The tag is a truncated
HMAC-SHA256 over the id keyed by a 128-bit nonce kept in `.frontlights/roadmap-sync/marker.json`.
The nonce never leaves the machine and never appears in the files or in the printed plan, so the
roadmap service cannot spell a valid marker whatever text it returns.

The credential is read from the environment only (on Windows also the value saved with `setx`),
sent only in the Authorization header to the approved endpoint, never written, and redacted from
every string this helper prints.
"""

import argparse
import datetime as dt
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import frontlights  # noqa: E402  (the board rules live there; this helper only reads them)

EFFORTS = ('Very High', 'High', 'Medium', 'Low')
GH_COMMAND = ['gh']
GH_TIMEOUT = 60
GAPS_BATCH = 20
GAPS_TITLE_LIMIT = 200
ISSUE_URL = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]{0,8})')
ACTIONS = ('add', 'modify', 'remove', 'move_lane')
COMPLETED_ACTION = 'completed'
COMPLETION_PREFIX = 'done-'
COMPLETED_ON_MEANS = 'sync date'
SAO_PAULO = dt.timezone(dt.timedelta(hours=-3))  # no daylight saving time since 2019 (docs/roads-contract.md)
MAX_BODY_BYTES = 5 * 1024 * 1024
BACKUP_GENERATIONS = 5
SHRINK_RATIO = 0.9
SECRET_ENV_PATTERN = r'^FRONTLIGHTS_[A-Z0-9_]+$'
ID_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'
FIELD_LIMITS = {'action': 100, 'title': 400, 'description': 4000, 'produto': 200, 'prioridade': 100,
                'effort': 100, 'lane': 200, 'laneId': 200, 'githubIssueUrl': 500, 'payload': 2000,
                'timezone': 100, 'reason': 100, 'message': 1000, 'error': 1000}
STATE_SCHEMA_VERSION = 1
STATE_YEARS = (2000, 2100)
ITEM_STATUSES = ('open', 'development', 'blocker', 'done', 'none')
SNAPSHOT_MAX_AGE = dt.timedelta(hours=24)
TEMPLATE_LOOKBACK_WEEKS = 26
REPARSE_POINT = 0x400
OFFLINE_MASK = 0x1000 | 0x40000 | 0x400000  # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS
MANIFEST = '.staging-origin.json'

_SECRETS = []


class Refusal(Exception):
    """A deliberate refusal: the message is safe to show the user."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def now_iso():
    return dt.datetime.now().astimezone().isoformat()


def sao_paulo_today(now=None):
    """The calendar day in Sao Paulo, whatever the clock of the machine says: the roadmap's calendar and the
    day a completion is recorded as of. `now`, when given, must carry a timezone."""
    now = now or dt.datetime.now(dt.timezone.utc)
    require(now.tzinfo is not None, 'internal error: sao_paulo_today needs a timezone-aware instant')
    return now.astimezone(SAO_PAULO).date()


def protect(text):
    for secret in _SECRETS:
        if secret:
            text = text.replace(secret, '[redacted]')
    return text


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json_atomic(value, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f'.{path.name}.{secrets.token_hex(8)}.tmp'
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def sha256(path):
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- configuration and context

def main_worktree(root):
    try:
        common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                cwd=root, capture_output=True, text=True, timeout=20)
        if common.returncode == 0 and common.stdout.strip():
            return Path(common.stdout.strip()).parent
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def config_path(root):
    """`.frontlights/config.json` here or, from a linked worktree, in the main one."""
    for place in (Path(root), main_worktree(root)):
        if place and (place / '.frontlights' / 'config.json').is_file():
            return (place / '.frontlights' / 'config.json').resolve()
    return None


def canonical_endpoint(url):
    parts = urllib.parse.urlsplit(url)
    return f'{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip("/")}'


def validate_endpoint(url):
    require(isinstance(url, str) and url, 'roadmapSync.endpoint is required')
    parts = urllib.parse.urlsplit(url)
    local = parts.hostname in ('localhost', '127.0.0.1', '::1')
    require(parts.scheme == 'https' or (parts.scheme == 'http' and local),
            'roadmapSync.endpoint must use https (http only for localhost)')
    require(parts.hostname and not parts.username and not parts.password and not parts.query and not parts.fragment,
            'roadmapSync.endpoint must be a plain URL without credentials, query or fragment')
    return url


def validate_issue_targets(targets):
    require(isinstance(targets, dict), 'roadmapSync.issueTargets must map each produto to its repository')
    for produto, target in targets.items():
        require(isinstance(target, dict) and isinstance(target.get('repository'), str)
                and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', target['repository']),
                f'roadmapSync.issueTargets[{produto!r}].repository must be owner/name')
        # A misspelt key would be dropped without a word; the board rules live in the top-level `project`.
        require(set(target) <= {'repository', 'project'},
                f'roadmapSync.issueTargets[{produto!r}] knows only repository and project')
        project = target.get('project')
        # `owner` is typed into `gh project item-add --owner`, and a config can come from a cloned repository:
        # it gets the same login rule as the top-level project's owner.
        require(project is None or (isinstance(project, dict) and set(project) <= {'owner', 'number'}
                                    and isinstance(project.get('owner'), str)
                                    and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', project['owner'])
                                    and type(project.get('number')) is int and project['number'] > 0),
                f'roadmapSync.issueTargets[{produto!r}].project must be null or {{owner, number}}: '
                'owner a GitHub login (letters, digits and -), number a positive integer')
    return targets


def expand_root(value):
    require(isinstance(value, str) and value.strip(), 'roadmapSync.scrumRoot is required')
    return os.path.expanduser(os.path.expandvars(value.strip()))


class Context:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config_path = config_path(root)
        require(self.config_path, 'No .frontlights/config.json in this project; create it first (see examples/config.json).')
        config = read_json(self.config_path)
        sync = config.get('roadmapSync')
        require(isinstance(sync, dict) and sync.get('enabled') is True,
                'This project does not enable roadmap sync: add a roadmapSync block with "enabled": true to .frontlights/config.json.')
        self.sync = sync
        self.endpoint = validate_endpoint(sync.get('endpoint'))
        self.secret_env = sync.get('secretEnvVar')
        require(isinstance(self.secret_env, str) and re.fullmatch(SECRET_ENV_PATTERN, self.secret_env),
                'roadmapSync.secretEnvVar must match ^FRONTLIGHTS_[A-Z0-9_]+$')
        self.scrum_root = expand_root(sync.get('scrumRoot'))
        for key in ('roadmapFile', 'weekFolderPattern', 'sprintFilePattern'):
            require(isinstance(sync.get(key), str) and sync[key].strip(), f'roadmapSync.{key} is required')
        self.max_sprint_items = sync.get('maxSprintItems', 4)
        require(isinstance(self.max_sprint_items, int) and self.max_sprint_items > 0,
                'roadmapSync.maxSprintItems must be a positive integer')
        self.mark_completed = sync.get('markCompleted', True)
        require(isinstance(self.mark_completed, bool), 'roadmapSync.markCompleted must be true or false')
        self.issue_targets = validate_issue_targets(sync.get('issueTargets') or {})
        self.state_dir = self.config_path.parent / 'roadmap-sync'
        self.plan_path = self.state_dir / 'plan.json'
        self.staging_dir = self.state_dir / 'staging'
        self.approval_path = self.state_dir / 'approval.json'
        self.marker_path = self.state_dir / 'marker.json'
        self.state_path = self.state_dir / 'state.json'
        self.name = str(config.get('repository') or self.config_path.parent.parent.name)
        self.repository = config.get('repository')
        self.project = config.get('project')


# ---------------------------------------------------------------- credential and approval

def windows_user_env(name):
    if not sys.platform.startswith('win'):
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
    except OSError:
        return None


def secret_present(name):
    return bool(os.environ.get(name) or windows_user_env(name))


def read_secret(name):
    """Process environment first, then the Windows user scope, which `setx` writes and which a
    session started before the variable existed cannot see in its own environment."""
    value = os.environ.get(name) or windows_user_env(name)
    require(value, f'Environment variable {name} is not set. Set it once in your own terminal with: '
                   f'setx {name} "<value issued by RoadS>" -- then restart Claude. It is read from the '
                   'environment only and never printed or stored.')
    _SECRETS.append(value)
    return value


def approval_pair(ctx):
    return {'endpoint': canonical_endpoint(ctx.endpoint), 'secretEnvVar': ctx.secret_env}


def approval_state(ctx):
    pair = approval_pair(ctx)
    try:
        stored = read_json(ctx.approval_path)
    except (OSError, ValueError):
        return 'unapproved', pair, None
    if stored.get('endpoint') == pair['endpoint'] and stored.get('secretEnvVar') == pair['secretEnvVar']:
        return 'approved', pair, None
    return 'changed', pair, {'endpoint': stored.get('endpoint'), 'secretEnvVar': stored.get('secretEnvVar')}


def assert_approved(ctx):
    state, pair, _ = approval_state(ctx)
    why = ('the endpoint URL or the secret variable changed since the last approval' if state == 'changed'
           else 'this pair has never been approved')
    require(state == 'approved', f'Roadmap sync is not approved to send {pair["secretEnvVar"]} to {pair["endpoint"]} '
                                 f'({why}). Ask the user; only after an explicit yes run the approve operation.')


# ---------------------------------------------------------------- week and paths

def sprint_week(today):
    """The Monday-Friday week containing today; a weekend belongs to the week just ended."""
    start = today - dt.timedelta(days=today.weekday())
    return start, start + dt.timedelta(days=4)


def expand_pattern(pattern, start, end):
    count = [0]

    def dd_mm(_match):
        count[0] += 1
        return (start if count[0] == 1 else end).strftime('%d_%m')
    text = re.sub(r'\{dd_MM\}', dd_mm, pattern)
    return text.replace('{yyyy}', start.strftime('%Y')).replace('{MM}', start.strftime('%m')).replace('{dd}', start.strftime('%d'))


def sprint_relative(ctx, start, end):
    folder = expand_pattern(ctx.sync['weekFolderPattern'], start, end)
    leaf = expand_pattern(ctx.sync['sprintFilePattern'], start, end)
    return folder.rstrip('/\\') + '/' + leaf


def targets(ctx, today):
    start, end = sprint_week(today)
    return {'week': (start, end), 'roadmap': expand_pattern(ctx.sync['roadmapFile'], start, end),
            'sprint': sprint_relative(ctx, start, end)}


def sprint_template(ctx, start, end):
    """The most recent existing sprint file before this sprint, walking back one week at a time
    with the same length; a new sprint file follows its headings and sections."""
    for weeks in range(1, TEMPLATE_LOOKBACK_WEEKS + 1):
        earlier = start - dt.timedelta(weeks=weeks)
        try:
            path = safe_target(ctx.scrum_root, sprint_relative(ctx, earlier, earlier + (end - start)))
        except Refusal:
            continue
        if os.path.isfile(path):
            return path
    return None


def reparse_tag(path):
    """0 for an ordinary entry, the reparse tag otherwise; -1 when unreadable."""
    try:
        info = os.lstat(path)
    except OSError:
        return -1
    attributes = getattr(info, 'st_file_attributes', 0)
    if attributes & REPARSE_POINT:
        return getattr(info, 'st_reparse_tag', -1)
    return -1 if os.path.islink(path) else 0


def cloud_tag(tag):
    # OneDrive Files On Demand and other sync providers use IO_REPARSE_TAG_CLOUD_*: storage, not
    # redirection, so it is allowed. Every other reparse point is refused.
    return tag > 0 and (tag & 0xFFFF0FFF) == 0x9000001A


def fully_qualified(path):
    if sys.platform.startswith('win'):
        return bool(re.match(r'^(?:[A-Za-z]:[\\/]|[\\/][\\/][^\\/]+[\\/])', path))
    return path.startswith('/')


def contained_path(scrum_root, relative):
    """The checks every path under scrumRoot gets: containment after normalisation, Windows' silent
    trimming of trailing dots and spaces, and no junction, symbolic link or non-cloud reparse point
    between scrumRoot and the path."""
    require(fully_qualified(scrum_root), f'Refusing scrumRoot {scrum_root}: it must be a fully qualified path')
    root = os.path.abspath(scrum_root).rstrip('\\/')
    require(os.path.splitdrive(root)[1].strip('\\/'),
            f'Refusing scrumRoot {scrum_root}: it must name a folder, not the root of a drive or share')
    require(os.path.isdir(root), f'scrumRoot does not exist: {root}')
    for segment in re.split(r'[\\/]', relative):
        require(not re.fullmatch(r'[. ]*', segment) and not re.search(r'[. ]$', segment) and ':' not in segment,
                f"Refusing target path: segment {segment!r} is empty, relative, or ends in a dot or space")
    require(not os.path.isabs(relative), 'Refusing target path: it must be relative to scrumRoot')
    full = os.path.abspath(os.path.join(root, relative))
    require(os.path.normcase(full).startswith(os.path.normcase(root + os.sep)), f'Refusing target path outside scrumRoot: {full}')
    cursor = full
    while True:
        if os.path.lexists(cursor):
            tag = reparse_tag(cursor)
            require(tag == 0 or cloud_tag(tag), f'Refusing target path: {cursor} is a junction, symbolic link or other reparse point')
        if len(cursor) <= len(root):
            break
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    return full


def safe_target(scrum_root, relative):
    """Resolve a pattern-derived file path under scrumRoot and refuse anything that could land a write
    elsewhere (see contained_path). An online-only cloud placeholder is refused: reading it would
    trigger a download."""
    full = contained_path(scrum_root, relative)
    if os.path.isfile(full):
        attributes = getattr(os.stat(full), 'st_file_attributes', 0)
        require(not attributes & OFFLINE_MASK, f"{full} is an online-only cloud placeholder not available on this device. "
                                               "Open it once or mark it 'Always keep on this device', then sync again.")
    else:
        require(not os.path.exists(full), f'Refusing target path: {full} is a directory')
    return full


def safe_folder(scrum_root, relative, create=False):
    """A pattern-derived folder under scrumRoot, with the same checks as a file target. With `create`,
    a missing folder is made and the chain is checked again, so nothing created in between redirects it."""
    full = contained_path(scrum_root, relative)
    require(not os.path.isfile(full), f'Refusing folder path: {full} is a file')
    if create and not os.path.isdir(full):
        os.makedirs(full, exist_ok=True)
        full = contained_path(scrum_root, relative)
    require(os.path.isdir(full), f'The folder does not exist: {full}')
    return full


def relative_to_root(ctx, path):
    root = os.path.abspath(ctx.scrum_root).rstrip('\\/') + os.sep
    full = os.path.abspath(path)
    require(os.path.normcase(full).startswith(os.path.normcase(root)), "The stored plan points outside scrumRoot; run fetch again.")
    return full[len(root):]


# ---------------------------------------------------------------- markers

def new_nonce():
    return secrets.token_hex(16)


def marker_record(ctx):
    try:
        stored = read_json(ctx.marker_path)
    except (OSError, ValueError):
        return None
    nonce = stored.get('nonce')
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        return None
    return stored


def write_marker_record(ctx, nonce, rotated=False):
    record = {'schemaVersion': 1, 'nonce': nonce, 'createdAt': now_iso()}
    if rotated:
        record['rotatedAt'] = record['createdAt']
    write_json_atomic(record, ctx.marker_path)


def marker_nonce(ctx):
    """The stored nonce, minting one when there is none; the flag says whether it was minted."""
    record = marker_record(ctx)
    if record:
        return record['nonce'], False
    nonce = new_nonce()
    write_marker_record(ctx, nonce)
    return nonce, True


def marker_tag(change_id, nonce, purpose='marker'):
    require(isinstance(nonce, str) and re.fullmatch(r'[0-9a-f]{32}', nonce), 'No usable marker nonce; run fetch again.')
    digest = hmac.new(bytes.fromhex(nonce), f'{purpose}:{change_id}'.encode('utf-8'), hashlib.sha256).digest()
    return digest[:8].hex()


def nonce_id(nonce):
    return marker_tag('nonce', nonce, 'nonce-id')


def marker_text(change_id, nonce, declined=False):
    suffix = ' declined' if declined else ''
    return f'<!-- roads:{change_id} {marker_tag(change_id, nonce)}{suffix} -->'


def marker_pattern(change_id, nonce):
    return r'<!--\s*roads:' + re.escape(change_id) + r'\s+' + marker_tag(change_id, nonce) + r'(?:\s+(declined))?\s*-->'


def marker_inventory(text, nonce):
    """Every marker this nonce vouches for, id -> 'applied' | 'declined'."""
    found = {}
    for match in re.finditer(r'<!--\s*roads:([A-Za-z0-9][A-Za-z0-9_.-]{0,127})\s+([0-9a-f]{16})(?:\s+(declined))?\s*-->', text or ''):
        change_id = match.group(1)
        if match.group(2) == marker_tag(change_id, nonce):
            found.setdefault(change_id, 'declined' if match.group(3) else 'applied')
    return found


def marker_state(text, change_id, nonce):
    match = re.search(marker_pattern(change_id, nonce), text or '')
    if not match:
        return None
    return 'declined' if match.group(1) else 'applied'


# ---------------------------------------------------------------- service data

def safe_string(value, field, limit):
    """Service text is untrusted and lands in files the user keeps and in the model's context:
    an HTML comment sequence refuses the whole batch, `<` and `>` are escaped so no sequence can be
    assembled across fields, control characters and fences are neutralised, and length is capped."""
    if value is None:
        return ''
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if not text:
        return ''
    require('<!--' not in text and '-->' not in text,
            f'RoadS returned an HTML comment sequence in {field}; nothing was written or acknowledged')
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', ' ', text)
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'`{3,}', '`', text)
    text = re.sub(r'~{3,}', '~', text)
    if len(text) > limit:
        text = text[:limit].rstrip() + ' [truncated]'
    return text


def timestamp(value, field='timestamp'):
    """(raw, parsed) for an ISO 8601 value, or None. The raw spelling is kept, trimmed."""
    if value is None:
        return None
    raw = safe_string(value, field, 100).strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return raw, parsed


def issue_target(ctx_targets, produto):
    for name, target in (ctx_targets or {}).items():
        if name.strip().casefold() == (produto or '').strip().casefold():
            return {'produto': name, **target}
    return None


def route_schema_version(payload, route, effect='Nothing was written or acknowledged'):
    """A route that carries schemaVersion must carry the one this Frontlights understands. A missing
    field is the implicit version 1 of the routes that predate it (docs/roads-contract.md)."""
    if isinstance(payload, dict) and 'schemaVersion' in payload:
        version = payload['schemaVersion']
        require(isinstance(version, int) and not isinstance(version, bool) and version == STATE_SCHEMA_VERSION,
                f'RoadS answered {route} with a schemaVersion that is not {STATE_SCHEMA_VERSION}, the only one understood. '
                f'{effect}; update Frontlights or take it to the RoadS owner.')


def move_lanes(payload, change_id):
    """The lanes a move_lane leaves and enters. The service sends `from_lane_id` (origin) and `lane_id`
    (destination); `from` and `to` are the older spelling and only stand in when the real key is absent."""
    def lane(*keys):
        for key in keys:
            if isinstance(payload.get(key), str):
                text = safe_string(payload[key], f'change {change_id} payload.{key}', FIELD_LIMITS['laneId']).strip()
                if text:
                    return text
        return None
    return lane('from_lane_id', 'from'), lane('lane_id', 'to')


def normalise_changes(payload, issue_targets=None):
    """Defensive normalisation of the pending-changes answer. Unknown fields are dropped. A change
    without a usable id is refused (it could never be marked and the ack would still consume it),
    and so is one without a title unless it is a remove identified by its itemId."""
    route_schema_version(payload, 'pending-changes')
    require(isinstance(payload, dict) and isinstance(payload.get('changes'), list), 'RoadS answered without a changes array')
    changes, seen = [], set()
    for change in payload['changes']:
        if change is None:
            continue
        require(isinstance(change, dict), 'RoadS returned a change that is not an object; nothing was written or acknowledged')
        raw_id = change.get('id')
        change_id = str(raw_id) if isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool) else ''
        require(re.fullmatch(ID_PATTERN, change_id), 'RoadS returned a change without a usable id; nothing was written or acknowledged')
        require(change_id not in seen, f'RoadS returned change {change_id} twice; nothing was written or acknowledged')
        seen.add(change_id)
        action = safe_string(change.get('action'), f'change {change_id} action', FIELD_LIMITS['action']).strip()
        item = change.get('item')
        require(item is None or isinstance(item, dict), f'RoadS returned change {change_id} with an item that is not an object')
        item = item or {}
        # A remove arrives with item and itemId both null: the queue row is written before the
        # delete and the foreign key is "on delete set null". The removed item's id, lane and title
        # travel in the payload, which also carries github_issue_url on a modify that links an issue.
        payload = change.get('payload') if isinstance(change.get('payload'), dict) else {}

        def safe_id(value):
            text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else None
            return text if text and re.fullmatch(ID_PATTERN, text) else None
        item_id = safe_id(change.get('itemId')) or safe_id(payload.get('item_id'))

        def field(name, payload_key=None):
            value = item.get(name)
            if (value is None or value == '') and payload_key:
                value = payload.get(payload_key)
            return safe_string(value, f'change {change_id} item.{name}', FIELD_LIMITS[name])
        title = field('title', 'title')
        require(title.strip() or (action == 'remove' and item_id),
                f'RoadS returned change {change_id} ({action or "no action"}) without a title; nothing was written or acknowledged. '
                'Either the change has no title or the service renamed the field: check the contract before running again.')
        effort_raw = field('effort')
        effort = next((e for e in EFFORTS if e.casefold() == effort_raw.strip().casefold()), None)
        issue_url = field('githubIssueUrl', 'github_issue_url')
        if not re.fullmatch(r'https?://[^\s<>"]+', issue_url) or re.search(r'&(?:lt|gt);', issue_url):
            issue_url = ''
        created = timestamp(change.get('createdAt'), f'change {change_id} createdAt')
        produto = field('produto')
        changes.append({
            'id': change_id, 'itemId': item_id, 'action': action,
            'knownAction': action in ACTIONS, 'synthetic': False,
            'createdAt': created[0] if created else None,
            'payload': safe_string(change.get('payload'), f'change {change_id} payload', FIELD_LIMITS['payload']) or None,
            'needsIssue': action in ('add', 'modify', 'move_lane') and not issue_url,
            'issueTarget': issue_target(issue_targets, produto),
            'item': {
                'title': title, 'description': field('description'), 'produto': produto,
                'prioridade': field('prioridade'), 'effort': effort, 'effortRaw': effort_raw,
                'githubIssueUrl': issue_url or None, 'lane': field('lane'), 'laneId': field('laneId', 'lane_id') or None},
            'itemMissing': not change.get('item'),
            '_created': created,
            # The lanes a move_lane leaves and enters, compared with the state's sprint laneIds.
            '_move': move_lanes(payload, change_id) if action == 'move_lane' else (None, None),
            # Only a completion is tied to sprints by the sprints that hold its item.
            '_sprints': [],
        })
    return changes


def as_of(payload, changes):
    """From the server, never the local clock: its asOf, else the newest createdAt returned."""
    server = timestamp(payload.get('asOf'), 'asOf')
    if server:
        return server[0], 'server'
    newest = None
    for change in changes:
        if change['_created'] and (newest is None or change['_created'][1] > newest[1]):
            newest = change['_created']
    return (newest[0], 'max-createdAt') if newest else (None, None)


def _state_refusal(field, what):
    return f'RoadS returned a roadmap-state whose {field} {what}; nothing was written or acknowledged'


def state_id(value, field, optional=False):
    if value is None and optional:
        return None
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
    require(re.fullmatch(ID_PATTERN, text), _state_refusal(field, 'is not a usable id'))
    return text


def state_text(value, field, limit, optional=True):
    require(isinstance(value, str) or (optional and value is None), _state_refusal(field, 'is not text'))
    return safe_string(value, f'roadmap-state {field}', limit)


def state_int(value, field, minimum, optional=False):
    if value is None and optional:
        return None
    require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum,
            _state_refusal(field, f'is not an integer of at least {minimum}'))
    return value


def state_bool(value, field):
    require(isinstance(value, bool), _state_refusal(field, 'is not true or false'))
    return value


def state_list(value, field, optional=False):
    if value is None and optional:
        return []
    require(isinstance(value, list), _state_refusal(field, 'is not a list'))
    return value


def state_time(value, field, optional=True):
    if value is None and optional:
        return None
    parsed = timestamp(value, f'roadmap-state {field}') if isinstance(value, str) else None
    require(parsed, _state_refusal(field, 'is not an ISO 8601 instant'))
    return parsed


def state_date(value, field):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), _state_refusal(field, 'is not a YYYY-MM-DD date'))
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise Refusal(_state_refusal(field, 'is not a valid calendar date'))
    # Week arithmetic (the template walks back, patterns expand) overflows near year 1 and 9999.
    require(STATE_YEARS[0] <= parsed.year <= STATE_YEARS[1],
            _state_refusal(field, f'is outside the years {STATE_YEARS[0]} to {STATE_YEARS[1]}'))
    return parsed


def state_item(raw, where, in_sprint):
    require(isinstance(raw, dict), _state_refusal(where, 'is not an object'))
    item_id = state_id(raw.get('id'), f'{where}.id')
    where = f'{where} ({item_id})'
    url = state_text(raw.get('githubIssueUrl'), f'{where}.githubIssueUrl', FIELD_LIMITS['githubIssueUrl'])
    if not re.fullmatch(r'https?://[^\s<>"]+', url) or re.search(r'&(?:lt|gt);', url):
        url = ''
    status = raw.get('status')
    require(status in ITEM_STATUSES, _state_refusal(f'{where}.status', 'is not one of ' + '|'.join(ITEM_STATUSES)))
    updated = state_time(raw.get('updatedAt'), f'{where}.updatedAt')
    pending = [state_id(value, f'{where}.pendingChangeIds') for value in state_list(raw.get('pendingChangeIds'), f'{where}.pendingChangeIds')]
    return {
        'id': item_id, 'position': state_int(raw.get('position'), f'{where}.position', 1),
        'title': state_text(raw.get('title'), f'{where}.title', FIELD_LIMITS['title'], optional=False),
        'description': state_text(raw.get('description'), f'{where}.description', FIELD_LIMITS['description']),
        'produto': state_text(raw.get('produto'), f'{where}.produto', FIELD_LIMITS['produto']),
        'prioridade': state_text(raw.get('prioridade'), f'{where}.prioridade', FIELD_LIMITS['prioridade']),
        'effort': state_text(raw.get('effort'), f'{where}.effort', FIELD_LIMITS['effort']),
        'githubIssueUrl': url or None, 'issueNumber': state_int(raw.get('issueNumber'), f'{where}.issueNumber', 1, optional=True),
        'status': status, 'done': state_bool(raw.get('done'), f'{where}.done'),
        # overLimit is the service's decision and exists only on sprint items.
        'overLimit': state_bool(raw.get('overLimit'), f'{where}.overLimit') if in_sprint else False,
        'updatedAt': updated[0] if updated else None, 'pendingChangeIds': pending}


def normalise_state(payload):
    """Defensive reading of GET roadmap-state (schemaVersion 1). An unknown schema version, a
    field of the wrong type, an invalid date or a duplicate sprint refuses the whole answer:
    nothing is guessed, and there is no fallback to the local week. Each sprint is a week; the weeks
    come out in the order of their dates (start, then end), never in the order of the text of their
    ids, which RoadS writes either as `sprint-YYYY-MM-DD` with a positional laneId (before its
    migration) or as `sprint-DD-MM-YYYY` for both sprintId and laneId (after it)."""
    require(isinstance(payload, dict), 'RoadS answered roadmap-state with something that is not an object')
    version = payload.get('schemaVersion')
    require(isinstance(version, int) and not isinstance(version, bool) and version == STATE_SCHEMA_VERSION,
            f'RoadS answered roadmap-state with a schemaVersion that is not {STATE_SCHEMA_VERSION}, the only one understood. '
            'Nothing was written or acknowledged; update Frontlights or take it to the RoadS owner.')
    state_as_of = state_time(payload.get('asOf'), 'asOf', optional=False)
    synced = state_time(payload.get('snapshotSyncedAt'), 'snapshotSyncedAt')
    sprints, seen = [], set()
    for index, raw in enumerate(state_list(payload.get('sprints'), 'sprints')):
        where = f'sprints[{index}]'
        require(isinstance(raw, dict), _state_refusal(where, 'is not an object'))
        sprint_id = state_id(raw.get('sprintId'), f'{where}.sprintId')
        require(sprint_id not in seen, _state_refusal(f'sprint {sprint_id}', 'appears twice'))
        seen.add(sprint_id)
        start, end = state_date(raw.get('startDate'), f'{where}.startDate'), state_date(raw.get('endDate'), f'{where}.endDate')
        require(end >= start, _state_refusal(f'sprint {sprint_id}', 'ends before it starts'))
        items = [state_item(item, f'{where}.items[{n}]', True) for n, item in enumerate(state_list(raw.get('items'), f'{where}.items'))]
        sprints.append({'sprintId': sprint_id, 'laneId': state_text(raw.get('laneId'), f'{where}.laneId', FIELD_LIMITS['laneId']),
                        'title': state_text(raw.get('title'), f'{where}.title', FIELD_LIMITS['title']),
                        'startDate': start.isoformat(), 'endDate': end.isoformat(), '_dates': (start, end),
                        'items': sorted(items, key=lambda i: i['position'])})
    sprints.sort(key=lambda sprint: sprint['_dates'])
    groups = []
    for index, raw in enumerate(state_list(payload.get('groups'), 'groups', optional=True)):
        where = f'groups[{index}]'
        require(isinstance(raw, dict), _state_refusal(where, 'is not an object'))
        groups.append({'laneId': state_text(raw.get('laneId'), f'{where}.laneId', FIELD_LIMITS['laneId']),
                       'title': state_text(raw.get('title'), f'{where}.title', FIELD_LIMITS['title']),
                       'items': [state_item(item, f'{where}.items[{n}]', False)
                                 for n, item in enumerate(state_list(raw.get('items'), f'{where}.items'))]})
    removed = []
    for index, raw in enumerate(state_list(payload.get('removedPending'), 'removedPending', optional=True)):
        where = f'removedPending[{index}]'
        require(isinstance(raw, dict), _state_refusal(where, 'is not an object'))
        removed.append({'changeId': state_id(raw.get('changeId'), f'{where}.changeId'),
                        'itemId': state_id(raw.get('itemId'), f'{where}.itemId', optional=True),
                        'title': state_text(raw.get('title'), f'{where}.title', FIELD_LIMITS['title']),
                        'laneId': state_text(raw.get('laneId'), f'{where}.laneId', FIELD_LIMITS['laneId'])})
    stale = synced is None or state_as_of[1] - synced[1] > SNAPSHOT_MAX_AGE
    return {'asOf': state_as_of[0], 'snapshotSyncedAt': synced[0] if synced else None, 'snapshotStale': stale,
            'maxSprintItems': state_int(payload.get('maxSprintItems'), 'maxSprintItems', 1, optional=True),
            'timezone': state_text(payload.get('timezone'), 'timezone', FIELD_LIMITS['timezone']),
            'sprints': sprints, 'groups': groups, 'removedPending': removed}


def board_result(text):
    """The sync-board answer, reduced to what the user is told. Never raises: a board sync that
    failed is reported, and the user decides whether to go on with the last state."""
    try:
        answer = json.loads(text)
        route_schema_version(answer, 'sync-board', 'The board sync may have run on the service; nothing was written here')
        require(isinstance(answer, dict) and isinstance(answer.get('ok'), bool), 'not the contract JSON')
        if not answer['ok']:
            reason = answer.get('reason')
            return {'ok': False, 'ran': False,
                    'reason': safe_string(reason, 'sync-board reason', FIELD_LIMITS['reason']) if isinstance(reason, str) and reason else 'error',
                    'message': safe_string(answer.get('message'), 'sync-board message', FIELD_LIMITS['message'])}
        roadmap = answer.get('roadmap') if isinstance(answer.get('roadmap'), dict) else {}

        def count(name):
            value = roadmap.get(name)
            return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        synced = timestamp(answer.get('syncedAt'), 'sync-board syncedAt') if isinstance(answer.get('syncedAt'), str) else None
        result = {'ok': True, 'ran': answer.get('ran') is True, 'syncedAt': synced[0] if synced else None,
                  'added': count('added'), 'removed': count('removed'), 'issuesCreated': count('issuesCreated')}
        if 'retitled' in roadmap:   # optional and additive: items whose title followed a renamed issue on GitHub
            result['retitled'] = count('retitled')
        if roadmap.get('error'):
            result['error'] = safe_string(roadmap['error'], 'sync-board roadmap.error', FIELD_LIMITS['error'])
        return result
    except (ValueError, Refusal) as error:
        # Only our own schemaVersion text is repeated; anything else RoadS sent stays out of the message.
        version_problem = isinstance(error, Refusal) and 'schemaVersion' in str(error)
        return {'ok': False, 'ran': False, 'reason': 'invalid_response',
                'message': str(error) if version_problem else
                'RoadS answered sync-board outside the contract (not JSON, another shape, or an HTML comment sequence)'}


# ---------------------------------------------------------------- transport

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def user_agent():
    """`frontlights-roadmap-sync/<commit>`, the skill checkout's `HEAD` (12 hex digits), so the service can tell this
    client's calls from any other; bare when Git or the checkout is unavailable."""
    try:
        done = subprocess.run(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', '--short=12', 'HEAD'],
                              capture_output=True, text=True, timeout=10)
        commit = done.stdout.strip() if done.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        commit = ''
    return 'frontlights-roadmap-sync' + (f'/{commit}' if re.fullmatch(r'[0-9a-f]{12}', commit) else '')

def http_default(method, url, headers, body):
    """Redirects are never followed, so the Authorization header cannot reach another host; a 3xx
    comes back as a status and is refused. Certificates are verified; the response is capped."""
    data = body.encode('utf-8') if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={**headers, 'Accept': 'application/json', 'User-Agent': user_agent(),
                                              **({'Content-Type': 'application/json'} if data is not None else {})})
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    except (urllib.error.URLError, OSError) as error:
        raise Refusal(f'network error contacting RoadS ({type(error).__name__})')
    with response:
        raw = response.read(MAX_BODY_BYTES + 1)
    require(len(raw) <= MAX_BODY_BYTES, 'the RoadS response exceeded the size limit')
    return response.status if hasattr(response, 'status') else response.code, raw.decode('utf-8', 'replace')


def endpoint_url(base, leaf, query=None):
    parts = urllib.parse.urlsplit(base)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/') + '/' + leaf, query or '', ''))


def request(ctx, transport, method, url, body=None):
    secret = read_secret(ctx.secret_env)
    base, target = urllib.parse.urlsplit(ctx.endpoint), urllib.parse.urlsplit(url)
    base_path = base.path.rstrip('/')
    require(target.scheme == base.scheme and target.netloc == base.netloc
            and (target.path == base_path or target.path.startswith(base_path + '/')),
            'internal error: request URL left the approved endpoint')
    status, text = transport(method, url, {'Authorization': f'Bearer {secret}'}, body)
    require(not 300 <= status < 400, f'RoadS answered with a redirect (HTTP {status}); redirects are never followed, '
                                     'so the credential was not sent anywhere else. Check roadmapSync.endpoint.')
    require(status not in (401, 403), f'RoadS rejected the credential (HTTP {status}). Check that {ctx.secret_env} holds '
                                      'the current value, then restart Claude.')
    require(200 <= status < 300, f'RoadS answered HTTP {status}')
    return text


# ---------------------------------------------------------------- plan, ack and files

def read_text(path):
    path = Path(path)
    if not path.is_file():
        return None
    return path.read_bytes().decode('utf-8-sig', 'replace')


def has_bom(path):
    path = Path(path)
    return path.is_file() and path.read_bytes()[:3] == b'\xef\xbb\xbf'


def read_plan(ctx):
    """Every reader of a plan re-derives what it trusts: each target path must resolve again to
    exactly itself, each staged copy must sit inside the staging directory, asOf must still parse to
    its own spelling (it is POSTed), and the plan must have been made under the current nonce."""
    require(ctx.plan_path.is_file(), 'No plan found; run fetch first.')
    plan = read_json(ctx.plan_path)
    require(plan.get('project') == ctx.name, 'The stored plan belongs to another project; run fetch again.')
    staging = os.path.normcase(os.path.abspath(ctx.staging_dir)) + os.sep
    stored = plan.get('targets')
    require(isinstance(stored, dict) and isinstance(stored.get('roadmap'), dict), 'The stored plan has no roadmap target; run fetch again.')
    seen = set()
    for name, target in stored.items():
        require(isinstance(target, dict) and target.get('path'), f'The stored plan has no {name} target; run fetch again.')
        require(safe_target(ctx.scrum_root, relative_to_root(ctx, target['path'])) == target['path'],
                'The stored plan does not match the configuration; run fetch again.')
        require(os.path.normcase(target['path']) not in seen,
                'The stored plan resolves two targets to the same path; check the patterns.')
        seen.add(os.path.normcase(target['path']))
        staged = target.get('staged') or ''
        require(os.path.normcase(os.path.abspath(staged)).startswith(staging),
                f'The stored plan points the {name} staged copy outside the staging directory; run fetch again.')
        if os.path.lexists(staged):
            tag = reparse_tag(staged)
            require(not os.path.isdir(staged) and (tag == 0 or cloud_tag(tag)),
                    f'The stored plan points the {name} staged copy at a directory or reparse point; run fetch again.')
    if plan.get('asOf'):
        parsed = timestamp(plan['asOf'], 'the stored plan asOf')
        require(parsed and parsed[0] == plan['asOf'], 'The stored plan asOf was altered since fetch; run fetch again.')
    record = marker_record(ctx)
    require(record, 'No marker nonce is stored, so no marker can be verified; run fetch again.')
    require(plan.get('markerNonceId') == nonce_id(record['nonce']), 'The stored plan was made with a different marker nonce; run fetch again.')
    return plan


def marker_report(plan, nonce):
    texts = [read_text(target['path']) for target in plan['targets'].values()]
    missing, declined = [], []
    for change in plan['changes']:
        states = {marker_state(text, change['id'], nonce) for text in texts} - {None}
        if 'applied' in states:
            continue
        (declined if 'declined' in states else missing).append(change['id'])
    return missing, declined


def plan_finished(plan):
    """A plan is finished once it was acknowledged, found to hold nothing to acknowledge, or discarded because
    nothing in the RoadS queue depended on it (a plan of completions only, when the markers were rotated)."""
    return 'ackedAt' in plan or 'ackNotNeededAt' in plan or 'discardedAt' in plan


def has_queued_changes(plan):
    return any(not c.get('synthetic') for c in plan['changes'])


def split_declined(plan, declined):
    """(declined changes of the RoadS queue, declined completions). Only the first kind is consumed by the
    acknowledgement; a completion is not in the queue, so nothing of it is consumed anywhere."""
    synthetic = {c['id'] for c in plan['changes'] if c.get('synthetic')}
    return [i for i in declined if i not in synthetic], [i for i in declined if i in synthetic]


def do_ack(ctx, transport, plan, result, nonce, confirm_declined):
    missing, declined = marker_report(plan, nonce)
    if missing:
        result.update(ack='refused', missingMarkers=missing, retryable=True,
                      message='Not acknowledged: these changes have no marker in the roadmap or sprint file: ' + ', '.join(missing))
        return 1
    declined, declined_completions = split_declined(plan, declined)
    if declined_completions:
        result['declinedCompletions'] = declined_completions
    # A declined change is consumed by the acknowledgement exactly like an applied one, so the
    # decline must be the user's, confirmed separately, never a conclusion drawn from service text.
    if declined:
        result['declined'] = declined
        if not confirm_declined:
            result.update(ack='refused', retryable=True, message=(
                'Not acknowledged yet: these changes are marked declined, and acknowledging consumes them at RoadS for good: '
                + ', '.join(declined) + '. Show the user each one and, only after they confirm each id, run ack with --confirm-declined.'))
            return 1
        result['declinedConfirmed'] = True
    if not has_queued_changes(plan):
        # Completions are read from roadmap-state, not from the queue: RoadS has nothing to consume for them.
        plan['ackNotNeededAt'] = now_iso()
        write_json_atomic(plan, ctx.plan_path)
        result.update(ack='not_needed', message=(
            'Written and verified. No acknowledgement is needed: this plan holds only completions read from roadmap-state, '
            'which are not in the RoadS queue, so there is nothing to consume. Nothing was sent to RoadS.'))
        return 0
    if not plan.get('asOf'):
        result.update(ack='skipped', retryable=False, message=(
            'Nothing acknowledged: RoadS sent no asOf and no change carried a usable createdAt, so there is no point to '
            'acknowledge up to. Running ack again will not change that; take it to the RoadS owner.'))
        return 2
    try:
        assert_approved(ctx)
        answer = request(ctx, transport, 'POST', endpoint_url(ctx.endpoint, 'ack'), json.dumps({'schemaVersion': STATE_SCHEMA_VERSION, 'asOf': plan['asOf']}))
    except Refusal as error:
        result.update(ack='failed', retryable=True, message=(
            f'Files are written and verified, but the acknowledgement failed: {error} Nothing is lost; the next sync skips '
            'the changes already marked and acknowledges them.'))
        return 2
    try:
        acked = json.loads(answer).get('acked')
    except (ValueError, AttributeError):
        acked = None
    write_json_atomic({'schemaVersion': 1, 'lastAckAsOf': plan['asOf'], 'lastAckAt': now_iso()}, ctx.state_path)
    plan['ackedAt'] = now_iso()
    write_json_atomic(plan, ctx.plan_path)
    result.update(ack='sent', asOf=plan['asOf'], acked=acked if isinstance(acked, int) else None)
    return 0


def backup_prefix(path):
    return '.' + Path(path).name + '.roads-backup'


def backup_generations(path):
    directory, prefix = Path(path).parent, backup_prefix(path)
    if not directory.is_dir():
        return []
    found = [p for p in directory.iterdir() if p.is_file() and (p.name == prefix or p.name.startswith(prefix + '-'))]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def new_backup_path(path):
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    for attempt in range(100):
        candidate = Path(path).parent / (backup_prefix(path) + '-' + stamp + (f'-{attempt}' if attempt else ''))
        if not candidate.exists():
            return candidate
    raise Refusal(f'Cannot find a free backup name beside {path}')


def hide(path):
    if sys.platform.startswith('win'):
        try:
            import ctypes
            attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attributes != -1:
                ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes | 0x2)
        except (OSError, AttributeError):
            pass


def prune_backups(path):
    for stale in backup_generations(path)[BACKUP_GENERATIONS:]:
        try:
            os.chmod(stale, 0o666)
            stale.unlink()
        except OSError:
            pass


def write_text_atomic(path, text, bom, backup):
    """The previous content always exists in some file: the backup is created (never over an
    existing name) before the new content replaces the target."""
    path = Path(path)
    temporary = path.parent / f'.{path.name}.{secrets.token_hex(8)}.tmp'
    try:
        with open(temporary, 'wb') as handle:
            handle.write((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
        if path.exists():
            require(backup, f'internal error: refusing to replace {path} without a backup')
            with open(backup, 'xb') as handle:
                handle.write(path.read_bytes())
            hide(backup)
            os.replace(temporary, path)
            prune_backups(path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_manifest(staging, files):
    write_json_atomic({'schemaVersion': 1, 'createdAt': now_iso(), 'appliedAt': None, 'files': files}, Path(staging) / MANIFEST)


def mark_staging_applied(staging):
    path = Path(staging) / MANIFEST
    try:
        manifest = read_json(path)
        manifest['appliedAt'] = now_iso()
        write_json_atomic(manifest, path)
    except (OSError, ValueError):
        pass


def staging_edits(staging):
    """Staged files that differ from what fetch put there and were never applied. With no readable
    manifest every file counts as edited: "cannot tell" means there may be work worth keeping."""
    staging = Path(staging)
    if not staging.is_dir():
        return []
    files = [p for p in staging.iterdir() if p.is_file() and p.name != MANIFEST]
    if not files:
        return []
    try:
        manifest = read_json(staging / MANIFEST)
    except (OSError, ValueError):
        return sorted(p.name for p in files)
    if manifest.get('appliedAt'):
        return []
    return sorted(p.name for p in files if (manifest.get('files') or {}).get(p.name) != sha256(p))


def remove_stale_staging(ctx):
    parent, leaf = ctx.staging_dir.parent, ctx.staging_dir.name
    if not parent.is_dir():
        return
    cutoff = dt.datetime.now().timestamp() - 24 * 3600
    for directory in parent.iterdir():
        is_new, is_previous = directory.name.startswith(leaf + '.new-'), directory.name.startswith(leaf + '.previous-')
        # A `.previous-*` may be the only copy of drafted prose while the staging directory is
        # missing mid-swap, so it is removed only while the staging directory exists.
        if not directory.is_dir() or not (is_new or is_previous) or (is_previous and not ctx.staging_dir.is_dir()):
            continue
        if directory.stat().st_mtime > cutoff:
            continue
        for child in sorted(directory.rglob('*'), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
        directory.rmdir()


def remove_tree(path):
    path = Path(path)
    if not path.exists():
        return
    for child in sorted(path.rglob('*'), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    path.rmdir()


# ---------------------------------------------------------------- operations

def op_status(root, today):
    result = {'configured': False}
    try:
        ctx = Context(root)
    except (Refusal, ValueError, OSError) as error:
        result.update(ok=True, exitCode=0, ready=False, message=str(error))
        return result
    state, pair, _ = approval_state(ctx)
    result.update(configured=True, project=ctx.name, secretEnvVar=ctx.secret_env,
                  secret='present' if secret_present(ctx.secret_env) else 'absent',
                  approval=state, endpoint=pair['endpoint'],
                  scrumRoot='exists' if os.path.isdir(ctx.scrum_root) else 'missing',
                  maxSprintItems=ctx.max_sprint_items, markCompleted=ctx.mark_completed,
                  issueTargets=sorted(ctx.issue_targets))
    paths = targets(ctx, today)
    start, end = paths['week']
    result['week'] = {'start': start.isoformat(), 'end': end.isoformat()}
    for name in ('roadmap', 'sprint'):
        try:
            full = safe_target(ctx.scrum_root, paths[name])
            result[name] = {'path': full, 'exists': os.path.isfile(full), 'safe': True}
        except Refusal as error:
            result[name] = {'relative': paths[name], 'safe': False, 'problem': str(error)}
    try:
        result['lastAckAsOf'] = read_json(ctx.state_path).get('lastAckAsOf')
    except (OSError, ValueError):
        result['lastAckAsOf'] = None
    result['sinceAvailable'] = result['lastAckAsOf']
    record = marker_record(ctx)
    result['markerNonce'] = 'present' if record else 'absent'
    if record:
        created = timestamp(record.get('createdAt'))
        result['markerNonceCreatedAt'] = record.get('createdAt')
        result['markerNonceAgeDays'] = (dt.datetime.now(dt.timezone.utc) - created[1]).days if created else None
    result['stagedDraft'] = staging_edits(ctx.staging_dir)
    result['ready'] = (result['secret'] == 'present' and state == 'approved' and result['scrumRoot'] == 'exists'
                       and result['roadmap']['safe'] and result['sprint']['safe'])
    message = 'Roadmap sync is ready.' if result['ready'] else 'Roadmap sync is not ready; see the fields above.'
    if not record:
        message += (' No marker nonce is stored yet: the next fetch mints one. If this project has synced before, marker.json '
                    'was lost and every change already written will be offered again; check for duplicates before applying.')
    result.update(ok=True, exitCode=0, message=message)
    return result


def op_approve(root):
    ctx = Context(root)
    pair = approval_pair(ctx)
    write_json_atomic({'schemaVersion': 1, **pair, 'approvedAt': now_iso()}, ctx.approval_path)
    return {'ok': True, 'exitCode': 0, 'project': ctx.name, 'approval': 'approved', **pair,
            'message': f'Approved: {pair["secretEnvVar"]} may be sent to {pair["endpoint"]}.'}


def sync_board(ctx, transport):
    """POST <endpoint>/sync-board, the board's own "Sincronizar". Its failure never aborts the
    fetch: it is reported, and the user decides whether to go on with the last state."""
    try:
        text = request(ctx, transport, 'POST', endpoint_url(ctx.endpoint, 'sync-board'))
    except Refusal as error:
        return {'ok': False, 'ran': False, 'reason': 'request_failed', 'message': str(error)}
    except (OSError, http.client.HTTPException, ValueError) as error:
        # A read that times out or ends early escapes the transport; only its type is reported.
        return {'ok': False, 'ran': False, 'reason': 'request_failed',
                'message': f'network error contacting RoadS ({type(error).__name__})'}
    return board_result(text)


def read_state(ctx, transport):
    """GET <endpoint>/roadmap-state. Without it there is no plan: no fallback to the local week."""
    try:
        text = request(ctx, transport, 'GET', endpoint_url(ctx.endpoint, 'roadmap-state'))
        payload = json.loads(text)
    except (Refusal, ValueError) as error:
        detail = str(error) if isinstance(error, Refusal) else 'the body is not JSON'
        raise Refusal(f'Could not read roadmap-state from RoadS ({detail}). There is no fallback: without it the sprints '
                      'cannot be resolved, so nothing was written or acknowledged.')
    return normalise_state(payload)


def completion_id(item_id):
    """The stable id of the completion of one item: `done-<itemId>`, or `done-` and a hash of the item id when
    that would not fit ID_PATTERN (a colon is not allowed in a marker, and the pattern caps the length)."""
    candidate = COMPLETION_PREFIX + item_id
    if re.fullmatch(ID_PATTERN, candidate):
        return candidate
    return COMPLETION_PREFIX + hashlib.sha256(item_id.encode('utf-8')).hexdigest()[:40]


def completion_changes(state, today, taken):
    """The sprint items roadmap-state shows as done, as synthetic `completed` changes, and how many were left
    out for lack of a title. Only the `done` flag of the state decides: never the open or closed state of the
    issue and never a text. Groups are not read; an item past the sprint limit (overLimit) is in its sprint, so it
    counts like the others. One
    item is one change, whatever the number of sprints that list it; every sprint that does is a target. The
    text of an item has already been through safe_string when the state was read. A change of the queue that
    already has the id of a completion is refused: the two kinds are told apart by that id."""
    found, untitled = {}, 0
    for sprint in state['sprints']:
        for item in sprint['items']:
            if item['done'] is not True:
                continue
            if not item['title'].strip():
                untitled += 1
                continue
            change_id = completion_id(item['id'])
            require(change_id not in taken, f'RoadS returned a change with the id {change_id}, which this helper reserves for the '
                                            f'completion of item {item["id"]}; nothing was written or acknowledged')
            if change_id in found:
                if sprint['sprintId'] not in found[change_id]['_sprints']:
                    found[change_id]['_sprints'].append(sprint['sprintId'])
                continue
            effort = next((e for e in EFFORTS if e.casefold() == item['effort'].strip().casefold()), None)
            found[change_id] = {
                'id': change_id, 'itemId': item['id'], 'action': COMPLETED_ACTION, 'knownAction': True, 'synthetic': True,
                'createdAt': None, 'payload': None, 'needsIssue': False, 'issueTarget': None,
                'completedOn': today.isoformat(), 'completedOnMeans': COMPLETED_ON_MEANS,
                'item': {'title': item['title'], 'description': item['description'], 'produto': item['produto'],
                         'prioridade': item['prioridade'], 'effort': effort, 'effortRaw': item['effort'],
                         'githubIssueUrl': item['githubIssueUrl'], 'lane': sprint['title'] or sprint['laneId'],
                         'laneId': sprint['laneId'] or None},
                'itemMissing': False,
                '_created': None, '_move': (None, None), '_sprints': [sprint['sprintId']]}
    return list(found.values()), untitled


def unrecorded_completions(ctx, state, completions, roadmap_path):
    """(completions no marker records yet, how many are recorded). A completion is recorded, applied or
    declined, when a marker of the local nonce for its id is in the roadmap or in the file of a sprint that
    holds the item: the same evidence `alreadyApplied` uses for the queued changes. Without a stored nonce no
    marker can vouch for anything, so every completion is new. Reading a sprint file here is the read the plan
    would make anyway, with the same path checks."""
    record = marker_record(ctx)
    if not completions or not record:
        return completions, 0
    dates = {sprint['sprintId']: sprint['_dates'] for sprint in state['sprints']}
    texts = {'roadmap': read_text(roadmap_path)}
    fresh, recorded = [], 0
    for change in completions:
        for sprint_id in change['_sprints']:
            if sprint_id not in texts:
                texts[sprint_id] = read_text(safe_target(ctx.scrum_root, sprint_relative(ctx, *dates[sprint_id])))
        names = ['roadmap', *change['_sprints']]
        if any(marker_state(texts[name], change['id'], record['nonce']) for name in names):
            recorded += 1
        else:
            fresh.append(change)
    return fresh, recorded


def unmatched_lanes(state, changes):
    """The lanes of the queue (the origin and destination of a move_lane) and of removedPending that match no
    week and no group of the state read by this fetch, in the order first seen. After the week turns, the week
    that ended is no longer in the state, so its lane is the expected case; a change that reaches a sprint only
    through such a lane goes to the roadmap only."""
    known = {sprint['laneId'] for sprint in state['sprints']} | {group['laneId'] for group in state['groups']}
    lanes = [lane for change in changes if not change['synthetic'] for lane in change['_move']]
    lanes += [removed['laneId'] for removed in state['removedPending']]
    return list(dict.fromkeys(lane for lane in lanes if lane and lane not in known))


def sprint_targets(ctx, state, changes):
    """Each sprint of the state with a pending change gets its own file. The link is the
    service's: a change belongs to a sprint when an item of that sprint lists it in
    pendingChangeIds, when removedPending puts its removal in that sprint's lane, or when a
    move_lane leaves that sprint's lane (payload.from_lane_id) or enters it (payload.lane_id) without any
    item of that sprint listing it. A lane is matched by its exact text against the laneId of the state
    read by this fetch: RoadS sends each answer in one shape only, positional or dated. An item
    past the limit (overLimit) is written in its sprint file too, after the items within the limit, so
    its changes reach that file like the others; the plan keeps the two lists apart (`items` and
    `outOfLimit`) only for the order of the file. A completion belongs to the sprints that
    hold its item (`_sprints`) and to no other: the links above are made only for the changes of
    the queue, so a state cannot send a completion to a sprint by naming it in pendingChangeIds or
    in removedPending."""
    change_ids = {c['id'] for c in changes if not c['synthetic']}
    sprints, files = [], {}
    for sprint in state['sprints']:
        within = [i for i in sprint['items'] if not i['overLimit']]
        over = [i for i in sprint['items'] if i['overLimit']]
        listed = {cid for item in sprint['items'] for cid in item['pendingChangeIds']}
        write = {cid for cid in listed if cid in change_ids}
        write |= {r['changeId'] for r in state['removedPending']
                  if r['laneId'] and r['laneId'] == sprint['laneId'] and r['changeId'] in change_ids}
        lane = sprint['laneId']
        write |= {c['id'] for c in changes if lane and c['_move'][0] == lane != c['_move'][1]}
        write |= {c['id'] for c in changes if lane and c['_move'][1] == lane and c['id'] not in listed}
        write |= {c['id'] for c in changes if sprint['sprintId'] in c['_sprints']}
        name = 'sprint:' + sprint['sprintId'] if write else None
        public = {key: value for key, value in sprint.items() if key != '_dates'}
        sprints.append({**public, 'items': within, 'outOfLimit': over, 'target': name})
        if name:
            start, end = sprint['_dates']
            files[name] = {'sprint': public, 'dates': (start, end), 'relative': sprint_relative(ctx, start, end),
                           'changeIds': sorted(write)}
    return sprints, files


def op_fetch(root, today, transport, since=None, discard_staged=False):
    # A refusal after the board sync still reports what the board sync did.
    result = {}
    try:
        return _fetch(root, today, transport, since, discard_staged, result)
    except (Refusal, ValueError, OSError, KeyError, TypeError) as error:
        result.update(ok=False, exitCode=1, message=str(error))
        return result


def _fetch(root, today, transport, since, discard_staged, result):
    ctx = Context(root)
    result['project'] = ctx.name
    read_secret(ctx.secret_env)
    assert_approved(ctx)
    paths = targets(ctx, today)
    roadmap_path = safe_target(ctx.scrum_root, paths['roadmap'])
    # The patterns are checked before any network call, on this week's sprint file.
    week_sprint = safe_target(ctx.scrum_root, paths['sprint'])
    require(os.path.normcase(week_sprint) != os.path.normcase(roadmap_path),
            'roadmapFile and the sprint patterns resolve to the same file; fix roadmapFile, weekFolderPattern or '
            'sprintFilePattern so each sprint has its own file.')
    edits = staging_edits(ctx.staging_dir)
    require(not edits or discard_staged, (
        f'Refusing to fetch: the staging directory holds drafted prose that was never applied ({", ".join(edits)}) in '
        f'{ctx.staging_dir}. Run apply to write it, or copy it out first; only then fetch again with --discard-staged.'))
    query = None
    if since:
        stamp = timestamp(since)
        require(stamp, '--since must be an ISO 8601 timestamp')
        query = 'since=' + urllib.parse.quote(stamp[0], safe='')
    board = sync_board(ctx, transport)
    result.update(syncBoard=board, syncBoardFailed=not board['ok'])
    notes = []
    if not board['ok']:
        notes.append(f' The RoadS board sync failed ({board["reason"]}: {board["message"]}). What follows is the last state '
                     'RoadS holds: ask the user whether to go on with it before drafting anything.')
    state = read_state(ctx, transport)
    result.update(stateAsOf=state['asOf'], snapshotSyncedAt=state['snapshotSyncedAt'], snapshotStale=state['snapshotStale'])
    if state['snapshotStale']:
        notes.append(' The RoadS snapshot is ' + (f'stale (synced at {state["snapshotSyncedAt"]}, more than 24 h before {state["asOf"]})'
                                                  if state['snapshotSyncedAt'] else 'missing (never synced)') + '; tell the user.')
    text = request(ctx, transport, 'GET', endpoint_url(ctx.endpoint, 'pending-changes', query))
    try:
        payload = json.loads(text)
    except ValueError:
        raise Refusal('RoadS answered with a body that is not JSON')
    changes = normalise_changes(payload, ctx.issue_targets)
    queued = len(changes)
    fresh, recorded, untitled = [], 0, 0
    if ctx.mark_completed:
        reserved = [c['id'] for c in changes if c['id'].startswith(COMPLETION_PREFIX)]
        if reserved:   # the message names the first one, so it is built only when there is one
            raise Refusal(f'RoadS returned a change with the id {reserved[0]}: the prefix {COMPLETION_PREFIX} is reserved '
                          'to the completions this helper records, so nothing was written or acknowledged. '
                          'Take it to the RoadS owner, or turn roadmapSync.markCompleted off.')
        found, untitled = completion_changes(state, today, {c['id'] for c in changes})
        fresh, recorded = unrecorded_completions(ctx, state, found, roadmap_path)
    completed = {'enabled': ctx.mark_completed, 'new': len(fresh), 'alreadyRecorded': recorded,
                 'completedOn': today.isoformat(), 'completedOnMeans': COMPLETED_ON_MEANS}
    if untitled:
        completed['withoutTitle'] = untitled
        notes.append(f' {untitled} done item(s) of roadmap-state have no title and were left out of the completions; tell the user.')
    result['completed'] = completed
    changes = changes + fresh
    if not changes:
        message = 'Nothing pending. No file was written and nothing was acknowledged.'
        if recorded:
            message += f' {recorded} completion(s) read from roadmap-state are already recorded in the files.'
        result.update(ok=True, exitCode=0, pending=0, message=message + ''.join(notes))
        return result
    sprints, files = sprint_targets(ctx, state, changes)
    unmatched = unmatched_lanes(state, changes)
    if unmatched:
        named = ', '.join(unmatched[:10]) + (f' and {len(unmatched) - 10} more' if len(unmatched) > 10 else '')
        notes.append(f' {len(unmatched)} lane(s) of the queue match no week or group ({named}): their changes reach '
                     'no sprint file through that lane and go to the roadmap. A week that already ended (the week turned) is '
                     'expected; tell the user about any other lane before apply.')
    resolved = {'roadmap': roadmap_path}
    for name, info in files.items():
        resolved[name] = safe_target(ctx.scrum_root, info['relative'])
    clash = len({os.path.normcase(p) for p in resolved.values()}) != len(resolved)
    require(not clash, 'Two targets resolve to the same file (' + ', '.join(sorted(resolved)) + '); fix roadmapFile, '
                       'weekFolderPattern or sprintFilePattern so each sprint has its own file.')
    nonce, minted = marker_nonce(ctx)
    result['markerNonceMinted'] = minted
    stamp, source = as_of(payload, changes)
    texts = {name: read_text(path) for name, path in resolved.items()}
    for change in changes:
        states = {marker_state(text, change['id'], nonce) for text in texts.values()} - {None}
        change['alreadyApplied'] = bool(states)
        change['markerState'] = 'applied' if 'applied' in states else 'declined' if states else None
        change['marker'] = marker_text(change['id'], nonce)
        change['declinedMarker'] = marker_text(change['id'], nonce, True)
        change['sprintTargets'] = [name for name, info in files.items() if change['id'] in info['changeIds']]
        del change['_created'], change['_move'], change['_sprints']
    run = secrets.token_hex(8)
    staging_new = ctx.staging_dir.with_name(ctx.staging_dir.name + '.new-' + run)
    staging_previous = ctx.staging_dir.with_name(ctx.staging_dir.name + '.previous-' + run)
    remove_stale_staging(ctx)
    staging_new.mkdir(parents=True)
    # A sprint file that does not exist yet is staged empty; apply creates its folder and file.
    leaves = {name: ('roadmap--' if name == 'roadmap' else f'sprint--{files[name]["sprint"]["sprintId"]}--') + Path(path).name
              for name, path in resolved.items()}
    for name, leaf in leaves.items():
        (staging_new / leaf).write_bytes((texts[name] or '').encode('utf-8'))
    write_manifest(staging_new, {leaf: sha256(staging_new / leaf) for leaf in leaves.values()})
    if ctx.staging_dir.exists():
        os.replace(ctx.staging_dir, staging_previous)
    os.replace(staging_new, ctx.staging_dir)
    remove_tree(staging_previous)
    plan_targets = {}
    for name, path in resolved.items():
        target = {'kind': 'roadmap' if name == 'roadmap' else 'sprint', 'path': path, 'exists': texts[name] is not None,
                  'sha256': sha256(path), 'staged': str(ctx.staging_dir / leaves[name])}
        if name != 'roadmap':
            info = files[name]
            target.update(sprintId=info['sprint']['sprintId'], title=info['sprint']['title'],
                          startDate=info['sprint']['startDate'], endDate=info['sprint']['endDate'],
                          createsFolder=not os.path.isdir(os.path.dirname(path)),
                          template=None if texts[name] is not None else sprint_template(ctx, *info['dates']),
                          changeIds=info['changeIds'])
        plan_targets[name] = target
    pending = [c['id'] for c in changes if not c['alreadyApplied']]
    # A completion that turned out to be marked after all (a marker in a file the first look did not cover) is recorded.
    completed.update(new=sum(1 for c in changes if c['synthetic'] and not c['alreadyApplied']),
                     alreadyRecorded=recorded + sum(1 for c in changes if c['synthetic'] and c['alreadyApplied']))
    start, end = paths['week']
    plan = {'schemaVersion': 1, 'project': ctx.name, 'markerNonceId': nonce_id(nonce), 'asOf': stamp, 'asOfSource': source,
            'stateAsOf': state['asOf'], 'week': {'start': start.isoformat(), 'end': end.isoformat()},
            'maxSprintItems': state['maxSprintItems'] or ctx.max_sprint_items, 'sprints': sprints,
            'targets': plan_targets, 'pending': pending, 'completed': completed, 'changes': changes}
    write_json_atomic(plan, ctx.plan_path)
    if pending:
        message = f'{len(pending)} change(s) to apply; {len(changes) - len(pending)} already marked.'
        if completed['new']:
            message += (f' {completed["new"]} completion(s) among them come from the done items of roadmap-state: they are not '
                        'in the RoadS queue and need no acknowledgement.')
    elif queued:
        message = 'Every returned change is already marked in the files; run ack to acknowledge them.'
    else:
        message = 'Every completion is already marked in the files; there is nothing to acknowledge.'
    if recorded:
        message += f' {recorded} completion(s) read from roadmap-state are already recorded in the files and are not offered again.'
    message += ''.join(notes)
    if minted:
        message += (' This run minted a new marker nonce, so no existing marker counts any more. If this project has synced '
                    'before, marker.json was lost: changes already written are offered again; check and decline duplicates.')
    try:
        result['sinceAvailable'] = read_json(ctx.state_path).get('lastAckAsOf')
    except (OSError, ValueError):
        result['sinceAvailable'] = None
    result.update(ok=True, exitCode=0, planPath=str(ctx.plan_path), since=query, plan=plan, message=message)
    return result


def op_apply(root, transport, no_ack=False, allow_shrink=False, confirm_declined=False):
    # Every apply result states what is on disk, a refusal included, so `written` and `backups`
    # are never left for the reader to infer from their absence.
    result = {'written': [], 'backups': []}
    try:
        return _apply(root, transport, no_ack, allow_shrink, confirm_declined, result)
    except (Refusal, ValueError, OSError, KeyError, TypeError) as error:
        result.update(ok=False, exitCode=1, message=str(error))
        return result


def _apply(root, transport, no_ack, allow_shrink, confirm_declined, result):
    ctx = Context(root)
    result['project'] = ctx.name
    plan = read_plan(ctx)
    require(not plan_finished(plan), 'This plan was already acknowledged (or needed no acknowledgement); run fetch again.')
    nonce = marker_record(ctx)['nonce']
    plan_ids = {c['id'] for c in plan['changes']}
    planned, seen = [], set()
    # Phase one decides everything and touches nothing; phase two only writes.
    for name, target in plan['targets'].items():
        relative = relative_to_root(ctx, target['path'])
        path = safe_target(ctx.scrum_root, relative)
        require(path == target['path'], 'The stored plan does not match the configuration; run fetch again.')
        require(os.path.normcase(path) not in seen, f'The plan resolves both targets to {path}. Nothing was written.')
        seen.add(os.path.normcase(path))
        require(os.path.isfile(target['staged']), (
            f'Staged copy missing for the {name} file; run fetch again. Nothing was written. If a fetch was interrupted, '
            f'the draft may be in a {ctx.staging_dir.name}.previous-* folder; copy it out first.'))
        staged = Path(target['staged']).read_bytes().decode('utf-8-sig', 'replace')
        current = read_text(path)
        if (current is None and not staged) or (current is not None and staged == current):
            continue
        current_sha = sha256(path)
        require(current_sha == target['sha256'] or (target.get('appliedSha256') and current_sha == target['appliedSha256']),
                f'The {name} file changed after the plan was made ({path}). Nothing was written; sync again.')
        if current and not allow_shrink and len(staged) < int(len(current) * SHRINK_RATIO):
            raise Refusal(f'Refusing to write the {name} file: the staged copy has {len(staged)} characters against {len(current)} '
                          f'in {path}, dropping {len(current) - len(staged)}. Nothing was written. Show the user the diff; only '
                          'their confirmation lets it through (--allow-shrink).')
        current_markers, staged_markers = marker_inventory(current, nonce), marker_inventory(staged, nonce)
        lost = [i for i in current_markers if i not in staged_markers]
        if lost and not allow_shrink:
            raise Refusal(f'Refusing to write the {name} file: the staged copy lost the marker of {", ".join(lost)} that {path} '
                          'carries now, so it drops content a previous run wrote. Nothing was written. Show the user those '
                          'entries; they decide.')
        invented = [i for i in staged_markers if i not in current_markers and i not in plan_ids]
        require(not invented, f'Refusing to write the {name} file: the staged copy carries a marker for {", ".join(invented)}, '
                              'which is not in this plan. Nothing was written. Copy markers from the plan only.')
        planned.append((name, target, path, relative, staged))
    written, backups = [], []
    try:
        for name, target, path, relative, staged in planned:
            # Checked again before a missing folder is created, so mkdir cannot follow a junction
            # that appeared after fetch, and again before the write.
            safe_target(ctx.scrum_root, relative)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            safe_target(ctx.scrum_root, relative)
            replaced = os.path.isfile(path)
            backup = new_backup_path(path) if replaced else None
            write_text_atomic(path, staged, has_bom(path), backup)
            written.append(path)
            if backup:
                backups.append(str(backup))
            target['appliedSha256'] = sha256(path)
    finally:
        result['written'], result['backups'] = written, backups
        if written:
            try:
                write_json_atomic(plan, ctx.plan_path)
            except OSError:
                pass
            mark_staging_applied(ctx.staging_dir)
    if not planned:
        mark_staging_applied(ctx.staging_dir)
    missing, declined = marker_report(plan, nonce)
    if missing:
        result.update(ok=False, exitCode=1, missingMarkers=missing, message=(
            'Written, but these changes have no marker in either file, so nothing was acknowledged: ' + ', '.join(missing)
            + '. Add the markers to the staged copies and run apply again; this run\'s own write does not block the retry.'))
        return result
    result['verified'] = True
    # A plan with nothing but completions has nothing to withhold: --no-ack leaves it open for no reason.
    if no_ack and has_queued_changes(plan):
        declined, declined_completions = split_declined(plan, declined)
        if declined:
            result['declined'] = declined
        if declined_completions:
            result['declinedCompletions'] = declined_completions
        result.update(ok=True, exitCode=0, ack='not requested', message='Written and verified; not acknowledged (--no-ack).')
        return result
    code = do_ack(ctx, transport, plan, result, nonce, confirm_declined)
    result.update(ok=code == 0, exitCode=code)
    if code == 0 and result.get('ack') == 'sent':
        result['message'] = f'Written, verified and acknowledged up to {plan["asOf"]}.'
    return result


def op_ack(root, transport, confirm_declined=False):
    ctx = Context(root)
    result = {'project': ctx.name}
    plan = read_plan(ctx)
    code = do_ack(ctx, transport, plan, result, marker_record(ctx)['nonce'], confirm_declined)
    result.update(ok=code == 0, exitCode=code)
    if code == 0 and result.get('ack') == 'sent':
        result['message'] = f'Acknowledged up to {plan["asOf"]}.'
    return result


def op_rotate(root, today):
    ctx = Context(root)
    record = marker_record(ctx)
    require(record, 'There is no marker nonce to rotate; run fetch first.')
    edits = staging_edits(ctx.staging_dir)
    require(not edits, f'Refusing to rotate: the staging directory holds drafted prose never applied ({", ".join(edits)}).')
    if ctx.plan_path.is_file():
        try:
            pending = read_json(ctx.plan_path)
        except (OSError, ValueError):
            pending = None
        require(not pending or plan_finished(pending) or not has_queued_changes(pending),
                'Refusing to rotate: a plan has not been acknowledged. Finish or discard it first.')
        if pending and not plan_finished(pending):
            # Only completions, which are not in the RoadS queue: nothing there waits for this plan, and its
            # markers are about to be replaced. It is finished; the next fetch makes a new one.
            pending['discardedAt'] = now_iso()
            write_json_atomic(pending, ctx.plan_path)
    paths = targets(ctx, today)
    fresh = new_nonce()
    rewritten, backups, rotated = [], [], []
    for name in ('roadmap', 'sprint'):
        path = safe_target(ctx.scrum_root, paths[name])
        text = read_text(path)
        if text is None:
            continue
        inventory = marker_inventory(text, record['nonce'])
        updated = text
        for change_id, state in inventory.items():
            updated = re.sub(marker_pattern(change_id, record['nonce']),
                             marker_text(change_id, fresh, state == 'declined').replace('\\', r'\\'), updated)
            rotated.append(change_id)
        if updated == text:
            continue
        backup = new_backup_path(path)
        write_text_atomic(path, updated, has_bom(path), backup)
        rewritten.append(path)
        backups.append(str(backup))
    write_marker_record(ctx, fresh, rotated=True)
    rotated = sorted(set(rotated))
    return {'ok': True, 'exitCode': 0, 'project': ctx.name, 'rewritten': rewritten, 'backups': backups,
            'rotatedMarkers': rotated, 'message': (
                f'Marker nonce rotated. Rewrote {len(rotated)} marker(s) in {len(rewritten)} file(s). Markers in earlier '
                "weeks' sprint files were not rewritten and no longer count; decline those changes if offered again.")}


# ---------------------------------------------------------------- gaps: complete what RoadS leaves out

def clean(value, limit=GAPS_TITLE_LIMIT):
    """Text read from GitHub is data: no markup or control characters, and a bounded length."""
    return re.sub(r'[<>\x00-\x1f\x7f]', '', str(value))[:limit]


def gh_environment():
    """gh has no use for the RoadS credential, so it does not get it."""
    return {name: value for name, value in os.environ.items() if not re.fullmatch(SECRET_ENV_PATTERN, name)}


def gh_default(argv):
    """Run `gh` without a shell and return its JSON answer. The credential is gh's own login; the
    answer's text is data. A failure never repeats gh's output, which could carry anything."""
    # gh writes UTF-8; the console code page would turn "Repositório" into mojibake and no field name would match.
    try:
        done = subprocess.run([*GH_COMMAND, *argv], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL, env=gh_environment())
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal('gh could not be run; check that it is installed and logged in')
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = None
    # gh exits 1 for a GraphQL answer that carries `errors` (an issue that does not exist, say) yet still
    # prints it with its `data`: the caller decides which errors it tolerates.
    if isinstance(answer, dict) and isinstance(answer.get('data'), dict) and answer.get('errors'):
        return answer
    if done.returncode != 0:
        raise Refusal('gh refused the GitHub read; check the active account, the repository access and the '
                      'project scope (gh auth refresh -s project)')
    require(answer is not None, 'gh answered with something that is not JSON')
    return answer


_FIELD_NAME = '... on ProjectV2FieldCommon { name }'
ISSUE_VIEW = '''number state title url
  labels(first: 100) { totalCount nodes { name } }
  assignees(first: 20) { totalCount nodes { login } }
  issueType { name }
  projectItems(first: 20) { totalCount nodes {
    project { number owner { ... on Organization { login } ... on User { login } } }
    fieldValues(first: 50) { totalCount nodes {
      ... on ProjectV2ItemFieldSingleSelectValue { name field { %(f)s } }
      ... on ProjectV2ItemFieldTextValue { text field { %(f)s } }
      ... on ProjectV2ItemFieldNumberValue { number field { %(f)s } }
      ... on ProjectV2ItemFieldDateValue { date field { %(f)s } }
      ... on ProjectV2ItemFieldIterationValue { title field { %(f)s } }
    } }
  } }''' % {'f': _FIELD_NAME}

BOARD_FIELDS = '''id
  fields(first: 100) { nodes {
    ... on ProjectV2SingleSelectField { name options { name } }
    ... on ProjectV2IterationField { name }
    ... on ProjectV2Field { name dataType }
  } }'''


def graphql(gh, query, missing_ok=()):
    """One GraphQL read. An error is tolerated only when it is NOT_FOUND for one of the issue aliases the
    caller named (GitHub answers a deleted or transferred number that way, with the alias null)."""
    answer = gh(['api', 'graphql', '-H', 'GraphQL-Features: issue_types', '-f', 'query=' + query])
    require(isinstance(answer, dict) and isinstance(answer.get('data'), dict),
            'GitHub answered the read with an error; check the repository, the project and the gh scopes')
    errors = answer.get('errors') or []
    require(isinstance(errors, list), 'GitHub answered the read with an error; check the repository, the project and the gh scopes')
    for error in errors:
        path = error.get('path') if isinstance(error, dict) else None
        require(isinstance(error, dict) and error.get('type') == 'NOT_FOUND' and isinstance(path, list) and len(path) == 2
                and path[0] == 'repository' and isinstance(path[1], str) and path[1] in missing_ok,
                'GitHub answered the read with an error; check the repository, the project and the gh scopes')
    return answer['data']


def board_layout(gh, board):
    """The board's fields and, for a single select, its options: what a chosen value must be one of.
    Names are kept as GitHub spells them, because the rules compare them to the configuration; they are
    cleaned only when shown."""
    data = graphql(gh, 'query { owner: repositoryOwner(login: "%s") { ... on ProjectV2Owner { project: projectV2(number: %d) { %s } } } }'
                   % (board['owner'], board['number'], BOARD_FIELDS))
    owner = data.get('owner')
    project = owner.get('project') if isinstance(owner, dict) else None
    # GitHub answers an unknown login with a null owner and no error: say so, never read it as an empty board.
    require(isinstance(project, dict), f'the board {board["owner"]}/{board["number"]} was not found; check project.owner and project.number')
    nodes = ((project.get('fields') or {}).get('nodes')) or []
    layout = {}
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get('name'), str):
            if isinstance(node.get('options'), list):
                layout[node['name']] = {'type': 'single_select',
                                        'options': [o['name'] for o in node['options'] if isinstance(o, dict) and isinstance(o.get('name'), str)]}
            elif 'dataType' in node:
                layout[node['name']] = {'type': str(node.get('dataType') or 'other').lower(), 'options': None}
            else:
                layout[node['name']] = {'type': 'iteration', 'options': None}
    return layout


def shown_field(info):
    """A layout entry as the session sees it: cleaned names, plus the options it must never type, which are
    those cleaning changed (the cleaned name does not exist on the board) or a command line could not carry."""
    if info is None:
        return {'type': 'unknown', 'options': None}
    options = info['options']
    shown = {'type': info['type'], 'options': None if options is None else [clean(o) for o in options]}
    if options:
        shown['unwritable'] = [clean(o) for o in options if clean(o) != o or frontlights.UNSAFE_CHARS.search(o)]
    return shown


def cut(connection):
    """The nodes of a GraphQL connection, and whether the page did not hold all of them."""
    connection = connection if isinstance(connection, dict) else {}
    nodes = [node for node in (connection.get('nodes') or []) if isinstance(node, dict)]
    total = connection.get('totalCount')
    return nodes, isinstance(total, int) and total > len(connection.get('nodes') or [])


def card_text(value):
    for key in ('name', 'text', 'date', 'title', 'number'):
        if value.get(key) is not None and not isinstance(value[key], (dict, list, bool)):
            text = str(value[key])
            return text if text.strip() else None
    return None


def read_issues(gh, repository, numbers, board):
    """Labels, assignees, native type and the card on the configured board of each issue number. A number
    GitHub does not know comes back as None; an issue whose labels, assignees, cards or card values did not
    fit one page is marked `truncated`, because a value cut off would read as empty."""
    repo_owner, repo_name = repository.split('/')
    views = {}
    for start in range(0, len(numbers), GAPS_BATCH):
        chunk = numbers[start:start + GAPS_BATCH]
        body = ' '.join(f'i{n}: issue(number: {n}) {{ {ISSUE_VIEW} }}' for n in chunk)
        data = graphql(gh, 'query { repository(owner: "%s", name: "%s") { %s } }' % (repo_owner, repo_name, body),
                       missing_ok={f'i{n}' for n in chunk})
        repo = data.get('repository') or {}
        for n in chunk:
            raw = repo.get(f'i{n}')
            if not isinstance(raw, dict):
                views[n] = None
                continue
            labels, cut_labels = cut(raw.get('labels'))
            assignees, cut_assignees = cut(raw.get('assignees'))
            items, cut_items = cut(raw.get('projectItems'))
            truncated = cut_labels or cut_assignees or cut_items
            card = None
            for item in items:
                project = item.get('project')
                card_owner = project.get('owner') if isinstance(project, dict) else None
                card_login = card_owner.get('login') if isinstance(card_owner, dict) else None
                if (isinstance(project, dict) and isinstance(card_login, str)
                        and project.get('number') == board['number'] and card_login.casefold() == board['owner'].casefold()):
                    card = {}
                    values, cut_values = cut(item.get('fieldValues'))
                    truncated = truncated or cut_values
                    for value in values:
                        field = (value.get('field') or {}).get('name')
                        text = card_text(value)
                        if isinstance(field, str) and field and text:
                            card[field] = text
            # Labels, assignees, type and card values stay as GitHub spells them: the rules compare them to the
            # configuration. `shown_view` cleans them when they are put in front of the session.
            views[n] = {'number': n, 'state': raw.get('state'), 'url': clean(raw.get('url') or ''),
                        'title': clean(raw.get('title') or ''),
                        'labels': [x['name'] for x in labels if isinstance(x.get('name'), str) and x['name']],
                        'assignees': [x['login'] for x in assignees if isinstance(x.get('login'), str) and x['login']],
                        'issueType': raw['issueType']['name'] if isinstance(raw.get('issueType'), dict) and isinstance(raw['issueType'].get('name'), str) and raw['issueType']['name'] else None,
                        'card': card, 'truncated': truncated}
    return views


def shown_view(view):
    """What of an issue is put in front of the session: everything GitHub wrote is cleaned and bounded."""
    return {'labels': [clean(x) for x in view['labels']], 'assignees': [clean(x) for x in view['assignees']],
            'issueType': clean(view['issueType']) if view['issueType'] else None,
            'fields': {clean(name): clean(value) for name, value in (view['card'] or {}).items()}}


# What the documented write commands can set. Anything else (an iteration, say) is reported, never tried.
WRITABLE_TYPES = ('single_select', 'text', 'number', 'date')


def issue_gaps(board, view, layout=None):
    """What one issue lacks against the board rules. `fill` holds values the configuration settles by
    itself (a field default, a label a field value implies, the board's assignee and type); `choose`
    holds what only a person can decide, which the session proposes and the user approves. A label a
    field value implies is filled only when the issue has no other label of that family; otherwise it is a
    `labelConflicts` entry for the user to settle, never written on top of the label that is there. A
    default that is not one of the board's options (`layout`) is `staleDefaults`: chosen again, not written.
    Labels are compared without regard to case, as GitHub does."""
    card = view['card']
    current = card or {}
    have = list(view['labels'])
    have_fold = {label.casefold() for label in have}
    fill, choose = {}, {}
    if card is None:
        fill['addToBoard'] = True
    fields_fill = {name: default for name, default in board['fields'].items() if not current.get(name) and default is not None}
    stale, blocked = [], []
    for name, default in list(fields_fill.items()) if layout is not None else []:
        info = layout.get(name)
        if info is None or info['type'] not in WRITABLE_TYPES or (info['type'] == 'single_select' and not info['options']):
            # Not on the board, of a type the write commands cannot set, or with no options: never written.
            blocked.append(name)
            del fields_fill[name]
        elif info['type'] == 'single_select' and default not in info['options']:
            stale.append(name)
            del fields_fill[name]
    fields_choose = [name for name, default in board['fields'].items()
                     if not current.get(name) and (default is None or name in stale or name in blocked)]
    values = {**current, **fields_fill}
    implied = []
    for field, mapping in board['labels']['by_field'].items():
        for label in mapping.get(values.get(field), []):
            if label not in implied:
                implied.append(label)
    derived, conflicts = [], []
    twins = frontlights.family_twins([mapping.get(values.get(field), []) for field, mapping in board['labels']['by_field'].items()])
    for label in implied:
        if label.casefold() in have_fold:
            continue
        (conflicts if label in twins or frontlights.clashes(label, have, implied) else derived).append(label)
    families = [prefix for prefix in board['labels']['require_prefix']
                if not any(label.casefold().startswith(prefix.casefold()) for label in have)]
    follow = [field for field in board['labels']['by_field'] if field not in values]
    if fields_fill:
        fill['fields'] = fields_fill
    if derived:
        fill['labels'] = derived
    if not view['assignees'] and board['assignee']:
        fill['assignee'] = board['assignee']
    if view['issueType'] is None:
        by_label = {label.casefold(): kind for label, kind in board['issue_type_by_label'].items()}
        kind = next((by_label[label.casefold()] for label in have + derived if label.casefold() in by_label), None)
        if families and not kind:
            choose['issueType'] = True
        elif kind or board['issue_type']:
            fill['issueType'] = kind or board['issue_type']
        else:
            choose['issueType'] = True
    if fields_choose:
        choose['fields'] = fields_choose
    if stale:
        choose['staleDefaults'] = stale
    if families:
        choose['labelPrefixes'] = families
    if follow:
        choose['labelsFollowFields'] = follow
    if conflicts:
        choose['labelConflicts'] = conflicts
    return fill, choose


def op_gaps(root, transport, gh=None, only_sprints=False):
    """Read-only: list the issues RoadS shows that still lack what the project's board rules ask for,
    each with what the configuration fills by itself and what needs a choice. Nothing is written to
    GitHub, to RoadS or to any file; the writes follow the approved table, with the session's own gh."""
    gh = gh or gh_default
    ctx = Context(root)
    repository = ctx.repository
    result = {'project': ctx.name}
    if not repository or ctx.project is None:
        result.update(ok=True, exitCode=0, board='unconfigured', issues=[],
                      message='This project has no repository or no project board in .frontlights/config.json, '
                              'so there is nothing to check against. Nothing was read.')
        return result
    require(frontlights.repository(repository), 'repository in .frontlights/config.json must be owner/name')
    board = frontlights.board(ctx.project, repository)
    read_secret(ctx.secret_env)
    assert_approved(ctx)
    state = read_state(ctx, transport)
    origin, skipped = {}, []
    lanes = [('sprint', sprint['title'] or sprint['sprintId'], sprint['items']) for sprint in state['sprints']]
    if not only_sprints:
        lanes += [('group', group['title'] or group['laneId'], group['items']) for group in state['groups']]
    for kind, lane, items in lanes:
        for item in items:
            if not item['githubIssueUrl']:
                continue
            match = ISSUE_URL.fullmatch(item['githubIssueUrl'])
            if not match:
                skipped.append({'url': clean(item['githubIssueUrl']), 'reason': 'not the URL of an issue'})
            elif f'{match.group(1)}/{match.group(2)}'.casefold() != repository.casefold():
                skipped.append({'url': clean(item['githubIssueUrl']), 'reason': 'outside the configured repository'})
            else:
                origin.setdefault(int(match.group(3)), {'kind': kind, 'lane': clean(lane)})
    numbers = sorted(origin)
    base = {'board': {'owner': board['owner'], 'number': board['number']}, 'repository': repository, 'stateAsOf': state['asOf'],
            'skipped': skipped, 'issues': [], 'fields': {}, 'unfillable': [], 'notOnBoard': [],
            'rules': {'labels': board['labels'], 'issueTypeByLabel': board['issue_type_by_label'],
                      'issueType': board['issue_type'], 'bodyFields': board['body_fields'],
                      'labelName': frontlights.LABEL_RULE, 'labelPattern': frontlights.LABEL_NAME.pattern,
                      'neverTyped': frontlights.UNTYPEABLE_NAMES}}
    if not numbers:
        result.update(ok=True, exitCode=0, checked=0, complete=0, closed=0, notFound=0, **base,
                      message='RoadS shows no issue of the configured repository to check'
                              + (f' ({len(skipped)} skipped; see skipped).' if skipped else '.'))
        return result
    layout = board_layout(gh, board)
    views = read_issues(gh, repository, numbers, board)
    issues, complete, closed, missing = [], 0, 0, 0
    for n in numbers:
        view = views.get(n)
        if view is None:
            missing += 1
            continue
        if view['state'] != 'OPEN':
            closed += 1
            continue
        if view['truncated']:
            skipped.append({'url': view['url'], 'reason': 'more labels, assignees or board values than one read holds; check it by hand'})
            continue
        fill, choose = issue_gaps(board, view, layout)
        if not fill and not choose:
            complete += 1
            continue
        issues.append({'number': n, 'url': view['url'], 'title': view['title'], 'from': origin[n],
                       'present': shown_view(view), 'fill': fill, 'choose': choose})
    # Every field the session may be told to write or to choose gets its layout (type and options), so it knows
    # which flag sets it; the ones that cannot be written at all are the `unfillable` below.
    asked = sorted({name for issue in issues for name in [*issue['choose'].get('fields', []), *issue['fill'].get('fields', {})]})
    fields = {name: shown_field(layout.get(name)) for name in asked}
    not_on_board = sorted(name for name in asked if name not in layout)
    unfillable = sorted(name for name in asked if name not in layout or layout[name]['type'] not in WRITABLE_TYPES
                        or (layout[name]['type'] == 'single_select' and not layout[name]['options']))
    base.update(issues=issues, fields=fields, unfillable=unfillable, notOnBoard=not_on_board)
    result.update(ok=True, exitCode=0, checked=len(numbers) - missing, complete=complete, closed=closed, notFound=missing, **base)
    result['message'] = (f'{len(issues)} issue(s) lack something; {complete} are complete; {closed} closed were left alone.'
                         if issues else f'Every open issue RoadS shows is complete against the board rules ({complete} checked).')
    if skipped:
        result['message'] += f' {len(skipped)} skipped; see skipped.'
    if missing:
        result['message'] += f' {missing} number(s) GitHub does not know were left out (notFound).'
    if unfillable:
        result['message'] += (f' These board fields cannot be filled: {", ".join(unfillable)} (no options on the board, not on the '
                              'board, or of a type this helper cannot write); someone has to deal with them first.')
    return result


def run(operation, root='.', today=None, transport=None, since=None, no_ack=False, allow_shrink=False,
        confirm_declined=False, discard_staged=False, gh=None, only_sprints=False):
    today = today or sao_paulo_today()
    transport = transport or http_default
    try:
        if operation == 'status':
            result = op_status(root, today)
        elif operation == 'approve':
            result = op_approve(root)
        elif operation == 'fetch':
            result = op_fetch(root, today, transport, since, discard_staged)
        elif operation == 'apply':
            result = op_apply(root, transport, no_ack, allow_shrink, confirm_declined)
        elif operation == 'ack':
            result = op_ack(root, transport, confirm_declined)
        elif operation == 'rotate-markers':
            result = op_rotate(root, today)
        elif operation == 'gaps':
            result = op_gaps(root, transport, gh, only_sprints)
        else:
            raise Refusal(f'Unknown operation: {operation}')
    except (Refusal, ValueError, OSError, KeyError, TypeError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    result['operation'] = operation
    result.setdefault('ok', result.get('exitCode') == 0)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=['status', 'approve', 'fetch', 'apply', 'ack', 'rotate-markers', 'gaps'])
    parser.add_argument('--only-sprints', action='store_true', help='gaps: leave the backlog groups out and check the sprints only')
    parser.add_argument('--root', default='.', help='project whose .frontlights/config.json declares roadmapSync')
    parser.add_argument('--since', help='ISO 8601; adds since=<stamp> to pending-changes. Never filled in automatically.')
    parser.add_argument('--no-ack', action='store_true')
    parser.add_argument('--allow-shrink', action='store_true', help="the user's confirmation that a file may lose content")
    parser.add_argument('--confirm-declined', action='store_true', help="the user's confirmation of every declined id")
    parser.add_argument('--discard-staged', action='store_true', help='let fetch replace a draft that was never applied')
    args = parser.parse_args()
    result = run(args.operation, args.root, since=args.since, no_ack=args.no_ack, allow_shrink=args.allow_shrink,
                 confirm_declined=args.confirm_declined, discard_staged=args.discard_staged,
                 only_sprints=args.only_sprints)
    print(protect(json.dumps(result, indent=2, ensure_ascii=True)))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
