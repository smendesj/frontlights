"""`frontlights.py artifact`: the skeleton of the grilling artifact (redesenho, issue 6).

  init     `[--issue <n>] [--title "<resultado>"] [--kind tela|fluxo|regra|camadas|texto] [--before <png>]`: copies
           `templates/artifact-page.html` to `.frontlights/artifact.html` of the main worktree (with `--issue`,
           `.frontlights/issues/<n>/artifact.html`) with section 1, the base: `<img src="antes.png">` with a screen,
           a placeholder for the diagram without one. Refuses an existing source.
  section  `--n 3 --kind tela|fluxo|regra|camadas|texto --title "<pergunta>" [--option "<opção>"…] --content
           <secao-3.md>`: one section per `--n` (several `--n` in one call, `--kind`/`--title`/`--content` in the
           same order; `--option "3:<opção>"` names the section when there are several), in the fixed fields of
           `templates/grilling-section.html`, filled from the `## <campo>` headings of the content file. A section
           with the same number is replaced (the expanded section of a re-ask). Refuses a missing Visual, Cenário por
           opção or Consequências, an option missing from Cenário or Consequências, inline style or script, and a
           code excerpt above 15 lines. A missing source with an artifact URL in the discovery log is refused with
           "leia a página publicada de volta para <caminho>".
  choose   `--n 3 --answer "<literal>"`: writes the answer in the Escolha field of that section.
  roteiro  `--content <roteiro.md>`: the last section, "Roteiro do teste livre", written after the merge into the local
           main and before the free test window opens: one `## <critério ou correção>` per group, an optional
           `Conta: conta1|conta2` line, `- ` steps and one `Esperado:` line each. Always the last section; a second call
           replaces it. Refuses a group without steps or without Esperado, inline style or script, and a password.

Every write prints `publish.file_path` (and, from `init --before`, `publish.files`): the session publishes the whole
source once per round with the host's artifact tool, on the same URL, never by `edits`. The content, the publication
and the URL are the session's; no script reads or publishes the page.
"""
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _cli  # noqa: E402

TEMPLATE = HERE.parent / 'templates' / 'artifact-page.html'
KINDS = ('tela', 'fluxo', 'regra', 'camadas', 'texto')
IMAGE = 'antes.png'
CODE_LINES = 15
START, END = '<!-- secoes -->', '<!-- /secoes -->'
# (key, heading in the page, css class, always present) in the order of templates/grilling-section.html
FIELDS = (('por que', 'Por que estamos perguntando isso', 'campo-por-que', False),
          ('visual', 'Visual', 'campo-visual', True),
          ('cenario', 'Cenário por opção', 'campo-cenario', True),
          ('consequencias', 'Consequências', 'campo-consequencias', True),
          ('conceitos', 'Conceitos', 'campo-conceitos', False),
          ('onde o projeto', 'Onde o projeto já faz', 'campo-projeto', False),
          ('recomendacao', 'Recomendação (opinião)', 'campo-recomendacao', False),
          ('escolha', 'Escolha', 'campo-escolha', False))
PENDING_CHOICE = 'a escolher, quando o usuário responder'


class Refusal(Exception):
    def __init__(self, reason, message, hint=None):
        super().__init__(message)
        self.reason, self.hint = reason, hint

    def result(self):
        out = {'ok': False, 'exitCode': 1, 'reason': self.reason, 'message': str(self)}
        if self.hint:
            out['hint'] = self.hint
        return out


def plain(text):
    text = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in text if not unicodedata.combining(c)).strip()


def source_path(root, issue):
    folder = Path(root).resolve() / '.frontlights'
    return folder / 'issues' / str(issue) / 'artifact.html' if issue else folder / 'artifact.html'


def logged_url(root):
    """The artifact URL the discovery log recorded, when it did."""
    log = Path(root) / '.frontlights' / 'discovery.md'
    if not log.is_file():
        return None
    for line in log.read_text(encoding='utf-8').splitlines():
        if 'Artifact URL' in line:
            found = re.search(r'https://\S+', line.split(':', 1)[1] if ':' in line else '')
            if found:
                return found.group(0).rstrip(').,;')
    return None


def publish(source, files=None, sections=None):
    out = {'ok': True, 'exitCode': 0, 'source': str(source), 'publish': {'file_path': str(source)}}
    if files:
        out['publish']['files'] = files
    if sections is not None:
        out['sections'] = sections
    out['message'] = (f'Publique a fonte inteira uma vez nesta rodada com a ferramenta de artefatos (file_path = '
                      f'{source}), na mesma URL; nunca por edits.')
    return out


# ---------------------------------------------------------------- the content file, in a small Markdown

def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def table(rows):
    cells = [[c.strip() for c in row.strip().strip('|').split('|')] for row in rows
             if not re.fullmatch(r'\|?[\s:|-]+\|?', row.strip())]
    if not cells:
        return ''
    head = ''.join(f'<th>{inline(c)}</th>' for c in cells[0])
    body = ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in row) + '</tr>' for row in cells[1:])
    return f'<table class="casos"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def blocks(text, n, field):
    """The body of one field: paragraphs, `- ` items, pipe tables, fenced code and lines of raw HTML."""
    out, para, items, rows, code = [], [], [], [], None
    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para))}</p>')
            para.clear()
        if items:
            out.append('<ul class="opcoes">' + ''.join(f'<li>{inline(i)}</li>' for i in items) + '</ul>')
            items.clear()
        if rows:
            out.append(table(rows))
            rows.clear()
    for line in text.splitlines():
        stripped = line.strip()
        if code is not None:
            if stripped.startswith('```'):
                if len(code) > CODE_LINES:
                    raise Refusal('code_too_long', f'seção {n}, {field}: trecho de código com {len(code)} linhas; o '
                                  f'limite é {CODE_LINES}, com o caminho', hint='corte o trecho ao essencial')
                out.append('<pre class="codigo"><code>' + html.escape('\n'.join(code), quote=False) + '</code></pre>')
                code = None
            else:
                code.append(line)
            continue
        if stripped.startswith('```'):
            flush()
            code = []
        elif not stripped:
            flush()
        elif stripped.startswith('|'):
            if para or items:
                flush()
            rows.append(stripped)
        elif stripped.startswith('- '):
            if para or rows:
                flush()
            items.append(stripped[2:])
        elif stripped.startswith('<'):
            flush()
            out.append(stripped)
        else:
            if items or rows:
                flush()
            para.append(stripped)
    if code is not None:
        raise Refusal('code_open', f'seção {n}, {field}: bloco de código sem o fechamento ```')
    flush()
    return '\n'.join(out)


def parse_content(path, n):
    path = Path(path)
    if not path.is_file():
        raise Refusal('content_missing', f'seção {n}: o arquivo de conteúdo {path} não existe',
                      hint='escreva os campos em ## <campo> (Por que, Visual, Cenário, Consequências, ...)')
    text = path.read_text(encoding='utf-8-sig')
    lowered = text.lower()
    if 'style=' in lowered or '<script' in lowered:
        raise Refusal('inline_style', f'seção {n}: estilo inline ou script no conteúdo; a página usa só as classes '
                      'e os tokens dela', hint='tire o style=/<script>; posição de marca vai em @x,y')
    fields, current = {}, None
    for line in text.splitlines():
        if line.startswith('## '):
            name = plain(line[3:])
            current = next((key for key, *_ in FIELDS if name.startswith(key)), None)
            if current is None:
                raise Refusal('unknown_field', f'seção {n}: campo desconhecido "{line[3:].strip()}"',
                              hint='; '.join(heading for _, heading, _, _ in FIELDS))
            fields[current] = []
        elif current:
            fields[current].append(line)
    return {key: '\n'.join(lines).strip() for key, lines in fields.items()}


# ---------------------------------------------------------------- one section

MARK = re.compile(r'^- \*\*(?P<option>[^*]+)\*\*\s*(?:@(?P<x>\d{1,3}),(?P<y>\d{1,3}))?\s*:\s*(?P<text>.+)$')


def screen_visual(n, title, options, body, image):
    """Tela: the base print and, per option, the same print with its marks; the bullets `- **<opção>** @x,y: texto`
    of the Visual field are the marks, the other lines follow the figures."""
    marks, rest, rules = {}, [], []
    for line in body.splitlines():
        match = MARK.match(line.strip())
        if match and match.group('option').strip() in options:
            marks.setdefault(match.group('option').strip(), []).append(match)
        else:
            rest.append(line)
    alt = html.escape(title)
    figures = [f'<figure class="base"><figcaption>Base</figcaption><img class="print" src="{image}" alt="Base: {alt}">'
               '</figure>']
    k = 0
    for option in options:
        inner = [f'<img class="print" src="{image}" alt="Com a opção {html.escape(option)}: {alt}">']
        for match in marks.get(option, []):
            k += 1
            mark_id = f'marca-{n}-{k}'
            inner.append(f'<p class="marca marca-texto" id="{mark_id}">{inline(match.group("text"))}</p>')
            if match.group('x'):
                rules.append(f'#{mark_id} {{ left: {int(match.group("x"))}%; top: {int(match.group("y"))}%; }}')
        figures.append(f'<figure class="com-opcao"><figcaption>Com a opção: {html.escape(option)}</figcaption>'
                       f'<div class="print-marcado">{"".join(inner)}</div></figure>')
    visual = '<div class="comparacao">' + ''.join(figures) + '</div>'
    extra = blocks('\n'.join(rest), n, 'Visual')
    return (visual + ('\n' + extra if extra else '')), rules


def render_section(n, kind, title, options, fields, image):
    for key, heading, _, required in FIELDS:
        if required and not fields.get(key):
            raise Refusal('missing_field', f'seção {n}: falta o campo {heading}; Visual, Cenário por opção e '
                          'Consequências estão em toda seção (uma frase basta)', hint=f'## {heading}')
    for option in options:
        for key in ('cenario', 'consequencias'):
            if option not in fields[key]:
                raise Refusal('option_missing', f'seção {n}: a opção "{option}" não aparece em '
                              f'{dict((k, h) for k, h, _, _ in FIELDS)[key]}',
                              hint=f'um item por opção: - **{option}**: ...')
    rules = []
    parts = [f'<section class="secao secao-{kind}" id="secao-{n}">',
             f'<h2 class="secao-titulo">Seção {n}: {html.escape(title)}</h2>']
    for key, heading, css, _ in FIELDS:
        body = fields.get(key, '')
        if key == 'escolha':
            content = f'<p>{inline(body) if body else PENDING_CHOICE}</p>'
        elif not body:
            continue
        elif key == 'visual' and kind == 'tela':
            content, rules = screen_visual(n, title, options, body, image)
        else:
            content = blocks(body, n, heading)
        parts.append(f'<div class="campo {css}">\n<h3>{heading}</h3>\n{content}\n</div>')
    parts.append('</section>')
    return '\n'.join(parts), rules


def section_re(n):
    return re.compile(r'<section class="secao[^"]*" id="secao-%d">.*?</section>\n?' % n, re.S)


def put_section(page, n, markup):
    found = section_re(n).search(page)
    if found:
        return page[:found.start()] + markup + '\n' + page[found.end():]
    later = [(int(m.group(1)), m.start()) for m in re.finditer(r'<section class="secao[^"]*" id="secao-(\d+)">', page)
             if int(m.group(1)) > n]
    script = page.find(ROTEIRO_OPEN)
    at = min(later)[1] if later else (script if script >= 0 else page.index(END))
    return page[:at] + markup + '\n' + page[at:]


def put_rules(page, n, rules):
    head, sep, tail = page.partition('<style id="marcas">\n')
    if not sep:
        return page
    block, close, after = tail.partition('</style>')
    kept = [line for line in block.splitlines() if line.strip() and not line.startswith(f'#marca-{n}-')]
    lines = kept + rules
    return head + sep + ''.join(line + '\n' for line in lines) + close + after


# ---------------------------------------------------------------- the operations

def read_source(root, issue):
    source = source_path(root, issue)
    if source.is_file():
        return source, source.read_text(encoding='utf-8')
    url = logged_url(root)
    if url:
        raise Refusal('source_missing', f'a fonte {source} não existe e o log de descoberta já tem a URL {url}: leia '
                      f'a página publicada de volta para {source} e repita',
                      hint=f'ferramenta de artefatos, action read, url {url}; grave o HTML em {source}')
    raise Refusal('no_artifact', f'não há artefato em {source} nem URL no log de descoberta',
                  hint='frontlights.py artifact init')


def op_init(root, issue, title, kind, before):
    source = source_path(root, issue)
    if source.exists():
        raise Refusal('artifact_exists', f'o artefato já existe em {source}: um por grilling, na mesma URL',
                      hint='acrescente seções com `frontlights.py artifact section`')
    page = TEMPLATE.read_text(encoding='utf-8').replace('{{TITULO}}', html.escape(title))
    if kind == 'tela':
        visual = (f'<div class="comparacao"><figure class="base"><figcaption>Base</figcaption>'
                  f'<img class="print" src="{IMAGE}" alt="A tela na base"></figure></div>')
    else:
        visual = '<p>O diagrama da base: o fluxo, as camadas ou a regra de hoje.</p>'
    first = (f'<section class="secao secao-{kind}" id="secao-1">\n<h2 class="secao-titulo">Seção 1: a base</h2>\n'
             f'<div class="campo campo-visual">\n<h3>Visual</h3>\n{visual}\n</div>\n</section>\n')
    page = page.replace(END, first + END)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(page, encoding='utf-8')
    files = None
    result = publish(source)
    if kind == 'tela':
        if before:
            files = {IMAGE: str(Path(before))}
            result = publish(source, files)
        else:
            result['message'] += (f' Antes, o print da base: `serve.py window shot --pass antes --name base`, '
                                  f'publicado em files como {IMAGE}.')
    result['message'] += ' Grave a URL e o caminho da fonte no log (templates/discovery.md, "Artifact URL and source path").'
    return result


def pair(values, count, flag, n_values, allow_one=False):
    if len(values) == count:
        return values
    if allow_one and len(values) == 1:
        return values * count
    raise Refusal('usage', f'{flag} aparece {len(values)} vez(es) para {count} --n ({", ".join(map(str, n_values))})',
                  hint=f'um {flag} por --n, na mesma ordem')


def options_for(n, values, single):
    out = []
    for value in values:
        match = re.match(r'^(\d+):(.*)$', value)
        if match and not single:
            if int(match.group(1)) == n:
                out.append(match.group(2).strip())
        elif single:
            out.append(value.strip())
    return out


def op_section(root, issue, ns, kinds, titles, options, contents, image):
    if not ns:
        raise Refusal('usage', 'section precisa de --n', hint='--n 3 --kind regra --title "..." --content secao-3.md')
    kinds = pair(kinds, len(ns), '--kind', ns, allow_one=True)
    titles = pair(titles, len(ns), '--title', ns)
    contents = pair(contents, len(ns), '--content', ns)
    source, page = read_source(root, issue)
    for n, kind, title, content in zip(ns, kinds, titles, contents):
        markup, rules = render_section(n, kind, title, options_for(n, options, len(ns) == 1),
                                       parse_content(content, n), image)
        page = put_rules(put_section(page, n, markup), n, rules)
    source.write_text(page, encoding='utf-8')
    return publish(source, sections=ns)


def op_choose(root, issue, n, answer):
    source, page = read_source(root, issue)
    found = section_re(n).search(page)
    if not found:
        raise Refusal('section_missing', f'a seção {n} não existe em {source}', hint='frontlights.py artifact section')
    block = found.group(0)
    choice = f'<div class="campo campo-escolha">\n<h3>Escolha</h3>\n<p>{inline(answer)}</p>\n</div>'
    if 'campo-escolha' in block:
        block = re.sub(r'<div class="campo campo-escolha">.*?</div>', lambda _: choice, block, count=1, flags=re.S)
    else:
        block = block.replace('</section>', choice + '\n</section>', 1)
    page = page[:found.start()] + block + page[found.end():]
    source.write_text(page, encoding='utf-8')
    return publish(source, sections=[n])


ROTEIRO_OPEN = '<section class="secao secao-roteiro" id="roteiro">'
ROTEIRO_RE = re.compile(re.escape(ROTEIRO_OPEN) + r'.*?</section>\n?', re.S)
SECRET = re.compile(r'\b(senha|password|passwd|pwd)\b\s*[:=]', re.I)


def render_roteiro(path):
    path = Path(path)
    if not path.is_file():
        raise Refusal('content_missing', f'roteiro: o arquivo {path} não existe',
                      hint='## S1 <critério>, Conta: conta1, - passo, Esperado: ...')
    text = path.read_text(encoding='utf-8-sig')
    lowered = text.lower()
    if 'style=' in lowered or '<script' in lowered:
        raise Refusal('inline_style', 'roteiro: estilo inline ou script no conteúdo')
    if SECRET.search(text):
        raise Refusal('secret', 'roteiro: uma senha no conteúdo; a conta entra só pelo rótulo (conta1, conta2)',
                      hint='Conta: conta1')
    groups, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if line.startswith('## '):
            current = {'title': line[3:].strip(), 'account': None, 'steps': [], 'expected': None}
            groups.append(current)
        elif current is None or not stripped:
            continue
        elif stripped.startswith('- '):
            current['steps'].append(stripped[2:])
        elif plain(stripped).startswith('conta:'):
            current['account'] = stripped.split(':', 1)[1].strip()
        elif plain(stripped).startswith('esperado:'):
            current['expected'] = stripped.split(':', 1)[1].strip()
    if not groups:
        raise Refusal('roteiro_empty', 'roteiro: nenhum grupo ## <critério>', hint='## S1 <critério>')
    parts = [ROTEIRO_OPEN, '<h2 class="secao-titulo">Roteiro do teste livre</h2>',
             '<p>Na janela "MAIN LOCAL: teste livre", siga um grupo por vez e marque o que conferiu. O teste é seu: '
             'peça ajuda ou uma correção a qualquer momento.</p>']
    for group in groups:
        if not group['steps'] or not group['expected']:
            missing = 'o passo a passo' if not group['steps'] else 'a linha Esperado:'
            raise Refusal('roteiro_incomplete', f'roteiro, "{group["title"]}": falta {missing}',
                          hint='- passo, depois Esperado: <o que a tela mostra>')
        parts.append(f'<div class="campo">\n<h3>{inline(group["title"])}</h3>')
        if group['account']:
            parts.append(f'<p>Conta: {inline(group["account"])}</p>')
        parts.append('<ol>' + ''.join(f'<li>{inline(step)}</li>' for step in group['steps']) + '</ol>')
        parts.append(f'<p><strong>Esperado:</strong> {inline(group["expected"])}</p>\n</div>')
    parts.append('</section>')
    return '\n'.join(parts), len(groups)


def op_roteiro(root, issue, content):
    if not content:
        raise Refusal('usage', 'roteiro precisa de --content', hint='--content roteiro.md')
    source, page = read_source(root, issue)
    markup, count = render_roteiro(content)
    page = ROTEIRO_RE.sub('', page)
    page = page.replace(END, markup + '\n' + END, 1)
    source.write_text(page, encoding='utf-8')
    result = publish(source, sections=['roteiro'])
    result['groups'] = count
    result['message'] += ' O roteiro é a última seção: diga ao usuário o link e que ele está no fim da página.'
    return result


def parser():
    p = _cli.JsonParser(prog='frontlights.py artifact', description=__doc__,
                        formatter_class=__import__('argparse').RawDescriptionHelpFormatter)
    p.add_argument('artifact_op', choices=('init', 'section', 'choose', 'roteiro'))
    p.add_argument('--root', help='worktree principal, onde fica .frontlights (padrão: a principal)')
    p.add_argument('--issue', help='issue já publicada: a fonte vai para .frontlights/issues/<n>/artifact.html')
    p.add_argument('--title', action='append', default=[], help='init: título da página; section: a pergunta, um por --n')
    p.add_argument('--kind', action='append', default=[], choices=KINDS,
                   help='o tipo da pergunta, que escolhe o Visual (init: a base; section: um por --n, ou um para todos)')
    p.add_argument('--before', help='init: o print da base (serve.py window shot --pass antes --name base), publicado como antes.png')
    p.add_argument('--n', type=int, action='append', default=[], help='section e choose: o número da seção; section aceita vários')
    p.add_argument('--option', action='append', default=[], help='section: uma opção; com vários --n, "<n>:<opção>"')
    p.add_argument('--content', action='append', default=[], help='section: o arquivo com os campos em ## <campo>, um por --n; roteiro: o roteiro do teste livre')
    p.add_argument('--image', default=IMAGE, help=f'section, tipo tela: o print publicado (padrão {IMAGE})')
    p.add_argument('--answer', help='choose: a resposta literal do usuário')
    return _cli.output_flags(p)


def run(args):
    root = _cli.root_path(args.root)
    if args.artifact_op == 'init':
        if len(args.title) > 1 or len(args.kind) > 1:
            raise Refusal('usage', 'init leva um --title e um --kind')
        return op_init(root, args.issue, args.title[0] if args.title else 'Artefato do grilling',
                       args.kind[0] if args.kind else 'tela', args.before)
    if args.artifact_op == 'section':
        return op_section(root, args.issue, args.n, args.kind, args.title, args.option, args.content, args.image)
    if args.artifact_op == 'roteiro':
        if len(args.content) > 1:
            raise Refusal('usage', 'roteiro leva um --content')
        return op_roteiro(root, args.issue, args.content[0] if args.content else None)
    if len(args.n) != 1 or not args.answer:
        raise Refusal('usage', 'choose leva um --n e --answer', hint='--n 3 --answer "<resposta literal>"')
    return op_choose(root, args.issue, args.n[0], args.answer)


def main(argv):
    """Prints one JSON object; exit 0 written, 1 refused (usage or a rule of the artifact)."""
    _cli.utf8_streams()
    try:
        args = parser().parse_args(argv)
    except _cli.UsageError as error:
        return _cli.print_usage_error(error, 1)
    try:
        result = run(args)
    except Refusal as refusal:
        result = refusal.result()
    except OSError as error:
        result = {'ok': False, 'exitCode': 1, 'reason': 'io', 'message': str(error)}
    _cli.emit(json.dumps(result, indent=2, ensure_ascii=False), f'artifact-{args.artifact_op}', args.full)
    return result['exitCode']
