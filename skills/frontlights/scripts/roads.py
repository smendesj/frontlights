#!/usr/bin/env python3
"""RoadS helpers: the `roadmapSync` block, its credential and approval.

The shared base of progress_report.py, closeout.py and cleanup.py: the configuration, the credential, the
first-use approval, the HTTP transport, path safety under scrumRoot and the GitHub reader. Frontlights no
longer writes ROADMAP.md or SPRINT_*.md and no longer reads roadmap-state: RoadS keeps the roadmap from the
open issues, and the week folders under scrumRoot only hold the files a step saves there (the prints of the
summary and of the watched runs).

Operations (each prints one JSON object on stdout):
  status    configuration, credential presence and approval of the (endpoint URL, secretEnvVar) pair,
            plus `obsoleteKeys`, the keys of the retired roadmap sync still in the block (ignored). No
            network, never fails for a missing configuration.
  approve   record the user's approval of that pair. Run only after the user said yes in the
            conversation.

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
import _cli  # noqa: E402  (defaults of --root and --config, the parser and UTF-8)

GH_COMMAND = ['gh']
GH_TIMEOUT = 60
GAPS_BATCH = 20        # issues per GraphQL read of the closeout
GAPS_TITLE_LIMIT = 200  # length of a title read from GitHub
MAX_BODY_BYTES = 5 * 1024 * 1024
SECRET_ENV_PATTERN = r'^FRONTLIGHTS_[A-Z0-9_]+$'
ID_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'
# Keys of the retired roadmap sync: still accepted in the block, ignored, and named by `status`.
OBSOLETE_KEYS = ('roadmapFile', 'sprintFilePattern', 'maxSprintItems', 'markCompleted', 'issueTargets')
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


# ---------------------------------------------------------------- the GitHub reader of closeout.py and cleanup.py

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


def run(operation, root='.'):
    try:
        if operation == 'status':
            result = op_status(root)
        elif operation == 'approve':
            result = op_approve(root)
        else:
            raise Refusal(f'Unknown operation: {operation}')
    except (Refusal, ValueError, OSError, KeyError, TypeError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    result['operation'] = operation
    result.setdefault('ok', result.get('exitCode') == 0)
    return result


def main():
    _cli.utf8_streams()
    parser = _cli.JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=['status', 'approve'])
    parser.add_argument('--root', help='project whose .frontlights/config.json declares roadmapSync (default: the main '
                                       'worktree of the current directory)')
    try:
        args = _cli.output_flags(parser).parse_args()
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 2)
    result = run(args.operation, str(_cli.root_path(args.root)))
    _cli.emit(protect(json.dumps(result, indent=2, ensure_ascii=True)), args.operation, args.full)
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
