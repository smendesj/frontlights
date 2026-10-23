"""Frontlights: deterministic planning/evidence helpers, never a shell agent.

Only inspect performs network reads. No command here publishes issues, executes
tests, grants Claude permissions, or changes a product repository.
"""
import argparse
import contextlib
import datetime as dt
import fnmatch
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import urllib.request
import urllib.parse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _cli  # noqa: E402  (defaults of --root, --tree, --config and --issue, the parser and UTF-8)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class PlanError(ValueError):
    """A plan refusal with the path of the field it is about, such as `issues[0].slices[2].walkthrough`."""

    def __init__(self, message, path):
        super().__init__(message)
        self.path = path


def need(condition, message, path):
    """`require` for a plan: the refusal names the field, relative (`.title`) to the `at` around it."""
    if not condition:
        raise PlanError(message, path)


@contextlib.contextmanager
def at(path):
    """Refusals inside carry `path`; a PlanError whose path starts with `.` is relative to it."""
    try:
        yield
    except PlanError as error:
        if error.path.startswith('.'):
            raise PlanError(str(error), path + error.path) from None
        raise
    except ValueError as error:
        raise PlanError(str(error), path) from None


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and bool(value) and all(nonempty(x) for x in value)


def number(value):
    return type(value) is int and value > 0


def repository(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value)


def relative(value):
    require(nonempty(value), 'ownership must name a path')
    value = value.replace('\\', '/')
    require(not PurePosixPath(value).is_absolute() and ':' not in value and
            all(p not in ('..', '.', '') for p in value.split('/')),
            'ownership must be a normalized relative path')
    require(value == '*' or not any(c in value for c in '*?['),
            f'ownership {value!r} has a glob: name the folder or file (for example src/feature) or use * for unknown ownership')
    return value.casefold().rstrip('/')


def overlap(a, b):
    a, b = relative(a), relative(b)
    return a == '*' or b == '*' or a == b or a.startswith(b + '/') or b.startswith(a + '/')


def conflicts(a, b):
    return any(overlap(x, y) for x in a['ownership'] for y in b['ownership'])


def repository_or_local(value):
    """None means a local project without a remote, which is a supported state."""
    return value is None or repository(value)


BOARD_KEYS = {'owner', 'number', 'assignee', 'issue_type', 'fields', 'labels', 'issue_type_by_label', 'body_fields'}


def board(project, repo=...):
    """The issue board every created issue must join, or None when none is configured.

    `fields` maps a board field to its default value; None means the value is chosen per
    issue in the approved plan. The board is data for gh, never a place to embed credentials.
    """
    if project is None:
        return None
    require(isinstance(project, dict), 'project must be an object or null')
    require(repo is not None, 'project board requires a GitHub repository; a local project has none')
    # A misspelt rule key would switch the rule off without a word, so an unknown key is refused.
    unknown = sorted(set(project) - BOARD_KEYS)
    require(not unknown, f'project has unknown setting(s): {", ".join(map(str, unknown))}; known: {", ".join(sorted(BOARD_KEYS))}')
    owner, num = project.get('owner'), project.get('number')
    require(isinstance(owner, str) and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', owner),
            'project.owner must be a GitHub user or organization login')
    require(number(num), 'project.number must be a positive integer')
    fields = project.get('fields', {})
    require(isinstance(fields, dict) and all(nonempty(k) and (v is None or nonempty(v))
            for k, v in fields.items()), 'project.fields must map field names to a value or null')
    for key in ('assignee', 'issue_type'):
        require(project.get(key) is None or nonempty(project.get(key)),
                f'project.{key} must be a non-empty string or null')
    # These strings are typed into `gh` commands, and a config can come from a cloned repository.
    require(project.get('assignee') is None or project['assignee'] in ('@me', '@copilot') or LOGIN.fullmatch(project['assignee']),
            'project.assignee must be @me, @copilot or a GitHub login')
    require(project.get('issue_type') is None or typeable(project['issue_type']),
            f'project.issue_type must be {TYPEABLE_RULE}')
    for name, default in fields.items():
        require(typeable(name), f'project.fields name {name!r} must be {TYPEABLE_RULE}')
        require(default is None or typeable(default), f'project.fields.{name} default must be {TYPEABLE_RULE}')
    return {'owner': owner, 'number': num, 'fields': dict(fields),
            'assignee': project.get('assignee'), 'issue_type': project.get('issue_type'),
            'labels': label_rules(project.get('labels'), fields),
            'issue_type_by_label': type_rules(project.get('issue_type_by_label')),
            'body_fields': body_rules(project.get('body_fields'))}


# Text that ends up as one argument of a `gh` command a session types. Passed as a single double-quoted
# argument it is inert in bash and PowerShell unless it holds `$`, a backtick, a double quote (Windows PowerShell
# also closes a string on the curly ones U+201C, U+201D and U+201E; U+201F, U+2033 and U+FF02 do not, and are
# refused only as a precaution because they look like one), a backslash or a control character, so those are
# refused wherever a config or a plan can introduce them. Not covered: `cmd.exe` (`%`), which this plugin does
# not target, and bash history expansion (`!`), which is interactive only.
UNSAFE_CHARS = re.compile(r'[$`"\\“”„‟″＂\x00-\x1f\x7f]')
UNTYPEABLE_NAMES = 'a dollar sign, backtick, double quote (straight or curly), backslash or control character'
TYPEABLE_RULE = f'text of up to 100 characters without {UNTYPEABLE_NAMES}'
LOGIN = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9_-]{0,38})(?:\[bot\])?')


def typeable(value):
    return nonempty(value) and len(value) <= 100 and not UNSAFE_CHARS.search(value)


# A label is such an argument too, so it is stricter: letters, digits and `: . / + -` or a space inside
# (up to 50 characters), starting with a letter or digit, ending in a letter, digit or `+`, and with no
# hyphen right after a space, so it can never read as an option. No quote, `;`, `&`, `|`, comma or line break.
LABEL_NAME = re.compile(r'(?!.*\s-)\w(?:[\w :./+-]{0,48}[\w+])?')
BODY_FIELD_NAME = re.compile(r'[^\r\n*:]{1,60}')
LABEL_RULE = ('letters, digits and : . / + - or a space inside; up to 50 characters; not ending in : . / - or a space; '
              'no hyphen after a space')


def label_names(value, where):
    require(isinstance(value, list) and value and all(isinstance(x, str) and LABEL_NAME.fullmatch(x) for x in value),
            f'{where} must be a non-empty list of label names ({LABEL_RULE})')
    return list(value)


FAMILY = re.compile(r'[^:/]+[:/]')


def family(label):
    """`area:` for `area:backend` (or `area/` for `area/backend`): the prefix a label family shares up to its
    first `:` or `/`, or None for a label without one. Vocabularies that split a family with another
    character (`area-backend`) are not recognised. GitHub treats label names as case-insensitive, so every
    comparison here is made on the folded text."""
    match = FAMILY.match(label)
    return match.group(0).casefold() if match else None


def clashes(label, present, wanted):
    """Whether adding `label` would leave its family with two labels: some label of that family is already
    there (`present`) and is not itself one of the labels `wanted` for that family."""
    kin = family(label)
    if kin is None:
        return False
    wanted_fold = {w.casefold() for w in wanted}
    return any(family(p) == kin and p.casefold() not in wanted_fold for p in present)


def family_twins(groups):
    """The labels one field implies that share a family with a different label another field implies:
    values of several fields that together would leave an issue with two labels of one family. One field
    value may imply several labels of a family on purpose (`Both`: `area:frontend` and `area:backend`)."""
    twins = []
    for index, group in enumerate(groups):
        others = [label for other, rest in enumerate(groups) if other != index for label in rest]
        for label in group:
            if label not in twins and family(label) is not None and any(
                    family(o) == family(label) and o.casefold() != label.casefold() for o in others):
                twins.append(label)
    return twins


def label_rules(rules, fields):
    """`project.labels`: which label families a top-level issue must carry and which labels follow
    from a board field value, so a project's own label vocabulary never lives in this plugin."""
    if rules is None:
        return {'require_prefix': [], 'by_field': {}}
    require(isinstance(rules, dict) and set(rules) <= {'require_prefix', 'by_field'},
            'project.labels must be an object with require_prefix and by_field, or null')
    prefixes = rules.get('require_prefix', [])
    require(isinstance(prefixes, list) and all(typeable(p) for p in prefixes),
            f'project.labels.require_prefix must be a list of label prefixes such as "type:", each {TYPEABLE_RULE}')
    by_field = rules.get('by_field', {})
    require(isinstance(by_field, dict), 'project.labels.by_field must map a board field to its values')
    for field, mapping in by_field.items():
        require(field in fields, f'project.labels.by_field.{field}: not a field of project.fields')
        require(isinstance(mapping, dict) and all(nonempty(k) for k in mapping),
                f'project.labels.by_field.{field} must map each field value to its labels')
        for value, names in mapping.items():
            label_names(names, f'project.labels.by_field.{field}.{value}')
    return {'require_prefix': list(prefixes), 'by_field': {f: dict(m) for f, m in by_field.items()}}


def type_rules(mapping):
    """`project.issue_type_by_label`: the native issue type a label implies."""
    if mapping is None:
        return {}
    require(isinstance(mapping, dict) and all(isinstance(k, str) and LABEL_NAME.fullmatch(k) and typeable(v)
                                              for k, v in mapping.items()),
            f'project.issue_type_by_label must map a label name ({LABEL_RULE}) to an issue type without {UNTYPEABLE_NAMES}')
    return dict(mapping)


def body_rules(rules):
    """`project.body_fields`: a line of the issue body (`**Name:** value`) with a closed list of values,
    for what the board has no field for."""
    if rules is None:
        return {}
    require(isinstance(rules, dict), 'project.body_fields must map a line name to its allowed values')
    for name, options in rules.items():
        require(isinstance(name, str) and BODY_FIELD_NAME.fullmatch(name) and name == name.strip(),
                f'project.body_fields name {name!r} must be plain text of up to 60 characters')
        require(strings(options) and all('\n' not in o and '\r' not in o for o in options),
                f'project.body_fields.{name} must be a non-empty list of single-line values')
    return {name: list(options) for name, options in rules.items()}


def is_sub_issue(issue):
    """A child of an issue of the plan (`parent`) or of a published issue outside it (`parent_external`)."""
    return issue.get('parent') is not None or issue.get('parent_external') is not None


def board_fields(project, issue):
    """Board values for one issue: defaults plus the per-issue choices, with nothing left open.

    A sub-issue (`parent` or `parent_external` set) joins the board only through its parent: it takes no values.
    """
    if is_sub_issue(issue):
        require('project_fields' not in issue,
                f'{issue["id"]}: sub-issue não leva project_fields; entra no quadro só pelo pai')
        return {}
    chosen = issue.get('project_fields', {})
    require(isinstance(chosen, dict) and all(nonempty(k) and nonempty(v) for k, v in chosen.items()),
            f'{issue["id"]}: project_fields must map field names to non-empty values')
    # A value is typed into `gh project item-edit`, so one that a shell could read is refused (reword it).
    unsafe = sorted(k for k, v in chosen.items() if UNSAFE_CHARS.search(v))
    require(not unsafe,
            f'{issue["id"]}: project_fields {", ".join(unsafe)} must not contain {UNTYPEABLE_NAMES}; reword the value')
    unknown = sorted(set(chosen) - set(project['fields']))
    need(not unknown, f'{issue["id"]}: project_fields not on the board: {", ".join(unknown)}', '.project_fields')
    values = {k: v for k, v in project['fields'].items() if v is not None}
    values.update(chosen)
    missing = sorted(k for k in project['fields'] if k not in values)
    need(not missing, f'{issue["id"]}: choose board field(s) {", ".join(missing)} in the plan',
         f'.project_fields.{missing[0]}' if missing else '.project_fields')
    return values


def board_labels(project, issue, values):
    """Labels a top-level issue is created with: the ones its plan names plus the ones the board's
    rules derive from the field values. A required label family that is still absent is refused."""
    named = issue.get('labels', [])
    require(isinstance(named, list) and all(isinstance(x, str) and LABEL_NAME.fullmatch(x) for x in named),
            f'{issue["id"]}: labels must be a list of label names ({LABEL_RULE})')
    # The required family is the plan's own choice: a label a field value implies never stands in for it.
    for prefix in project['labels']['require_prefix']:
        require(any(label.casefold().startswith(prefix.casefold()) for label in named),
                f'{issue["id"]}: choose a "{prefix}*" label in the plan (labels)')
    labels = list(dict.fromkeys(named))
    folded = {label.casefold() for label in labels}
    implied = []
    for field, mapping in project['labels']['by_field'].items():
        for label in mapping.get(values.get(field), []):
            if label not in implied:
                implied.append(label)
    derived = [label for label in implied if label.casefold() not in folded]
    # Every implied label counts, named or not: a plan that names `area:backend` and `area:frontend` while the
    # fields imply only the first leaves two labels of one family just as a derived one would.
    twins = family_twins([mapping.get(values.get(field), []) for field, mapping in project['labels']['by_field'].items()])
    require(not twins, f'{issue["id"]}: the {field_values(project, values)} imply the labels {", ".join(twins)}, '
                       f'of one family; change a field value or the configuration in project.labels.by_field')
    for label in implied:
        require(not clashes(label, named, implied),
                f'{issue["id"]}: the {field_values(project, values)} imply the label {label}, which clashes with the same-family '
                f'label already named in the plan; keep one')
    return labels + derived


def field_values(project, values):
    """The field values that imply labels, for a refusal message."""
    shown = [f'{field}={values[field]}' for field in project['labels']['by_field'] if values.get(field)]
    return ', '.join(shown) or 'field values'


def board_body_fields(project, issue):
    rules = project['body_fields']
    chosen = issue.get('body_fields', {})
    require(isinstance(chosen, dict) and all(nonempty(k) and nonempty(v) for k, v in chosen.items()),
            f'{issue["id"]}: body_fields must map line names to non-empty values')
    unknown = sorted(set(chosen) - set(rules))
    require(not unknown, f'{issue["id"]}: body_fields not on the board: {", ".join(unknown)}')
    # An issue that already exists (it carries its `url`) cannot get a body line: the text already in a body is
    # never edited (stage 5 only appends the spec and the slices to it).
    missing = [] if issue.get('url') else sorted(set(rules) - set(chosen))
    require(not missing, f'{issue["id"]}: choose body field(s) {", ".join(missing)} in the plan')
    for name, value in chosen.items():
        require(value in rules[name], f'{issue["id"]}: body_fields {name} must be one of {", ".join(rules[name])}')
    return dict(chosen)


def board_has_rules(project):
    """Whether the project configures labels, a label-implied type or body lines. Without any of them the
    plan's `labels` and `body_fields` mean nothing to the board and are not looked at."""
    return bool(project['labels']['require_prefix'] or project['labels']['by_field'] or
                project['issue_type_by_label'] or project['body_fields'])


def resolve_board(project, issue):
    """Everything a top-level issue is created with on the board, or None for a sub-issue (which takes
    its labels, type and board card from its parent). The native type is the plan's, else the one its
    labels imply, else the board default."""
    values = board_fields(project, issue)
    rules = board_has_rules(project)
    if is_sub_issue(issue):
        require(not (rules and ('labels' in issue or 'body_fields' in issue)),
                f'{issue["id"]}: sub-issue não leva labels nem body_fields; herda do pai')
        return None
    labels = board_labels(project, issue, values) if rules else []
    by_label = {label.casefold(): kind for label, kind in project['issue_type_by_label'].items()}
    implied = next((by_label[label.casefold()] for label in labels if label.casefold() in by_label), None)
    issue_type = issue.get('issue_type') or implied or project['issue_type']
    require(nonempty(issue_type), f'{issue["id"]}: issue_type required by the board (plan, labels or project default)')
    require(typeable(issue_type), f'{issue["id"]}: issue_type must be {TYPEABLE_RULE}')
    return {'fields': values, 'labels': labels, 'issue_type': issue_type,
            'body_fields': board_body_fields(project, issue) if rules else {}}


def board_resolution(plan, project):
    """The resolved board values per top-level issue, only when the project configures the rules
    that make them more than the plan's own fields (labels, label-implied type, body lines)."""
    board_ = board(project, plan['repository'])
    if board_ is None or not board_has_rules(board_):
        return None
    resolved = {}
    for issue in plan['issues']:
        value = resolve_board(board_, issue)
        if value is not None:
            resolved[str(issue['id'])] = value
    return resolved


STATUSES = {'ready', 'running', 'blocked', 'verified', 'proposed'}
SLICE_ID_RULE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,15}$')
SLICES_MAX = 5   # a short issue: at most five acceptance-criteria boxes (issue 31, S1)
# Issue 32, S1, and the decision of 20/10/2026: the branch of an issue enters the LOCAL main with one gate green,
# the watched run: `browser-gate` (`answered`, or `not_needed` when nothing on the screen changed), the word the
# tool prints. `suite_gate` and `review_gate` (`homolog suite-gate`, `review-gate`) are optional: accepted in
# `gates` with any value, never required, never refused. The remote main (`origin/main`) is never a target.
LOCAL_MAIN_GATES = {'browser_gate': ('answered', 'not_needed')}
# Work without an issue (the Direct path, or a Short one that publishes no issue) is named by a slug of its own: the
# `direct` of its `worktrees` entries, listed in the charter's `direct_ids`, takes the place of `issue`.
DIRECT_RULE = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')


WALKTHROUGH_FIELDS = ('persona', 'steps', 'before', 'after')


def walkthrough_of(label, sid, walkthrough):
    """The walkthrough of a slice (issue 65, S3), shapes only: an object whose persona (a label such as `conta 1` or
    `sem tela`, never a login), steps, before and after are non-empty strings. The before is the one recorded at the
    base by the reconnaissance, so a slice without it has nothing to compare the after with."""
    require(isinstance(walkthrough, dict),
            f'{label}: slice {sid}: falta walkthrough (objeto com persona, steps, before e after; o '
            f'walkthrough.before é o antes gravado na base pelo reconhecimento)')
    for field in WALKTHROUGH_FIELDS:
        require(nonempty(walkthrough.get(field)), f'{label}: slice {sid}: falta walkthrough.{field} (texto não vazio)')


def slices_of(issue):
    """The slices of an issue, validated: one acceptance-criteria box each, in dependency order (blockers
    first), every one with what it delivers, its seams, its layers and its walkthrough. None when the issue has no `slices`,
    in which case it keeps `acceptance` and `vertical_check`."""
    slices = issue.get('slices')
    if slices is None:
        return None
    label = issue['id']
    require(isinstance(slices, list) and slices, f'{label}: slices precisa ser uma lista com ao menos uma slice')
    # A short issue: the sixth slice is cut out into top-level issues linked by --blocked-by (issue 31, S1).
    # Leftover boxes (P1, P2) are added later, outside the plan, so they never count here.
    require(len(slices) <= SLICES_MAX,
            f'{label}: {len(slices)} slices: uma issue tem no máximo {SLICES_MAX}; o excedente vira issues de topo '
            f'ligadas por --blocked-by (nunca uma sub-issue nova)')
    seen = []
    for index, item in enumerate(slices):
        with at(f'.slices[{index}]'):
            require(isinstance(item, dict),
                    f'{label}: cada slice precisa ser um objeto com id, title, delivers, seams, layers, depends_on e walkthrough')
            sid = item.get('id')
            require(isinstance(sid, str) and SLICE_ID_RULE.fullmatch(sid),
                    f'{label}: slice com id inválido {sid!r}: use um rótulo curto sem espaço, como S1')
            require(sid not in seen, f'{label}: slice repetida {sid}')
            need(nonempty(item.get('title')), f'{label}: slice {sid}: falta title', '.title')
            need(nonempty(item.get('delivers')),
                 f'{label}: slice {sid}: falta delivers (o que dá para demonstrar quando ela termina)', '.delivers')
            for field in ('seams', 'layers'):
                need(strings(item.get(field)), f'{label}: slice {sid}: falta {field} (lista não vazia)', f'.{field}')
            with at('.walkthrough'):
                walkthrough_of(label, sid, item.get('walkthrough'))
            deps = item.get('depends_on', [])   # absent means none ("Depende de: nenhuma")
            require(isinstance(deps, list) and all(isinstance(d, str) for d in deps) and len(deps) == len(set(deps)),
                    f'{label}: slice {sid}: depends_on precisa ser uma lista de ids de slices, sem repetição')
            for dep in deps:
                require(dep != sid, f'{label}: slice {sid} depende de {sid}, ela mesma')
                require(dep in seen,
                        f'{label}: slice {sid} depende de {dep}, que não existe ou vem depois dela: bloqueadoras primeiro')
            seen.append(sid)
    return slices


def validate_plan(plan, project=None):
    require(isinstance(plan, dict) and 'repository' in plan and repository_or_local(plan['repository']),
            'repository must be owner/name, or null for a local project')
    project = board(project, plan['repository'])
    issues = plan.get('issues')
    require(isinstance(issues, list) and 0 < len(issues) <= 24,
            'plan must contain 1..24 session-sized issues; split larger batches')
    ids = set()
    for index, issue in enumerate(issues):
        with at(f'issues[{index}]'):
            require(isinstance(issue, dict) and number(issue.get('id')), 'positive integer issue id required')
            require(issue['id'] not in ids, 'duplicate issue id')
            ids.add(issue['id'])
            sliced = slices_of(issue) is not None   # the slices carry the acceptance and the demonstration
            for field in ('title', 'outcome') + (() if sliced else ('vertical_check',)):
                need(nonempty(issue.get(field)), f'{issue["id"]}: missing {field}', f'.{field}')
            for field in (() if sliced else ('acceptance',)) + ('tests', 'ownership', 'non_goals', 'risks'):
                need(strings(issue.get(field)), f'{issue["id"]}: missing {field}', f'.{field}')
            for position, path in enumerate(issue['ownership']):
                with at(f'.ownership[{position}]'):
                    relative(path)
            need(issue.get('session_sized') is True, 'oversized issue must be decomposed', '.session_sized')
            deps = issue.get('dependencies')
            need(isinstance(deps, list) and all(number(x) for x in deps) and len(deps) == len(set(deps)),
                 'dependencies must be unique integer ids', '.dependencies')
            need(issue.get('status') in STATUSES,
                 f'{issue["id"]}: invalid status {issue.get("status")!r}: use one of {", ".join(sorted(STATUSES))} '
                 '(an issue already published on GitHub is "ready" when its dependencies are met, "blocked" otherwise)',
                 '.status')
            if issue.get('parent') is not None:
                require(number(issue['parent']),
                        f'{issue["id"]}: parent precisa ser o id (inteiro positivo) de uma issue deste plano')
                require(issue['parent'] != issue['id'], f'{issue["id"]}: parent não pode ser a própria issue')
            if issue.get('parent_external') is not None:
                require(number(issue['parent_external']) and issue['parent_external'] != issue['id'],
                        f'{issue["id"]}: parent_external precisa ser o número (inteiro positivo, diferente da própria issue) '
                        'de uma issue já publicada fora deste plano')
                require(issue.get('parent') is None,
                        f'{issue["id"]}: parent_external e parent são exclusivos: use parent para uma issue do plano')
            if issue.get('parent') is not None or issue.get('parent_external') is not None:
                # Only a family that already exists has children: the plan never proposes a sub-issue.
                published = issue.get('status') != 'proposed' and (plan['repository'] is None or nonempty(issue.get('url')))
                require(published,
                        f'{issue["id"]}: sub-issue nova não é proposta: o plano só carrega filhas já publicadas '
                        '(status ready, running, verified ou blocked, com o url da issue); um achado vira critério '
                        'da issue de origem ou issue de topo')
            if project is not None:
                resolve_board(project, issue)
            if issue.get('url'):
                require(plan['repository'] is not None, 'a local plan cannot reference GitHub issue URLs')
                require(issue['url'] == f'https://github.com/{plan["repository"]}/issues/{issue["id"]}',
                        'issue URL does not match repository/id')
    for issue in issues:   # a parent that is in the plan is `parent`: its links, depth and limits are checked offline
        require(issue.get('parent_external') not in ids,
                f'{issue["id"]}: parent_external {issue.get("parent_external")} é uma issue deste plano: use parent')
    graph = {i['id']: i['dependencies'] for i in issues}
    visited, visiting = set(), set()
    def visit(node):
        require(node in graph, f'missing dependency {node}')
        require(node not in visiting, 'circular dependencies')
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    sub_issues(issues)
    return plan


SUB_ISSUES_MAX = 100   # GitHub: sub-issues per parent
SUB_ISSUES_DEPTH = 8   # GitHub: levels of nesting below a top-level issue


def sub_issues(issues):
    """Parent links must stay inside the plan and within GitHub's sub-issue limits.

    `parent` names another issue of this same plan, so the check needs no network.
    Only the plan's children are counted; the children a parent already has on
    GitHub are checked before publishing (`subIssuesSummary.total`).
    """
    by_id = {i['id']: i for i in issues}
    children = {}
    for i in issues:
        parent = i.get('parent')
        if parent is None:
            continue
        require(parent in by_id, f'{i["id"]}: parent {parent} não está no plano; inclua a issue de origem no plano')
        children[parent] = children.get(parent, 0) + 1
    for parent, count in children.items():
        require(count <= SUB_ISSUES_MAX,
                f'{parent}: {count} filhas passam do limite de {SUB_ISSUES_MAX} sub-issues por pai do GitHub')
    for i in issues:
        seen, node, depth = {i['id']}, i, 0
        while node.get('parent') is not None:
            require(node['parent'] not in seen, f'{i["id"]}: ciclo em parent')
            seen.add(node['parent'])
            node, depth = by_id[node['parent']], depth + 1
        require(depth <= SUB_ISSUES_DEPTH,
                f'{i["id"]}: {depth} níveis de sub-issue passam do limite de {SUB_ISSUES_DEPTH} do GitHub')


def schedule(plan, limit):
    """Maximum-cardinality non-conflicting ready wave, deterministic tie-breaking."""
    validate_plan(plan)
    require(number(limit) and limit <= 24, 'concurrency must be 1..24')
    issues = plan['issues']
    active = [i for i in issues if i['status'] == 'running']
    require(len(active) <= limit, 'running issues exceed authorization')
    require(not any(conflicts(a, b) for a, b in itertools.combinations(active, 2)),
            'running issues have overlapping ownership')
    completed = {i['id'] for i in issues if i['status'] == 'verified'}
    require(all(set(i['dependencies']) <= completed for i in active),
            'running issue has an unverified dependency')
    ready = [i for i in issues if i['status'] == 'ready' and
             set(i['dependencies']) <= completed and not any(conflicts(i, a) for a in active)]
    # Bounded at 24 issues. Search larger subsets first so a broad first issue
    # cannot serialize independent narrow slices. No process launch is implied.
    for size in range(min(limit - len(active), len(ready)), 0, -1):
        for group in itertools.combinations(ready, size):
            if not any(conflicts(a, b) for a, b in itertools.combinations(group, 2)):
                return [i['id'] for i in group]
    return []


def publish_order(plan):
    """The ids of a valid plan in the order to publish them: every blocker before the issues it blocks, ties by
    id, so each `gh issue create --blocked-by` can name real numbers at creation."""
    validate_plan(plan)
    pending = {i['id']: set(i['dependencies']) for i in plan['issues']}
    order = []
    while pending:
        ready = sorted(i for i, deps in pending.items() if not deps - set(order))
        order.extend(ready)
        for i in ready:
            del pending[i]
    return order


def context_action(used, reserve):
    if used is None:
        return 'stop'
    require(type(used) is int and used >= 0 and number(reserve), 'invalid context accounting')
    if used + reserve >= 150000:
        return 'stop'
    if used + reserve >= 100000:
        return 'handoff'
    return 'continue'


def authorize(charter, operation):
    """Check an intended structured operation. This does NOT grant permissions."""
    require(isinstance(charter, dict) and isinstance(operation, dict), 'objects required')
    require('repository' in charter and repository_or_local(charter['repository']), 'invalid charter repository')
    for field in ('approved_by', 'approval_reference'):
        require(nonempty(charter.get(field)), f'missing human {field}')
    expiry = dt.datetime.fromisoformat(charter.get('expires_at', ''))
    require(expiry.tzinfo is not None and expiry > dt.datetime.now(dt.timezone.utc), 'authorization expired')
    require(number(charter.get('concurrency')), 'invalid concurrency')
    require(strings(charter.get('stop_conditions')), 'stop conditions required')
    monitor = charter.get('monitoring', {})
    require(monitor.get('mode') in {'phone', 'local', 'alternative'} and
            nonempty(monitor.get('confirmed_by')), 'monitoring arrangement unconfirmed')
    if monitor['mode'] == 'alternative':
        require(nonempty(monitor.get('details')), 'alternative monitoring needs details')
    if monitor['mode'] == 'phone':
        require(monitor.get('phone_connected') is True, 'physical phone not confirmed')
    require('repository' in operation and operation['repository'] == charter['repository'],
            'unapproved repository')
    if 'direct' in operation:
        require('issue' not in operation, 'an operation names an issue or a direct, never both')
        direct = operation['direct']
        require(isinstance(direct, str) and DIRECT_RULE.fullmatch(direct),
                f'invalid direct {direct!r}: a slug of lower-case letters, digits and hyphens, up to 64 characters')
        approved = charter.get('direct_ids', [])
        require(isinstance(approved, list) and direct in approved, 'unapproved direct')
        key, value = 'direct', direct
    else:
        require(number(operation.get('issue')) and operation['issue'] in charter.get('issue_ids', []),
                'unapproved issue')
        key, value = 'issue', operation['issue']
    kind = operation.get('kind')
    require(kind in {'edit', 'test', 'checkpoint', 'draft_pr', 'issue_update', 'merge_into_local_main'} and
            kind in charter.get('operations', []), 'operation outside bounded authorization')
    if kind in {'draft_pr', 'issue_update'}:
        raise ValueError('external write requires native permission; this plugin cannot securely scope generic tools')
    require(nonempty(operation.get('worktree')), 'worktree required')
    try:
        worktree = Path(operation['worktree']).resolve(strict=True)
    except FileNotFoundError:
        raise ValueError(f'the worktree of the operation does not exist: {operation["worktree"]}') from None
    # Only the operation's worktree must exist: another entry of the charter (a slice stacked on another one,
    # declared before it is cut) is validated by shape and compared without resolving it strictly.
    entries = charter.get('worktrees', [])
    require(isinstance(entries, list) and all(isinstance(w, dict) for w in entries), 'invalid worktree entry')
    own = [w for w in entries if w.get(key) == value]
    require(all(w.get('issue') is None or w.get('direct') is None for w in own),
            'invalid worktree entry: issue and direct are exclusive')
    require(all(nonempty(w.get('path')) for w in own), 'invalid worktree entry: path required')
    matches = [w for w in own if Path(w['path']).resolve() == worktree]
    require(len(matches) == 1, 'unapproved or ambiguous worktree')
    selected = matches[0]
    # A slice's worktree (issue 31, S2): the charter entry names the box (`slice`), and an operation
    # on it names the same box, so a worker never edits another slice's worktree by mistake.
    expected, given = selected.get('slice'), operation.get('slice')
    if expected is not None or given is not None:
        require(isinstance(expected, str) and SLICE_ID_RULE.fullmatch(expected),
                'the worktree entry needs a slice label such as S2 when the operation names one')
        require(given == expected, f'operation for slice {given!r} on the worktree of slice {expected!r}')
    branch = operation.get('branch')
    extra = charter.get('protected_branches', [])
    require(isinstance(extra, list) and all(nonempty(p) and p.strip('/') for p in extra),
            'invalid protected_branches')
    # A trailing slash is malformed for Git; normalize it rather than let it match nothing.
    protected = {p.casefold().rstrip('/') for p in {'main', 'master'} | set(extra)}
    # The prefix may not sit inside a protected name or trailing-* namespace.
    namespaces = {p.rstrip('*').rstrip('/') for p in protected} - {''}
    prefix = _cli.branch_prefix(record=charter)[0]
    stem = prefix.rstrip('/').casefold() if isinstance(prefix, str) else ''
    require(nonempty(prefix) and prefix.endswith('/') and nonempty(stem) and
            not any(stem == n or stem.startswith(n + '/') for n in namespaces), 'invalid branch_prefix')
    # Each protected entry p also protects everything below it (p/*), so
    # release/*/hotfix, */hotfix and dev/issue-1 cover their descendants
    # without blocking sibling branches.
    folded = branch.casefold() if nonempty(branch) else ''
    require(nonempty(branch) and branch == selected.get('branch') and branch.startswith(prefix) and
            not any(fnmatch.fnmatchcase(folded, p) or fnmatch.fnmatchcase(folded, p + '/*')
                    for p in protected), 'protected or unapproved branch')
    if kind == 'test':
        argv = operation.get('argv')
        require(strings(argv) and argv in charter.get('verification_commands', []), 'unapproved verification argv')
    elif kind == 'merge_into_local_main':
        # Issue 32, S1: the branch of the issue (never a slice branch) enters the local main, the base branch
        # of the charter, only with the watched run green; a remote-tracking name is never the target.
        require(expected is None and given is None,
                'only the branch of the issue enters the local main, never a slice branch')
        base = charter.get('base')
        require(isinstance(base, dict) and nonempty(base.get('branch')),
                'the charter needs base.branch to name the local main')
        require(not base['branch'].startswith(('origin/', 'refs/', 'remotes/')) and '..' not in base['branch'],
                f'base.branch {base["branch"]!r} names a remote-tracking branch; the local main is a local branch')
        target = operation.get('target')
        require(nonempty(target), 'target required: the local main, the base branch of the charter')
        if target != base['branch']:
            # The base branch of the charter may carry a slash (release/main) and is accepted as it is; any other
            # name with a slash reads as a remote-tracking branch, which is never the target.
            require('/' not in target, f'the remote main is never a target: {target!r} names a remote-tracking branch')
            raise ValueError(f'target {target!r} is not the base branch of the charter ({base["branch"]!r})')
        gates = operation.get('gates')
        require(isinstance(gates, dict), 'gates required: browser_gate green (suite_gate and review_gate optional)')
        for gate, green in LOCAL_MAIN_GATES.items():
            require(gates.get(gate) in green,
                    f'gate {gate} is not green: {gates.get(gate)!r} (green is {" or ".join(green)})')
    else:
        require(nonempty(operation.get('path')), 'target path required')
        target = Path(operation['path'])
        if not target.is_absolute():
            target = worktree / target
        target = target.resolve()
        require(target.is_relative_to(worktree), 'path escapes worktree')
        rel = target.relative_to(worktree).as_posix()
        parts = {p.casefold() for p in target.relative_to(worktree).parts}
        forbidden = {'.git', '.claude', '.codex', '.agents', '.frontlights', '.workflows', 'claude.md', 'agents.md'}
        require(not (parts & forbidden), 'policy and control files require human review')
        require(any(relative(p) != '*' and
                    (relative(rel) == relative(p) or relative(rel).startswith(relative(p) + '/'))
                    for p in selected.get('ownership', [])), 'path outside owned scope')
    return {'scope_check': 'pass', 'permission_granted': False,
            'note': 'Verify actual Git branch/remotes and native permissions before acting.'}


def run(argv, cwd=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=45)
    require(result.returncode == 0, f'{argv[0]} read failed (exit {result.returncode}); inspect credentials/configuration locally')
    return result.stdout


def git_evidence(root):
    root = Path(root).resolve(strict=True)
    def git(*args):
        return run(['git', '-C', str(root), *args])
    head = git('rev-parse', 'HEAD').decode().strip()
    branch = git('branch', '--show-current').decode().strip()
    diff = git('diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD', '--', '.', ':!.frontlights')
    names = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    files = {}
    for raw in sorted(set(names)):
        if not raw:
            continue
        name = os.fsdecode(raw)
        if name.replace('\\', '/').startswith('.frontlights/'):
            continue
        path = root / name
        require(path.resolve().is_relative_to(root), 'tracked/untracked path escapes repository')
        if path.is_symlink():
            files[name] = hashlib.sha256(os.readlink(path).encode()).hexdigest()
        elif path.is_file():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            files[name] = 'missing-or-submodule'
    return {'head': head, 'branch': branch,
            'diff_sha256': hashlib.sha256(diff).hexdigest(),
            'files_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            'files': files}


REVIEW_KEYS = ('head', 'branch', 'diff_sha256', 'files_sha256')


def review_gate(saved, current):
    """Whether an independent review still covers the code: `saved` is the `evidence` output taken when the
    reviewer was bound to it (bare, or under `evidence` or `git` as a checkpoint keeps it), `current` the evidence
    now. Any difference in HEAD, branch, diff or files makes the review stale, so the author's later commit,
    edit or new file is never reported as reviewed."""
    if isinstance(saved, dict) and not all(key in saved for key in REVIEW_KEYS):
        saved = saved.get('evidence') if isinstance(saved.get('evidence'), dict) else saved.get('git')
    # `branch` is empty on a detached HEAD; the other three always carry a hash.
    require(isinstance(saved, dict) and all(isinstance(saved.get(key), str) and (saved[key] or key == 'branch')
                                            for key in REVIEW_KEYS),
            'the review file needs the saved evidence: head, branch, diff_sha256 and files_sha256 '
            '(the output of the evidence command taken when the review was bound)')
    changed = [key for key in REVIEW_KEYS if saved[key] != current[key]]
    before, after = saved.get('files'), current['files']
    files_changed = sorted(name for name in (set(before) | set(after))
                           if before.get(name) != after.get(name)) if isinstance(before, dict) else []
    return {'status': 'stale' if changed else 'current', 'changed': changed, 'files_changed': files_changed,
            'reviewed_head': saved['head'], 'current_head': current['head']}


def drift(snapshot, current):
    return [key for key in ('number', 'title', 'body', 'state', 'labels', 'assignees', 'updated_at')
            if snapshot.get(key) != current.get(key)]


PENDING_NAME = re.compile(r'[a-z][a-z0-9_]{0,39}')


def pending_names(pending):
    """Open obligations a session carries over (`teste_assistido`, say): short lowercase names, no repeats."""
    names = list(pending or [])
    require(all(isinstance(name, str) and PENDING_NAME.fullmatch(name) for name in names),
            'pending names are short lowercase words, for example teste_assistido')
    return sorted(set(names))


def checkpoint(root, issue, handoff, next_step, pending=(), slice_id=None):
    root, handoff = Path(root).resolve(strict=True), Path(handoff).resolve()
    require(handoff.is_file(), 'durable handoff file required')
    require(number(issue.get('number')) and nonempty(issue.get('body')) and
            (nonempty(issue.get('html_url')) or issue.get('source') == 'local'),
            'current canonical GitHub issue snapshot, or a local issue with source "local", required')
    require(nonempty(next_step), 'next concrete step required')
    if slice_id is not None:   # the acceptance-criteria box in progress, so the next window resumes there
        require(isinstance(slice_id, str) and SLICE_ID_RULE.fullmatch(slice_id),
                'slice is a short label without spaces, such as S2')
    return {'version': 1, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'root': str(root), 'issue': issue, 'git': git_evidence(root),
            'handoff_sha256': hashlib.sha256(handoff.read_bytes()).hexdigest(),
            'next_step': next_step, 'pending': pending_names(pending), 'slice': slice_id}


def resume(root, saved, current_issue, handoff):
    require(saved.get('version') == 1, 'unsupported checkpoint version')
    require(Path(root).resolve(strict=True) == Path(saved['root']).resolve(strict=True),
            'checkpoint belongs to a different worktree')
    require(saved['issue'].get('number') == current_issue.get('number') and
            saved['issue'].get('html_url') == current_issue.get('html_url') and
            saved['issue'].get('source') == current_issue.get('source'),
            'checkpoint belongs to a different issue/repository')
    live = git_evidence(root)
    changed = drift(saved['issue'], current_issue)
    git_changed = [k for k in ('head', 'branch', 'diff_sha256', 'files_sha256') if saved['git'].get(k) != live.get(k)]
    handoff_changed = hashlib.sha256(Path(handoff).read_bytes()).hexdigest() != saved['handoff_sha256']
    return {'state': 'reconcile' if changed or git_changed or handoff_changed else 'unchanged',
            'issue_drift': changed, 'git_drift': git_changed, 'handoff_changed': handoff_changed,
            'pending': pending_names(saved.get('pending')), 'next_step': saved['next_step'],
            'slice': saved.get('slice'),
            'required': 'Read current GitHub issue, handoff and diff before continuing.'}


def issue_snapshot(value, tree, main, gh=None):
    """(snapshot, number) for `checkpoint` and `resume`. `value` a JSON file is the snapshot the session saved
    (the form of before, kept one cycle; number None); an issue number, or nothing (the issue of the charter entry
    of the tree, `_cli.issue_number`), is read by the script: `gh api repos/<repository>/issues/<n>` with the
    `repository` of the config of the main worktree, or `.frontlights/issues/<n>/issue.json` (`source: local`) of
    the main worktree in a project without a remote."""
    if value is not None and not str(value).strip().lstrip('#').isdigit():
        return load(value), None
    number = _cli.issue_number(value, tree, main)
    config = _cli.config_path(None, main, required=False)
    repository = load(config).get('repository') if config else None
    if repository is None:
        local = Path(main) / '.frontlights' / 'issues' / str(number) / 'issue.json'
        require(local.is_file(), f'sem repository no config e sem {local.as_posix()}: passe --issue <arquivo.json>')
        return load(local), number
    require(repository_or_local(repository), 'repository in the configuration must be owner/name')
    answer = (gh or _cli.gh_json)(['api', f'repos/{repository}/issues/{number}'])
    require(isinstance(answer, dict) and answer.get('number') == number,
            f'o gh não leu a issue #{number} de {repository}: confira a conta (gh auth status) e o número')
    return answer, number


def checkpoint_file(tree, number, slice_id=None):
    """`<tree>/.frontlights/issues/<n>/checkpoint.json`, or `checkpoint-<slice>.json` for a slice worktree."""
    name = f'checkpoint-{slice_id}.json' if slice_id else 'checkpoint.json'
    return Path(tree) / '.frontlights' / 'issues' / str(number) / name


def checkpoint_cli(issue, tree, handoff, next_step, pending=(), slice_id=None, gh=None, main=None):
    """`checkpoint`: by issue number the snapshot is read and the checkpoint is also saved (`saved` names it)."""
    main = main or str(_cli.main_worktree(tree))
    snapshot, number = issue_snapshot(issue, tree, main, gh)
    record = checkpoint(tree, snapshot, handoff, next_step, pending, slice_id)
    if number is None:
        return record
    path = checkpoint_file(tree, number, slice_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)
    return {**record, 'saved': str(path)}


def resume_cli(issue, tree, handoff, saved, gh=None, main=None, slice_id=None):
    """`resume`: by issue number the snapshot is read and `--checkpoint` defaults to the file `checkpoint` saved."""
    main = main or str(_cli.main_worktree(tree))
    snapshot, number = issue_snapshot(issue, tree, main, gh)
    if saved is None:
        require(number is not None, 'resume com --issue <arquivo> precisa de --checkpoint <arquivo>')
        saved = checkpoint_file(tree, number, slice_id)
        require(saved.is_file(), f'sem checkpoint em {saved.as_posix()}: passe --checkpoint <arquivo>')
    return resume(tree, load(saved), snapshot, handoff)


ROUND_SUFFIX = re.compile(r'-r([1-9][0-9]{0,3})$')


def archive_round(root, number):
    """Close a round of an issue's homologation: `.frontlights/issues/<n>/browser/result.json` and every
    `merge-local-main*.json` of `.frontlights/issues/<n>/` get the suffix `-r<k>` of the round (k = one past the
    highest round already archived there), so the next round starts without the records of the previous one. A
    name already taken is refused before anything is renamed; nothing is deleted."""
    folder = Path(root) / '.frontlights' / 'issues' / str(number)
    files = [folder / 'browser' / 'result.json'] + sorted(folder.glob('merge-local-main*.json'))
    current = [f for f in files if f.is_file() and not ROUND_SUFFIX.search(f.stem)]
    done = [int(m.group(1)) for f in [*folder.glob('*.json'), *folder.glob('browser/*.json')]
            if (m := ROUND_SUFFIX.search(f.stem))]
    round_ = max(done, default=0) + 1
    moves = [(f, f.with_name(f'{f.stem}-r{round_}{f.suffix}')) for f in current]
    taken = [target.name for _, target in moves if target.exists()]
    require(not taken, f'já existe {", ".join(taken)}: nada foi renomeado')
    for origin, target in moves:
        os.replace(origin, target)
    renamed = [{'from': o.relative_to(folder).as_posix(), 'to': t.relative_to(folder).as_posix()} for o, t in moves]
    message = (f'rodada {round_} da issue #{number} arquivada: {len(renamed)} registro(s) renomeado(s)' if renamed
               else f'nada a arquivar na issue #{number}: nenhum result.json nem merge-local-main*.json da rodada')
    return {'ok': True, 'exitCode': 0, 'issue': number, 'round': round_ if renamed else max(done, default=0),
            'renamed': renamed, 'message': message}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('RoadS redirect refused; configure the final approved endpoint')


LONG_PATH_LIMIT = 160
SHORT_BASE_ADVICE = ('Git worktrees under this root may exceed the Windows path limit; propose a short '
                     'worktree base such as C:/wt/<project> and ask before using it.')


def path_risk(given, resolved, platform=None):
    """Flag roots where `git worktree add` can fail on Windows ('$GIT_DIR' too big).

    Packaged desktop apps may redirect AppData into a much longer
    `Packages/<app>/LocalCache` path that Git sees but the user never typed.
    """
    platform = platform or sys.platform
    given_n, resolved_n = (str(p).replace('\\', '/').rstrip('/') for p in (given, resolved))
    result = {'status': 'ok', 'length': max(len(given_n), len(resolved_n))}
    if not platform.startswith('win'):
        return result
    lowered = resolved_n.casefold()
    if given_n.casefold() != lowered and '/packages/' in lowered and '/localcache/' in lowered:
        result.update(status='virtualized', resolved=resolved_n, advice=SHORT_BASE_ADVICE)
    elif result['length'] > LONG_PATH_LIMIT:
        result.update(status='long_path', advice=SHORT_BASE_ADVICE)
    return result


def verification_candidates(root):
    """Candidate argv from repository files. Candidates, never approved commands."""
    root = Path(root)
    pyproject = root / 'pyproject.toml'
    if (root / 'pytest.ini').is_file() or (
            pyproject.is_file() and '[tool.pytest' in pyproject.read_text(encoding='utf-8', errors='replace')):
        return [['python', '-m', 'pytest']]
    if (root / 'tests').is_dir() and any((root / 'tests').glob('test*.py')):
        return [['python', '-m', 'unittest', 'discover', '-s', 'tests', '-v']]
    return []


def validate_test_blocks(config, path):
    """Refuse the browserTest and checks blocks with the config-only rules of serve.py and checks.py.

    Absent or null blocks: nothing is read. The validators read `path`, the file `config` was loaded from (no
    copy of the test password is written anywhere). The refusal text gets the checks mask (test login and
    password, also percent-encoded), so it never echoes a secret. A browserTest that declares only the accounts
    (the project starts its own environment) is valid: it comes back as a warning, never as a refusal.
    Returns the list of warnings.
    """
    warnings = []
    browser, block = config.get('browserTest'), config.get('checks')
    if browser is None and block is None:
        return warnings
    require(path is not None, 'browserTest/checks: o inspect precisa do caminho do config para validar os blocos')
    import checks
    import serve
    checks.load_user_secrets(path)
    try:
        if browser is not None:
            checks.require_maskable_user_secrets(path)
            if not serve.load_block(path, need_processes=False):
                warnings.append('browserTest.processes não está declarado: o serve não tem o que subir, então o ambiente precisa '
                                'estar no ar antes do teste (só as contas e a baseUrl foram conferidas).')
            checks.require_local_declarations(path)
            validate_isolated_block(config)
            if browser.get('frontPaths') is not None:
                import browser_gate
                browser_gate.validate_front_paths(browser['frontPaths'])
            else:
                warnings.append('browserTest.frontPaths não está declarado: o browser-gate estima os arquivos visíveis pelo nome '
                                '(telas, estilos, imagens de assets); declare os caminhos de tela do projeto para que nenhuma '
                                'mudança visível passe em silêncio.')
        if block is not None:
            if not isinstance(block, dict):
                raise checks.Refused('checks precisa ser um objeto com regression, integration ou smoke.')
            for name in ('regression', 'integration'):
                if name in block:
                    checks.command_settings(path, name)
            if 'smoke' in block:
                checks.smoke_settings(path)
            checks.optional_name(block.get('backend'), 'checks.backend')
    except (serve.Refusal, checks.Refused, checks.Infra) as refusal:
        raise ValueError(checks.redact(str(refusal))) from None
    return warnings


def validate_isolated_block(config):
    """Refuse an invalid `browserTest.isolated` (the assisted test in its own processes and ports, on the local
    development database itself, never a copy: a block that still declares `copyDatabase` or `dropDatabase`, even
    null, is refused). Absent or null: nothing is checked. Works on the config already read: the caller masks the
    refusal text."""
    import checks
    block = config['browserTest'].get('isolated')
    if block is None:
        return
    if not isinstance(block, dict):
        raise checks.Refused('browserTest.isolated precisa ser um objeto com baseUrl e processes.')
    stale = [field for field in ('copyDatabase', 'dropDatabase') if field in block]
    if stale:
        raise checks.Refused(f'browserTest.isolated não aceita mais {" nem ".join(stale)}: o teste assistido roda no '
                             'banco de desenvolvimento local, sem cópia; apague os campos copyDatabase e dropDatabase '
                             'do bloco.')
    if not isolated_local_url(block.get('baseUrl')):
        raise checks.Refused('browserTest.isolated.baseUrl precisa ser uma URL http(s) em host local (127.0.0.1, '
                             'localhost ou ::1), sem usuário e senha; {port} pode ocupar o lugar da porta.')
    import serve
    where = 'browserTest.isolated.processes'
    try:
        processes = serve.validate_processes(block.get('processes'), where)
    except serve.Refusal as refusal:  # the serve text names the process, not the block: say which list it is
        message = str(refusal)
        raise checks.Refused(message if where in message else f'{where}: {message}') from None
    base_url = block['baseUrl']
    for item in processes:
        if not isolated_local_url(item['health']):
            raise checks.Refused(f'{where}: o health do processo {item["name"]} declara um host que não é local; a '
                                 'instância isolada só roda na própria máquina (127.0.0.1, localhost ou ::1).')
        cwd = item.get('cwd')
        folder = PureWindowsPath(cwd) if cwd else None  # splits on / and \, and sees a drive (C:) or a root
        if folder is not None and (folder.anchor or '..' in folder.parts):  # serve never starts these: check here
            raise checks.Refused(f'{where}: o processo {item["name"]} declara um cwd que sai da worktree; o cwd '
                                 'precisa ser relativo a ela, sem ".." e sem unidade ou raiz.')
    browser = config['browserTest']
    preview = config.get('preview') if isinstance(config.get('preview'), dict) else {}
    taken = {'preview.processes': fixed_ports(preview.get('processes')),
             'browserTest.processes': fixed_ports(browser.get('processes'))}
    if checks.PORT_PLACEHOLDER not in base_url:
        base_port = serve.url_port(urllib.parse.urlsplit(base_url))
        if base_port is None:
            raise checks.Refused('browserTest.isolated.baseUrl tem uma porta inválida: use uma porta de 1 a 65535 '
                                 'ou {port}.')
        clash = [f'{key} ({url})' for key, url in (('preview.baseUrl', preview.get('baseUrl')),
                                                   ('browserTest.baseUrl', browser.get('baseUrl')))
                 if fixed_url_port(url) == base_port]
        clash += [f'o processo {ports[base_port]} de {other}' for other, ports in taken.items() if base_port in ports]
        if clash:
            raise checks.Refused(f'browserTest.isolated.baseUrl usa a porta {base_port}, que colide com '
                                 f'{" e ".join(clash)}: o teste assistido nunca roda nas portas da prévia nem do '
                                 'serve.')
        if base_port not in fixed_ports(processes):
            raise checks.Refused(f'browserTest.isolated.baseUrl usa a porta fixa {base_port}, mas nenhum processo de '
                                 f'{where} usa essa porta (port inteiro ou porta do health): ninguém responderia '
                                 'nela. Use a porta fixa de um processo ou {port} com um processo de port "auto".')
    for port, name in fixed_ports(processes).items():
        for other, ports in taken.items():
            if port in ports:
                raise checks.Refused(f'{where}: o processo {name} usa a porta fixa {port}, a mesma do processo '
                                     f'{ports[port]} em {other}. A instância isolada nunca roda nas portas da prévia '
                                     'nem do serve: use port "auto" (com {port} no health) ou outra porta.')
    if checks.PORT_PLACEHOLDER in base_url and not any(serve.is_auto(item) for item in processes):
        raise checks.Refused('browserTest.isolated.baseUrl usa {port}, mas nenhum processo de '
                             'browserTest.isolated.processes tem port "auto": a que porta ele se referiria? Use a '
                             'porta fixa do processo na baseUrl ou port "auto" no processo.')


def fixed_url_port(url):
    """Port of a declared base URL without `{port}`; None when it is absent, automatic or unreadable."""
    import checks
    import serve
    if not isinstance(url, str) or checks.PORT_PLACEHOLDER in url:
        return None
    try:
        return serve.url_port(urllib.parse.urlsplit(url))
    except ValueError:
        return None


def fixed_ports(processes):
    """{port: process name} of the processes that do not use port "auto" (the integer `port`, or else the port of
    the health URL). Read-only and lenient: items this block's own validator would refuse are skipped here."""
    import serve
    ports = {}
    for item in processes if isinstance(processes, list) else []:
        if not isinstance(item, dict) or serve.is_auto(item):
            continue
        port = item.get('port')
        if not isinstance(port, int) or isinstance(port, bool):
            health = item.get('health')
            try:
                port = serve.url_port(urllib.parse.urlsplit(health)) if isinstance(health, str) else None
            except ValueError:
                port = None
        if port is not None:
            ports.setdefault(port, item.get('name'))
    return ports


def isolated_local_url(value):
    """True for an http(s) URL on this machine, without credentials; `{port}` stands for an automatic port."""
    import checks
    if not isinstance(value, str) or not value or '\0' in value:
        return False
    try:
        parts = urllib.parse.urlsplit(value.replace(checks.PORT_PLACEHOLDER, checks.STAND_IN_PORT))
        parts.port  # an out-of-range or non-numeric port raises here
    except ValueError:
        return False
    return parts.scheme in ('http', 'https') and (parts.hostname or '').lower() in checks.LOCAL_HOSTS \
        and '@' not in parts.netloc


def validate_homolog_block(config):
    """Refuse an invalid `homolog` block (`homolog.backupDir`, the backup folder of `homolog bundle`, and
    `homolog.suites`, the suites of `homolog suite`) with the rules of homolog.py. An absent, null or valid block adds
    nothing to the output, and the folder itself is not checked here: inspect is read-only and `bundle` checks it at
    run time."""
    if config.get('homolog') is None:
        return
    import homolog
    try:
        homolog.backup_dir(config)
        homolog.suite_block(config)
    except homolog.Refusal as refusal:
        raise ValueError(str(refusal)) from None


def validate_preview_block(config, path, root):
    """Refuse an invalid top-level `preview` block with the rules of `serve preview` (worktree inside `root`,
    branch, baseUrl, processes). Absent or null: nothing is read. The refusal gets the masks of serve (loaded by
    `load_preview_block` from browserTest.users) and of checks, so it never echoes a test login or password."""
    if config.get('preview') is None:
        return
    require(path is not None, 'preview: o inspect precisa do caminho do config para validar o bloco')
    import checks
    import serve
    try:
        serve.load_preview_block(path, root)
    except serve.Refusal as refusal:  # a process-level text names the process, not the block: say which one
        message = str(refusal) if 'preview' in str(refusal) else f'preview: {refusal}'
        raise ValueError(checks.redact(serve.protect(message))) from None


def validate_preview_ports(config):
    """With the `preview` block present (already validated), refuse a fixed port of `browserTest.processes` (integer
    `port`, or else the port of the health) or of `browserTest.baseUrl` that is a fixed port of the preview (one of
    `preview.processes`, or the port of `preview.baseUrl`), with or without `browserTest.isolated`: the assisted test
    never runs on the ports of the preview. `auto` and `{port}` never collide here."""
    browser, preview = config.get('browserTest'), config.get('preview')
    if not isinstance(browser, dict) or not isinstance(preview, dict):
        return
    import checks
    import serve
    base_url = preview.get('baseUrl')
    taken = fixed_ports(preview.get('processes'))

    def sides(port):
        found = [f'da preview.baseUrl ({base_url})'] if fixed_url_port(base_url) == port else []
        return found + ([f'do processo {taken[port]} de preview.processes'] if port in taken else [])
    clashes = [(f'browserTest.processes: o processo {name} usa a porta fixa {port}', sides(port))
               for port, name in fixed_ports(browser.get('processes')).items()]
    own = fixed_url_port(browser.get('baseUrl'))
    if own is not None:
        clashes.append((f'browserTest.baseUrl ({browser["baseUrl"]}) usa a porta {own}', sides(own)))
    for what, found in clashes:
        if found:
            message = (f'{what}, a mesma {" e ".join(found)}: o teste assistido nunca roda nas portas da '
                       'prévia. Use port "auto" (com {port} no health e na browserTest.baseUrl) ou outra porta.')
            raise ValueError(checks.redact(serve.protect(message)))


def inspect(config, root, config_path=None, summary=False):
    # A missing key is a typo, not a local project: only an explicit null disables GitHub.
    require('repository' in config and repository_or_local(config['repository']),
            'repository must be owner/name, or null for a local project')
    warnings = validate_test_blocks(config, config_path)
    validate_preview_block(config, config_path, root)
    validate_preview_ports(config)
    validate_homolog_block(config)
    repo = config['repository']
    result = {'repository': repo, 'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'sources': {}, 'verification_commands': {},
              'verification_candidates': verification_candidates(root),
              'path_risk': path_risk(Path(root).absolute(), os.path.realpath(root))}
    if repo is None:
        result['sources']['github'] = {'status': 'unconfigured'}
    else:
        try:
            raw = run(['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/issues?state=all&per_page=100'])
            pages = json.loads(raw)
            require(isinstance(pages, list) and all(isinstance(page, list) and
                    all(isinstance(i, dict) and number(i.get('number')) for i in page)
                    for page in pages), 'malformed GitHub paginated response')
            result['sources']['github'] = {'status': 'available', 'source': f'https://github.com/{repo}/issues',
                                           'issues': [i for page in pages for i in page if 'pull_request' not in i]}
        except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            result['sources']['github'] = {'status': 'unavailable', 'reason': 'GitHub read failed; check gh authentication and repository access'}
    project = board(config.get('project'), repo)
    if project is None:
        result['sources']['project'] = {'status': 'unconfigured'}
    else:
        board_summary = {'owner': project['owner'], 'number': project['number'],
                   'defaults': {k: v for k, v in project['fields'].items() if v is not None},
                   'choose_per_issue': sorted(k for k, v in project['fields'].items() if v is None),
                   'assignee': project['assignee'], 'issue_type': project['issue_type'],
                   'labels': project['labels'], 'issue_type_by_label': project['issue_type_by_label'],
                   'body_fields': project['body_fields']}
        try:
            view = json.loads(run(['gh', 'project', 'view', str(project['number']),
                                   '--owner', project['owner'], '--format', 'json']))
            require(isinstance(view, dict) and nonempty(view.get('title')), 'malformed project response')
            result['sources']['project'] = {'status': 'available', 'title': view['title'],
                                            'url': view.get('url'), **board_summary}
        except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            result['sources']['project'] = {'status': 'unavailable', **board_summary,
                                            'reason': 'project board read failed; check gh "project" scope and board access'}
    roads = config.get('roads')
    if not roads:
        result['sources']['roads'] = {'status': 'unconfigured'}
    else:
        try:
            url = roads['observations_url']
            parsed = urllib.parse.urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and
                    not parsed.password and not parsed.query and not parsed.fragment,
                    'RoadS requires HTTPS endpoint without credentials/query/fragment')
            token = os.environ.get(roads.get('token_env', ''))
            require(token, 'RoadS token unavailable')
            request = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
            with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
                raw = response.read(2_000_001)
            require(len(raw) <= 2_000_000, 'RoadS payload exceeds the size limit')
            result['sources']['roads'] = {'status': 'available', 'source': url, 'data': json.loads(raw)}
        except (ValueError, OSError, KeyError):
            result['sources']['roads'] = {'status': 'unavailable', 'reason': 'RoadS read failed; verify endpoint contract and token locally'}
    package = Path(root) / 'package.json'
    if package.exists():
        result['verification_commands'] = json.loads(package.read_text(encoding='utf-8')).get('scripts', {})
    if warnings:
        result['warnings'] = warnings
    return summarize(result) if summary else result


def summarize(result):
    """The `inspect --summary` output: the same keys plus `summary: true`, with the GitHub issues cut to number,
    title, state and acceptance-criteria boxes (`closeout.criteria`, None without that section) and counted, and
    the RoadS payload counted instead of dumped. The board (`sources.project`) and a source that is not
    `available` keep what they say."""
    import closeout
    result = dict(result, summary=True, sources=dict(result['sources']))
    github = result['sources'].get('github', {})
    if github.get('status') == 'available':
        issues = []
        for issue in github['issues']:
            boxes = closeout.criteria(issue.get('body'))
            issues.append({'number': issue['number'], 'title': issue.get('title'), 'state': issue.get('state'),
                           'boxes': None if boxes is None else {'checked': boxes[0], 'total': boxes[1]}})
        result['sources']['github'] = {'status': 'available', 'source': github.get('source'), 'count': len(issues),
                                       'open': sum(i['state'] == 'open' for i in issues), 'issues': issues}
    roads = result['sources'].get('roads', {})
    if roads.get('status') == 'available':
        data = roads.get('data')
        short = {'status': 'available', 'source': roads.get('source'),
                 'count': len(data) if isinstance(data, list) else None}
        if isinstance(data, dict):
            short['keys'] = sorted(data)[:50]
        result['sources']['roads'] = short
    return result


SKILL_ROOT = Path(__file__).resolve().parents[1]


def git_text(root, *args, timeout=30):
    """Stripped stdout of a Git command run in `root`; raises on any failure."""
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, f'git {args[0]} failed (exit {result.returncode})')
    return result.stdout.strip()


def git_ok(root, *args, timeout=30):
    """Whether a Git command exits 0, for predicates such as `merge-base --is-ancestor`."""
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=timeout).returncode == 0


def update_check(skill_root=SKILL_ROOT):
    """Compare the installed skill's commit with the tip of the branch it tracks.

    The skill is a Git checkout (or a junction into one), so "installed" is `HEAD` and
    "published" is what the remote reports for the upstream branch. `git ls-remote` asks the
    remote and writes nothing locally; a published tip that is not an ancestor of `HEAD`
    means the remote moved on. Read only; it never pulls.
    """
    result = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'skill': 'frontlights',
              'installed': None, 'published': None}
    try:
        root = git_text(skill_root, 'rev-parse', '--show-toplevel')
        result['root'] = root
        head = git_text(root, 'rev-parse', 'HEAD')
        result['installed'] = head[:12]
        upstream = git_text(root, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
        remote, _, branch = upstream.partition('/')
        require(remote and branch, 'no upstream branch')
        listed = git_text(root, 'ls-remote', '--heads', remote, branch)
        published = listed.split()[0] if listed else ''
        require(re.fullmatch(r'[0-9a-f]{40}', published), 'remote branch not found')
        result['published'] = published[:12]
        result['source'] = f'{remote}/{branch}'
    except (ValueError, OSError, subprocess.TimeoutExpired):
        result['status'] = 'unavailable'
        result['reason'] = 'published commit could not be read; check the network, the Git remote and the upstream branch'
        return result
    if published == head or git_ok(root, 'merge-base', '--is-ancestor', published, head):
        result['status'] = 'current'   # equal, or a checkout ahead of what is published (development)
    else:
        result['status'] = 'update_available'
        result['commands'] = [f'git -C "{root}" pull --ff-only']
    return result

OPEN_QUESTION = 'Fechar as issues que já têm todos os critérios marcados?'


def open_session(config, root, gh=None, fetch=True):
    """`open` (issue 2 of the redesign): the reads of the opening in one command. `git fetch --prune origin` (the one
    write: remote-tracking refs, never a branch or a worktree), then `cleanup.py plan --from-authorizations` and
    `closeout.py candidates`, in the same process. It removes, closes and asks nothing: `cleanup.py run` executes the
    cleanup, and the closing question waits for the session. A part that fails becomes a warning; the other runs."""
    import cleanup   # noqa: PLC0415  (lazy: both import this module)
    import closeout  # noqa: PLC0415
    warnings = []
    result = {'ok': True, 'exitCode': 0, 'operation': 'open', 'fetched': False, 'cleanup': None, 'closeout': None,
              'warnings': warnings}
    try:
        origin = cleanup.has_origin(root)
        if fetch and origin:
            code, _ = cleanup.git(root, 'fetch', '--prune', cleanup.REMOTE)
            result['fetched'] = code == 0
            if code != 0:
                warnings.append('fetch_failed: o git fetch --prune origin falhou; a limpeza e o fechamento julgaram '
                                'pelo origin/<base> da última busca')
        elif not origin:
            warnings.append('no_origin: o projeto não tem o remoto origin; nada foi buscado')
    except cleanup.Refusal as error:
        warnings.append(f'fetch_failed: {error}')
    plan = cleanup.run('plan', config, root, gh=gh, from_authorizations=True)
    if plan.get('ok'):
        result['cleanup'] = {
            'commands': plan['commands'],
            'ask': [{'key': c['key'], 'branch': c['branch'], 'path': c['path'], 'askReason': c.get('askReason'),
                     'askIgnored': c.get('askIgnored', [])} for c in plan['candidates'] if c['ask']],
            'excluded': plan['excluded'], 'alreadyClean': plan['alreadyClean'], 'candidates': len(plan['candidates']),
            'issues': plan.get('issues', []), 'expectedBase': plan.get('expectedBase')}
    else:
        warnings.append(f"cleanup_failed: {plan.get('message')}")
    found = closeout.run('candidates', config, root, gh=gh)
    if found.get('ok'):
        issues = [{'number': c['number'], 'title': c['title'], 'order': c['order'], 'level': c['level'],
                   'parent': c['parent'], 'cautions': c['cautions'], 'pendingOutside': c['pendingOutside'],
                   'parentTicks': c['parentTicks']} for c in found['candidates']]
        result['closeout'] = {'ask': bool(issues), 'count': len(issues), 'issues': issues,
                              'awaiting_release': [e['number'] for e in found['excluded'] if e['reason'] == 'awaiting_release'],
                              'excluded': len(found['excluded']), 'alreadyDone': found['alreadyDone']}
        if issues:
            result['closeout']['question'] = OPEN_QUESTION
    else:
        warnings.append(f"closeout_failed: {found.get('message')}")
    parts = []
    if result['cleanup'] is not None:
        count = result['cleanup']['candidates']
        parts.append(f'Limpeza: {count} item(ns) para remover sem pergunta com `cleanup.py run --from-authorizations`'
                     if count else 'Limpeza: nada a remover')
        if result['cleanup']['ask']:
            parts.append(f"{len(result['cleanup']['ask'])} com arquivos ignorados pedem pergunta própria (`ask`)")
    if result['closeout'] is not None:
        parts.append(f"Fechamento: {result['closeout']['count']} issue(s) prontas; pergunte \"{OPEN_QUESTION}\""
                     if result['closeout']['ask'] else 'Fechamento: nenhuma issue pronta para fechar')
        if result['closeout']['awaiting_release']:
            parts.append('esperam a release: ' + ', '.join(f'#{n}' for n in result['closeout']['awaiting_release']))
    parts.append('Nada foi removido nem fechado')
    result['message'] = '. '.join(parts) + '.'
    return result


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def build_parser():
    parser = _cli.JsonParser(prog='frontlights.py', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate-plan', 'schedule'):
        p = sub.add_parser(name)
        p.add_argument('--plan', required=True)
        if name == 'schedule':
            p.add_argument('--limit', type=int, required=True)
        else:
            p.add_argument('--config', help='.frontlights/config.json; enforces its project board fields')
    p = sub.add_parser('authorize')
    p.add_argument('--charter', required=True)
    p.add_argument('--operation', required=True, help='the operation JSON file, or - to read it from standard input')
    p = sub.add_parser('context')
    p.add_argument('--used', type=int)
    p.add_argument('--reserve', type=int, required=True)
    p.add_argument('--pending', action='append', default=[], help='open obligation, e.g. teste_assistido; repeatable')
    p = sub.add_parser('inspect')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--summary', action='store_true',
                   help='per source the status and the count; per issue only number, title, state and boxes')
    p = sub.add_parser('open', help='the opening reads in one command: git fetch --prune, cleanup plan '
                                    '--from-authorizations and closeout candidates; removes and closes nothing')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--no-fetch', action='store_true', dest='no_fetch', help='skip git fetch --prune origin')
    p = sub.add_parser('evidence')
    p.add_argument('--root', help='default: the worktree of the current directory')
    p = sub.add_parser('review-gate')
    p.add_argument('--root', help='default: the worktree of the current directory')
    p.add_argument('--review', required=True, help='saved evidence output taken when the independent review was bound')
    p = sub.add_parser('browser-gate')
    p.add_argument('--root', action='append',
                   help='worktree of the issue, or of one of its slices (named in --stacked with the branch of its issue); '
                        'repeatable (default: the worktree of the current directory)')
    p.add_argument('--base', required=True, help='approved base of the issue (the local main, or the branch it is stacked on), the same for every --root')
    p.add_argument('--config', help='.frontlights/config.json (browserTest and browserTest.frontPaths; default: the '
                                    'one of the main worktree, when it exists)')
    p.add_argument('--toca', choices=['sim', 'nao', 'não', 'ausente'], help="the plan's `Toca o frontend:`")
    p.add_argument('--record', help='the batch result.json, which may not exist yet')
    p.add_argument('--stacked', action='append', default=[], metavar='BRANCH=TARGET',
                   help='the branch of a stacked issue and the branch its PR targets (its base in the stacking authorization); repeatable')
    sub.add_parser('update-check')
    p = sub.add_parser('publish-order')
    p.add_argument('--plan', required=True, help='the plan; prints its issue ids blockers first, for --blocked-by')
    for name in ('checkpoint', 'resume'):
        p = sub.add_parser(name)
        p.add_argument('--root', help='default: the worktree of the current directory')
        p.add_argument('--issue', help='the issue number, read with gh (default: the issue of the charter entry of '
                                       'the worktree); or a saved gh api issue JSON file, the form of before')
        p.add_argument('--handoff', required=True)
        p.add_argument('--slice', help='the slice (acceptance-criteria box) in progress, e.g. S2')
        if name == 'checkpoint':
            p.add_argument('--next-step', required=True)
            p.add_argument('--pending', action='append', default=[], help='open obligation, e.g. teste_assistido; repeatable')
        else:
            p.add_argument('--checkpoint', help='default, with an issue number: the file checkpoint saved')
    p = sub.add_parser('archive', help='close a round of the homologation of an issue: result.json and '
                                       'merge-local-main*.json get the suffix -r<k>')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--issue', help='the issue number (default: the issue of the charter entry of the worktree)')
    p = sub.add_parser('drift')
    p.add_argument('--snapshot', required=True)
    p.add_argument('--current', required=True)
    p = sub.add_parser('homolog', help='homolog.py: `sync`, `bundle` and `release-plan` of the local main, '
                                       'the homologation (issue 32), and `suite` and `suite-gate` (issue 52)')
    p.add_argument('homolog_args', nargs=argparse.REMAINDER, help='the operation and its options, e.g. sync --root .')
    p = sub.add_parser('stamp', add_help=False,
                       help='stamp.py: binds the approval of a document to its exact content (issue 61); '
                            'delegated before this parser runs')
    p.add_argument('stamp_args', nargs=argparse.REMAINDER, help='the file and its options, e.g. spec.md --check')
    return parser


def resolve_defaults(args):
    """--root and --config the command line left out, by the rules of `_cli`."""
    if args.command == 'inspect':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root)
    elif args.command == 'open':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root)
    elif args.command in ('evidence', 'review-gate', 'checkpoint', 'resume'):
        args.root = str(_cli.tree_path(args.root))
    elif args.command == 'archive':
        args.root = str(_cli.root_path(args.root))
        args.issue = _cli.issue_number(args.issue, _cli.current_tree(), args.root)
    elif args.command == 'browser-gate':
        args.root = args.root or [str(_cli.current_tree())]
        args.config = _cli.config_path(args.config, _cli.main_worktree(args.root[0]), required=False)
    return args


def main():
    _cli.utf8_streams()
    if sys.argv[1:2] == ['stamp']:
        # Delegated whole, so its options may come before the file (a REMAINDER would leave them to this parser).
        import stamp
        return stamp.main(sys.argv[2:])  # prints its own JSON
    try:
        args = resolve_defaults(_cli.output_flags(build_parser()).parse_args())
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 2)
    code = 0
    try:
        if args.command == 'validate-plan':
            project = load(args.config).get('project') if args.config else None
            plan_ = validate_plan(load(args.plan), project)
            result = {'valid': True, 'semantic_review_required': True}
            resolved = board_resolution(plan_, project)
            if resolved is not None:
                result['resolved'] = resolved
        elif args.command == 'schedule':
            result = {'start': schedule(load(args.plan), args.limit)}
        elif args.command == 'authorize':
            operation = (json.loads(sys.stdin.buffer.read().decode('utf-8-sig')) if args.operation == '-'
                         else load(args.operation))
            result = authorize(load(args.charter), operation)
        elif args.command == 'context':
            result = {'action': context_action(args.used, args.reserve)}
            if args.pending:
                result['pending'] = pending_names(args.pending)
                if 'teste_assistido' in result['pending'] and result['action'] in ('handoff', 'stop'):
                    # The watched run must not be the last thing a window pays for: ask it before spending more.
                    result['ask_before_continuing'] = ['teste_assistido']
        elif args.command == 'inspect':
            result = inspect(load(args.config), args.root, args.config, args.summary)
        elif args.command == 'open':
            result = open_session(args.config, args.root, fetch=not args.no_fetch)
        elif args.command == 'evidence':
            result = git_evidence(args.root)
        elif args.command == 'review-gate':
            result = review_gate(load(args.review), git_evidence(args.root))
            code = 0 if result['status'] == 'current' else 2
        elif args.command == 'browser-gate':
            import browser_gate
            result, code = browser_gate.run_cli(args.root, args.base, args.config, args.toca, args.record, args.stacked)
        elif args.command == 'publish-order':
            result = {'order': publish_order(load(args.plan))}
        elif args.command == 'update-check':
            result = update_check()
        elif args.command == 'checkpoint':
            result = checkpoint_cli(args.issue, args.root, args.handoff, args.next_step, args.pending, args.slice)
        elif args.command == 'resume':
            result = resume_cli(args.issue, args.root, args.handoff, args.checkpoint, slice_id=args.slice)
        elif args.command == 'archive':
            result = archive_round(args.root, args.issue)
        elif args.command == 'homolog':
            import homolog
            code = homolog.main(args.homolog_args)  # prints its own JSON
            result = None
        else:
            result = {'discrepancies': drift(load(args.snapshot), load(args.current))}
        if result is not None:
            _cli.emit(json.dumps(result, indent=2, ensure_ascii=True), args.command, args.full)
        return code
    except _cli.UsageError as error:   # an issue the charter does not give, say: what to pass is in the hint
        return _cli.print_usage_error(error, 2)
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        where = {'path': exc.path} if isinstance(exc, PlanError) else {}   # the field of the plan, such as issues[1].title
        print(json.dumps({'error': str(exc), **where}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
