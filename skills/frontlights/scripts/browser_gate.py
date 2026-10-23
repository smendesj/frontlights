#!/usr/bin/env python3
"""The watched-run gate: has the user been asked about, and answered, the browser test of a batch of work
that changes what they see on the screen?

`review-gate` says whether an independent review still covers the code; this says whether the watched
browser run (`skills/frontlights/references/browser-testing.md`) covers the visible change. It reads the
Git diff, not the plan's text, so a screen change the plan forgot to declare is still caught.

One issue is one decision: the roots are the worktrees of the issue and of its slices (each slice has its own
worktree and branch, cut from the branch of the issue, so a slice root is named with `--stacked <its
branch>=<the branch of its issue>`), and, for a family that already exists, of its sub-issues. The gate
finds the visible changes of each root and compares them with the record of the watched run kept for the
issue (`.frontlights/issues/<n>/browser/result.json`), never one record per slice or branch.

Inputs: `--root` (repeatable) the worktrees, `--base` the approved base of the issue (normally the default
branch), the same for every root, `--config` the project's `.frontlights/config.json` (its
`browserTest.frontPaths` names the visible paths; absent, a conservative default applies, and an absent
config also silences `unconfigured`), `--toca` what the plan's `Toca o frontend:` says (`sim`, `nao` or
`ausente`; `sim` when any issue of a family says it), `--record` the result.json (it may not exist).

What a root changes. Each root is measured from the commit it shares with the base, except an issue stacked on
another branch, which the caller names with `--stacked <its branch>=<the branch its PR targets>` (what the
stacking authorization already records as its base): that issue is measured from the commit it shares with
that branch, so only its own changes count and an API-only child stacked on a parent that changes the screen
is not a visible root. Without `--stacked` every root is measured from the base.
Committed, staged, edited and new files count; files the repository ignores and any `.frontlights` folder
(at any depth) do not; paths are read from the top of each repository, so a `--root` inside a subfolder gives the same answer.

What counts as a visible change. Not a document (`.md`, `.mdx`, `.txt`, `.rst`, or a bare `README`,
`CHANGELOG`, `LICENSE`, `NOTICE`) and not a test (`.spec.`, `.test.`, `.e2e.` in the name, or a file that is
not a screen file inside a folder named `tests`, `test`, `__tests__`, `e2e`, `cypress`, `fixtures`, `spec`,
`specs`, `docs` or `doc`). A screen file (`.html`, `.css`, `.scss`, `.vue`, `.tsx`, `*.component.ts` and
similar) is never excluded by its folder: asking about a documentation page or an HTML fixture is a cheap
mistake (answer `dispensado`), a screen change that passes in silence is not. Then it must match
`frontPaths` (globs from the repository root, at most 50 of at most 200 characters with at most 8 `*` groups
each, no `{}` or `[]`: `*` and `?` stay inside one folder, `**` crosses folders, a folder name covers what is
inside it, the case does not matter; the matcher never backtracks, and a time budget per root turns a
pathological pattern into an error) or, without `frontPaths`, look like a screen
file (the suffixes above, and images under `assets`, `public` or `static`). Limits: a script or an image
inside a test or documentation folder stays excluded even when `frontPaths` names it, markdown pages never
count, and a changed submodule pointer is not inspected.

Status (exit code 0 for the first two, 2 for every other, 1 for an error such as an unreadable file or a base
that does not exist), with a `reason` and an `action`:
  not_needed     nothing visible changed and the plan does not turn the browser test on (action `none`).
  answered       the user decided (`situacao` is `aprovado`, `prosseguir`, `sem-assistir` or `dispensado`)
                 and no code that is not a test or a document changed in the visible roots since (`none`).
  pending        the user has not decided: no record (`sem-registro`), `pendente`, `ainda-nao` (asked, said
                 not yet) or `alteracao` (asked for a change; the change comes first, then a new run with
                 no new "pronto" question). Action `ask`. Seen before the last screen slice has closed its
                 loop it is expected and nothing is asked yet; that timing is the session's, not the gate's.
  stale          the user decided, and visible-root code (not tests or documents) changed after
                 (`codigo-mudou`, with `changed_roots`), or the record carries no `lote.roots` to compare
                 with (`sem-vinculo`). Action `ask-again`.
  contradiction  the diff changes what the user sees and the plan says `nao` or says nothing; not yet
                 decided. Action `ask-plan`.
  unconfigured   something visible changed, nobody decided, and the project has no `browserTest`: there is
                 no way to run it, so the session asks how to verify (`ask-how`).

`roots` in the output maps each visible root (its branch, or `detached:<folder name>`) to the hash of its
own non-test, non-document changes; the session copies it into the record as `lote.roots` when it records
the user's answer, and the gate compares it later. `by_root` lists the visible files of every root, so the
session can compare each issue with its own plan, and `stacked_on` names the branch each stacked issue is
measured from. Roots with no visible change are listed in `other_roots` and never make a record stale:
when one of them changes behavior the `Fluxo:` exercises, the session asks again by hand.

`--answer "<literal>"` (with `--record`, or `--issue <n>` for `.frontlights/issues/<n>/browser/result.json` of the main
worktree) records the user's answer in the same call: `situacao` from the option the literal names, `lote.roots` from
this run of the gate, `pergunta.resposta` verbatim; the output is the gate read again over the record just written.
An option that is not a decision ("Assistir de novo", "Sim, pode rodar") is refused: it starts a run, it ends none.

`record --pass antes|depois --criterion S<n> --head <sha> [--case id=ok|falha:<texto>] [--failure-kind ...]
[--account conta1|conta2] [--profile-field "<campo>=<antes>-><depois>"] [--origin back-real|interceptada]` writes one
criterion of one pass into the same result.json, run by whoever conducts the pass, and prints one line. The fields
(`RECORD_FIELDS`, `PASS_FIELDS`, `CRITERION_FIELDS`) are those of `docs/protocol.md`, "Teste no navegador", the only
place they are described; `serve.py window shot` writes the print of a criterion through `record_print`, the same
schema. Neither judges a pass: passed or failed is the session's and the user's.
"""

import argparse
import hashlib
import json
import os
import re
import unicodedata
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _cli  # noqa: E402  (defaults of --root and --config, the parser and UTF-8)

TEST_SEGMENTS = {'tests', 'test', '__tests__', '__mocks__', 'e2e', 'cypress', 'fixtures', 'spec', 'specs',
                 'docs', 'doc'}
TEST_NAME = re.compile(r'\.(spec|test|e2e)\.[a-z0-9]+$')
DOC_SUFFIXES = ('.md', '.mdx', '.txt', '.rst')
DOC_NAME = re.compile(r'(?:readme|changelog|license|notice)\Z')
FRONT_SUFFIXES = ('.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte', '.jsx', '.tsx', '.astro',
                  '.ejs', '.hbs', '.cshtml', '.razor')
FRONT_NAME = re.compile(r'\.component\.(ts|js)$')
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico')
IMAGE_FOLDERS = {'assets', 'public', 'static'}
SITUATIONS = ('pendente', 'ainda-nao', 'aprovado', 'prosseguir', 'sem-assistir', 'dispensado', 'alteracao')
ANSWERED = ('aprovado', 'prosseguir', 'sem-assistir', 'dispensado')
TOCA = {'sim': 'sim', 'nao': 'nao', 'não': 'nao', 'ausente': 'ausente', None: 'ausente'}
MAX_PATTERNS = 50
MAX_PATTERN_LENGTH = 200
MAX_WILDCARD_GROUPS = 8
MATCH_BUDGET_SECONDS = 20     # per root: a pathological frontPaths is an error, never a silent wait or a silent pass

# The result.json of the watched run: docs/protocol.md, "Teste no navegador", lists exactly these (a test compares).
RECORD_FIELDS = ('situacao', 'aprovacao', 'pergunta', 'lote', 'assistido', 'rodadas', 'pastaDosPrints', 'criterios',
                 'passadas', 'registradoEm')
PASS_FIELDS = ('branch', 'head', 'repeticoes', 'criterios')
CRITERION_FIELDS = ('head', 'print', 'casos', 'tipoDeFalha', 'conta', 'perfil', 'origem', 'registradoEm')
PASSES = ('antes', 'depois')
FAILURE_KINDS = ('infraestrutura', 'produto', 'config')
ACCOUNTS = {'conta1': 'conta 1', 'conta2': 'conta 2'}
ORIGINS = {'back-real': 'back real', 'interceptada': 'interceptada'}
CRITERION = re.compile(r'S[1-9][0-9]?')
HEAD = re.compile(r'[0-9a-f]{7,64}')
CASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,39}')
# the literal of an option of the three questions (and of the gate's own) -> situacao; None keeps the decision
ANSWERS = (('aprovado', 'aprovado'), ('pode prosseguir', 'prosseguir'), ('precisa de alteracao', 'alteracao'),
           ('ainda nao', 'ainda-nao'), ('rodar sem assistir', 'sem-assistir'), ('dispensar o teste', 'dispensado'),
           ('verificar a mao e dispensar', 'dispensado'), ('manter a decisao anterior', None))
NOT_DECISIONS = ('assistir de novo', 'sim, pode rodar', 'rodar o teste assistido', 'sem mudar perfil',
                 'configurar o browsertest agora', 'informar a issue', 'corrigir e testar de novo')


def git(root, *args):
    done = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=60, env=_cli.git_environment())
    if done.returncode != 0:
        raise ValueError(f'git {args[0]} failed in {root}: {done.stderr.decode("utf-8", "replace").strip()[:200]}')
    return done.stdout


def looks_screen(path):
    lowered = path.lower()
    return lowered.endswith(FRONT_SUFFIXES) or bool(FRONT_NAME.search(lowered.rsplit('/', 1)[-1]))


def is_test_or_doc(path):
    parts = path.lower().split('/')
    name = parts[-1]
    if name.endswith(DOC_SUFFIXES) or DOC_NAME.match(name) or TEST_NAME.search(name):
        return True
    return bool(set(parts[:-1]) & TEST_SEGMENTS) and not looks_screen(path)


def normalize_pattern(pattern):
    """The glob as it is matched: forward slashes, no spaces around it, no leading `./`, no repeated or trailing
    slash, runs of `*` longer than two folded into `**`."""
    text = pattern.strip().replace('\\', '/')
    text = re.sub(r'/{2,}', '/', text)
    while text.startswith('./'):
        text = text[2:]
    text = text.rstrip('/')
    if text == '.':
        text = ''
    return re.sub(r'\*{3,}', '**', text)


def validate_front_paths(paths):
    """`browserTest.frontPaths`: a short list of relative globs. Braces and classes are not supported, and a
    pattern that matches nothing by construction (empty once normalized) is refused."""
    ok = (isinstance(paths, list) and 0 < len(paths) <= MAX_PATTERNS and
          all(isinstance(item, str) and normalize_pattern(item) and len(item) <= MAX_PATTERN_LENGTH and
              '\x00' not in item and not item.strip().startswith(('/', '\\', '~')) and
              not re.match(r'^[A-Za-z]:', item.strip()) and not re.search(r'[{}\[\]]', item) and
              not ({'..', '.'} & set(normalize_pattern(item).split('/'))) and
              len(re.findall(r'\*+', item)) <= MAX_WILDCARD_GROUPS for item in paths))
    if not ok:
        raise ValueError(f'browserTest.frontPaths must be a list of at most {MAX_PATTERNS} relative globs of at most '
                         f'{MAX_PATTERN_LENGTH} characters, each naming something (not `.` or empty), with at most '
                         f'{MAX_WILDCARD_GROUPS} `*` groups, without `{{}}` or `[]` and without an absolute path, `.` or '
                         '`..` segments or `~`')
    return list(paths)


class Glob:
    """A glob matched without backtracking, so a config a clone brings cannot stall the gate. Relative to the
    repository root; the case does not matter. `*` and `?` stay inside one folder, `**` crosses folders, and a
    pattern that names a folder covers what is inside it."""

    def __init__(self, pattern):
        text, self.tokens, index = normalize_pattern(pattern), [], 0
        while index < len(text):
            if text.startswith('**/', index):
                self.tokens.append(('deep_folder', None))
                index += 3
            elif text.startswith('**', index):
                self.tokens.append(('deep', None))
                index += 2
            elif text[index] == '*':
                self.tokens.append(('star', None))
                index += 1
            elif text[index] == '?':
                self.tokens.append(('one', None))
                index += 1
            else:
                self.tokens.append(('char', text[index].lower()))
                index += 1

    def match(self, path):
        path = path.lower()
        size = len(path)
        reach = {0}
        for kind, char in self.tokens:
            following = set()
            if kind == 'char':
                following = {p + 1 for p in reach if p < size and path[p] == char}
            elif kind == 'one':
                following = {p + 1 for p in reach if p < size and path[p] != '/'}
            elif kind == 'star':
                for start in reach:
                    position = start
                    while position <= size and position not in following:
                        following.add(position)
                        if position == size or path[position] == '/':
                            break
                        position += 1
            elif kind == 'deep':
                following = set(range(min(reach), size + 1)) if reach else set()
            else:                                           # `**/`: nothing at all, or anything ending in a slash
                if reach:
                    first = min(reach)
                    following = set(reach) | {p + 1 for p in range(first, size) if path[p] == '/'}
            reach = following
            if not reach:
                return False
        return any(p == size or path[p] == '/' for p in reach)


def compile_glob(pattern):
    return Glob(pattern)


def looks_visible(path):
    lowered = path.lower()
    if looks_screen(path):
        return True
    return lowered.endswith(IMAGE_SUFFIXES) and bool(set(lowered.split('/')[:-1]) & IMAGE_FOLDERS)


def is_front(path, patterns):
    """A visible change among the files that are not tests or documents."""
    if is_test_or_doc(path):
        return False
    return any(pattern.match(path) for pattern in patterns) if patterns else looks_visible(path)


def front_patterns(config):
    if not isinstance(config, dict):
        raise ValueError('the config must be a JSON object')
    block = config.get('browserTest')
    paths = block.get('frontPaths') if isinstance(block, dict) else None
    if paths is None:
        return None
    return [compile_glob(item) for item in validate_front_paths(paths)]


def changed_files(top, reference):
    """Files changed in the working tree against `reference` (committed, staged, edited and new), without the
    control folder. `top` is the top of the repository, so every path is relative to it."""
    names = git(top, 'diff', '--name-only', '-z', '--no-renames', reference).split(b'\0')
    names += git(top, 'ls-files', '-z', '--others', '--exclude-standard').split(b'\0')
    found = set()
    for raw in names:
        name = raw.decode('utf-8', 'replace').replace('\\', '/')
        if name and '.frontlights' not in name.split('/'):
            found.add(name)
    return sorted(found)


def digest(top, names):
    hashes = {}
    for name in names:
        path = Path(top) / name
        if path.is_file():
            sha = hashlib.sha256()
            with open(path, 'rb') as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b''):
                    sha.update(block)
            hashes[name] = sha.hexdigest()
        else:
            hashes[name] = 'deleted'
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def locate(root):
    top = git(root, 'rev-parse', '--show-toplevel').decode().strip()
    head = git(top, 'rev-parse', 'HEAD').decode().strip()
    branch = git(top, 'branch', '--show-current').decode().strip()
    return {'top': top, 'head': head, 'label': branch or f'detached:{Path(top).name}'}


def reference_of(place, base, stacked):
    """The commit a root is measured from: the one it shares with the branch its PR targets, which is the base
    unless the caller says the issue is stacked on another branch."""
    target = stacked.get(place['label'], base)
    return git(place['top'], 'merge-base', target, place['head']).decode().strip()


def root_report(place, reference, patterns):
    changed = changed_files(place['top'], reference)
    behavior = [name for name in changed if not is_test_or_doc(name)]
    deadline, front = time.monotonic() + MATCH_BUDGET_SECONDS, []
    for name in behavior:
        if time.monotonic() > deadline:
            raise ValueError(f'matching browserTest.frontPaths took more than {MATCH_BUDGET_SECONDS} s on this diff: '
                             'shorten the patterns (the cost grows with their length and the length of the paths)')
        if is_front(name, patterns):
            front.append(name)
    return {'label': place['label'], 'head': place['head'], 'behavior': behavior, 'front': front,
            'behavior_sha256': digest(place['top'], behavior)}


def situation(record):
    """The user's decision recorded for the batch. `situacao` is explicit; a record from before it existed is read
    through `aprovacao`, and anything else is still pending."""
    if not isinstance(record, dict):
        return 'pendente'
    explicit = record.get('situacao')
    if explicit is not None:
        return explicit if explicit in SITUATIONS else 'pendente'
    approval = record.get('aprovacao')
    return approval if approval in ('aprovado', 'prosseguir', 'alteracao') else 'pendente'


def gate(roots, base, config=None, toca=None, record=None, stacked=None):
    if not (isinstance(base, str) and base.strip()) or not roots:
        raise ValueError('browser-gate needs --base and at least one --root')
    if toca not in TOCA:
        raise ValueError('--toca must be sim, nao or ausente')
    toca = TOCA[toca]
    patterns = front_patterns(config) if config is not None else None
    places = [locate(root) for root in roots]
    labels = [place['label'] for place in places]
    if len(set(labels)) != len(labels):
        raise ValueError('two --root entries are on the same branch (or the same worktree folder name when detached): a '
                         "batch lists each root (an issue's or a slice's worktree) once")
    stacked = dict(stacked or {})
    unknown = sorted(set(stacked) - set(labels))
    if unknown:
        raise ValueError(f'--stacked names {unknown}, which is not the branch of any --root ({labels})')
    reports = [root_report(place, reference_of(place, base, stacked), patterns) for place in places]
    stacked_on = {label: target for label, target in stacked.items()}
    visible = [report for report in reports if report['front']]
    front_files = sorted({name for report in visible for name in report['front']})
    bound = visible or [report for report in reports if report['behavior']]
    current = {report['label']: report['behavior_sha256'] for report in bound}
    result = {'toca': toca, 'front_files': front_files, 'roots': current,
              'by_root': {report['label']: report['front'] for report in reports}, 'stacked_on': stacked_on,
              'other_roots': [report['label'] for report in reports if report not in bound], 'warnings': []}
    if not (front_files or toca == 'sim'):
        result.update(status='not_needed', action='none')
        return result
    state = situation(record)
    result['situacao'] = state
    if state not in ANSWERED:
        if config is not None and not isinstance(config.get('browserTest'), dict):
            result.update(status='unconfigured', reason='sem-browsertest', action='ask-how',
                          message='something visible changed (or the plan turns the browser test on) and the project '
                                  'has no browserTest: ask the user how to verify it')
            return result
        reason = {'pendente': 'sem-registro' if not isinstance(record, dict) else 'pendente',
                  'ainda-nao': 'ainda-nao', 'alteracao': 'alteracao'}[state]
        contradiction = bool(front_files) and toca != 'sim'
        result.update(status='contradiction' if contradiction else 'pending', reason=reason,
                      action='ask-plan' if contradiction else 'ask')
        if contradiction:
            result['message'] = 'the diff changes what the user sees and the plan does not turn the browser test on'
        return result
    if toca != 'sim' and front_files:
        result['warnings'].append('the plan says the browser test is off or says nothing, but the diff changes what the '
                                  'user sees: correct `Toca o frontend:` in the plan')
    recorded = (record.get('lote') or {}).get('roots') if isinstance(record.get('lote'), dict) else None
    if not isinstance(recorded, dict):
        result.update(status='stale', reason='sem-vinculo', action='ask-again',
                      message='the record carries no lote.roots: copy `roots` from this output into it, or run again')
        return result
    changed = sorted(label for label, value in current.items() if recorded.get(label) != value)
    if changed:
        result.update(status='stale', reason='codigo-mudou', changed_roots=changed, action='ask-again')
        return result
    result.update(status='answered', action='none')
    return result


def parse_stacked(entries):
    """`<branch>=<the branch its PR targets>` entries as a dict."""
    found = {}
    for entry in entries or ():
        label, separator, target = str(entry).partition('=')
        if not (separator and label.strip() and target.strip()):
            raise ValueError(f'--stacked takes <branch>=<the branch its PR targets>, got {entry!r}')
        found[label.strip()] = target.strip()
    return found


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def plain(text):
    folded = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(folded.lower().replace('`', '').split())


def answer_situation(literal):
    """(label, situacao or None to keep the decision) of the option the literal names; ValueError otherwise."""
    text = plain(literal)
    if not text:
        raise ValueError('--answer needs the literal answer of the user')
    for label in NOT_DECISIONS:
        if text.startswith(label):
            raise ValueError(f'"{literal}" starts a run, it is not a decision of the gate: record the answer of the '
                             'question that ends the run')
    for label, state in ANSWERS:
        if text.startswith(label):
            return label, state
    options = ', '.join(f'"{label}"' for label, _ in ANSWERS)
    raise ValueError(f'"{literal}" names none of the options the gate records ({options}); pass the literal of the '
                     'option the user chose')


def now_text():
    return _cli.sao_paulo_now().isoformat(timespec='seconds')


def load_record(path):
    if not path or not Path(path).is_file():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f'{path} must hold a JSON object')
    return data


def save_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def record_answer(path, result, literal, issues=None):
    """Write the user's answer into the record: situacao, lote.roots of this gate run, pergunta.resposta verbatim."""
    label, state = answer_situation(literal)
    record = load_record(path)
    if state is None:
        state = situation(record)
        if state not in ANSWERED:
            raise ValueError('"Manter a decisão anterior" needs a decision already recorded; there is none')
    record['situacao'] = state
    if state in ('aprovado', 'prosseguir', 'alteracao'):
        record['aprovacao'] = state
    lote = record.get('lote') if isinstance(record.get('lote'), dict) else {}
    lote['roots'] = result['roots']
    if issues:
        lote['issues'] = sorted(set(lote.get('issues') or []) | set(issues))
    record['lote'] = lote
    record['pergunta'] = {'resposta': literal, 'opcao': label, 'em': now_text()}
    record['registradoEm'] = now_text()
    save_record(path, record)
    return record


def pass_entry(record, pass_):
    passes = record.setdefault('passadas', {})
    entry = passes.setdefault(pass_, {})
    entry.setdefault('criterios', {})
    return entry


def record_print(path, pass_, criterion, file_name, folder=None):
    """`serve.py window shot`: the print of one criterion of one pass, in the same schema as `record`."""
    if pass_ not in PASSES or not CRITERION.fullmatch(criterion or ''):
        raise ValueError('a print is recorded for --pass antes|depois and --criterion S<n>')
    record = load_record(path)
    item = pass_entry(record, pass_)['criterios'].setdefault(criterion, {})
    item['print'] = file_name
    item['registradoEm'] = now_text()
    if folder:
        record['pastaDosPrints'] = str(folder)
    save_record(path, record)
    return record


def parse_case(text):
    name, separator, value = str(text).partition('=')
    usage = f'--case takes <id>=ok or <id>=falha:<o que aconteceu>, got {text!r}'
    if not (separator and CASE_ID.fullmatch(name.strip())):
        raise ValueError(usage)
    value = value.strip()
    if value == 'ok':
        return name.strip(), 'ok'
    if value.startswith('falha:') and value[len('falha:'):].strip():
        return name.strip(), 'falha: ' + value[len('falha:'):].strip()[:300]
    raise ValueError(usage)


def parse_profile(text):
    field, separator, change = str(text).partition('=')
    before, arrow, after = change.partition('->')
    if not (separator and arrow and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{0,59}', field.strip())):
        raise ValueError('--profile-field takes "<campo>=<antes>-><depois>", only the field of the profile, never a row')
    return {'campo': field.strip(), 'antes': before.strip()[:100], 'depois': after.strip()[:100]}


def missing_before(record):
    """The criteria of the record that still lack their ANTES (no print and no case in the antes pass)."""
    wanted = record.get('criterios') if isinstance(record.get('criterios'), list) else []
    antes = ((record.get('passadas') or {}).get('antes') or {}).get('criterios') or {}
    return [name for name in wanted
            if not (antes.get(name) or {}).get('print') and not (antes.get(name) or {}).get('casos')]


def record_pass(path, pass_, criterion, head, cases=(), failure_kind=None, account=None, profile=None, origin=None,
                branch=None, criteria=None):
    """One criterion of one pass into the record (the fields of CRITERION_FIELDS); never a verdict."""
    if pass_ not in PASSES:
        raise ValueError('--pass must be antes or depois')
    if not CRITERION.fullmatch(criterion or ''):
        raise ValueError('--criterion is S<n>, the box whose Fluxo: the pass walks')
    if not HEAD.fullmatch(head or ''):
        raise ValueError('--head is the commit served in the pass (7 to 64 hexadecimal characters)')
    if failure_kind is not None and failure_kind not in FAILURE_KINDS:
        raise ValueError(f'--failure-kind is one of {", ".join(FAILURE_KINDS)}')
    if account is not None and account not in ACCOUNTS:
        raise ValueError('--account is conta1 or conta2, never the login')
    if origin is not None and origin not in ORIGINS:
        raise ValueError('--origin is back-real or interceptada')
    parsed_cases = dict(parse_case(case) for case in cases)
    parsed_profile = parse_profile(profile) if profile else None
    record = load_record(path)
    if criteria:
        names = [name.strip() for name in criteria.split(',') if name.strip()]
        if not names or not all(CRITERION.fullmatch(name) for name in names):
            raise ValueError('--criteria lists the boxes as S1,S2,S3')
        record['criterios'] = sorted(set(record.get('criterios') or []) | set(names), key=lambda n: int(n[1:]))
    entry = pass_entry(record, pass_)
    if branch:
        entry['branch'] = branch
    entry['head'] = head
    entry['repeticoes'] = 2
    item = entry['criterios'].setdefault(criterion, {})
    item['head'] = head
    if parsed_cases:
        item['casos'] = dict(item.get('casos') or {}, **parsed_cases)
    if failure_kind:
        item['tipoDeFalha'] = failure_kind
    if account:
        item['conta'] = ACCOUNTS[account]
    if parsed_profile:
        item['perfil'] = parsed_profile
    if origin:
        item['origem'] = ORIGINS[origin]
    item['registradoEm'] = now_text()
    save_record(path, record)
    cases_now = item.get('casos') or {}
    return {'ok': True, 'record': str(path), 'pass': pass_, 'criterion': criterion, 'head': head,
            'ok_cases': sum(1 for value in cases_now.values() if value == 'ok'),
            'failed_cases': sum(1 for value in cases_now.values() if value != 'ok'),
            'missing_before': missing_before(record)}


def default_record(issue, root):
    """(path, number): `.frontlights/issues/<n>/browser/result.json` of the main worktree of `root`."""
    main = _cli.main_worktree(root)
    number = _cli.issue_number(issue, _cli.current_tree(root), main)
    return str(Path(main) / '.frontlights' / 'issues' / str(number) / 'browser' / 'result.json'), number


def run_cli(roots, base, config_path=None, toca=None, record_path=None, stacked=(), answer=None, issues=None):
    config = read_json(config_path) if config_path else None
    if config is not None and not isinstance(config, dict):
        raise ValueError('the config must be a JSON object')
    record = read_json(record_path) if record_path and Path(record_path).is_file() else None
    result = gate(roots, base, config, toca, record, parse_stacked(stacked))
    if answer is not None:
        if not record_path:
            raise ValueError('--answer needs --record (or --issue) to write the answer into')
        record = record_answer(record_path, result, answer, issues)
        result = gate(roots, base, config, toca, record, parse_stacked(stacked))
        result['recorded'] = {'record': str(record_path), 'situacao': record['situacao'],
                              'resposta': record['pergunta']['resposta']}
    return result, (0 if result['status'] in ('not_needed', 'answered') else 2)


def record_main(argv):
    """`browser-gate record ...`: one criterion of one pass into the result.json; one line out."""
    parser = _cli.JsonParser(prog='browser-gate record', description='Grava um critério de uma passada no result.json '
                             '(campos: docs/protocol.md, "Teste no navegador"). Não julga a passada.')
    parser.add_argument('--record', help="the issue's result.json (default: the one of --issue in the main worktree)")
    parser.add_argument('--issue', help="the issue (the lead one of a family); default: the charter's for this worktree")
    parser.add_argument('--root', help='a worktree of the project (default: the current one)')
    parser.add_argument('--pass', dest='pass_', required=True, choices=PASSES)
    parser.add_argument('--criterion', required=True, help='S<n>, the box whose Fluxo: the pass walks')
    parser.add_argument('--head', required=True, help='the commit served in the pass')
    parser.add_argument('--branch', help='the branch served (DEPOIS) or the base (ANTES)')
    parser.add_argument('--criteria', help='every box of the run, as S1,S2,S3 (once is enough)')
    parser.add_argument('--case', action='append', default=[], help='<id>=ok or <id>=falha:<o que aconteceu>; repeatable')
    parser.add_argument('--failure-kind', choices=FAILURE_KINDS)
    parser.add_argument('--account', choices=sorted(ACCOUNTS))
    parser.add_argument('--profile-field', help='"<campo>=<antes>-><depois>": only the field of a moved profile')
    parser.add_argument('--origin', choices=sorted(ORIGINS))
    try:
        args = parser.parse_args(argv)
        path = args.record or default_record(args.issue, args.root or '.')[0]
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 2)
    try:
        result = record_pass(path, args.pass_, args.criterion, args.head, args.case, args.failure_kind, args.account,
                             args.profile_field, args.origin, args.branch, args.criteria)
    except (ValueError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


def main(argv=None):
    _cli.utf8_streams()
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ['record']:
        return record_main(argv[1:])
    parser = _cli.JsonParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', action='append',
                        help='worktree of the issue, or of one of its slices (named in --stacked); repeatable '
                             '(default: the worktree of the current directory)')
    parser.add_argument('--base', required=True, help='approved base of the issue, the same for every root')
    parser.add_argument('--config', help="the project's .frontlights/config.json (browserTest.frontPaths, browserTest; "
                                         "default: the one of the main worktree, when it exists)")
    parser.add_argument('--toca', choices=sorted(k for k in TOCA if k), help="the plan's `Toca o frontend:`")
    parser.add_argument('--record', help="the issue's result.json (may not exist yet)")
    parser.add_argument('--stacked', action='append', default=[], metavar='BRANCH=TARGET',
                        help='the branch of a slice (or of a stacked issue) and the branch it is measured from: the branch '
                             'of its issue, or the one its PR targets; repeatable')
    parser.add_argument('--answer', help="the user's answer, verbatim: recorded in --record with this run's roots")
    parser.add_argument('--issue', help='the issue whose result.json (main worktree) is --record when it is left out')
    try:
        args = _cli.output_flags(parser).parse_args(argv)
        args.root = args.root or [str(_cli.current_tree())]
        args.config = _cli.config_path(args.config, _cli.main_worktree(args.root[0]), required=False)
        issues = None
        if args.issue is not None:
            path, number = default_record(args.issue, args.root[0])
            args.record = args.record or path
            issues = [number]
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 2)
    try:
        result, code = run_cli(args.root, args.base, args.config, args.toca, args.record, args.stacked, args.answer,
                               issues)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    _cli.emit(json.dumps(result, indent=2, ensure_ascii=True), 'browser-gate', args.full)
    return code


if __name__ == '__main__':
    sys.exit(main())
