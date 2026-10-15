#!/usr/bin/env python3
"""Homologation helper (issue 32): the local base branch (`main`) is the homologation bench of the project. It is
never pushed; the release leaves by a branch of its own and one pull request. This module guards that rule in Git
and keeps the bench current with the remote. Every Git call is a list argv run without a shell, with a timeout and
GIT_TERMINAL_PROMPT=0. Later slices add their operations to `run`; an unknown one is a refusal.

Operations (each prints one JSON object on stdout):
  hook   --check (the default): is the `pre-push` hook that refuses pushing the local base installed, and is it
         ours (its first lines carry MARKER)? --install writes it when missing or already ours (idempotent),
         creates the hooks folder when needed and never overwrites a hook that is not ours: the user merges the
         two by hand. The hook is POSIX sh with the base baked in; it refuses a push when any ref line has the
         local or the remote ref equal to `refs/heads/<base>` (`git push origin main` and `git push origin x:main`
         alike) and lets every other branch through.
  sync   bring `<remote>/<base>` into the local base: the worktree must have the base checked out, be clean
         (untracked files are fine) and have no merge in progress; then `git fetch <remote>` and `git merge
         --no-edit <remote>/<base>`, a fast-forward when possible. A conflict is aborted at once, the worktree is
         checked clean again at the commit it stood on, and the conflicting files are reported for the session to
         ask the user. It never pushes, never touches another branch, never uses --force, reset or rebase.
  bundle write one Git bundle of the local base and of every local branch under `--prefix` (default `claude/`)
         into the folder that `homolog.backupDir` in the config names (`backup_dir` validates the key, and
         `inspect` reuses it). Without the key it says there is no folder and writes nothing. The folder must exist and
         must not sit behind a junction, symbolic link or other reparse point (a OneDrive cloud placeholder is
         storage, not redirection, and is allowed); it is never created. The file is
         `<root folder>-<YYYYmmdd>-<HHMMSS>.bundle` in local time, `-2`, `-3`... when the name is taken: nothing
         is ever overwritten or deleted. `git bundle verify` must accept the file before it is reported.

Exit codes: 0 done; 1 refused or failed (bad usage, a precondition not met, Git failing); 2 a question for the
session (hook missing or foreign on --check; a conflict on sync). A refusal is JSON, never a traceback.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

GIT_TIMEOUT = 45
FETCH_TIMEOUT = 120
BUNDLE_TIMEOUT = 300
STDERR_LIMIT = 200       # characters of Git's own text repeated in a message
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


def plain_name(value, what):
    require(bool(NAME.fullmatch(value or '')) and '..' not in value and not value.endswith('.lock'),
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


def hook_path(root):
    """Where Git looks for the pre-push hook: honours core.hooksPath and linked worktrees."""
    code, out, _ = git(root, 'rev-parse', '--git-path', 'hooks/pre-push')
    require(code == 0 and out.strip(), 'o git não disse onde fica o hook pre-push')
    path = Path(out.strip())
    return (path if path.is_absolute() else Path(root) / path).resolve()


def hook_state(path):
    """(installed, ours, foreign): a file whose first lines carry MARKER is ours; any other file is foreign."""
    if not path.is_file():
        return False, False, False
    with open(path, encoding='utf-8', errors='replace') as handle:
        head = [handle.readline() for _ in range(MARKER_LINES)]
    ours = any(line.strip() == MARKER for line in head)
    return True, ours, not ours


def op_hook(root, base, install):
    worktree(root)
    base = plain_name(base, 'a branch base')
    path = hook_path(root)
    installed, ours, foreign = hook_state(path)
    result = {'installed': installed, 'ours': ours, 'foreign': foreign, 'path': str(path), 'base': base,
              'script': hook_script(base)}
    if foreign:
        result['exitCode'] = 1 if install else 2
        result['message'] = (f'Há um hook pre-push em {path} que não é do Frontlights; ele nunca é sobrescrito'
                             + (', e nada foi escrito' if install else '') + ': junte os dois à mão.')
    elif install:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(result['script'])
        os.chmod(path, 0o755)
        result.update(installed=True, ours=True, exitCode=0,
                      message=f'Hook pre-push do Frontlights instalado em {path}: a {base} local nunca é enviada.')
    elif installed:
        result.update(exitCode=0, message=f'O hook pre-push do Frontlights está instalado em {path}.')
    else:
        result.update(exitCode=2, message=f'Não há hook pre-push em {path}; `homolog hook --install` o instala.')
    if install:
        result['written'] = not foreign
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


def branch_prefix(value):
    require(bool(NAME.fullmatch(value or '')) and '..' not in value and value.endswith('/'),
            'o prefixo das branches precisa ser um nome simples terminado em `/`, como claude/')
    return value


def bundle_refs(root, base, prefix):
    """`refs/heads/<base>` and every local branch under `prefix`, as full ref names (never ambiguous with a tag)."""
    require(rev(root, f'refs/heads/{base}'), f'a branch base `{base}` não existe neste repositório')
    code, out, err = git(root, 'for-each-ref', '--format=%(refname)', f'refs/heads/{prefix}')
    require(code == 0, f'`git for-each-ref` falhou: {trimmed(err)}')
    branches = [line.strip() for line in out.splitlines() if line.strip()]
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


def op_bundle(root, config_path, base, prefix):
    worktree(root)
    base = plain_name(base, 'a branch base')
    prefix = branch_prefix(prefix)
    folder = backup_dir(load_config(config_path))
    if folder is None:
        return {'configured': False, 'written': False, 'exitCode': 1,
                'message': 'não há pasta de backup configurada (homolog.backupDir); nada foi gravado'}
    result = {'configured': True, 'written': False}
    try:
        check_backup_folder(folder)
        path, heads = write_bundle(root, folder, bundle_refs(root, base, prefix))
    except Refusal as error:
        result.update(exitCode=1, message=str(error))
        return result
    result.update(written=True, verified=True, path=str(path), refs=heads, bytes=path.stat().st_size, exitCode=0,
                  message=f'Bundle {path.name} gravado em {folder} com {len(heads)} ref(s): {", ".join(heads)}.')
    return result


# ---------------------------------------------------------------- command line

def run(operation, root, base='main', remote='origin', install=False, config=None, prefix='claude/'):
    try:
        if operation == 'hook':
            result = op_hook(root, base, install)
        elif operation == 'sync':
            result = op_sync(root, base, remote)
        elif operation == 'bundle':
            result = op_bundle(root, config, base, prefix)
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
    for name in ('hook', 'sync', 'bundle'):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument('--root', required=True, help="the project's main worktree")
        command.add_argument('--base', default='main', help='the base branch, the local homologation (default main)')
        if name == 'hook':
            mode = command.add_mutually_exclusive_group()
            mode.add_argument('--check', action='store_true', help='report the hook without writing (the default)')
            mode.add_argument('--install', action='store_true', help='write the hook when missing or already ours')
        elif name == 'sync':
            command.add_argument('--remote', default='origin', help='the remote the base is fetched from (default origin)')
        else:
            command.add_argument('--config', required=True, help='.frontlights/config.json; its homolog.backupDir names the folder')
            command.add_argument('--prefix', default='claude/', help='the work branches to include: every local branch under it (default claude/)')
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        result = run(args.operation, args.root, args.base, getattr(args, 'remote', 'origin'),
                     getattr(args, 'install', False), getattr(args, 'config', None), getattr(args, 'prefix', 'claude/'))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'message': str(error)}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
