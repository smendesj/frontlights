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
  output     `emit(text, verb, full)`: the JSON a script prints. Past 4 KB or 80 lines it prints a summary instead
             (`summary: true`, the top-level scalars such as `ok`, `exitCode`, `status`, `message`, `question` and
             the paths, `counts` of the top-level lists and objects, `full` and a `hint`) and saves the whole JSON
             in `<tree>/.frontlights/out/<verb>-<YYYYMMDD-HHMMSS>-<pid>.json` (America/Sao_Paulo time, written
             under a temporary name and renamed, the 5 newest of each verb kept). `--full` (or `--json`, added by
             `output_flags`) prints it all; `stamp`, `authorize`, `tick`, `verify` and `checkpoint` are never
             summarized. `out/` lives inside `.frontlights/`, which the project already keeps out of Git, and the
             `archive` of the cleanup leaves it out.

Messages for the user are in Portuguese. Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG = Path('.frontlights') / 'config.json'
CHARTER = Path('.frontlights') / 'authorization.json'
OUT = Path('.frontlights') / 'out'
ZONE = 'America/Sao_Paulo'
SUMMARY_BYTES = 4096     # past this many bytes of output, a summary is printed
SUMMARY_LINES = 80       # or past this many lines
KEEP_PER_VERB = 5        # saved outputs kept per verb in out/
SCALAR_LIMIT = 300       # characters of a top-level string repeated in the summary
NEVER_SUMMARIZED = frozenset({'stamp', 'authorize', 'tick', 'verify', 'checkpoint'})


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


def print_usage_error(failure, exit_code=1, **extra):
    """Print a `UsageError` as the script's JSON and return its exit code; `extra` keys win (serve and checks keep
    the text in `error`, their own convention)."""
    print(json.dumps(failure.result(exit_code, **extra), indent=2, ensure_ascii=False))
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
    raise UsageError(f'a worktree {Path(tree).name} não é de uma issue do charter e a issue não é escolhida: passe '
                     '--issue <n>',
                     hint=f'passe --issue <n> ({where})')


def output_flags(parser):
    """`--full` (alias `--json`) on every leaf parser: the whole JSON, never the summary of `emit`."""
    subs = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
    if not subs:
        parser.add_argument('--full', '--json', dest='full', action='store_true',
                            help='print the whole JSON, never the summary of a long output')
        return parser
    for action in subs:
        for child in set(action.choices.values()):
            delegated = any(a.nargs == argparse.REMAINDER for a in child._actions)   # the other script parses them
            if not delegated and not any(o in ('--full', '--json') for a in child._actions for o in a.option_strings):
                output_flags(child)
    return parser


def sao_paulo_now():
    """Now in America/Sao_Paulo; -03:00 when the machine has no time zone data (no daylight saving since 2019)."""
    try:
        return datetime.now(zoneinfo.ZoneInfo(ZONE))
    except (KeyError, OSError, ValueError):   # ZoneInfoNotFoundError is a KeyError
        return datetime.now(timezone(timedelta(hours=-3)))


def too_long(text):
    return len(text.encode('utf-8')) > SUMMARY_BYTES or text.count('\n') + 1 > SUMMARY_LINES


def save_output(text, verb, tree):
    """Write `text` to `<tree>/.frontlights/out/<verb>-<stamp>-<pid>.json` under a temporary name, rename it into
    place and keep the newest KEEP_PER_VERB of the verb. Returns the path."""
    folder = Path(tree) / OUT
    folder.mkdir(parents=True, exist_ok=True)
    stamp = sao_paulo_now().strftime('%Y%m%d-%H%M%S')
    path = folder / f'{verb}-{stamp}-{os.getpid()}.json'
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)
    mine = sorted((p for p in folder.glob(f'{verb}-*.json') if p.name[len(verb) + 1:len(verb) + 2].isdigit()),
                  key=lambda p: (p.stat().st_mtime, p.name))
    for old in mine[:-KEEP_PER_VERB]:
        if old != path:
            try:
                old.unlink()
            except OSError:
                pass
    return path


def summarize(data, path):
    summary = {'summary': True}
    counts = {}
    for key, value in data.items():
        if isinstance(value, (list, dict)):
            counts[key] = len(value)
        elif isinstance(value, str):
            summary[key] = value if len(value) <= SCALAR_LIMIT else value[:SCALAR_LIMIT] + '…'
        else:
            summary[key] = value
    summary['counts'] = counts
    summary['full'] = str(path)
    summary['hint'] = (f'saída longa resumida; o JSON inteiro está em {path} (leia só a chave que precisa); '
                       '--full imprime tudo')
    return summary


def emit(text, verb, full=False, tree=None):
    """Print `text`, the JSON of a script, or its summary when it is long (see the module's docstring)."""
    if full or verb in NEVER_SUMMARIZED or not too_long(text):
        print(text)
        return
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print(text)
        return
    try:
        path = save_output(text, verb, current_tree() if tree is None else tree)
    except OSError:   # nowhere to save it: the whole output, never a summary pointing at nothing
        print(text)
        return
    print(json.dumps(summarize(data, path), indent=2, ensure_ascii=False))

