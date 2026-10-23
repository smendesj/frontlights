"""Ponteiros que resolvem (redesenho, issue 3).

Um ponteiro `arquivo, "seção"` (com ou sem crase, com ou sem `step N, `/`stage N, ` no meio) manda a sessão ler uma
seção de outro arquivo. Antes do redesenho, 69 ponteiros apontavam para parágrafos em negrito que não eram títulos, e a
sessão lia o arquivo inteiro para achar a seção. Aqui todo ponteiro precisa resolver para um título real (`##` ou
`###`) do arquivo citado; no `SKILL.md`, as regras de toda etapa são itens com o nome em negrito (`- **Fan out.**`), e
o nome conta como seção; num modelo (`templates/`), um campo da lista (`- Artifact URL and source path (…)`) também. Todo `references/<x>.md`, `templates/<x>` e `docs/<x>.md` citado precisa existir; o
`docs/roads-contract.md` vive dentro da skill desde o redesenho (issue 10); `docs/acceptance.md` e `docs/recovery.md`
vivem na raiz do repositório e contam lá.

Um título resolve o ponteiro quando é igual ao texto citado ou começa por ele seguido de `:` ou de espaço (o ponteiro
"The artifact" resolve "## The artifact: the picture of each round"); um número de passo no começo do título
("## 5. Clean up …") não conta.

Seam: o texto dos arquivos da skill, do README, do CLAUDE.md e de `docs/` (fora de `docs/redesenho/`, que descreve a
forma futura). Teste que só relata; nenhum hook o roda.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'

POINTER = re.compile(r'(?P<file>[\w./-]+\.md)`?\)?,\s+(?:(?:step|stage) \d+,\s+)?"(?P<section>[^"]{1,120})"')
NAMED = re.compile(r'(?<![\w/.-])(?P<path>(?:references|templates|docs)/[\w.-]+\.(?:md|html))')
HEADING = re.compile(r'^#{2,3} (.+?)\s*$', re.M)
RULE = re.compile(r'^- \*\*(.+?)\.\*\*', re.M)


def sources():
    files = [p for p in SKILL.rglob('*') if p.suffix in ('.md', '.py', '.html', '.cjs') and p.is_file()]
    files += [ROOT / 'README.md', ROOT / 'CLAUDE.md']
    files += [p for p in (ROOT / 'docs').glob('*.md')]
    return sorted(files)


def known_files():
    files = {p.relative_to(SKILL).as_posix(): p for p in SKILL.rglob('*') if p.is_file()}
    for path in (ROOT / 'docs').glob('*.md'):  # acceptance.md and recovery.md live at the root
        files.setdefault(f'docs/{path.name}', path)
    return files


def resolve(name, known):
    name = name.split('skills/frontlights/')[-1]
    hits = [rel for rel in known if rel == name or rel.endswith('/' + name)]
    return [known[rel] for rel in hits]


def headings(path):
    text = path.read_text(encoding='utf-8')
    found = [re.sub(r'^\d+\.\s+', '', h) for h in HEADING.findall(text)]
    if path.name == 'SKILL.md':
        found += RULE.findall(text)
    if path.parent.name == 'templates':
        found += re.findall(r'^- (.+?)(?: \(|$)', text, re.M)  # a template's field
    return found


def resolves(section, titles):
    return any(t == section or t.startswith(section + ':') or t.startswith(section + ' ') for t in titles)


def pointers():
    for path in sources():
        text = path.read_text(encoding='utf-8')
        for match in POINTER.finditer(text):
            section = re.sub(r"'\s*'", '', match.group('section'))  # a Python string split across lines
            yield path, match.group('file'), ' '.join(section.split())


class PointerTests(unittest.TestCase):
    def test_every_pointer_names_a_real_heading(self):
        known = known_files()
        blind = []
        count = 0
        for path, name, section in pointers():
            targets = resolve(name, known)
            if not targets:
                continue  # a file outside the skill (e.g. `templates/issue.md` of another tool) is not a pointer
            count += 1
            if not any(resolves(section, headings(t)) for t in targets):
                blind.append(f'{path.relative_to(ROOT).as_posix()}: {name}, "{section}"')
        self.assertGreater(count, 40)
        self.assertEqual(blind, [], 'ponteiro cego: crie o título ou corrija o ponteiro')

    def test_every_named_reference_exists(self):
        known = known_files()
        missing = []
        for path in sources():
            if path.suffix != '.md':
                continue
            for match in NAMED.finditer(path.read_text(encoding='utf-8')):
                name = match.group('path')
                if '<' in name or not resolve(name, known):
                    if '<' not in name:
                        missing.append(f'{path.relative_to(ROOT).as_posix()}: {name}')
        self.assertEqual(missing, [])

    def test_the_resolution_rule(self):
        titles = ['The artifact: the picture of each round', 'Converting a family into one issue with slices',
                  'Slices in order']
        self.assertTrue(resolves('The artifact', titles))
        self.assertTrue(resolves('Converting a family', titles))
        self.assertTrue(resolves('Slices in order', titles))
        self.assertFalse(resolves('Slices', ['Slicesxyz']))
        self.assertFalse(resolves('Which tests run when', titles))


class DevelopmentIndexTests(unittest.TestCase):
    """development.md abre com o índice "Section | Read when"; cada linha nomeia um título real."""

    def setUp(self):
        self.text = (SKILL / 'references' / 'development.md').read_text(encoding='utf-8')

    def test_the_index_lists_real_sections(self):
        head = self.text.split('\n## ', 1)[0]
        self.assertIn('| Section | Read when |', head)
        rows = re.findall(r'^\| (?!Section|---)(.+?) \|', head, re.M)
        self.assertGreaterEqual(len(rows), 7)
        titles = headings(SKILL / 'references' / 'development.md')
        for row in rows:
            with self.subTest(row=row):
                self.assertIn(row.strip('"'), titles)

    def test_the_seven_sections_the_roadmap_names_are_literal_headings(self):
        for title in ('Standing authorization and the denied operations', 'The start of stage 6', 'Slices in order',
                      'Review, checkpoints and renewal', 'Into the local main', 'The free test on the local main',
                      'The release'):
            with self.subTest(title=title):
                self.assertEqual(self.text.count(f'\n## {title}\n'), 1)

    def test_the_bold_leads_a_pointer_names_are_headings(self):
        for title in ('Which tests run when', 'Work without an issue', 'When the review is done'):
            with self.subTest(title=title):
                self.assertIn(f'\n### {title}\n', self.text)


class EntryLineTests(unittest.TestCase):
    """Cada referência de etapa diz, logo abaixo do título, quando é lida."""

    def test_each_stage_reference_opens_with_its_entry_line(self):
        for name in ('development', 'browser-testing', 'issues', 'grilling', 'closeout', 'progress-report'):
            with self.subTest(file=name):
                text = (SKILL / 'references' / f'{name}.md').read_text(encoding='utf-8')
                second = text.split('\n\n')[1]
                self.assertTrue(second.startswith('Read when:'), second[:80])


if __name__ == '__main__':
    unittest.main()
