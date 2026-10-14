#!/usr/bin/env python3
"""Clean-up helper: which worktrees and branches the work left behind are no longer needed, once the pull
requests that carried the work were merged into the approved base.

Read only. It reads Git (worktree list, status, ancestry; always with `--no-optional-locks`, so not even the index
is refreshed) and GitHub (`gh api graphql`, the reader of roadmap_sync.py) and prints what the session may propose.
Removing is done by the session, with its own `git`, after the user said yes: this helper never changes a
repository, a file or GitHub, and the commands it prints are values to type, not something it runs. Every command
is built from validated values (an existing registered worktree path without characters a command line cannot
carry, a plain branch name) and never uses `--force`.

Operations (each prints one JSON object on stdout):
  plan    the worktrees and branches of --issues (the `worktrees` of .frontlights/authorization*.json), plus any
          --worktree PATH named by hand, split into what can be removed now, with the commands in the order to run
          them, and what stays and why. A worktree and its branch can be removed only when it is not the main one,
          nor the folder this process runs in, nor locked or checked out elsewhere, it has nothing uncommitted, the
          branch is not protected, its tip is the head of a pull request that was merged, that pull request reached
          the approved base (directly, or through a stacked parent that did), and no open pull request is based on
          the branch or comes from it. The remote branch is deleted only when `origin` is the configured repository
          and the branch still points at that same commit. Ignored files go away with the worktree: they are named
          in the `ignored_files` caution.
          --integration PATH names the local-only integration worktree of a family (never pushed, never a pull
          request): it can go when its branch has no pull request and was never pushed, and every commit of its own
          is already part of a pull request that reached the base; a merge is one of its own when it carries content
          (a conflict resolved by hand, a file added to it).
  verify  reread --worktree and --branch values and say whether each is gone (worktree unregistered and its
          folder absent, local branch absent, remote branch absent).

Run it from the folder the session stands in, with --root pointing at the project's main worktree: it never
offers the folder it runs in.

Exit codes: 0 done; 1 refusal (bad usage or configuration, a failed read) or, for verify, something that is not
gone yet. A refusal is JSON, never a traceback.
"""

import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import closeout  # noqa: E402  (its reader of the records, branch rule and the GitHub reader it shares)
import frontlights  # noqa: E402  (the rule for text a command line can carry)
import roadmap_sync as rs  # noqa: E402

Refusal = rs.Refusal
require = rs.require

GIT_TIMEOUT = 45
MAX_ITEMS = 50           # worktrees one run looks at
BATCH = 8                # branches read from GitHub in one query
MAX_CHAIN = 8            # stacked parents followed from a pull request up to the approved base
MAX_IGNORED = 20         # ignored names listed in a caution
REMOTE = 'origin'
OID = re.compile(r'[0-9a-f]{40,64}')
REMOTE_URL = re.compile(r'[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$')
PULLS = 'nodes { number state merged mergedAt baseRefName headRefOid }'


# ---------------------------------------------------------------- git

def git(root, *args):
    """(exit code, stdout) of a Git command run in `root` without a shell. Git's own text is data and a failure
    never repeats it. `--no-optional-locks` keeps `git status` from refreshing (writing) the index."""
    environment = rs.gh_environment()
    environment['GIT_TERMINAL_PROMPT'] = '0'
    try:
        done = subprocess.run(['git', '-C', str(root), '--no-optional-locks', *args], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL,
                              env=environment)
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal('git could not be run; check that it is installed')
    return done.returncode, done.stdout


def norm(path):
    """One spelling of a path for comparisons: real, absolute and with the case Windows ignores."""
    return os.path.normcase(os.path.realpath(str(path)))


def list_worktrees(root):
    """The worktrees of the repository `root` belongs to, as Git lists them: the first is the main one."""
    code, out = git(root, 'worktree', 'list', '--porcelain')
    require(code == 0, 'the project folder is not a Git repository; pass --root <project>')
    entries = []
    for line in out.splitlines():
        if line.startswith('worktree '):
            entries.append({'path': line[len('worktree '):], 'branch': None, 'head': None, 'detached': False, 'locked': False})
        elif entries and line.startswith('HEAD '):
            entries[-1]['head'] = line[len('HEAD '):]
        elif entries and line.startswith('branch '):
            ref = line[len('branch '):]
            entries[-1]['branch'] = ref[len('refs/heads/'):] if ref.startswith('refs/heads/') else ref
        elif entries and line == 'detached':
            entries[-1]['detached'] = True
        elif entries and (line == 'locked' or line.startswith('locked ')):
            entries[-1]['locked'] = True
    require(entries, 'git listed no worktree for the project folder')
    return entries


def local_tip(root, branch):
    """The commit a local branch points at, or None when there is no such branch."""
    code, out = git(root, 'rev-parse', '--verify', '--quiet', f'refs/heads/{branch}^{{commit}}')
    tip = out.strip()
    return tip if code == 0 and OID.fullmatch(tip) else None


def is_ancestor(root, commit, of):
    """True or False when Git can tell, None when it cannot (a commit this clone does not have)."""
    code, _ = git(root, 'merge-base', '--is-ancestor', commit, of)
    return True if code == 0 else False if code == 1 else None


def origin_is(root, repository):
    """Does `origin` push to the configured repository? (`git push` follows the push URL, which may differ from the
    fetch one.) Removing a branch on the wrong remote is not undone."""
    code, out = git(root, 'remote', 'get-url', '--push', REMOTE)
    found = REMOTE_URL.search(out.strip()) if code == 0 else None
    return bool(found) and found.group(1).casefold() == repository.casefold()


def base_ref(root, base):
    """The ref the approved base is compared with: the remote-tracking one as of the last fetch when it exists
    (what was delivered), else the local branch."""
    for ref in (f'refs/remotes/{REMOTE}/{base}', f'refs/heads/{base}'):
        code, _ = git(root, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
        if code == 0:
            return ref
    return None


def unique_commits(ctx, tip):
    """What `tip` holds of its own: the commits that are not a merge and are neither in the base nor in a delivered
    pull request, and the merges that carry content of their own (a conflict resolved by hand, a merge amended with a
    file): `git log --merges --cc` shows nothing for a clean merge. [] when the branch holds nothing of its own, None
    when Git cannot tell."""
    ref = base_ref(ctx['root'], ctx['base'])
    if ref is None:
        return None
    outside = [*[f'^{oid}' for oid in sorted(ctx['delivered'])], f'^{ref}']
    code, out = git(ctx['root'], 'rev-list', '--no-merges', tip, *outside)
    if code != 0:
        return None
    found = out.split()
    # no textconv, no external diff and submodules compared: a diff setting of the user's must not hide content
    code, shown = git(ctx['root'], 'log', '--merges', '--cc', '--no-textconv', '--no-ext-diff', '--ignore-submodules=none',
                      '--format=', tip, *outside)
    if code != 0:
        return None
    return found + (['merge-with-content'] if shown.strip() else [])


# ---------------------------------------------------------------- scope

def authorized_worktrees(root, issues):
    """The worktrees the authorizations of the project name for `issues`: [{issue, path, branch}], and the
    protected branch names those authorizations declare."""
    found = []
    try:
        files = sorted((Path(root) / '.frontlights').glob('authorization*.json'))
    except OSError:
        files = []
    protected = []
    for file in files:
        data = closeout.read_record(file)
        if not isinstance(data, dict):
            continue
        listed = data.get('protected_branches')
        protected += [p for p in listed if isinstance(p, str) and p.strip('/')] if isinstance(listed, list) else []
        entries = data.get('worktrees')
        for entry in entries if isinstance(entries, list) else []:
            if (isinstance(entry, dict) and closeout.valid_number(entry.get('issue')) and entry['issue'] in issues
                    and isinstance(entry.get('path'), str) and entry['path'].strip()):
                branch = entry.get('branch')
                found.append({'issue': entry['issue'], 'path': entry['path'], 'branch': branch if isinstance(branch, str) else None})
    return found, protected


def is_protected(branch, protected):
    """The rule of `frontlights.authorize`: a protected name also protects everything below it."""
    folded = branch.casefold()
    return any(fnmatch.fnmatchcase(folded, p.casefold().rstrip('/')) or fnmatch.fnmatchcase(folded, p.casefold().rstrip('/') + '/*')
               for p in protected)


# ---------------------------------------------------------------- GitHub

def read_default_branch(gh, repository):
    owner, name = repository.split('/')
    data = rs.graphql(gh, 'query { repository(owner: "%s", name: "%s") { defaultBranchRef { name } } }' % (owner, name))
    branch = (data.get('repository') or {}).get('defaultBranchRef')
    name = branch.get('name') if isinstance(branch, dict) else None
    return name if isinstance(name, str) and closeout.valid_branch(name) else None


def read_branches(gh, repository, branches):
    """{branch: {'heads': pull requests opened from it, 'cut': they did not all fit, 'dependents': open pull requests
    based on it, 'remote': the commit the remote branch points at, or None}}. Branch names are validated by the
    caller, so they are safe inside the query."""
    owner, name = repository.split('/')
    found = {}
    for start in range(0, len(branches), BATCH):
        chunk = branches[start:start + BATCH]
        parts = []
        for i, branch in enumerate(chunk):
            parts.append(f'h{i}: pullRequests(headRefName: "{branch}", first: 20, states: [OPEN, MERGED, CLOSED]) '
                         f'{{ totalCount {PULLS} }} '
                         f'd{i}: pullRequests(baseRefName: "{branch}", first: 1, states: OPEN) {{ totalCount }} '
                         f'r{i}: ref(qualifiedName: "refs/heads/{branch}") {{ target {{ oid }} }}')
        data = rs.graphql(gh, 'query { repository(owner: "%s", name: "%s") { %s } }' % (owner, name, ' '.join(parts)))
        repo = data.get('repository') or {}
        for i, branch in enumerate(chunk):
            heads, cut = closeout.page(repo.get(f'h{i}'))
            dependents = (repo.get(f'd{i}') or {}).get('totalCount')
            target = (repo.get(f'r{i}') or {}).get('target')
            oid = target.get('oid') if isinstance(target, dict) else None
            found[branch] = {'heads': heads, 'cut': cut, 'dependents': dependents if isinstance(dependents, int) else 0,
                             'remote': oid if isinstance(oid, str) and OID.fullmatch(oid) else None}
    return found


def reaches_base(ctx, pull, tip, depth=0):
    """Did the work of `pull` (a merged pull request whose head was the local `tip`) reach the approved base?
    True when it was merged into the base; for a stacked branch, when its parent's pull request was merged into
    the base after it and contains its commit. None when that cannot be told."""
    if pull.get('baseRefName') == ctx['base']:
        return True
    parent = pull.get('baseRefName')
    if depth >= MAX_CHAIN or not isinstance(parent, str) or not closeout.valid_branch(parent):
        return False
    known = ctx['more'].get(parent)
    if known is None:
        known = ctx['more'][parent] = read_branches(ctx['gh'], ctx['repository'], [parent])[parent]
    outcomes = []
    for above in known['heads']:
        oid = above.get('headRefOid')
        if above.get('state') != 'MERGED' or not isinstance(oid, str) or not OID.fullmatch(oid):
            continue
        if not (isinstance(above.get('mergedAt'), str) and isinstance(pull.get('mergedAt'), str)
                and above['mergedAt'] >= pull['mergedAt']):
            continue
        inside = is_ancestor(ctx['root'], tip, oid)
        outcomes.append(None if inside is None else reaches_base(ctx, above, oid, depth + 1) if inside else False)
    return True if True in outcomes else None if None in outcomes else False


# ---------------------------------------------------------------- assessment

def pull_reasons(ctx, github, tip):
    """Why a branch that carried a pull request stays, and (for the integration pass) the heads it delivered."""
    reasons = []
    heads = github['heads']
    if any(p.get('state') == 'OPEN' for p in heads):
        reasons.append('open_pr')
    merged = [p for p in heads if p.get('state') == 'MERGED']
    matching = [p for p in merged if p.get('headRefOid') == tip]
    if not merged:
        reasons.append('no_merged_pr')
    elif not matching:
        reasons.append('newer_than_merged_pr')
    else:
        verdicts = [(p, reaches_base(ctx, p, tip)) for p in matching]
        ctx['delivered'].update(p['headRefOid'] for p, v in verdicts if v is True and OID.fullmatch(p['headRefOid'] or ''))
        if not any(v is True for _, v in verdicts):
            reasons.append('merged_into_other_branch' if all(v is False for _, v in verdicts) else 'ancestry_unverifiable')
    if github['dependents']:
        reasons.append('open_dependents')
    return reasons


def integration_reasons(ctx, github, tip):
    """Why a local-only integration branch stays: it must have no pull request, never have been pushed, and hold no
    commit of its own (a merge of member branches is disposable; a fix belongs to the member branch that owns it)."""
    reasons = []
    if github['heads']:
        reasons.append('integration_has_pull_request')
    if github['remote'] is not None:
        reasons.append('integration_pushed')
    if github['dependents']:
        reasons.append('open_dependents')
    if not reasons:
        unique = unique_commits(ctx, tip)
        if unique is None:
            reasons.append('ancestry_unverifiable')
        elif unique:
            reasons.append('integration_has_unique_commits')
    return reasons


def worktree_state(path):
    """(uncommitted, ignored): the lines of `git status` that are changes or new files, and the ignored names
    (`.frontlights` aside, which has its own caution), or None for the first when git could not tell."""
    code, out = git(path, 'status', '--porcelain', '-z', '--untracked-files=all', '--ignored=matching')
    if code != 0:
        return None, []
    lines = [line for line in out.split('\0') if line.strip()]   # -z: names come raw, never quoted
    ignored = [line[3:] for line in lines if line.startswith('!! ') and line[3:].strip('/"') != '.frontlights']
    return [line for line in lines if not line.startswith('!! ')], ignored


def assess(ctx, item, registered, github):
    """(reasons it stays, record when it can go). `registered` is the Git entry of the worktree, or None."""
    reasons, cautions = [], []
    path = item['path'] if registered is None else registered['path']
    branch = registered['branch'] if registered is not None else item['branch']
    tip = registered['head'] if registered is not None else (local_tip(ctx['root'], branch) if branch else None)
    integration = bool(item.get('integration'))
    if registered is not None and norm(registered['path']) == ctx['main']:
        return ['main_worktree'], None
    if registered is None and Path(item['path']).exists():
        return ['not_a_worktree'], None   # a folder Git does not know: not something `git worktree remove` can take away
    if registered is not None:
        here = norm(Path.cwd())
        folder = norm(registered['path'])
        if here == folder or here.startswith(folder + os.sep):
            return ['current_directory'], None
        if registered['detached'] or not branch:
            return ['detached_head'], None
        if registered['locked']:
            return ['locked_worktree'], None
        if not Path(registered['path']).is_dir():
            reasons.append('path_missing')
    if not branch or not closeout.valid_branch(branch):
        return ['unsafe_branch'] if branch else ['nothing_left'], None
    if tip is None and registered is None:
        return ['nothing_left'], None
    if is_protected(branch, ctx['protected']):
        return ['protected_branch'], None
    if registered is None and any(e['branch'] == branch for e in ctx['listing']):
        return ['checked_out_elsewhere'], None
    ignored = []
    if registered is not None:
        if frontlights.UNSAFE_CHARS.search(registered['path']):
            reasons.append('unsafe_path')
        uncommitted, ignored = worktree_state(registered['path'])
        if uncommitted is None:
            reasons.append('unreadable_status')
        elif uncommitted:
            reasons.append('uncommitted_changes')
        records = Path(registered['path']) / '.frontlights'
        if records.is_dir() and any(records.iterdir()):
            cautions.append('frontlights_records')
        if ignored:
            cautions.append('ignored_files')
        if item.get('branch') and item['branch'] != branch:
            cautions.append('branch_differs_from_authorization')
    if github is None or github['cut']:
        reasons.append('pull_requests_unreadable')
    else:
        reasons += integration_reasons(ctx, github, tip) if integration else pull_reasons(ctx, github, tip)
    if reasons:
        return reasons, None
    remote = github['remote']
    remove_remote = not integration and ctx['origin_ok'] and remote is not None and remote == tip
    if integration:
        cautions.append('local_only_integration')
    elif remote is None:
        cautions.append('remote_branch_gone')
    elif not ctx['origin_ok']:
        cautions.append('origin_is_not_the_repository')
    elif not remove_remote:
        cautions.append('remote_branch_moved')
    main = ctx['main_path']
    commands = []
    if registered is not None:
        commands.append({'kind': 'remove_worktree', 'argv': ['git', '-C', main, 'worktree', 'remove', registered['path']]})
    commands.append({'kind': 'delete_branch', 'argv': ['git', '-C', main, 'branch', '-D', branch]})
    if remove_remote:
        commands.append({'kind': 'delete_remote_branch', 'argv': ['git', '-C', main, 'push', REMOTE, '--delete', branch]})
    record = {'issue': item.get('issue'), 'path': path if registered is not None else None, 'branch': branch, 'tip': tip,
              'pullRequests': sorted(p['number'] for p in github['heads'] if isinstance(p.get('number'), int)),
              'removeWorktree': registered is not None, 'deleteRemoteBranch': remove_remote,
              'cautions': cautions, 'commands': commands}
    if ignored:
        record['ignoredCount'] = len(ignored)
        record['ignored'] = [rs.clean(name, 200) for name in ignored[:MAX_IGNORED]]
    return [], record


def op_plan(config, root='.', issues=None, base=None, worktrees=(), integrations=(), gh=None):
    """Read only: what can be removed now, with the commands in the order to run them, and what stays."""
    gh = gh or rs.gh_default
    repository, _ = closeout.load_project(config)
    require(issues is not None and issues != '' and issues != [], 'plan needs the issues whose work is done: pass --issues 12,13')
    numbers = closeout.parse_numbers(issues)
    require(base is None or closeout.valid_branch(base), '--base must be a plain branch name')
    listing = list_worktrees(root)
    main_entry = listing[0]
    records_root = root if (Path(root) / '.frontlights').is_dir() else main_entry['path']
    authorized, protected = authorized_worktrees(records_root, set(numbers))
    items, seen = [], {}
    named = [{'issue': None, 'path': str(p), 'branch': None} for p in worktrees]
    named += [{'issue': None, 'path': str(p), 'branch': None, 'integration': True} for p in integrations]
    for entry in authorized + named:
        path = Path(entry['path'])
        key = norm(path if path.is_absolute() else Path(root) / path)
        if key in seen:
            if entry.get('integration'):
                seen[key]['integration'] = True   # named as the integration worktree: that is how it is judged
            continue
        entry['path'] = str(path if path.is_absolute() else Path(root) / path)
        seen[key] = entry
        items.append(entry)
    require(len(items) <= MAX_ITEMS, f'name at most {MAX_ITEMS} worktrees')
    default = read_default_branch(gh, repository)
    expected = base or default
    require(isinstance(expected, str), 'the approved base is unknown: pass --base <branch> (the repository default could not be read)')
    by_path = {norm(e['path']): e for e in listing}
    protected = list(protected) + ['main', 'master', expected] + ([default] if default else [])
    result = {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'expectedBase': expected,
              'baseSource': 'argument' if base else 'default_branch', 'candidates': [], 'excluded': [], 'alreadyClean': 0, 'ask': False}
    if not items:
        result['message'] = ('No worktree is recorded for these issues in an authorization and none was named: nothing to clean. '
                             'Name one with --worktree PATH.')
        return result
    resolved = []
    for item in items:
        registered = by_path.get(norm(item['path']))
        branch = registered['branch'] if registered is not None else item['branch']
        resolved.append((item, registered, branch))
    names = sorted({b for _, _, b in resolved if b and closeout.valid_branch(b) and not is_protected(b, protected)})
    github = read_branches(gh, repository, names) if names else {}
    ctx = {'root': main_entry['path'], 'main': norm(main_entry['path']), 'main_path': main_entry['path'], 'base': expected,
           'protected': protected, 'gh': gh, 'repository': repository, 'more': {}, 'delivered': set(), 'listing': listing,
           'origin_ok': origin_is(main_entry['path'], repository)}
    # the integration worktrees go last: what they hold is judged against the pull requests the others delivered
    for item, registered, branch in sorted(resolved, key=lambda r: bool(r[0].get('integration'))):
        reasons, record = assess(ctx, item, registered, github.get(branch))
        if record is not None and any(frontlights.UNSAFE_CHARS.search(a) for c in record['commands'] for a in c['argv']):
            reasons, record = ['unsafe_path'], None
        if record is not None:
            result['candidates'].append(record)
        elif reasons == ['nothing_left'] and item.get('issue') is not None:
            result['alreadyClean'] += 1
        else:
            result['excluded'].append({'issue': item.get('issue'), 'path': rs.clean(item['path'], 300),
                                       'branch': rs.clean(branch, 200) if branch else None,
                                       'reasons': ['not_found'] if reasons == ['nothing_left'] else reasons})
    result['candidates'].sort(key=lambda c: (c['issue'] is None, c['issue'] or 0, c['branch']))
    result['ask'] = bool(result['candidates'])
    parts = [f'{len(result["candidates"])} worktree(s) or branch(es) can be removed.' if result['candidates']
             else 'Nothing can be removed now.']
    if result['excluded']:
        parts.append(f'{len(result["excluded"])} stay (see excluded for the reason of each).')
    if result['alreadyClean']:
        parts.append(f'{result["alreadyClean"]} already gone.')
    if result['candidates']:
        parts.append('Nothing was removed. Ask the user, then run the commands in order; verify afterwards.')
    result['message'] = ' '.join(parts)
    return result


def op_verify(config, root='.', worktrees=(), branches=(), gh=None):
    """Read only: whether each named worktree and branch is gone."""
    gh = gh or rs.gh_default
    repository, _ = closeout.load_project(config)
    require(worktrees or branches, 'verify needs what to check: pass --worktree PATH and/or --branch NAME')
    require(all(closeout.valid_branch(b) for b in branches), '--branch must be a plain branch name')
    listing = list_worktrees(root)
    registered = {norm(e['path']) for e in listing}
    entries = []
    for text in worktrees:
        path = Path(text)
        path = path if path.is_absolute() else Path(root) / path
        gone = norm(path) not in registered and not path.exists()
        entries.append({'kind': 'worktree', 'name': rs.clean(str(text), 300), 'gone': gone})
    remote = read_branches(gh, repository, sorted(set(branches))) if branches else {}
    for branch in branches:
        local = local_tip(listing[0]['path'], branch) is None
        online = remote[branch]['remote'] is None
        entries.append({'kind': 'branch', 'name': branch, 'localGone': local, 'remoteGone': online, 'gone': local and online})
    waiting = [e['name'] for e in entries if not e['gone']]
    result = {'ok': not waiting, 'exitCode': 0 if not waiting else 1, 'project': repository, 'repository': repository,
              'entries': entries}
    result['message'] = (f'All {len(entries)} item(s) are gone.' if not waiting else
                         f'{len(waiting)} of {len(entries)} item(s) are not gone yet: ' + ', '.join(waiting) + '.')
    return result


# ---------------------------------------------------------------- command line

def run(operation, config, root='.', issues=None, base=None, worktrees=(), branches=(), gh=None, integrations=()):
    try:
        if operation == 'plan':
            result = op_plan(config, root, issues, base, worktrees, integrations, gh)
        elif operation == 'verify':
            result = op_verify(config, root, worktrees, branches, gh)
        else:
            raise Refusal(f'Unknown operation: {rs.clean(operation, 40)}')
    except (Refusal, ValueError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    except Exception as error:  # noqa: BLE001  (a refusal in JSON, never a traceback; nothing was removed)
        result = {'ok': False, 'exitCode': 1,
                  'message': f'cleanup stopped on an unexpected {type(error).__name__}; nothing was removed'}
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
    for name in ('plan', 'verify'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--config', required=True, help="the project's .frontlights/config.json")
        command.add_argument('--root', default='.', help="the project's main worktree")
        command.add_argument('--worktree', action='append', default=[], dest='worktrees', help='a worktree path, as many times as needed')
        if name == 'plan':
            command.add_argument('--issues', help='issue numbers whose work is done, such as 12,13 (required)')
            command.add_argument('--base', help="the approved base branch; without it, the repository's default branch")
            command.add_argument('--integration', action='append', default=[], dest='integrations',
                                 help="the local-only integration worktree of a family, as many times as needed")
        else:
            command.add_argument('--branch', action='append', default=[], dest='branches', help='a branch name, as many times as needed')
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        result = run(args.operation, args.config, args.root, getattr(args, 'issues', None), getattr(args, 'base', None),
                     args.worktrees, getattr(args, 'branches', []), integrations=getattr(args, 'integrations', []))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
