"""Leitura dos textos da skill e do repositório para os testes de documento (redesenho, issue 10).

Um helper só, no lugar das cópias de `read`/`flat`/`section` espalhadas pelos módulos:

- `read(*partes)`: o texto cru de um arquivo, a partir da raiz do repositório;
- `flat(texto)` e `doc(*partes)`: o texto com os espaços achatados (`doc` lê e achata);
- `section(texto, título)`: o corpo de uma seção `##`/`###` cujo título começa com `título`, até o próximo título
  do mesmo nível ou acima (vazio quando não há a seção);
- `assertPointsTo(caso, texto, arquivo, título)`: o texto aponta para a seção (`arquivo`, "título", com ou sem
  crase e vírgula, como `test_pointers` lê) e a seção existe no arquivo.

`assertPointsTo` serve só onde um doc é cópia de outra casa (a regra vive na referência, o doc só aponta). Formato e
permissão continuam pinados no doc que os define; os `assertNotIn` das regras antigas ficam como estão.

Seam: o texto dos arquivos. Só biblioteca padrão.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def doc(*parts):
    return flat(read(*parts))


def section(text, title):
    """O corpo da primeira seção `##` ou `###` cujo título começa com `title`, sem a linha do título."""
    match = re.search(rf'^(#{{2,3}}) {re.escape(title)}[^\n]*\n', text, re.M)
    if not match:
        return ''
    level = len(match.group(1))
    rest = text[match.end():]
    end = re.search(rf'^#{{1,{level}}} ', rest, re.M)
    return rest[:end.start()] if end else rest


def _skill_path(path):
    """Um caminho como os textos o citam (`references/x.md`, `docs/y.md`, `SKILL.md`) dentro da skill, ou da raiz."""
    inside = SKILL / path
    return inside if inside.exists() else ROOT / path


def assertPointsTo(case, text, path, title):
    """`text` cita `path` e, logo depois, "title"; e `path` tem uma seção com esse título."""
    plain = flat(text)
    pointer = re.compile(rf'`?{re.escape(path)}`?,? \(?"{re.escape(title)}"')
    case.assertRegex(plain, pointer, f'o texto não aponta para {path}, "{title}"')
    target = _skill_path(path)
    case.assertTrue(target.exists(), f'{path} não existe')
    case.assertTrue(section(target.read_text(encoding='utf-8'), title), f'{path} não tem a seção "{title}"')
