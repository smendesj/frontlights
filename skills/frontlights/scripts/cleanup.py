#!/usr/bin/env python3
"""Clean-up helper: which worktrees and branches the work left behind are no longer needed, once the pull
requests that carried the work were merged into the approved base, and the commands that remove them.

`plan` and `verify` only read; `run`, `archive` and `unlink` write. They read Git (worktree list, status, ancestry; always with `--no-optional-locks`, so
not even the index is refreshed) and GitHub (`gh api graphql`, the reader of roads.py) and print what the session
runs. The cleanup of merged work needs no approval (closeout.md, step 5): the session runs the printed commands
itself, with its own `git`, in order; only a candidate with `ask: true` waits for the user's yes. The commands are
values to type, not something `plan` runs. Every command is built from validated values (an existing registered
worktree path without characters a command line cannot carry, a plain branch name) and never uses `--force`. One
command touches a remote branch, `delete_remote_branch` (`git push origin --delete <branch>`, issue 70): only the
branch of an issue (its authorization entry without `slice`, never the `-integra` one, a release or a protected
branch) whose tip on GitHub `origin/<base>` already contains, that is, released. It comes after the fetch and before
the local delete of the same item. Every other remote branch is left alone: GitHub deletes the head branch of a merged
pull request on its own ("Automatically delete head branches"), the release's among them, and `git fetch --prune`
drops the remote-tracking ref it left.

Operations (each prints one JSON object on stdout):
  plan    the worktrees and branches of --issues (the `worktrees` of .frontlights/authorization*.json), plus any
          --worktree PATH named by hand, plus every local release branch (`<branch_prefix>release-<YYYY-MM-DD>[-N]`,
          the prefixes of the authorization records) whose work reached the approved base, split into what can be
          removed now, with the commands in the order to run them, and what stays and why. `commands` is the whole
          list to run: `git fetch --prune origin` first (when there is an `origin`, `item` null), then, per candidate
          that does not ask, its own `commands`, each with `item` (the candidate's branch): a failed command skips the
          rest of its item. A worktree holding Frontlights records (`frontlights_records`) gets `copy_records`
          before `git worktree remove`: `cleanup.py archive` copies its `.frontlights` to the main worktree's
          `.frontlights/issues/<n>/worktrees/<folder>-<short tip>/` (`.frontlights/worktrees/<folder>-<short tip>/`
          without an issue), a folder of its own per archive. A
          candidate whose ignored files include anything besides dependency or build folders (DISPOSABLE) carries
          `ask: true`, `askReason` and `askIgnored`, and its commands stay out of `commands` until the user said yes.
          A worktree and its branch can be removed only when it is not the main one,
          nor the folder this process runs in, nor locked or checked out elsewhere, it has nothing uncommitted, the
          branch is not protected, no open pull request is based on the branch or comes from it, and the work was
          delivered: either its tip is the head of a pull request that was merged and that pull request reached
          the approved base (directly, or through a stacked parent that did), or it has no pull request at all and
          the approved base (`origin/<base>` when the remote-tracking ref exists, else the local branch) already
          contains its tip (issue 32: delivered by a merge into the local main; the
          `contained_in_base_without_pull_request` caution says so). A pull request closed without a merge is not
          the absence of one: that branch stays. Ignored files go away with the worktree: they are named in the
          `ignored_files` caution. A release branch is offered by the same rule, with the caution
          `merged_release_branch`, when no worktree has it checked out; one not merged yet is left alone, unsaid.
          --integration PATH names the local-only integration worktree of a family (never pushed, never a pull
          request): it can go when its branch has no pull request and was never pushed, and every commit of its own
          is already part of a pull request that reached the base; a merge is one of its own when it carries content
          (a conflict resolved by hand, a file added to it).
          A slice's worktree (an authorization entry with `slice`, issue 31) is delivered to the branch of its own
          issue, never by a pull request: it can go when that branch (the entry of the same issue without `slice`)
          contains its tip, it was never pushed and no pull request was opened from it.
          --from-authorizations takes the issues (the `issue_ids`) and the base (`base.branch` of the newest record
          naming one of them) from the authorization records; --issues then narrows them. More than 50 worktrees
          are read a page at a time (--page, `page` and `pages`). The saved outputs of the main worktree
          (`.frontlights/out`, what a long output leaves) older than 30 days are a candidate of their own, `key` `out`,
          caution `saved_outputs`, always `ask: true`, with the command `unlink_outputs`.
  run     plan again, in this process, and run only the commands of that fresh plan: `git fetch --prune origin`
          first (before the plan reads `origin/<base>`), then per candidate, in order, `copy_records` (the archive,
          in process), the junctions of the first two levels of the worktree undone with `os.rmdir` (never the
          target, never inside `.frontlights`), `git worktree remove`, `git branch -D`; a failed command stops its
          item. No `--force`, ever, and no `git push`: a candidate with `delete_remote_branch` leaves that command and
          the rest of its item in `sessionCommands`, for the session to run in order. A candidate with `ask: true`
          runs only when --yes names its `key` (its branch, or `out`), after the user's yes in its own question.
          --integration takes only the worktree of an `-integra` entry of the records. A locked worktree, or one a
          process holds (the removal fails with "permission denied" or the like), goes to `excluded` as `in_use`.
          `verify` runs at the end on what was removed; `.frontlights/cleanup-<AAAAMMDD-HHMMSS>.json` (São Paulo time)
          keeps the result as evidence. Exit 1 when an item failed or the verify did not pass.
  unlink  remove the saved outputs of --out (a `.frontlights/out` folder of a worktree of this repository): only the
          files named by the saver and older than 30 days, recomputed; never a folder, a link or another file.
  archive copy --from <worktree>/.frontlights into --to, a folder under the `.frontlights` folder of the main
          worktree of that repository (read from Git), that does not exist yet or is empty. One whose files are all
          the same as the records (same paths, same bytes: an earlier copy, whole or stopped half-way, whose removal
          failed) gets the missing files and is ok; one with any differing or extra file is refused, nothing copied,
          so no earlier archive is ever overwritten. The one operation that writes, and only into --to.
  verify  reread --worktree, --branch, --remote-branch and --records values and say whether each worktree is gone
          (unregistered and its folder absent), each local branch is gone, each remote branch is gone from `origin`
          (`git ls-remote`, the one read of the remote) and each records folder holds the copied files.

Run it from the folder the session stands in, with --root pointing at the project's main worktree: it never
offers the folder it runs in.

Cautions of a candidate (they inform): frontlights_records, ignored_files, local_only_integration,
slice_merged_into_issue_branch, contained_in_base_without_pull_request, merged_release_branch,
branch_differs_from_authorization, saved_outputs. Ignored files ask nothing when they are dependency or build output
(node_modules, .venv, __pycache__, dist, build, bin, obj, .vs, TestResults, next-env.d.ts, *.tsbuildinfo, .dart_tool,
Pods, DerivedData, .terraform, caches and the like), when the `cleanup.disposable` globs of the project's config match
them, or when they are a byte-for-byte copy of the same path in the main worktree.
Reasons a worktree or branch stays (`excluded`, each needs work or a decision, never removal): main_worktree,
current_directory, detached_head, locked_worktree (in_use for `run`), in_use, junction_unverifiable (Windows before
Python 3.12, which cannot see a junction), checked_out_elsewhere, not_a_worktree, not_found, path_missing,
unsafe_path, unsafe_branch, protected_branch, uncommitted_changes, unreadable_status, open_pr, no_merged_pr,
newer_than_merged_pr, merged_into_other_branch, ancestry_unverifiable, open_dependents, pull_requests_unreadable,
integration_has_pull_request, integration_pushed, integration_has_unique_commits, slice_has_pull_request,
slice_pushed, slice_is_issue_branch, slice_issue_branch_unknown, slice_not_in_issue_branch.

Exit codes: 0 done; 1 refusal (bad usage or configuration, a failed read or copy) or, for verify, something that is
not gone or not copied yet. A refusal is JSON, never a traceback.
"""

import argparse
import filecmp
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import closeout  # noqa: E402  (its reader of the records, branch rule and the GitHub reader it shares)
import frontlights  # noqa: E402  (the rule for text a command line can carry)
import _cli  # noqa: E402  (defaults of --root, --config and --issue, the parser and UTF-8)
import roads as rs  # noqa: E402

Refusal = rs.Refusal
require = rs.require

GIT_TIMEOUT = 45
MAX_ITEMS = 50           # worktrees one run looks at
BATCH = 8                # branches read from GitHub in one query
MAX_CHAIN = 8            # stacked parents followed from a pull request up to the approved base
MAX_IGNORED = 20         # ignored names listed in a caution
SHORT_TIP = 7            # characters of the tip in the folder an archive goes to
REMOTE = 'origin'
OID = re.compile(r'[0-9a-f]{40,64}')
RELEASE = re.compile(r'release-\d{4}-\d{2}-\d{2}(?:-\d+)?')   # after the branch prefix (homolog.py, release_name)
PREFIX = re.compile(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/')
FOLDER = re.compile(r'[^A-Za-z0-9._-]+')
# Folders of dependencies, builds and caches: ignored files that are rebuilt, so removing them asks nothing.
DISPOSABLE = frozenset({'node_modules', 'bower_components', 'jspm_packages', '.venv', 'venv', '__pycache__', '.eggs',
                        'dist', 'build', 'out', 'target', 'coverage', 'htmlcov', '.cache', '.parcel-cache', '.turbo',
                        '.next', '.nuxt', '.svelte-kit', '.angular', '.gradle', '.pytest_cache', '.mypy_cache',
                        '.ruff_cache', '.tox', '.nox',
                        # .NET, Next.js, Flutter, iOS and Terraform (issue 2 of the redesign: asked about in real sessions)
                        'bin', 'obj', '.vs', 'TestResults', 'next-env.d.ts', '.dart_tool', 'Pods', 'DerivedData',
                        '.terraform'})
DISPOSABLE_SUFFIXES = ('.pyc', '.pyo', '.egg-info', '.tsbuildinfo')
MAX_SAME_FILES = 200     # files of an ignored folder compared byte for byte with the main worktree's
OUT_AGE_DAYS = 30        # saved outputs (.frontlights/out) older than this are offered, with a question
OUT_NAME = re.compile(r'[a-z0-9][a-z0-9-]*-\d{8}-\d{6}-\d+\.json')   # the name `_cli.save_output` gives
JUNCTION_DEPTH = 2       # levels of a worktree where `run` looks for junctions to undo before `git worktree remove`
IN_USE = re.compile(r'permission denied|being used|resource busy|invalid argument|access is denied', re.IGNORECASE)
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


def has_origin(root):
    """Is there an `origin` remote to prune the remote-tracking refs of?"""
    code, _ = git(root, 'remote', 'get-url', REMOTE)
    return code == 0


def released_base_ref(root, base):
    """The remote-tracking ref of the approved base (`origin/<base>` as of the last fetch: what was released), or
    None. The local base never stands for it: the local main is where the work is homologated, before the release."""
    ref = f'refs/remotes/{REMOTE}/{base}'
    code, _ = git(root, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
    return ref if code == 0 else None


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
    """The worktrees the authorizations of the project name for `issues`: [{issue, path, branch}], the protected
    branch names those authorizations declare, and the branch prefixes they use: the `branchPrefix` of the config
    and the `branch_prefix` of each record (the legacy prefix of `_cli.branch_prefix` for a record without it)."""
    found = []
    try:
        files = sorted((Path(root) / '.frontlights').glob('authorization*.json'))
    except OSError:
        files = []
    protected, prefixes = [], set()
    named = _cli.config_prefix(Path(root) / '.frontlights' / 'config.json')
    if named and PREFIX.fullmatch(named) and '..' not in named:
        prefixes.add(named)
    for file in files:
        data = closeout.read_record(file)
        if not isinstance(data, dict):
            continue
        prefix = _cli.branch_prefix(record=data)[0]
        if isinstance(prefix, str) and PREFIX.fullmatch(prefix) and '..' not in prefix:
            prefixes.add(prefix)
        listed = data.get('protected_branches')
        protected += [p for p in listed if isinstance(p, str) and p.strip('/')] if isinstance(listed, list) else []
        entries = data.get('worktrees')
        for entry in entries if isinstance(entries, list) else []:
            if (isinstance(entry, dict) and closeout.valid_number(entry.get('issue')) and entry['issue'] in issues
                    and isinstance(entry.get('path'), str) and entry['path'].strip()):
                branch = entry.get('branch')
                box = entry.get('slice')   # a slice's worktree (issue 31): judged against the branch of its issue
                found.append({'issue': entry['issue'], 'path': entry['path'], 'branch': branch if isinstance(branch, str) else None,
                              'slice': box if isinstance(box, str) and box.strip() else None})
    return found, protected, sorted(prefixes)


def authorization_scope(root, numbers=None):
    """(issue numbers, approved base) the authorization records of the project give, for `--from-authorizations`:
    the `issue_ids` of every `.frontlights/authorization*.json` (or `numbers`, when the command line narrows them) and
    the `base.branch` of the newest record that names one of them (None when no record names a plain one)."""
    ids, base = set(), None
    for path in closeout.authorization_records(root):
        data = closeout.read_record(path)
        listed = data.get('issue_ids') if isinstance(data, dict) else None
        if isinstance(listed, list):
            ids.update(n for n in listed if closeout.valid_number(n))
    wanted = sorted(ids) if numbers is None else list(numbers)
    for path in reversed(closeout.authorization_records(root)):
        data = closeout.read_record(path)
        listed = data.get('issue_ids') if isinstance(data, dict) else None
        branch = data.get('base', {}).get('branch') if isinstance(data, dict) and isinstance(data.get('base'), dict) else None
        if isinstance(listed, list) and any(n in listed for n in wanted) and isinstance(branch, str) and closeout.valid_branch(branch):
            base = branch
            break
    return wanted, base


def release_branches(root, prefixes):
    """The local branches named like a release (`<prefix>release-<YYYY-MM-DD>[-N]`) under one of `prefixes`."""
    if not prefixes:
        return []
    code, out = git(root, 'for-each-ref', '--format=%(refname:short)', *(f'refs/heads/{p}' for p in prefixes))
    if code != 0:
        return []
    names = []
    for name in out.split():
        if any(name.startswith(p) and RELEASE.fullmatch(name[len(p):]) for p in prefixes) and closeout.valid_branch(name):
            names.append(name)
    return sorted(set(names))


def nothing_left(main, entry, key, known):
    """An authorization entry whose worktree Git no longer lists, whose folder is gone and whose branch (a plain name)
    has no local tip: nothing of it is left to remove (issue 65's follow-up: old charters filled the cap)."""
    branch = entry.get('branch')
    if key in known or Path(entry['path']).exists():
        return False
    if branch is None:
        return True
    return closeout.valid_branch(branch) and local_tip(main, branch) is None


def disposable(name, globs=()):
    """An ignored name inside a folder of dependencies, builds or caches (rebuilt, so removing it asks nothing), or one
    the project's `cleanup.disposable` globs match (the whole relative path or any part of it)."""
    parts = [part for part in name.strip('/"').split('/') if part]
    if not parts:
        return False
    if any(part in DISPOSABLE or part.endswith('.egg-info') for part in parts) or parts[-1].endswith(DISPOSABLE_SUFFIXES):
        return True
    whole = '/'.join(parts)
    return any(fnmatch.fnmatchcase(whole, g.strip('/')) or any(fnmatch.fnmatchcase(part, g.strip('/')) for part in parts)
               for g in globs)


def config_disposable(config):
    """The `cleanup.disposable` globs of the project's config (a list of plain strings), or ()."""
    try:
        data = frontlights.load(config)
    except (OSError, ValueError):
        return ()
    block = data.get('cleanup') if isinstance(data, dict) else None
    globs = block.get('disposable') if isinstance(block, dict) else None
    return tuple(g for g in globs if isinstance(g, str) and g.strip('/ ')) if isinstance(globs, list) else ()


def same_as_main(main, worktree, name):
    """Whether the ignored `name` of `worktree` is a byte-for-byte copy of the same path in the main worktree (a
    `.env` copied there, say): a file with the same bytes, or a folder whose every file (at most MAX_SAME_FILES) has
    its twin there. A link or junction never counts as a copy."""
    relative = name.strip('/"')
    if not relative or '..' in relative.split('/'):
        return False
    mine, theirs = Path(worktree) / relative, Path(main) / relative
    try:
        if is_link(mine) or is_link(theirs):
            return False
        if mine.is_file():
            return theirs.is_file() and filecmp.cmp(mine, theirs, shallow=False)
        if not (mine.is_dir() and theirs.is_dir()):
            return False
        seen = 0
        for folder, dirs, files in os.walk(mine):
            for entry in dirs + files:
                if is_link(Path(folder) / entry):
                    return False
            for entry in files:
                seen += 1
                twin = theirs / (Path(folder) / entry).relative_to(mine)
                if seen > MAX_SAME_FILES or not twin.is_file() or not filecmp.cmp(Path(folder) / entry, twin, shallow=False):
                    return False
        return True
    except OSError:
        return False


def records_destination(main, item, folder, tip):
    """Where the Frontlights records of a worktree are copied in the main worktree before it is removed: a folder of
    its own per worktree and tip (`<folder>-<short tip>`), so a later archive never lands on an earlier one."""
    name = FOLDER.sub('-', Path(folder).name).strip('.-') or 'worktree'
    if isinstance(tip, str) and OID.fullmatch(tip):
        name = f'{name}-{tip[:SHORT_TIP]}'
    base = Path(main) / '.frontlights'
    target = base / 'issues' / str(item['issue']) / 'worktrees' / name if item.get('issue') is not None else base / 'worktrees' / name
    return target.as_posix()


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
    """Why an issue branch stays, and (for the integration pass) the heads it delivered. With pull requests, its tip
    must be the head of a merged one that reached the approved base. With none at all (issue 32: delivered by a merge
    into the local main), the approved base must already contain its tip; `assess` then adds the
    `contained_in_base_without_pull_request` caution."""
    reasons = []
    heads = github['heads']
    if not heads:
        base = base_ref(ctx['root'], ctx['base'])
        inside = None if base is None or tip is None else is_ancestor(ctx['root'], tip, base)
        if inside is None:
            reasons.append('ancestry_unverifiable')
        elif not inside:
            reasons.append('no_merged_pr')
    else:
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


def slice_reasons(ctx, github, tip, issue_branch, branch):
    """Why a slice's worktree stays (issue 31, S3): its branch is delivered to the branch of its own issue, never by a
    pull request of its own, so it goes once that branch contains a commit of its own, it was never pushed and no
    pull request was opened from it. When the branch of the issue is already gone (cleaned in an earlier round), the
    slice counts as delivered only when the approved base holds its tip."""
    reasons = []
    if github['heads']:
        reasons.append('slice_has_pull_request')
    if github['remote'] is not None:
        reasons.append('slice_pushed')
    if github['dependents']:
        reasons.append('open_dependents')
    if isinstance(issue_branch, str) and branch == issue_branch:
        reasons.append('slice_is_issue_branch')   # an entry with `slice` that points at the issue's own branch: never a slice to delete
    elif not isinstance(issue_branch, str) or not closeout.valid_branch(issue_branch):
        reasons.append('slice_issue_branch_unknown')
    elif not reasons:
        issue_tip = local_tip(ctx['root'], issue_branch)
        if issue_tip is None:
            base = base_ref(ctx['root'], ctx['base'])
            inside = None if base is None else is_ancestor(ctx['root'], tip, base)
            if inside is None:
                reasons.append('ancestry_unverifiable')
            elif not inside:
                reasons.append('slice_issue_branch_unknown')
        elif tip == issue_tip:
            reasons.append('slice_not_in_issue_branch')   # freshly cut, nothing of its own merged yet
        else:
            inside = is_ancestor(ctx['root'], tip, issue_tip)
            if inside is None:
                reasons.append('ancestry_unverifiable')
            elif not inside:
                reasons.append('slice_not_in_issue_branch')
    return reasons


def released_remote(ctx, item, branch, github):
    """Does the remote branch of this candidate go too (issue 70, S3)? Only the branch of an issue (the entry of the
    issue without `slice`, never an integration or a release branch), when there is an `origin`, GitHub has the branch
    and the remote-tracking base already contains its tip there. Anything Git cannot tell keeps it."""
    if item.get('issue') is None or item.get('slice') or item.get('integration'):
        return False
    if ctx['issue_branches'].get(item['issue']) != branch or branch.endswith('-integra'):
        return False
    if RELEASE.fullmatch(branch.rsplit('/', 1)[-1]) or not ctx['origin']:
        return False
    remote = github.get('remote')
    if not isinstance(remote, str) or not OID.fullmatch(remote):
        return False
    base = released_base_ref(ctx['root'], ctx['base'])
    return base is not None and is_ancestor(ctx['root'], remote, base) is True


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
    sliced = bool(item.get('slice'))
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
        if not junctions_readable():
            return ['junction_unverifiable'], None   # a junction left in it could lead the removal outside it
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
        if records.is_dir() and any(entry.name != 'out' for entry in records.iterdir()):   # out/ is never archived
            cautions.append('frontlights_records')
        if ignored:
            cautions.append('ignored_files')
        if item.get('branch') and item['branch'] != branch:
            cautions.append('branch_differs_from_authorization')
    if github is None or github['cut']:
        reasons.append('pull_requests_unreadable')
    else:
        reasons += (integration_reasons(ctx, github, tip) if integration
                    else slice_reasons(ctx, github, tip, item.get('issue_branch'), branch) if sliced
                    else pull_reasons(ctx, github, tip))
    if reasons:
        return reasons, None
    if integration:
        cautions.append('local_only_integration')
    elif sliced:
        cautions.append('slice_merged_into_issue_branch')
    elif not github['heads']:
        cautions.append('contained_in_base_without_pull_request')   # issue 32: a merge into the local main, no pull request
    main = ctx['main_path']
    commands = []
    destination = None
    if 'frontlights_records' in cautions:
        # the records go to the main worktree before the worktree that holds them is removed
        destination = records_destination(main, item, registered['path'], tip)
        commands.append({'kind': 'copy_records',
                         'argv': [ctx['python'], ctx['script'], 'archive', '--from', f"{registered['path']}/.frontlights",
                                  '--to', destination]})
    if registered is not None:
        commands.append({'kind': 'remove_worktree', 'argv': ['git', '-C', main, 'worktree', 'remove', registered['path']]})
    if released_remote(ctx, item, branch, github):
        # the written exception (issue 70): the released issue branch on GitHub goes before the local one, so a
        # failed push skips the local delete of the same item
        commands.append({'kind': 'delete_remote_branch', 'argv': ['git', '-C', main, 'push', REMOTE, '--delete', branch]})
    commands.append({'kind': 'delete_branch', 'argv': ['git', '-C', main, 'branch', '-D', branch]})
    for command in commands:
        command['item'] = branch   # a failed command skips the rest of its item
    record = {'key': branch, 'issue': item.get('issue'), 'slice': item.get('slice'), 'release': False,
              'path': path if registered is not None else None, 'branch': branch, 'tip': tip,
              'pullRequests': sorted(p['number'] for p in github['heads'] if isinstance(p.get('number'), int)),
              'removeWorktree': registered is not None, 'recordsTo': destination, 'cautions': cautions,
              'ask': False, 'commands': commands}
    if ignored:
        record['ignoredCount'] = len(ignored)
        record['ignored'] = [rs.clean(name, 200) for name in ignored[:MAX_IGNORED]]
        kept = [name for name in ignored if not disposable(name, ctx.get('disposable', ()))
                and not same_as_main(main, registered['path'], name)]
        if kept:
            record.update(ask=True, askReason='ignored_files_besides_dependencies',
                          askIgnored=[rs.clean(name, 200) for name in kept[:MAX_IGNORED]])
    return [], record


def assess_release(ctx, branch, github):
    """(reasons it stays, record when it can go) for a local release branch: the rule of an issue branch (its tip is
    the head of a merged pull request that reached the base, or the base contains it), and no worktree has it."""
    tip = local_tip(ctx['root'], branch)
    if tip is None:
        return ['nothing_left'], None
    if is_protected(branch, ctx['protected']):
        return ['protected_branch'], None
    if github is None or github['cut']:
        return ['pull_requests_unreadable'], None
    reasons = pull_reasons(ctx, github, tip)
    if not reasons and any(e['branch'] == branch for e in ctx['listing']):
        reasons = ['checked_out_elsewhere']
    if reasons:
        return reasons, None
    return [], {'key': branch, 'issue': None, 'slice': None, 'release': True, 'path': None, 'branch': branch, 'tip': tip,
                'pullRequests': sorted(p['number'] for p in github['heads'] if isinstance(p.get('number'), int)),
                'removeWorktree': False, 'recordsTo': None, 'cautions': ['merged_release_branch'], 'ask': False,
                'commands': [{'kind': 'delete_branch', 'item': branch,
                              'argv': ['git', '-C', ctx['main_path'], 'branch', '-D', branch]}]}


def op_plan(config, root='.', issues=None, base=None, worktrees=(), integrations=(), gh=None, from_authorizations=False,
            page=1):
    """Read only: what can be removed now, with the commands in the order to run them, and what stays. With
    `from_authorizations`, the issues (unless `issues` narrows them) and the base (unless `base` is given) come from
    the authorization records (`authorization_scope`)."""
    gh = gh or rs.gh_default
    repository = closeout.load_project(config)
    listing = list_worktrees(root)
    main_entry = listing[0]
    records_root = root if (Path(root) / '.frontlights').is_dir() else main_entry['path']
    if from_authorizations:
        given = None if issues is None or issues == '' or issues == [] else closeout.parse_numbers(issues)
        numbers, recorded = authorization_scope(records_root, given)
        base = base or recorded
        if not numbers and not worktrees and not integrations:
            return {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'expectedBase': base,
                    'baseSource': 'authorization' if recorded else None, 'issues': [], 'commands': [], 'candidates': [],
                    'excluded': [], 'alreadyClean': 0, 'ask': False,
                    'message': 'No authorization record lists issue ids: nothing to clean.'}
        numbers = numbers or [0]   # only named worktrees: no issue of the records takes part
    else:
        require(issues is not None and issues != '' and issues != [], 'plan needs the issues whose work is done: pass --issues 12,13')
        numbers = closeout.parse_numbers(issues)
        recorded = None
    require(base is None or closeout.valid_branch(base), '--base must be a plain branch name')
    authorized, protected, prefixes = authorized_worktrees(records_root, set(numbers))
    # the branch of the issue (`<prefix>issue-<n>`) wins over a later entry of the same issue without `slice`, such as
    # its local integration branch (`<prefix>issue-<n>-integra`, issue 70): the slices are merged into the former
    issue_branches = {}
    for e in authorized:
        if e.get('slice') or not e['branch']:
            continue
        own = e['branch'].rsplit('/', 1)[-1] == f"issue-{e['issue']}"
        if own or not issue_branches.get(e['issue'], (None, False))[1]:
            issue_branches[e['issue']] = (e['branch'], own)
    issue_branches = {number: branch for number, (branch, _) in issue_branches.items()}
    for entry in authorized:
        if entry.get('slice'):
            entry['issue_branch'] = issue_branches.get(entry['issue'])
    items, seen, gone = [], {}, 0
    known = {norm(e['path']) for e in listing}
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
        if entry.get('issue') is not None and nothing_left(main_entry['path'], entry, key, known):
            gone += 1   # what `assess` would count as already clean: it never takes a place under the cap
            continue
        items.append(entry)
    # more than MAX_ITEMS worktrees are read a page at a time (`page`, 1-based); the release branches and the saved
    # outputs belong to the first page
    require(isinstance(page, int) and page >= 1, '--page must be a positive integer')
    pages = max(1, -(-len(items) // MAX_ITEMS))
    require(page <= pages, f'there are {pages} page(s) of worktrees; --page {page} has none')
    items = items[(page - 1) * MAX_ITEMS:page * MAX_ITEMS]
    default = read_default_branch(gh, repository)
    expected = base or default
    require(isinstance(expected, str), 'the approved base is unknown: pass --base <branch> (the repository default could not be read)')
    by_path = {norm(e['path']): e for e in listing}
    protected = list(protected) + ['main', 'master', expected] + ([default] if default else [])
    main = main_entry['path']
    releases = [b for b in release_branches(main, prefixes) if not is_protected(b, protected)][:MAX_ITEMS] if page == 1 else []
    outputs = saved_outputs(main) if page == 1 else None
    source = ('authorization' if recorded and base == recorded else 'argument') if base else 'default_branch'
    result = {'ok': True, 'exitCode': 0, 'project': repository, 'repository': repository, 'expectedBase': expected,
              'baseSource': source, 'issues': [n for n in numbers if n], 'commands': [], 'candidates': [], 'excluded': [],
              'alreadyClean': gone, 'ask': False, 'page': page, 'pages': pages}
    if not items and not releases and outputs is None:
        result['message'] = (f'{gone} recorded worktree(s) of these issues are already gone, with their branches: nothing to clean.'
                              if gone else
                              'No worktree is recorded for these issues in an authorization and none was named: nothing to clean. '
                              'Name one with --worktree PATH.')
        return result
    resolved = []
    for item in items:
        registered = by_path.get(norm(item['path']))
        branch = registered['branch'] if registered is not None else item['branch']
        resolved.append((item, registered, branch))
    names = sorted({b for _, _, b in resolved if b and closeout.valid_branch(b) and not is_protected(b, protected)} | set(releases))
    github = read_branches(gh, repository, names) if names else {}
    ctx = {'root': main, 'main': norm(main), 'main_path': main, 'base': expected, 'origin': has_origin(main),
           'issue_branches': issue_branches,
           'protected': protected, 'gh': gh, 'repository': repository, 'more': {}, 'delivered': set(), 'listing': listing,
           'disposable': config_disposable(config),
           'python': Path(sys.executable).as_posix(), 'script': Path(__file__).resolve().as_posix()}
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
    taken = {c['branch'] for c in result['candidates']} | {e['branch'] for e in result['excluded']}
    for branch in releases:
        if branch in taken:
            continue   # a release branch an authorization names as a worktree was judged above
        reasons, record = assess_release(ctx, branch, github.get(branch))
        if record is not None and any(frontlights.UNSAFE_CHARS.search(a) for c in record['commands'] for a in c['argv']):
            reasons, record = ['unsafe_path'], None
        if record is not None:
            result['candidates'].append(record)
        elif reasons in (['checked_out_elsewhere'], ['unsafe_path']):
            # merged, but it cannot go: said; a release still in flight is no business of the cleanup
            result['excluded'].append({'issue': None, 'path': None, 'branch': branch, 'reasons': reasons})
    # the slices of an issue come before the issue's own worktree: its branch is what they are judged against; the
    # release branches go last
    result['candidates'].sort(key=lambda c: (c['release'], c['issue'] is None, c['issue'] or 0, c.get('slice') is None, c['branch']))
    if outputs is not None:
        result['candidates'].append(outputs)   # always asked: removing them is the user's call
    if ctx['origin']:
        # GitHub deletes the merged head branches; the fetch drops the remote-tracking refs they left here
        result['commands'].append({'kind': 'fetch_prune', 'item': None, 'argv': ['git', '-C', main, 'fetch', '--prune', REMOTE]})
    for candidate in result['candidates']:
        if not candidate['ask']:
            result['commands'] += candidate['commands']
    asking = [c for c in result['candidates'] if c['ask']]
    result['ask'] = bool(asking)
    parts = [f'{len(result["candidates"])} worktree(s) or branch(es) can be removed.' if result['candidates']
             else 'Nothing can be removed now.']
    if result['excluded']:
        parts.append(f'{len(result["excluded"])} stay (see excluded for the reason of each).')
    if result['alreadyClean']:
        parts.append(f'{result["alreadyClean"]} already gone.')
    parts.append('Nothing was removed. Run `commands` in order, with no question; verify afterwards.')
    if asking:
        parts.append(f'{len(asking)} candidate(s) hold ignored files besides dependency or build folders, or saved '
                     'outputs (`ask`): their commands are not in `commands` and run only after the user said yes.')
    if pages > 1:
        parts.append(f'Page {page} of {pages} of worktrees (at most {MAX_ITEMS} each): pass --page for the next one; '
                     '`run` reads them all.')
    result['message'] = ' '.join(parts)
    return result


def saved_outputs(main):
    """The candidate for the saved outputs of the main worktree (`.frontlights/out`, what `_cli.emit` writes) older than
    OUT_AGE_DAYS, or None when there is none. Always `ask: true`: removing them is the user's call, never silent."""
    folder = Path(main) / '.frontlights' / 'out'
    old = old_outputs(folder)
    if not old:
        return None
    command = {'kind': 'unlink_outputs', 'item': 'out',
               'argv': [Path(sys.executable).as_posix(), Path(__file__).resolve().as_posix(), 'unlink', '--out',
                        folder.as_posix()]}
    return {'key': 'out', 'issue': None, 'slice': None, 'release': False, 'path': folder.as_posix(), 'branch': None,
            'tip': None, 'pullRequests': [], 'removeWorktree': False, 'recordsTo': None, 'cautions': ['saved_outputs'],
            'files': len(old), 'ask': True, 'askReason': 'saved_outputs',
            'askIgnored': [p.name for p in old[:MAX_IGNORED]], 'commands': [command]}


def old_outputs(folder, now=None):
    """The files of an `out` folder named as `_cli.save_output` names them, regular (never a link or a junction) and
    older than OUT_AGE_DAYS, oldest first. [] when the folder is missing, is a link, or cannot be read."""
    folder = Path(folder)
    now = time.time() if now is None else now
    try:
        if not folder.is_dir() or is_link(folder):
            return []
        found = []
        for entry in folder.iterdir():
            if (OUT_NAME.fullmatch(entry.name) and not is_link(entry) and entry.is_file()
                    and now - entry.stat().st_mtime > OUT_AGE_DAYS * 86400):
                found.append(entry)
    except OSError:
        return []
    return sorted(found, key=lambda e: (e.stat().st_mtime, e.name))


def op_unlink(folder):
    """Remove the saved outputs (`unlink_outputs`) of a `.frontlights/out` folder of a worktree of this repository: only
    the files `old_outputs` names (regular, named by `_cli.save_output`, older than OUT_AGE_DAYS), recomputed now; never
    a folder, a link or another file. Run only after the user's yes to the candidate `out`."""
    require(folder, 'unlink needs --out <worktree>/.frontlights/out')
    target = Path(os.path.abspath(folder))
    require(target.name == 'out' and target.parent.name == '.frontlights', '--out must be a .frontlights/out folder')
    require(target.is_dir() and not is_link(target) and not is_link(target.parent),
            '--out must be a real folder, not a link or a junction')
    listing = list_worktrees(target.parent.parent)
    require(any(norm(e['path']) == norm(target.parent.parent) for e in listing),
            '--out must be inside a worktree of this repository')
    removed, failed = [], []
    for entry in old_outputs(target):
        try:
            entry.unlink()
            removed.append(entry.name)
        except OSError:
            failed.append(entry.name)
    return {'ok': not failed, 'exitCode': 0 if not failed else 1, 'out': target.as_posix(), 'removed': len(removed),
            'failed': failed, 'message': f'{len(removed)} saved output(s) removed from {target.as_posix()}.'
            + (f' {len(failed)} could not be removed.' if failed else '')}


ARCHIVE_TEMP = re.compile(r'^\..+\.frontlights-archive-tmp$')


def archive_temp_name(name):
    """The temporary name a file of `archive` is copied under, in its own folder, before it is renamed into place."""
    return f'.{name}.frontlights-archive-tmp'


def is_link(path):
    """A symlink, or a Windows junction (which `is_symlink` does not see)."""
    return os.path.islink(path) or is_junction(path)


def is_junction(path):
    """A Windows junction (`os.path.isjunction`, Python 3.12 and later; none before it is read)."""
    return bool(getattr(os.path, 'isjunction', lambda _: False)(path)) and not os.path.islink(path)


def junctions_readable():
    """False on Windows before Python 3.12: no `os.path.isjunction`, so a junction in a worktree cannot be seen, and
    removing that worktree could reach through it (`junction_unverifiable`)."""
    return os.name != 'nt' or hasattr(os.path, 'isjunction')


def within(path, folder):
    """Whether the real path of `path` is `folder` or lies under it."""
    real, home = norm(path), norm(folder)
    return real == home or real.startswith(home.rstrip(os.sep) + os.sep)


def same_entry(origin, copy):
    """Whether `copy` is what `shutil.copytree(..., symlinks=True)` makes of `origin`: the same link, or a regular file
    with the same bytes."""
    if origin.is_symlink() or copy.is_symlink():
        return origin.is_symlink() and copy.is_symlink() and os.readlink(origin) == os.readlink(copy)
    return origin.is_file() and copy.is_file() and filecmp.cmp(origin, copy, shallow=False)


def archived_part(origin, target):
    """`(present, leftovers)`: the relative paths of the files already in `target` when every one of them is the same
    as in `origin` (an earlier copy of these records, whole or stopped half-way), and the temporary files an
    interrupted copy left there (review r3 of issue 63, R3-2); None when `target` holds anything else, a junction, or
    an entry other than a symlink whose real path leaves `target` (R3-1: the copy would write through it)."""
    present, leftovers = set(), []
    for folder, dirs, files in os.walk(target):
        here = Path(folder)
        for name in dirs + files:
            copy, relative = here / name, (here / name).relative_to(target)
            if is_junction(copy) or (not copy.is_symlink() and not within(copy, target)):
                return None
            if name in dirs and not copy.is_symlink():
                if not (origin / relative).is_dir() or is_link(origin / relative):
                    return None
                continue
            if (not copy.is_symlink() and copy.is_file() and ARCHIVE_TEMP.match(name)
                    and not os.path.lexists(origin / relative)):
                leftovers.append(copy)
                continue
            if not same_entry(origin / relative, copy):
                return None
            present.add(relative.as_posix())
    return present, leftovers


def copy_whole(src, dst):
    """The `copy_function` of `archive`: copy under a temporary name in the same folder, then rename into place, so a
    final file is never an incomplete copy (review r3 of issue 63, R3-2)."""
    temporary = os.path.join(os.path.dirname(dst), archive_temp_name(os.path.basename(dst)))
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    out = os.open(temporary, flags, 0o600)   # exclusive: an entry already there, a link included, is never written
    try:                                      # through (review r4 of issue 63, R4-1)
        with open(src, 'rb') as reading, os.fdopen(out, 'wb') as writing:
            shutil.copyfileobj(reading, writing)
        shutil.copystat(src, temporary)
        os.replace(temporary, dst)
    except BaseException:
        if os.path.lexists(temporary) and not os.path.islink(temporary):
            os.unlink(temporary)
        raise
    return dst


def op_archive(source, destination):
    """Copy the Frontlights records of a worktree (`<worktree>/.frontlights`) into `destination`, a folder under the
    `.frontlights` folder of the main worktree of the same repository (Git says which). A destination that does not
    exist or is empty gets the copy; one whose files are all the same as the records (same paths, same bytes) is an
    earlier copy of them (review r2 of issue 63, R2-1: the removal after it failed), so the files it lacks are copied
    and it is ok; one with any differing or extra file is refused, nothing copied: an earlier archive is never
    overwritten. A symlink or junction between the main `.frontlights` and the destination (the destination included),
    a junction inside the destination or in the records, or an entry of the destination whose real path leaves it, is
    refused too (review r3 of issue 63, R3-1). Each file is copied under a temporary name, created exclusively, and
    renamed into place; a temporary file an interrupted run left in the destination is removed (R3-2); an entry of the
    records named like that temporary file is refused, nothing copied (R4-1). The one write of this helper, and only
    into `destination`."""
    require(source and destination, 'archive needs --from <worktree>/.frontlights and --to <folder>')
    raw = Path(os.path.abspath(destination))
    origin, target = Path(source).resolve(), Path(destination).resolve()
    require(origin.name == '.frontlights' and origin.is_dir(), '--from must be the .frontlights folder of a worktree')
    records = Path(list_worktrees(origin.parent)[0]['path']).resolve() / '.frontlights'

    def holds(outer, inner):
        return outer == inner or outer in inner.parents
    require(norm(records) != norm(target) and any(norm(records) == norm(p) for p in target.parents),
            '--to must be a folder under the .frontlights folder of the main worktree')
    require(not holds(origin, target) and not holds(target, origin), '--from and --to must not hold one another')
    linked = ('a symlink or junction on the way to --to leads the copy elsewhere: nothing was copied; the worktree '
              'keeps its records')
    try:
        for step in (raw, *raw.parents):   # from the destination up to the main `.frontlights`, both included
            if os.path.normcase(str(step)) == os.path.normcase(str(records)):
                break
            require(not (os.path.lexists(step) and is_link(step)), linked)
            if norm(step) == norm(records):
                break
        for folder, dirs, files in os.walk(origin):
            require(not any(is_junction(Path(folder) / n) for n in dirs + files),
                    'the records hold a junction, which is not copied through: nothing was copied; the worktree keeps them')
            require(not any(ARCHIVE_TEMP.match(n) for n in dirs + files),
                    'the records hold an entry named like the temporary file of the copy (.<name>.frontlights-archive-tmp), '
                    'which the copy would take for its own: nothing was copied; the worktree keeps them')
        found = ((set(), []) if not target.exists() else
                 archived_part(origin, target) if target.is_dir() and not is_link(target) else None)
    except OSError:
        raise Refusal(linked)
    require(found is not None, '--to already holds files that differ from these records or that they do not have, or '
                               'a link that leaves it: nothing was copied, so no earlier archive is overwritten; the '
                               'worktree keeps its records')
    present, leftovers = found

    def skip(folder, names):   # what an earlier copy already holds, the same (checked above), and out/ (saved outputs)
        return [n for n in names if (Path(folder) / n).relative_to(origin).as_posix() in present
                or (Path(folder) == origin and n == 'out')]
    try:
        for leftover in leftovers:   # a temporary file of an interrupted run, inside the destination
            leftover.unlink()
        shutil.copytree(origin, target, symlinks=True, dirs_exist_ok=True, ignore=skip, copy_function=copy_whole)
    except (OSError, shutil.Error):
        raise Refusal('the records could not be copied; nothing was removed, so the worktree keeps them')
    copied = sum(1 for p in target.rglob('*') if p.is_file())
    where = target.as_posix()
    message = (f'{copied} file(s) of records are in {where}.' if not present else
               f'{where} already held {len(present)} of these file(s), the same; {copied - len(present)} missing '
               f'file(s) copied, {copied} in all.' if copied > len(present) else
               f'{where} already holds these {copied} file(s), the same: the records were already archived; nothing copied.')
    return {'ok': True, 'exitCode': 0, 'to': rs.clean(where, 300), 'files': copied,
            'alreadyArchived': len(present), 'message': message}


def op_verify(config, root='.', worktrees=(), branches=(), gh=None, records=(), remote_branches=()):
    """Read only: whether each named worktree and local branch is gone, each named remote branch is gone from `origin`
    (`git ls-remote`) and each records folder holds the copy."""
    repository = closeout.load_project(config)
    require(worktrees or branches or records or remote_branches,
            'verify needs what to check: pass --worktree PATH, --branch NAME, --remote-branch NAME and/or --records FOLDER')
    require(all(closeout.valid_branch(b) for b in branches), '--branch must be a plain branch name')
    require(all(closeout.valid_branch(b) for b in remote_branches), '--remote-branch must be a plain branch name')
    listing = list_worktrees(root)
    registered = {norm(e['path']) for e in listing}
    entries = []
    for text in worktrees:
        path = Path(text)
        path = path if path.is_absolute() else Path(root) / path
        gone = norm(path) not in registered and not path.exists()
        entries.append({'kind': 'worktree', 'name': rs.clean(str(text), 300), 'gone': gone})
    for branch in branches:
        entries.append({'kind': 'branch', 'name': branch, 'gone': local_tip(listing[0]['path'], branch) is None})
    for branch in remote_branches:
        code, out = git(listing[0]['path'], 'ls-remote', '--heads', REMOTE, f'refs/heads/{branch}')
        listed = {line.split('\t', 1)[-1].strip() for line in out.splitlines() if line.strip()}
        entry = {'kind': 'remote_branch', 'name': branch, 'gone': code == 0 and f'refs/heads/{branch}' not in listed}
        if code != 0:
            entry['unreadable'] = True   # the remote could not be read: not known to be gone
        entries.append(entry)
    for text in records:
        folder = Path(text)
        folder = folder if folder.is_absolute() else Path(root) / folder
        try:
            copied = folder.is_dir() and any(p.is_file() for p in folder.rglob('*'))
        except OSError:
            copied = False
        entries.append({'kind': 'records', 'name': rs.clean(str(text), 300), 'copied': copied})
    waiting = [e['name'] for e in entries if not e.get('gone', e.get('copied'))]
    result = {'ok': not waiting, 'exitCode': 0 if not waiting else 1, 'project': repository, 'repository': repository,
              'entries': entries}
    result['message'] = (f'All {len(entries)} item(s) are done.' if not waiting else
                         f'{len(waiting)} of {len(entries)} item(s) are not gone or not copied yet: ' + ', '.join(waiting) + '.')
    return result


# ---------------------------------------------------------------- run: the plan, executed

def execute(argv):
    """(exit code, stdout, stderr) of a command of the plan, run without a shell. Its text is data, never repeated
    whole: only a bounded, cleaned line reaches the result."""
    environment = rs.gh_environment()
    environment['GIT_TERMINAL_PROMPT'] = '0'
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=GIT_TIMEOUT * 4, stdin=subprocess.DEVNULL, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        return 1, '', 'the command could not be run or did not finish in time'
    return done.returncode, done.stdout, done.stderr


def undo_junctions(worktree):
    """Undo the junctions (and directory symlinks) at the first JUNCTION_DEPTH levels of `worktree` with `os.rmdir`,
    which removes the link and never what it points at, so `git worktree remove` cannot reach through one. Never
    inside `.frontlights` (the archive refuses a junction there), never the target. Returns the relative paths undone;
    raises Refusal when one cannot be undone (the worktree then stays)."""
    undone = []
    top = Path(worktree)
    level = [top]
    for _ in range(JUNCTION_DEPTH):
        deeper = []
        for folder in level:
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                path = Path(entry.path)
                if path.parent == top and entry.name in ('.frontlights', '.git'):
                    continue
                if is_junction(path) or (os.path.islink(path) and os.path.isdir(path)):
                    try:
                        if os.path.islink(path) and os.name != 'nt':
                            os.unlink(path)   # a POSIX symlink to a folder: unlink removes the link alone
                        else:
                            os.rmdir(path)    # a junction or a Windows directory symlink: the link alone
                    except OSError:
                        raise Refusal(f'the link {path.relative_to(top).as_posix()} could not be undone; the worktree '
                                      'stays, so nothing outside it is reached')
                    undone.append(path.relative_to(top).as_posix())
                elif entry.is_dir(follow_symlinks=False):
                    deeper.append(path)
        level = deeper
    return undone


def integration_paths(root):
    """The worktree paths of the `-integra` entries of the authorization records (`--integration` takes only those)."""
    found = set()
    for path in closeout.authorization_records(root):
        data = closeout.read_record(path)
        entries = data.get('worktrees') if isinstance(data, dict) else None
        for entry in entries if isinstance(entries, list) else []:
            if (isinstance(entry, dict) and isinstance(entry.get('branch'), str) and entry['branch'].endswith('-integra')
                    and isinstance(entry.get('path'), str) and entry['path'].strip()):
                found.add(norm(entry['path']))
    return found


def evidence_path(main):
    """`<main>/.frontlights/cleanup-<AAAAMMDD-HHMMSS>[-k].json`, São Paulo time, never an existing name."""
    folder = Path(main) / '.frontlights'
    stamp = _cli.sao_paulo_now().strftime('%Y%m%d-%H%M%S')
    for attempt in range(1, 100):
        path = folder / (f'cleanup-{stamp}' + ('' if attempt == 1 else f'-{attempt}') + '.json')
        if not path.exists():
            return path
    raise Refusal('no free name for the cleanup evidence')


def op_run(config, root='.', issues=None, base=None, integrations=(), yes=(), gh=None, from_authorizations=False,
           runner=None):
    """Plan again in this process and run only the commands of that fresh plan (see the module's docstring)."""
    runner = runner or execute
    require(from_authorizations or not (issues is None or issues == '' or issues == []),
            'run needs --from-authorizations (or --issues 12,13)')
    listing = list_worktrees(root)
    main = listing[0]['path']
    records_root = root if (Path(root) / '.frontlights').is_dir() else main
    allowed = integration_paths(records_root)
    for path in integrations:
        require(norm(path) in allowed, '--integration takes only the worktree of an -integra entry of the authorization '
                                       'records')
    require(all(isinstance(k, str) and (k == 'out' or closeout.valid_branch(k)) for k in yes),
            '--yes takes the branch of a candidate with ask (or out), as many times as needed')
    ran, failed, session, warnings = [], [], [], []
    if has_origin(main):
        argv = ['git', '-C', main, 'fetch', '--prune', REMOTE]
        code, _, _ = runner(argv)
        ran.append({'item': None, 'kind': 'fetch_prune', 'argv': argv, 'exitCode': code})
        if code != 0:
            warnings.append('fetch_failed: the plan judged by origin/<base> as of the last fetch')
    plans = [op_plan(config, root, issues, base, (), integrations, gh, from_authorizations, 1)]
    for page in range(2, plans[0]['pages'] + 1):
        plans.append(op_plan(config, root, issues, base, (), integrations, gh, from_authorizations, page))
    candidates = [c for plan in plans for c in plan['candidates']]
    excluded = [dict(e) for plan in plans for e in plan['excluded']]
    for entry in excluded:
        if 'locked_worktree' in entry['reasons']:
            entry['reasons'] = ['in_use']
            entry['inUse'] = 'locked'
    approved = set(yes)
    asked = [{'key': c['key'], 'path': c['path'], 'askReason': c.get('askReason'), 'askIgnored': c.get('askIgnored', [])}
             for c in candidates if c['ask'] and c['key'] not in approved]
    unused = sorted(approved - {c['key'] for c in candidates if c['ask']})
    removed, deleted, copied = [], [], []
    for candidate in candidates:
        if candidate['ask'] and candidate['key'] not in approved:
            continue
        commands = candidate['commands']
        for position, command in enumerate(commands):
            kind, argv = command['kind'], command['argv']
            step = {'item': candidate['key'], 'kind': kind, 'argv': argv}
            if kind == 'delete_remote_branch':
                # no script runs `git push`: the session runs this and what follows of the item, in order
                session += [dict(c) for c in commands[position:]]
                break
            try:
                if kind == 'copy_records':
                    outcome = op_archive(argv[argv.index('--from') + 1], argv[argv.index('--to') + 1])
                    step['exitCode'] = 0
                    copied.append(outcome['to'])
                elif kind == 'unlink_outputs':
                    outcome = op_unlink(argv[argv.index('--out') + 1])
                    step.update(exitCode=outcome['exitCode'], removed=outcome['removed'])
                    require(outcome['ok'], outcome['message'])
                elif kind == 'remove_worktree':
                    step['junctionsUndone'] = undo_junctions(argv[-1])
                    code, _, err = runner(argv)
                    step['exitCode'] = code
                    if code != 0:
                        if Path(argv[-1]).exists() and IN_USE.search(err or ''):
                            excluded.append({'issue': candidate['issue'], 'path': rs.clean(argv[-1], 300),
                                             'branch': candidate['branch'], 'reasons': ['in_use'], 'inUse': 'busy'})
                            step['inUse'] = True
                        raise Refusal(f'git worktree remove failed (exit {code})')
                    removed.append(argv[-1])
                else:
                    code, _, _ = runner(argv)
                    step['exitCode'] = code
                    require(code == 0, f'{kind} failed (exit {code})')
                    if kind == 'delete_branch':
                        deleted.append(argv[-1])
            except Refusal as error:
                step.setdefault('exitCode', 1)
                step['message'] = rs.clean(str(error), 300)
                ran.append(step)
                failed.append({'item': candidate['key'], 'kind': kind, 'message': step['message']})
                break   # the rest of this item does not run
            ran.append(step)
    verify = None
    if removed or deleted or copied:
        verify = op_verify(config, main, removed, deleted, gh, copied)
    result = {'ok': not failed and (verify is None or verify['ok']), 'project': plans[0]['project'],
              'repository': plans[0]['repository'], 'expectedBase': plans[0]['expectedBase'],
              'issues': plans[0].get('issues', []), 'ran': ran, 'failed': failed, 'excluded': excluded,
              'alreadyClean': sum(plan['alreadyClean'] for plan in plans), 'ask': asked, 'yesUnused': unused,
              'sessionCommands': session, 'verify': verify, 'warnings': warnings}
    result['exitCode'] = 0 if result['ok'] else 1
    parts = [f'{len(removed)} worktree(s) and {len(deleted)} branch(es) removed.']
    if failed:
        parts.append(f'{len(failed)} item(s) stopped at a failed command (failed); never retried with force.')
    if session:
        parts.append(f'{len(session)} command(s) left for the session, in order (sessionCommands: the push that deletes '
                     'a released issue branch on origin, then its local delete).')
    if asked:
        parts.append(f'{len(asked)} candidate(s) wait for their own question (ask); run again with --yes <key> after a yes.')
    if unused:
        parts.append('--yes named no asking candidate: ' + ', '.join(unused) + '.')
    if excluded:
        parts.append(f'{len(excluded)} stay (excluded).')
    result['message'] = ' '.join(parts)
    try:
        path = evidence_path(main)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
        result['evidence'] = path.as_posix()
    except (OSError, Refusal):
        result['evidence'] = None
        result['warnings'].append('evidence_not_written: the cleanup evidence file could not be written')
    return result


# ---------------------------------------------------------------- command line

def run(operation, config, root='.', issues=None, base=None, worktrees=(), branches=(), gh=None, integrations=(),
        records=(), source=None, destination=None, remote_branches=(), from_authorizations=False, page=1, yes=(),
        runner=None, out=None):
    try:
        if operation == 'plan':
            result = op_plan(config, root, issues, base, worktrees, integrations, gh, from_authorizations, page)
        elif operation == 'run':
            result = op_run(config, root, issues, base, integrations, yes, gh, from_authorizations, runner)
        elif operation == 'unlink':
            result = op_unlink(out)
        elif operation == 'verify':
            result = op_verify(config, root, worktrees, branches, gh, records, remote_branches)
        elif operation == 'archive':
            result = op_archive(source, destination)
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


def build_parser():
    parser = _cli.JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('plan', 'verify', 'run'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--config', help="the project's .frontlights/config.json (default: the one of the main worktree)")
        command.add_argument('--root', help="the project's main worktree (default: the main worktree of the current directory)")
        if name != 'run':
            command.add_argument('--worktree', action='append', default=[], dest='worktrees', help='a worktree path, as many times as needed')
        if name in ('plan', 'run'):
            command.add_argument('--issues', help='issue numbers whose work is done, such as 12,13 (required without '
                                                  '--from-authorizations, which it then narrows)')
            command.add_argument('--from-authorizations', action='store_true', dest='from_authorizations',
                                 help='the issues (the issue_ids) and the base (base.branch of the newest record) from '
                                      '.frontlights/authorization*.json')
            command.add_argument('--base', help="the approved base branch; without it, the repository's default branch")
            command.add_argument('--integration', action='append', default=[], dest='integrations',
                                 help="the local-only integration worktree of a family, as many times as needed"
                                      + (' (only an -integra entry of the records)' if name == 'run' else ''))
            if name == 'plan':
                command.add_argument('--page', type=int, default=1, help=f'the page of worktrees, {MAX_ITEMS} each (default 1)')
            else:
                command.add_argument('--yes', action='append', default=[], dest='yes',
                                     help='the key (branch, or out) of a candidate with ask the user said yes to, in its '
                                          'own question; as many times as needed')
        else:
            command.add_argument('--branch', action='append', default=[], dest='branches', help='a branch name, as many times as needed')
            command.add_argument('--remote-branch', action='append', default=[], dest='remote_branches',
                                 help='a branch name on origin (the `delete_remote_branch` of plan), as many times as needed')
            command.add_argument('--records', action='append', default=[], dest='records',
                                 help='a folder the records of a worktree were copied to (the `recordsTo` of plan)')
    command = sub.add_parser('unlink', allow_abbrev=False)
    command.add_argument('--out', required=True, help='the .frontlights/out folder whose old saved outputs go (after a yes)')
    command = sub.add_parser('archive', allow_abbrev=False)
    command.add_argument('--from', required=True, dest='source', help='the .frontlights folder of the worktree')
    command.add_argument('--to', required=True, dest='destination', help='the folder of the main worktree it is copied to')
    return parser


def resolve_defaults(args):
    """--root and --config the command line left out, by the rules of `_cli`."""
    if hasattr(args, 'root'):
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root)
    return args


def main(argv=None):
    _cli.utf8_streams()
    try:
        args = resolve_defaults(_cli.output_flags(build_parser()).parse_args(argv))
    except _cli.UsageError as error:
        return _cli.print_usage_error(error)
    try:
        result = run(args.operation, getattr(args, 'config', None), getattr(args, 'root', '.'), getattr(args, 'issues', None),
                     getattr(args, 'base', None), getattr(args, 'worktrees', []), getattr(args, 'branches', []),
                     integrations=getattr(args, 'integrations', []), records=getattr(args, 'records', []),
                     remote_branches=getattr(args, 'remote_branches', []),
                     from_authorizations=getattr(args, 'from_authorizations', False),
                     page=getattr(args, 'page', 1), yes=getattr(args, 'yes', []), out=getattr(args, 'out', None),
                     source=getattr(args, 'source', None), destination=getattr(args, 'destination', None))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    _cli.emit(json.dumps(result, indent=2, ensure_ascii=True), args.operation, args.full)
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
