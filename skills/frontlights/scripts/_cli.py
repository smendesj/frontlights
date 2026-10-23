"""The command line every Frontlights script shares (redesign, issue 1).

Imported by every script; there is no dispatcher. What it gives them:

  defaults   `--root` is the main worktree (config and records), from `git rev-parse --git-common-dir`; `--tree` is
             the worktree of the current directory (where checks, suite, stamp, checkpoint, evidence and
             browser-gate act); `--config` is `<root>/.frontlights/config.json`; `--issue` comes only from the entry
             of the charter (`<root>/.frontlights/authorization.json`, `worktrees`) whose path is the tree, else it
             is refused with a `hint` that lists the issues of the charter: it never chooses one. Outside Git both
             root and tree are the folder itself.
  usage      `JsonParser`: a usage mistake raises `UsageError` (message and `hint`), which the script prints as one
             JSON object (`ok: false`, `error: "usage"`, `message`, `hint`), never argparse's text and exit 2 alone.
  streams    `utf8_streams()`: stdout and stderr in UTF-8, called first by every `main`.

Messages for the user are in Portuguese. Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path('.frontlights') / 'config.json'
CHARTER = Path('.frontlights') / 'authorization.json'


class UsageError(Exception):
    """A command line the script cannot run: `message` and the `hint` that says what to pass instead."""

    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint

    def result(self, exit_code=1, **extra):
        result = {'ok': False, 'exitCode': exit_code, 'error': 'usage', 'message': str(self), 'hint': self.hint}
        result.update(extra)
        return result


class JsonParser(argparse.ArgumentParser):
    """The one parser of the scripts: a usage mistake is a `UsageError`, printed as JSON by the script."""

    def error(self, message):
        raise UsageError(f'uso inválido: {message}', hint=f'veja `{self.prog} --help`')


def utf8_streams():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


def print_usage_error(error, exit_code=1, **extra):
    """Print a `UsageError` as the script's JSON and return its exit code."""
    print(json.dumps(error.result(exit_code, **extra), indent=2, ensure_ascii=False))
    return exit_code


def git_line(cwd, *args):
    try:
        done = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = done.stdout.strip()
    return out if done.returncode == 0 and out else None


def current_tree(cwd='.'):
    """The worktree of `cwd` (its top level); outside Git, `cwd` itself."""
    cwd = Path(cwd).resolve()
    top = git_line(cwd, 'rev-parse', '--show-toplevel')
    return Path(top).resolve() if top else cwd


def main_worktree(cwd='.'):
    """The main worktree of the repository of `cwd`, where config and records live; outside Git, `cwd` itself."""
    cwd = Path(cwd).resolve()
    common = git_line(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if common and Path(common).name == '.git':
        return Path(common).parent.resolve()
    return current_tree(cwd)


def root_path(value, cwd='.'):
    return Path(value) if value else main_worktree(cwd)


def tree_path(value, cwd='.'):
    return Path(value) if value else current_tree(cwd)


def config_path(value, root, required=True):
    """`value` when given; else `<root>/.frontlights/config.json` when it exists; else a refusal (or None when the
    config is optional)."""
    if value:
        return value
    path = Path(root) / CONFIG
    if path.is_file():
        return str(path)
    if not required:
        return None
    raise UsageError(f'sem --config e sem {CONFIG.as_posix()} na worktree principal ({Path(root).name})',
                     hint='rode dentro do projeto de destino ou passe --config <caminho do config.json>')


def same_path(a, b):
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except (OSError, ValueError):
        return False


def read_charter(root):
    try:
        data = json.loads((Path(root) / CHARTER).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def issue_number(value, tree, root):
    """`value` as an integer when given; else the issue of the charter entry whose path is `tree`. Anything else is
    refused with the issues of the charter in the `hint`: the issue is never chosen."""
    if value is not None and str(value).strip():
        text = str(value).strip().lstrip('#')
        if not text.isdigit() or int(text) < 1:
            raise UsageError(f'--issue precisa ser um número de issue, não {str(value)[:40]!r}',
                             hint='passe --issue <n>, como --issue 12')
        return int(text)
    charter = read_charter(root)
    entries = charter.get('worktrees') if charter else None
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get('path'), str) and same_path(entry['path'], tree):
            if type(entry.get('issue')) is int and entry['issue'] > 0:
                return entry['issue']
            break
    ids = charter.get('issue_ids') if charter else None
    listed = ', '.join(str(n) for n in ids if type(n) is int) if isinstance(ids, list) else ''
    where = f'issues do charter: {listed}' if listed else 'nenhum charter com issues na worktree principal'
    raise UsageError(f'a worktree {Path(tree).name} não é de uma issue do charter; a issue não é escolhida',
                     hint=f'passe --issue <n> ({where})')
