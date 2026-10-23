"""Duplicação nos textos da skill, como relatório (redesenho, issue 10).

`--shingles` procura trechos de `--min-words` palavras seguidas (padrão 15) que aparecem em mais de um lugar dos textos
da skill (`SKILL.md`, `references/`, `docs/`, `templates/*.md|html`): o mesmo trecho em dois arquivos, ou duas vezes no
mesmo arquivo (as licenças ficam de fora). Cada trecho sai uma vez, no primeiro lugar. É o sinal de uma regra com dois lares; a casa única e os ponteiros são decisão de quem edita.

Só relata: sai sempre com 0 depois de imprimir o relatório (nunca é portão nem hook; o `tests/pre_commit.py` o chama
e mostra o resumo). As palavras são comparadas sem caixa e sem a pontuação das pontas; blocos de código cercados por
``` ficam de fora, e cada parágrafo conta sozinho (um trecho não atravessa linha em branco). Por padrão, um trecho com
crase (comando, caminho, identificador) não conta, porque comandos e ponteiros se repetem por desenho;
`--allow-backticks` os inclui.

Uso: python skill_lint.py --shingles [--min-words N] [--allow-backticks] [--root PASTA] [--json] [arquivo ...]
Saída 0: relatório impresso (com ou sem trechos); 2: erro de uso. Só lê; nada grava, nada chama.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
EDGES = '.,;:!?()[]{}"\'«»“”*_|'
PREVIEW_WORDS = 12


def texts(root):
    """Os textos da skill, menos as licenças (texto legal que se repete por desenho)."""
    found = [root / 'SKILL.md', *root.glob('references/*.md'), *root.glob('docs/*.md'),
             *root.glob('templates/*.md'), *root.glob('templates/*.html')]
    return sorted(path for path in found if not path.name.startswith('LICENSE'))


def tokens(text):
    """[(palavra normalizada, palavra crua, linha, parágrafo)], fora dos blocos de código."""
    found, paragraph, fenced = [], 0, False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith('```'):
            fenced = not fenced
            paragraph += 1
            continue
        if fenced:
            continue
        if not line.strip():
            paragraph += 1
            continue
        for raw in line.split():
            word = raw.strip(EDGES).casefold()
            if word:
                found.append((word, raw, number, paragraph))
    return found


def shingles(words, size, allow_backticks):
    """{posição: chave} das janelas de `size` palavras num mesmo parágrafo."""
    keys = {}
    for start in range(len(words) - size + 1):
        window = words[start:start + size]
        if window[0][3] != window[-1][3]:
            continue
        if not allow_backticks and any('`' in raw for _, raw, _, _ in window):
            continue
        keys[start] = ' '.join(word for word, _, _, _ in window)
    return keys


def report(paths, root, size=15, allow_backticks=False):
    """Os trechos repetidos: cada um com o arquivo, a linha, o tamanho em palavras, o começo e os outros lugares."""
    words, keys, where = {}, {}, defaultdict(list)
    for path in paths:
        name = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        words[name] = tokens(path.read_text(encoding='utf-8'))
        keys[name] = shingles(words[name], size, allow_backticks)
        for start, key in keys[name].items():
            where[key].append((name, start))
    repeated = {key for key, places in where.items() if len(places) > 1}
    passages = []
    for name in words:
        run = None
        for start in sorted(keys[name]):
            if keys[name][start] not in repeated:
                continue
            if run and start == run[1] + 1:
                run[1] = start
                continue
            if run:
                passages.append(passage(name, run, words, keys, where, size))
            run = [start, start]
        if run:
            passages.append(passage(name, run, words, keys, where, size))
    passages = [item for item in passages if first_of_its_group(item)]
    return {'minWords': size, 'allowBackticks': allow_backticks, 'files': len(words), 'count': len(passages),
            'passages': passages}


def place(text):
    name, line = text.rsplit(':', 1)
    return name, int(line)


def first_of_its_group(item):
    """Um trecho repetido aparece uma vez no relatório: no primeiro dos lugares em que está."""
    return all((item['file'], item['line']) < place(other) for other in item['also'])


def passage(name, run, words, keys, where, size):
    first, last = run
    stream = words[name]
    others = sorted({f'{other}:{words[other][start][2]}' for other, start in where[keys[name][first]]
                     if (other, start) != (name, first)})
    length = last - first + size
    return {'file': name, 'line': stream[first][2], 'words': length, 'also': others,
            'start': ' '.join(raw for _, raw, _, _ in stream[first:first + PREVIEW_WORDS])}


def text_report(result):
    lines = [f'Trechos repetidos de {result["minWords"]}+ palavras: {result["count"]} (relatório, não bloqueia)']
    for item in result['passages']:
        lines.append(f'- {item["file"]}:{item["line"]} ({item["words"]} palavras), também em '
                     f'{", ".join(item["also"])}: «{item["start"]}…»')
    return '\n'.join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description='Duplicação nos textos da skill, como relatório que nunca bloqueia.')
    parser.add_argument('--shingles', action='store_true', required=True,
                        help='procura trechos de --min-words palavras repetidos entre os textos da skill')
    parser.add_argument('--min-words', type=int, default=15, help='tamanho mínimo do trecho (padrão: 15)')
    parser.add_argument('--allow-backticks', action='store_true',
                        help='conta também os trechos com crase (comandos, caminhos, identificadores)')
    parser.add_argument('--root', default=str(SKILL), help='a pasta da skill (padrão: a deste script)')
    parser.add_argument('--json', action='store_true', help='imprime o relatório em JSON')
    parser.add_argument('files', nargs='*', help='só estes arquivos (padrão: SKILL.md, references, docs, templates)')
    options = parser.parse_args(argv)
    if options.min_words < 2:
        parser.error('--min-words precisa ser 2 ou mais')
    root = Path(options.root).resolve()
    paths = [Path(item).resolve() for item in options.files] or texts(root)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        parser.error(f'arquivo inexistente: {", ".join(missing)}')
    result = report(paths, root, options.min_words, options.allow_backticks)
    print(json.dumps(result, ensure_ascii=False, indent=2) if options.json else text_report(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
