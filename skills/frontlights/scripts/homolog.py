#!/usr/bin/env python3
"""Homologation helper (issue 32): the local base branch (`main`) is the homologation bench of the project. It is
never pushed; the release leaves by a branch of its own and one pull request. This module guards that rule in Git
and keeps the bench current with the remote. Every Git call is a list argv run without a shell, with a timeout and
GIT_TERMINAL_PROMPT=0. `run` knows four operations, `hook`, `sync`, `bundle` and `release-plan`; an unknown one is
a refusal.

Operations (each prints one JSON object on stdout):
  hook   --check (the default): is the `pre-push` hook that refuses pushing the local base installed, is it ours
         (its first lines carry MARKER) and is it current (byte for byte the script for `--base`, line endings
         aside)? A hook that is ours but not current (another base baked in, or edited) is a question (exit 2):
         `--install` rewrites it. --install writes the hook when missing or already ours (idempotent), creates
         the hooks folder when needed and never overwrites a hook that is not ours: the user merges the two by
         hand. The hook must live inside the common Git dir of the repository: when `core.hooksPath` points
         elsewhere, `--check` reports `outsideRepository` (exit 2) and `--install` refuses (exit 1); nothing is
         written outside the repository. The hook is POSIX sh with the base baked in; it refuses a push when any
         ref line has the local or the remote ref equal to `refs/heads/<base>` (`git push origin main` and
         `git push origin x:main` alike) and lets every other branch through.
  sync   bring `<remote>/<base>` into the local base: the worktree must have the base checked out, be clean
         (untracked files are fine) and have no merge in progress; then `git fetch <remote>` and `git merge
         --no-edit <remote>/<base>`, a fast-forward when possible. A conflict is aborted at once, the worktree is
         checked clean again at the commit it stood on, and the conflicting files are reported for the session to
         ask the user. It never pushes, never touches another branch, never uses --force, reset or rebase.
  bundle write one Git bundle of the local base and of every local branch under the work prefixes: `--prefix` alone
         when given; otherwise every `branch_prefix` of the valid `.frontlights/authorization*.json` records under
         `--records` (default the root; a record without the key counts as `claude/`), and `claude/` when there is
         no valid record (issue 44); `prefixes` and `prefixSource` (`argument`, `records` or `default`) say which, and
         `skipped` counts the records left out;
         into the folder that `homolog.backupDir` in the config names (`backup_dir` validates the key, and
         `inspect` reuses it). Without the key it says there is no folder and writes nothing. The folder must exist and
         must not sit behind a junction, symbolic link or other reparse point (a OneDrive cloud placeholder is
         storage, not redirection, and is allowed); it is never created. The file is
         `<root folder>-<YYYYmmdd>-<HHMMSS>.bundle` in local time, `-2`, `-3`... when the name is taken: nothing
         is ever overwritten or deleted. `git bundle verify` must accept the file before it is reported.
  release-plan  what the release would carry: the issues whose branch (the `worktrees` entries without `slice` of
         every `.frontlights/authorization*.json` under `--records`, default the root) is in the local base and
         not yet in `<remote>/<base>`, how many commits the local base is ahead of and behind the remote one, and
         the name of the release branch, `<prefix>release-<YYYY-MM-DD>` (`--prefix` alone when given; otherwise the
         `branch_prefix` of the record with the newest `issued_at`, a record without a valid instant ranking last, and
         `claude/` without a valid record, issue 44; `prefix` and `prefixSource` say which; the date in America/Sao_Paulo, the
         machine's local date when that zone is unavailable), `-2`, `-3`... past a local branch, or a
         remote-tracking branch of `--remote`, that already has the name. `ready` is true (exit 0) when the local
         base is ahead, not behind, and at least one issue is in
         the release; otherwise exit 2 says what is missing (behind: sync first; nothing ahead; commits ahead with
         no issue branch mapped). It only reads Git and the records: it never fetches, never creates the branch
         and never pushes. Without `<remote>/<base>` it refuses (exit 1) and asks for `homolog sync` first.

Exit codes: 0 done; 1 refused or failed (bad usage, a precondition not met, Git failing); 2 a question for the
session (hook missing or foreign on --check; a conflict on sync; a release that is not ready). A refusal is JSON,
never a traceback.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import zoneinfo
from datetime import datetime, timezone
from pathlib import Path

GIT_TIMEOUT = 45
FETCH_TIMEOUT = 120
BUNDLE_TIMEOUT = 300
STDERR_LIMIT = 200       # characters of Git's own text repeated in a message
RECORD_LIMIT = 200       # authorization records release-plan and bundle read
DEFAULT_PREFIX = 'claude/'   # the branch prefix when neither --prefix nor a record names one
RECORD_BYTES = 2 * 1024 * 1024                  # the largest record it reads
RELEASE_ZONE = 'America/Sao_Paulo'              # the date in the name of the release branch
BACKUP_KEYS = {'backupDir'}                     # the only key of the `homolog` block of the config
CONTROL = re.compile(r'[\x00-\x1f\x7f]')
REPARSE_POINT = 0x400                           # FILE_ATTRIBUTE_REPARSE_POINT
MARKER_LINES = 3         # the marker sits among the first lines of the hook
MARKER = '# frontlights pre-push hook v1 (homolog hook)'
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]*')   # a plain branch or remote name: safe inside the hook's quotes
OID = re.compile(r'[0-9a-f]{40,64}')
HOOK = '''#!/bin/sh
{marker}
# The local {base} is the homologation bench of the project: it is never pushed. The release leaves by a branch
# of its own and one pull request. Installed by `frontlights.py homolog hook --install`; `--check` verifies it.
base="refs/heads/{base}"
while read -r local_ref local_sha remote_ref remote_sha; do
  if [ "$local_ref" = "$base" ] || [ "$remote_ref" = "$base" ]; then
    echo "frontlights: a {base} local é a homologação e nunca é enviada; a release sobe por uma branch própria e uma PR única." >&2
    exit 1
  fi
done
exit 0
'''


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


def status_lines(root):
    """Tracked files with changes (staged or not); untracked files are not counted."""
    code, out, _ = git(root, 'status', '--porcelain', '--untracked-files=no')
    require(code == 0, 'o git não leu o estado da worktree')
    return [line for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------- hook

def hook_script(base):
    return HOOK.format(marker=MARKER, base=base)


def git_path(root, *args, what):
    """A path Git reports (`rev-parse --git-path ...`, `--git-common-dir`), absolute against `root` and resolved."""
    code, out, _ = git(root, 'rev-parse', *args)
    require(code == 0 and out.strip(), f'o git não disse onde fica {what}')
    path = Path(out.strip())
    return (path if path.is_absolute() else Path(root) / path).resolve()


def hook_path(root):
    """Where Git looks for the pre-push hook: honours core.hooksPath and linked worktrees."""
    return git_path(root, '--git-path', 'hooks/pre-push', what='o hook pre-push')


def common_dir(root):
    """The common Git dir of the repository (`.git` of the main worktree), shared by every linked worktree."""
    return git_path(root, '--git-common-dir', what='o diretório Git do repositório')


def inside(path, folder):
    """True when `path` is `folder` or below it; both already resolved, compared case-insensitively on Windows."""
    path, folder = os.path.normcase(str(path)), os.path.normcase(str(folder))
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def hook_state(path, expected):
    """(installed, ours, foreign, current): a file whose first lines carry MARKER is ours; any other file is
    foreign; ours and equal to `expected` (CRLF read as LF) is current. A hook installed for another base, or
    edited after the install, is ours but not current."""
    if not path.is_file():
        return False, False, False, False
    with open(path, encoding='utf-8', errors='replace', newline='') as handle:
        content = handle.read().replace('\r\n', '\n')
    ours = any(line.strip() == MARKER for line in content.split('\n', MARKER_LINES)[:MARKER_LINES])
    return True, ours, not ours, ours and content == expected


def op_hook(root, base, install):
    worktree(root)
    base = plain_name(base, 'a branch base')
    path = hook_path(root)
    outside = not inside(path, common_dir(root))
    script = hook_script(base)
    installed, ours, foreign, current = hook_state(path, script)
    result = {'installed': installed, 'ours': ours, 'foreign': foreign, 'current': current, 'path': str(path),
              'base': base, 'script': script, 'outsideRepository': outside}
    if outside and current and not install:
        # The user installed our hook by hand in a hooks folder outside the repository: it is there and current,
        # which is all the check asks; the skill still never writes there.
        result.update(exitCode=0, message=f'O hook pre-push do Frontlights está instalado em {path} (pasta de '
                                          'core.hooksPath fora do diretório Git; a skill não escreve ali).')
    elif outside:
        # core.hooksPath (often a global one) sends the hooks to a folder outside the repository: the skill never
        # writes there, in either mode.
        result['exitCode'] = 1 if install else 2
        result['message'] = (f'A pasta de hooks ({path.parent}) fica fora do diretório Git do repositório por '
                             'core.hooksPath; a skill não escreve nada ali' + (', e nada foi escrito' if install else '')
                             + '. Ajuste core.hooksPath ou instale o hook à mão.')
    elif foreign:
        result['exitCode'] = 1 if install else 2
        result['message'] = (f'Há um hook pre-push em {path} que não é do Frontlights; ele nunca é sobrescrito'
                             + (', e nada foi escrito' if install else '') + ': junte os dois à mão.')
    elif install:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(script)
        os.chmod(path, 0o755)
        result.update(installed=True, ours=True, current=True, exitCode=0,
                      message=f'Hook pre-push do Frontlights instalado em {path}: a {base} local nunca é enviada.')
    elif current:
        result.update(exitCode=0, message=f'O hook pre-push do Frontlights está instalado em {path}.')
    elif installed:
        result.update(exitCode=2, message=f'O hook pre-push em {path} é do Frontlights, mas difere do script esperado '
                                          f'para a {base} (outra branch base, ou editado); `homolog hook --install` '
                                          'o reescreve.')
    else:
        result.update(exitCode=2, message=f'Não há hook pre-push em {path}; `homolog hook --install` o instala.')
    if install:
        result['written'] = not (outside or foreign)
    return result


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

    `homolog` absent or null is None; otherwise it must be an object whose only key is `backupDir`, so a typo never
    passes in silence. `backupDir` absent or null is None; otherwise a non-empty string with an absolute path (a
    drive or UNC root on Windows), without `..` segments, not starting with `~`, without `{placeholder}` braces,
    NUL or control characters. The folder need not exist: `inspect` is read-only and the folder may be a synced
    cloud folder; `bundle` checks it at run time. A refusal never repeats the value.
    """
    block = config.get('homolog')
    if block is None:
        return None
    require(isinstance(block, dict), 'homolog precisa ser um objeto com a chave backupDir')
    unknown = [str(key)[:40] for key in block if key not in BACKUP_KEYS]
    if unknown:
        raise Refusal(f'homolog tem a chave desconhecida `{unknown[0]}`; a única chave aceita é backupDir')
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
    """0 for an ordinary entry, the reparse tag otherwise; -1 when unreadable (as roadmap_sync does for scrumRoot)."""
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
    require(is_prefix(value or ''), 'o prefixo das branches precisa ser um nome simples terminado em `/`, como claude/')
    return value


def bundle_refs(root, base, prefixes):
    """`refs/heads/<base>` and every local branch under one of `prefixes`, as full ref names (never ambiguous with a
    tag), each once."""
    require(rev(root, f'refs/heads/{base}'), f'a branch base `{base}` não existe neste repositório')
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


def bundle_prefixes(prefix, records):
    """(prefixes, source, skipped): `[prefix]` and `argument` when one is given; otherwise the sorted union of the
    `branch_prefix` of the valid records and `records`, or `[DEFAULT_PREFIX]` and `default` without one; `skipped`
    counts the records left out (issue 44)."""
    if prefix is not None:
        return [branch_prefix(prefix)], 'argument', 0
    found, skipped = record_prefixes(records)
    if found:
        return sorted({entry['prefix'] for entry in found}), 'records', skipped
    return [DEFAULT_PREFIX], 'default', skipped


def op_bundle(root, config_path, base, prefix, records=None):
    worktree(root)
    base = plain_name(base, 'a branch base')
    prefixes, source, skipped = bundle_prefixes(prefix, root if records is None else records)
    folder = backup_dir(load_config(config_path))
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
    """([{'file', 'prefix', 'issuedAt'}], skipped) for every record under `folder` whose `branch_prefix` (absent:
    DEFAULT_PREFIX) is a valid prefix; an unreadable record, a bad prefix, and every record past RECORD_LIMIT, is
    skipped and counted (issue 44)."""
    files = record_files(folder)
    skipped = max(0, len(files) - RECORD_LIMIT)
    found = []
    for file in files[:RECORD_LIMIT]:
        data = read_record(file)
        prefix = data.get('branch_prefix', DEFAULT_PREFIX) if data is not None else None
        if data is None or not is_prefix(prefix):
            skipped += 1
            continue
        found.append({'file': file.name, 'prefix': prefix, 'issuedAt': data.get('issued_at')})
    return found, skipped


def issue_branches(folder):
    """({issue number: branch}, skipped) from the `worktrees` entries without `slice` of every
    `.frontlights/authorization*.json` under `folder`. An entry counts when its `issue` is a positive integer and its
    `branch` is a plain name under the record's `branch_prefix` (default `claude/`); a later record wins for the same
    issue. A slice entry is ignored in silence; a malformed entry, record or prefix, and every record past
    RECORD_LIMIT, is skipped and counted."""
    files = record_files(folder)
    skipped = max(0, len(files) - RECORD_LIMIT)
    mapping = {}
    for file in files[:RECORD_LIMIT]:
        data = read_record(file)
        prefix = data.get('branch_prefix', DEFAULT_PREFIX) if data is not None else None
        entries = data.get('worktrees', []) if data is not None else None
        if data is None or not is_prefix(prefix) or not isinstance(entries, list):
            skipped += 1
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get('slice'), str) and entry['slice'].strip():
                continue   # a slice is delivered to the branch of its issue, never to the base by itself
            number = entry.get('issue') if isinstance(entry, dict) else None
            branch = entry.get('branch') if isinstance(entry, dict) else None
            if type(number) is not int or number <= 0 or not is_plain(branch) or not branch.startswith(prefix):
                skipped += 1
                continue
            mapping[number] = branch
    return mapping, skipped


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
    """`<prefix>release-<date>`, then `-2`, `-3`... past every local branch, and every remote-tracking branch of
    `remote`, that already carries the name."""
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


def release_prefix(prefix, records):
    """(prefix, source): `prefix` and `argument` when one is given; otherwise the `branch_prefix` of the record with
    the newest `issued_at` (records without a valid instant rank last, then by file name) and `records`, or
    DEFAULT_PREFIX and `default` without a valid record (issue 44)."""
    if prefix is not None:
        return branch_prefix(prefix), 'argument'
    found, _ = record_prefixes(records)
    if not found:
        return DEFAULT_PREFIX, 'default'

    def rank(entry):
        moment = instant(entry['issuedAt'])
        return (moment is not None, moment if moment is not None else 0.0, entry['file'])

    return max(found, key=rank)['prefix'], 'records'


def op_release_plan(root, base, remote, prefix, records):
    worktree(root)
    base = plain_name(base, 'a branch base')
    remote = plain_name(remote, 'o remoto')
    prefix, source = release_prefix(prefix, root if records is None else records)
    local_ref, remote_ref = f'refs/heads/{base}', f'refs/remotes/{remote}/{base}'
    local = rev(root, local_ref)
    require(local, f'a branch base `{base}` não existe neste repositório')
    remote_tip = rev(root, remote_ref)
    mapping, skipped = issue_branches(root if records is None else records)
    issues = []
    for number in sorted(mapping):
        tip = rev(root, f'refs/heads/{mapping[number]}')
        issues.append({'issue': number, 'branch': mapping[number], 'tip': tip, 'present': tip is not None,
                       'inLocalMain': ancestry(root, tip, local_ref),
                       'inRemoteMain': ancestry(root, tip, remote_ref if remote_tip else None)})
    release = [i['issue'] for i in issues if i['present'] and i['inLocalMain'] is True and i['inRemoteMain'] is False]
    ahead, behind = counts(root, local_ref, remote_ref) if remote_tip else (None, None)
    name = release_name(root, prefix, remote)
    result = {'base': base, 'remote': remote, 'localMain': local, 'remoteMain': remote_tip, 'ahead': ahead,
              'behind': behind, 'issues': issues, 'release': release, 'releaseBranch': name, 'prefix': prefix,
              'prefixSource': source, 'skipped': skipped, 'ready': False}
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
    elif not release:
        result.update(exitCode=2, message=f'A {base} local tem {ahead} commit(s) além de {remote}/{base}, mas nenhuma '
                                          'branch de issue das autorizações está neles; confira os registros em '
                                          '.frontlights/ ou aponte --records para a pasta certa.')
    else:
        listed = ', '.join(f'#{number}' for number in release)
        result.update(ready=True, exitCode=0,
                      message=f'Release pronta: {len(release)} issue(s) ({listed}) em {ahead} commit(s) da {base} local '
                              f'ainda fora de {remote}/{base}; a branch da release é {name}.')
    return result


# ---------------------------------------------------------------- command line

def run(operation, root, base='main', remote='origin', install=False, config=None, prefix=None, records=None):
    try:
        if operation == 'hook':
            result = op_hook(root, base, install)
        elif operation == 'sync':
            result = op_sync(root, base, remote)
        elif operation == 'bundle':
            result = op_bundle(root, config, base, prefix, records)
        elif operation == 'release-plan':
            result = op_release_plan(root, base, remote, prefix, records)
        else:
            raise Refusal(f'operação desconhecida: {str(operation)[:40]}')
    except (Refusal, OSError) as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    except Exception as error:  # noqa: BLE001  (a refusal in JSON, never a traceback)
        result = {'ok': False, 'exitCode': 1, 'message': f'homolog parou num {type(error).__name__} inesperado'}
    result['operation'] = str(operation)[:40]
    result.setdefault('ok', result['exitCode'] == 0)
    return result


class JsonParser(argparse.ArgumentParser):
    """A usage mistake is a JSON refusal like any other."""

    def error(self, message):
        raise Refusal(f'uso: {message}')


def build_parser():
    parser = JsonParser(prog='homolog', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                        allow_abbrev=False)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('hook', 'sync', 'bundle', 'release-plan'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--root', required=True, help="the project's main worktree")
        command.add_argument('--base', default='main', help='the base branch, the local homologation (default main)')
        if name == 'hook':
            mode = command.add_mutually_exclusive_group()
            mode.add_argument('--check', action='store_true', help='report the hook without writing (the default)')
            mode.add_argument('--install', action='store_true', help='write the hook when missing or already ours')
        elif name == 'sync':
            command.add_argument('--remote', default='origin', help='the remote the base is fetched from (default origin)')
        elif name == 'bundle':
            command.add_argument('--config', required=True, help='.frontlights/config.json; its homolog.backupDir names the folder')
            command.add_argument('--prefix', help='the work branches to include: every local branch under it alone '
                                                  '(default: every branch_prefix of the authorization records, claude/ '
                                                  'without one)')
            command.add_argument('--records', help='the folder that holds .frontlights/authorization*.json (default --root)')
        else:
            command.add_argument('--remote', default='origin', help='the remote whose base the release goes to (default origin)')
            command.add_argument('--prefix', help='the prefix of the release branch name (default: the branch_prefix '
                                                  'of the newest authorization record, claude/ without one)')
            command.add_argument('--records', help='the folder that holds .frontlights/authorization*.json (default --root)')
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        result = run(args.operation, args.root, args.base, getattr(args, 'remote', 'origin'),
                     getattr(args, 'install', False), getattr(args, 'config', None), getattr(args, 'prefix', None),
                     getattr(args, 'records', None))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
