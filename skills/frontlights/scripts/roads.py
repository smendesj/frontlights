#!/usr/bin/env python3
"""RoadS helpers: the `roadmapSync` block, its credential and approval, and the issue gaps.

Deterministic helper behind the issue-gaps question of /frontlights and the shared base of
progress_report.py, closeout.py and cleanup.py: the configuration, the credential, the first-use
approval, the HTTP transport, path safety under scrumRoot and the GitHub reader. Frontlights no
longer writes ROADMAP.md or SPRINT_*.md: RoadS keeps the roadmap from the open issues, and the week
folders under scrumRoot only hold the files a step saves there (the prints of the summary).

Operations (each prints one JSON object on stdout):
  status    configuration, credential presence and approval of the (endpoint URL, secretEnvVar) pair,
            plus `obsoleteKeys`, the keys of the retired roadmap sync still in the block (ignored). No
            network, never fails for a missing configuration.
  approve   record the user's approval of that pair. Run only after the user said yes in the
            conversation.
  gaps      read only: GET <endpoint>/roadmap-state, then read on GitHub (gh api graphql) the issues of
            the configured repository that RoadS shows, and list what each still lacks against the
            project's board rules: `fill` is what the configuration settles by itself, `choose` what
            needs a person. Writes nothing anywhere; --only-sprints skips the backlog groups.

Exit codes: 0 done; 1 refused (the message says why; nothing was written).

The credential is read from the environment only (on Windows also the value saved with `setx`),
sent only in the Authorization header to the approved endpoint, never written, and redacted from
every string this helper prints. The approval stays in `.frontlights/roadmap-sync/approval.json`, where
the retired roadmap sync kept it, so an existing approval still holds.
"""

import argparse
import datetime as dt
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

GH_COMMAND = ['gh']
GH_TIMEOUT = 60
GAPS_BATCH = 20
GAPS_TITLE_LIMIT = 200
ISSUE_URL = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]{0,8})')
MAX_BODY_BYTES = 5 * 1024 * 1024
SECRET_ENV_PATTERN = r'^FRONTLIGHTS_[A-Z0-9_]+$'
ID_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'
FIELD_LIMITS = {'title': 400, 'description': 4000, 'produto': 200, 'prioridade': 100, 'effort': 100,
                'laneId': 200, 'githubIssueUrl': 500, 'timezone': 100}
# Keys of the retired roadmap sync: still accepted in the block, ignored, and named by `status`.
OBSOLETE_KEYS = ('roadmapFile', 'sprintFilePattern', 'maxSprintItems', 'markCompleted', 'issueTargets')
STATE_SCHEMA_VERSION = 1
STATE_YEARS = (2000, 2100)
ITEM_STATUSES = ('open', 'development', 'blocker', 'done', 'none')
SNAPSHOT_MAX_AGE = dt.timedelta(hours=24)
REPARSE_POINT = 0x400
OFFLINE_MASK = 0x1000 | 0x40000 | 0x400000  # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS

_SECRETS = []


class Refusal(Exception):
    """A deliberate refusal: the message is safe to show the user."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def now_iso():
    return dt.datetime.now().astimezone().isoformat()


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
                'This project does not enable RoadS: add a roadmapSync block with "enabled": true to .frontlights/config.json.')
        self.sync = sync
        self.endpoint = validate_endpoint(sync.get('endpoint'))
        self.secret_env = sync.get('secretEnvVar')
        require(isinstance(self.secret_env, str) and re.fullmatch(SECRET_ENV_PATTERN, self.secret_env),
                'roadmapSync.secretEnvVar must match ^FRONTLIGHTS_[A-Z0-9_]+$')
        self.obsolete_keys = [key for key in OBSOLETE_KEYS if key in sync]
        self.approval_path = self.config_path.parent / 'roadmap-sync' / 'approval.json'
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
    require(state == 'approved', f'RoadS is not approved to send {pair["secretEnvVar"]} to {pair["endpoint"]} '
                                 f'({why}). Ask the user; only after an explicit yes run the approve operation.')


# ---------------------------------------------------------------- week folders and paths

def expand_pattern(pattern, start, end):
    count = [0]

    def dd_mm(_match):
        count[0] += 1
        return (start if count[0] == 1 else end).strftime('%d_%m')
    text = re.sub(r'\{dd_MM\}', dd_mm, pattern)
    return text.replace('{yyyy}', start.strftime('%Y')).replace('{MM}', start.strftime('%m')).replace('{dd}', start.strftime('%d'))



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
            f'RoadS returned an HTML comment sequence in {field}; the whole answer was refused')
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


def _state_refusal(field, what):
    return f'RoadS returned a roadmap-state whose {field} {what}; the whole answer was refused'


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
    # Week arithmetic overflows near year 1 and 9999.
    require(STATE_YEARS[0] <= parsed.year <= STATE_YEARS[1],
            _state_refusal(field, f'is outside the years {STATE_YEARS[0]} to {STATE_YEARS[1]}'))
    return parsed


def state_item(raw, where):
    require(isinstance(raw, dict), _state_refusal(where, 'is not an object'))
    item_id = state_id(raw.get('id'), f'{where}.id')
    where = f'{where} ({item_id})'
    url = state_text(raw.get('githubIssueUrl'), f'{where}.githubIssueUrl', FIELD_LIMITS['githubIssueUrl'])
    if not re.fullmatch(r'https?://[^\s<>"]+', url) or re.search(r'&(?:lt|gt);', url):
        url = ''
    status = raw.get('status')
    require(status in ITEM_STATUSES, _state_refusal(f'{where}.status', 'is not one of ' + '|'.join(ITEM_STATUSES)))
    updated = state_time(raw.get('updatedAt'), f'{where}.updatedAt')
    return {
        'id': item_id, 'position': state_int(raw.get('position'), f'{where}.position', 1),
        'title': state_text(raw.get('title'), f'{where}.title', FIELD_LIMITS['title'], optional=False),
        'description': state_text(raw.get('description'), f'{where}.description', FIELD_LIMITS['description']),
        'produto': state_text(raw.get('produto'), f'{where}.produto', FIELD_LIMITS['produto']),
        'prioridade': state_text(raw.get('prioridade'), f'{where}.prioridade', FIELD_LIMITS['prioridade']),
        'effort': state_text(raw.get('effort'), f'{where}.effort', FIELD_LIMITS['effort']),
        'githubIssueUrl': url or None, 'issueNumber': state_int(raw.get('issueNumber'), f'{where}.issueNumber', 1, optional=True),
        'status': status, 'done': state_bool(raw.get('done'), f'{where}.done'),
        'updatedAt': updated[0] if updated else None}


def normalise_state(payload):
    """Defensive reading of GET roadmap-state (schemaVersion 1). An unknown schema version, a
    field of the wrong type, an invalid date or a duplicate sprint refuses the whole answer:
    nothing is guessed. Fields gaps does not use (the queue of the retired roadmap sync, the sprint
    limit) are not read. Each sprint is a week; the weeks
    come out in the order of their dates (start, then end), never in the order of the text of their
    ids, which RoadS writes either as `sprint-YYYY-MM-DD` with a positional laneId (before its
    migration) or as `sprint-DD-MM-YYYY` for both sprintId and laneId (after it)."""
    require(isinstance(payload, dict), 'RoadS answered roadmap-state with something that is not an object')
    version = payload.get('schemaVersion')
    require(isinstance(version, int) and not isinstance(version, bool) and version == STATE_SCHEMA_VERSION,
            f'RoadS answered roadmap-state with a schemaVersion that is not {STATE_SCHEMA_VERSION}, the only one understood. '
            'Nothing was checked; update Frontlights or take it to the RoadS owner.')
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
        items = [state_item(item, f'{where}.items[{n}]') for n, item in enumerate(state_list(raw.get('items'), f'{where}.items'))]
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
                       'items': [state_item(item, f'{where}.items[{n}]')
                                 for n, item in enumerate(state_list(raw.get('items'), f'{where}.items'))]})
    stale = synced is None or state_as_of[1] - synced[1] > SNAPSHOT_MAX_AGE
    return {'asOf': state_as_of[0], 'snapshotSyncedAt': synced[0] if synced else None, 'snapshotStale': stale,
            'timezone': state_text(payload.get('timezone'), 'timezone', FIELD_LIMITS['timezone']),
            'sprints': sprints, 'groups': groups}


# ---------------------------------------------------------------- transport

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def user_agent():
    """`frontlights-roadmap-sync/<commit>` (a name the RoadS contract fixes, docs/roads-contract.md), the skill checkout's `HEAD` (12 hex digits), so the service can tell this
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


# ---------------------------------------------------------------- operations

def op_status(root):
    result = {'configured': False, 'enabled': False}
    try:
        ctx = Context(root)
    except (Refusal, ValueError, OSError) as error:
        # An enabled block that does not validate is the user's mistake to hear about, not a project without RoadS.
        try:
            sync = read_json(config_path(root)).get('roadmapSync')
            result['enabled'] = isinstance(sync, dict) and sync.get('enabled') is True
        except (TypeError, AttributeError, ValueError, OSError):
            pass
        result.update(ok=True, exitCode=0, ready=False, message=str(error))
        return result
    state, pair, _ = approval_state(ctx)
    secret = 'present' if secret_present(ctx.secret_env) else 'absent'
    ready = secret == 'present' and state == 'approved'
    result.update(configured=True, enabled=True, project=ctx.name, secretEnvVar=ctx.secret_env, secret=secret, approval=state,
                  endpoint=pair['endpoint'], ready=ready, obsoleteKeys=ctx.obsolete_keys, ok=True, exitCode=0,
                  message='RoadS is ready.' if ready else 'RoadS is not ready; see the fields above.')
    if ctx.obsolete_keys:
        result['message'] += (' The block still carries keys of the retired roadmap sync, which are ignored: '
                              + ', '.join(ctx.obsolete_keys) + '.')
    return result


def op_approve(root):
    ctx = Context(root)
    pair = approval_pair(ctx)
    write_json_atomic({'schemaVersion': 1, **pair, 'approvedAt': now_iso()}, ctx.approval_path)
    return {'ok': True, 'exitCode': 0, 'project': ctx.name, 'approval': 'approved', **pair,
            'message': f'Approved: {pair["secretEnvVar"]} may be sent to {pair["endpoint"]}.'}


def read_state(ctx, transport):
    """GET <endpoint>/roadmap-state: the sprints and groups whose issues gaps checks."""
    try:
        text = request(ctx, transport, 'GET', endpoint_url(ctx.endpoint, 'roadmap-state'))
        payload = json.loads(text)
    except (Refusal, ValueError) as error:
        detail = str(error) if isinstance(error, Refusal) else 'the body is not JSON'
        raise Refusal(f'Could not read roadmap-state from RoadS ({detail}); nothing was checked.')
    return normalise_state(payload)



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
            'snapshotSyncedAt': state['snapshotSyncedAt'], 'snapshotStale': state['snapshotStale'],
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


def run(operation, root='.', transport=None, gh=None, only_sprints=False):
    transport = transport or http_default
    try:
        if operation == 'status':
            result = op_status(root)
        elif operation == 'approve':
            result = op_approve(root)
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
    parser.add_argument('operation', choices=['status', 'approve', 'gaps'])
    parser.add_argument('--only-sprints', action='store_true', help='gaps: leave the backlog groups out and check the sprints only')
    parser.add_argument('--root', default='.', help='project whose .frontlights/config.json declares roadmapSync')
    args = parser.parse_args()
    result = run(args.operation, args.root, only_sprints=args.only_sprints)
    print(protect(json.dumps(result, indent=2, ensure_ascii=True)))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
