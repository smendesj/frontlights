#!/usr/bin/env python3
"""Start, inspect and stop the processes of one issue's browser test environment.

Helper behind the browser-test route of /frontlights. It reads the `browserTest` block of the
project's `.frontlights/config.json` and brings up each process in the issue's worktree.

Operations (each prints one JSON object on stdout):
  start   spawn every process, wait for its health URL (HTTP 2xx/3xx, polled until a deadline)
          and record pids and times in `<root>/.frontlights/serve/<issue>.json`.
  status  read that record and check whether each pid is still alive.
  stop    kill the whole process tree of each recorded process, remove the record and release the issue's
          port reservations (`reservas_liberadas`; also when there is no record, which still reports a refusal).

Automatic ports: a process declares `"port": "auto"` (the only rule: omitting `port` keeps the #9 behaviour,
where the port is read from the health URL). Its `argv` elements and `health` may use `{port}`; with "auto" the
health URL must carry it in place of the port (`http://127.0.0.1:{port}/`). For each such process start reserves a
free port (the OS offers one, the bind must succeed, and it must not be reserved by a live start or process of
another issue or worktree), records it
exclusively (O_EXCL) in `<git-common-dir>/frontlights-serve/ports/<port>.json` (shared by all worktrees of the
repository; outside Git: `<root>/.frontlights/serve/ports/`), and gives the process the environment variables
`PORT` and `FRONTLIGHTS_PORT_<NAME>` (name upper-cased, non-alphanumerics as `_`). A reservation whose coordinator
and process are both dead is an orphan and is reused, except for a grace of 60 s when the coordinator died after
marking the reservation `spawning` and before recording the child pid. `stop` and a failed start release the issue's
reservations.
A process that ignores its port fails the start as an infrastructure failure, naming the process and the port.
All the ports of one start are reserved under one acquisition of a short lock on `.reserve.lock`, reentrant for the
same start. It is an operating-system lock (Windows `msvcrt.locking` on one byte, POSIX `fcntl.flock`) taken on a file
that is created if missing and never moved nor deleted, so there is no window in which the lock is absent; the system
releases it by itself when the owner dies (even by kill -9), hence no stale-lock or pid logic. It is retried until
`RESERVE_LOCK_SECONDS` and then refused, in every path of the loop. It does not depend on hard links, so it works on
FAT/exFAT. A reservation file that cannot be read (or whose pid is not an integer from 1 to 2**31-1) is treated as
being written by its owner (alive) while it is recent, and as an orphan once it is older than 60 s. A port counts as
busy when it cannot be bound on 127.0.0.1, 0.0.0.0, 127.0.0.2 (when the platform has it) or (when IPv6 works) ::1 and
::, or when something already accepts connections there.
`stop` takes the same per-issue lock as `start` (`<issue>.lock`): while a start of that issue is in progress in the
same worktree, `stop` is refused instead of releasing the reservations the start is still using. That lock is
created, judged and (when its owner is dead, or it is empty and older than `EMPTY_LOCK_SECONDS`, the leftover of an
owner killed before writing its pid) replaced under a short operating-system lock on
`.frontlights/serve/.locks.guard`, so two callers never both replace the same stale lock. Its retry loop checks the
deadline on every pass.
Reservations are shared only among the worktrees of ONE repository (they live in that repository's Git common
directory): two different repositories, or a project outside Git, do not see each other's reservations, so both may be
offered the same candidate port until one of the servers binds it (the bind/connect probe then skips it). The start
output only says whether the reservations are shared (`reservas_compartilhadas`), not with whom. The race between two
repositories (or a project outside Git) is not prevented: when both are offered the same candidate port, the one that
loses it fails its start as an infrastructure failure (the process cannot bind the port) and can start again.
An I/O error while creating or writing a lock, a reservation or a record is an infrastructure refusal with JSON
(never a traceback), and the issue lock is released; `main` turns any other OSError that escapes into the same
refusal. A config error is refused as `uso` before anything is reserved or spawned: a health URL or `port` outside
1 to 65535 or of the wrong type, credentials in the health URL, an invalid `timeoutSeconds`, a NUL character in the
`argv`, `health` or `cwd`, and a `cwd` that is not text, is absolute, leaves the worktree or does not exist.
Limit of the `spawning` grace: between spawning the process and recording its pid in the reservation (the pid is known
only once Popen returns) the reservation holds for 60 s on the `spawning` mark alone. If the coordinator is killed in
that window and the server only starts listening after the 60 s, another start may be offered its port; a server that
listens sooner is seen by the bind/connect probe.
The variable name is the process name upper-cased with non-alphanumerics as `_`, so two `auto` processes named
`web-api` and `web_api` would get the same `FRONTLIGHTS_PORT_WEB_API`: such a config is refused (category `uso`).
Processes with a fixed port or without `port` do not receive the variable, so their names may collide.
The start output says whether the reservations are shared (`reservas_compartilhadas`).

Preview (issue 34): `preview start|refresh|status|stop` is the long-running mode, one per project, read from the
top-level `preview` block of the config (`worktree` relative to --root, `branch`, `baseUrl` on a local host,
`processes` with the same rules as `browserTest.processes`, each `health` on a local host too). `preview.branch` is a
plain branch name that is neither main, master nor a match (fnmatch without case, a pattern also covering
`pattern/*`) of the `protected_branches` of any readable `<root>/.frontlights/authorization*.json`. Its processes run
in the preview worktree, with their stdout and stderr relayed line by line by `relay --config <config> --log <file>`
(a second process spawned by `preview start`, which loads the secrets of `browserTest.users` from the config itself
and masks them) into `<root>/.frontlights/preview/log/<name>.log`. The record lives in
`<root>/.frontlights/preview/registry.json` under its own lock (`<root>/.frontlights/preview/.lock`), so
`stop --issue <n>` never touches it, and a new session finds the processes through it. Port reservations of the
preview carry `"issue": "preview"`, so the release of an issue's reservations never frees them. `preview start` is
refused while the preview is alive (any process or log relay of the record) and when the preview worktree does not
exist. `preview status` and `preview stop` work from the record alone, with or without the `preview` block in the
config (the mask still comes from its `browserTest.users`). `preview status` adds `alive` and `relayAlive` per process
(`running` needs both for every process), `log` and the last `TAIL_LINES` lines of each log (`tail`, read from at most
the last `TAIL_BYTES` of the file), masked again on output, and what the worktree holds (`base`, `baseCommit`,
`merged`) when a refresh brought it up.
`preview refresh [--base main] [--branch <b> ...]` (under the same lock) first refuses as `uso` whatever needs no
change (a branch that is not a plain local name or does not exist, a preview worktree that is not a worktree of this
repository on `preview.branch`, or that has tracked changes or a merge in progress, and, when the preview worktree is
missing, a `preview.branch` that already exists and is not the one the preview record names: `worktree add -B` would
move it), then stops the preview, redoes `preview.branch` at the local base (`git checkout -B` inside the preview
worktree, or `git worktree add --force -B` when it is missing), merges each `--branch` in order (`git merge --no-ff --no-edit` of the commit the check read, the
one recorded in `merged`, with the message `Merge branch '<b>' into <preview.branch>`) and brings the processes up as
`preview start` does. A conflict is aborted (`git merge --abort`), nothing comes up and the refusal names the branch
and the files (`conflict: true`). A process that exits before its health, or whose health never answers, is a broken
build: everything is torn down and the refusal carries `build: "quebrado"`, the log and its last lines written by
this run (`tail`). A log relay that dies (or cannot start) before the health is an infrastructure failure, torn down
the same way but without `build`: the process itself did not fail. Git runs from an argv list without a shell and
without prompts, with a deadline; the refresh never pushes, rebases or forces a merge, and writes no branch but
`preview.branch` (the local main and the issue branches never move). The preview branch is never pushed.

Exit codes: 0 done; 1 refusal or failure (a failed start tears down whatever already came up and
names the failing process, classified as an infrastructure failure).

Processes are started from an argv list, never through a shell. Logins and passwords from the
config are never read into the record and are redacted from every string this helper prints.
"""

import argparse
import contextlib
import datetime as dt
import fnmatch
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

POLL_SECONDS = 0.2
DEFAULT_TIMEOUT = 60
PORT_AUTO = 'auto'
INFRASTRUCTURE = 'infraestrutura'
USAGE = 'uso'
UNKNOWN_IDENTITY = 'desconhecida'
BATCH_UNSAFE = '&|^%<>!"'
MIN_SECRET = 4
MASK = '[redacted]'
KILL_WAIT_SECONDS = 15
PORT_ATTEMPTS = 200
RESERVE_LOCK_SECONDS = 20
ORPHAN_SECONDS = 60
EMPTY_LOCK_SECONDS = 5
PERSISTENT_ERRORS = 25
MAX_PID = 2 ** 31 - 1
REMOVE_ATTEMPTS = 40
CONNECT_SECONDS = 0.05
PREVIEW_ISSUE = 'preview'  # the `issue` of the preview's port reservations: never an issue number
TAIL_LINES = 20
TAIL_BYTES = 64 * 1024  # `tail_lines` reads at most this much from the end of a log
RELAY_DRAIN_SECONDS = 3  # a torn-down preview process's relay gets this long to write the last lines
GIT_SECONDS = 300  # deadline of each Git command of `preview refresh`
DEFAULT_BASE = 'main'
BRANCH_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9/._-]*')
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
PROTECTED_BRANCHES = ('main', 'master')
MAX_AUTHORIZATION_BYTES = 2 * 1024 * 1024  # an authorization record past this is skipped, never read

_SECRETS = []


class Refusal(Exception):
    """A deliberate refusal: the message is safe to show the user."""

    def __init__(self, message, process=None, category=None, extra=None):
        super().__init__(message)
        self.process = process
        self.category = category or INFRASTRUCTURE
        self.extra = extra or {}


class RelayFailure(Refusal):
    """The log relay of a preview process died or could not start: an infrastructure failure, never a broken
    build (the process itself did not fail)."""


def require(condition, message, process=None, category=None):
    if not condition:
        raise Refusal(message, process, category)


def io_failure(action, error):
    """A Refusal (infrastructure) for an I/O error: the user gets a message and JSON, never a traceback."""
    detail = error.strerror or type(error).__name__
    return Refusal(f'Falha de entrada e saída ao {action}: {detail}. Confira o espaço em disco, as permissões e '
                   'se o caminho é mesmo uma pasta ou um arquivo comum; depois tente de novo.')


@contextlib.contextmanager
def io_guard(action):
    """Turn any OSError raised inside the block into an infrastructure Refusal (see io_failure)."""
    try:
        yield
    except OSError as error:
        raise io_failure(action, error) from error


def count_denial(path, error, denied):
    """Count consecutive denials to create `path` while it does not exist; the last one is an infrastructure failure.

    A file being deleted can answer "denied" for a few milliseconds on Windows; `PERSISTENT_ERRORS` denials in a row
    with nothing there to compete are a real permission problem, not contention.
    """
    if os.path.exists(path):
        return 0
    if denied + 1 >= PERSISTENT_ERRORS:
        raise io_failure(f'criar {Path(path).name}', error) from error
    return denied + 1


def now_iso():
    return dt.datetime.now().astimezone().isoformat()


def protect(text):
    """Mask every known secret in one regex pass, longest first (never feeds on its own mask)."""
    found_secrets = sorted({secret for secret in _SECRETS if secret}, key=len, reverse=True)
    if not found_secrets:
        return text
    # the mask FIRST, replaced by itself (so masking twice changes nothing, even for a secret that is a prefix
    # of the mask), then the secrets from the longest to the shortest
    pattern = '|'.join([re.escape(MASK)] + [re.escape(secret) for secret in found_secrets])
    return re.sub(pattern, lambda found: MASK, text)


def scrub(value, skip=()):
    """Mask the string VALUES of a JSON-like value; keys and structure stay untouched.

    `skip` lists dict keys whose values are technical data (e.g. process identity) that must stay exact.
    """
    if isinstance(value, str):
        return protect(value)
    if isinstance(value, list):
        return [scrub(item, skip) for item in value]
    if isinstance(value, dict):
        return {key: item if key in skip else scrub(item, skip) for key, item in value.items()}
    return value


REGISTRY_EXACT = ('identity', 'relayIdentity', 'startedAt')


def write_json_atomic(value, path):
    """Write the value masked once, as valid JSON, replacing the file atomically."""
    path = Path(path)
    with io_guard(f'gravar {path.name}'):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f'.{path.name}.{secrets.token_hex(8)}.tmp'
        try:
            temporary.write_text(json.dumps(scrub(value, REGISTRY_EXACT), indent=2, ensure_ascii=False),
                                 encoding='utf-8')
            for attempt in range(REMOVE_ATTEMPTS):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:  # Windows: a reader holds the target open for a moment
                    if attempt == REMOVE_ATTEMPTS - 1:
                        raise
                    time.sleep(min(0.002 * (attempt + 1), 0.05))
        finally:
            if temporary.exists():
                temporary.unlink()


# ---------------------------------------------------------------- configuration

def read_config(config_file):
    try:
        return json.loads(Path(config_file).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise Refusal('Não foi possível ler o config informado em --config.')


def load_block(config_file, need_processes=True):
    """Read browserTest. `need_processes=False` is for a caller that only checks the accounts: a block that
    declares no `processes` (the project starts its own environment) then gives back an empty list, while one
    that declares them wrongly is still refused."""
    config = read_config(config_file)
    block = config.get('browserTest') if isinstance(config, dict) else None
    require(isinstance(block, dict), 'O config não tem o bloco browserTest.')
    load_secrets(block)
    if 'processes' not in block:
        require(not need_processes,
                'O config não declara browserTest.processes: o serve não tem o que subir. Suba o ambiente você mesmo '
                '(as contas de teste continuam valendo) ou declare os processos em browserTest.processes.', category=USAGE)
        return []
    return validate_processes(block.get('processes'), 'browserTest.processes')


def load_secrets(block):
    """Load the login and password of every account of a browserTest block (None: no accounts) into the mask."""
    _SECRETS.clear()
    for user in (block or {}).get('users') or []:
        if isinstance(user, dict):
            for key in ('login', 'password'):
                value = user.get(key)
                if isinstance(value, str) and value:
                    require(MASK not in value,
                            f'O {key} de um usuário em browserTest.users contém o texto {MASK}, que colide com o '
                            'marcador de máscara usado na saída e nos registros e impediria mascará-lo por inteiro. '
                            f'Use um {key} de teste sem esse texto.', category=USAGE)
                    require(len(value) >= MIN_SECRET,
                            f'O {key} de um usuário em browserTest.users tem menos de {MIN_SECRET} caracteres: '
                            'um segredo curto não pode ser mascarado com segurança na saída e nos registros. '
                            f'Use um {key} de teste com {MIN_SECRET} ou mais caracteres.', category=USAGE)
                    _SECRETS.extend([value, urllib.parse.quote(value, safe=''), urllib.parse.quote_plus(value)])


def validate_processes(processes, where):
    """Refuse a process list (`where` names it: browserTest.processes or preview.processes) before anything runs."""
    require(isinstance(processes, list) and processes, f'{where} precisa ser uma lista não vazia.')
    names, variables = set(), {}
    for item in processes:
        require(isinstance(item, dict), f'Cada item de {where} precisa ser um objeto.')
        name = item.get('name')
        require(isinstance(name, str) and name and name not in names,
                'Cada processo precisa de um name único e não vazio.')
        names.add(name)
        argv = item.get('argv')
        texts = [item.get('health'), item.get('cwd')] + (argv if isinstance(argv, list) else [])
        require(not any(isinstance(text, str) and '\0' in text for text in texts),
                f'O processo {name} tem um caractere NUL no argv, no health ou no cwd: remova-o do config.', name,
                USAGE)
        require(isinstance(argv, list) and argv and all(isinstance(part, str) and part for part in argv),
                f'O processo {name} precisa de argv como lista de strings (sem shell embutido).', name)
        health = item.get('health')
        try:
            parts = urllib.parse.urlsplit(health) if isinstance(health, str) else None
        except ValueError:  # e.g. an unterminated IPv6 literal
            parts = None
        require(parts and parts.scheme in ('http', 'https') and parts.hostname,
                f'O processo {name} precisa de health como URL http(s).', name, USAGE)
        require('port' not in item or item['port'] == PORT_AUTO
                or isinstance(item['port'], int) and not isinstance(item['port'], bool),
                f'O processo {name} tem port inválida: use um inteiro ou "{PORT_AUTO}".', name, USAGE)
        require('@' not in parts.netloc, f'O health do processo {name} não pode ter usuário e senha na URL.', name,
                USAGE)
        timeout = item.get('timeoutSeconds', DEFAULT_TIMEOUT)
        require(isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0,
                f'O processo {name} tem timeoutSeconds inválido: use um número maior que zero.', name, USAGE)
        require(item.get('cwd') is None or isinstance(item['cwd'], str),
                f'O cwd do processo {name} precisa ser um texto (caminho relativo à worktree).', name, USAGE)
        # refused here, before anything is spawned: a port outside 1..65535 would otherwise fail after the spawn
        require(not isinstance(item.get('port'), int) or valid_port(item['port']),
                f'O processo {name} tem port fora da faixa de 1 a 65535.', name, USAGE)
        if not is_auto(item):  # an auto health URL carries {port}, filled in only after the reservation
            require(url_port(parts) is not None,
                    f'O health do processo {name} tem uma porta inválida: use uma porta de 1 a 65535 na URL, ou '
                    f'port "{PORT_AUTO}".', name, USAGE)
        if is_auto(item):  # only these receive FRONTLIGHTS_PORT_<NAME>, so only they can collide
            require(parts.netloc.endswith(':{port}'),
                    f'O processo {name} usa port "{PORT_AUTO}", então o health precisa ter {{port}} no lugar da '
                    'porta (por exemplo http://127.0.0.1:{port}/): sem isso a saúde não prova que o processo '
                    'escutou a porta reservada.', name, USAGE)
            variable = env_name(name)
            require(variable not in variables,
                    f'Os processos {variables.get(variable)} e {name} geram a mesma variável {variable} depois de '
                    'normalizar o nome (maiúsculas, e tudo que não é letra ou número vira "_"). Renomeie um deles.',
                    name, USAGE)
            variables[variable] = name
    return processes


def load_preview_block(config_file, root, need_processes=True):
    """Read the top-level `preview` block (worktree, branch, baseUrl, processes) and load the mask from
    browserTest.users. `need_processes=False` (status, stop) only loads the mask and returns the block or None: those
    two work from the record alone, so a config without the block still reaches them."""
    config = read_config(config_file)
    browser = config.get('browserTest') if isinstance(config, dict) else None
    load_secrets(browser if isinstance(browser, dict) else None)
    block = config.get('preview') if isinstance(config, dict) else None
    if not need_processes:
        return block if isinstance(block, dict) else None
    require(isinstance(block, dict), 'O config não tem o bloco preview: declare worktree, branch, baseUrl e processes '
            'nele para usar a prévia.', category=USAGE)
    worktree = block.get('worktree')
    require(isinstance(worktree, str) and worktree and '\0' not in worktree,
            'preview.worktree precisa ser um caminho relativo ao --root (texto não vazio).', category=USAGE)
    parts = Path(worktree)
    require(not parts.is_absolute() and not parts.drive and not worktree.startswith(('/', '\\'))
            and '..' not in parts.parts,
            'preview.worktree precisa ser relativo ao --root, sem ".." e sem unidade ou raiz.', category=USAGE)
    base = Path(root).resolve()
    target = (base / worktree).resolve()
    require(base in target.parents, 'preview.worktree precisa ficar dentro do --root (e não ser o próprio --root).',
            category=USAGE)
    branch = block.get('branch')
    require(plain_branch(branch),
            'preview.branch precisa ser um nome simples de branch (letras, dígitos, "/", "-", "_" e ".", começando '
            'por letra ou dígito, sem "..", "//", "/." nem ".lock", e sem terminar em "/" ou ".").', category=USAGE)
    pattern = protected_pattern(branch, protected_patterns(root))
    require(pattern is None, f'preview.branch ({branch}) é uma branch protegida (casa com {pattern}: main, master ou '
            'um padrão de protected_branches em .frontlights/authorization*.json). A prévia tem uma branch própria, '
            'refeita a partir da base a cada refresh: escolha outro nome.', category=USAGE)
    base_url = block.get('baseUrl')
    try:
        url = urllib.parse.urlsplit(base_url) if isinstance(base_url, str) else None
    except ValueError:
        url = None
    require(url and url.scheme in ('http', 'https') and url.hostname in LOCAL_HOSTS and '@' not in url.netloc,
            'preview.baseUrl precisa ser uma URL http(s) em host local (127.0.0.1, localhost ou ::1), sem usuário '
            'e senha.', category=USAGE)
    require('processes' in block, 'O config não declara preview.processes: a prévia não tem o que subir.',
            category=USAGE)
    processes = validate_processes(block['processes'], 'preview.processes')
    logs = {}
    for item in processes:
        host = urllib.parse.urlsplit(item['health']).hostname  # parsed by validate_processes
        require(host in LOCAL_HOSTS, f'O health do processo {item["name"]} precisa ficar em host local (127.0.0.1, '
                'localhost ou ::1), como a preview.baseUrl.', item['name'], USAGE)
        # case-folded: on Windows (and macOS) Web.log and web.log are the same file
        log_name = log_file_name(item['name'])
        require(log_name.casefold() not in logs, f'Os processos {logs.get(log_name.casefold())} e {item["name"]} '
                f'gerariam o mesmo arquivo de log ({log_name}) depois de normalizar o nome. Renomeie um deles.',
                item['name'], USAGE)
        logs[log_name.casefold()] = item['name']
    return {'worktree': worktree, 'branch': branch, 'baseUrl': base_url, 'processes': processes}


def authorization_records(root):
    """(file name, object) of every readable `<root>/.frontlights/authorization*.json`, in name order. A file that is
    missing, unreadable, larger than `MAX_AUTHORIZATION_BYTES`, nested too deep for json or not an object is
    skipped: these records are read only to refuse more, never to allow."""
    try:
        files = sorted((Path(root) / '.frontlights').glob('authorization*.json'))
    except OSError:
        files = []
    records = []
    for path in files:
        try:
            with open(path, 'rb') as handle:
                raw = handle.read(MAX_AUTHORIZATION_BYTES + 1)
            if len(raw) > MAX_AUTHORIZATION_BYTES:
                continue
            data = json.loads(raw.decode('utf-8-sig'))
        except (OSError, ValueError, RecursionError, MemoryError):
            continue
        if isinstance(data, dict):
            records.append((relative(Path(root), path), data))
    return records


def protected_patterns(root):
    """main, master and the `protected_branches` of every readable `<root>/.frontlights/authorization*.json`
    (`authorization_records`); an entry that is not a non-empty text is skipped."""
    patterns = list(PROTECTED_BRANCHES)
    for _, data in authorization_records(root):
        listed = data.get('protected_branches')
        if isinstance(listed, list):
            patterns += [item for item in listed if isinstance(item, str) and item.strip('/')]
    return patterns


def protected_pattern(branch, patterns):
    """The first pattern that protects `branch`, or None. The rule of `frontlights.authorize`: fnmatch without case,
    and a pattern also protects everything below it (`pattern/*`)."""
    folded = branch.casefold()
    for pattern in patterns:
        stem = pattern.casefold().rstrip('/')
        if fnmatch.fnmatchcase(folded, stem) or fnmatch.fnmatchcase(folded, stem + '/*'):
            return pattern
    return None


def log_file_name(name):
    return re.sub(r'[^A-Za-z0-9._-]', '_', name) + '.log'


def valid_port(value):
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def url_port(parts):
    """Port of a parsed http(s) URL (the scheme default when absent), or None when it is not 1..65535."""
    try:
        port = parts.port
    except ValueError:
        return None
    if port is None:
        return 443 if parts.scheme == 'https' else 80
    return port if valid_port(port) else None


def is_auto(item):
    return item.get('port') == PORT_AUTO


def env_name(name):
    return 'FRONTLIGHTS_PORT_' + re.sub(r'[^A-Z0-9]', '_', name.upper())


def with_port(item, port):
    """Copy of the process with {port} replaced in every argv element and in the health URL."""
    token = str(port)
    return dict(item, port=port, autoPort=True, argv=[part.replace('{port}', token) for part in item['argv']],
                health=item['health'].replace('{port}', token))


def process_port(item):
    if isinstance(item.get('port'), int):
        return item['port']
    return url_port(urllib.parse.urlsplit(item['health']))


def process_cwd(root, item, scope='da issue'):
    base = Path(root).resolve()
    target = (base / item['cwd']).resolve() if item.get('cwd') else base
    require(target == base or base in target.parents,
            f'O cwd do processo {item["name"]} precisa ficar dentro da worktree {scope}.', item['name'], USAGE)
    require(target.is_dir(), f'O cwd do processo {item["name"]} não existe.', item['name'], USAGE)
    return target


# ---------------------------------------------------------------- process control

def spawn(argv, cwd, env=None, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
    """Start argv detached (its own process group, no console window), never through a shell."""
    executable = shutil.which(argv[0])
    if executable is None:
        raise OSError('executável não encontrado')
    options = {'cwd': str(cwd), 'stdin': stdin, 'stdout': stdout, 'stderr': stderr}
    if env:
        options['env'] = dict(os.environ, **env)
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        options['start_new_session'] = True
    return subprocess.Popen([executable] + argv[1:], **options)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def healthy(url):
    try:
        with _OPENER.open(url, timeout=2) as answer:
            return 200 <= answer.status < 400
    except urllib.error.HTTPError as error:
        return 300 <= error.code < 400
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return False


def wait_healthy(child, item, relay=None):
    timeout = item.get('timeoutSeconds', DEFAULT_TIMEOUT)  # validated by load_block, before anything is spawned
    reserved = f' (porta reservada {item["port"]})' if item.get('autoPort') else ''
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise Refusal(f'O processo {item["name"]} terminou antes de ficar saudável{reserved} '
                          f'(código {child.returncode}).', item['name'])
        if relay is not None and relay.poll() is not None:
            raise RelayFailure(f'O relé do log do processo {item["name"]} terminou (código {relay.returncode}) antes '
                               'de o processo ficar saudável: o log da prévia não seria gravado.', item['name'])
        if healthy(item['health']):
            return
        time.sleep(POLL_SECONDS)
    raise Refusal(f'O processo {item["name"]} não ficou saudável em {timeout} s{reserved}. Se ele ignora a porta '
                  'reservada, faça-o ler PORT, a variável FRONTLIGHTS_PORT_<NOME> ou {port} no argv.'
                  if reserved else f'O processo {item["name"]} não ficou saudável em {timeout} s.', item['name'])


def guard_batch(argv, name):
    """On Windows a .cmd/.bat runs through cmd.exe, which would interpret shell metacharacters."""
    if os.name != 'nt':
        return
    executable = shutil.which(argv[0]) or ''
    if executable.lower().endswith(('.cmd', '.bat')):
        require(not any(char in part for part in argv[1:] for char in BATCH_UNSAFE),
                f'O processo {name} usa um .cmd/.bat (via cmd.exe): o argv não pode ter '
                f'metacaracteres de shell ({BATCH_UNSAFE}).', name)


def _kill_signal(pid):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, timeout=60)
    else:
        import signal
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def kill_tree(pid):
    """Kill the process tree of pid and report whether the root is really gone afterwards.

    The exit status of taskkill/killpg is not trusted: pid_alive decides. Returns True when dead.
    """
    _kill_signal(pid)
    deadline = time.monotonic() + KILL_WAIT_SECONDS
    while pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    return not pid_alive(pid)


def valid_pid(value):
    """True for an integer (not a bool) from 1 to 2**31-1: the only values a real pid can have."""
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_PID


def pid_alive(pid):
    if not valid_pid(pid):
        return False
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_identity(pid):
    """Creation time of a process as a string, or None when the platform cannot tell."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            created, spent, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(spent),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
        return fields[19]  # field 22: start time in clock ticks since boot
    except (OSError, IndexError):
        pass
    try:
        done = subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)], capture_output=True, text=True,
                              timeout=10, env=dict(os.environ, LC_ALL='C'))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def same_process(entry):
    """True when the recorded pid is alive and (as far as known) is still the recorded process."""
    if not pid_alive(entry['pid']):
        return False
    recorded, current = entry.get('identity'), process_identity(entry['pid'])
    if recorded in (None, UNKNOWN_IDENTITY) or current is None:
        return True  # cannot tell: assume alive for refusing a start; never used to kill
    return recorded == current


# ---------------------------------------------------------------- operations

def registry_path(root, issue):
    return Path(root) / '.frontlights' / 'serve' / f'{issue}.json'


def lock_path(root, issue):
    return Path(root) / '.frontlights' / 'serve' / f'{issue}.lock'


def relative(root, path):
    return path.relative_to(root).as_posix()


def acquire_lock(root, issue):
    """Create <issue>.lock exclusively; see acquire_lock_file. `start` and `stop` of the issue both take it."""
    return acquire_lock_file(root, lock_path(root, issue), f'da issue {issue}')


def acquire_lock_file(root, path, scope):
    """Create the lock file `path` exclusively; a lock of a dead owner is replaced, an unreadable one refused.

    `scope` names the owner in messages ("da issue 9", "da prévia"). Creating, judging and replacing it happen
    under a short operating-system lock on `.locks.guard` next to it (never moved nor deleted): two callers can never
    both replace the same stale lock, and nobody reads a lock that is still being written. A lock that is EMPTY and
    older than `EMPTY_LOCK_SECONDS` is the leftover of an owner killed between creating and writing it (the creator
    holds the guard across both steps, so under the guard an empty lock has no live writer): it is replaced like the
    lock of a dead owner; a recent empty one is waited for until the deadline. Any other content that is not a pid
    stays refused. The loop has a single exit path per pass, the deadline check followed by a short sleep: no branch
    (a lock being deleted by its owner on Windows, a replacement that did not remove the file, an empty lock) skips
    it, so the call always ends within `RESERVE_LOCK_SECONDS` (the wait for the guard counts in it), plus the retries
    of one removal. An I/O error becomes an infrastructure refusal, and a lock created but not written is removed
    again; so does a denial that persists with no lock file there (`count_denial`), instead of waiting for the
    deadline.
    """
    name = relative(Path(root), path)
    with io_guard('criar a pasta de travas'):
        path.parent.mkdir(parents=True, exist_ok=True)
    unreadable = (f'O arquivo de trava {name} está ilegível, então não dá para saber se outro start ou stop está em '
                  f'andamento. Se nenhum start ou stop {scope} estiver rodando, apague {name} à mão e tente '
                  'de novo.')
    deadline = time.monotonic() + RESERVE_LOCK_SECONDS
    guard = take_os_lock(path.parent / '.locks.guard',
                         f'Não foi possível obter a trava {name} em {RESERVE_LOCK_SECONDS} s: outro start ou stop '
                         'a mantém. Tente de novo em instantes.')
    denied = 0
    try:
        while True:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                descriptor = None
            except PermissionError as error:  # Windows: being deleted by its owner, unless it never goes away
                descriptor = None
                denied = count_denial(path, error, denied)
            except OSError as error:
                raise io_failure('criar a trava', error) from error
            if descriptor is not None:
                try:
                    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                        handle.write(str(os.getpid()))
                except OSError as error:
                    remove_file(path)  # never leave an empty lock behind
                    raise io_failure('gravar a trava', error) from error
                return path
            try:
                text = path.read_text(encoding='utf-8')
            except (FileNotFoundError, PermissionError):
                text = None  # released (or being deleted) between the failed create and the read: try again
            except (OSError, ValueError):
                raise Refusal(unreadable, category=USAGE)
            if text is not None and not text.strip():
                if older_than(path, EMPTY_LOCK_SECONDS):
                    remove_file(path)  # the owner died before writing its pid; under the guard nobody else writes
            elif text is not None:
                owner = int(text) if re.fullmatch(r'\s*[0-9]{1,10}\s*', text) else None
                require(valid_pid(owner), unreadable, category=USAGE)
                require(not pid_alive(owner),
                        f'Outro start ou stop {scope} está em andamento (pid {owner}). Aguarde-o terminar; '
                        f'se ele já não existe, apague {name} à mão.', category=USAGE)
                remove_file(path)  # dead owner: under the guard nobody else replaces it meanwhile
            require(time.monotonic() < deadline,
                    f'Não foi possível obter a trava {name}; tente de novo. Se o arquivo continua vazio, com data '
                    f'no futuro (relógio adiantado), apague {name} à mão.', category=USAGE)
            time.sleep(0.02)
    finally:
        release_os_lock(guard)


def release_lock(path):
    remove_file(path)


def write_registry(root, issue, entries):
    write_json_atomic({'issue': issue, 'root': str(Path(root).resolve()), 'processes': entries},
                      registry_path(root, issue))


# ---------------------------------------------------------------- preview (issue 34)

def preview_dir(root):
    return Path(root) / '.frontlights' / 'preview'


def preview_registry_path(root):
    return preview_dir(root) / 'registry.json'


def preview_lock_path(root):
    return preview_dir(root) / '.lock'


def preview_log_dir(root):
    return preview_dir(root) / 'log'


def write_preview_registry(root, block, entries, started_at, contents=None):
    """`contents` ({base, baseCommit, merged}, from `preview refresh`) says what the preview worktree holds."""
    write_json_atomic({'root': str(Path(root).resolve()), 'worktree': block['worktree'], 'branch': block['branch'],
                       'baseUrl': block['baseUrl'], **(contents or {}), 'startedAt': started_at,
                       'processes': entries},
                      preview_registry_path(root))


def read_preview_registry(root):
    path = preview_registry_path(root)
    name = relative(Path(root), path)
    require(path.is_file(), 'Não há registro da prévia nesta worktree: rode preview start.')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        require(isinstance(record.get('processes'), list), 'registro inválido')
        for entry in record['processes']:
            require(valid_pid(entry.get('pid')), 'registro inválido')
            require(entry.get('relayPid') is None or valid_pid(entry['relayPid']), 'registro inválido')
    except (OSError, ValueError, AttributeError, Refusal):
        raise Refusal(f'O registro da prévia ({name}) está ilegível ou inválido, então preview start, status e stop '
                      'não conseguem usá-lo. Confira se há processos da prévia em execução, encerre-os à mão e '
                      f'apague {name}.')
    return record


def relay_argv(config_file, log_file):
    """argv of the relay (absolute paths: it runs with the main worktree as cwd, not the caller's)."""
    return [sys.executable, str(Path(__file__).resolve()), 'relay', '--config', str(Path(config_file).resolve()),
            '--log', str(Path(log_file).resolve())]


def relay(config_file, log_file):
    """Copy stdin to the log file line by line, masking the secrets of browserTest.users, until EOF.

    The secrets come from the config (never from argv or the environment). The file is opened in append mode and
    flushed per line, so the log survives a crash of the process and of the relay itself. Limit: a secret split
    across two lines is not masked.
    """
    config = read_config(config_file)
    browser = config.get('browserTest') if isinstance(config, dict) else None
    load_secrets(browser if isinstance(browser, dict) else None)
    path = Path(log_file)
    with io_guard('abrir o log da prévia'):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, 'a', encoding='utf-8', errors='replace', newline='')
    lines = 0
    with handle:
        for raw in sys.stdin.buffer:
            with io_guard('gravar o log da prévia'):
                handle.write(protect(raw.decode('utf-8', errors='replace')))
                handle.flush()
            lines += 1
    return {'ok': True, 'log': str(path), 'lines': lines}


def preview_start(config_file, root):
    block = load_preview_block(config_file, root)
    lock = acquire_lock_file(root, preview_lock_path(root), 'da prévia')
    try:
        return preview_start_locked(block, config_file, root)
    finally:
        release_lock(lock)


def preview_start_locked(block, config_file, root):
    if preview_registry_path(root).is_file():
        previous = read_preview_registry(root)
        # the process or its relay: a live relay alone still holds the log of a process nobody tracks any more
        require(not any(same_process(item) for item in preview_kill_list(previous['processes'])),
                'A prévia já está no ar (um processo ou o relé do log dele está vivo); rode `preview refresh` para '
                'refazê-la ou `preview stop` para derrubá-la.', category=USAGE)
    worktree = (Path(root).resolve() / block['worktree'])
    require(worktree.is_dir(), f'A worktree da prévia ({block["worktree"]}) não existe; rode `preview refresh` para '
            'criá-la.', category=USAGE)
    return launch_preview(block, config_file, root)


def launch_preview(block, config_file, root, contents=None):
    """Bring the preview's processes up in its worktree (shared by `preview start` and `preview refresh`).

    Each process gets its relay and log; the record is written after every spawn. A process that exits before it is
    healthy, or whose health never answers, is a broken build: everything that came up is torn down (each process
    before its relay, which is given `RELAY_DRAIN_SECONDS` to write the last lines) and the refusal carries
    `build: "quebrado"`, the log (`log`) and its last `TAIL_LINES` lines written by this run (`tail`).
    """
    worktree = Path(root).resolve() / block['worktree']
    processes = block['processes']
    cwds = [process_cwd(worktree, item, 'da prévia') for item in processes]  # refused before anything is reserved
    log_dir = preview_log_dir(root)
    started, started_at, broken = [], now_iso(), None
    try:
        with io_guard('criar a pasta de log da prévia'):
            log_dir.mkdir(parents=True, exist_ok=True)
        ports = reserve_ports(root, PREVIEW_ISSUE, [item['name'] for item in processes if is_auto(item)])
        for item, cwd in zip(processes, cwds):
            env = None
            if is_auto(item):
                port = ports[item['name']]
                env = {'PORT': str(port), env_name(item['name']): str(port)}
                item = with_port(item, port)
            guard_batch(item['argv'], item['name'])
            if env:
                mark_spawning(root, port)
            log_file = log_dir / log_file_name(item['name'])
            offset = log_size(log_file)  # the tail of a broken build shows only what this run wrote
            try:
                child = spawn(item['argv'], cwd, env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            except (OSError, ValueError):  # ValueError: e.g. a NUL character in argv
                raise Refusal(f'Não foi possível iniciar o processo {item["name"]}.', item['name'])
            started.append({'name': item['name'], 'pid': child.pid, 'port': process_port(item),
                            'url': item['health'], 'startedAt': now_iso(),
                            'identity': process_identity(child.pid) or UNKNOWN_IDENTITY,
                            'log': relative(Path(root), log_file)})
            if env:
                attach_child(root, port, started[-1])
            write_preview_registry(root, block, started, started_at, contents)  # from here on stop has something
            try:
                relay_child = spawn(relay_argv(config_file, log_file), Path(root).resolve(), stdin=child.stdout)
            except (OSError, ValueError):
                raise RelayFailure(f'Não foi possível iniciar o relé do log do processo {item["name"]}.',
                                   item['name'])
            finally:
                child.stdout.close()  # only the relay keeps the read end: it sees EOF when the process dies
            started[-1].update(relayPid=relay_child.pid,
                               relayIdentity=process_identity(relay_child.pid) or UNKNOWN_IDENTITY)
            write_preview_registry(root, block, started, started_at, contents)
            try:
                wait_healthy(child, item, relay_child)
            except RelayFailure:
                raise  # the relay died, not the process: infrastructure, never a broken build
            except Refusal:
                broken = (log_file, offset)
                raise
    except BaseException as failure:
        left = kill_preview(started)
        left_names = {entry['pid'] for entry in left}
        kept = [entry for entry in started if entry['pid'] in left_names or entry.get('relayPid') in left_names]
        try:
            if kept:  # keep only what survived, so stop can retry
                write_preview_registry(root, block, kept, started_at, contents)
            else:
                preview_registry_path(root).unlink(missing_ok=True)
        except (OSError, Refusal):  # best effort: the original failure is what the user must see
            pass
        release_ports(root, PREVIEW_ISSUE, keep=[entry['port'] for entry in kept])
        if broken and isinstance(failure, Refusal):  # read after the teardown, so the relay wrote the last lines
            failure.extra = dict(failure.extra, build='quebrado', log=relative(Path(root), broken[0]),
                                 tail=tail_lines(broken[0], offset=broken[1]))
        if left and isinstance(failure, Refusal):
            names = ', '.join(f'{entry["name"]} (pid {entry["pid"]})' for entry in left)
            raise Refusal(f'{failure} Não foi possível derrubar: {names}; rode preview stop para tentar de novo.',
                          failure.process, failure.category,
                          dict(failure.extra, left=[{'name': entry['name'], 'pid': entry['pid']} for entry in left]))
        raise
    return {'ok': True, 'worktree': block['worktree'], 'branch': block['branch'], 'baseUrl': block['baseUrl'],
            'processes': started, 'log': relative(Path(root), log_dir),
            'reservas_compartilhadas': ports_location(root)[1]}


def log_size(path):
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def tail_lines(path, count=TAIL_LINES, offset=0):
    """Last `count` lines of a log from byte `offset` on (decoded with replacement); unreadable or missing: [].

    Only the end is read: at most `TAIL_BYTES` before the end of the file (never before `offset`). When that window
    starts in the middle of a line, the cut line is dropped (the byte before the window says whether it is).
    """
    try:
        with open(path, 'rb') as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(offset, size - TAIL_BYTES, 0)
            if start > offset:  # the window cut the file: read from the byte before it and drop up to its first
                handle.seek(start - 1)  # newline, so a window that starts on a line keeps that line
                data = handle.read(TAIL_BYTES + 1).partition(b'\n')[2]
            else:
                handle.seek(start)
                data = handle.read(TAIL_BYTES)
    except OSError:
        return []
    return data.decode('utf-8', errors='replace').splitlines()[-count:]


def kill_preview(started):
    """Tear down what a preview launch brought up, last first: each process tree, then its relay, which is first
    given `RELAY_DRAIN_SECONDS` to reach EOF and write the process's last lines. Returns the {name, pid, identity}
    items whose root is still alive."""
    left = []
    for entry in reversed(started):
        for item in preview_kill_list([entry]):
            if item['pid'] == entry.get('relayPid'):
                deadline = time.monotonic() + RELAY_DRAIN_SECONDS
                while pid_alive(item['pid']) and time.monotonic() < deadline:
                    time.sleep(POLL_SECONDS / 4)
            left += kill_started([item])
    return left


def relay_alive(entry):
    return valid_pid(entry.get('relayPid')) and same_process({'pid': entry['relayPid'],
                                                             'identity': entry.get('relayIdentity')})


def preview_status(config_file, root):
    """Works from the record alone (the `preview` block may be gone from the config); the mask comes from the
    config's browserTest.users. `running` needs every process and its log relay alive."""
    load_preview_block(config_file, root, need_processes=False)
    record = read_preview_registry(root)
    # main masks the output, so the tail (already masked by the relay) is masked again on the way out
    processes = [dict(entry, alive=same_process(entry), relayAlive=relay_alive(entry),
                      tail=tail_lines(Path(root) / entry['log']) if isinstance(entry.get('log'), str) else [])
                 for entry in record['processes']]
    return {'ok': True, 'running': all(entry['alive'] and entry['relayAlive'] for entry in processes),
            'worktree': record.get('worktree'),
            'branch': record.get('branch'), 'baseUrl': record.get('baseUrl'),
            **{key: record[key] for key in ('base', 'baseCommit', 'merged') if key in record},
            'processes': processes}


def preview_kill_list(entries):
    """Processes of the preview and their relays, as {name, pid, identity} items, the process before its relay."""
    items = []
    for entry in entries:
        items.append({'name': entry['name'], 'pid': entry['pid'], 'identity': entry.get('identity')})
        if valid_pid(entry.get('relayPid')):
            items.append({'name': f'{entry["name"]} (relé do log)', 'pid': entry['relayPid'],
                          'identity': entry.get('relayIdentity')})
    return items


def kill_started(entries):
    """Kill every entry's process tree, last first; returns the entries whose root is still alive."""
    left = []
    for entry in reversed(entries):
        try:
            dead = kill_tree(entry['pid'])
        except Exception:
            dead = False
        if not dead:
            left.append(entry)
    return left


def ports_location(root):
    """Folder for port reservations and whether it is shared by every worktree of the repository.

    It lives in the Git common directory (`frontlights-serve/ports`), so worktrees of one repository see each
    other's reservations. Without Git (or when Git cannot say) it falls back to `<root>/.frontlights/serve/ports`
    and the second value is False.
    """
    for flags in (['--path-format=absolute', '--git-common-dir'], ['--git-common-dir']):
        try:
            done = subprocess.run(['git', '-C', str(root), 'rev-parse', *flags], capture_output=True, text=True,
                                  encoding='utf-8', timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        text = done.stdout.strip() if done.returncode == 0 else ''
        if text:
            common = Path(text)
            if not common.is_absolute():
                common = Path(root) / common
            if common.is_dir():
                return common / 'frontlights-serve' / 'ports', True
    return Path(root) / '.frontlights' / 'serve' / 'ports', False


def ports_dir(root):
    return ports_location(root)[0]


def candidate_ports():
    """Ports offered by the operating system (bind to port 0), one per attempt."""
    for _ in range(PORT_ATTEMPTS):
        with io_guard('pedir uma porta ao sistema'):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
        yield port  # offered only after the probe socket is closed, so bindable() can test it


_IPV6 = []
_ALIAS = []
LOOPBACK_ALIAS = '127.0.0.2'


def ipv6_usable():
    if not _IPV6:
        try:
            with socket.socket(socket.AF_INET6) as sock:
                sock.bind(('::1', 0))
            _IPV6.append(True)
        except (OSError, AttributeError):
            _IPV6.append(False)
    return _IPV6[0]


def loopback_alias_usable():
    """True when the platform has the second loopback address (127.0.0.2); macOS has it only when configured."""
    if not _ALIAS:
        try:
            with socket.socket(socket.AF_INET) as sock:
                sock.bind((LOOPBACK_ALIAS, 0))
            _ALIAS.append(True)
        except OSError:
            _ALIAS.append(False)
    return _ALIAS[0]


def bindable(port):
    """True when nothing else holds the port: it binds on every local address and nothing accepts connections.

    Addresses: 127.0.0.1, 0.0.0.0 and the loopback alias 127.0.0.2 (when the platform has it) and, when IPv6 works,
    ::1 and ::. A listener on any of them (or one the bind cannot see, like a specific address next to a wildcard on
    Windows) makes the port busy. Limit: a listener on another specific address (say 127.0.0.3) is seen only on
    platforms where the wildcard bind already fails because of it; the 127/8 block cannot be enumerated.
    """
    families = [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET, '0.0.0.0')]
    connects = [(socket.AF_INET, '127.0.0.1')]
    if loopback_alias_usable():
        families.append((socket.AF_INET, LOOPBACK_ALIAS))
        connects.append((socket.AF_INET, LOOPBACK_ALIAS))
    if ipv6_usable():
        families += [(socket.AF_INET6, '::1'), (socket.AF_INET6, '::')]
        connects.append((socket.AF_INET6, '::1'))
    for family, address in families:
        try:
            with socket.socket(family) as sock:
                sock.bind((address, port))
        except OSError:
            return False
    for family, address in connects:
        with socket.socket(family) as sock:
            sock.settimeout(CONNECT_SECONDS)
            if sock.connect_ex((address, port)) == 0:
                return False
    return True


def read_brief(path, limit=65536):
    """Read a small file and close it at once (os.open without delete-sharing would block a delete for longer)."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        return os.read(descriptor, limit).decode('utf-8', errors='replace')
    finally:
        os.close(descriptor)


def remove_file(path):
    """Delete a file, retrying a few ms (Windows refuses while a reader has it open). True when it is gone."""
    for attempt in range(REMOVE_ATTEMPTS):
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(min(0.002 * (attempt + 1), 0.05))
    return False


def older_than(path, seconds):
    try:
        return time.time() - os.stat(path).st_mtime > seconds
    except OSError:
        return False


def older_than_orphan(path):
    return older_than(path, ORPHAN_SECONDS)


_LOCAL_LOCK = threading.RLock()
_HELD = {}


def try_os_lock(descriptor):
    """Try once to take the exclusive operating-system lock on the file; True when taken."""
    if os.name == 'nt':
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def release_os_lock(descriptor):
    """Unlock and close; closing alone would also release it, so a failed unlock is not an error."""
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def take_os_lock(path, message):
    """Take the exclusive operating-system lock on `path` (retrying until the deadline) and return its descriptor.

    The file is created if missing (without O_EXCL) and never moved or deleted, so the lock is always on the same
    file and needs no hard links (FAT/exFAT work). The system releases it when the owner dies, even by kill -9.
    Every failed attempt (busy lock, or a file another process holds open without sharing) reaches the deadline
    check, which refuses with `message`. The descriptor is closed on every path that does not return it. An error
    that keeps opening the file (a folder in its place, a denied permission) is an infrastructure refusal with the
    reason after `PERSISTENT_ERRORS` tries in a row, not a wait for the deadline; an existing file that is held open
    by someone else is contention and keeps waiting.
    """
    deadline = time.monotonic() + RESERVE_LOCK_SECONDS
    failures = 0
    while True:
        descriptor = None
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0))
            failures = 0
            if try_os_lock(descriptor):
                taken, descriptor = descriptor, None
                return taken
        except OSError as error:
            # a regular file that cannot be opened is held by someone else (Windows: no sharing): contention
            failures = 0 if os.path.isfile(path) else failures + 1
            if failures >= PERSISTENT_ERRORS:
                raise io_failure(f'abrir {Path(path).name}', error) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
        require(time.monotonic() < deadline, message)
        time.sleep(0.02)


def take_reserve_file(directory):
    """Take the operating-system lock on `.reserve.lock` of the reservation folder and return its descriptor."""
    return take_os_lock(directory / '.reserve.lock',
                        f'Não foi possível obter a trava de reserva de portas em {RESERVE_LOCK_SECONDS} s: outra '
                        'reserva a mantém. O sistema libera a trava sozinho quando o dono termina; tente de novo em '
                        'instantes.')


@contextlib.contextmanager
def reservation_lock(directory):
    """Short exclusive lock so choosing and recording ports is one step across processes and threads.

    Reentrant: a start that reserves several ports holds it once and never waits for itself.
    """
    directory = Path(directory)
    with io_guard('criar a pasta de reservas de portas'):
        directory.mkdir(parents=True, exist_ok=True)
    key = str(directory)
    with _LOCAL_LOCK:
        if _HELD.get(key):
            _HELD[key] += 1
            try:
                yield
            finally:
                _HELD[key] -= 1
            return
        descriptor = take_reserve_file(directory)
        _HELD[key] = 1
        try:
            yield
        finally:
            _HELD.pop(key, None)
            release_os_lock(descriptor)


def read_reservation(path):
    try:
        record = json.loads(read_brief(path))
        return record if isinstance(record, dict) and valid_pid(record.get('pid')) else None
    except (OSError, ValueError):
        return None


def reservation_live(path):
    """A reservation holds while its coordinator (a running start) or its started process is alive.

    Unreadable (a start that crashed between creating and writing it, or one still writing): alive while the
    file is recent, an orphan once it is older than 60 s.
    """
    record = read_reservation(path)
    if record is None:
        return not older_than_orphan(path)
    child = record.get('child')
    if same_process(record) or (isinstance(child, dict) and valid_pid(child.get('pid'))
                                and same_process(child)):
        return True
    # a coordinator that died between spawning the process and recording its pid leaves a process nobody tracks:
    # the "spawning" mark keeps the port for a grace period (a start that never got to spawn leaves no mark)
    return bool(record.get('spawning')) and not isinstance(child, dict) and not older_than_orphan(path)


def reserve_port(root, issue, name):
    """Reserve a free port for the process: record it exclusively and return it (the reservation path too).

    An I/O error (the system offers no candidate port, the record cannot be written) is an infrastructure refusal,
    and a record created but not written is removed again.
    """
    directory = ports_dir(root)
    denied = 0
    with reservation_lock(directory):
        for port in candidate_ports():
            path = directory / f'{port}.json'
            if path.exists():
                if reservation_live(path):
                    continue  # reserved by a live start/issue (maybe of another worktree)
                if not remove_file(path):
                    continue
            if not bindable(port):
                continue  # another program holds it
            record = {'issue': issue, 'process': name, 'root': str(Path(root).resolve()), 'pid': os.getpid(),
                      'identity': process_identity(os.getpid()) or UNKNOWN_IDENTITY, 'reservedAt': now_iso()}
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            except PermissionError as error:  # Windows: the file is being deleted, unless it never goes away
                denied = count_denial(path, error, denied)
                continue
            except OSError as error:
                raise io_failure('criar a reserva da porta', error) from error
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    handle.write(json.dumps(scrub(record, REGISTRY_EXACT), indent=2, ensure_ascii=False))
            except OSError as error:
                remove_file(path)  # never leave an empty reservation behind
                raise io_failure('gravar a reserva da porta', error) from error
            return port
    raise Refusal(f'Não foi possível reservar uma porta livre para o processo {name}.')


def reserve_ports(root, issue, names):
    """Reserve one port per name under a single acquisition of the lock; returns {name: port}."""
    with reservation_lock(ports_dir(root)):
        return {name: reserve_port(root, issue, name) for name in names}


def release_ports(root, issue, keep=()):
    """Remove this issue's reservations made from this worktree (except the ports in `keep`); returns the ports."""
    directory = ports_dir(root)
    here = str(Path(root).resolve())
    kept = {str(port) for port in keep}
    released = []
    try:
        paths = sorted(directory.glob('*.json')) if directory.is_dir() else []
    except OSError:  # an unreadable folder: nothing is reported as released; the reservations of a dead start are
        paths = []  # reclaimed as orphans by the next reserve
    for path in paths:
        record = read_reservation(path)
        if record and record.get('issue') == issue and record.get('root') == here and path.stem not in kept:
            if remove_file(path) and path.stem.isdigit():
                released.append(int(path.stem))
    return sorted(released)


def mark_spawning(root, port):
    """Mark the reservation just before the process is spawned (see reservation_live)."""
    path = ports_dir(root) / f'{port}.json'
    record = read_reservation(path)
    if record is not None:
        record['spawning'] = now_iso()
        write_json_atomic(record, path)


def attach_child(root, port, child_entry):
    """Record the started process in its reservation, so it keeps holding after the start command exits."""
    path = ports_dir(root) / f'{port}.json'
    record = read_reservation(path)
    if record is not None:
        record['child'] = {'pid': child_entry['pid'], 'identity': child_entry['identity']}
        write_json_atomic(record, path)


def start(config_file, root, issue):
    processes = load_block(config_file)
    lock = acquire_lock(root, issue)
    try:
        return start_locked(processes, root, issue)
    finally:
        release_lock(lock)


def start_locked(processes, root, issue):
    if registry_path(root, issue).is_file():
        previous = read_registry(root, issue)
        require(not any(same_process(entry) for entry in previous['processes']),
                f'Já há processos em execução para a issue {issue}: rode stop antes de um novo start.',
                category=USAGE)
    cwds = [process_cwd(root, item) for item in processes]  # a bad cwd is refused before anything is reserved
    started = []
    try:
        ports = reserve_ports(root, issue, [item['name'] for item in processes if is_auto(item)])
        for item, cwd in zip(processes, cwds):
            env = None
            if is_auto(item):
                port = ports[item['name']]
                env = {'PORT': str(port), env_name(item['name']): str(port)}
                item = with_port(item, port)
            guard_batch(item['argv'], item['name'])
            if env:
                mark_spawning(root, port)
            try:
                child = spawn(item['argv'], cwd, env)
            except (OSError, ValueError):  # ValueError: e.g. a NUL character in argv
                raise Refusal(f'Não foi possível iniciar o processo {item["name"]}.', item['name'])
            started.append({'name': item['name'], 'pid': child.pid, 'port': process_port(item),
                            'url': item['health'], 'startedAt': now_iso(),
                            'identity': process_identity(child.pid) or UNKNOWN_IDENTITY})
            if env:
                attach_child(root, port, started[-1])
            write_registry(root, issue, started)  # a crash from here on leaves something stop can tear down
            wait_healthy(child, item)
    except BaseException as failure:
        left = kill_started(started)
        try:
            if left:
                write_registry(root, issue, left)  # keep only what survived, so stop can retry
            else:
                registry_path(root, issue).unlink(missing_ok=True)
        except (OSError, Refusal):  # best effort: the original failure is what the user must see
            pass
        release_ports(root, issue, keep=[entry['port'] for entry in left])
        if left and isinstance(failure, Refusal):
            names = ', '.join(f'{entry["name"]} (pid {entry["pid"]})' for entry in left)
            raise Refusal(f'{failure} Não foi possível derrubar: {names}; rode stop para tentar de novo.',
                          failure.process, failure.category,
                          {'left': [{'name': entry['name'], 'pid': entry['pid']} for entry in left]})
        raise
    return {'ok': True, 'issue': issue, 'processes': started,
            'reservas_compartilhadas': ports_location(root)[1]}


def read_registry(root, issue):
    path = registry_path(root, issue)
    name = relative(Path(root), path)
    require(path.is_file(), f'Não há registro de processos para a issue {issue} nesta worktree.')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        require(isinstance(record.get('processes'), list), 'registro inválido')
        for entry in record['processes']:
            require(valid_pid(entry.get('pid')), 'registro inválido')
    except (OSError, ValueError, AttributeError, Refusal):
        raise Refusal(f'O registro da issue {issue} ({name}) está ilegível ou inválido, então start, status e '
                      f'stop não conseguem usá-lo. Confira se há processos da issue em execução, encerre-os '
                      f'à mão e apague {name}.')
    return record


def status(root, issue):
    record = read_registry(root, issue)
    # main masks the output: a secret that sits in a health URL query shows up as [redacted] here too
    processes = [dict(entry, alive=same_process(entry)) for entry in record['processes']]
    return {'ok': True, 'issue': issue, 'running': all(entry['alive'] for entry in processes),
            'processes': processes}


def stop(root, issue):
    """Stop the issue's processes under the same lock as start: a start in progress makes stop refuse."""
    lock = acquire_lock(root, issue)
    try:
        return stop_locked(root, issue)
    finally:
        release_lock(lock)


def stop_locked(root, issue):
    try:
        record = read_registry(root, issue)
    except Refusal as refusal:
        if not registry_path(root, issue).is_file():
            # no record at all (a start that died early): nothing to kill, but its reservations must not leak;
            # an unreadable record may still describe live processes, so then the reservations stay
            refusal.extra = dict(refusal.extra, reservas_liberadas=release_ports(root, issue))
        raise
    result = stop_entries(root, record['processes'], registry_path(root, issue),
                          lambda: release_ports(root, issue), 'stop')
    return {'ok': True, 'issue': issue, **result}


def stop_entries(root, entries, registry_file, release, retry):
    """Kill the recorded processes ({name, pid, identity} each), remove the record and release the ports.

    Every identity is checked first, so a refusal kills nothing. `release` frees the port reservations and returns
    them; `retry` names the command to run again. Returns {'processes': [...], 'reservas_liberadas': [...]}.
    """
    name = relative(Path(root), registry_file)
    stopped, left = [], []
    for entry in entries:  # check every identity first, so a refusal kills nothing
        if pid_alive(entry['pid']):
            recorded, current = entry.get('identity'), process_identity(entry['pid'])
            require(recorded not in (None, UNKNOWN_IDENTITY) and current is not None,
                    f'Identidade desconhecida do processo {entry.get("name")} (pid {entry["pid"]}): '
                    'o registro não prova que o pid ainda é o processo iniciado, então ele não foi encerrado '
                    'para não derrubar um processo alheio. Confira e encerre manualmente; depois apague '
                    f'{name} à mão.')
    for entry in entries:
        item = {'name': entry.get('name'), 'pid': entry['pid']}
        if not pid_alive(entry['pid']):
            stopped.append(dict(item, stopped=True))
        elif process_identity(entry['pid']) != entry.get('identity'):
            # the pid now belongs to another process: the recorded one is already gone
            stopped.append(dict(item, stopped=True, reused=True))
        else:
            # Limit: only the recorded root pid is confirmed dead; grandchildren rely on taskkill /T
            # (Windows) or the process group (POSIX), since the standard library cannot list them.
            try:
                dead = kill_tree(entry['pid'])
            except Exception:
                dead = False
            stopped.append(dict(item, stopped=dead))
            if not dead:
                left.append(item)
    if left:
        raise Refusal('Nem todos os processos foram encerrados; o registro foi mantido para nova tentativa.',
                      extra={'left': left, 'processes': stopped})
    try:
        registry_file.unlink()
    except OSError as error:
        detail = error.strerror or type(error).__name__
        raise Refusal(f'Os processos foram encerrados, mas não foi possível apagar o registro {name} ({detail}). '
                      f'Apague-o à mão ou rode {retry} de novo.',
                      extra={'processes': stopped, 'reservas_liberadas': release()}) from error
    return {'processes': stopped, 'reservas_liberadas': release()}


def preview_stop(config_file, root):
    """Stop the preview's processes and relays under the preview lock; an issue's stop never reaches them. Like
    status, it works from the record alone, with or without the `preview` block in the config."""
    load_preview_block(config_file, root, need_processes=False)
    lock = acquire_lock_file(root, preview_lock_path(root), 'da prévia')
    try:
        try:
            record = read_preview_registry(root)
        except Refusal as refusal:
            if not preview_registry_path(root).is_file():
                refusal.extra = dict(refusal.extra, reservas_liberadas=release_ports(root, PREVIEW_ISSUE))
            raise
        result = stop_entries(root, preview_kill_list(record['processes']), preview_registry_path(root),
                              lambda: release_ports(root, PREVIEW_ISSUE), 'preview stop')
        return {'ok': True, 'worktree': record.get('worktree'), 'branch': record.get('branch'), **result}
    finally:
        release_lock(lock)


# ---------------------------------------------------------------- preview refresh (issue 34, slice 2)

def git(cwd, *args, timeout=GIT_SECONDS):
    """(exit code, stdout, stderr) of `git -C <cwd> ...`: an argv list found by shutil.which, never a shell, no
    prompts, with a deadline."""
    executable = shutil.which('git')
    require(executable, 'O git não foi encontrado no PATH; o preview refresh precisa dele.')
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_MERGE_AUTOEDIT='no')
    try:
        done = subprocess.run([executable, '-C', str(cwd), *args], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, stdin=subprocess.DEVNULL, env=environment)
    except (OSError, subprocess.SubprocessError):
        raise Refusal(f'O git não respondeu a `git {args[0]}` (ausente, ou além do prazo de {timeout} s).')
    return done.returncode, done.stdout, done.stderr


def git_text(text):
    """Git's own text as one line of at most 200 characters (main masks it on output)."""
    return ' '.join(text.split())[:200] or 'sem detalhe'


def plain_branch(value):
    """A local branch name Git accepts and no argv can mistake for an option: BRANCH_NAME (starts with a letter or
    digit), no "..", "//" or component starting with "." or ending in ".lock", and no trailing "/" or "."."""
    return (isinstance(value, str) and bool(BRANCH_NAME.fullmatch(value)) and '..' not in value and '//' not in value
            and not value.endswith(('/', '.')) and not any(part.startswith('.') or part.endswith('.lock')
                                                            for part in value.split('/')))


def git_commit(cwd, ref):
    """The commit `ref` names in the repository of `cwd`, or None."""
    code, out, _ = git(cwd, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
    return out.strip() if code == 0 and re.fullmatch(r'[0-9a-f]{40,64}', out.strip()) else None


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


def registered_worktrees(root):
    """{path key: branch name or None} of every worktree Git knows in the repository of `root`."""
    code, out, err = git(root, 'worktree', 'list', '--porcelain')
    require(code == 0, f'O git não listou as worktrees do repositório: {git_text(err)}')
    found, current = {}, None
    for line in out.splitlines():
        if line.startswith('worktree '):
            current = path_key(line[len('worktree '):])
            found[current] = None
        elif line.startswith('branch refs/heads/') and current is not None:
            found[current] = line[len('branch refs/heads/'):]
    return found


def tracked_changes(worktree):
    code, out, err = git(worktree, 'status', '--porcelain', '--untracked-files=no')
    require(code == 0, f'O git não leu o estado da worktree da prévia: {git_text(err)}')
    return [line for line in out.splitlines() if line.strip()]


def check_refresh(block, root, branches, base):
    """Every refusal of `preview refresh` that needs no change: run before the preview is stopped, so a refused
    refresh leaves the preview as it was. Returns (worktree path, exists, base commit, {branch: commit})."""
    preview_branch = block['branch']
    require(plain_branch(base), '--base precisa ser um nome simples de branch local (por exemplo main).',
            category=USAGE)
    require(base != preview_branch, f'A base não pode ser a própria branch da prévia ({preview_branch}).',
            category=USAGE)
    for name in branches:
        require(plain_branch(name), f'--branch {name} não é um nome simples de branch local.', category=USAGE)
        require(name not in (preview_branch, base), f'--branch {name} não pode ser a branch da prévia nem a base: '
                'passe só as branches das issues em andamento.', category=USAGE)
    require(len(set(branches)) == len(branches), 'Cada --branch pode aparecer uma vez só.', category=USAGE)
    code, _, _ = git(root, 'rev-parse', '--show-toplevel')
    require(code == 0, 'O --root não é uma worktree Git; o preview refresh precisa do repositório.', category=USAGE)
    base_commit = git_commit(root, f'refs/heads/{base}')
    require(base_commit, f'A branch base {base} não existe localmente.', category=USAGE)
    commits = {}
    for name in branches:
        commits[name] = git_commit(root, f'refs/heads/{name}')
        require(commits[name], f'A branch {name} não existe localmente; passe em --branch só branches de issue que '
                'existem neste repositório.', category=USAGE)
    worktree = Path(root).resolve() / block['worktree']
    known = registered_worktrees(root)
    here = path_key(worktree)
    elsewhere = [path for path, branch in known.items() if branch == preview_branch and path != here]
    require(not elsewhere, f'A branch da prévia ({preview_branch}) está em uso em outra worktree; o refresh só a '
            'refaz na worktree da prévia. Confira preview.branch no config.', category=USAGE)
    exists = worktree.exists()
    if not exists and git_commit(root, f'refs/heads/{preview_branch}'):
        # `worktree add --force -B` would move it: only a branch the preview's own record names may be redone
        require(recorded_preview_branch(root) == preview_branch, f'A branch {preview_branch} já existe e não é da '
                'prévia (o registro da prévia não a nomeia), e a worktree da prévia não existe: o refresh a moveria '
                'para a base. Escolha outro nome em preview.branch ou, se ela não guarda nada, apague a branch à mão.',
                category=USAGE)
    if exists:
        require(worktree.is_dir() and here in known, f'{block["worktree"]} existe, mas não é uma worktree deste '
                'repositório; o refresh não toca nela. Confira preview.worktree no config.', category=USAGE)
        require(known[here] == preview_branch, f'A worktree da prévia ({block["worktree"]}) não está na branch '
                f'{preview_branch}; o refresh não toca nela. Confira preview.branch no config.', category=USAGE)
        require(not tracked_changes(worktree) and git_commit(worktree, 'MERGE_HEAD') is None,
                'A worktree da prévia tem alterações; ela é refeita a cada refresh, então nada se edita nela. '
                f'Confira {block["worktree"]} e desfaça as alterações antes de um novo refresh.', category=USAGE)
    return worktree, exists, base_commit, commits


def recorded_preview_branch(root):
    """The `branch` the preview record names, or None (no record, unreadable, or without it)."""
    try:
        record = json.loads(preview_registry_path(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return record.get('branch') if isinstance(record, dict) else None


def recreate_preview_worktree(block, root, worktree, exists, base_commit):
    """The preview branch is reset to the base commit inside the preview worktree (`checkout -B`), or the worktree is
    added on it; the local main and the issue branches are never written."""
    if exists:
        code, _, err = git(worktree, 'checkout', '-q', '-B', block['branch'], base_commit)
    else:
        with io_guard('criar a pasta da worktree da prévia'):
            worktree.parent.mkdir(parents=True, exist_ok=True)
        code, _, err = git(root, 'worktree', 'add', '-q', '--force', '-B', block['branch'], str(worktree), base_commit)
    require(code == 0, f'O git não refez a worktree da prévia na base: {git_text(err)}')


def merge_branches(block, worktree, branches, commits):
    """Merge each issue branch, in order, into the preview branch; a conflict is aborted and refused."""
    merged = []
    for name in branches:
        before = git_commit(worktree, 'HEAD')
        # the commit check_refresh read (the one recorded in `merged`), never the branch read again: a branch that
        # moved meanwhile, or a tag with the same name, cannot change what enters the preview
        code, _, err = git(worktree, 'merge', '--no-ff', '--no-edit', '-m',
                           f"Merge branch '{name}' into {block['branch']}", commits[name])
        if code == 0:
            merged.append({'branch': name, 'commit': commits[name]})
            continue
        _, unmerged, _ = git(worktree, 'diff', '--name-only', '--diff-filter=U')
        files = sorted(line.strip() for line in unmerged.splitlines() if line.strip())
        conflicted = bool(files) or git_commit(worktree, 'MERGE_HEAD') is not None
        if conflicted:
            git(worktree, 'merge', '--abort')
        require(not tracked_changes(worktree) and git_commit(worktree, 'MERGE_HEAD') is None
                and git_commit(worktree, 'HEAD') == before,
                f'O merge de {name} na branch da prévia falhou e a worktree da prévia não voltou limpa a '
                f'{(before or "?")[:7]}; confira {block["worktree"]} à mão.')
        if not conflicted:
            raise Refusal(f'O git não mesclou {name} na branch da prévia: {git_text(err)}. A prévia ficou fora do ar.',
                          extra={'branch': name, 'merged': merged})
        raise Refusal(f'O merge de {name} na branch da prévia ({block["branch"]}) tem conflito em: '
                      f'{", ".join(files) or "(arquivos não listados pelo git)"}. O merge foi desfeito, a worktree da '
                      'prévia ficou limpa e a prévia não foi subida de novo: pergunte ao usuário como seguir.',
                      extra={'conflict': True, 'branch': name, 'files': files, 'merged': merged})
    return merged


def preview_refresh(config_file, root, branches, base):
    block = load_preview_block(config_file, root)
    lock = acquire_lock_file(root, preview_lock_path(root), 'da prévia')
    try:
        return preview_refresh_locked(block, config_file, root, branches, base)
    finally:
        release_lock(lock)


def preview_refresh_locked(block, config_file, root, branches, base):
    """Stop the preview, redo its branch from the local base, merge the issue branches in progress and bring it up.

    Git runs as argv lists without a shell; it never pushes, never rebases, never forces a merge and writes no branch
    but `preview.branch`. A conflict is aborted (nothing comes up); a broken build is torn down and refused with its
    log (`launch_preview`).
    """
    worktree, exists, base_commit, commits = check_refresh(block, root, branches, base)
    stopped = []
    if preview_registry_path(root).is_file():
        record = read_preview_registry(root)
        stopped = stop_entries(root, preview_kill_list(record['processes']), preview_registry_path(root),
                               lambda: release_ports(root, PREVIEW_ISSUE), 'preview refresh')['processes']
    recreate_preview_worktree(block, root, worktree, exists, base_commit)
    merged = merge_branches(block, worktree, branches, commits)
    contents = {'base': base, 'baseCommit': base_commit, 'merged': merged}
    result = launch_preview(block, config_file, root, contents)
    return dict(result, **contents, stopped=stopped)


def preview(action, config_file, root, branches=None, base=None):
    require(action is not None, 'preview precisa da ação: preview start, preview refresh, preview status ou '
            'preview stop.', category=USAGE)
    require(action == 'refresh' or (branches is None and base is None),
            '--branch e --base só valem para preview refresh.', category=USAGE)
    if action == 'start':
        return preview_start(config_file, root)
    if action == 'refresh':
        return preview_refresh(config_file, root, branches or [], base or DEFAULT_BASE)
    if action == 'status':
        return preview_status(config_file, root)
    return preview_stop(config_file, root)


def run(operation, config_file, root, issue, action=None, log=None, branches=None, base=None):
    """Dispatch one operation; the flags each one needs are refused as `uso` when missing (argparse only
    requires --config, shared by all)."""
    if operation != 'preview':
        require(branches is None and base is None, '--branch e --base só valem para preview refresh.',
                category=USAGE)
    if operation == 'relay':
        require(log, 'relay precisa de --log <arquivo>.', category=USAGE)
        return relay(config_file, log)
    require(root, f'{operation} precisa de --root <worktree>.', category=USAGE)
    require(log is None, '--log só vale para relay.', category=USAGE)
    if operation == 'preview':
        return preview(action, config_file, root, branches, base)
    require(action is None, f'{operation} não aceita uma ação depois do nome; a ação é só de preview.',
            category=USAGE)
    require(issue is not None, f'{operation} precisa de --issue <n>.', category=USAGE)
    if operation == 'start':
        return start(config_file, root, issue)
    if operation == 'status':
        return status(root, issue)
    return stop(root, issue)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('operation', choices=('start', 'stop', 'status', 'preview', 'relay'))
    parser.add_argument('action', nargs='?', choices=('start', 'refresh', 'status', 'stop'),
                        help='só para preview: start, refresh, status ou stop')
    parser.add_argument('--config', required=True)
    parser.add_argument('--root', help='worktree da issue (start, stop, status) ou worktree principal (preview)')
    parser.add_argument('--issue', type=int, help='número da issue (start, stop, status)')
    parser.add_argument('--log', help='só para relay: arquivo de log a acrescentar')
    parser.add_argument('--branch', action='append', help='só para preview refresh: branch de issue em andamento a '
                        'mesclar na branch da prévia (repetível, na ordem dada)')
    parser.add_argument('--base', help=f'só para preview refresh: branch base local (padrão {DEFAULT_BASE})')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        result = run(args.operation, args.config, args.root, args.issue, args.action, args.log, args.branch,
                     args.base)
        code = 0
    except (Refusal, OSError) as failure:
        # the safety net: an I/O error that escaped every specific handler is still a refusal with JSON
        refusal = failure if isinstance(failure, Refusal) else io_failure('executar a operação', failure)
        result = {'ok': False, 'error': str(refusal), 'category': refusal.category}
        if refusal.process:
            result['failedProcess'] = refusal.process
        result.update(refusal.extra)
        code = 1
    print(json.dumps(scrub(result), ensure_ascii=False))  # the single masking pass of the output
    return code


if __name__ == '__main__':
    sys.exit(main())
