"""Frontlights: deterministic planning/evidence helpers, never a shell agent.

Only inspect performs network reads. No command here publishes issues, executes
tests, grants Claude permissions, or changes a product repository.

Exception (redesign, issue 7): `publish-issue` publishes the approved plan with gh, only after `stamp --check` of
the approved file, with the account and the repository checked before every write.
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


# The thresholds of a window (docs/protocol.md, "Contexto e conclusão", their only home in the text).
CONTEXT_HANDOFF, CONTEXT_STOP, CONTEXT_CUT = 100000, 150000, 200000
CONTEXT_EVERY = 50        # turns between two `context --used` reports
HOST_BASE_LIMIT = 80000   # first-turn context above which the host's connectors are named


def next_report(turn):
    """The turn of the next `context --used` report: the next multiple of `CONTEXT_EVERY`."""
    require(type(turn) is int and turn >= 0, 'turn is a whole number of turns')
    return (turn // CONTEXT_EVERY + 1) * CONTEXT_EVERY


def host_base(tokens, connectors, project=()):
    """The host-base warning of `update-check` and `open`: above 80k on the first turn, the connectors of the host
    that are not the project's (`connectors` of `.frontlights/config.json`). None when nothing was measured."""
    if tokens is None:
        return None
    require(type(tokens) is int and tokens >= 0, 'base is the context of the first turn, in tokens')
    own = {str(c).strip().lower() for c in project or () if str(c).strip()}
    names = []
    for name in connectors or ():
        name = str(name).strip()
        if name and name.lower() not in own and name not in names:
            names.append(name)
    over = tokens > HOST_BASE_LIMIT
    result = {'tokens': tokens, 'limit': HOST_BASE_LIMIT, 'over': over, 'notProject': names if over else []}
    if over:
        listed = ', '.join(names) if names else 'nenhum informado'
        result['message'] = (f'A base do host abre com {round(tokens / 1000)} mil tokens, acima de 80 mil, e pesa em '
                             f'todo turno. Conectores que não são deste projeto: {listed}. Desligá-los nesta sessão '
                             'baixa esse custo.')
    return result


def project_connectors(config_path):
    """`connectors` of the config (names of the host connectors the project uses); [] without config or key."""
    if not config_path:
        return []
    try:
        names = load(config_path).get('connectors')
    except (OSError, ValueError, AttributeError):
        return []
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def context_action(used, reserve):
    """`continue` below 100k; `handoff` (close at the next safe point), `stop` (no new step) and `cut` (the hard
    cut: end the window now) from 100k, 150k and 200k, the reserve included; unknown usage is `stop`."""
    if used is None:
        return 'stop'
    require(type(used) is int and used >= 0 and number(reserve), 'invalid context accounting')
    if used + reserve >= CONTEXT_CUT:
        return 'cut'
    if used + reserve >= CONTEXT_STOP:
        return 'stop'
    if used + reserve >= CONTEXT_HANDOFF:
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
            'root': str(root), 'issue': issue, 'git': git_evidence(root), 'handoff': str(handoff),
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
    state = 'reconcile' if changed or git_changed or handoff_changed else 'unchanged'
    return {'state': state, 'issue_drift': changed, 'git_drift': git_changed, 'handoff_changed': handoff_changed,
            'pending': pending_names(saved.get('pending')), 'next_step': saved['next_step'],
            'slice': saved.get('slice'),
            'required': 'Read current GitHub issue, handoff and diff before continuing.',
            'rule': RESUME_RULE}


RESUME_RULE = ('O GitHub vence o handoff: numa divergência, releia a issue, diga o que mudou e siga pelo que o GitHub '
               'diz; o handoff e o checkpoint são cópias de referência.')


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


def handoff_file(main, number):
    """The handoff of a window boundary: `<main worktree>/.frontlights/issues/<n>/handoff.md`, where the next window,
    opened at the project root, finds it."""
    return Path(main) / '.frontlights' / 'issues' / str(number) / 'handoff.md'


def checkpoint_cli(issue, tree, handoff, next_step, pending=(), slice_id=None, gh=None, main=None):
    """`checkpoint`: by issue number the snapshot is read and the checkpoint is also saved (`saved` names it);
    `--handoff` defaults to the handoff of the issue in the main worktree (`handoff_file`)."""
    main = main or str(_cli.main_worktree(tree))
    snapshot, number = issue_snapshot(issue, tree, main, gh)
    if handoff is None:
        require(number is not None, 'checkpoint com --issue <arquivo> precisa de --handoff <arquivo>')
        handoff = handoff_file(main, number)
        require(handoff.is_file(), f'sem handoff em {handoff.as_posix()}: escreva-o por templates/handoff.md '
                                   'antes do checkpoint, ou passe --handoff <arquivo>')
    record = checkpoint(tree, snapshot, handoff, next_step, pending, slice_id)
    if number is None:
        return record
    path = checkpoint_file(tree, number, slice_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)
    return {**record, 'saved': str(path)}


def checkpoint_candidates(tree, main, number, slice_id=None):
    """Where `resume --issue <n>` looks for the checkpoint: the worktree it runs in, the main worktree (the next
    window opens at the project root) and every worktree the charter gives to the issue."""
    folders = [Path(tree), Path(main)]
    charter = _cli.read_charter(main) or {}
    for entry in charter.get('worktrees') or []:
        if isinstance(entry, dict) and entry.get('issue') == number and isinstance(entry.get('path'), str):
            folders.append(Path(entry['path']))
    seen, found = set(), []
    for folder in folders:
        # By the issue alone (the next window only knows "retome a issue #n") a slice checkpoint counts too, and
        # `latest_checkpoint` picks the most recent; with --slice only that slice's file.
        paths = [checkpoint_file(folder, number, slice_id)]
        if slice_id is None:
            paths += sorted(checkpoint_file(folder, number).parent.glob('checkpoint-*.json'))
        for path in paths:
            key = os.path.normcase(str(path.resolve())) if path.is_file() else None
            if key and key not in seen:
                seen.add(key)
                found.append(path)
    return found


def latest_checkpoint(paths):
    """The most recent of the checkpoints found (by `created_at`); a file that does not parse is skipped."""
    best = None
    for path in paths:
        try:
            record = load(path)
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and (best is None or str(record.get('created_at')) > str(best[1].get('created_at'))):
            best = (path, record)
    return best


def window_hint(main, number):
    """The ANTES window crosses the boundary: with `browser/window.json` the next window runs `window attach`."""
    path = Path(main) / '.frontlights' / 'issues' / str(number) / 'browser' / 'window.json'
    if not path.is_file():
        return None
    return {'record': str(path), 'command': f'serve.py window attach --issue {number}',
            'message': 'A janela ANTES ficou aberta: rode `serve.py window attach` antes de usá-la; se ela morreu, '
                       'o attach reabre na mesma base e faixa, sem pergunta.'}


def resume_cli(issue, tree, handoff, saved, gh=None, main=None, slice_id=None):
    """`resume`: by issue number the snapshot is read, the checkpoint is found alone (`checkpoint_candidates`, the
    latest wins) and the handoff is the one the checkpoint recorded (else `handoff_file`). It prints the next step,
    the slice, the pending obligations and the drift; GitHub wins over the handoff (`rule`)."""
    main = main or str(_cli.main_worktree(tree))
    snapshot, number = issue_snapshot(issue, tree, main, gh)
    root = tree
    if saved is None:
        require(number is not None, 'resume com --issue <arquivo> precisa de --checkpoint <arquivo>')
        best = latest_checkpoint(checkpoint_candidates(tree, main, number, slice_id))
        expected = checkpoint_file(tree, number, slice_id).as_posix()
        require(best is not None, f'sem checkpoint da issue #{number} ({expected}, na worktree principal ou nas '
                                  'worktrees do charter): passe --checkpoint <arquivo>')
        saved, record = best
        root = record.get('root') or tree
        require(Path(root).is_dir(), f'a worktree do checkpoint não existe mais: {root}')
    else:
        record = load(saved)
    if handoff is None:
        recorded = record.get('handoff')
        if recorded and Path(recorded).is_file():
            handoff = Path(recorded)
        else:
            require(number is not None, 'sem handoff: passe --handoff <arquivo>')
            handoff = handoff_file(main, number)
            require(handoff.is_file(), f'sem handoff em {handoff.as_posix()}: passe --handoff <arquivo>')
    result = resume(root, record, snapshot, handoff)
    result.update({'checkpoint': str(saved), 'handoff': str(handoff), 'worktree': str(root)})
    if number is not None:
        window = window_hint(main, number)
        if window:
            result['window'] = window
    return result


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


def inspect(config, root, config_path=None, summary=False, offline=False, issue=None, gh=None):
    """`offline` reads no source over the network (`offline_sources`); `issue` adds its `family`
    (`issue_family`); `warnings` carries the block warnings and the setup gaps (`setup_warnings`)."""
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
    if offline:
        result['sources'] = offline_sources(config)
    elif repo is None:
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
    if offline:
        pass
    elif project is None:
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
    if offline:
        pass
    elif not roads:
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
    if issue is not None:
        result['family'] = issue_family(repo, issue, gh, offline)
    warnings = warnings + setup_warnings(config, root)
    if warnings:
        result['warnings'] = warnings
    return summarize(result) if summary else result


# What `inspect` refuses in a config (exit 1). One line per rule, in Portuguese: the `inspect --help` epilog prints
# these lines and `docs/security.md`, "Recusas do `inspect`", carries the same lines between its markers;
# `tests/test_inspect_blocks.py` compares the three (redesign, issue 10).
INSPECT_REFUSALS = (
    '`repository` ausente, ou que não é `dono/nome` nem `null`',
    '`browserTest.users` com login ou senha de menos de 4 caracteres ou com o texto do marcador de máscara',
    '`health` ou `baseUrl` de `browserTest` e `checks` fora de `127.0.0.1`, `localhost` ou `::1`',
    'shell embutido nos `argv` de `checks` (cmd, sh, powershell, `.bat`, `&&`, `|`, `python -c`, `env`, `xargs`)',
    '`{port}` sem um processo de porta `auto`',
    '`browserTest.isolated` que ainda declara `copyDatabase` ou `dropDatabase` (mesmo `null`)',
    '`browserTest.isolated` com host que não é local, porta fixa igual à da prévia ou do `serve`, `baseUrl` fixa '
    'que não é a porta de um processo isolado, ou `cwd` de processo que sai da worktree',
    '`preview` com worktree fora do `--root`, sem branch, `baseUrl` fora da porta fixa local de um processo dela, '
    'ou processo com porta `auto` ou `{port}` no argv ou no `cwd`',
    'porta fixa de `browserTest.processes` ou da `browserTest.baseUrl` igual a uma porta da prévia',
    '`homolog` com chave além de `backupDir` e `suites`, e `homolog.suites` com chave além de `impact` e `full`',
    '`homolog.backupDir` relativo, com `..`, `~` ou marcador `{}`',
)


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


# ---------------------------------------------------------------- setup (redesign, issue 11)
# `inspect` names what is missing in `warnings` (one code each; `references/setup.md` reads them), `--offline`
# reads nothing over the network, `--issue <n>` adds the family; `init-config` writes the first config.

SETUP = 'references/setup.md'
GITHUB_REMOTE = re.compile(r'^(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)'
                           r'([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$')
BRANCH_PREFIX = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,40}/')
REMOTE_HINT = 'passe --repository OWNER/REPOSITORY (ou --repository null para um projeto local)'


def in_work_tree(root):
    return _cli.git_line(root, 'rev-parse', '--is-inside-work-tree') == 'true'


def setup_warnings(config, root):
    """The setup gaps of a project, one `code: text` line each: `legacy_workflows_dir`, `browser_test_missing`
    (no key at all; `null` declares a project without a screen), `project_unresolved` (a repository and no `project`
    key; `null` declares no board) and, inside a Git work tree, `frontlights_not_ignored` and `branch_prefix_missing`
    (neither `branchPrefix` in the config nor `branch_prefix` in the charter). Reads files and local Git only."""
    warnings, base = [], Path(root)
    if (base / '.workflows').is_dir():
        warnings.append('legacy_workflows_dir: ' + (
            '.workflows/ convive com .frontlights/; use .frontlights/ e diga isso numa linha'
            if (base / '.frontlights').is_dir() else
            'o projeto tem .workflows/ e não .frontlights/: renomeie a pasta no lugar e diga isso numa linha'))
    if 'browserTest' not in config:
        warnings.append(f'browser_test_missing: o config não tem o bloco browserTest (null declara um projeto sem '
                        f'tela); {SETUP}')
    if config.get('repository') is not None and 'project' not in config:
        warnings.append(f'project_unresolved: o config não diz o quadro (um quadro, ou project: null sem quadro); '
                        f'pergunte antes de publicar qualquer issue; {SETUP}')
    if in_work_tree(root):
        if not git_ok(root, 'check-ignore', '-q', '.frontlights/'):
            warnings.append('frontlights_not_ignored: o Git não ignora .frontlights/; acrescente a linha '
                            '/.frontlights/ em .git/info/exclude')
        record = _cli.read_charter(root)
        if _cli.config_prefix(config) is None and not (isinstance(record, dict) and record.get('branch_prefix')):
            warnings.append(f'branch_prefix_missing: nem branchPrefix no config nem branch_prefix na autorização; o '
                            f'charter recusa sem prefixo; {SETUP}')
    return warnings


def offline_sources(config):
    """`--offline`: every source the config names is `offline` (nothing read); one it does not name stays
    `unconfigured`."""
    named = {'github': config.get('repository') is not None, 'project': bool(config.get('project')),
             'roads': bool(config.get('roads'))}
    return {name: {'status': 'offline' if on else 'unconfigured'} for name, on in named.items()}


def issue_family(repository, issue, gh=None, offline=False):
    """The family of an issue for `inspect --issue`: the issue and its sub-issues down to `closeout.MAX_DEPTH`
    levels (`closeout.expand`), with `open` (number, title, parent), `open_count`, `history` (the closed ones),
    `excluded` (a sub-issue of another repository) and `truncated` (a level or a list that did not fit)."""
    if offline:
        return {'status': 'offline', 'issue': issue}
    if repository is None:
        return {'status': 'unconfigured', 'issue': issue}
    import closeout  # noqa: PLC0415  (lazy: it imports this module)
    gh = gh or closeout.rs.gh_default
    try:
        numbers, truncated = closeout.expand(gh, repository, [issue])
        views = closeout.read_views(gh, repository, numbers)
    except (closeout.Refusal, ValueError, OSError, subprocess.TimeoutExpired):
        return {'status': 'unavailable', 'issue': issue,
                'reason': 'GitHub read failed; check gh authentication and repository access'}
    top = views.get(issue)
    if top is None:
        return {'status': 'unavailable', 'issue': issue, 'reason': f'GitHub does not know issue #{issue}'}
    opened, history, excluded = [], [], []
    for n in numbers:
        view = views.get(n)
        if view is None:
            continue
        excluded += [f"{c['external']}#{c['number']}" for c in view['children']['nodes'] if c['external']]
        truncated = truncated or bool(view['truncated'])
        if n == issue:
            continue
        if view['state'] == 'CLOSED':
            history.append(n)
        else:
            opened.append({'number': n, 'title': view['title'], 'parent': view['parent']})
    return {'status': 'available', 'issue': issue, 'title': top['title'], 'state': top['state'],
            'parent': top['parent'], 'open_count': len(opened), 'open': opened, 'history': history,
            'excluded': sorted(set(excluded)), 'truncated': truncated}


def remote_repository(root):
    """`owner/name` of the GitHub remote: `origin`, else the only remote; None without any remote. A remote that is
    not a GitHub URL, or several remotes and no `origin`, refuse (`ambiguous_remote`)."""
    names = (_cli.git_line(root, 'remote') or '').split()
    if not names:
        return None
    if 'origin' in names:
        name = 'origin'
    elif len(names) == 1:
        name = names[0]
    else:
        raise Stage6Refusal('ambiguous_remote', f'o projeto tem os remotos {", ".join(names)} e nenhum origin',
                            hint=REMOTE_HINT)
    found = GITHUB_REMOTE.match(_cli.git_line(root, 'remote', 'get-url', name) or '')
    if not found:
        raise Stage6Refusal('ambiguous_remote', f'o remoto {name} não é um repositório do GitHub', hint=REMOTE_HINT)
    return f'{found.group(1)}/{found.group(2)}'


def list_boards(repository, gh=None):
    """The project boards of the repository's owner, for the board question: [{number, title, url}], or None when
    gh cannot read them (the `project` scope, say)."""
    if repository is None:
        return []
    answer = (gh or _cli.gh_json)(['project', 'list', '--owner', repository.split('/')[0], '--format', 'json',
                                   '--limit', '50'])
    projects = answer.get('projects') if isinstance(answer, dict) else None
    if not isinstance(projects, list):
        return None
    return [{'number': p['number'], 'title': p.get('title'), 'url': p.get('url')}
            for p in projects if isinstance(p, dict) and number(p.get('number'))]


def init_config(root, repository=..., prefix=None, gh=None):
    """`init-config`: the first `.frontlights/config.json`, in the main worktree only, refused when one exists
    (`config_exists`). `repository` comes from the remote (`remote_repository`) unless given; the `project` key is
    never written (the board is a question: `references/issues.md`, "Project board"); `branchPrefix` only when
    `prefix` is given. Returns the boards of the owner for that question and the setup warnings left."""
    root = Path(root)
    if not in_work_tree(root):
        raise Stage6Refusal('not_a_repository', f'{root.name} não é um repositório Git',
                            hint='rode dentro do projeto de destino')
    main = _cli.main_worktree(root)
    if not _cli.same_path(root, main):
        raise Stage6Refusal('not_main_worktree', 'o config vive só na worktree principal',
                            hint=f'rode na worktree principal ({main.name}) ou passe --root com ela')
    path = root / _cli.CONFIG
    if path.exists():
        raise Stage6Refusal('config_exists', f'{_cli.CONFIG.as_posix()} já existe; nada foi gravado',
                            hint='frontlights.py inspect --summary relata o que falta nele')
    if repository is ...:
        repository = remote_repository(root)
    require(repository_or_local(repository), 'repository must be owner/name, or null for a local project')
    config = {'repository': repository}
    if prefix:
        require(BRANCH_PREFIX.fullmatch(prefix), 'branchPrefix must look like name/ (letters, digits, ., -, _)')
        config['branchPrefix'] = prefix
    write_json_file(path, config)
    boards = list_boards(repository, gh)
    result = {'ok': True, 'exitCode': 0, 'operation': 'init-config', 'written': True, 'config_path': str(path),
              'config': config, 'boards': boards, 'warnings': setup_warnings(config, root)}
    if repository is None:
        result['message'] = 'Config gravado para um projeto local (sem remoto): não há quadro a escolher.'
    elif boards is None:
        result['message'] = ('Config gravado; os quadros não puderam ser lidos (escopo "project" do gh). Pergunte o '
                             'quadro, ou project: null, antes de publicar qualquer issue.')
    else:
        result['message'] = (f'Config gravado com {repository}; pergunte o quadro entre os {len(boards)} listados '
                             f'(ou project: null) antes de publicar qualquer issue ({SETUP}).')
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


# ---------------------------------------------------------------- stage 6 by command (redesign, issue 4)
# `charter` writes the record `authorize` reads; `slice open` cuts the branches and worktrees of the slices of an
# issue; `slice merge` merges a slice into the branch of its issue. Local Git only: the remote writes (`gh issue
# develop`, the push of the branch of the issue) come back as argv in `commands`, for the session to run.

CHARTER_HOURS = 24
CHARTER_OPERATIONS = ['edit', 'test', 'checkpoint', 'merge_into_local_main']
APPROVAL_REFERENCE = 'autorização permanente (docs/security.md)'
STOP_CONDITIONS = ['decisão nova de produto', 'teste vermelho que a slice não explica',
                   'conflito de merge que a sessão não resolve', 'operação negada sem o "Sim" da pergunta própria',
                   'pedido do usuário']
CHARTER_FILE = Path('.frontlights') / 'authorization.json'
SLICE_LABEL = re.compile(r'[Ss]([1-9][0-9]{0,2})')
TEST_TIMEOUT = 1800


class Stage6Refusal(ValueError):
    """A refusal of `charter` or `slice` with the reason the session reads; nothing past the check was written."""

    def __init__(self, reason, message, hint=None, code=1, **extra):
        super().__init__(message)
        self.reason, self.hint, self.code, self.extra = reason, hint, code, extra

    def result(self):
        result = {'ok': False, 'exitCode': self.code, 'reason': self.reason, 'message': str(self)}
        if self.hint:
            result['hint'] = self.hint
        result.update(self.extra)
        return result


def git_call(cwd, *args, timeout=120):
    """(exit code, stdout, stderr) of `git -C cwd ...` without a shell and without prompts."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    try:
        done = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, stdin=subprocess.DEVNULL, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        raise Stage6Refusal('git_failed', f'o git não respondeu a `git {args[0]}`')
    return done.returncode, done.stdout, done.stderr


def git_rev(cwd, ref):
    code, out, _ = git_call(cwd, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
    return out.strip() if code == 0 and re.fullmatch(r'[0-9a-f]{40,64}', out.strip()) else None


def write_json_file(path, data):
    """Write under a temporary name and rename into place, so a reader never sees half a record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def sao_paulo_text(moment):
    return moment.astimezone(_cli.sao_paulo_now().tzinfo).strftime('%d/%m/%Y %H:%M')


def parse_ownership(values, ids):
    """{id: [paths]} from `--ownership` values: `path` (every id of this command) or `<id>=path[,path]`. Every id
    needs at least one path, and never `*` alone (authorize ignores `*`: it owns nothing)."""
    owned = {key: [] for key in ids}
    for value in values or ():
        key, separator, paths = str(value).partition('=')
        targets = [key.strip().lstrip('#')] if separator else list(ids)
        if separator and targets[0] not in owned:
            raise Stage6Refusal('ownership_unknown_id', f'--ownership {value!r} nomeia {key!r}, que não está entre as '
                                f'issues ou trabalhos deste comando ({", ".join(ids)})',
                                hint='use <issue>=<caminho> com uma issue de --issue (ou um slug de --direct)')
        for path in (paths if separator else value).split(','):
            path = path.strip().replace('\\', '/').rstrip('/')
            if not path:
                continue
            try:
                relative(path)
            except ValueError as error:
                raise Stage6Refusal('ownership_invalid', f'--ownership {path!r}: {error}',
                                    hint='caminhos relativos à raiz do projeto, sem glob, como src/feature') from None
            for target in targets:
                if path not in owned[target]:
                    owned[target].append(path)
    missing = [key for key, paths in owned.items() if not paths or all(p == '*' for p in paths)]
    if missing:
        raise Stage6Refusal('ownership_required', 'a posse (ownership) é obrigatória e nunca só `*`: falta para '
                            + ', '.join(f'#{m}' if m.isdigit() else m for m in missing),
                            hint='passe --ownership <caminho> (ou <issue>=<caminho> num lote), as pastas e arquivos '
                                 'que a issue edita, da seção "## Propriedade" do corpo')
    return owned


def charter_ids(issues, directs):
    ids = []
    for value in issues or ():
        text = str(value).strip().lstrip('#')
        if not text.isdigit() or int(text) < 1:
            raise Stage6Refusal('issue_invalid', f'--issue precisa ser um número de issue, não {str(value)[:40]!r}',
                                hint='passe --issue <n>, como --issue 12')
        ids.append(str(int(text)))
    for value in directs or ():
        if not DIRECT_RULE.fullmatch(str(value)):
            raise Stage6Refusal('direct_invalid', f'--direct {str(value)[:70]!r} não é um slug (minúsculas, dígitos e '
                                'hífens, até 64)', hint='como --direct melhoria-x')
        ids.append(str(value))
    return ids


def homolog_module():
    import homolog  # noqa: PLC0415  (homolog imports closeout, which imports this module)
    return homolog


def charter_base(root, base, has_issues, has_directs):
    """The base of the charter: `branch` is the local main (the target of `merge_into_local_main`); an issue starts
    from `origin/<base>`, work without an issue from the local main."""
    if not homolog_module().is_plain(base):
        raise Stage6Refusal('base_invalid', f'--base {str(base)[:40]!r} não é um nome de branch simples',
                            hint='como --base main')
    result = {'branch': base}
    if has_issues:
        commit = git_rev(root, f'refs/remotes/origin/{base}')
        result['issues'] = {'from': f'origin/{base}' if commit else base,
                            'commit': commit or git_rev(root, f'refs/heads/{base}')}
    if has_directs:
        result['direct'] = {'from': base, 'commit': git_rev(root, f'refs/heads/{base}')}
    return result


def approver(root, given):
    if nonempty(given):
        return given.strip()
    code, out, _ = git_call(root, 'config', 'user.name')
    if code == 0 and out.strip():
        return out.strip()
    raise Stage6Refusal('approved_by_required', 'sem --approved-by e sem `git config user.name`: o charter registra '
                        'o usuário em approved_by e confirmed_by', hint='passe --approved-by <nome do usuário>')


def dry_run(record, root, ids):
    """`authorize` on an `edit` of the first owned path of each id, from a phantom entry on the main worktree: the
    charter must pass before it is written."""
    answers = []
    for key in ids:
        name = 'direct' if not key.isdigit() else 'issue'
        value = int(key) if name == 'issue' else key
        branch = f'{record["branch_prefix"]}issue-{key}' if name == 'issue' else f'{record["branch_prefix"]}{key}'
        owned = [p for p in record['ownership'][key] if p != '*']
        phantom = dict(record, worktrees=[{name: value, 'path': str(root), 'branch': branch, 'ownership': owned}])
        operation = {'repository': record['repository'], name: value, 'kind': 'edit', 'worktree': str(root),
                     'branch': branch, 'path': owned[0]}
        try:
            answer = authorize(phantom, operation)
        except (ValueError, OSError) as error:
            raise Stage6Refusal('authorize_refused', f'o charter não passaria no authorize ({name} {key}): {error}; '
                                'nada foi gravado', hint='corrija --prefix, --protect ou --ownership e repita') from None
        answers.append({name: value, 'scope_check': answer['scope_check'], 'path': owned[0]})
    return answers


def keep_previous(root):
    """Copy the current charter to `authorization-<YYYY-MM-DD>-issue-<n>.json` (never overwritten: `-2`, `-3`), the
    records release-plan, bundle, closeout and cleanup still read. None when there is no charter."""
    current = Path(root) / CHARTER_FILE
    if not current.is_file():
        return None
    data = current.read_bytes()
    try:
        old = json.loads(data.decode('utf-8-sig'))
    except ValueError:
        old = {}
    old = old if isinstance(old, dict) else {}
    issued = old.get('issued_at')
    try:
        day = dt.datetime.fromisoformat(issued).strftime('%Y-%m-%d') if isinstance(issued, str) else None
    except ValueError:
        day = None
    day = day or _cli.sao_paulo_now().strftime('%Y-%m-%d')
    ids = old.get('issue_ids') if isinstance(old.get('issue_ids'), list) else []
    directs = old.get('direct_ids') if isinstance(old.get('direct_ids'), list) else []
    tag = f'issue-{ids[0]}' if ids else f'direct-{directs[0]}' if directs else 'sem-issue'
    for attempt in range(1, 100):
        path = current.with_name(f'authorization-{day}-{tag}' + ('' if attempt == 1 else f'-{attempt}') + '.json')
        if path.is_file() and path.read_bytes() == data:
            return path
        try:
            with open(path, 'xb') as handle:
                handle.write(data)
            return path
        except FileExistsError:
            continue
    raise Stage6Refusal('keep_failed', 'sem nome livre para guardar o charter anterior; nada foi gravado')


def announcement(record, prefix_source):
    ids = [f'#{n}' for n in record.get('issue_ids', [])] + list(record.get('direct_ids', []))
    base = record['base']
    start = base.get('issues') or base.get('direct') or {}
    commit = (start.get('commit') or '')[:7]
    owned = '; '.join(f'{"#" + k if k.isdigit() else k} → {", ".join(v)}' for k, v in record['ownership'].items())
    verify = ', '.join('`' + ' '.join(argv) + '`' for argv in record.get('verification_commands', [])) or 'nenhum'
    expires = sao_paulo_text(dt.datetime.fromisoformat(record['expires_at']))
    return (f'Etapa 6 sob a autorização permanente, sem pergunta de abertura: {", ".join(ids)} em '
            f'{record["repository"] or "projeto sem remoto"}; concorrência {record["concurrency"]}; base '
            f'{start.get("from", base["branch"])}{" (" + commit + ")" if commit else ""}, main local '
            f'{base["branch"]}; prefixo {record["branch_prefix"]} ({prefix_source}); posse: {owned}; verificação: '
            f'{verify}; para em: {"; ".join(record["stop_conditions"])}. Vale até {expires} (São Paulo). As slices, a '
            'ordem e as worktrees vêm com `slice open`; as operações negadas seguem com pergunta própria.')


def load_config_file(path):
    if not path or not Path(path).is_file():
        raise Stage6Refusal('no_config', 'sem .frontlights/config.json do projeto', hint='passe --config <caminho>')
    data = load(path)
    if not isinstance(data, dict):
        raise Stage6Refusal('no_config', 'o config não é um objeto JSON', hint='confira o .frontlights/config.json')
    return data


def verification_argv(values):
    argvs = []
    for value in values or ():
        try:
            argv = json.loads(value) if isinstance(value, str) else value
        except ValueError:
            argv = None
        if not strings(argv):
            raise Stage6Refusal('verify_invalid', f'{str(value)[:80]!r} não é uma lista JSON de textos',
                                hint='como \'["python", "-m", "unittest"]\'')
        argvs.append(argv)
    return argvs


def charter_cli(action, root, config_path, issues=(), directs=(), ownership=(), prefix=None, concurrency=None,
                protect=(), base=None, approved_by=None, verify=(), hours=CHARTER_HOURS):
    """`charter new|renew|add`; the result dict, `ok: false` with `reason` on a refusal (nothing written)."""
    try:
        return charter_action(action, Path(root), config_path, issues, directs, ownership, prefix, concurrency,
                              protect, base, approved_by, verify, hours)
    except Stage6Refusal as refusal:
        return refusal.result()


def charter_action(action, root, config_path, issues, directs, ownership, prefix, concurrency, protect, base,
                   approved_by, verify, hours):
    if type(hours) is not int or not 1 <= hours <= CHARTER_HOURS:
        raise Stage6Refusal('hours', f'--hours {hours!r}: o charter vale no máximo {CHARTER_HOURS} horas',
                            hint=f'passe --hours entre 1 e {CHARTER_HOURS}')
    config = load_config_file(config_path)
    path = root / CHARTER_FILE
    now = _cli.sao_paulo_now().replace(microsecond=0)
    expires = (now + dt.timedelta(hours=hours)).isoformat()
    existing = None
    if action in ('renew', 'add'):
        if not path.is_file():
            raise Stage6Refusal('no_charter', f'não há charter em {CHARTER_FILE.as_posix()} para {action}',
                                hint='rode `charter new --issue <n> --ownership <caminhos>` primeiro')
        existing = load(path)
        if not isinstance(existing, dict):
            raise Stage6Refusal('no_charter', 'o charter atual não é um objeto JSON', hint='rode `charter new`')
    if action == 'renew':
        record = dict(existing, expires_at=expires, renewed_at=now.isoformat())
        ids = [str(n) for n in record.get('issue_ids', [])] + list(record.get('direct_ids', []))
        checked = dry_run(record, root, [k for k in ids if record.get('ownership', {}).get(k)])
        write_json_file(path, record)
        return {'ok': True, 'exitCode': 0, 'action': 'renew', 'charter': str(path), 'expires_at': expires,
                'dryRun': checked,
                'message': f'Charter renovado: vale até {sao_paulo_text(dt.datetime.fromisoformat(expires))} '
                           '(São Paulo).'}
    ids = charter_ids(issues, directs)
    if not ids:
        raise Stage6Refusal('no_issue', 'o charter precisa de ao menos uma issue ou um trabalho sem issue',
                            hint='passe --issue <n> (repetível) ou --direct <slug>')
    owned = parse_ownership(ownership, ids)
    if action == 'add':
        present = {str(n) for n in existing.get('issue_ids', [])} | set(existing.get('direct_ids', []))
        repeated = [k for k in ids if k in present]
        if repeated:
            raise Stage6Refusal('already_in_charter', f'já está no charter: {", ".join(repeated)}',
                                hint='use `charter renew` para estender o prazo; a posse muda com `charter new`')
        record = dict(existing)
        record['issue_ids'] = list(existing.get('issue_ids', [])) + [int(k) for k in ids if k.isdigit()]
        new_directs = [k for k in ids if not k.isdigit()]
        record['direct_ids'] = list(existing.get('direct_ids', [])) + new_directs
        record['ownership'] = dict(existing.get('ownership', {}), **owned)
        branch = record.get('base', {}).get('branch', 'main')
        extra = charter_base(root, branch, any(k.isdigit() for k in ids), bool(new_directs))
        record['base'] = dict(extra, **record.get('base', {}))
        checked = dry_run(record, root, ids)
        write_json_file(path, record)
        return {'ok': True, 'exitCode': 0, 'action': 'add', 'charter': str(path), 'added': ids, 'dryRun': checked,
                'announcement': announcement(record, 'authorization')}
    chosen, source = _cli.branch_prefix(prefix, config, None)
    if not chosen:
        raise Stage6Refusal('no_prefix', 'sem prefixo das branches: nem --prefix, nem branchPrefix no config',
                            hint='declare "branchPrefix" no .frontlights/config.json do projeto ou passe --prefix '
                                 '<nome>/')
    if concurrency is not None and (type(concurrency) is not int or concurrency < 1):
        raise Stage6Refusal('concurrency', '--concurrency precisa ser um inteiro positivo', hint='como --concurrency 2')
    who = approver(root, approved_by)
    record = {
        'repository': config.get('repository'),
        'issue_ids': [int(k) for k in ids if k.isdigit()],
        'direct_ids': [k for k in ids if not k.isdigit()],
        'operations': list(CHARTER_OPERATIONS),
        'protected_branches': [str(p) for p in protect or ()],
        'stop_conditions': list(STOP_CONDITIONS),
        'base': charter_base(root, base or 'main', any(k.isdigit() for k in ids), any(not k.isdigit() for k in ids)),
        'issued_at': now.isoformat(),
        'expires_at': expires,
        'approved_by': who,
        'confirmed_by': who,
        'approval_reference': APPROVAL_REFERENCE,
        'monitoring': {'mode': 'local', 'confirmed_by': who, 'at': now.isoformat()},
        'concurrency': concurrency or 2,
        'branch_prefix': chosen,
        'ownership': owned,
        'verification_commands': verification_argv(verify),
        'worktrees': [],
    }
    if not repository_or_local(record['repository']):
        raise Stage6Refusal('repository', 'o repository do config não é owner/name nem null',
                            hint='confira "repository" no .frontlights/config.json')
    checked = dry_run(record, root, ids)
    kept = keep_previous(root)
    write_json_file(path, record)
    return {'ok': True, 'exitCode': 0, 'action': 'new', 'charter': str(path), 'kept': str(kept) if kept else None,
            'prefix': chosen, 'prefixSource': source, 'dryRun': checked, 'announcement': announcement(record, source)}

def read_charter_record(root):
    path = Path(root) / CHARTER_FILE
    if not path.is_file():
        raise Stage6Refusal('no_charter', f'não há charter em {CHARTER_FILE.as_posix()}',
                            hint='rode `charter new --issue <n> --ownership <caminhos>` primeiro')
    record = load(path)
    if not isinstance(record, dict):
        raise Stage6Refusal('no_charter', 'o charter não é um objeto JSON', hint='rode `charter new`')
    return path, record


def charter_issue(record, issue):
    text = str(issue).strip().lstrip('#') if issue is not None else ''
    if not text.isdigit() or int(text) < 1:
        raise Stage6Refusal('issue_invalid', '--issue precisa ser um número de issue', hint='passe --issue <n>')
    number = int(text)
    if number not in record.get('issue_ids', []):
        listed = ', '.join(f'#{n}' for n in record.get('issue_ids', [])) or 'nenhuma'
        raise Stage6Refusal('unapproved_issue', f'a issue #{number} não está no charter (issues: {listed})',
                            hint='acrescente-a com `charter add --issue <n> --ownership <caminhos>`')
    return number


def slice_label(value):
    match = SLICE_LABEL.fullmatch(str(value).strip())
    if not match:
        raise Stage6Refusal('slice_invalid', f'{str(value)[:20]!r} não é uma slice', hint='como --slice S2')
    return f'S{int(match.group(1))}'


def record_prefix(record):
    prefix = _cli.branch_prefix(record=record)[0]
    if not nonempty(prefix) or not prefix.endswith('/'):
        raise Stage6Refusal('no_prefix', 'o charter não tem branch_prefix válido', hint='rode `charter new`')
    return prefix


def entry_of(record, issue, label=None):
    """The `worktrees` entry of the issue's own branch (label None) or of its slice `label`."""
    prefix = record_prefix(record)
    for entry in record.get('worktrees', []):
        if not isinstance(entry, dict) or entry.get('issue') != issue:
            continue
        if label is None and entry.get('slice') is None and entry.get('branch') == f'{prefix}issue-{issue}':
            return entry
        if label is not None and entry.get('slice') == label:
            return entry
    return None


def changed_files(tree):
    """Tracked changes and untracked files (ignored ones never count) of a worktree."""
    code, out, _ = git_call(tree, 'status', '--porcelain', '--untracked-files=normal')
    if code != 0:
        raise Stage6Refusal('git_failed', f'o git não leu o estado de {Path(tree).name}')
    return [line[3:] for line in out.splitlines() if line.strip()]


def has_remote(root, name='origin'):
    return git_call(root, 'remote', 'get-url', name)[0] == 0


def worktree_folder(root, given):
    return Path(given) if given else Path(root).parent / f'{Path(root).name}-worktrees'


def add_worktree(root, path, branch, start=None):
    if Path(path).exists():
        raise Stage6Refusal('path_exists', f'a pasta {path} já existe; a worktree não é criada por cima',
                            hint='passe --dir <outra pasta> ou remova a pasta')
    args = ['worktree', 'add', str(path), branch] if start is None else ['worktree', 'add', '-b', branch, str(path), start]
    code, _, err = git_call(root, *args)
    if code != 0:
        raise Stage6Refusal('worktree_failed', f'`git worktree add` falhou: {" ".join(err.split())[:200]}')


def slice_ownership(values, labels, default):
    owned = {label: [] for label in labels}
    for value in values or ():
        key, separator, paths = str(value).partition('=')
        targets = [slice_label(key)] if separator else list(labels)
        for path in (paths if separator else value).split(','):
            path = path.strip().replace('\\', '/').rstrip('/')
            if not path:
                continue
            try:
                relative(path)
            except ValueError as error:
                raise Stage6Refusal('ownership_invalid', f'--ownership {path!r}: {error}') from None
            for target in targets:
                if target not in owned:
                    raise Stage6Refusal('ownership_unknown_id', f'--ownership {value!r} nomeia uma slice que não '
                                        'está em --slice', hint='use S<k>=<caminho> com uma slice de --slice')
                owned[target].append(path)
    for label in labels:
        owned[label] = owned[label] or list(default)
        if not [p for p in owned[label] if p != '*']:
            raise Stage6Refusal('ownership_required', f'a slice {label} não tem posse (ownership)',
                                hint='passe --ownership S<k>=<caminho> ou grave a posse da issue no charter')
    return owned


def slice_open(root, config_path, issue, slices, stacked_on=None, ownership=(), directory=None):
    root = Path(root)
    path, record = read_charter_record(root)
    number = charter_issue(record, issue)
    prefix = record_prefix(record)
    labels = [slice_label(value) for value in slices or ()]
    if not labels:
        raise Stage6Refusal('slice_required', 'slice open precisa de ao menos uma slice', hint='--slice S1 [S2 ...]')
    base = (record.get('base') or {}).get('branch') or 'main'
    issue_branch = f'{prefix}issue-{number}'
    folder = worktree_folder(root, directory)
    commands, warnings, created = [], [], []
    origin = has_remote(root)
    if origin:
        code, _, err = git_call(root, 'fetch', '--quiet', 'origin', timeout=180)
        if code != 0:
            warnings.append(f'git fetch origin falhou ({" ".join(err.split())[:120]}); seguiu com as refs locais')
    if git_rev(root, f'refs/heads/{issue_branch}') is None:
        remote_ref = f'refs/remotes/origin/{issue_branch}'
        if git_rev(root, remote_ref):
            code, _, err = git_call(root, 'branch', '--track', issue_branch, f'origin/{issue_branch}')
        else:
            start = f'origin/{base}' if git_rev(root, f'refs/remotes/origin/{base}') else base
            code, _, err = git_call(root, 'branch', issue_branch, start)
            if record.get('repository') and origin:
                commands.append(['gh', 'issue', 'develop', str(number), '--repo', record['repository'], '--base',
                                 base, '--name', issue_branch])
        if code != 0:
            raise Stage6Refusal('branch_failed', f'a branch {issue_branch} não foi criada: {" ".join(err.split())[:200]}')
    own = entry_of(record, number)
    issue_owned = (record.get('ownership') or {}).get(str(number)) or []
    if own is None:
        target = folder / f'issue-{number}'
        add_worktree(root, target, issue_branch)
        own = {'issue': number, 'path': str(target), 'branch': issue_branch, 'ownership': list(issue_owned)}
        record.setdefault('worktrees', []).append(own)
        created.append({'branch': issue_branch, 'path': str(target)})
    owned = slice_ownership(ownership, labels, issue_owned)
    start_branch, stacked_branch = issue_branch, None
    if stacked_on:
        under = entry_of(record, number, slice_label(stacked_on))
        if under is None:
            raise Stage6Refusal('stacked_unknown', f'a slice {slice_label(stacked_on)} não tem worktree no charter',
                                hint='abra-a antes com `slice open`')
        start_branch = stacked_branch = under['branch']
    opened = []
    for label in labels:
        existing = entry_of(record, number, label)
        if existing is not None:
            opened.append(dict(existing, already=True))
            continue
        branch = f'{issue_branch}-s{label[1:]}'
        target = folder / f'issue-{number}-s{label[1:]}'
        add_worktree(root, target, branch, start_branch)
        entry = {'issue': number, 'slice': label, 'path': str(target), 'branch': branch, 'ownership': owned[label]}
        if stacked_branch:
            entry['base'] = stacked_branch
        record['worktrees'].append(entry)
        opened.append(entry)
    open_slices = [e for e in record['worktrees'] if isinstance(e, dict) and e.get('issue') == number and e.get('slice')]
    for index, first in enumerate(open_slices):
        for second in open_slices[index + 1:]:
            if any(overlap(a, b) for a in first['ownership'] for b in second['ownership'] if '*' not in (a, b)):
                warnings.append(f'{first["slice"]} e {second["slice"]} têm posse em comum: duas slices nunca editam '
                                'o mesmo arquivo; empilhe a segunda (--stacked-on) ou separe a posse')
    write_json_file(path, record)
    return {'ok': True, 'exitCode': 0, 'issue': number, 'issueBranch': issue_branch, 'issueWorktree': own['path'],
            'created': created, 'slices': opened, 'commands': commands, 'warnings': warnings,
            'message': (f'Slices {", ".join(labels)} da issue #{number} abertas, cada uma na sua worktree e no charter. '
                        + ('Rode já o `gh issue develop` de `commands` (cria a branch da issue no GitHub a partir da '
                           f'origin/{base} e a liga à issue), antes do primeiro push. ' if commands else '')
                        + f'Ao fechar o ciclo de uma slice: `slice merge --issue {number} --slice S<k>`.')}


def run_tests(argvs, cwd, log_path):
    """Run each argv in `cwd` without a shell; ([{argv, exitCode}], first failure or None). The output goes to
    `log_path`, in the records, never to the screen."""
    ran, failure = [], None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'w', encoding='utf-8', errors='replace') as log:
        for argv in argvs:
            log.write(f'$ {" ".join(argv)}\n')
            log.flush()
            try:
                done = subprocess.run(argv, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, timeout=TEST_TIMEOUT)
                code = done.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                log.write(f'[não rodou: {type(error).__name__}]\n')
                code = None
            ran.append({'argv': argv, 'exitCode': code})
            if code != 0:
                failure = ran[-1]
                break
    return ran, failure


def tail(path, lines=20):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').splitlines()[-lines:]
    except OSError:
        return []


def suite_from(source, tree):
    """The green record of `homolog suite` run on the same commit tree as `tree`'s HEAD, or a refusal."""
    data = load(source)
    if not isinstance(data, dict):
        raise Stage6Refusal('suite_invalid', f'{source} não é um registro de suíte')
    if data.get('exitCode') != 0 or data.get('timedOut'):
        raise Stage6Refusal('red', f'a suíte de {Path(source).name} não está verde (exitCode {data.get("exitCode")})',
                            hint='rode os testes de novo e corrija o vermelho antes do merge')
    head = data.get('head')
    homolog = homolog_module()
    mine, theirs = homolog.tree_of(tree, 'HEAD'), homolog.tree_of(tree, head) if isinstance(head, str) else None
    if mine is None or mine != theirs:
        raise Stage6Refusal('suite_other_tree', f'a suíte de {Path(source).name} rodou noutra árvore (head '
                            f'{str(head)[:12]}), não na ponta da slice', hint='rode a suíte na ponta da slice ou '
                            'passe --test com os testes dos seams')
    return {'from': str(source), 'head': head, 'exitCode': 0}


def local_main_only(root, issue_branch, base):
    """The commits the push of the branch of the issue would send that are only in the local main (never pushed
    before the release): in `<issue> ^origin/<base> ^origin/<issue>` and in `<base> ^origin/<base>`."""
    excluded = [f'^refs/remotes/origin/{base}']
    if git_rev(root, f'refs/remotes/origin/{issue_branch}'):
        excluded.append(f'^refs/remotes/origin/{issue_branch}')
    code, pushed, _ = git_call(root, 'rev-list', f'refs/heads/{issue_branch}', *excluded)
    code2, local, _ = git_call(root, 'rev-list', f'refs/heads/{base}', f'^refs/remotes/origin/{base}')
    if code != 0 or code2 != 0:
        return []
    only = set(local.split())
    return [sha for sha in pushed.split() if sha in only]


def preview_branches(root, base):
    """The list of `serve preview refresh` (references/development.md, "The start of stage 6"): the branch of every
    issue (and work without an issue) of the authorization records, plus the `merged` of the preview's record,
    minus each one the local main already holds or `origin/<base>` already carries, and only those that exist
    locally. It never names only the issue at hand: every issue in progress stays in the preview."""
    homolog = homolog_module()
    entries, _ = homolog.work_entries(root)
    names = [e['branch'] for e in homolog.issue_entries(entries).values()]
    names += [e['branch'] for e in entries if 'direct' in e]
    registry = Path(root) / '.frontlights' / 'preview' / 'registry.json'
    data = homolog.read_record(registry) if registry.is_file() else None
    for item in (data or {}).get('merged', []) if isinstance(data, dict) else []:
        name = item.get('branch') if isinstance(item, dict) else item
        if isinstance(name, str):
            names.append(name)
    chosen = []
    remote_base = git_rev(root, f'refs/remotes/origin/{base}')
    for name in names:
        tip = git_rev(root, f'refs/heads/{name}') if homolog.is_plain(name) else None
        if tip is None or name in chosen:
            continue
        if git_call(root, 'merge-base', '--is-ancestor', tip, f'refs/heads/{base}')[0] == 0:
            continue
        if remote_base and git_call(root, 'merge-base', '--is-ancestor', tip, remote_base)[0] == 0:
            continue
        chosen.append(name)
    return chosen


def refresh_preview(root, config_path, base):
    config = load(config_path) if config_path and Path(config_path).is_file() else {}
    if not isinstance(config, dict) or not isinstance(config.get('preview'), dict):
        return {'skipped': 'sem bloco preview no config: nada de prévia'}
    branches = preview_branches(root, base)
    argv = [sys.executable, str(HERE / 'serve.py'), 'preview', 'refresh', '--config', str(config_path), '--root',
            str(root), '--base', base, '--full']
    for name in branches:
        argv += ['--branch', name]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900,
                              stdin=subprocess.DEVNULL)
        answer = json.loads(done.stdout) if done.stdout.strip() else {}
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return {'branches': branches, 'ok': False, 'error': f'serve preview refresh não respondeu ({type(error).__name__})'}
    return {'branches': branches, 'ok': done.returncode == 0,
            'message': answer.get('message') or answer.get('error') if isinstance(answer, dict) else None}


def slice_merge(root, config_path, issue, label, source=None, tests=(), watched_only=False, comment_file=None):
    root = Path(root)
    _, record = read_charter_record(root)
    number = charter_issue(record, issue)
    label = slice_label(label)
    own, piece = entry_of(record, number), entry_of(record, number, label)
    if own is None or piece is None:
        raise Stage6Refusal('no_worktree', f'o charter não tem a worktree {"da issue" if own is None else label} da '
                            f'issue #{number}', hint=f'rode `slice open --issue {number} --slice {label}`')
    for entry in (piece, own):
        if not Path(entry['path']).is_dir():
            raise Stage6Refusal('no_worktree', f'a worktree {entry["path"]} não existe')
        dirty = changed_files(entry['path'])
        if dirty:
            raise Stage6Refusal('dirty', f'a worktree {Path(entry["path"]).name} tem {len(dirty)} arquivo(s) sem '
                                f'commit: {", ".join(dirty[:10])}', hint='commite (ou descarte) na worktree e repita',
                                files=dirty[:50])
    base = (record.get('base') or {}).get('branch') or 'main'
    issue_branch, branch = own['branch'], piece['branch']
    tip = git_rev(root, f'refs/heads/{branch}')
    if tip is None:
        raise Stage6Refusal('no_branch', f'a branch {branch} não existe')
    already = git_call(root, 'merge-base', '--is-ancestor', tip, f'refs/heads/{issue_branch}')[0] == 0
    result = {'issue': number, 'slice': label, 'branch': branch, 'issueBranch': issue_branch, 'alreadyMerged': already,
              'tests': None}
    if not already:
        stamp = _cli.sao_paulo_now().strftime('%Y%m%d-%H%M%S')
        log = root / '.frontlights' / 'issues' / str(number) / f'slice-merge-{label}-{stamp}.log'
        if source:
            result['tests'] = suite_from(source, piece['path'])
        elif watched_only:
            result['tests'] = {'skipped': 'só com teste assistido: nenhum teste escrito nem rodado'}
        else:
            argvs = verification_argv(tests) or record.get('verification_commands') or []
            if not argvs:
                raise Stage6Refusal('no_tests', 'sem testes para rerrodar: o coordenador rerroda os testes da slice '
                                    'antes do merge', hint="passe --test '<argv JSON>' (os testes dos seams), --from "
                                    '<registro da suíte na mesma árvore> ou --watched-only numa execução só com teste '
                                    'assistido')
            ran, failure = run_tests(argvs, piece['path'], log)
            result['tests'] = {'ran': ran, 'log': str(log)}
            if failure:
                raise Stage6Refusal('red', f'teste vermelho na slice {label}: `{" ".join(failure["argv"])}` saiu '
                                    f'{failure["exitCode"]}; nada foi mesclado', hint='corrija na worktree da slice e '
                                    'repita', tests=result['tests'], tail=tail(log))
        message = f'Merge da slice {label} na issue #{number}'
        code, _, err = git_call(own['path'], 'merge', '--no-ff', '--no-edit', '-m', message, branch)
        if code != 0:
            _, unmerged, _ = git_call(own['path'], 'diff', '--name-only', '--diff-filter=U')
            files = sorted(line for line in unmerged.splitlines() if line.strip())
            git_call(own['path'], 'merge', '--abort')
            if not files:
                raise Stage6Refusal('merge_failed', f'`git merge {branch}` falhou: {" ".join(err.split())[:200]}')
            raise Stage6Refusal('conflict', f'o merge da slice {label} na branch da issue tem conflito em: '
                                f'{", ".join(files)}; o merge foi abortado e a worktree da issue está limpa',
                                hint='resolva na worktree da issue (o merge abaixo, os arquivos, o commit) e rode '
                                     '`slice merge` de novo, que segue do merge já feito', code=2, files=files,
                                commands=[['git', '-C', own['path'], 'merge', '--no-ff', branch]])
        result['merge'] = git_rev(root, f'refs/heads/{issue_branch}')
    result['commands'] = []
    if record.get('repository') and has_remote(root):
        leaked = local_main_only(root, issue_branch, base)
        if leaked:
            raise Stage6Refusal('local_main_commit', f'o push da {issue_branch} levaria {len(leaked)} commit(s) que '
                                f'só estão na main local ({", ".join(c[:7] for c in leaked[:5])}): a main local nunca '
                                'entra numa branch enviada; nada foi enviado', code=3, commits=leaked[:50],
                                hint='tire esses commits da branch da issue (a main local entra só na worktree '
                                     '-integra) e repita')
        result['commands'].append(['git', '-C', own['path'], 'push', 'origin', issue_branch])
    else:
        result['note'] = 'projeto sem remoto: a branch da issue fica local e nada é enviado'
    result['preview'] = refresh_preview(root, config_path, base)
    tick = ['python', str(HERE / 'closeout.py'), 'tick', '--issue', str(number), '--box', label]
    if comment_file:
        tick += ['--comment-file', str(comment_file)]
    result['next'] = {'tick': tick, 'when': 'só depois do "Aprovado" do teste assistido (caixa com tela) ou com '
                                            f'walkthroughs/{label}.md gravado (caixa sem tela)'}
    pushed = ' Rode o push de `commands` (coberto).' if result['commands'] else ''
    result.update(ok=True, exitCode=0,
                  message=f'A slice {label} {"já estava" if already else "foi"} mesclada na branch da issue #{number}.'
                          f'{pushed} A marcação da caixa vem depois, com a evidência ({result["next"]["when"]}).')
    return result


def slice_cli(action, root, config_path, issue, slices=(), stacked_on=None, ownership=(), directory=None, source=None,
              tests=(), watched_only=False, comment_file=None):
    try:
        if action == 'open':
            return slice_open(root, config_path, issue, slices, stacked_on, ownership, directory)
        if len(slices or ()) != 1:
            raise Stage6Refusal('slice_required', 'slice merge mescla uma slice por vez', hint='--slice S2')
        return slice_merge(root, config_path, issue, slices[0], source, tests, watched_only, comment_file)
    except Stage6Refusal as refusal:
        return refusal.result()


# ---------------------------------------------------------------- stage 5 by command (redesign, issue 7)
# `publish-issue` publishes the approved plan: the stamp of the approved file checked first, the issues created
# blockers first (`publish-order`) with their labels and `--blocked-by`, then the board; an issue that already exists
# (an adopted one) takes only labels, blocked-by and the board, never a body write. Every write checks the gh account
# and the repository first; a state file under `.frontlights/publish/` makes `--resume` idempotent. At the end, the
# exploration notes of `.frontlights/notes/` move to `issues/<n>/notes/` of the first issue published (redesign,
# issue 10; `move_notes`, which never overwrites).

def walkthrough_lines(item):
    """The two walkthrough lines of a slice box (references/issues.md, "Slices as acceptance criteria")."""
    walk = item['walkthrough']
    return [f'  - Roteiro: {walk["persona"]} · {walk["steps"]}',
            f'    → antes: {walk["before"]}; depois: {walk["after"]}']


def criteria_lines(issue):
    """The acceptance-criteria boxes of an issue of the plan: one box per slice with Entrega, Seams, Camadas, Depende
    de and the walkthrough, in the plan's order; an issue without slices, one box per `acceptance` item."""
    if not issue.get('slices'):
        return [f'- [ ] {text}' for text in issue.get('acceptance') or []]
    lines = []
    for item in issue['slices']:
        lines += [f'- [ ] {item["id"]}. {item["title"]}', f'  - Entrega: {item["delivers"]}',
                  f'  - Seams: {"; ".join(item["seams"])}', f'  - Camadas: {", ".join(item["layers"])}',
                  f'  - Depende de: {", ".join(item.get("depends_on") or []) or "nenhuma"}',
                  *walkthrough_lines(item)]
    return lines


PUBLISH_FOLDER = Path('.frontlights') / 'publish'
ISSUE_URL = re.compile(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)')
REREAD_FIELDS = 'number,title,body,url,state,labels,assignees,issueType,projectItems,blockedBy'


class PublishRefusal(Stage6Refusal):
    """A refusal of `publish-issue`, with the reason the session reads."""


def gh_text(argv):
    """`gh <argv>` without a shell: (exit code, stdout). gh's own output is never repeated in a refusal."""
    try:
        done = subprocess.run(['gh', *argv], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''
    return done.returncode, done.stdout


def gh_reader(gh):
    """A JSON reader over `gh` for `_cli.gh_account` and the rereads: raises on a failure, never guesses."""
    def read(argv):
        code, out = gh(argv)
        if code != 0:
            raise PublishRefusal('gh_failed', f'o gh recusou a leitura `gh {" ".join(argv[:2])}`',
                                 hint='confira a conta ativa (gh auth status) e o acesso ao repositório')
        try:
            return json.loads(out)
        except ValueError:
            raise PublishRefusal('gh_failed', f'o gh não respondeu JSON a `gh {" ".join(argv[:2])}`') from None
    return read


def normalized(text):
    """A body compared by its lines: line endings and the empty lines at the end do not count."""
    lines = re.split(r'\r\n|\r|\n', text)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines)


def stamp_check(path, root):
    """`stamp --check` in the process: {'path', 'sha256', 'approved', 'revision', 'answer'}; `approved` is False when
    the file changed since its last approval or has none."""
    import stamp  # noqa: PLC0415
    file = Path(path)
    if not file.is_file():
        raise PublishRefusal('approved_missing', f'o arquivo aprovado {path} não existe',
                             hint='passe o arquivo carimbado que o usuário aprovou')
    shown = stamp.shown_path(str(file), root)
    sha = hashlib.sha256(file.read_bytes()).hexdigest()[:stamp.STAMP_LENGTH]
    try:
        entries = [e for e in stamp.read_approvals(Path(root) / stamp.APPROVALS)
                   if isinstance(e, dict) and e.get('path') == shown]
    except stamp.Refusal as error:
        raise PublishRefusal('approvals_unreadable', str(error)) from None
    last = entries[-1] if entries else None
    return {'path': shown, 'sha256': sha, 'approved': bool(last) and last.get('sha256') == sha,
            'revision': last.get('revision') if last else None, 'answer': last.get('answer') if last else None}


def issue_body(issue, plan_path):
    """The body of an issue of the plan: `body` inline, or `body_file` (relative to the plan's folder)."""
    if nonempty(issue.get('body')):
        return issue['body']
    name = issue.get('body_file')
    if not nonempty(name):
        raise PublishRefusal('body_missing', f'a issue {issue["id"]} do plano não tem body nem body_file',
                             hint='ponha em body_file o arquivo do corpo aprovado (relativo à pasta do plano)')
    file = Path(name) if Path(name).is_absolute() else Path(plan_path).parent / name
    if not file.is_file():
        raise PublishRefusal('body_missing', f'o body_file da issue {issue["id"]} não existe: {name}')
    return file.read_bytes().decode('utf-8-sig')


def publish_steps(issue, board_, plan_repo):
    """The named writes of one issue, in order, as (key, kind, detail); the numbers come at run time."""
    adopted = nonempty(issue.get('url'))
    sub = is_sub_issue(issue)
    resolved = None if board_ is None or sub else resolve_board(board_, issue)
    labels = (resolved['labels'] if resolved and resolved['labels'] else
              [x for x in issue.get('labels', []) if isinstance(x, str) and LABEL_NAME.fullmatch(x)])
    if sub:
        labels = []
    if plan_repo is None:
        return [('local', 'local', {})], resolved, labels
    steps = []
    if adopted:
        if labels:
            steps.append(('labels', 'labels', {'labels': labels}))
        if issue['dependencies']:
            steps.append(('blocked-by', 'blocked-by', {}))
    else:
        steps.append(('create', 'create', {'labels': labels}))
    if resolved is not None:
        steps.append(('item-add', 'item-add', {}))
        steps.append(('assignee-type', 'assignee-type', {'assignee': board_.get('assignee'),
                                                          'issue_type': resolved['issue_type']}))
        for name, value in resolved['fields'].items():
            steps.append((f'field:{name}', 'field', {'field': name, 'value': value}))
    return steps, resolved, labels


def step_argv(kind, detail, repo, board_, number, url, title, body_file, blockers):
    """The argv of one write; `number`, `url` and `blockers` may be placeholders in a dry run."""
    if kind == 'create':
        argv = ['issue', 'create', '--repo', repo, '--title', title, '--body-file', str(body_file)]
        for label in detail['labels']:
            argv += ['--label', label]
        if blockers:
            argv += ['--blocked-by', ','.join(str(b) for b in blockers)]
        return argv
    if kind == 'labels':
        argv = ['issue', 'edit', str(number), '--repo', repo]
        for label in detail['labels']:
            argv += ['--add-label', label]
        return argv
    if kind == 'blocked-by':
        return ['issue', 'edit', str(number), '--repo', repo, '--add-blocked-by', ','.join(str(b) for b in blockers)]
    if kind == 'item-add':
        return ['project', 'item-add', str(board_['number']), '--owner', board_['owner'], '--url', str(url)]
    if kind == 'assignee-type':
        argv = ['issue', 'edit', str(number), '--repo', repo]
        if detail.get('assignee'):
            argv += ['--add-assignee', detail['assignee']]
        return argv + ['--type', detail['issue_type']]
    if kind == 'field':
        return ['project', 'item-edit', str(board_['number']), '--owner', board_['owner'], '--url', str(url),
                '--field', detail['field'], '--value', detail['value']]
    raise PublishRefusal('step_unknown', f'escrita desconhecida {kind}')


def find_by_title(read, repo, title, started_at):
    """`--resume`: the issue with exactly this title created since `started_at` (`in:title`), or None."""
    found = read(['issue', 'list', '--repo', repo, '--state', 'all', '--search', f'{title} in:title',
                  '--json', 'number,title,url,createdAt', '--limit', '30'])
    start = dt.datetime.fromisoformat(started_at)
    hits = []
    for item in found if isinstance(found, list) else []:
        if not isinstance(item, dict) or item.get('title') != title:
            continue
        try:
            created = dt.datetime.fromisoformat(str(item.get('createdAt', '')).replace('Z', '+00:00'))
        except ValueError:
            continue
        if created >= start - dt.timedelta(minutes=2):   # the clocks of this machine and of GitHub may differ a little
            hits.append(item)
    if len(hits) > 1:
        raise PublishRefusal('resume_ambiguous', f'{len(hits)} issues com o título "{title[:80]}" desde o início da '
                             'publicação; nada foi criado', hint='diga qual é a certa e grave o número no arquivo de estado')
    return hits[0] if hits else None


def reread_issue(read, repo, number, expected):
    """The reread of GitHub after the writes: body, boxes, labels, assignee, type, board and blockers."""
    import closeout  # noqa: PLC0415  (closeout imports this module)
    view = read(['issue', 'view', str(number), '--repo', repo, '--json', REREAD_FIELDS])
    body = view.get('body') if isinstance(view, dict) else None
    if not isinstance(body, str):
        return {'verified': False, 'problems': ['sem corpo na releitura']}
    problems = []
    if expected.get('body') is not None and normalized(body) != normalized(expected['body']):
        problems.append('corpo diferente do aprovado')
    names = {(x.get('name') or '').casefold() for x in view.get('labels') or [] if isinstance(x, dict)}
    missing = [x for x in expected.get('labels', []) if x.casefold() not in names]
    if missing:
        problems.append('labels ausentes: ' + ', '.join(missing))
    if expected.get('board'):
        if not view.get('projectItems'):
            problems.append('fora do quadro')
        kind = view.get('issueType') or {}
        kind = kind.get('name') if isinstance(kind, dict) else kind
        if expected.get('issue_type') and (kind or '').casefold() != expected['issue_type'].casefold():
            problems.append(f'tipo {kind or "vazio"}, esperado {expected["issue_type"]}')
        assignee = expected.get('assignee')
        logins = [(x.get('login') or '').casefold() for x in view.get('assignees') or [] if isinstance(x, dict)]
        if assignee and (not logins or (assignee != '@me' and assignee.casefold() not in logins)):
            problems.append(f'responsável ausente ({assignee})')
    blocked = {x.get('number') for x in view.get('blockedBy') or [] if isinstance(x, dict)}
    absent = [b for b in expected.get('blockers', []) if b not in blocked]
    if absent:
        problems.append('blocked-by ausente: ' + ', '.join(f'#{b}' for b in absent))
    counts = closeout.criteria(body) or (0, 0)
    return {'verified': not problems, 'problems': problems, 'criteria': {'checked': counts[0], 'total': counts[1]}}


def publish_issue(plan_path, approved, root, config_path=None, dry_run=False, resume=False, gh=None, account=None):
    """`publish-issue` (see the block comment above); the result dict, `ok: false` with `reason` on a refusal."""
    try:
        return publish_run(Path(plan_path), approved, Path(root), config_path, dry_run, resume, gh, account)
    except PublishRefusal as refusal:
        return {'operation': 'publish-issue', **refusal.result()}
    except _cli.AccountMismatch as mismatch:
        return {'operation': 'publish-issue', **mismatch.result(written=False)}


def publish_entries(plan, plan_path, board_, approval, approved_text, same_file):
    """Per issue, in publish order: its steps, resolved board values, labels and body, every body and title found
    letter by letter in the approved file (the plan itself, when the plan is the stamped file)."""
    entries = []
    by_id = {i['id']: i for i in plan['issues']}
    for ident in publish_order(plan):
        issue = by_id[ident]
        steps, resolved, labels = publish_steps(issue, board_, plan['repository'])
        body = None if nonempty(issue.get('url')) else issue_body(issue, plan_path)
        if body is not None:
            findings = lint_body(body)
            if findings:
                raise PublishRefusal('lint_failed', f'o corpo da issue {ident} ainda tem texto de instrução ou marcador '
                                     'sem preencher; nada foi publicado', findings=findings,
                                     hint='tire do corpo (issue-lint --body <arquivo>), mostre e aprove de novo')
            if not same_file and normalized(body) not in approved_text:
                raise PublishRefusal('body_not_approved', f'o corpo da issue {ident} não está, letra por letra, no '
                                     f'arquivo aprovado {approval["path"]}',
                                     hint='o arquivo aprovado traz o corpo inteiro de cada issue; aprove de novo')
            for name, value in (resolved or {}).get('body_fields', {}).items():
                if f'**{name}:** {value}' not in body:
                    raise PublishRefusal('body_field_missing', f'o corpo da issue {ident} não tem a linha '
                                         f'**{name}:** {value} que o quadro pede',
                                         hint='ponha a linha no corpo e aprove de novo')
        if not same_file and issue['title'] not in approved_text:
            raise PublishRefusal('title_not_approved', f'o título da issue {ident} não está no arquivo aprovado '
                                 f'{approval["path"]}', hint='o arquivo aprovado traz a tabela das issues; aprove de novo')
        entries.append({'issue': issue, 'steps': steps, 'resolved': resolved, 'labels': labels, 'body': body})
    return entries


def publish_run(plan_path, approved, root, config_path, dry_run, resume, gh, account):
    config = load(config_path) if config_path and Path(config_path).is_file() else {}
    config = config if isinstance(config, dict) else {}
    plan = load(plan_path)
    project = config.get('project')
    try:
        validate_plan(plan, project)
    except ValueError as error:
        where = {'path': error.path} if isinstance(error, PlanError) else {}
        raise PublishRefusal('plan_invalid', f'o plano não passa no validate-plan: {error}', **where) from None
    repo = plan['repository']
    if 'repository' in config and config.get('repository') != repo:
        raise PublishRefusal('repository_mismatch', f'o plano publica em {repo or "projeto local"} e o config pede '
                             f'{config.get("repository") or "projeto local"}', hint='corrija o plano ou o config')
    board_ = board(project, repo) if repo is not None else None
    approval = stamp_check(approved, root)
    approved_text = normalized(Path(approved).read_bytes().decode('utf-8-sig', errors='replace'))
    entries = publish_entries(plan, plan_path, board_, approval, approved_text,
                              Path(approved).resolve() == plan_path.resolve())
    if dry_run:
        return publish_dry_run(entries, repo, board_, approval)
    if not approval['approved']:
        raise PublishRefusal('not_approved', f'{approval["path"]} ({approval["sha256"]}) não confere com a última '
                             f'aprovação registrada ({approval["revision"] or "nenhuma"}); nada foi publicado',
                             hint='mostre o arquivo e peça a aprovação por link e carimbo (stamp --approve) de novo')
    state_path = root / PUBLISH_FOLDER / f'{approval["sha256"]}.json'
    state = load(state_path) if state_path.is_file() else None
    if state and not resume and any(v.get('done') for v in state.get('issues', {}).values()):
        raise PublishRefusal('partial_publication', 'esta aprovação já tem publicação registrada em '
                             f'{state_path.relative_to(root).as_posix()}; nada foi escrito', hint='repita com --resume: '
                             'ele relê o GitHub pelo título antes de criar o que falta')
    if state is None:
        state = {'approved': approval['path'], 'sha256': approval['sha256'], 'repository': repo,
                 'started_at': _cli.sao_paulo_now().isoformat(timespec='seconds'), 'issues': {}}
    if repo is None:
        return publish_local(entries, root, state, state_path, approval)
    return publish_remote(entries, plan, config, repo, board_, root, state, state_path, approval, resume,
                          gh or gh_text, account)


def publish_remote(entries, plan, config, repo, board_, root, state, state_path, approval, resume, gh, account):
    read = gh_reader(gh)
    check_account = account or (lambda data: _cli.gh_account(data, read))
    numbers = {i['id']: i['id'] for i in plan['issues'] if nonempty(i.get('url'))}
    for key, saved in state['issues'].items():
        if saved.get('number'):
            numbers[int(key)] = saved['number']
    relative_state = state_path.relative_to(root).as_posix()
    published, writes = [], 0
    for entry in entries:
        issue, ident = entry['issue'], entry['issue']['id']
        saved = state['issues'].setdefault(str(ident), {'done': []})
        if nonempty(issue.get('url')):
            saved.update(number=ident, url=issue['url'], adopted=True)
        elif not saved.get('number') and resume:
            hit = find_by_title(read, repo, issue['title'], state['started_at'])
            if hit:
                saved.update(number=hit['number'], url=hit['url'], recovered=True)
                saved['done'] = list(dict.fromkeys(saved['done'] + ['create']))
                numbers[ident] = hit['number']
        blockers = [numbers[d] for d in issue['dependencies'] if d in numbers]
        for key, kind, detail in entry['steps']:
            if key in saved['done']:
                continue
            check_account(config)   # before every write, never cached: another session may switch the account
            body_file = None
            if kind == 'create':
                body_file = root / PUBLISH_FOLDER / f'{approval["sha256"]}-{ident}.md'
                body_file.parent.mkdir(parents=True, exist_ok=True)
                body_file.write_bytes(entry['body'].encode('utf-8'))
            argv = step_argv(kind, detail, repo, board_, saved.get('number'), saved.get('url'), issue['title'],
                             body_file, blockers)
            code, out = gh(argv)
            writes += 1
            if code != 0:
                saved.setdefault('failed', []).append(key)
                write_json_file(state_path, state)
                raise PublishRefusal('write_failed', f'o gh recusou `gh {" ".join(argv[:2])}` da issue {ident}; a '
                                     'publicação parcial está no arquivo de estado', stateFile=relative_state,
                                     hint='corrija a causa e repita com --resume (só as escritas que faltam)')
            if kind == 'create':
                match = ISSUE_URL.search(out or '')
                if not match or match.group(1).casefold() != repo.casefold():
                    write_json_file(state_path, state)
                    raise PublishRefusal('create_unclear', f'o gh não devolveu a URL da issue {ident} criada',
                                         hint='repita com --resume: ele procura a issue pelo título antes de criar',
                                         stateFile=relative_state)
                saved.update(number=int(match.group(2)), url=match.group(0))
                numbers[ident] = saved['number']
            saved['done'].append(key)
            write_json_file(state_path, state)
        expected = {'body': entry['body'], 'labels': entry['labels'], 'board': entry['resolved'] is not None,
                    'blockers': blockers}
        if entry['resolved'] is not None:
            expected.update(issue_type=entry['resolved']['issue_type'], assignee=board_.get('assignee'))
        check = reread_issue(read, repo, saved['number'], expected)
        published.append({'id': ident, 'number': saved['number'], 'url': saved.get('url'),
                          'adopted': bool(saved.get('adopted')), 'recovered': bool(saved.get('recovered')),
                          'done': list(saved['done']), **check})
    state['finished_at'] = _cli.sao_paulo_now().isoformat(timespec='seconds')
    write_json_file(state_path, state)
    bad = [p for p in published if not p['verified']]
    shown = ', '.join(f'#{p["number"]}' for p in published)
    notes = move_notes(root, published[0]['number']) if published else None  # the notes follow the first issue
    return {'ok': not bad, 'exitCode': 0 if not bad else 2, 'operation': 'publish-issue', 'repository': repo,
            'approved': approval, 'order': [e['issue']['id'] for e in entries], 'writes': writes,
            'published': published, 'stateFile': relative_state, 'notes': notes,
            'message': (f'Publicadas e relidas: {shown}; corpo, caixas e quadro conferem.' if not bad else
                        f'Publicadas: {shown}; a releitura não confere em ' +
                        ', '.join(f'#{p["number"]} ({"; ".join(p["problems"])})' for p in bad) +
                        '. Mostre a diferença e pergunte; nada é reescrito sozinho.') + notes_sentence(notes)}


def publish_dry_run(entries, repo, board_, approval):
    """The named writes, argv by argv, with `<#id>` for a number GitHub has not given yet; nothing runs."""
    adopted = {e['issue']['id'] for e in entries if nonempty(e['issue'].get('url'))}
    issues = []
    for entry in entries:
        issue, ident = entry['issue'], entry['issue']['id']
        number = ident if ident in adopted else f'<#{ident}>'
        blockers = [d if d in adopted else f'<#{d}>' for d in issue['dependencies']]
        argvs = [['gh', *step_argv(kind, detail, repo, board_, number, issue.get('url') or f'<url #{ident}>',
                                   issue['title'], issue.get('body_file') or f'<corpo #{ident}>', blockers)]
                 for _, kind, detail in entry['steps'] if kind != 'local']
        issues.append({'id': ident, 'adopted': ident in adopted, 'commands': argvs})
    count = sum(len(i['commands']) for i in issues)
    return {'ok': True, 'exitCode': 0, 'operation': 'publish-issue', 'dryRun': True, 'repository': repo,
            'approved': approval, 'order': [e['issue']['id'] for e in entries], 'issues': issues,
            'message': f'Ensaio: {count} escrita(s) em {len(issues)} issue(s), na ordem de publish-order; nada foi '
                       'escrito.' + ('' if approval['approved'] else
                                     f' {approval["path"]} ainda não tem aprovação que confira.')}


def move_notes(root, number):
    """The exploration notes written before the issue had a number (`.frontlights/notes/`, in the main worktree) go to
    `.frontlights/issues/<number>/notes/` (docs/protocol.md, "Registros"). A file already there is never overwritten:
    the note stays where it was and is named in `kept`. None when there is no note to move."""
    source = root / '.frontlights' / 'notes'
    files = sorted(path for path in source.iterdir() if path.is_file()) if source.is_dir() else []
    if not files:
        return None
    target = root / '.frontlights' / 'issues' / str(number) / 'notes'
    target.mkdir(parents=True, exist_ok=True)
    moved, kept = [], []
    for path in files:
        if (target / path.name).exists():
            kept.append(path.name)
            continue
        os.replace(path, target / path.name)
        moved.append(path.name)
    if not any(source.iterdir()):
        source.rmdir()
    return {'to': target.relative_to(root).as_posix(), 'moved': moved, 'kept': kept}


def notes_sentence(notes):
    if not notes:
        return ''
    text = f' Notas de exploração movidas para {notes["to"]}: {len(notes["moved"])}.'
    return text + (f' Ficaram em .frontlights/notes (já existiam lá): {", ".join(notes["kept"])}.' if notes['kept'] else '')


def publish_local(entries, root, state, state_path, approval):
    """A project without a remote: each approved body becomes `.frontlights/issues/<n>/issue.json` (`source: local`)."""
    published = []
    for entry in entries:
        issue = entry['issue']
        record = root / '.frontlights' / 'issues' / str(issue['id']) / 'issue.json'
        if record.is_file() and str(issue['id']) not in state['issues']:
            raise PublishRefusal('local_exists', f'{record.relative_to(root).as_posix()} já existe; nada foi gravado',
                                 hint='uma issue local já publicada não é recriada')
        if entry['body'] is not None:
            write_json_file(record, {'number': issue['id'], 'title': issue['title'], 'body': entry['body'],
                                     'state': 'open', 'source': 'local'})
        state['issues'][str(issue['id'])] = {'number': issue['id'], 'done': ['local']}
        published.append({'id': issue['id'], 'number': issue['id'], 'url': None, 'verified': True, 'problems': [],
                          'record': record.relative_to(root).as_posix()})
    write_json_file(state_path, state)
    notes = move_notes(root, published[0]['number']) if published else None
    return {'ok': True, 'exitCode': 0, 'operation': 'publish-issue', 'repository': None, 'approved': approval,
            'published': published, 'stateFile': state_path.relative_to(root).as_posix(), 'notes': notes,
            'message': f'Projeto sem remoto: {len(published)} issue(s) gravadas em .frontlights/issues/<n>/issue.json.'
                       + notes_sentence(notes)}


# ---------------------------------------------------------------- render-criteria and issue-lint (redesign, issue 7)
# `render-criteria` prints the boxes of an issue of the plan for its body; `issue-lint` refuses a body that still
# carries the template's instruction text or an unfilled `<placeholder>` (the instructions live in
# references/issues.md and references/issue.md, never in a published body). It reads one issue with gh, or local
# bodies with --body: the bodies a daily triage proposes go through the same lint before they are shown.

# Sentences of the issue template's instructions (the template before the redesign carried ~700 words of them under
# its sections); a body that still holds one was published with the instructions in it.
INSTRUCTION_PHRASES = (
    'As seções até "Fora de escopo" são a spec',
    'O problema do ponto de vista de quem usa',
    'A solução do ponto de vista de quem usa',
    'O que é um bom teste aqui: só comportamento observável pela interface pública',
    'O que foi recusado, com o motivo. São as linhas mais úteis da página',
    'As slices, em ordem de dependência, bloqueadoras primeiro: uma caixa por slice, com o',
    'Achado de revisão, de teste ao vivo ou de conferência que não for corrigido no PR entra',
    'A fatia é esta issue mais as sub-issues dela',
    'A fatia só é definida depois da leitura de todas as camadas',
    'Rastreio dos campos, botões e ações que a fatia toca na tela, feito por busca no código',
    'é uma declaração, e o `browser-gate` a confere com o diff',
    'Troque `none` pelos links canônicos',
    'Arquivos e componentes, arquivos gerados, migrations, portas',
    'Riscos, dependências externas (outro sistema, outra equipe) e o tamanho da sessão',
    'Data e hora, branch/PR, hashes exatos de `HEAD` e do diff',
)
HTML_TAGS = {'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'details', 'div', 'dl', 'dt', 'em', 'h1', 'h2',
             'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'ol', 'p', 'picture', 'pre', 'q', 's',
             'samp', 'source', 'span', 'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
             'thead', 'tr', 'tt', 'u', 'ul', 'var', 'video'}
PLACEHOLDER = re.compile(r'<(?!!--)([^<>\n`]{1,120})>')
INLINE_CODE = re.compile(r'(`+)(?:(?!\1).)+?\1')


# The placeholders of the issue template before the redesign; the current template's are read from the file. Only
# these count as blanks: a real body carries its own `<id>` in a route, `<motivo>` in a message or `S<k>` in a
# conversion note, and those are content (found by linting the open issues of a real project, 23/10/2026).
LEGACY_PLACEHOLDERS = frozenset({
    'Um resultado observável', 'as camadas que ela toca', 'campo', 'conta 1 | contas 1 e 2', 'filha',
    'interfaces públicas em que o comportamento é observado',
    'navegador, integração, regressão, permissões entre contas, smoke', 'nenhum',
    'o que dá para demonstrar quando ela termina', 'o que mostram quando a slice entra',
    'o que os passos mostram no commit de partida', 'passos', 'persona',
    'resultado observável de ponta a ponta desta slice', 'resultado observável', 'sim | não',
    'slices anteriores, ou nenhuma', 'teste, medição ou diff revisado'})


def template_placeholders():
    """The `<...>` blanks of `templates/issue.md` (outside inline code) plus the legacy ones."""
    template = Path(__file__).resolve().parent.parent / 'templates' / 'issue.md'
    text = INLINE_CODE.sub('', template.read_text(encoding='utf-8')) if template.is_file() else ''
    return LEGACY_PLACEHOLDERS | {m.group(1) for m in PLACEHOLDER.finditer(text)}


def placeholder(inside, blanks=None):
    """Whether `<inside>` is an unfilled blank of the issue template (not an HTML tag, an autolink, an e-mail, nor
    a `<...>` the body uses as content)."""
    word = re.match(r'/?([A-Za-z][A-Za-z0-9-]*)', inside)
    if word and word.group(1).casefold() in HTML_TAGS and (len(inside) == len(word.group(0)) or
                                                           inside[len(word.group(0))] in ' /'):
        return False
    if re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', inside) or '@' in inside:
        return False
    return inside.strip() in (template_placeholders() if blanks is None else blanks)


def lint_body(body):
    """The findings of a body: [{'line', 'kind': 'instruction'|'placeholder', 'text'}]. Inline code, fenced code and
    HTML comments are skipped: a placeholder quoted in backticks is a format, not a blank."""
    import closeout  # noqa: PLC0415  (closeout imports this module)
    findings = []
    flat_body = ' '.join(body.split())
    for phrase in INSTRUCTION_PHRASES:
        if ' '.join(phrase.split()) in flat_body:
            line = next((n for n, text in enumerate(re.split(r'\r\n|\r|\n', body), 1) if phrase[:30] in text), None)
            findings.append({'line': line, 'kind': 'instruction', 'text': phrase[:80]})
    blanks = template_placeholders()
    for number, text in closeout.visible_lines(body):
        for match in PLACEHOLDER.finditer(INLINE_CODE.sub('', text)):
            if placeholder(match.group(1), blanks):
                findings.append({'line': number, 'kind': 'placeholder', 'text': match.group(0)[:80]})
    return findings


def issue_lint(issue=None, bodies=(), config_path=None, gh=None):
    """`issue-lint`: exit 0 when every body is clean, 1 with the findings otherwise."""
    targets = []
    if issue is not None:
        config = load(config_path) if config_path and Path(config_path).is_file() else {}
        repo = config.get('repository') if isinstance(config, dict) else None
        if not repository(repo):
            raise PublishRefusal('no_repository', 'issue-lint --issue lê o corpo do GitHub: o config não nomeia o '
                                 'repository', hint='passe --body <arquivo> para um corpo local')
        view = gh_reader(gh or gh_text)(['issue', 'view', str(issue), '--repo', repo, '--json', 'body'])
        body = view.get('body') if isinstance(view, dict) else None
        if not isinstance(body, str):
            raise PublishRefusal('gh_failed', f'o GitHub não deu o corpo da issue #{issue}')
        targets.append((f'#{issue}', body))
    for name in bodies or ():
        targets.append((str(name), Path(name).read_bytes().decode('utf-8-sig')))
    if not targets:
        raise PublishRefusal('nothing_to_lint', 'issue-lint precisa de --issue <n> ou --body <arquivo>')
    results = [{'source': source, 'findings': lint_body(body)} for source, body in targets]
    dirty = [r for r in results if r['findings']]
    return {'ok': not dirty, 'exitCode': 1 if dirty else 0, 'operation': 'issue-lint', 'bodies': results,
            'message': ('Nenhum texto de instrução nem marcador sem preencher.' if not dirty else
                        'Texto de instrução ou marcador sem preencher em ' +
                        ', '.join(f'{r["source"]} ({len(r["findings"])})' for r in dirty) +
                        ': tire do corpo antes de mostrar ou publicar; a instrução vive nas referências.')}


def render_criteria(plan_path, ident, config_path=None):
    """`render-criteria`: the boxes of issue `ident` of a valid plan, as markdown for its body."""
    plan = load(plan_path)
    config = load(config_path) if config_path and Path(config_path).is_file() else {}
    try:
        validate_plan(plan, config.get('project') if isinstance(config, dict) else None)
    except ValueError as error:
        where = {'path': error.path} if isinstance(error, PlanError) else {}
        raise PublishRefusal('plan_invalid', f'o plano não passa no validate-plan: {error}', **where) from None
    found = [i for i in plan['issues'] if str(i['id']) == str(ident).lstrip('#')]
    if not found:
        raise PublishRefusal('issue_missing', f'a issue {ident} não está no plano')
    lines = criteria_lines(found[0])
    return {'ok': True, 'exitCode': 0, 'operation': 'render-criteria', 'issue': found[0]['id'],
            'boxes': sum(1 for line in lines if line.startswith('- [ ] ')), 'markdown': '\n'.join(lines) + '\n',
            'message': 'As caixas para a seção "## Critérios de aceitação" do corpo, na ordem do plano.'}

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def host_flags(p):
    p.add_argument('--base', type=int, help='context of the first turn, in tokens; above 80k the host connectors '
                                            'that are not the project\'s are named (hostBase)')
    p.add_argument('--connector', action='append', default=[],
                   help='a connector (MCP server) of the host in this session; repeatable')


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
    p.add_argument('--turn', type=int, help='the turn of this report; prints next_report_turn (every 50 turns)')
    p = sub.add_parser('inspect', formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog='Recusa (saída 1):\n' + '\n'.join(f'- {line}' for line in INSPECT_REFUSALS))
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--summary', action='store_true',
                   help='per source the status and the count; per issue only number, title, state and boxes')
    p.add_argument('--offline', action='store_true', help='read nothing over the network: each source the config '
                                                          'names comes back offline (a rehearsal)')
    p.add_argument('--issue', type=int, help='add the family of the issue: its sub-issues down to 8 levels, open_count, '
                                             'open, history (closed) and excluded (another repository)')
    p = sub.add_parser('init-config', help='write the first .frontlights/config.json in the main worktree: repository '
                                           'from the remote, never the project key; returns the boards to ask about')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--repository', help='OWNER/REPOSITORY, or null for a local project (default: the remote origin)')
    p.add_argument('--prefix', help='also write branchPrefix, e.g. name/')
    p = sub.add_parser('open', help='the opening reads in one command: git fetch --prune, cleanup plan '
                                    '--from-authorizations and closeout candidates; removes and closes nothing')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--no-fetch', action='store_true', dest='no_fetch', help='skip git fetch --prune origin')
    host_flags(p)
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
    p = sub.add_parser('update-check')
    host_flags(p)
    p = sub.add_parser('publish-order')
    p.add_argument('--plan', required=True, help='the plan; prints its issue ids blockers first, for --blocked-by')
    for name in ('checkpoint', 'resume'):
        p = sub.add_parser(name)
        p.add_argument('--root', help='default: the worktree of the current directory')
        p.add_argument('--issue', help='the issue number, read with gh (default: the issue of the charter entry of '
                                       'the worktree); or a saved gh api issue JSON file, the form of before')
        p.add_argument('--handoff', help='default, with an issue number: .frontlights/issues/<n>/handoff.md of the '
                                         'main worktree (resume: the handoff the checkpoint recorded)')
        p.add_argument('--slice', help='the slice (acceptance-criteria box) in progress, e.g. S2')
        if name == 'checkpoint':
            p.add_argument('--next-step', required=True,
                           help='"<stage, step>", the step the next window starts with (each window boundary)')
            p.add_argument('--pending', action='append', default=[], help='open obligation, e.g. teste_assistido; repeatable')
        else:
            p.add_argument('--checkpoint', help='default, with an issue number: the latest checkpoint of the issue in '
                                                'this worktree, the main worktree or a worktree of the charter')
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
    p = sub.add_parser('charter', help='stage 6: write the charter authorize reads (new), extend it (renew) or add '
                                       'an issue to it (add); prints the announcement in Portuguese')
    p.add_argument('action', choices=('new', 'renew', 'add'))
    p.add_argument('--issue', action='append', default=[], help='an issue of the run; repeatable')
    p.add_argument('--direct', action='append', default=[], help='the slug of a work without an issue; repeatable')
    p.add_argument('--ownership', nargs='+', action='extend', default=[],
                   help='required for new and add: the paths the issue edits, or <issue>=<path>[,<path>] in a batch')
    p.add_argument('--prefix', help='the branch prefix (default: branchPrefix of the config)')
    p.add_argument('--concurrency', type=int, help='default 2')
    p.add_argument('--protect', action='append', default=[], help='one more protected branch; repeatable')
    p.add_argument('--base', help='the local main (default main)')
    p.add_argument('--approved-by', help='the user (default: git config user.name)')
    p.add_argument('--verify', action='append', default=[], help='a verification argv as a JSON list; repeatable')
    p.add_argument('--hours', type=int, default=CHARTER_HOURS, help=f'validity, at most {CHARTER_HOURS} (default)')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p = sub.add_parser('slice', help='stage 6: cut the branches and worktrees of slices (open) or merge one slice into '
                                     'the branch of its issue after rerunning its tests (merge)')
    p.add_argument('action', choices=('open', 'merge'))
    p.add_argument('--issue', help='the issue (default: the issue of the charter entry of the worktree)')
    p.add_argument('--slice', nargs='+', default=[], help='open: S1 [S2 ...]; merge: one slice')
    p.add_argument('--stacked-on', help='open: cut from that slice instead of the branch of the issue')
    p.add_argument('--ownership', nargs='+', action='extend', default=[],
                   help='open: S<k>=<path>[,<path>] or <path> (default: the ownership of the issue in the charter)')
    p.add_argument('--dir', help='open: the folder of the worktrees (default: <root>-worktrees beside the project)')
    p.add_argument('--from', dest='source', help='merge: a green record of homolog suite on the same commit tree')
    p.add_argument('--test', action='append', default=[], help="merge: a test argv as a JSON list; repeatable "
                                                              "(default: verification_commands of the charter)")
    p.add_argument('--watched-only', action='store_true', help='merge: a run "só com teste assistido", no test rerun')
    p.add_argument('--comment-file', help='merge: carried into the tick command it prints')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p = sub.add_parser('artifact', add_help=False,
                       help='stage 3: the skeleton of the grilling artifact, init|section|choose (_artifact.py); '
                            'delegated before this parser runs')
    p.add_argument('artifact_args', nargs=argparse.REMAINDER, help='the operation and its options, e.g. section --n 3')
    p = sub.add_parser('publish-issue', help='stage 5: publish the approved plan (stamp --check first, blockers first, '
                                             'labels, --blocked-by, the board), then reread GitHub')
    p.add_argument('--plan', required=True, help='the plan; each issue to create carries body or body_file')
    p.add_argument('--approved', required=True, help='the stamped file the user approved (bodies, board values, writes)')
    p.add_argument('--dry-run', action='store_true', dest='dry_run', help='print the named writes; write nothing')
    p.add_argument('--resume', action='store_true', help='continue a partial publication, rereading GitHub by title')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p = sub.add_parser('render-criteria', help='stage 5: the acceptance-criteria boxes of an issue of the plan, '
                                               'as markdown for its body')
    p.add_argument('--plan', required=True)
    p.add_argument('--issue', required=True, help='the id of the issue in the plan')
    p.add_argument('--config', help='.frontlights/config.json; enforces its project board fields')
    p.add_argument('--out', help='also write the markdown to this file')
    p = sub.add_parser('issue-lint', help='refuse a body that still carries the template instructions or an unfilled '
                                          '<placeholder>')
    p.add_argument('--issue', help='an issue number, read with gh (repository of the config)')
    p.add_argument('--body', action='append', default=[], help='a local body file, such as one a daily triage '
                                                               'proposes; repeatable')
    p.add_argument('--root', help='default: the main worktree of the current directory')
    p.add_argument('--config', help='default: the .frontlights/config.json of the main worktree')
    p = sub.add_parser('stamp', add_help=False,
                       help='stamp.py: binds the approval of a document to its exact content (issue 61); '
                            'delegated before this parser runs')
    p.add_argument('stamp_args', nargs=argparse.REMAINDER, help='the file and its options, e.g. spec.md --check')
    return parser


def resolve_defaults(args):
    """--root and --config the command line left out, by the rules of `_cli`."""
    if args.command == 'inspect':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
    elif args.command == 'init-config':
        args.root = str(_cli.root_path(args.root))
    elif args.command == 'open':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root)
    elif args.command in ('evidence', 'review-gate', 'checkpoint', 'resume'):
        args.root = str(_cli.tree_path(args.root))
    elif args.command == 'archive':
        args.root = str(_cli.root_path(args.root))
        args.issue = _cli.issue_number(args.issue, _cli.current_tree(), args.root)
    elif args.command == 'charter':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root)
    elif args.command == 'slice':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
        args.issue = _cli.issue_number(args.issue, _cli.current_tree(), args.root)
    elif args.command == 'issue-lint':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
    elif args.command == 'publish-issue':
        args.root = str(_cli.root_path(args.root))
        args.config = _cli.config_path(args.config, args.root, required=False)
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
    if sys.argv[1:2] == ['artifact']:
        # Delegated whole (redesenho, issue 6): init, section and choose live in _artifact.py, one parser.
        import _artifact
        return _artifact.main(sys.argv[2:])
    if sys.argv[1:2] == ['browser-gate']:
        # Delegated whole (issue 8): `--answer` and the `record` subcommand live in browser_gate.py, one parser.
        import browser_gate
        return browser_gate.main(sys.argv[2:])
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
                if 'teste_assistido' in result['pending'] and result['action'] in ('handoff', 'stop', 'cut'):
                    # The watched run must not be the last thing a window pays for: ask it before spending more.
                    result['ask_before_continuing'] = ['teste_assistido']
            if args.turn is not None:
                result['next_report_turn'] = next_report(args.turn)
        elif args.command == 'inspect' and args.config is None:
            # No config: the setup is the next step, not a usage error (references/setup.md).
            result = {'ok': True, 'status': 'config_missing',
                      'config_path': str(Path(args.root) / _cli.CONFIG),
                      'warnings': [w for w in setup_warnings({'browserTest': None}, args.root)
                                   if not w.startswith('branch_prefix_missing')],
                      'hint': f'frontlights.py init-config grava o config na worktree principal; {SETUP}'}
        elif args.command == 'inspect':
            result = inspect(load(args.config), args.root, args.config, args.summary, args.offline, args.issue)
        elif args.command == 'init-config':
            repository = ... if args.repository is None else (None if args.repository == 'null' else args.repository)
            try:
                result = init_config(args.root, repository, args.prefix)
            except Stage6Refusal as refusal:
                result = refusal.result()
            code = result['exitCode']
        elif args.command == 'open':
            result = open_session(args.config, args.root, fetch=not args.no_fetch)
            warning = host_base(args.base, args.connector, project_connectors(args.config))
            if warning:
                result['hostBase'] = warning
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
            warning = host_base(args.base, args.connector,
                                project_connectors(_cli.config_path(None, _cli.main_worktree(), required=False)))
            if warning:
                result['hostBase'] = warning
        elif args.command == 'checkpoint':
            result = checkpoint_cli(args.issue, args.root, args.handoff, args.next_step, args.pending, args.slice)
        elif args.command == 'resume':
            result = resume_cli(args.issue, args.root, args.handoff, args.checkpoint, slice_id=args.slice)
        elif args.command == 'archive':
            result = archive_round(args.root, args.issue)
        elif args.command == 'charter':
            result = charter_cli(args.action, args.root, args.config, args.issue, args.direct, args.ownership,
                                 args.prefix, args.concurrency, args.protect, args.base, args.approved_by,
                                 args.verify, args.hours)
            code = result['exitCode']
        elif args.command == 'slice':
            result = slice_cli(args.action, args.root, args.config, args.issue, args.slice, args.stacked_on,
                               args.ownership, args.dir, args.source, args.test, args.watched_only, args.comment_file)
            code = result['exitCode']
        elif args.command == 'render-criteria':
            try:
                result = render_criteria(args.plan, args.issue, args.config)
            except PublishRefusal as refusal:
                result = {'operation': 'render-criteria', **refusal.result()}
            if args.out and result['ok']:
                Path(args.out).write_bytes(result['markdown'].encode('utf-8'))
            code = result['exitCode']
        elif args.command == 'issue-lint':
            try:
                result = issue_lint(args.issue, args.body, args.config)
            except PublishRefusal as refusal:
                result = {'operation': 'issue-lint', **refusal.result()}
            code = result['exitCode']
        elif args.command == 'publish-issue':
            result = publish_issue(args.plan, args.approved, args.root, args.config, args.dry_run, args.resume)
            code = result['exitCode']
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
