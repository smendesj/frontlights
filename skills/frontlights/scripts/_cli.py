"""The command line every Frontlights script shares (redesign, issue 1).

Imported by every script; there is no dispatcher. What it gives them:

  defaults   `--root` is the main worktree (config and records), from `git rev-parse --git-common-dir`; `--tree` is
             the worktree of the current directory (where checks, suite, stamp, checkpoint, evidence and
             browser-gate act); `--config` is `<root>/.frontlights/config.json`; `--issue` comes only from the entry
             of a charter (`charter_files`, `worktrees`) whose path is the tree, else it is refused with a `hint`
             that lists the issues of the charters: it never chooses one. Outside Git both root and tree are the
             folder itself.
  charters   one charter per issue, `<root>/.frontlights/authorization/<n>.json` (`direct-<slug>.json` for work
             without an issue), so writing one never erases another. The legacy single `authorization.json` is
             still read, never written: for an issue without a file of its own, the legacy record narrowed to it
             (`narrow`) is its charter, and the first write of that issue moves it to its own file.
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
CHARTER = Path('.frontlights') / 'authorization.json'   # the legacy single charter: read, never written
CHARTERS = Path('.frontlights') / 'authorization'       # one charter per issue (charter_name)
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


def git_environment(base=None):
    """The environment of every Git subprocess of the scripts: `base` (default: this process's environment) with
    GIT_TERMINAL_PROMPT=0 and GCM_INTERACTIVE=never, so neither Git nor the Git Credential Manager ever waits on a
    prompt or an account picker that nobody will answer."""
    return {**(os.environ if base is None else base), 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}


def git_line(cwd, *args):
    try:
        done = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL, env=git_environment())
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


def charter_name(key):
    """The file name of the charter of an issue (`12.json`) or of a work without an issue (`direct-<slug>.json`)."""
    key = str(key)
    return f'{int(key)}.json' if key.isdigit() else f'direct-{key}.json'


def charter_path(root, key):
    return Path(root) / CHARTERS / charter_name(key)


def charter_files(root):
    """The active charters: every `.frontlights/authorization/*.json` by name, then the legacy `authorization.json`."""
    try:
        files = sorted(p for p in (Path(root) / CHARTERS).glob('*.json') if p.is_file())
    except OSError:
        files = []
    legacy = Path(root) / CHARTER
    return files + ([legacy] if legacy.is_file() else [])


def record_files(root):
    """Every authorization record: `.frontlights/authorization*.json` by name (the legacy charter and the kept
    copies), then the per-issue charters by name, so the current charter of an issue is read last."""
    try:
        kept = sorted(p for p in (Path(root) / '.frontlights').glob('authorization*.json') if p.is_file())
    except OSError:
        kept = []
    return kept + [p for p in charter_files(root) if p.parent.name == CHARTERS.name]


def read_record(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def charter_keys(record):
    """The ids a charter names: its issues as text, then its works without an issue."""
    issues = record.get('issue_ids') if isinstance(record.get('issue_ids'), list) else []
    directs = record.get('direct_ids') if isinstance(record.get('direct_ids'), list) else []
    return ([str(n) for n in issues if type(n) is int and n > 0]
            + [d for d in directs if isinstance(d, str) and d])


def narrow(record, key):
    """The record of a (legacy, shared) charter restricted to one issue or work: its id, ownership and worktrees."""
    key = str(key)
    issue = key.isdigit()
    field = 'issue' if issue else 'direct'
    value = int(key) if issue else key
    ownership = record.get('ownership') if isinstance(record.get('ownership'), dict) else {}
    entries = record.get('worktrees') if isinstance(record.get('worktrees'), list) else []
    return dict(record, issue_ids=[value] if issue else [], direct_ids=[] if issue else [value],
                ownership={key: list(ownership.get(key) or [])} if key in ownership else {},
                worktrees=[e for e in entries if isinstance(e, dict) and e.get(field) == value])


def read_charters(root):
    """[(path, record)] of every readable active charter (`charter_files`), the legacy one last."""
    found = []
    for path in charter_files(root):
        data = read_record(path)
        if data is not None:
            found.append((path, data))
    return found


def read_charter(root, key):
    """The charter of issue (or work) `key`: its own file, else the legacy `authorization.json` narrowed to it when
    it names it; None when neither does."""
    own = read_record(charter_path(root, key))
    if own is not None:
        return own
    legacy = read_record(Path(root) / CHARTER)
    if legacy is not None and str(key).lstrip('#') in charter_keys(legacy):
        return narrow(legacy, str(key).lstrip('#'))
    return None


def issue_number(value, tree, root):
    """`value` as an integer when given; else the issue of the charter entry whose path is `tree`. Anything else is
    refused with the issues of the charter in the `hint`: the issue is never chosen."""
    if value is not None and str(value).strip():
        text = str(value).strip().lstrip('#')
        if not text.isdigit() or int(text) < 1:
            raise UsageError(f'--issue precisa ser um número de issue, não {str(value)[:40]!r}',
                             hint='passe --issue <n>, como --issue 12')
        return int(text)
    charters = read_charters(root)
    for _, charter in charters:
        entries = charter.get('worktrees')
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get('path'), str) and same_path(entry['path'], tree):
                if type(entry.get('issue')) is int and entry['issue'] > 0:
                    return entry['issue']
                break
    ids = sorted({int(k) for _, charter in charters for k in charter_keys(charter) if k.isdigit()})
    listed = ', '.join(str(n) for n in ids)
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


# ---------------------------------------------------------------- branch prefix and GitHub account

LEGACY_PREFIX = 'claude/'   # the one place it is named: what a record without `branch_prefix` meant before


def config_prefix_entry(config):
    """(prefix, source, warning) of a config (a dict, or the path of the file): `branchPrefix` with source `config`,
    else the older snake_case `branch_prefix` with source `config:branch_prefix`; (None, None, None) without either.
    `warning` (`branch_prefix_conflict`) only when both are set and differ: `branchPrefix` wins."""
    if not isinstance(config, dict):
        try:
            config = json.loads(Path(config).read_text(encoding='utf-8-sig')) if config else None
        except (OSError, ValueError):
            config = None
    if not isinstance(config, dict):
        return None, None, None
    camel, snake = (config.get(key) for key in ('branchPrefix', 'branch_prefix'))
    camel = camel if isinstance(camel, str) and camel.strip() else None
    snake = snake if isinstance(snake, str) and snake.strip() else None
    if camel:
        warning = (f'branch_prefix_conflict: o config tem branchPrefix {camel} e branch_prefix {snake}; vale '
                   f'branchPrefix, apague a outra chave' if snake and snake != camel else None)
        return camel, 'config', warning
    return (snake, 'config:branch_prefix', None) if snake else (None, None, None)


def config_prefix(config):
    """The prefix of a config by `config_prefix_entry`, or None."""
    return config_prefix_entry(config)[0]


def branch_prefix(explicit=None, config=None, record=None):
    """(prefix, prefixSource) by the chain `--prefix` > the prefix of the config (`config_prefix_entry`) > the
    `branch_prefix` of the authorization record: `argument`, `config`, `config:branch_prefix`, `authorization`, or
    `legacy` for a record without the key (read as the prefix it meant then); (None, None) when none names one."""
    if isinstance(explicit, str) and explicit.strip():
        return explicit, 'argument'
    named, source, _ = config_prefix_entry(config)
    if named:
        return named, source
    if isinstance(record, dict):
        if 'branch_prefix' in record:
            return record['branch_prefix'], 'authorization'
        return LEGACY_PREFIX, 'legacy'
    return None, None


class AccountMismatch(Exception):
    """The gh login or the repository of the current directory is not the one a write needs."""

    def __init__(self, reason, message, login=None, expected=None):
        super().__init__(message)
        self.reason, self.login, self.expected = reason, login, expected

    def result(self, **extra):
        target = self.expected or '<a conta com escrita no repositório>'
        result = {'ok': False, 'exitCode': 1, 'reason': self.reason, 'message': str(self), 'login': self.login,
                  'question': f'Trocar para {target} com `gh auth switch --user {target}` e repetir?',
                  'options': [f'Trocar para {target} com `gh auth switch --user {target}` e repetir', 'Parar'],
                  'hint': 'o gh auth switch é do usuário; o script nunca troca a conta'}
        result.update(extra)
        return result


def gh_json(argv):
    """`gh <argv>` without a shell, its stdout read as JSON; None when gh fails or answers something else."""
    try:
        done = subprocess.run(['gh', *argv], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return json.loads(done.stdout) if done.returncode == 0 else None
    except ValueError:
        return None


WRITE_PERMISSIONS = ('ADMIN', 'MAINTAIN', 'WRITE')


def gh_account(config, gh=None):
    """Checked before each write through gh, never cached (another session may run `gh auth switch`): the login
    (`gh api user`), the repository of the current directory and the permission of the login on it
    (`gh repo view --json nameWithOwner,viewerPermission`) against `config.repository` and, when the config names
    it, `config.github.account`. Returns {login, repository, permission}; raises AccountMismatch
    (`account_mismatch` or `repository_mismatch`). `gh` is a callable that answers JSON (or raises)."""
    gh = gh or gh_json
    expected_repo = config.get('repository') if isinstance(config, dict) else None
    github = config.get('github') if isinstance(config, dict) else None
    expected = github.get('account') if isinstance(github, dict) and isinstance(github.get('account'), str) else None
    try:
        user = gh(['api', 'user'])
    except Exception:  # noqa: BLE001  (a gh that cannot answer is a mismatch to show, never a write)
        user = None
    login = user.get('login') if isinstance(user, dict) else None
    if not isinstance(login, str) or not login:
        raise AccountMismatch('account_mismatch', 'o gh não disse qual conta está ativa (gh auth status)',
                              expected=expected)
    if expected and login.casefold() != expected.casefold():
        raise AccountMismatch('account_mismatch', f'o gh está na conta {login}, e o config pede {expected}',
                              login, expected)
    try:
        repo = gh(['repo', 'view', '--json', 'nameWithOwner,viewerPermission'])
    except Exception:  # noqa: BLE001  (the folder's repository could not be read: no write either)
        raise AccountMismatch('repository_mismatch', 'o gh não leu o repositório da pasta atual (gh repo view); '
                              f'o config pede {expected_repo}', login, expected) from None
    name = repo.get('nameWithOwner') if isinstance(repo, dict) else None
    if not isinstance(expected_repo, str) or not isinstance(name, str) or name.casefold() != expected_repo.casefold():
        raise AccountMismatch('repository_mismatch', f'a pasta atual é do repositório {name or "desconhecido"}, e o '
                              f'config pede {expected_repo}', login, expected)
    permission = repo.get('viewerPermission')
    if permission not in WRITE_PERMISSIONS:
        shown = permission or 'sem permissão'
        raise AccountMismatch('account_mismatch', f'a conta {login} não tem escrita em {name} ({shown})',
                              login, expected)
    return {'login': login, 'repository': name, 'permission': permission}
