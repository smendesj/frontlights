"""Leitura do `SKILL.md` por parte, para os testes de texto (redesenho, issue 3).

O `SKILL.md` virou roteiro: um cabeçalho, as regras de toda etapa como itens com o nome em negrito
(`- **Fan out.** …`), as etapas como uma lista numerada (`6. **Bounded development.** …`) e a tabela de ponteiros.
Os testes que antes cortavam o texto em `## 6.` e `## 7.` pedem a parte aqui.

Cada função devolve o texto cru da parte; `flat` achata os espaços, como nos outros testes.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'skills' / 'frontlights' / 'SKILL.md'


def text():
    return PATH.read_text(encoding='utf-8')


def flat(value):
    return ' '.join(value.split())


def _between(start, end):
    body = text()
    if start not in body:
        return ''
    after = body.split(start, 1)[1]
    return after.split(end, 1)[0] if end in after else after


def header():
    """O que vem antes de `## Rules in every stage` (frontmatter incluído)."""
    return text().split('\n## Rules', 1)[0]


def rules():
    return _between('\n## Rules in every stage\n', '\n## Stages\n')


def rule(name):
    """O item da regra `name` (sem o ponto final do negrito), até o item seguinte."""
    match = re.search(rf'^- \*\*{re.escape(name)}\.\*\*.*?(?=^- \*\*|^## |\Z)', rules(), re.M | re.S)
    return match.group(0) if match else ''


def stages():
    return _between('\n## Stages\n', '\n## Pointers\n')


def stage(number):
    """O item da etapa `number` da lista numerada, até a etapa seguinte."""
    match = re.search(rf'^{number}\. \*\*.*?(?=^\d+\. \*\*|\Z)', stages(), re.M | re.S)
    return match.group(0) if match else ''


def pointers():
    """A tabela `## Pointers`."""
    return text().split('\n## Pointers\n', 1)[1] if '\n## Pointers\n' in text() else ''
