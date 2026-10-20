"""A class template repository for the tests (tooling of whoever develops Frontlights; outside the skill).

A test class builds its Git fixture once, in `setUpClass`, with `template(cls, build)`; each test then gets a whole
copy of it with `copy(template_folder, dest)`, inside the test's own temporary folder. The copy costs no Git process.

    @classmethod
    def setUpClass(cls):
        cls.template = gitfixture.template(cls, build)    # build(folder) lays out repositories inside `folder`

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = gitfixture.copy(self.template, Path(tmp.name) / 'repo')

Rules:
- Never put a worktree in the template: worktree metadata holds absolute paths, so a copy would point back at the
  template. Make worktrees in the test, after the copy; branches in the template are fine. `copy` refuses a template
  with a worktree.
- A bare origin (or any repository) built inside the template folder is copied along, and each remote URL of the
  copy that points inside the template is rewritten to the same place inside the copy: push and fetch in the copy
  never touch the template. Remotes outside the template are kept as they are.
- The template folder is removed at the end of the class (`addClassCleanup`), even when `build` fails.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

IDENTITY = (('user.email', 'fixture@example.invalid'), ('user.name', 'Fixture'))
URL_LINE = re.compile(r'^(\s*(?:url|pushurl)\s*=\s*)(.*?)\s*$', re.IGNORECASE)


def git(root, *args):
    """`git -C root ...`, checked, with text output."""
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)


def init(root, branch='main'):
    """A new repository at `root` on `branch`, with the fixture identity."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q', '-b', branch)
    for key, value in IDENTITY:
        git(root, 'config', key, value)
    return root


def template(cls, build):
    """A class temporary folder laid out by `build(folder)`, removed when the class ends. Call it in `setUpClass`."""
    tmp = tempfile.TemporaryDirectory()
    cls.addClassCleanup(tmp.cleanup)
    folder = Path(tmp.name)
    build(folder)
    return folder


def git_dirs(folder):
    """Every Git directory under `folder`: the `.git` of a repository and each bare repository."""
    for current, dirs, files in os.walk(folder):
        here = Path(current)
        if '.git' in files:
            raise ValueError(f'the template holds a worktree ({here}): make worktrees in the test, after the copy')
        if {'HEAD', 'config'} <= set(files) and 'objects' in dirs:
            yield here
            dirs[:] = []                                    # nothing of interest inside a Git directory


def key(path):
    return os.path.normcase(str(Path(path).resolve()))


def unquote(value):
    """A value of a Git config line as Git reads it: quotes dropped, `\\\\` and `\\"` unescaped."""
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return re.sub(r'\\(.)', r'\1', value)


def quote(value):
    """A value Git reads back as is, whatever it holds (`#`, `;`, spaces, backslashes, quotes)."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def rewrite_remotes(config, source, dest):
    """Point each remote URL of `config` that lies inside `source` at the same place inside `dest`."""
    inside, lines, changed = key(source), [], False
    for line in config.read_text(encoding='utf-8').splitlines(keepends=True):
        match = URL_LINE.match(line)
        if match:
            value = unquote(match.group(2))
            if '://' not in value and os.path.isabs(value):
                target = key(value)
                if target == inside or target.startswith(inside + os.sep):
                    moved = Path(dest) / os.path.relpath(target, inside)
                    line = f'{match.group(1)}{quote(moved.as_posix())}\n'   # quoted: `#` and `;` open a comment
                    changed = True
        lines.append(line)
    if changed:
        config.write_text(''.join(lines), encoding='utf-8')


def copy(template_folder, dest, exist_ok=False):
    """A whole copy of the template at `dest`, with its inner remotes rewritten. `dest` must not exist yet, unless
    `exist_ok`: then what is already there stays, and a file of the template with the same name replaces it."""
    source = Path(template_folder)
    found = list(git_dirs(source))
    for gitdir in found:                                    # a worktree made outside the folder still leaves this
        linked = gitdir / 'worktrees'
        if linked.is_dir() and any(linked.iterdir()):
            raise ValueError(f'the template holds a worktree ({gitdir}): make worktrees in the test, after the copy')
    dest = Path(dest)
    shutil.copytree(source, dest, dirs_exist_ok=exist_ok)
    for gitdir in found:
        rewrite_remotes(dest / gitdir.relative_to(source) / 'config', source, dest)
    return dest
