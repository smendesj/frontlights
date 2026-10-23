#!/usr/bin/env python3
"""Homologation helper (issue 32): the local base branch (`main`) is the homologation bench of the project. It is
never pushed to the remote base; the release pushes its tip to a branch name of its own (`git push origin
main:refs/heads/<release branch>`) and opens one pull request. This module keeps the bench
current with the remote and plans the release. Every Git call is a list argv run without a shell, with a timeout and
GIT_TERMINAL_PROMPT=0. `run` knows seven operations, `sync`, `bundle`, `release-plan`, `suite`, `suite-gate`,
`merge` and `release` (redesign, issue 4); an unknown one is a refusal.

Operations (each prints one JSON object on stdout):
  sync   bring `<remote>/<base>` into the local base: the worktree must have the base checked out, be clean
         (untracked files are fine) and have no merge in progress; then `git fetch <remote>` and `git merge
         --no-edit <remote>/<base>`, a fast-forward when possible. A conflict is aborted at once, the worktree is
         checked clean again at the commit it stood on, and the conflicting files are reported for the session to
         ask the user. It never pushes, never touches another branch, never uses --force, reset or rebase.
  bundle write one Git bundle of the local base and of every local branch under the work prefixes into the folder
         that `homolog.backupDir` in the config names. The prefixes are `--prefix` alone when given; otherwise the
         `branchPrefix` of the config and every `branch_prefix` of the valid `.frontlights/authorization*.json`
         records under `--records` (default the root; a record without the key counts as the legacy prefix of
         `_cli.branch_prefix`), and none (only the base) without either (issue 44); `prefixes` and `prefixSource`
         (`argument`, `config`, `authorization`, `legacy` or null) say which, and `skipped` counts the
         records left out. `backup_dir` validates the key, and `inspect` reuses it. Without the key it says there
         is no folder and writes nothing. The folder must exist and must not sit behind a junction, symbolic link
         or other reparse point (a OneDrive cloud placeholder is storage, not redirection, and is allowed); it is
         never created. The file is
         `<root folder>-<YYYYmmdd>-<HHMMSS>.bundle` in local time, `-2`, `-3`... when the name is taken: nothing
         is ever overwritten or deleted. `git bundle verify` must accept the file before it is reported.
  release-plan  what the release would carry: the issues whose branch (the `worktrees` entries without `slice` of
         every `.frontlights/authorization*.json` under `--records`, default the root) is in the local base and
         not yet in `<remote>/<base>`, how many commits the local base is ahead of and behind the remote one, and
         the name of the release branch, `<prefix>release-<YYYY-MM-DD>` (`--prefix` alone when given; otherwise the
         `branchPrefix` of the config; otherwise the `branch_prefix` of the record with the newest `issued_at`, a
         record without a valid instant ranking last; null without any, issue 44; `prefix` and `prefixSource`
         (`argument`, `config`, `authorization` or `legacy`) say which; the date in America/Sao_Paulo, the
         machine's local date when that zone is unavailable), `-2`, `-3`... past a local branch, or a
         remote-tracking branch of `--remote`, that already has the name (GitHub deletes the head branch of a merged
         pull request and accepts its name again once `git fetch --prune` drops the ref).
         `ready` is true (exit 0) when the local
         base is ahead, not behind, and at least one issue is in
         the release; otherwise exit 2 says what is missing (behind: sync first; nothing ahead; commits ahead with
         no issue branch mapped). `fullSuite` is information only (the whole suite is not a requirement of the
         release; the only gate of stage 6 is the watched run): it judges `.frontlights/release/suite.json` at the
         tip of the local base the way `suite-gate --release` does, `current`, `missing`, `stale`, `red`, or
         `elsewhere` when the main worktree is not on that tip, with `recordPath`, `recordedHead` and what changed,
         and never changes `ready` or the exit code. Work without an issue (an entry with a `direct` slug instead of `issue`) goes
         the same way, in `directs` and `releaseDirect`, and makes the release ready too. `closes` (issue 63) lists
         the top-level issues of `release` the pull request closes with `Closes #n`: open, every box of the acceptance
         criteria ticked, no open sub-issue, no open leftover outside the criteria; each issue of `release` in
         `issues` takes `state`, `level`, `parent`, `criteria`, `openChildren`, `pendingOutside` and `closing` (true
         or the reason), read from GitHub (read only, through closeout's reader) with the `repository` of `--config`
         (default `<root>/.frontlights/config.json`). Without a read, or with a base that is not the default branch
         (GitHub closes by keyword only on a merge into it), `closes` is empty and `closesReason` says why
         (`nothing_to_release`, `no_config`, `no_repository`, `github_unavailable`, `base_not_default`), with
         `closesMessage`; it never changes `ready` or the exit code. It only reads Git, the records and GitHub:
         it never fetches, never creates the branch and never pushes. Without `<remote>/<base>` it refuses (exit 1) and asks for `homolog sync` first.
  merge  the issue into the local base in one command (references/development.md, "Into the local main"; only the
         coordinating session runs it): refuses (exit 1) a main worktree off the base, dirty or mid-merge, a slice of
         the charter that is not an ancestor of the branch of the issue, an open box of the criteria (GitHub, read
         only, or the local record), and a box without a screen without its walkthrough in format; runs
         `browser-gate` on the worktree of the issue (not green: exit 2 with the `question` and `options`); cuts
         `<prefix>issue-<n>-integra` from the branch of the issue (its own charter entry, local, never pushed) and
         merges the branch of the issue and the local base into it (a conflict stays there for the session: exit 2
         with `files`); writes the operation to `.frontlights/issues/<n>/merge-local-main-<YYYYmmdd-HHMMSS>.json`,
         runs `authorize`, `git merge --no-ff` of the integration branch into the local base (a conflict is
         aborted), `bundle` and the `update-check` of the skill, all kept in that record. `--free-test-fix` skips the
         gate only with the result.json answered and a previous merge record with `scope_check: pass`, and records
         `browser_gate: answered` with `evidence: "teste livre"`; `--dry-run` checks and lists the steps, writing
         nothing. Never pushes, never --force, reset or rebase.
  release  the release by command, `release plan|body-check|go|status|landed`: `plan` is release-plan, exit 1 with
         `watched_run_missing` when an issue of `closes` has no merge record with the watched run green; `body-check
         --body <file>` checks the body against templates/pr.md (its sections in order, no marker left, no absolute
         path) and its `Closes #n` lines against `closes` (one per issue, before `## Resumo`, no other closing word);
         `go --body <file>` prints the argv of `git push <remote> <base>:refs/heads/<release>` and of `gh pr create`
         (the session runs them; `--legacy-branch` only with `--answer Sim`: a local branch and `push -u`), keeps
         `.frontlights/release/pending.json`, and `go --record --pr <n>` turns it into `release/current.json`;
         `status` reads the PR through closeout's `merge-status` (`reviewDecision`, `mergeStateStatus`, `mergeable`,
         merged): `blocked` never offers the merge, `ready` (and every watched run recorded) carries the question
         "Mesclar a PR #<n> em <base>?" with the argv of `gh pr ready` and `gh pr merge --merge`; `--since <state>`
         exits 0 only when the state changed (4 otherwise) and `--quiet` prints one line then, nothing before: the
         until-loop of the monitor wakes the session once. `landed`, once merged: `git pull --ff-only` (not a
         fast-forward: exit 2, stop and ask, never reset), `git fetch --prune`, the `cleanup plan` of the issues of
         the release, its `commands` and the `closeout verify` left to run; `current.json` is kept as
         `current-<stamp>.json` and `landed-<stamp>.json`. It never pushes, never creates nor merges a pull request.
  suite  run the suite `homolog.suites.<mode>` of the config declares (`--mode impact|full`; each `{"argv": [...],
         "timeoutSeconds": N}`, the shape and the refusals of `checks.regression`) in `--root`, without a shell, the
         whole process tree killed at the timeout; `{base}` in the argv becomes `--base` (default main), and
         `{report}` (only in `homolog.suites.impact.argv`, only as one whole argument, at most once; refused anywhere
         else) the absolute path of a fresh `.frontlights/issues/<n>/suite-report-<YYYYmmdd-HHMMSS>.json`: after the
         run the record takes `report` (the path) and, from a valid report (an object with `ran` and `complete`,
         lists of ids; any other key, like the usual ones of the `--report` of `tests/suite.py`, ignored), `ran`
         and `complete`; a missing, too large or invalid one is a warning in `warnings`, the exit code as is.
         `{covered}` (only in `homolog.suites.full.argv`, with the same rules; refused in impact and in `--argv`)
         becomes the absolute path of a fresh `suite-covered-<YYYYmmdd-HHMMSS>.json` in the record folder,
         `{"complete": [ids]}`: with `--release`, the union of `complete` of the impact records of the issues of the
         release (the `release` of `release-plan`), each read from `.frontlights/issues/<n>/suite.json` in the
         worktree its authorization entry names, that ran green on a clean tree whose commit tree is the tip's, the
         bytes on disk not compared (the checks of the adoption after its first), with no tracked file hidden from
         `git status` (skip-worktree, assume-unchanged) in that worktree; a record that does not count adds nothing and its
         reason is kept. Outside the release the list is empty. The record takes `covered` {complete, from [{issue,
         path, head, tree}], refused [{issue, path, reason}], file}, and `warnings` when the list of the issues of
         the release cannot be had (no `<remote>/<base>`, or no authorization record names one of them), so the
         record says why nothing was skipped; without the marker, nothing of this. With
         `--mode full`, `--argv '<json list>'` runs once the argv the user accepted instead of the config (`source:
         argument`; `config` otherwise); `--argv` with impact is a refusal. `--timeout-seconds N` (a positive
         integer, with or without `--argv`) is the timeout of this run in place of the config's; without either,
         full gets 3600 s and impact the default of `checks`. The masked output goes to
         `.frontlights/issues/<n>/suite-<mode>-<YYYYmmdd-HHMMSS>.log` and the record to `.frontlights/issues/<n>/
         suite.json`: mode, source, base, argv, head and evidence (`frontlights.py evidence`, taken before the run,
         `.frontlights/` left out), exitCode, timedOut, seconds, output, concurrent (`--concurrent`: the watched
         run was in progress), startedAt and finishedAt in America/Sao_Paulo. `state` green exits 0; red (failed,
         timed out or not started) exits 1; a mode without a suite is `unconfigured` (exit 2) and nothing runs.
         `--release` (in place of `--issue`) is the whole suite of the release: only `--mode full`, only in a
         worktree with the local base checked out at its tip (HEAD is `refs/heads/<base>`), and only on a clean
         tree (no change outside `.frontlights/` left uncommitted, tracked, staged or not, or untracked; the
         refusal names the files), each refused (exit 1) otherwise, nothing run and no record written; the record
         and the log go to `.frontlights/release/`, and the record also to
         `release/suite-<full head sha>.json`, the copy of that tip that a run at another tip never overwrites.
         `--release --mode full --from <record>` runs nothing: it adopts a whole-suite record of the same commit tree
         (an issue's `suite.json` or another release's `release/suite-<sha>.json`) that ran green, without timeout, on
         a clean tree: it answers `state: "adopted"` and writes both release records with `adoptedFrom` (the origin path, its
         head and tree). It refuses (exit 1, nothing written) an impact, red or timed-out record, one with a diff or a
         file outside the commit, an unknown head or another tree (bytes on disk are not compared), one outside a Git
         worktree or whose worktree has a tracked file hidden from `git status` (skip-worktree, assume-unchanged), a place that
         is not the clean tip of the local base, and `--from` with `--argv` or `--timeout-seconds`.
  suite-gate  compare suite.json with the tip now, the way `review-gate` does: `current` (same evidence, the
         suite exited 0; with `--require full` only a full record), `stale` (`changed` names the fields that
         differ, `files_changed` the files), `red` (the tip of the record, the suite failed), `missing` (no record
         while the config declares a suite, or an impact record under `--require full`) and `unconfigured` (no
         record and no `homolog.suites`). A record is judged even without suites in the config. Exit 0 only for
         current, 2 otherwise. `--release` judges `.frontlights/release/suite.json` as `--require full`, refused
         (exit 1) off the tip of the local `--base` (default main); `release-plan` shares the judgment.
         A release record with `covered` (a run with `{covered}`) is the whole suite of its tip like any other; both
         judges of the release, and `release-plan`, pass `covered` on and say how many modules it skipped.
         `--release --head <full sha>` judges the copy of that tip instead, wherever the main worktree stands:
         `current` (a full run of that head exited 0), `red` (it failed) or `missing` (no copy, or a copy whose
         evidence shows changes not committed: a diff other than the empty one, or a file the commit lacks, so it
         does not stand for the commit); `--head` without
         `--release`, or not a full sha, is refused (exit 1).

Exit codes: 0 done; 1 refused or failed (bad usage, a precondition not met, Git failing); 2 a question for the
session (a conflict on sync; a release that is not ready). A refusal is JSON,
never a traceback.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zoneinfo
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _cli  # noqa: E402  (defaults of --root, --config and --issue, the parser and UTF-8)

GIT_TIMEOUT = 45
FETCH_TIMEOUT = 120
BUNDLE_TIMEOUT = 300
STDERR_LIMIT = 200       # characters of Git's own text repeated in a message
RECORD_LIMIT = 200       # authorization records release-plan and bundle read
RECORD_BYTES = 2 * 1024 * 1024                  # the largest record it reads
RELEASE_ZONE = 'America/Sao_Paulo'              # the date in the name of the release branch
HOMOLOG_KEYS = ('backupDir', 'suites')          # the keys of the `homolog` block of the config
SUITE_MODES = ('impact', 'full')                # the suites `homolog.suites` may declare
SUITE_KEYS = ('argv', 'timeoutSeconds')         # the keys of each suite, the shape of `checks.regression`
BASE_TOKEN = '{base}'                           # replaced in a suite argv by the base the run compares with
REPORT_TOKEN = '{report}'                       # impact only, a whole argument: the path of the report of the run
COVERED_TOKEN = '{covered}'                     # full only, a whole argument: the path of what is already covered
MARKERS = {REPORT_TOKEN: 'impact', COVERED_TOKEN: 'full'}   # each marker and the only suite whose argv takes it
FULL_SUITE_TIMEOUT = 3600                       # the whole suite without a configured timeout (impact: checks')
EMPTY_DIFF = hashlib.sha256(b'').hexdigest()    # `diff_sha256` of the evidence of a tree with no tracked change
CONTROL = re.compile(r'[\x00-\x1f\x7f]')
REPARSE_POINT = 0x400                           # FILE_ATTRIBUTE_REPARSE_POINT
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]*')   # a plain branch or remote name
OID = re.compile(r'[0-9a-f]{40,64}')
DIRECT = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')   # the slug of work without an issue (frontlights.DIRECT_RULE)


class Refusal(Exception):
    """A deliberate refusal: the message is safe to show the user."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


# ---------------------------------------------------------------- git

def git(root, *args, timeout=GIT_TIMEOUT):
    """(exit code, stdout, stderr) of a Git command run in `root` without a shell and without prompts."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    try:
        done = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, stdin=subprocess.DEVNULL, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        raise Refusal(f'o git não respondeu a `git {args[0]}` (ausente, ou além do prazo de {timeout} s)')
    return done.returncode, done.stdout, done.stderr


def trimmed(text):
    """Git's own text as one line of at most STDERR_LIMIT characters."""
    return ' '.join(text.split())[:STDERR_LIMIT] or 'sem detalhe'


def worktree(root):
    """Refuses when `root` is not inside a Git worktree."""
    code, _, _ = git(root, 'rev-parse', '--show-toplevel')
    require(code == 0, f'{root} não é uma worktree Git')


def is_plain(value):
    """The NAME rule as a predicate: a plain branch or remote name, without `..` and not ending in `.lock`."""
    return isinstance(value, str) and bool(NAME.fullmatch(value)) and '..' not in value and not value.endswith('.lock')


def plain_name(value, what):
    require(is_plain(value or ''),
            f'{what} precisa ser um nome simples, como {"main" if what.startswith("a branch") else "origin"}')
    return value


def rev(root, ref):
    """The commit `ref` names, or None."""
    code, out, _ = git(root, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
    tip = out.strip()
    return tip if code == 0 and OID.fullmatch(tip) else None


def tree_of(root, commit):
    """The tree of the commit `commit` names, or None when the repository does not know that commit."""
    code, out, _ = git(root, 'rev-parse', '--verify', '--quiet', f'{commit}^{{commit}}^{{tree}}')
    tree = out.strip()
    return tree if code == 0 and OID.fullmatch(tree) else None


def status_lines(root):
    """Tracked files with changes (staged or not); untracked files are not counted."""
    code, out, _ = git(root, 'status', '--porcelain', '--untracked-files=no')
    require(code == 0, 'o git não leu o estado da worktree')
    return [line for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------- sync

def check_sync_preconditions(root, base):
    code, out, _ = git(root, 'symbolic-ref', '--short', '--quiet', 'HEAD')
    head = out.strip() if code == 0 else None
    require(head == base, f'a worktree está em `{head or "HEAD solta"}`, não em `{base}`; a sync só roda na {base} local')
    dirty = status_lines(root)
    require(not dirty, f'a worktree tem {len(dirty)} arquivo(s) com alterações não commitadas; a sync precisa de uma '
                       'worktree limpa')
    require(rev(root, 'MERGE_HEAD') is None,
            'há um merge em andamento na worktree (MERGE_HEAD); conclua-o ou aborte-o antes da sync')


def fetch(root, remote):
    code, _, err = git(root, 'fetch', '--quiet', remote, timeout=FETCH_TIMEOUT)
    require(code == 0, f'`git fetch {remote}` falhou: {trimmed(err)}')


def abort_merge(root, before):
    """Undo a conflicted merge; True when the worktree is clean again at `before`."""
    code, _, _ = git(root, 'merge', '--abort')
    return code == 0 and not status_lines(root) and rev(root, 'HEAD') == before and rev(root, 'MERGE_HEAD') is None


def merged_message(base, remote, before, after, tip):
    if after == before:
        return f'A {base} local já está em dia com {remote}/{base} ({tip[:7]}).'
    how = f'(fast-forward até {remote}/{base})' if after == tip else f'por um commit de merge com {remote}/{base}'
    return f'A {base} local avançou de {before[:7]} para {after[:7]} {how}.'


def op_sync(root, base, remote):
    worktree(root)
    base = plain_name(base, 'a branch base')
    remote = plain_name(remote, 'o remoto')
    check_sync_preconditions(root, base)
    fetch(root, remote)
    tip = rev(root, f'refs/remotes/{remote}/{base}')
    require(tip, f'`{remote}/{base}` não existe depois do fetch; confira o remoto e a branch base')
    before = rev(root, 'HEAD')
    result = {'before': before, 'remoteTip': tip, 'base': base, 'remote': remote}
    code, _, err = git(root, 'merge', '--no-edit', f'{remote}/{base}')
    if code == 0:
        after = rev(root, 'HEAD')
        result.update(after=after, advanced=after != before, fastForward=after == tip, exitCode=0,
                      message=merged_message(base, remote, before, after, tip))
        return result
    _, unmerged, _ = git(root, 'diff', '--name-only', '--diff-filter=U')
    files = sorted(line.strip() for line in unmerged.splitlines() if line.strip())
    if not files and rev(root, 'MERGE_HEAD') is None:
        raise Refusal(f'`git merge {remote}/{base}` falhou: {trimmed(err)}')
    require(abort_merge(root, before), f'o merge de {remote}/{base} teve conflito e o abort não deixou a worktree '
                                       f'limpa em {before[:7]}; confira-a à mão')
    result.update(conflict=True, files=files, exitCode=2,
                  message=f'O merge de {remote}/{base} na {base} local tem conflito em: {", ".join(files)}. '
                          f'O merge foi abortado e a worktree voltou a {before[:7]}, limpa.')
    return result


# ---------------------------------------------------------------- bundle

def backup_dir(config):
    """The folder `homolog.backupDir` names, as a Path, or None when no backup is configured.

    `homolog` absent or null is None; otherwise it must be an object whose keys are `backupDir` and `suites` (see
    `suite_settings`), so a typo never passes in silence. `backupDir` absent or null is None; otherwise a non-empty string with an absolute path (a
    drive or UNC root on Windows), without `..` segments, not starting with `~`, without `{placeholder}` braces,
    NUL or control characters. The folder need not exist: `inspect` is read-only and the folder may be a synced
    cloud folder; `bundle` checks it at run time. A refusal never repeats the value.
    """
    block = config.get('homolog')
    if block is None:
        return None
    require(isinstance(block, dict), 'homolog precisa ser um objeto com as chaves backupDir e suites')
    unknown = [str(key)[:40] for key in block if key not in HOMOLOG_KEYS]
    if unknown:
        raise Refusal(f'homolog tem a chave desconhecida `{unknown[0]}`; as chaves aceitas são backupDir e suites')
    value = block.get('backupDir')
    if value is None:
        return None
    require(isinstance(value, str) and value.strip(),
            'homolog.backupDir precisa ser um texto não vazio com o caminho absoluto da pasta de backup')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts and not value.startswith('~')
            and not CONTROL.search(value) and '{' not in value and '}' not in value,
            'homolog.backupDir precisa ser um caminho absoluto (com unidade ou raiz UNC no Windows), sem `..` nem `~`, '
            'sem chaves `{}` nem caracteres de controle')
    return path


def load_config(path):
    """The config object at `path`; a Refusal when unreadable or not a JSON object."""
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise Refusal(f'não foi possível ler o config em {path}: confira o caminho e o JSON')
    require(isinstance(config, dict), f'o config em {path} precisa ser um objeto JSON')
    return config


def reparse_tag(path):
    """0 for an ordinary entry, the reparse tag otherwise; -1 when unreadable (as roads.py does for scrumRoot)."""
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


def check_backup_folder(folder):
    """The folder must exist as a directory, with no junction, symbolic link or non-cloud reparse point from the
    folder up to the root of its drive or share. It is never created."""
    require(folder.is_dir(), f'a pasta de backup homolog.backupDir não existe ou não é uma pasta: {folder}')
    cursor = os.path.abspath(str(folder))
    while True:
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        tag = reparse_tag(cursor)
        require(tag == 0 or cloud_tag(tag), f'a pasta de backup homolog.backupDir passa por uma junção, link simbólico '
                                             f'ou outro reparse point em {cursor}; use uma pasta comum')
        cursor = parent


def is_prefix(value):
    """A branch prefix: a plain name that ends in `/`."""
    return isinstance(value, str) and bool(NAME.fullmatch(value)) and '..' not in value and value.endswith('/')


def branch_prefix(value):
    require(is_prefix(value or ''), 'o prefixo das branches precisa ser um nome simples terminado em `/`, como dev/')
    return value


def bundle_refs(root, base, prefixes):
    """`refs/heads/<base>` and every local branch under one of `prefixes`, as full ref names (never ambiguous with a
    tag), each once."""
    require(rev(root, f'refs/heads/{base}'), f'a branch base `{base}` não existe neste repositório')
    if not prefixes:   # no prefix: the base alone (for-each-ref without a pattern would list every branch)
        return [f'refs/heads/{base}']
    code, out, err = git(root, 'for-each-ref', '--format=%(refname)', *(f'refs/heads/{prefix}' for prefix in prefixes))
    require(code == 0, f'`git for-each-ref` falhou: {trimmed(err)}')
    branches = sorted({line.strip() for line in out.splitlines() if line.strip()})
    return [f'refs/heads/{base}'] + [ref for ref in branches if ref != f'refs/heads/{base}']


def short(ref):
    return ref[len('refs/heads/'):] if ref.startswith('refs/heads/') else ref


def fresh_file(folder, stem, suffix='.bundle'):
    """A path in `folder` that does not exist yet: `<stem>.bundle`, then `<stem>-2.bundle`, `<stem>-3.bundle`..."""
    candidate = folder / f'{stem}{suffix}'
    counter = 2
    while candidate.exists():
        candidate = folder / f'{stem}-{counter}{suffix}'
        counter += 1
    return candidate


def bundle_name(root):
    """`<root folder>-<YYYYmmdd>-<HHMMSS>` in the machine's local time."""
    stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    return f'{Path(os.path.abspath(root)).name or "repo"}-{stamp}'


def write_bundle(root, folder, refs):
    """Creates the bundle, has Git verify it and returns (path, refs it carries as short names)."""
    path = fresh_file(folder, bundle_name(root))
    code, _, err = git(root, 'bundle', 'create', str(path), *refs, timeout=BUNDLE_TIMEOUT)
    require(code == 0, f'`git bundle create` falhou: {trimmed(err)}')
    code, _, err = git(root, 'bundle', 'verify', str(path), timeout=BUNDLE_TIMEOUT)
    require(code == 0, f'`git bundle verify` recusou o arquivo gravado: {trimmed(err)}')
    code, out, err = git(root, 'bundle', 'list-heads', str(path))
    require(code == 0, f'`git bundle list-heads` falhou: {trimmed(err)}')
    heads = [short(line.split()[-1]) for line in out.splitlines() if line.strip()]
    return path, heads


def bundle_prefixes(prefix, records, config=None):
    """(prefixes, source, skipped): `[prefix]` and `argument` when one is given; otherwise the sorted union of the
    `branchPrefix` of the config and the `branch_prefix` of the valid records (`legacy` for a record without the key)
    under `records`, with the source of the chain of `_cli.branch_prefix` (`config`, `authorization` or `legacy`);
    `[]` and None without any, and then only the base goes into the bundle; `skipped` counts the records left out
    (issue 44)."""
    if prefix is not None:
        return [branch_prefix(prefix)], 'argument', 0
    found, skipped = record_prefixes(records)
    named = _cli.config_prefix(config)
    prefixes = sorted({entry['prefix'] for entry in found} | ({branch_prefix(named)} if named else set()))
    if named:
        return prefixes, 'config', skipped
    if found:
        legacy = all(entry['source'] == 'legacy' for entry in found)
        return prefixes, 'legacy' if legacy else 'authorization', skipped
    return [], None, skipped


def op_bundle(root, config_path, base, prefix, records=None):
    worktree(root)
    base = plain_name(base, 'a branch base')
    config = load_config(config_path)
    prefixes, source, skipped = bundle_prefixes(prefix, root if records is None else records, config)
    folder = backup_dir(config)
    if folder is None:
        return {'configured': False, 'written': False, 'prefixes': prefixes, 'prefixSource': source,
                'skipped': skipped, 'exitCode': 1,
                'message': 'não há pasta de backup configurada (homolog.backupDir); nada foi gravado'}
    result = {'configured': True, 'written': False, 'prefixes': prefixes, 'prefixSource': source, 'skipped': skipped}
    try:
        check_backup_folder(folder)
        path, heads = write_bundle(root, folder, bundle_refs(root, base, prefixes))
    except Refusal as error:
        result.update(exitCode=1, message=str(error))
        return result
    result.update(written=True, verified=True, path=str(path), refs=heads, bytes=path.stat().st_size, exitCode=0,
                  message=f'Bundle {path.name} gravado em {folder} com {len(heads)} ref(s): {", ".join(heads)}.')
    return result


# ---------------------------------------------------------------- release-plan

def read_record(path):
    """The JSON object a record holds, or None when the file is too large, unreadable or not an object."""
    try:
        if path.stat().st_size > RECORD_BYTES:
            return None
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def record_files(folder):
    """The `.frontlights/authorization*.json` files under `folder`, sorted by name; [] when the folder is unreadable."""
    try:
        return sorted(Path(folder, '.frontlights').glob('authorization*.json'))
    except OSError:
        return []


def record_prefixes(folder):
    """([{'file', 'prefix', 'source', 'issuedAt'}], skipped) for every record under `folder` whose `branch_prefix`
    (absent: the legacy prefix of `_cli.branch_prefix`, source `legacy`) is a valid prefix and whose `worktrees` (absent: none) is a list, the same validity as
    `issue_branches`; an unreadable record, a bad prefix or `worktrees`, and every record past RECORD_LIMIT, is
    skipped and counted (issue 44)."""
    files = record_files(folder)
    skipped = max(0, len(files) - RECORD_LIMIT)
    found = []
    for file in files[:RECORD_LIMIT]:
        data = read_record(file)
        prefix, source = _cli.branch_prefix(record=data) if data is not None else (None, None)
        entries = data.get('worktrees', []) if data is not None else None
        if data is None or not is_prefix(prefix) or not isinstance(entries, list):
            skipped += 1
            continue
        found.append({'file': file.name, 'prefix': prefix, 'source': source, 'issuedAt': data.get('issued_at')})
    return found, skipped


def issue_branches(folder):
    """({issue number: branch}, skipped): the issue side of `work_branches`, for the readers that only follow
    issues (closeout)."""
    issues, _, skipped = work_branches(folder)
    return issues, skipped


def work_branches(folder):
    """({issue number: branch}, {direct slug: branch}, skipped) from the `worktrees` entries without `slice` of every
    `.frontlights/authorization*.json` under `folder`. An entry counts when it names either a positive integer
    `issue` or a `direct` slug (work without an issue: lower-case letters, digits and hyphens, up to 64 characters),
    never both, and its `branch` is a plain name under the record's `branch_prefix` (the legacy prefix without it); a later
    record wins for the same issue or slug, except that the entry of the branch of the issue (`<prefix>issue-<n>`)
    wins over a later one of the same issue (`issue_entries`). A slice entry is ignored in silence; a malformed
    entry, record or prefix, and every record past RECORD_LIMIT, is skipped and counted."""
    entries, skipped = work_entries(folder)
    issues = {number: entry['branch'] for number, entry in issue_entries(entries).items()}
    directs = {entry['direct']: entry['branch'] for entry in entries if 'direct' in entry}
    return issues, directs, skipped


def issue_entries(entries):
    """{issue number: its entry} from `work_entries`: a later entry wins, but the entry of the branch of the issue
    (`<prefix>issue-<n>`) wins over a later one of the same issue (a review fix's own branch and worktree, issue 57),
    because the issue is delivered by its own branch and its impact record is written in that branch's worktree."""
    chosen = {}
    for entry in entries:
        if 'issue' not in entry:
            continue
        own = entry['branch'].rsplit('/', 1)[-1] == f'issue-{entry["issue"]}'
        if own or not chosen.get(entry['issue'], (None, False))[1]:
            chosen[entry['issue']] = (entry, own)
    return {number: entry for number, (entry, _) in chosen.items()}


def issue_worktrees(folder):
    """{issue number: the `path` of its worktree} from the entry `issue_entries` chooses for each issue (issue 57,
    S4); an entry without a non-empty `path` names no worktree."""
    entries, _ = work_entries(folder)
    return {number: entry['path'] for number, entry in issue_entries(entries).items() if entry['path']}


def work_entries(folder):
    """([{'issue' or 'direct', 'branch', 'path'}], skipped) in record order: the valid entries `work_branches`
    describes, with the `path` of the worktree (None when it is not a non-empty text)."""
    files = record_files(folder)
    skipped = max(0, len(files) - RECORD_LIMIT)
    found = []
    for file in files[:RECORD_LIMIT]:
        data = read_record(file)
        prefix = _cli.branch_prefix(record=data)[0] if data is not None else None
        entries = data.get('worktrees', []) if data is not None else None
        if data is None or not is_prefix(prefix) or not isinstance(entries, list):
            skipped += 1
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get('slice'), str) and entry['slice'].strip():
                continue   # a slice is delivered to the branch of its issue, never to the base by itself
            number = entry.get('issue') if isinstance(entry, dict) else None
            direct = entry.get('direct') if isinstance(entry, dict) else None
            branch = entry.get('branch') if isinstance(entry, dict) else None
            path = entry.get('path') if isinstance(entry, dict) else None
            path = path if isinstance(path, str) and path.strip() else None
            if not is_plain(branch) or not branch.startswith(prefix):
                skipped += 1
            elif direct is None and type(number) is int and number > 0:
                found.append({'issue': number, 'branch': branch, 'path': path})
            elif number is None and isinstance(direct, str) and DIRECT.fullmatch(direct):
                found.append({'direct': direct, 'branch': branch, 'path': path})
            else:
                skipped += 1
    return found, skipped


def ancestry(root, commit, ref):
    """True or False when Git can tell whether `commit` is in `ref`, None when it cannot or either is missing."""
    if commit is None or ref is None:
        return None
    code, _, _ = git(root, 'merge-base', '--is-ancestor', commit, ref)
    return True if code == 0 else False if code == 1 else None


def counts(root, local_ref, remote_ref):
    """(ahead, behind): commits only in the local base, commits only in the remote one; (None, None) when Git fails."""
    code, out, _ = git(root, 'rev-list', '--left-right', '--count', f'{local_ref}...{remote_ref}')
    parts = out.split()
    if code != 0 or len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None, None
    return int(parts[0]), int(parts[1])


def release_date():
    """Today in RELEASE_ZONE as YYYY-MM-DD; the machine's local date when the zone is unavailable (no tzdata)."""
    try:
        now = datetime.now(zoneinfo.ZoneInfo(RELEASE_ZONE))
    except (KeyError, OSError, ValueError):   # ZoneInfoNotFoundError is a KeyError
        now = datetime.now().astimezone()
    return now.strftime('%Y-%m-%d')


def release_name(root, prefix, remote):
    """`<prefix>release-<date>`, then `-2`, `-3`... past every local branch and every remote-tracking branch of
    `remote` that already carries the name."""
    stem = f'{prefix}release-{release_date()}'
    name, counter = stem, 2
    while rev(root, f'refs/heads/{name}') is not None or rev(root, f'refs/remotes/{remote}/{name}') is not None:
        name = f'{stem}-{counter}'
        counter += 1
    return name


def instant(value):
    """The POSIX time of an ISO-8601 `issued_at` (UTC when it carries no offset), or None when it is not one."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def release_prefix(prefix, records, config=None):
    """(prefix, source) by the chain of `_cli.branch_prefix`: `prefix` and `argument` when one is given; else the
    `branchPrefix` of the config and `config`; else the `branch_prefix` of the record with the newest `issued_at`
    (records without a valid instant rank last, then by file name) and `authorization` (`legacy` for a record
    without the key); (None, None) without any: the plan is still read, with no release branch name (issue 44)."""
    if prefix is not None:
        return branch_prefix(prefix), 'argument'
    named = _cli.config_prefix(config)
    if named:
        return branch_prefix(named), 'config'
    found, _ = record_prefixes(records)
    if not found:
        return None, None

    def rank(entry):
        moment = instant(entry['issuedAt'])
        return (moment is not None, moment if moment is not None else 0.0, entry['file'])

    newest = max(found, key=rank)
    return newest['prefix'], newest['source']


def release_work(root, base, remote, records):
    """(issues, directs, skipped): every issue and every work without an issue of the authorization records under
    `records` (`work_branches`), each with its branch, its tip and whether that tip is in the local `base` and in
    `<remote>/<base>`; `pending` says which of them the release carries."""
    local_ref, remote_ref = f'refs/heads/{base}', f'refs/remotes/{remote}/{base}'
    remote_tip = rev(root, remote_ref)
    mapping, direct_mapping, skipped = work_branches(records)

    def located(key, value, branch):
        tip = rev(root, f'refs/heads/{branch}')
        return {key: value, 'branch': branch, 'tip': tip, 'present': tip is not None,
                'inLocalMain': ancestry(root, tip, local_ref),
                'inRemoteMain': ancestry(root, tip, remote_ref if remote_tip else None)}

    issues = [located('issue', number, mapping[number]) for number in sorted(mapping)]
    directs = [located('direct', slug, direct_mapping[slug]) for slug in sorted(direct_mapping)]
    return issues, directs, skipped


def pending(item):
    """True when the release carries this item of `release_work`: its branch is in the local base, not in the remote."""
    return item['present'] and item['inLocalMain'] is True and item['inRemoteMain'] is False


CLOSES_NONE = ('a PR da release vai sem `Closes #n`, e as issues dela seguem a pergunta de fechamento da etapa 7')


def release_closes(root, config_path, base, release, issues, gh=None):
    """(closes, reason, message): the top-level issues of `release` whose pull request line is `Closes #n`, read from
    GitHub (read only, through closeout) with the repository of the config (`config_path`, default
    `<root>/.frontlights/config.json`). Each issue of the release in `issues` takes what was read of it (`state`,
    `level`, `parent`, `criteria`, `openChildren`, `pendingOutside`) and `closing`, True or the reason. Without a read
    (nothing to release, no config, no repository, GitHub unavailable, a base that is not the default branch)
    `closes` is empty with the reason: when in doubt, no keyword. Never a refusal: the plan answers as it would."""
    if not release:
        return [], 'nothing_to_release', 'Nada a liberar, nada a fechar: `closes` vazio.'
    import closeout   # noqa: PLC0415  (lazy: only the closing keyword of the release reads GitHub)
    path = Path(config_path) if config_path else Path(root, '.frontlights', 'config.json')
    try:
        config = load_config(path)
    except Refusal:
        return [], 'no_config', f'Sem config legível (`--config`, padrão `.frontlights/config.json` da raiz), o ' \
                                f'release-plan não leu o GitHub: {CLOSES_NONE}; sem `Closes #n`.'
    repository = config.get('repository')
    if not closeout.frontlights.repository(repository):
        return [], 'no_repository', f'O config não nomeia um repositório `owner/name` do GitHub: {CLOSES_NONE}; ' \
                                    'sem `Closes #n`.'
    try:
        default, found = closeout.release_keywords(gh or closeout.rs.gh_default, repository, release, base)
    except Exception:   # noqa: BLE001  (a failed read only empties the list: when in doubt, no keyword)
        default, found = None, None
    if default is None:
        return [], 'github_unavailable', f'O GitHub não respondeu à leitura (gh, conta ou acesso): {CLOSES_NONE}; ' \
                                         'sem `Closes #n`.'
    if default != base:
        return [], 'base_not_default', (f'A base `{base}` não é a branch padrão do repositório (`{default}`), e o '
                                        f'GitHub só fecha por palavra num merge na padrão: {CLOSES_NONE}; sem '
                                        '`Closes #n`.')
    for item in issues:
        if item['issue'] in found:
            item.update(found[item['issue']])
    closes = [number for number in release if found.get(number, {}).get('closing') is True]
    if not closes:
        return [], None, f'Nenhuma issue da release está pronta para `Closes #n` (veja `closing` de cada uma): ' \
                         f'{CLOSES_NONE}.'
    lines = ', '.join(f'`Closes #{number}`' for number in closes)
    return closes, None, (f'A PR da release leva uma linha por issue de `closes`: {lines}; o merge aprovado as fecha. '
                          'As outras seguem a pergunta de fechamento da etapa 7.')


def suite_sentence(suite):
    """What the release message says of the whole suite: information only, never a requirement of the release."""
    if suite.get('status') == 'current':
        return skipped_sentence(suite.get('covered'))
    return f' Suíte inteira (opcional, não exigida pela release): {suite.get("status")}.'


def op_release_plan(root, base, remote, prefix, records, config_path=None, gh=None):
    """What the release would carry. `ready` and the exit code depend only on the local base being ahead, not
    behind, with an issue or a direct work in it; `fullSuite` is reported as information and never blocks."""
    worktree(root)
    base = plain_name(base, 'a branch base')
    remote = plain_name(remote, 'o remoto')
    prefix, source = release_prefix(prefix, root if records is None else records,
                                    config_path if config_path and Path(config_path).is_file() else None)
    local_ref, remote_ref = f'refs/heads/{base}', f'refs/remotes/{remote}/{base}'
    local = rev(root, local_ref)
    require(local, f'a branch base `{base}` não existe neste repositório')
    remote_tip = rev(root, remote_ref)
    issues, directs, skipped = release_work(root, base, remote, root if records is None else records)
    release = [i['issue'] for i in issues if pending(i)]
    release_direct = [d['direct'] for d in directs if pending(d)]
    ahead, behind = counts(root, local_ref, remote_ref) if remote_tip else (None, None)
    name = release_name(root, prefix, remote) if prefix else None
    result = {'base': base, 'remote': remote, 'localMain': local, 'remoteMain': remote_tip, 'ahead': ahead,
              'behind': behind, 'issues': issues, 'release': release, 'directs': directs,
              'releaseDirect': release_direct, 'releaseBranch': name, 'prefix': prefix,
              'prefixSource': source, 'skipped': skipped, 'fullSuite': release_suite(root, base), 'ready': False}
    closes, reason, closes_message = release_closes(root, config_path, base, release, issues, gh)
    result.update(closes=closes, closesReason=reason, closesMessage=closes_message)
    if remote_tip is None:
        result.update(exitCode=1, message=f'`{remote}/{base}` não existe neste repositório; rode `homolog sync` (um fetch) '
                                          'antes do release-plan.')
    elif ahead is None:
        result.update(exitCode=1, message=f'o git não contou os commits entre a {base} local e {remote}/{base}')
    elif behind > 0:
        result.update(exitCode=2, message=f'A {base} local está {behind} commit(s) atrás de {remote}/{base}; rode '
                                          f'`homolog sync` antes da release.')
    elif ahead == 0:
        result.update(exitCode=2, message=f'A {base} local não tem commit além de {remote}/{base}: nada a liberar.')
    elif not release and not release_direct:
        result.update(exitCode=2, message=f'A {base} local tem {ahead} commit(s) além de {remote}/{base}, mas nenhuma '
                                          'branch de issue das autorizações está neles; confira os registros em '
                                          '.frontlights/ ou aponte --records para a pasta certa.')
    else:
        parts = [f'{len(release)} issue(s) ({", ".join(f"#{number}" for number in release)})'] if release else []
        if release_direct:
            parts.append(f'{len(release_direct)} trabalho(s) sem issue ({", ".join(release_direct)})')
        named = (f'a branch da release é {name}.' if name else
                 'sem prefixo das branches, a release não tem nome: passe --prefix ou declare branchPrefix no config.')
        result.update(ready=True, exitCode=0,
                      message=f'Release pronta: {" e ".join(parts)} em {ahead} commit(s) da {base} local '
                              f'ainda fora de {remote}/{base}; {named}'
                              f'{suite_sentence(result["fullSuite"])}')
    return result


# ---------------------------------------------------------------- suite and suite-gate

def suite_block(config):
    """The `homolog.suites` object, every mode in it validated, or None when it is absent or null."""
    if config.get('homolog') is None:
        return None
    backup_dir(config)   # the refusals of the block itself and of its keys
    suites = config['homolog'].get('suites')
    if suites is None:
        return None
    require(isinstance(suites, dict), 'homolog.suites precisa ser um objeto com as chaves impact e full')
    unknown = [str(key)[:40] for key in suites if key not in SUITE_MODES]
    if unknown:
        raise Refusal(f'homolog.suites tem a chave desconhecida `{unknown[0]}`; as chaves aceitas são impact e full')
    for mode in SUITE_MODES:
        suite_entry(suites.get(mode), f'homolog.suites.{mode}', mode=mode)
    return suites


def suite_argv(argv, key, mode=None):
    """The rules of `checks.<name>.argv` (checks.command_settings): a list of non-empty texts, no NUL byte, no
    embedded shell. In the suite `mode` of the config, its marker of MARKERS (REPORT_TOKEN for impact,
    COVERED_TOKEN for full) may be one whole argument, at most once; anywhere else (another suite, `--argv`) a
    marker is refused. A refusal never repeats the arguments."""
    import checks   # noqa: PLC0415  (lazy: only the suite operations need it)
    require(isinstance(argv, list), f'{key} precisa ser uma lista de argumentos, não um texto')
    require(argv and all(isinstance(argument, str) and argument for argument in argv),
            f'{key} precisa ter só textos não vazios')
    require(not any('\0' in argument for argument in argv), f'{key} não aceita byte NUL em nenhum argumento')
    for token, place in MARKERS.items():
        marked = [argument for argument in argv if token in argument]
        require(mode == place or not marked, f'{key} não aceita o marcador {token}: ele vale só em '
                                             f'homolog.suites.{place}.argv, como um argumento inteiro')
        require(all(argument == token for argument in marked),
                f'{key} aceita o marcador {token} só como um argumento inteiro, não dentro de outro argumento')
        require(len(marked) <= 1, f'{key} aceita o marcador {token} uma vez só')
    reason = checks.embedded_shell(argv)
    require(not reason, f'{key} não aceita shell embutido ({reason}; cmd, sh, bash, powershell, .bat, wrappers, &&, '
                        '|, ;, redirecionamentos, python -c); declare o executável e seus argumentos')
    return argv


def suite_entry(entry, key, default_timeout=None, mode=None):
    """{'argv', 'timeout'} of one suite, or None when it is absent or null; the shape of `checks.regression`.
    Without `timeoutSeconds`, `default_timeout` (`checks.DEFAULT_TIMEOUT` when not given); `mode`: the argv may
    carry the marker of that suite (`suite_argv`)."""
    import checks   # noqa: PLC0415
    if entry is None:
        return None
    require(isinstance(entry, dict), f'{key} precisa ser um objeto com argv e timeoutSeconds')
    unknown = [str(name)[:40] for name in entry if name not in SUITE_KEYS]
    if unknown:
        raise Refusal(f'{key} tem a chave desconhecida `{unknown[0]}`; as chaves aceitas são argv e timeoutSeconds')
    argv = suite_argv(entry.get('argv'), f'{key}.argv', mode)
    timeout = entry.get('timeoutSeconds', default_timeout or checks.DEFAULT_TIMEOUT)
    require(type(timeout) is int and timeout > 0, f'{key}.timeoutSeconds precisa ser um inteiro positivo')
    return {'argv': argv, 'timeout': timeout}


def issue_number(value):
    require(isinstance(value, str) and value.isdigit() and 0 < int(value) and len(value) <= 9,
            'a issue precisa ser um número inteiro positivo')
    return int(value)


def record_folder(root, issue=None):
    """The folder of the suite record: `.frontlights/issues/<n>/` of an issue, `.frontlights/release/` without one."""
    folder = Path(root).resolve() / '.frontlights'
    return folder / 'release' if issue is None else folder / 'issues' / str(issue)


def tip_record_path(root, head):
    """`.frontlights/release/suite-<full head sha>.json`, the release suite record of one tip."""
    return record_folder(root) / f'suite-{head}.json'


def off_base_tip(root, base):
    """None when `root` has the local `base` checked out and HEAD is `refs/heads/<base>`; otherwise where it stands,
    in Portuguese: the release suite is run, and judged, only on the tip of the local base."""
    code, out, _ = git(root, 'symbolic-ref', '--short', '--quiet', 'HEAD')
    branch = out.strip() if code == 0 else None
    head, tip = rev(root, 'HEAD'), rev(root, f'refs/heads/{base}')
    if branch == base and head is not None and head == tip:
        return None
    return f'a worktree principal está em `{branch or "HEAD solta"}`, não na {base} local'


def uncommitted_files(root):
    """The files with a change not committed, tracked (staged or not) or untracked, `.frontlights/` left out as the
    evidence leaves it out: the release suite runs only on a clean tree, so its per-tip record is the commit's."""
    code, out, _ = git(root, '-c', 'core.quotePath=false', 'status', '--porcelain', '--untracked-files=all',
                       '--', '.', ':(exclude).frontlights')
    require(code == 0, 'o git não leu o estado da worktree')
    return sorted({line[3:].split(' -> ')[-1].strip('"') for line in out.splitlines() if line.strip()})


def zoned_now():
    """Now in RELEASE_ZONE (the user's zone), in the machine's local zone when it is unavailable; with offset."""
    try:
        return datetime.now(zoneinfo.ZoneInfo(RELEASE_ZONE))
    except (KeyError, OSError, ValueError):
        return datetime.now().astimezone()


def tree_evidence(root):
    """The `frontlights.py evidence` of `root` (HEAD, branch, diff and file hashes, `.frontlights/` left out): the
    evidence `review-gate` compares."""
    import frontlights   # noqa: PLC0415  (lazy: frontlights imports this module too)
    try:
        return frontlights.git_evidence(root)
    except (ValueError, subprocess.TimeoutExpired) as error:
        raise Refusal(f'a evidência da árvore não pôde ser lida: {str(error)[:STDERR_LIMIT]}')


def timeout_argument(text):
    """`--timeout-seconds` as a positive integer, None when it is not given."""
    if text is None:
        return None
    try:
        value = int(str(text).strip())
    except ValueError:
        value = 0
    require(value > 0, '--timeout-seconds precisa ser um inteiro positivo (segundos)')
    return value


def suite_run_settings(config, mode, argv_text, timeout_seconds=None):
    """(settings, source): the suite of the config, or the one `--argv` gives (full only; the timeout of the config
    when it declares the mode). Without a configured timeout, full gets FULL_SUITE_TIMEOUT and impact
    `checks.DEFAULT_TIMEOUT`; `--timeout-seconds` overrides the timeout either way. Settings None: the mode is not
    configured and nothing is given."""
    import checks   # noqa: PLC0415
    timeout_seconds = timeout_argument(timeout_seconds)
    default = FULL_SUITE_TIMEOUT if mode == 'full' else checks.DEFAULT_TIMEOUT
    configured = suite_entry((suite_block(config) or {}).get(mode), f'homolog.suites.{mode}', default, mode=mode)
    if argv_text is None:
        settings, source = configured, 'config'
    else:
        require(mode == 'full', '--argv só vale com --mode full: a suíte de impacto vem sempre do config')
        try:
            given = json.loads(argv_text)
        except ValueError:
            raise Refusal('--argv precisa ser uma lista JSON de argumentos')
        timeout = configured['timeout'] if configured else default
        settings, source = {'argv': suite_argv(given, '--argv'), 'timeout': timeout}, 'argument'
    if settings is not None and timeout_seconds is not None:
        settings = dict(settings, timeout=timeout_seconds)
    return settings, source


def run_suite_process(argv, root, timeout):
    """(exit code or None, timed out, error or None, output, warnings) of one run, no shell, the whole process tree
    killed at the timeout (checks.run_process); a timeout keeps the partial output, then the timeout sentence."""
    import checks   # noqa: PLC0415
    warnings = []
    try:
        code, output = checks.run_process(argv, root, timeout, warnings)
        return code, False, None, output, warnings
    except subprocess.TimeoutExpired as expired:
        partial = expired.output if isinstance(expired.output, str) else ''
        if partial and not partial.endswith('\n'):
            partial += '\n'
        return None, True, None, f'{partial}A suíte passou de {timeout} s e foi interrompida.\n', warnings
    except FileNotFoundError:
        return None, False, 'executable_missing', 'Executável da suíte não encontrado.\n', warnings
    except OSError:
        return None, False, 'cannot_start', 'A suíte não pôde ser iniciada.\n', warnings


def report_refusal(data):
    """None when `data` is a valid suite report: an object with `ran` and `complete` (lists of non-empty texts
    without NUL, no repeated id, every id of complete also in ran); any other key, like the usual keys of the
    `--report` of `tests/suite.py` (version, modules, totals, mode...), is ignored. Otherwise why not, in
    Portuguese."""
    if not isinstance(data, dict) or not {'ran', 'complete'} <= set(data):
        return 'ele precisa ser um objeto com as chaves ran e complete'
    for key in ('ran', 'complete'):
        ids = data[key]
        if not (isinstance(ids, list) and all(isinstance(item, str) and item and '\0' not in item for item in ids)):
            return f'{key} precisa ser uma lista de textos não vazios, sem byte NUL'
        if len(set(ids)) != len(ids):
            return f'{key} repete um id'
    if not set(data['complete']) <= set(data['ran']):
        return 'todo id de complete precisa estar também em ran'
    return None


def suite_report(path):
    """({'ran', 'complete'}, None) from the report the run wrote at `path` (at most RECORD_BYTES, UTF-8 with or
    without BOM; only those two keys are taken), or (None, the warning in Portuguese) when it is missing, too large
    or invalid."""
    lacking = 'o registro fica sem ran e complete'
    try:
        size = path.stat().st_size
    except OSError:
        return None, f'a suíte não gravou o relatório {path}; {lacking}'
    if size > RECORD_BYTES:
        return None, f'o relatório {path} passa de {RECORD_BYTES} bytes e não foi lido; {lacking}'
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, RecursionError):
        return None, f'o relatório {path} não é um JSON legível em UTF-8; {lacking}'
    reason = report_refusal(data)
    if reason:
        return None, f'o relatório {path} foi recusado: {reason}; {lacking}'
    return {'ran': data['ran'], 'complete': data['complete']}, None


def suite_message(record, timeout):
    mode = record['mode']
    if record['exitCode'] == 0:
        return f'A suíte {mode} passou em {record["seconds"]} s em {record["head"][:7]}.'
    if record['timedOut']:
        return f'A suíte {mode} passou do prazo de {timeout} s e foi interrompida.'
    if record.get('error'):
        return f'A suíte {mode} não rodou ({record["error"]}).'
    return f'A suíte {mode} falhou (código {record["exitCode"]}); a saída está em {record["output"]}.'


def write_release_records(root, record):
    """`release/suite.json` (the latest) and `release/suite-<head>.json` (this tip's, which a later tip never
    overwrites), the same text in both; their paths."""
    folder = record_folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, indent=2, ensure_ascii=True)
    latest, tip = folder / 'suite.json', tip_record_path(root, record['head'])
    latest.write_text(text, encoding='utf-8')
    tip.write_text(text, encoding='utf-8')
    return latest, tip


def adoption_refusal(root, base, origin, evidence):
    """None when the record `origin` may be adopted by the release at the tip of the local `base`, whose evidence
    now is `evidence`; otherwise why not, in Portuguese: a green whole suite, run on a clean tree, whose commit
    tree is the tip's (the bytes on disk are not compared)."""
    if origin['mode'] != 'full':
        return 'é um registro da suíte por impacto, e a release pede a suíte inteira'
    return same_tree_refusal(root, base, origin, evidence, 'a suíte inteira')


def same_tree_refusal(root, base, origin, evidence, what):
    """None when the suite record `origin` (`what` names its suite in the reason) stands for the tip of the local
    `base`: it ran green (exit code 0, no timeout, no error) on a clean tree, its head is known and the tree of that
    head is the tip's. Otherwise why not, in Portuguese. The bytes on disk are not compared (issue 57): with
    `core.autocrlf` two clean worktrees of the same commit tree can hold other line endings, and a clean tree of the
    same commit tree already holds the same content. The adoption (`adoption_refusal`) and the covered modules of
    the release (`impact_refusal`) share it; `evidence` is kept in the signature for them."""
    if origin.get('exitCode') != 0 or origin.get('timedOut') is not False or origin.get('error'):
        return f'{what} desse registro não passou (código diferente de 0, prazo estourado ou não rodou)'
    head = origin.get('head')
    if not (isinstance(head, str) and OID.fullmatch(head) and origin['evidence'].get('head') == head
            and tree_of(root, head)):
        return f'este repositório não conhece o commit {str(head)[:40]} do registro'
    changes = tip_changes(root, head, origin['evidence'])
    if changes:
        return f'ele rodou com {changes}, e só vale o registro de uma árvore limpa'
    tree, tip_tree = tree_of(root, head), tree_of(root, f'refs/heads/{base}')
    if tree != tip_tree:
        return f'ele rodou em outra árvore ({tree[:7]}), e a ponta da {base} local tem a árvore {str(tip_tree)[:7]}'
    return None


def adopt_suite(root, base, from_record):
    """Issue 54: the whole suite of the release taken from a green record of the same commit tree (`--from`),
    nothing run: the record keeps the original run and takes the evidence of the local main now, with
    `adoptedFrom` naming the path, the head and the tree of the origin."""
    path = Path(from_record).resolve()
    try:
        origin = read_suite_record(path)
    except Refusal as error:
        raise Refusal(f'{error}; nada foi gravado')
    require(origin is not None, f'não há registro de suíte em {path}; nada foi gravado')
    evidence = tree_evidence(root)
    reason = adoption_refusal(root, base, origin, evidence)
    if reason is None:
        code, top, _ = git(path.parent, 'rev-parse', '--show-toplevel')
        reason = (hidden_refusal(top.strip()) if code == 0 and top.strip() else
                  'a pasta do registro não está numa worktree do git, e não há como ver arquivos escondidos do git status')
    require(reason is None, f'{path} não vale pela ponta da {base} local: {reason}; nada foi gravado')
    tree = tree_of(root, origin['head'])
    record = dict(origin, base=base, head=evidence['head'], evidence=evidence,
                  adoptedFrom={'path': str(path), 'head': origin['head'], 'tree': tree,
                               'adoptedAt': zoned_now().isoformat(timespec='seconds')})
    latest, tip = write_release_records(root, record)
    return {'state': 'adopted', 'record': record, 'recordPath': str(latest), 'tipRecordPath': str(tip),
            'exitCode': 0,
            'message': f'A suíte inteira de {origin["head"][:7]} foi adotada para a ponta {evidence["head"][:7]} '
                       f'da {base} local (mesma árvore {str(tree)[:7]}); nada rodou.'}


def hidden_files(worktree):
    """The tracked files (outside `.frontlights/`) that `git status` does not watch in `worktree`: marked
    skip-worktree (tag `S`) or assume-unchanged (a lower-case tag) in `git ls-files -v`. A file so marked may hold
    other content than the commit and no evidence sees it (issue 57); None when Git cannot list the index."""
    code, out, _ = git(worktree, 'ls-files', '-v', '-z')
    if code != 0:
        return None
    hidden = []
    for line in out.split('\0'):
        if len(line) > 2 and (line[0] == 'S' or line[0].islower()) and not line[2:].startswith('.frontlights/'):
            hidden.append(line[2:])
    return sorted(hidden)


def hidden_refusal(worktree):
    """None when every tracked file of `worktree` is watched by `git status`; otherwise why not, in Portuguese."""
    hidden = hidden_files(worktree)
    if hidden is None:
        return f'o git não listou o índice de {worktree}'
    if hidden:
        names = ', '.join(hidden[:10]) + (', ...' if len(hidden) > 10 else '')
        return (f'arquivo(s) marcado(s) skip-worktree ou assume-unchanged ({names}): o git status não os vê, e a '
                'suíte pode ter rodado sobre outro conteúdo')
    return None


def impact_refusal(root, base, origin, evidence):
    """None when the impact record `origin` of an issue covers its `complete` at the tip of the local `base`;
    otherwise why not, in Portuguese (`same_tree_refusal` after the impact checks)."""
    if origin['mode'] != 'impact':
        return 'é um registro da suíte inteira, e só o impacto diz o que rodou inteiro'
    if report_refusal({'ran': origin.get('ran'), 'complete': origin.get('complete')}):
        return (f'ele não traz ran e complete válidos (a suíte de impacto rodou sem o {REPORT_TOKEN}, ou o '
                'relatório foi recusado)')
    return same_tree_refusal(root, base, origin, evidence, 'a suíte por impacto')


def covered_by_release(root, base, remote, evidence):
    """{'complete', 'from', 'refused'}: the union of `complete` of the impact records of the issues of the release
    (`release_work` over the authorization records of `root`, `pending`) that count by `impact_refusal`, read from
    `.frontlights/issues/<n>/suite.json` in the worktree its authorization entry names; `from` names each record
    that counted ({issue, path, head, tree}), `refused` each one that did not ({issue, path, reason}). When the list
    of the issues of the release cannot be had (no `refs/remotes/<remote>/<base>`, or no authorization record names
    an issue the release carries), `warnings` says why nothing was skipped."""
    remote_ref = f'refs/remotes/{remote}/{base}'
    if rev(root, remote_ref) is None:
        return {'complete': [], 'from': [], 'refused': [], 'warnings': [
            f'não há {remote_ref} neste repositório, então a lista das issues da release não pôde ser calculada e '
            f'nada foi pulado; rode o homolog sync antes']}
    issues, _, _ = release_work(root, base, remote, root)
    places = issue_worktrees(root)
    complete, origins, refused = [], [], []
    carried = [item for item in issues if pending(item)]
    if not carried:
        return {'complete': [], 'from': [], 'refused': [], 'warnings': [
            f'nenhum registro de autorização desta worktree nomeia uma issue da release (na {base} local e fora de '
            f'{remote_ref}), então nada foi pulado']}
    for item in carried:
        number = item['issue']
        place = places.get(number)
        if place is None:
            refused.append({'issue': number, 'path': None,
                            'reason': 'as autorizações não dão a worktree da issue, então não há registro a ler'})
            continue
        path, origin, reason = record_folder(Path(root, place), number) / 'suite.json', None, None
        if not Path(root, place).is_dir():
            reason = f'a worktree da issue não existe mais em {place}'
        else:
            try:
                origin = read_suite_record(path)
            except Refusal as error:
                reason = str(error)
            if origin is not None:
                reason = impact_refusal(root, base, origin, evidence) or hidden_refusal(Path(root, place))
            elif reason is None:
                reason = 'não há registro de suíte da issue'
        if reason:
            refused.append({'issue': number, 'path': str(path), 'reason': reason})
            continue
        complete += [name for name in origin['complete'] if name not in complete]
        origins.append({'issue': number, 'path': str(path), 'head': origin['head'],
                        'tree': tree_of(root, origin['head'])})
    return {'complete': complete, 'from': origins, 'refused': refused}


def skipped_sentence(covered):
    """The sentence of a message that says how many modules a run with COVERED_TOKEN skipped and from whose
    impact; '' without `covered`."""
    if not isinstance(covered, dict):
        return ''
    names = ', '.join(f'#{item.get("issue")}' for item in covered.get('from') or [])
    count, refused = len(covered.get('complete') or []), len(covered.get('refused') or [])
    where = f', que o impacto de {names} rodou inteiro(s) na mesma árvore' if names else ''
    left = f'; {refused} registro(s) de issue não contaram' if refused else ''
    why = ''.join(f' ({warning})' for warning in covered.get('warnings') or [])
    return f' A suíte inteira pulou {count} módulo(s){where}{left}{why}.'


def op_suite(root, config_path, issue, mode, base, concurrent, argv_text, release=False, timeout_seconds=None,
             from_record=None, remote='origin'):
    import checks   # noqa: PLC0415
    worktree(root)
    issue = None if release else issue_number(issue)
    require(mode in SUITE_MODES, 'o modo da suíte precisa ser impact ou full')
    require(not release or mode == 'full', '--release só aceita --mode full: a release roda a suíte inteira')
    require(from_record is None or release, '--from só vale com --release: a release adota a suíte inteira de uma '
                                            'issue; nada foi gravado')
    require(from_record is None or (argv_text is None and timeout_seconds is None),
            '--from não roda nada, então não aceita --argv nem --timeout-seconds; nada foi gravado')
    base = plain_name(base, 'a branch base')
    place = off_base_tip(root, base) if release else None
    require(place is None, f'{place}; a suíte da release roda só na ponta da {base} local')
    dirty = uncommitted_files(root) if release else []
    require(not dirty, f'a worktree tem {len(dirty)} arquivo(s) com alterações não commitadas '
                       f'({", ".join(dirty[:10])}{", ..." if len(dirty) > 10 else ""}); a suíte da release roda só '
                       f'numa árvore limpa, commite ou descarte antes; nada foi rodado')
    if from_record is not None:
        return adopt_suite(root, base, from_record)
    settings, source = suite_run_settings(load_config(config_path), mode, argv_text, timeout_seconds)
    if settings is None:
        return {'state': 'unconfigured', 'exitCode': 2,
                'message': f'o config não declara homolog.suites.{mode}; nada foi rodado'}
    argv = [argument.replace(BASE_TOKEN, base) for argument in settings['argv']]
    checks.load_user_secrets(config_path)
    evidence = tree_evidence(root)          # before the run: an edit during it makes the record stale
    folder = record_folder(root, issue)
    folder.mkdir(parents=True, exist_ok=True)
    started = zoned_now()
    stamp = started.strftime('%Y%m%d-%H%M%S')
    log = fresh_file(folder, f'suite-{mode}-{stamp}', '.log')
    report = fresh_file(folder, f'suite-report-{stamp}', '.json') if REPORT_TOKEN in argv else None
    if report is not None:
        argv = [str(report) if argument == REPORT_TOKEN else argument for argument in argv]
    covered = None
    if COVERED_TOKEN in argv:   # outside the release no issue covers anything: the file lists nothing
        covered = (covered_by_release(root, base, plain_name(remote, 'o remoto'), evidence) if release
                   else {'complete': [], 'from': [], 'refused': []})
        file = fresh_file(folder, f'suite-covered-{stamp}', '.json')
        file.write_text(json.dumps({'complete': covered['complete']}, ensure_ascii=True), encoding='utf-8')
        covered['file'] = str(file)
        argv = [str(file) if argument == COVERED_TOKEN else argument for argument in argv]
    code, timed_out, error, output, warnings = run_suite_process(argv, str(Path(root).resolve()), settings['timeout'])
    finished = zoned_now()
    log.write_text(checks.redact(output), encoding='utf-8')
    record = {'mode': mode, 'source': source, 'base': base, 'argv': checks.redact_argv(argv),
              'head': evidence['head'], 'evidence': evidence, 'exitCode': code, 'timedOut': timed_out,
              'seconds': round((finished - started).total_seconds(), 3), 'output': str(log),
              'concurrent': bool(concurrent), 'startedAt': started.isoformat(timespec='seconds'),
              'finishedAt': finished.isoformat(timespec='seconds')}
    if error:
        record['error'] = error
    if report is not None:   # the run's own exit code stands either way; a bad report is only a warning
        record['report'] = str(report)
        lists, warning = suite_report(report)
        if warning:
            warnings.append(warning)
        else:
            record.update(lists)
    if covered is not None:
        record['covered'] = covered
    if warnings:
        record['warnings'] = warnings
    path = folder / 'suite.json'
    text = json.dumps(record, indent=2, ensure_ascii=True)
    path.write_text(text, encoding='utf-8')
    result = {'state': 'green' if code == 0 else 'red', 'record': record, 'recordPath': str(path),
              'exitCode': 0 if code == 0 else 1,
              'message': suite_message(record, settings['timeout']) + skipped_sentence(covered)}
    if release:   # the copy of this tip, which a run at a later tip never overwrites (`suite-gate --head`)
        tip = tip_record_path(root, evidence['head'])
        tip.write_text(text, encoding='utf-8')
        result['tipRecordPath'] = str(tip)
    return result


def read_suite_record(path):
    """The record at `path`, or None when there is none; a Refusal when it is not a suite record."""
    if not path.exists():
        return None
    data = read_record(path)
    evidence = data.get('evidence') if isinstance(data, dict) else None
    require(isinstance(evidence, dict) and data.get('mode') in SUITE_MODES,
            f'{path} não é um registro de suíte (mode e evidence); rode `homolog suite` de novo')
    return data


def judge_suite(root, path, required=None, configured=True):
    """The suite record at `path` judged against the tree of `root` now, the way `review-gate` does: `current`
    (exit code 0), `stale`, `red`, or `missing` (no record, or not a full one when `required` is full); without a
    record and with `configured` false, `unconfigured`. `suite-gate` and `release-plan` share it."""
    import frontlights   # noqa: PLC0415
    record = read_suite_record(path)
    result = {'recordPath': str(path)}
    if record is None:
        if not configured:
            result.update(status='unconfigured', exitCode=2,
                          message='não há registro de suíte e o config não declara homolog.suites')
        else:
            result.update(status='missing', exitCode=2, message=f'não há registro de suíte em {path}; rode `homolog suite`')
        return result
    try:
        compared = frontlights.review_gate(record['evidence'], tree_evidence(root))
    except ValueError as error:
        raise Refusal(f'{path} tem uma evidência incompleta: {str(error)[:STDERR_LIMIT]}')
    result.update(mode=record['mode'], source=record.get('source'), suiteExitCode=record.get('exitCode'),
                  changed=compared['changed'], files_changed=compared['files_changed'],
                  recordedHead=compared['reviewed_head'], currentHead=compared['current_head'])
    if compared['status'] != 'current':
        result.update(status='stale', exitCode=2,
                      message=f'a suíte rodou em outra ponta; difere: {", ".join(compared["changed"])}')
    elif record.get('exitCode') != 0:
        result.update(status='red', exitCode=2, message=f'a suíte {record["mode"]} falhou nesta ponta')
    elif required == 'full' and record['mode'] != 'full':
        result.update(status='missing', exitCode=2,
                      message=f'o registro é da suíte {record["mode"]}; --require full pede a suíte completa')
    else:
        result.update(status='current', exitCode=0,
                      message=f'a suíte {record["mode"]} passou nesta ponta ({compared["current_head"][:7]})')
    return result


def release_suite(root, base):
    """The whole suite of the release judged at the tip of the local base (`judge_suite`, full required), or
    `elsewhere` when the main worktree is not on that tip; never a refusal, so the plan still answers."""
    path = record_folder(root) / 'suite.json'
    place = off_base_tip(root, base)
    if place is not None:
        return {'recordPath': str(path), 'status': 'elsewhere', 'message': place}
    try:
        judged = judge_suite(root, path, 'full')
    except Refusal as error:
        return {'recordPath': str(path), 'status': 'missing', 'message': str(error)}
    if judged['status'] == 'missing' and 'mode' not in judged:
        judged['message'] = f'não há registro da suíte inteira em {path}'
    judged.pop('exitCode')
    return adopted(judged, read_suite_record(path) or {})


def tip_changes(root, head, evidence):
    """None when the evidence of a per-tip record shows a clean tree at `head`: the diff is empty (EMPTY_DIFF) and
    every file it hashed is in the commit. Otherwise, in Portuguese, what was not committed (`.frontlights/` is never
    in the evidence)."""
    files = evidence.get('files')
    if evidence.get('diff_sha256') != EMPTY_DIFF:
        return 'alterações não commitadas em arquivos versionados'
    code, out, _ = git(root, 'ls-tree', '-r', '-z', '--name-only', head)
    if code != 0 or not isinstance(files, dict):
        return 'uma evidência que não se confere com o commit'
    extra = sorted(set(files) - set(out.split('\0')))
    if extra:
        return f'arquivo(s) não commitado(s) ({", ".join(extra[:10])}{", ..." if len(extra) > 10 else ""})'
    return None


def adopted(result, record):
    """`result` with the `adoptedFrom` of an adopted record and, when it is current, the tip it was adopted from in
    its message (issue 54); and with what a run with COVERED_TOKEN skipped (`skipping`)."""
    origin = record.get('adoptedFrom')
    if isinstance(origin, dict):
        result['adoptedFrom'] = origin
        if result.get('status') == 'current':
            result['message'] += f', adotada da ponta {str(origin.get("head"))[:7]}'
    return skipping(result, record)


def skipping(result, record):
    """`result` with the `covered` of a release run with COVERED_TOKEN (issue 57, S4) and, in its message, how many
    modules it skipped and from whose impact."""
    covered = record.get('covered')
    if isinstance(covered, dict):
        result['covered'] = covered
        sentence = skipped_sentence(covered).strip().rstrip('.')
        result['message'] += f'; {sentence[0].lower()}{sentence[1:]}'
    return result


def judge_tip(root, head):
    """The release suite record of one tip (`release/suite-<head>.json`) judged by itself: `current` when it is a
    full run of that head that exited 0, `red` when it failed, `missing` without it. The main worktree may stand
    anywhere: the tip is named, not read from the tree."""
    path = tip_record_path(root, head)
    record = read_suite_record(path)
    result = {'recordPath': str(path), 'head': head, 'required': 'full'}
    if record is None:
        result.update(status='missing', exitCode=2,
                      message=f'não há registro da suíte inteira da ponta {head[:7]} em {path}')
        return result
    require(record.get('head') == head, f'{path} não é o registro da ponta {head[:7]} (head {str(record.get("head"))[:7]})')
    result.update(mode=record['mode'], source=record.get('source'), suiteExitCode=record.get('exitCode'))
    changes = tip_changes(root, head, record['evidence'])
    if record['mode'] != 'full':
        result.update(status='missing', exitCode=2, message=f'o registro da ponta {head[:7]} não é da suíte inteira')
    elif changes:
        result.update(status='missing', exitCode=2,
                      message=f'o registro da ponta {head[:7]} rodou com {changes}; não vale pelo commit, rode a '
                              f'suíte da release de novo numa árvore limpa')
    elif record.get('exitCode') != 0:
        result.update(status='red', exitCode=2, message=f'a suíte inteira falhou na ponta {head[:7]}')
    else:
        result.update(status='current', exitCode=0, message=f'a suíte inteira passou na ponta {head[:7]}')
    return adopted(result, record)


def full_sha(value):
    """`--head` as a full commit sha (40 or 64 hex digits), lowercased."""
    text = str(value or '').strip().lower()
    require(len(text) in (40, 64) and all(char in '0123456789abcdef' for char in text),
            '--head precisa ser o sha completo de um commit (40 ou 64 dígitos hexadecimais)')
    return text


def op_suite_gate(root, config_path, issue, required, release=False, base='main', head=None):
    worktree(root)
    require(head is None or release, '--head só vale com --release: julga o registro da release de uma ponta')
    issue = None if release else issue_number(issue)
    suites = suite_block(load_config(config_path))
    if release and head is not None:
        plain_name(base, 'a branch base')
        return judge_tip(root, full_sha(head))
    if release:
        base = plain_name(base, 'a branch base')
        place = off_base_tip(root, base)
        require(place is None, f'{place}; a suíte da release só é julgada na ponta da {base} local')
        required = 'full'
    configured = bool(suites) and any(suites.get(mode) is not None for mode in SUITE_MODES)
    result = {'required': required}
    path = record_folder(root, issue) / 'suite.json'
    result.update(judge_suite(root, path, required, configured))
    return skipping(result, read_suite_record(path) or {}) if release else result


# ---------------------------------------------------------------- merge into the local main (redesign, issue 4)

GATE_QUESTIONS = {
    'pending': ('O teste assistido da issue #{n} ainda não foi respondido. Rodar agora?',
                ['Rodar o teste assistido agora', 'Parar']),
    'stale': ('O código da issue #{n} mudou depois do teste assistido. Assistir de novo?',
              ['Assistir de novo', 'Parar']),
    'contradiction': ('O diff da issue #{n} muda a tela, e o plano diz que não toca o frontend. Rodar o teste '
                      'assistido?', ['Rodar o teste assistido', 'Parar']),
    'unconfigured': ('A issue #{n} muda a tela e o projeto não tem browserTest. Como verificar?',
                     ['Configurar o browserTest agora', 'Dispensar o teste assistido desta issue', 'Parar']),
}


def charter_of(root):
    path = Path(root) / '.frontlights' / 'authorization.json'
    data = read_record(path) if path.is_file() else None
    require(isinstance(data, dict), 'não há charter legível em .frontlights/authorization.json; rode `frontlights.py '
                                    'charter new` antes')
    return path, data


def issue_body(root, repository, number, gh=None):
    """The body of the issue: GitHub (read only) with a repository, the local record without one."""
    import closeout   # noqa: PLC0415
    if repository:
        return closeout.read_issue_body(gh or closeout.rs.gh_default, repository, number)
    local = read_record(Path(root) / '.frontlights' / 'issues' / str(number) / 'issue.json')
    require(isinstance(local, dict) and isinstance(local.get('body'), str),
            f'sem repositório e sem .frontlights/issues/{number}/issue.json com o corpo da issue')
    return local['body']


def merge_preconditions(root, base):
    code, out, _ = git(root, 'symbolic-ref', '--short', '--quiet', 'HEAD')
    head = out.strip() if code == 0 else None
    require(head == base, f'a worktree principal está em `{head or "HEAD solta"}`, não em `{base}`; o merge na main '
                          'local roda na worktree principal')
    dirty = status_lines(root)
    require(not dirty, f'a worktree principal tem {len(dirty)} arquivo(s) com alterações não commitadas; o merge na '
                       'main local precisa dela limpa')
    require(rev(root, 'MERGE_HEAD') is None, 'há um merge em andamento na worktree principal; conclua-o ou aborte-o')


def unmerged_files(tree):
    _, out, _ = git(tree, 'diff', '--name-only', '--diff-filter=U')
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def previous_merge_passed(folder):
    for path in sorted(folder.glob('merge-local-main*.json')):
        data = read_record(path)
        answer = data.get('authorize') if isinstance(data, dict) else None
        if isinstance(answer, dict) and answer.get('scope_check') == 'pass':
            return path
    return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def op_merge(root, config_path, issue, free_test_fix=False, dry_run=False, toca=None, gh=None, update_check=None):
    """`homolog merge --issue n`: the steps of "Into the local main" in one command (see the module's docstring)."""
    import closeout      # noqa: PLC0415
    import frontlights   # noqa: PLC0415
    worktree(root)
    root = Path(root)
    number = issue_number(str(issue))
    charter_path, record = charter_of(root)
    require(number in record.get('issue_ids', []), f'a issue #{number} não está no charter')
    prefix = _cli.branch_prefix(record=record)[0]
    require(is_prefix(prefix), 'o charter não tem branch_prefix válido')
    base = plain_name((record.get('base') or {}).get('branch') or 'main', 'a branch base')
    merge_preconditions(root, base)
    issue_branch, integra = f'{prefix}issue-{number}', f'{prefix}issue-{number}-integra'
    tip = rev(root, f'refs/heads/{issue_branch}')
    require(tip, f'a branch da issue `{issue_branch}` não existe')
    entries = [e for e in record.get('worktrees', []) if isinstance(e, dict) and e.get('issue') == number]
    own = next((e for e in entries if e.get('branch') == issue_branch and not e.get('slice')), None)
    require(own and Path(own.get('path', '')).is_dir(), f'o charter não tem a worktree da branch {issue_branch}')
    outside = []
    for entry in entries:
        if entry.get('slice'):
            slice_tip = rev(root, f'refs/heads/{entry.get("branch")}')
            if slice_tip is None or ancestry(root, slice_tip, f'refs/heads/{issue_branch}') is not True:
                outside.append(entry['slice'])
    if outside:
        return {'exitCode': 1, 'reason': 'slice_outside', 'slices': outside,
                'message': f'a(s) slice(s) {", ".join(outside)} do charter não está(ão) na branch da issue: rode '
                           '`slice merge` de cada uma antes do merge na main local'}
    body = issue_body(root, record.get('repository'), number, gh)
    counted = closeout.criteria(body) or (0, 0)
    boxes = closeout.slice_boxes(body)
    if counted[1] == 0:
        return {'exitCode': 1, 'reason': 'no_criteria', 'criteria': {'checked': 0, 'total': 0},
                'message': f'a issue #{number} não tem caixas na seção de critérios de aceitação: o merge na main local '
                           'conta as caixas marcadas com evidência; escreva os critérios na issue (etapa 5) antes'}
    if counted[0] != counted[1]:
        opened = [b['label'] for b in boxes if not b['ticked']]
        return {'exitCode': 1, 'reason': 'open_boxes', 'criteria': {'checked': counted[0], 'total': counted[1]},
                'open': opened, 'message': f'a issue #{number} tem {counted[1] - counted[0]} caixa(s) aberta(s) nos '
                                           f'critérios{" (" + ", ".join(opened) + ")" if opened else ""}: marque-as '
                                           'com a evidência antes do merge na main local'}
    folder = root / '.frontlights' / 'issues' / str(number)
    record_path = folder / 'browser' / 'result.json'
    result = {'issue': number, 'issueBranch': issue_branch, 'integration': integra, 'base': base}
    if free_test_fix:
        import browser_gate   # noqa: PLC0415
        answered = read_record(record_path) if record_path.is_file() else None
        situation = browser_gate.situation(answered) if answered else None
        require(situation in browser_gate.ANSWERED, f'--free-test-fix exige o result.json da issue respondido (está '
                                                    f'{situation or "sem registro"})')
        previous = previous_merge_passed(folder)
        require(previous, '--free-test-fix exige um merge anterior desta issue na main local com o authorize em pass')
        gate = {'status': 'answered', 'evidence': 'teste livre', 'previous': str(previous)}
    else:
        import browser_gate   # noqa: PLC0415
        try:
            gate, code = browser_gate.run_cli([own['path']], base, config_path, toca,
                                              str(record_path) if record_path.is_file() else None)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            raise Refusal(f'o browser-gate não respondeu: {str(error)[:200]}')
        if code != 0:
            text, options = GATE_QUESTIONS.get(gate.get('status'), GATE_QUESTIONS['pending'])
            return {'exitCode': 2, 'reason': 'gate', 'gate': gate, 'question': text.format(n=number),
                    'options': options, 'message': f'o portão da issue #{number} não está verde '
                                                   f'({gate.get("status")}): pergunte antes do merge'}
    result['gate'] = gate
    need = [b['label'] for b in boxes if gate['status'] == 'not_needed' or b['semTela']]
    walks, missing = {}, []
    for label in need:
        path = folder / 'walkthroughs' / f'{label}.md'
        problems = closeout.walkthrough_problems(path.read_text(encoding='utf-8-sig')) if path.is_file() else ['ausente']
        walks[label] = {'path': str(path), 'problems': problems}
        if problems:
            missing.append(label)
    result['walkthroughs'] = walks
    if missing:
        return dict(result, exitCode=1, reason='walkthroughs', missing=missing,
                    message=f'sem o roteiro no formato das caixas sem tela {", ".join(missing)}: rode o roteiro e '
                            'grave walkthroughs/S<k>.md antes do merge na main local')
    present = rev(root, f'refs/heads/{integra}')
    entry = next((e for e in entries if e.get('branch') == integra), None)
    path = Path(entry['path']) if entry else Path(own['path']).parent / f'issue-{number}-integra'
    if dry_run:
        steps = ([f'git worktree add -b {integra} {path} {issue_branch}'] if present is None else
                 [f'git merge {issue_branch} (em {path})']) + [f'git merge {base} (em {path})', 'authorize',
                                                                 f'git merge --no-ff {integra} (na principal)', 'bundle']
        return dict(result, exitCode=0, dryRun=True, steps=steps, written=False,
                    message=f'Dry-run: a issue #{number} entra na main local por {integra}; nada foi gravado.')
    if present is None:
        require(not path.exists(), f'a pasta {path} já existe; a worktree de integração não é criada por cima')
        code, _, err = git(root, 'worktree', 'add', '-b', integra, str(path), issue_branch)
        require(code == 0, f'`git worktree add` da integração falhou: {trimmed(err)}')
        entry = {'issue': number, 'path': str(path), 'branch': integra, 'ownership': list(own.get('ownership', []))}
        record.setdefault('worktrees', []).append(entry)
        write_json(charter_path, record)
    else:
        require(entry is not None and path.is_dir(), f'a branch {integra} existe, mas o charter não tem a worktree '
                                                     'dela; registre-a ou remova a branch')
        require(not status_lines(path) and rev(path, 'MERGE_HEAD') is None,
                f'a worktree {path.name} tem alterações ou um merge em andamento: conclua a resolução e repita')
        code, _, err = git(path, 'merge', '--no-edit', issue_branch)
        if code != 0:
            files = unmerged_files(path)
            require(files, f'`git merge {issue_branch}` na integração falhou: {trimmed(err)}')
            return dict(result, exitCode=2, conflict=True, files=files, worktree=str(path),
                        message=f'conflito ao trazer a branch da issue para {integra} em: {", ".join(files)}; '
                                'resolva e commite na worktree de integração e repita `homolog merge`')
    code, _, err = git(path, 'merge', '--no-edit', base)
    if code != 0:
        files = unmerged_files(path)
        require(files, f'`git merge {base}` na integração falhou: {trimmed(err)}')
        return dict(result, exitCode=2, conflict=True, files=files, worktree=str(path),
                    message=f'conflito ao trazer a {base} local para {integra} em: {", ".join(files)}; resolva e '
                            'commite na worktree de integração e repita `homolog merge`')
    stamp = zoned_now().strftime('%Y%m%d-%H%M%S')
    operation = {'repository': record.get('repository'), 'issue': number, 'kind': 'merge_into_local_main',
                 'worktree': str(path), 'branch': integra, 'target': base,
                 'gates': {'browser_gate': gate['status']}}
    if free_test_fix:
        operation['evidence'] = 'teste livre'
    record_file = folder / f'merge-local-main-{stamp}.json'
    saved = dict(operation, at=zoned_now().isoformat(timespec='seconds'), gate=gate, walkthroughs=walks)
    try:
        saved['authorize'] = frontlights.authorize(record, operation)
    except (ValueError, OSError) as error:
        saved['authorize'] = {'scope_check': 'fail', 'error': str(error)[:300]}
        write_json(record_file, saved)
        return dict(result, exitCode=1, reason='authorize', record=str(record_file),
                    message=f'o authorize recusou o merge na main local: {str(error)[:200]}; pergunte ao usuário, '
                            'nunca edite os portões')
    before = rev(root, 'HEAD')
    code, _, err = git(root, 'merge', '--no-ff', '--no-edit', '-m', f'Merge na main local: issue #{number}', integra)
    if code != 0:
        files = unmerged_files(root)
        abort_merge(root, before)
        saved['merge'] = {'conflict': files}
        write_json(record_file, saved)
        return dict(result, exitCode=2, conflict=True, files=files, record=str(record_file),
                    message=f'o merge de {integra} na {base} local teve conflito em {", ".join(files)} e foi '
                            'abortado; traga a main local de novo para a integração e repita')
    saved['merge'] = {'before': before, 'after': rev(root, 'HEAD')}
    if config_path:
        try:
            saved['bundle'] = op_bundle(root, config_path, base, None)
        except Refusal as error:
            saved['bundle'] = {'written': False, 'exitCode': 1, 'message': str(error)}
    else:
        saved['bundle'] = {'written': False, 'configured': False, 'message': 'sem config: sem backup configurado'}
    saved['skillUpdate'] = (update_check or frontlights.update_check)()
    write_json(record_file, saved)
    bundled = saved['bundle'].get('path') or 'sem backup configurado'
    return dict(result, exitCode=0, record=str(record_file), merge=saved['merge'], authorize=saved['authorize'],
                bundle=saved['bundle'], skillUpdate=saved['skillUpdate'], integrationWorktree=str(path),
                message=f'A issue #{number} entrou na {base} local ({saved["merge"]["after"][:7]}) por {integra}, com '
                        f'o portão {gate["status"]}; backup: {bundled}. Registro em {record_file.name}.')


# ---------------------------------------------------------------- release by command (redesign, issue 4)

RELEASE_ACTIONS = ('plan', 'body-check', 'go', 'status', 'landed')
UNCHANGED = 4                                    # `release status --since`: the state did not change
GREEN_GATES = ('answered', 'not_needed')
CLOSING_WORD = re.compile(r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*(?:[\w.-]+/[\w.-]+)?#\d+', re.I)
CLOSES_LINE = re.compile(r'^Closes #([0-9]{1,9})\s*$')
ABSOLUTE_PATH = re.compile(r'(?<![\w/])(?:[A-Za-z]:\\|/home/|/Users/)')
PLACEHOLDER = re.compile(r'<(?:n|a|b|título|titulo|data)>|#<')
MERGE_OPTIONS = ['Sim, mesclar', 'Não, aguardar o merge']


def release_folder(root):
    return Path(root) / '.frontlights' / 'release'


def watched(root, number):
    """True when a merge record of the issue in the local main carries the watched run green and authorize in pass."""
    for path in sorted((Path(root) / '.frontlights' / 'issues' / str(number)).glob('merge-local-main*.json')):
        data = read_record(path)
        gates = data.get('gates') if isinstance(data, dict) else None
        answer = data.get('authorize') if isinstance(data, dict) else None
        if isinstance(gates, dict) and gates.get('browser_gate') in GREEN_GATES and (
                not isinstance(answer, dict) or answer.get('scope_check') == 'pass'):
            return True
    return False


def template_headings():
    text = (HERE.parent / 'templates' / 'pr.md').read_text(encoding='utf-8')
    return [line[3:].strip() for line in text.splitlines() if line.startswith('## ')]


def body_problems(text, closes):
    """What the body of the release's pull request lacks against templates/pr.md and `closes`."""
    problems, fence, found, close_lines, first_heading = [], False, [], [], None
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r'^\s*(```|~~~)', line):
            fence = not fence
            continue
        if fence:
            continue
        if line.startswith('## '):
            found.append(line[3:].strip())
            first_heading = first_heading or number
            continue
        match = CLOSES_LINE.match(line)
        if match:
            close_lines.append((number, int(match.group(1))))
        elif CLOSING_WORD.search(line):
            problems.append(f'linha {number}: palavra de fechamento fora das linhas `Closes #n` de `closes`')
    wanted = [h for h in template_headings() if h in ('Resumo', 'Evidência', 'Risco do merge')]
    positions = [found.index(h) if h in found else None for h in wanted]
    for heading, position in zip(wanted, positions):
        if position is None:
            problems.append(f'sem a seção ## {heading} do modelo templates/pr.md')
    present = [p for p in positions if p is not None]
    if present != sorted(present):
        problems.append(f'as seções fora da ordem do modelo ({", ".join(wanted)})')
    numbers = [n for _, n in close_lines]
    if sorted(set(numbers)) != sorted(set(closes)) or len(numbers) != len(set(numbers)):
        problems.append(f'as linhas `Closes #n` ({", ".join(f"#{n}" for n in numbers) or "nenhuma"}) não são as de '
                        f'`closes` ({", ".join(f"#{n}" for n in closes) or "nenhuma"}), uma por issue')
    if close_lines and first_heading and any(line > first_heading for line, _ in close_lines):
        problems.append('as linhas `Closes #n` vêm antes de ## Resumo, fora de bloco de código')
    if PLACEHOLDER.search(text):
        problems.append('marcador do modelo não preenchido (<n>, <título>, #<a>...)')
    if ABSOLUTE_PATH.search(text):
        problems.append('caminho absoluto no corpo: cite o print pelo nome e pela pasta da issue')
    return problems


def closes_list(value):
    if value is None:
        return None
    numbers = [part.strip().lstrip('#') for part in str(value).split(',') if part.strip()]
    require(all(n.isdigit() and int(n) > 0 for n in numbers), '--closes leva números de issue, como --closes 12,13')
    return [int(n) for n in numbers]


def release_title(plan):
    issues = ', '.join(f'#{n}' for n in plan.get('release', []))
    directs = '; '.join(plan.get('releaseDirect', []))
    named = f'issues {issues}' if issues else ''
    named = '; '.join(part for part in (named, directs) if part)
    return f'Release {release_date()}: {named}'


def monitor_line(root, state):
    script = HERE / 'homolog.py'
    return (f'until python "{script}" release status --root "{root}" --since {state} --quiet; do sleep 180; done')


def pr_state(entry):
    status = entry.get('status')
    if status == 'merged_into_base':
        return 'merged'
    if status != 'open':
        return status or 'unknown'
    if entry.get('blocked'):
        return 'blocked'
    if entry.get('mergeable') in (None, 'UNKNOWN') or entry.get('mergeStateStatus') in (None, 'UNKNOWN'):
        return 'pending'
    return 'ready'


def current_release(root):
    path = release_folder(root) / 'current.json'
    data = read_record(path) if path.is_file() else None
    require(isinstance(data, dict) and isinstance(data.get('pr'), int), 'não há release aberta em '
            '.frontlights/release/current.json; grave-a com `release go --record --pr <n>` depois do gh pr create')
    return path, data


def op_release(action, root, base='main', remote='origin', config_path=None, prefix=None, records=None, body=None,
               closes=None, record=False, pr=None, legacy=False, answer=None, since=None, gh=None, update_check=None,
               planner=None):
    """`release plan|body-check|go|status|landed` (see the module's docstring)."""
    worktree(root)
    root = Path(root)
    require(action in RELEASE_ACTIONS, f'release {str(action)[:20]}: a ação é {", ".join(RELEASE_ACTIONS)}')
    if action == 'plan':
        result = op_release_plan(root, base, remote, prefix, records, config_path, gh)
        missing = [n for n in result.get('closes', []) if not watched(root, n)]
        if missing:
            result.update(exitCode=1, ready=False, reason='watched_run_missing', missing=missing,
                          message=f'sem teste assistido registrado (merge-local-main com o portão verde) para '
                                  f'{", ".join(f"#{n}" for n in missing)}, de `closes`: a release espera o portão '
                                  'de cada issue')
        return result
    if action == 'body-check':
        require(body and Path(body).is_file(), 'body-check precisa de --body <arquivo do corpo da PR>')
        wanted = closes_list(closes)
        if wanted is None:
            wanted = op_release_plan(root, base, remote, prefix, records, config_path, gh).get('closes', [])
        problems = body_problems(Path(body).read_text(encoding='utf-8-sig'), wanted)
        return {'exitCode': 1 if problems else 0, 'body': str(body), 'closes': wanted, 'problems': problems,
                'message': ('O corpo segue templates/pr.md e as linhas `Closes #n` são as de `closes`.' if not problems
                            else f'O corpo tem {len(problems)} problema(s): ' + '; '.join(problems))}
    if action == 'go':
        folder = release_folder(root)
        if record:
            require(isinstance(pr, int) and pr > 0, '--record precisa de --pr <número da PR criada>')
            pending_path = folder / 'pending.json'
            pending = read_record(pending_path) if pending_path.is_file() else None
            require(isinstance(pending, dict), 'sem .frontlights/release/pending.json: rode `release go --body <arquivo>` '
                                               'antes e o push e o gh pr create que ele imprimir')
            current = dict(pending, pr=pr, recordedAt=zoned_now().isoformat(timespec='seconds'),
                           waitingSince=zoned_now().isoformat(timespec='seconds'))
            write_json(folder / 'current.json', current)
            os.replace(pending_path, folder / f'pending-{zoned_now().strftime("%Y%m%d-%H%M%S")}.json')
            return {'exitCode': 0, 'release': current, 'monitor': monitor_line(root, 'pending'),
                    'message': f'Release registrada: PR #{pr} de {current["branch"]} em {current["base"]}. A sessão '
                               'aguarda o merge do usuário; aja só sobre `release status`, nunca sobre uma notificação.'}
        plan = op_release_plan(root, base, remote, prefix, records, config_path, gh)
        if plan.get('exitCode') != 0:
            return plan
        missing = [n for n in plan.get('closes', []) if not watched(root, n)]
        require(not missing, f'sem teste assistido registrado para {", ".join(f"#{n}" for n in missing)}: a release '
                             'espera o portão de cada issue')
        require(plan.get('releaseBranch'), 'sem prefixo das branches, a release não tem nome: declare branchPrefix')
        require(body and Path(body).is_file(), 'go precisa de --body <arquivo do corpo da PR> (templates/pr.md)')
        problems = body_problems(Path(body).read_text(encoding='utf-8-sig'), plan.get('closes', []))
        if problems:
            return {'exitCode': 1, 'reason': 'body', 'problems': problems,
                    'message': 'O corpo da PR não passa no body-check: ' + '; '.join(problems)}
        if legacy:
            require(answer == 'Sim', '--legacy-branch só com --answer "Sim", a resposta literal da pergunta "Lançar '
                                     'pelo caminho antigo, com a branch local <release>?"')
        name, title = plan['releaseBranch'], release_title(plan)
        config = load_config(config_path) if config_path and Path(config_path).is_file() else {}
        repository = config.get('repository')
        create = ['gh', 'pr', 'create', '--base', base, '--head', name, '--title', title, '--body-file', str(body)]
        if repository:
            create[3:3] = ['--repo', repository]
        commands = ([['git', '-C', str(root), 'branch', name, base], ['git', '-C', str(root), 'push', '-u', remote, name]]
                    if legacy else [['git', '-C', str(root), 'push', remote, f'{base}:refs/heads/{name}']]) + [create]
        pending = {'branch': name, 'base': base, 'remote': remote, 'issues': plan.get('release', []),
                   'directs': plan.get('releaseDirect', []), 'closes': plan.get('closes', []), 'title': title,
                   'body': str(body), 'legacy': bool(legacy), 'answer': answer if legacy else None,
                   'localMain': plan.get('localMain'), 'at': zoned_now().isoformat(timespec='seconds')}
        write_json(folder / 'pending.json', pending)
        update = (update_check or __import__('frontlights').update_check)()
        return {'exitCode': 0, 'commands': commands, 'release': pending, 'skillUpdate': update,
                'next': ['python', str(HERE / 'homolog.py'), 'release', 'go', '--record', '--pr', '<n>'],
                'message': f'Rode os comandos de `commands` (cobertos: o push da ponta da {base} local para {name} e a '
                           'PR única), depois `release go --record --pr <n>` com o número da PR.'}
    path, current = current_release(root)
    import closeout   # noqa: PLC0415
    status = closeout.op_merge_status(config_path, str(current['pr']), current.get('base') or base, gh)
    entry = status['pullRequests'][0]
    state = pr_state(entry)
    missing = [n for n in current.get('closes', []) if not watched(root, n)]
    if action == 'status':
        result = {'exitCode': 0, 'pr': current['pr'], 'state': state, 'pullRequest': entry, 'offerMerge': False,
                  'monitor': monitor_line(root, state)}
        if state == 'ready' and not missing:
            number = str(current['pr'])
            result.update(offerMerge=True, question=f'Mesclar a PR #{number} em {current["base"]}?',
                          options=list(MERGE_OPTIONS),
                          commands=[['gh', 'pr', 'ready', number], ['gh', 'pr', 'merge', number, '--merge']],
                          message=f'A PR #{number} está pronta: pergunte (operação negada, "Sim" antes de rodar).')
        elif state == 'blocked':
            result['message'] = (f'A PR #{current["pr"]} está bloqueada ({"; ".join(entry.get("blockedBy", []))}): '
                                 'nunca "Mesclar?"; diga ao usuário o que a bloqueia e aguarde.')
        elif state == 'merged':
            result['message'] = f'A PR #{current["pr"]} foi mesclada em {current["base"]}: rode `release landed`.'
        elif missing:
            result['message'] = (f'Falta o teste assistido registrado de {", ".join(f"#{n}" for n in missing)}: sem '
                                 '"Mesclar?" até lá.')
        else:
            result['message'] = f'A PR #{current["pr"]} está {state}: aguarde.'
        if since is not None:
            result['changed'] = state != since
            result['exitCode'] = 0 if result['changed'] else UNCHANGED
        return result
    if state != 'merged':
        return {'exitCode': 2, 'state': state, 'pr': current['pr'],
                'message': f'A PR #{current["pr"]} ainda não foi mesclada na base ({state}): nada a trazer.'}
    landing_base = current.get('base') or base
    merge_preconditions(root, landing_base)
    before = rev(root, 'HEAD')
    code, _, err = git(root, 'pull', '--ff-only', remote, landing_base, timeout=FETCH_TIMEOUT)
    if code != 0:
        return {'exitCode': 2, 'reason': 'not_fast_forward', 'pr': current['pr'],
                'message': f'`git pull --ff-only` não avançou a {landing_base} local ({trimmed(err)}): pare e pergunte; '
                           'nunca merge nem reset aqui.'}
    code, _, err = git(root, 'fetch', '--prune', remote, timeout=FETCH_TIMEOUT)
    pruned = code == 0
    issues = current.get('issues', [])
    plan = None
    if issues:
        plan = (planner or default_cleanup_plan)(root, config_path, issues, landing_base)
    stamp = zoned_now().strftime('%Y%m%d-%H%M%S')
    landed = dict(current, landedAt=zoned_now().isoformat(timespec='seconds'), before=before, after=rev(root, 'HEAD'))
    write_json(release_folder(root) / f'landed-{stamp}.json', landed)
    os.replace(path, release_folder(root) / f'current-{stamp}.json')
    verify = ['python', str(HERE / 'closeout.py'), 'verify', '--issues', ','.join(str(n) for n in current.get('closes', []))]
    return {'exitCode': 0, 'pr': current['pr'], 'before': before, 'after': landed['after'], 'pruned': pruned,
            'cleanup': plan, 'commands': (plan or {}).get('commands', []),
            'verify': verify if current.get('closes') else None,
            'message': f'A {landing_base} local avançou por fast-forward até o merge da PR #{current["pr"]}. Rode a '
                       'limpeza de `commands` (sem pergunta, só o que o plano oferece) e depois o `verify`.'}


def default_cleanup_plan(root, config_path, issues, base):
    import cleanup   # noqa: PLC0415  (issue 2 owns it; the plan only reads)
    return cleanup.run('plan', config_path, str(root), issues=','.join(str(n) for n in issues), base=base)


# ---------------------------------------------------------------- command line

def run(operation, root, base='main', remote='origin', config=None, prefix=None, records=None,
        issue=None, mode=None, concurrent=False, argv=None, required=None, release=False, timeout_seconds=None,
        head=None, source=None, free_test_fix=False, dry_run=False, toca=None, release_args=None):
    release_args = release_args or {}
    try:
        if operation == 'suite':
            result = op_suite(root, config, issue, mode, base, concurrent, argv, release, timeout_seconds, source,
                              remote)
        elif operation == 'suite-gate':
            result = op_suite_gate(root, config, issue, required, release, base, head)
        elif operation == 'sync':
            result = op_sync(root, base, remote)
        elif operation == 'bundle':
            result = op_bundle(root, config, base, prefix, records)
        elif operation == 'release-plan':
            result = op_release_plan(root, base, remote, prefix, records, config)
        elif operation == 'merge':
            result = op_merge(root, config, issue, free_test_fix, dry_run, toca)
        elif operation == 'release':
            result = op_release(release_args.get('action'), root, base, remote, config, prefix, records,
                                release_args.get('body'), release_args.get('closes'), release_args.get('record'),
                                release_args.get('pr'), release_args.get('legacy'), release_args.get('answer'),
                                release_args.get('since'))
        else:
            raise Refusal(f'operação desconhecida: {str(operation)[:40]}')
    except (Refusal, OSError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    except Exception as error:  # noqa: BLE001  (a refusal in JSON, never a traceback)
        result = {'ok': False, 'exitCode': 1, 'message': f'homolog parou num {type(error).__name__} inesperado'}
    result['operation'] = str(operation)[:40]
    result.setdefault('ok', result['exitCode'] == 0)
    return result


def build_parser():
    parser = _cli.JsonParser(prog='homolog', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                        allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    merge = sub.add_parser('merge', allow_abbrev=False,
                           help='the issue into the local main: integration branch, gate, walkthroughs, authorize, '
                                'merge --no-ff and bundle (redesign, issue 4)')
    merge.add_argument('--root', help="the project's main worktree (default: the main worktree of the current directory)")
    merge.add_argument('--config', help='.frontlights/config.json (default: the one of the main worktree)')
    merge.add_argument('--issue', help='the issue number (default: the issue of the charter entry of the worktree)')
    merge.add_argument('--free-test-fix', action='store_true',
                       help='a fix of the free test: no gate, the watched run already answered and a previous merge '
                            'that passed authorize')
    merge.add_argument('--dry-run', action='store_true', help='check and say what would run; writes nothing')
    merge.add_argument('--toca', choices=('sim', 'nao', 'não', 'ausente'), help="the plan's `Toca o frontend:`")
    release = sub.add_parser('release', allow_abbrev=False,
                             help='the release by command: plan, body-check, go (argv of the push and of gh pr '
                                  'create; --record --pr <n>), status (the block of the PR) and landed')
    release.add_argument('action', choices=RELEASE_ACTIONS)
    release.add_argument('--root', help="the project's main worktree (default: the main worktree of the current directory)")
    release.add_argument('--base', default='main', help='the base branch (default main)')
    release.add_argument('--remote', default='origin', help='the remote (default origin)')
    release.add_argument('--config', help='.frontlights/config.json (default: the one of the main worktree)')
    release.add_argument('--prefix', help='the prefix of the release branch name (plan, go)')
    release.add_argument('--records', help='the folder that holds .frontlights/authorization*.json (default --root)')
    release.add_argument('--body', help='body-check, go: the body file of the pull request')
    release.add_argument('--closes', help='body-check: the issues of `closes` (default: a fresh plan)')
    release.add_argument('--record', action='store_true', help='go: record the pull request opened (--pr)')
    release.add_argument('--pr', type=int, help='go --record: the number of the pull request')
    release.add_argument('--legacy-branch', dest='legacy', action='store_true',
                         help='go: the old path with a local release branch, only with --answer "Sim"')
    release.add_argument('--answer', help='go --legacy-branch: the literal answer of the question')
    release.add_argument('--since', help='status: exit 0 only when the state is no longer this one (4 otherwise)')
    release.add_argument('--quiet', action='store_true', help='status --since: one line on a change, nothing otherwise')
    for name in ('sync', 'bundle', 'release-plan', 'suite', 'suite-gate'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--root', help="the project's main worktree (default: the main worktree of the current "
                                            "directory; suite and suite-gate: the worktree of the current directory)")
        command.add_argument('--base', default='main',
                             help='the base branch, the local homologation (default main); suite: replaces {base}; '
                                  '--release: the local base whose tip the record covers')
        if name in ('suite', 'suite-gate'):
            command.add_argument('--config', help='.frontlights/config.json (default: the one of the main worktree); '
                                                  'its homolog.suites')
            record = command.add_mutually_exclusive_group()
            record.add_argument('--issue', help='the issue number: the record is .frontlights/issues/<n>/suite.json '
                                                '(default: the issue of the charter entry of the worktree)')
            record.add_argument('--release', action='store_true',
                                help='the whole suite of the release on the local base: .frontlights/release/suite.json')
        if name == 'suite':
            command.add_argument('--mode', required=True, choices=SUITE_MODES, help='the suite to run')
            command.add_argument('--concurrent', action='store_true',
                                 help='the watched run was in progress during this run (recorded)')
            command.add_argument('--argv', help='full only: a JSON list run once instead of homolog.suites.full')
            command.add_argument('--timeout-seconds', help='a positive integer: the timeout of this run, in place of '
                                                           'timeoutSeconds of the config (with or without --argv)')
            command.add_argument('--from', dest='source',
                                 help='with --release: a green whole-suite record of the same commit tree, adopted '
                                      'without running anything')
        elif name == 'suite-gate':
            command.add_argument('--require', choices=('full',), help='only a full suite record counts')
            command.add_argument('--head', help='with --release: the full sha of a tip; judges release/suite-<sha>.json '
                                                'wherever the main worktree stands')
        elif name == 'sync':
            command.add_argument('--remote', default='origin', help='the remote the base is fetched from (default origin)')
        elif name == 'bundle':
            command.add_argument('--config', help='.frontlights/config.json (default: the one of the main worktree); '
                                                  'its homolog.backupDir names the folder')
            command.add_argument('--prefix', help='the work branches to include: every local branch under it alone '
                                                  '(default: branchPrefix of the config and every branch_prefix of the '
                                                  'authorization records)')
            command.add_argument('--records', help='the folder that holds .frontlights/authorization*.json (default --root)')
        else:
            command.add_argument('--remote', default='origin', help='the remote whose base the release goes to (default origin)')
            command.add_argument('--prefix', help='the prefix of the release branch name (default: branchPrefix of '
                                                  'the config, else the branch_prefix of the newest authorization record)')
            command.add_argument('--records', help='the folder that holds .frontlights/authorization*.json (default --root)')
            command.add_argument('--config', help='.frontlights/config.json (default <root>/.frontlights/config.json): '
                                                  'its repository is read on GitHub for `closes`')
    return parser


def resolve_defaults(args):
    """--root, --config and --issue the command line left out, by the rules of `_cli`."""
    main = _cli.main_worktree()
    if args.operation == 'release':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
        return args
    if args.operation == 'merge':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
        args.issue = str(_cli.issue_number(args.issue, _cli.current_tree(), args.root))
        return args
    if args.operation in ('suite', 'suite-gate'):
        args.root = str(_cli.tree_path(args.root))
        args.config = _cli.config_path(args.config, main)
        if not args.release:
            args.issue = str(_cli.issue_number(args.issue, args.root, main))
    else:
        args.root = str(_cli.root_path(args.root))
        if args.operation == 'bundle':
            args.config = _cli.config_path(args.config, args.root)
        elif args.operation == 'release-plan':
            args.config = _cli.config_path(args.config, args.root, required=False)
    return args


def main(argv=None):
    _cli.utf8_streams()
    try:
        args = resolve_defaults(_cli.output_flags(build_parser()).parse_args(argv))
    except _cli.UsageError as error:
        return _cli.print_usage_error(error)
    try:
        result = run(args.operation, args.root, getattr(args, 'base', 'main'), getattr(args, 'remote', 'origin'),
                     getattr(args, 'config', None), getattr(args, 'prefix', None),
                     getattr(args, 'records', None), getattr(args, 'issue', None), getattr(args, 'mode', None),
                     getattr(args, 'concurrent', False), getattr(args, 'argv', None), getattr(args, 'require', None),
                     getattr(args, 'release', False), getattr(args, 'timeout_seconds', None),
                     getattr(args, 'head', None), getattr(args, 'source', None),
                     getattr(args, 'free_test_fix', False), getattr(args, 'dry_run', False), getattr(args, 'toca', None),
                     {key: getattr(args, key, None) for key in ('action', 'body', 'closes', 'record', 'pr', 'legacy',
                                                                 'answer', 'since')})
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    if getattr(args, 'quiet', False) and getattr(args, 'since', None) is not None:
        if result['exitCode'] == 0:   # the monitor wakes the session once, on the change
            print(f'release: PR #{result.get("pr")} {result.get("state")} ({str(result.get("message", ""))[:160]})')
        elif result['exitCode'] != UNCHANGED:
            print(f'release status falhou: {str(result.get("message", ""))[:200]}')
        return int(result['exitCode'])
    _cli.emit(json.dumps(result, indent=2, ensure_ascii=True), args.operation, args.full)
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
