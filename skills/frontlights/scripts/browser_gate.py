#!/usr/bin/env python3
"""The watched-run gate: has the user been asked about, and answered, the browser test of a batch of work
that changes what they see on the screen?

`review-gate` says whether an independent review still covers the code; this says whether the watched
browser run (`skills/frontlights/references/browser-testing.md`) covers the visible change. It reads the
Git diff, not the plan's text, so a screen change the plan forgot to declare is still caught.

One batch is one decision: the roots are the worktrees of every slice the session finished and means to
deliver together (the issue, its sub-issues, and any other issue authorized in the same run). The gate
finds the visible changes of each root and compares them with the record of the watched run kept for the
whole batch (`.frontlights/issues/<lead>/browser/result.json`), never one record per branch.

Inputs: `--root` (repeatable) the worktrees, `--base` the approved base of the batch (normally the default
branch), the same for every root, `--config` the project's `.frontlights/config.json` (its
`browserTest.frontPaths` names the visible paths; absent, a conservative default applies, and an absent
config also silences `unconfigured`), `--toca` what the plan's `Toca o frontend:` says (`sim`, `nao` or
`ausente`; `sim` when any slice of the batch says it), `--record` the result.json (it may not exist).

What a root changes. Each root is measured from the commit it shares with the base, except a slice stacked on
another branch, which the caller names with `--stacked <its branch>=<the branch its PR targets>` (what the
stacking authorization already records as its base): that slice is measured from the commit it shares with
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
session can compare each slice with its own plan, and `stacked_on` names the branch each stacked slice is
measured from. Roots with no visible change are listed in `other_roots` and never make a record stale:
when one of them changes behavior the `Fluxo:` exercises, the session asks again by hand.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

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


def git(root, *args):
    done = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=60)
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
    unless the caller says the slice is stacked on another branch."""
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
                         'batch lists each slice once')
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


def run_cli(roots, base, config_path=None, toca=None, record_path=None, stacked=()):
    config = read_json(config_path) if config_path else None
    if config is not None and not isinstance(config, dict):
        raise ValueError('the config must be a JSON object')
    record = read_json(record_path) if record_path and Path(record_path).is_file() else None
    result = gate(roots, base, config, toca, record, parse_stacked(stacked))
    return result, (0 if result['status'] in ('not_needed', 'answered') else 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', action='append', required=True, help='worktree of a slice of the batch; repeatable')
    parser.add_argument('--base', required=True, help='approved base of the batch, the same for every root')
    parser.add_argument('--config', help="the project's .frontlights/config.json (browserTest.frontPaths, browserTest)")
    parser.add_argument('--toca', choices=sorted(k for k in TOCA if k), help="the plan's `Toca o frontend:`")
    parser.add_argument('--record', help='the batch result.json (may not exist yet)')
    parser.add_argument('--stacked', action='append', default=[], metavar='BRANCH=TARGET',
                        help='a stacked slice and the branch its PR targets; repeatable')
    args = parser.parse_args()
    try:
        result, code = run_cli(args.root, args.base, args.config, args.toca, args.record, args.stacked)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
