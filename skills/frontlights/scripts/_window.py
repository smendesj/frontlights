"""`serve.py window`: the visible Chrome window of the watched run (issue 8).

  open    `--issue <n> --strip "ANTES: origin/main" [--base-url <url>] [--account 1|2]`: Chrome, visible,
          maximized, in a disposable profile, with `--remote-debugging-port`, driven over CDP by the Playwright the
          project already has (in this order: `browserTest.playwright`, `PLAYWRIGHT_PATH`, the `node_modules` of the
          worktree or of the main worktree, the npx cache). With it: `viewport: null`, the strip on every page by an
          init script, the login by `browserTest.login` (`user`, `password`, `submit` selectors, optional `url`) or by
          the conductor, and a look at whether the whole page fits (`fits`, `checkShot`, an image in the disposable
          profile that is never kept). Without any Playwright: the same Chrome with the CDP port, and the conductor
          drives it (no strip from here). Without Chrome either: an infrastructure refusal. Records `cdpUrl`, `pid`,
          `profileDir` in `.frontlights/issues/<n>/browser/window.json` of the main worktree. Never installs anything.
  attach  the window of `window.json` when it is alive; otherwise it reopens it on the same base and strip, with no
          question (`reopened: true`).
  hold    `[--minutes none|<n>]`: the holder, in the foreground (whoever drives the pass runs it in the background). It
          keeps the strip on new pages and exits when the window closes (`window close` by the conductor, or the user:
          `disconnected`) or, given minutes, when they end (then it closes the window itself); prints `ended_by`.
          Default none: the passes and the free test never wait on a timer.
  shot    `--pass antes|depois --criterion S<n>` (or `--name <label>` for the screens of the artifact): one print in
          the folder `progress_report.py evidence-dir` gives (the sprint folder), `antes-<cover>-S<n>.png`.
  close   stops only the Chrome this helper started (same pid and start time) and removes its profile.
  brief   `--pass antes|depois --criteria S1,S2`: fills the placeholders of `references/browser-conductor.md` (the
          window, the strip, the criteria, the folders, the commands) and writes it as `brief-<pass>.md` beside the
          record; prints its path, so whoever conducts reads it there.

Before the issue has a number (a grilling that starts from a request), leave `--issue` out: the window record and the
prints go to `.frontlights/evidencias-pendentes/` (`antes-pendente-<label>.png`), and the first window command with
`--issue <n>` moves them into the issue's folders, renamed with the number (`pendentesMovidos`).

The window never judges a pass: passed or failed is the session's and the user's. It starts no server: with
`browserTest.processes` the servers are `serve start`'s; without them the session brings the environment up itself
(`ambiente: sessao_sobe`), never the user.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import _cli
import serve
from serve import Refusal, require, INFRASTRUCTURE, USAGE

HERE = Path(__file__).resolve().parent
DRIVER = HERE / 'window_driver.cjs'
PROFILE_PREFIX = 'frontlights-janela-'
PENDING = Path('.frontlights') / 'evidencias-pendentes'
PENDING_LABEL = 'pendente'
CDP_WAIT_SECONDS = 20
DRIVER_SECONDS = 120
HOLD_POLL_SECONDS = 1
STRIP_PREFIXES = ('ANTES: ', 'DEPOIS: branch ', 'MAIN LOCAL: teste livre')
STRIP_MAX = 100
CRITERION = re.compile(r'S[1-9][0-9]{0,2}')   # the slice label S<k>, as `slice open` and `closeout tick` take it
LABEL = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')
PASSES = ('antes', 'depois')
OPERATIONS = ('open', 'attach', 'hold', 'shot', 'close', 'brief')
PLAYWRIGHT_PACKAGES = ('playwright', 'playwright-core', os.path.join('@playwright', 'test'))
CHROME_CANDIDATES_NT = (
    ('PROGRAMFILES', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ('PROGRAMFILES(X86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ('LOCALAPPDATA', 'Google', 'Chrome', 'Application', 'chrome.exe'),
)
CHROME_NAMES = ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome')
CHROME_MAC = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


# ---------------------------------------------------------------- where things are

def issue_folder(root, issue):
    return Path(root) / '.frontlights' / 'issues' / str(issue) / 'browser'


def state_path(root, issue):
    """window.json: in the issue's browser folder, or in the pending folder before the issue has a number."""
    return (issue_folder(root, issue) if issue else Path(root) / PENDING) / 'window.json'


def read_state(root, issue):
    path = state_path(root, issue)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_state(root, issue, state):
    serve.write_json_atomic(state, state_path(root, issue))


def resolve_issue(value, tree, root):
    """The issue given, or the charter's for the worktree; None (pending mode) when neither exists."""
    if value is not None:
        return _cli.issue_number(value, tree, root)
    try:
        return _cli.issue_number(None, tree, root)
    except _cli.UsageError:
        return None


def move_pending(root, issue, evidence_dir):
    """Prints taken before the issue had a number go into the issue's evidence folder, renamed with the number;
    a pending window.json goes into the issue's browser folder. Returns the names moved."""
    pending = Path(root) / PENDING
    if not issue or not pending.is_dir():
        return []
    moved = []
    for item in sorted(pending.iterdir()):
        if item.suffix.lower() == '.png' and f'-{PENDING_LABEL}-' in item.name:
            target = Path(evidence_dir) / item.name.replace(f'-{PENDING_LABEL}-', f'-{issue}-', 1)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
            moved.append(target.name)
    window = pending / 'window.json'
    if window.is_file() and not state_path(root, issue).exists():
        state_path(root, issue).parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(window.read_text(encoding='utf-8'))
        data['issue'] = issue
        write_state(root, issue, data)
        window.unlink()
        moved.append('window.json')
    return moved


def evidence_dir(root, issue):
    """The folder of the run's prints: `progress_report.py evidence-dir` (the sprint folder when the config names
    it), or the pending folder before the issue has a number."""
    if not issue:
        folder = Path(root) / PENDING
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)
    import progress_report
    result = progress_report.run('evidence-dir', str(root), issue=issue)
    require(result.get('ok'), f'evidence-dir recusou: {result.get("message")}', category=USAGE)
    return result['evidenceDir']


# ---------------------------------------------------------------- what the project already has

def find_playwright(config, tree, root):
    """(node, package path, source) of the first Playwright found, or None. Nothing is ever installed."""
    node = shutil.which('node')
    if not node:
        return None
    block = config.get('browserTest') if isinstance(config, dict) else None
    candidates = []
    declared = block.get('playwright') if isinstance(block, dict) else None
    if isinstance(declared, str) and declared.strip():
        path = Path(declared)
        candidates.append(('browserTest.playwright', path if path.is_absolute() else Path(tree) / path))
    if os.environ.get('PLAYWRIGHT_PATH'):
        candidates.append(('PLAYWRIGHT_PATH', Path(os.environ['PLAYWRIGHT_PATH'])))
    for base in dict.fromkeys([Path(tree), Path(root)]):
        for package in PLAYWRIGHT_PACKAGES:
            candidates.append(('node_modules', base / 'node_modules' / package))
    for cache in npx_caches():
        for found in sorted(cache.glob('*/node_modules/playwright'), reverse=True):
            candidates.append(('npx', found))
    for source, path in candidates:
        if (path / 'package.json').is_file() or (path.is_file() and path.suffix in ('.js', '.cjs')):
            return node, str(path), source
    return None


def npx_caches():
    found = []
    if os.environ.get('LOCALAPPDATA'):
        found.append(Path(os.environ['LOCALAPPDATA']) / 'npm-cache' / '_npx')
    found.append(Path.home() / '.npm' / '_npx')
    return [path for path in found if path.is_dir()]


def find_chrome(playwright=None):
    """The argv prefix of a Chrome to start: CHROME_PATH, the usual install places, or the Chromium of the
    Playwright found. None when there is none."""
    if os.environ.get('CHROME_PATH') and Path(os.environ['CHROME_PATH']).is_file():
        return [os.environ['CHROME_PATH']]
    if os.name == 'nt':
        for variable, *parts in CHROME_CANDIDATES_NT:
            if os.environ.get(variable):
                path = Path(os.environ[variable], *parts)
                if path.is_file():
                    return [str(path)]
    elif Path(CHROME_MAC).is_file():
        return [CHROME_MAC]
    for name in CHROME_NAMES:
        if shutil.which(name):
            return [shutil.which(name)]
    if playwright:
        answer = run_driver(playwright, 'executable', {})
        if answer.get('ok') and answer.get('executable') and Path(answer['executable']).is_file():
            return [answer['executable']]
    return None


def run_driver(playwright, command, payload, env=None, timeout=DRIVER_SECONDS):
    """Run `node window_driver.cjs <command>` with the JSON payload on stdin; its last JSON line, or a refusal."""
    node, package, _ = playwright
    data = dict(payload, playwright=package)
    try:
        done = subprocess.run([node, str(DRIVER), command], input=json.dumps(data), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout,
                              env=dict(os.environ, **(env or {})))
    except subprocess.TimeoutExpired:
        raise Refusal(f'O driver da janela não respondeu a `{command}` em {timeout} s.', category=INFRASTRUCTURE)
    except OSError as error:
        raise Refusal(f'O Node não rodou o driver da janela: {error}', category=INFRASTRUCTURE)
    for line in reversed(done.stdout.splitlines()):
        try:
            answer = json.loads(line)
        except ValueError:
            continue
        if isinstance(answer, dict):
            return answer
    return {'ok': False, 'error': (done.stderr or 'sem saída')[-400:]}


# ---------------------------------------------------------------- checks of the input

def check_strip(text):
    require(isinstance(text, str) and text.startswith(STRIP_PREFIXES) and len(text) <= STRIP_MAX,
            'A faixa precisa começar por "ANTES: ", "DEPOIS: branch " ou ser "MAIN LOCAL: teste livre", com até '
            f'{STRIP_MAX} caracteres.', category=USAGE)
    require(not re.search(r'[\\@]|[A-Za-z]:[/\\]|^/|\s/', text) and '\n' not in text,
            'A faixa não leva login, senha nem caminho local: só a base ou a branch.', category=USAGE)
    return text


def local_base_url(url):
    parts = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    require(parts and parts.scheme in ('http', 'https') and parts.hostname in serve.LOCAL_HOSTS
            and '@' not in parts.netloc and '{port}' not in url,
            'A janela abre só um endereço local (127.0.0.1, localhost ou ::1), sem {port} por preencher: passe '
            '--base-url com a porta que o serve devolveu.', category=USAGE)
    return url


def account_of(block, account):
    users = block.get('users') if isinstance(block, dict) else None
    if not users:
        return None
    require(isinstance(users, list) and 1 <= account <= len(users) and isinstance(users[account - 1], dict),
            f'browserTest.users não tem a conta {account}.', category=USAGE)
    return users[account - 1]


def read_config(config_file):
    if not config_file:
        return {}
    config = serve.read_config(config_file)
    require(isinstance(config, dict), 'O config precisa ser um objeto JSON.', category=USAGE)
    block = config.get('browserTest')
    if isinstance(block, dict):
        serve.load_secrets(block)
    return config


# ---------------------------------------------------------------- Chrome

def cdp_alive(url):
    try:
        with urllib.request.urlopen(f'{url}/json/version', timeout=2) as answer:
            return answer.status == 200
    except (OSError, ValueError):
        return False


def start_chrome(chrome, profile):
    argv = [*chrome, f'--user-data-dir={profile}', '--remote-debugging-port=0', '--start-maximized',
            '--no-first-run', '--no-default-browser-check', 'about:blank']
    options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008   # DETACHED_PROCESS
    else:
        options['start_new_session'] = True
    try:
        child = subprocess.Popen(argv, **options)
    except OSError as error:
        raise Refusal(f'O Chrome não abriu: {error}', category=INFRASTRUCTURE)
    port_file = Path(profile) / 'DevToolsActivePort'
    deadline = time.monotonic() + CDP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise Refusal(f'O Chrome terminou ao abrir (código {child.returncode}).', category=INFRASTRUCTURE)
        try:
            port = int(port_file.read_text(encoding='utf-8').splitlines()[0])
        except (OSError, ValueError, IndexError):
            time.sleep(0.2)
            continue
        url = f'http://127.0.0.1:{port}'
        if cdp_alive(url):
            return child, url
        time.sleep(0.2)
    serve.kill_tree(child.pid)
    raise Refusal(f'O Chrome não abriu a porta de depuração em {CDP_WAIT_SECONDS} s.', category=INFRASTRUCTURE)


def remove_profile(profile):
    """Remove the disposable profile, only when it is one this helper made (a temporary folder with its prefix)."""
    path = Path(profile or '')
    if not profile or not path.name.startswith(PROFILE_PREFIX):
        return False
    if os.path.normcase(str(path.resolve().parent)) != os.path.normcase(str(Path(tempfile.gettempdir()).resolve())):
        return False
    for _ in range(20):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.2)
    return False


def ours_alive(state):
    return (isinstance(state, dict) and state.get('startedBy') == 'frontlights' and serve.valid_pid(state.get('pid'))
            and serve.same_process({'pid': state['pid'], 'identity': state.get('identity')}))


# ---------------------------------------------------------------- operations

def environment_of(block):
    if isinstance(block, dict) and block.get('processes'):
        return 'serve', None
    return 'sessao_sobe', ('Sem browserTest.processes: a sessão sobe ela mesma a API e o web da árvore em teste, no '
                           'banco local de desenvolvimento, confere que respondem e para o que subiu; nunca pede ao '
                           'usuário que suba. Ofereça declarar os comandos em browserTest.processes.')


def op_open(config_file, root, tree, issue, strip, base_url, account, reopen_of=None):
    started = time.monotonic()
    config = read_config(config_file)
    block = config.get('browserTest') if isinstance(config.get('browserTest'), dict) else {}
    strip = check_strip(strip)
    base_url = local_base_url(base_url or block.get('baseUrl'))
    user = account_of(block, account)
    current = read_state(root, issue)
    if reopen_of is None and ours_alive(current) and cdp_alive(current.get('cdpUrl', '')):
        raise Refusal('A janela desta issue já está aberta; use `serve.py window attach` para reusá-la.',
                      category=USAGE, extra={'cdpUrl': current['cdpUrl'], 'pid': current['pid']})
    folder = evidence_dir(root, issue)
    moved = move_pending(root, issue, folder)
    playwright = find_playwright(config, tree, root)
    chrome = find_chrome(playwright)
    require(chrome, 'Sem Chrome nesta máquina (nem o do Playwright do projeto): a janela não abriu. Nada foi instalado; '
            'é falha de infraestrutura, pergunte ao usuário.', category=INFRASTRUCTURE)
    profile = tempfile.mkdtemp(prefix=PROFILE_PREFIX)
    child, cdp_url = start_chrome(chrome, profile)
    state = {'cdpUrl': cdp_url, 'pid': child.pid, 'identity': serve.process_identity(child.pid) or serve.UNKNOWN_IDENTITY,
             'profileDir': profile, 'startedBy': 'frontlights', 'issue': issue, 'baseUrl': base_url, 'strip': strip,
             'account': account, 'driver': 'playwright' if playwright else 'cdp',
             'playwright': playwright[1] if playwright else None, 'openedAt': serve.now_iso()}
    result = {'ok': True, 'cdpUrl': cdp_url, 'pid': child.pid, 'profileDir': profile, 'driver': state['driver'],
              'playwright': state['playwright'], 'strip': strip, 'issue': issue, 'evidenceDir': folder,
              'state': str(state_path(root, issue))}
    if playwright:
        login = block.get('login') if isinstance(block.get('login'), dict) else None
        env = {}
        if login and user:
            env = {'FRONTLIGHTS_WINDOW_USER': str(user.get('login', '')),
                   'FRONTLIGHTS_WINDOW_PASSWORD': str(user.get('password', ''))}
        check = str(Path(profile) / 'conferencia.png')
        answer = run_driver(playwright, 'open', {'cdpUrl': cdp_url, 'baseUrl': base_url, 'strip': strip,
                                                 'login': login, 'check': check}, env=env)
        if not answer.get('ok'):
            serve.kill_tree(child.pid)
            remove_profile(profile)
            raise Refusal(f'O driver não preparou a janela: {answer.get("error")}', category=INFRASTRUCTURE)
        result.update(fits=answer.get('fits'), checkShot=answer.get('checkShot'), login=answer.get('login'))
        result['message'] = ('Janela aberta com a faixa. Rode agora `serve.py window hold` em segundo plano: a faixa '
                             'acompanha as páginas novas enquanto o holder roda. Olhe o checkShot (não guarde): '
                             'faixa e bordas inteiras, senão ajuste antes do primeiro caso.')
        if answer.get('fits') is False:
            result['message'] += ' fits: false, a página não coube na janela.'
    else:
        result.update(fits=None, checkShot=None, login='condutor')
        result['message'] = ('Sem Playwright no projeto: o Chrome abriu com a porta de depuração (cdpUrl) e quem conduz '
                             'injeta a faixa, faz o login e confere a tela. Nada foi instalado.')
    environment, todo = environment_of(block)
    result['ambiente'] = environment
    if todo:
        result['next'] = todo
    if moved:
        result['pendentesMovidos'] = moved
    if reopen_of is not None:
        result['reopened'] = True
    seconds = round(time.monotonic() - started, 1)
    state['preparoSegundos'] = seconds
    write_state(root, issue, state)
    result['preparoSegundos'] = seconds
    result['message'] = f'preparo: {seconds} s. ' + result['message']
    return result


def op_attach(config_file, root, tree, issue):
    folder = evidence_dir(root, issue) if issue else None
    moved = move_pending(root, issue, folder) if issue else []
    state = read_state(root, issue)
    require(state, 'Nenhuma janela registrada para esta issue: abra com `serve.py window open`.', category=USAGE)
    if ours_alive(state) and cdp_alive(state.get('cdpUrl', '')):
        result = {'ok': True, 'reopened': False, 'cdpUrl': state['cdpUrl'], 'pid': state['pid'],
                  'profileDir': state.get('profileDir'), 'strip': state.get('strip'), 'driver': state.get('driver'),
                  'playwright': state.get('playwright')}
    else:
        remove_profile(state.get('profileDir'))
        result = op_open(config_file, root, tree, issue, state.get('strip'), state.get('baseUrl'),
                         state.get('account') or 1, reopen_of=state)
        result['message'] = 'A janela tinha fechado e foi reaberta na mesma base, sem pergunta. ' + result['message']
    if moved:
        result['pendentesMovidos'] = moved
    return result


def finish(root, issue, state, ended_by):
    """After the window ends: kill what this helper started (if still up), remove the profile, keep the record."""
    killed = ours_alive(state) and serve.kill_tree(state['pid'])
    removed = remove_profile(state.get('profileDir'))
    state.update(closedAt=serve.now_iso(), endedBy=ended_by)
    write_state(root, issue, state)
    return bool(killed), removed


def op_hold(root, issue, minutes):
    state = read_state(root, issue)
    require(state, 'Nenhuma janela registrada para esta issue: abra com `serve.py window open`.', category=USAGE)
    require(ours_alive(state), 'A janela registrada não está aberta: use `serve.py window attach`.', category=USAGE)
    started = time.monotonic()
    ended = None
    if state.get('driver') == 'playwright' and state.get('playwright') and shutil.which('node'):
        timeout = None if minutes is None else minutes * 60 + DRIVER_SECONDS
        answer = run_driver((shutil.which('node'), state['playwright'], 'window.json'), 'hold',
                            {'cdpUrl': state['cdpUrl'], 'strip': state.get('strip'), 'minutes': minutes},
                            timeout=timeout or 10 ** 7)
        ended = answer.get('ended_by') if answer.get('ok') else None
    if ended is None:   # no driver, or it failed: the holder still watches the window itself
        deadline = None if minutes is None else started + minutes * 60
        while ours_alive(state) and (deadline is None or time.monotonic() < deadline):
            time.sleep(HOLD_POLL_SECONDS)
        ended = 'disconnected' if not ours_alive(state) else 'prazo'
    killed, _ = finish(root, issue, state, ended)
    message = ('A janela fechou (o window close de quem conduz ou o usuário).' if ended == 'disconnected'
               else f'Os {minutes} minutos acabaram e a janela foi fechada pelo holder.')
    return {'ok': True, 'ended_by': ended, 'closedByHolder': killed, 'seconds': round(time.monotonic() - started),
            'message': message + ' Nenhum dos dois é resposta à pergunta: siga para o relato e a pergunta.'}


def shot_name(issue, cover, pass_, criterion, name):
    require(pass_ in PASSES, '--pass precisa ser antes ou depois.', category=USAGE)
    require(bool(criterion) != bool(name), 'Passe --criterion S<n> (um print por critério) ou --name <rótulo> (telas do '
            'artefato), um dos dois.', category=USAGE)
    if criterion:
        require(CRITERION.fullmatch(criterion or ''), '--criterion é S<n>, como S2.', category=USAGE)
    else:
        require(LABEL.fullmatch(name or ''), '--name é um rótulo curto em minúsculas (letras, números e hífen).',
                category=USAGE)
    owner = str(cover or issue) if issue else PENDING_LABEL
    return f'{pass_}-{owner}-{criterion or name}.png'


def op_shot(root, issue, pass_, criterion, name, cover):
    file_name = shot_name(issue, cover, pass_, criterion, name)
    folder = evidence_dir(root, issue)
    moved = move_pending(root, issue, folder)
    state = read_state(root, issue)
    require(state and ours_alive(state), 'A janela não está aberta: use `serve.py window attach` (reabre na base sem '
            'pergunta) e tire o print de novo.', category=USAGE)
    if not (state.get('driver') == 'playwright' and state.get('playwright') and shutil.which('node')):
        raise Refusal('Sem Playwright no projeto: tire o print pelo CDP (cdpUrl) e salve em evidenceDir com o nome dado.',
                      category=INFRASTRUCTURE,
                      extra={'evidenceDir': folder, 'file': file_name, 'cdpUrl': state.get('cdpUrl')})
    path = str(Path(folder) / file_name)
    answer = run_driver((shutil.which('node'), state['playwright'], 'window.json'), 'shot',
                        {'cdpUrl': state['cdpUrl'], 'path': path})
    require(answer.get('ok'), f'O print não foi tirado: {answer.get("error")}', category=INFRASTRUCTURE)
    result = {'ok': True, 'file': file_name, 'path': path, 'evidenceDir': folder, 'pass': pass_,
              'criterion': criterion, 'name': name,
              'message': 'Olhe o print antes de guardá-lo: só dados de teste, sem senha, sem pessoa real, sem caminho.'}
    if issue and criterion:   # the same schema as `browser-gate record` (docs/protocol.md, "Teste no navegador")
        import browser_gate
        record = issue_folder(root, issue) / 'result.json'
        browser_gate.record_print(record, pass_, criterion, file_name, folder)
        result['record'] = str(record)
    if moved:
        result['pendentesMovidos'] = moved
    return result


def op_close(root, issue):
    state = read_state(root, issue)
    require(state, 'Nenhuma janela registrada para esta issue.', category=USAGE)
    if state.get('closedAt') and not ours_alive(state):
        return {'ok': True, 'closed': False, 'message': 'A janela já estava fechada; nada foi parado.'}
    ours = ours_alive(state)
    killed, removed = finish(root, issue, state, 'close')
    return {'ok': True, 'closed': killed, 'profileRemoved': removed,
            'message': ('Fechei só o Chrome que este script abriu (mesmo pid e mesmo início).' if ours else
                        'O pid registrado não é mais o Chrome que este script abriu: nada foi parado.')}


def run(args, root, tree, config_file):
    issue = resolve_issue(args.issue, tree, root)
    if args.window_op == 'open':
        require(args.strip, 'window open precisa de --strip, como --strip "ANTES: origin/main".', category=USAGE)
        return op_open(config_file, root, tree, issue, args.strip, args.base_url, args.account)
    if args.window_op == 'attach':
        return op_attach(config_file, root, tree, issue)
    if args.window_op == 'hold':
        return op_hold(root, issue, args.minutes)
    if args.window_op == 'shot':
        return op_shot(root, issue, args.pass_, args.criterion, args.name, args.cover)
    if args.window_op == 'brief':
        return op_brief(config_file, root, issue, args.pass_, args.criteria, args.strip, args.base_url, args.account)
    return op_close(root, issue)


ENDINGS = {
    'antes': ('The ANTES window stays open while the slices are worked; its holder has no time limit. Once the last '
              'criterion has its print and its record, close it at once with `window close`, with no wait, and tell the '
              'session, which stops the ANTES server; a window closed before that (by the user, a crash or the end of '
              'a session) reopens on the base with `window attach`, with no question, when the next capture is due. '
              'Tell the session which criteria still lack their ANTES.'),
    'depois': ('Once the last criterion has its print and its record, close the window at once with `window close`, '
               'with no wait, then return your report: the session asks what comes next from the prints, never holding '
               'the window open for it.'),
}


def op_brief(config_file, root, issue, pass_, criteria, strip, base_url, account):
    """Fill references/browser-conductor.md for one pass and write it beside the record; print its path."""
    require(pass_ in PASSES, 'window brief precisa de --pass antes ou --pass depois.', category=USAGE)
    names = [name.strip() for name in (criteria or '').split(',') if name.strip()]
    require(names and all(CRITERION.fullmatch(name) for name in names),
            'window brief precisa de --criteria com as caixas da passada, como S1,S2,S3.', category=USAGE)
    config = read_config(config_file)
    block = config.get('browserTest') if isinstance(config.get('browserTest'), dict) else {}
    state = read_state(root, issue) or {}
    strip = check_strip(strip or state.get('strip') or ('ANTES: origin/main' if pass_ == 'antes' else ''))
    base_url = local_base_url(base_url or state.get('baseUrl') or block.get('baseUrl'))
    live = ours_alive(state) and cdp_alive(state.get('cdpUrl', ''))
    folder = evidence_dir(root, issue)
    record = issue_folder(root, issue) / 'result.json' if issue else Path(root) / PENDING / 'result.json'
    values = {
        'PASS_NAME': pass_.upper(), 'PASS': pass_, 'ISSUE': str(issue) if issue else '(sem número: omita --issue)',
        'STRIP': strip, 'BASE_URL': base_url, 'ACCOUNT': f'conta {account}', 'ACCOUNT_NUMBER': str(account),
        'CRITERIA': ', '.join(names), 'EVIDENCE_DIR': folder, 'RECORD': str(record),
        'WINDOW': (f'open, cdpUrl {state["cdpUrl"]}' if live else 'not open: step 1 opens it'),
        'SCRIPTS': str(HERE), 'HOLD': 'none',
        'PLAYWRIGHT': state.get('playwright') or 'the one `window open` reports in `playwright`',
        'ENDING': ENDINGS[pass_],
    }
    text = (HERE.parent / 'references' / 'browser-conductor.md').read_text(encoding='utf-8')
    for key, value in values.items():
        text = text.replace('{{' + key + '}}', value)
    left = sorted(set(re.findall(r'\{\{([A-Z_]+)\}\}', text)))
    require(not left, f'O brief ficou com marcadores sem valor: {", ".join(left)}.')
    target = (issue_folder(root, issue) if issue else Path(root) / PENDING) / f'brief-{pass_}.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serve.protect(text), encoding='utf-8')
    return {'ok': True, 'brief': str(target), 'pass': pass_, 'criteria': names, 'window': 'aberta' if live else 'fechada',
            'message': f'Despache quem conduz com "leia {target} e siga"; o texto não precisa entrar no seu contexto.'}


def minutes_value(text):
    if text in ('none', 'sem', 'nenhum'):
        return None
    try:
        value = int(text)
    except ValueError:
        raise _cli.UsageError('--minutes é um número de minutos ou none', hint='--minutes none (o padrão)')
    if value < 1:
        raise _cli.UsageError('--minutes precisa ser 1 ou mais, ou none', hint='--minutes none')
    return value


def parser():
    p = _cli.JsonParser(prog='serve.py window', description='A janela visível do teste assistido (issue 8).')
    p.add_argument('window_op', choices=OPERATIONS)
    p.add_argument('--config', help='padrão: o .frontlights/config.json da worktree principal')
    p.add_argument('--root', help='worktree principal, onde ficam os registros (padrão: a principal)')
    p.add_argument('--tree', help='worktree da passada, onde se procura o node_modules (padrão: a da pasta atual)')
    p.add_argument('--issue', help='número da issue; sem ele e sem charter, modo pendente (antes do número)')
    p.add_argument('--strip', help='open: "ANTES: origin/main", "DEPOIS: branch <nome>" ou "MAIN LOCAL: teste livre"')
    p.add_argument('--base-url', help='open: endereço local servido (padrão: browserTest.baseUrl)')
    p.add_argument('--account', type=int, choices=(1, 2), default=1, help='open: conta de browserTest.users')
    p.add_argument('--minutes', type=minutes_value, default=None, help='hold: none (padrão; a janela fecha pelo window close) ou minutos')
    p.add_argument('--pass', dest='pass_', choices=PASSES, help='shot e brief: antes ou depois')
    p.add_argument('--criterion', help='shot: S<n>, o critério cujo Fluxo a passada percorre')
    p.add_argument('--name', help='shot: rótulo de uma tela do artefato (no grilling), em vez de --criterion')
    p.add_argument('--cover', type=int, help='shot: a issue de topo da família (padrão: --issue)')
    p.add_argument('--criteria', help='brief: as caixas da passada, como S1,S2,S3')
    return _cli.output_flags(p)


def main(argv):
    """`serve.py window ...`: prints one JSON object; exit 0 done, 1 refusal (category `uso` or `infraestrutura`)."""
    try:
        args = parser().parse_args(argv)
        root = Path(args.root) if args.root else _cli.main_worktree()
        tree = Path(args.tree) if args.tree else _cli.current_tree()
        config_file = _cli.config_path(args.config, root, required=False)
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 1, error=str(error), category=USAGE)
    try:
        result = run(args, root, tree, config_file)
        code = 0
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 1, error=str(error), category=USAGE)
    except (Refusal, OSError) as failure:
        refusal = failure if isinstance(failure, Refusal) else serve.io_failure('operar a janela', failure)
        result = {'ok': False, 'error': str(refusal), 'category': refusal.category, **refusal.extra}
        code = 1
    _cli.emit(json.dumps(serve.scrub(result), ensure_ascii=False), f'window-{args.window_op}', args.full)
    return code
