"""Uma slice estacionada ganha, logo abaixo da caixa aberta, o sub-item "Bloqueada: <o que falta e de quem>", escrito
pela etapa 6 só por acréscimo e apagado ao destravar, antes da marcação; o fechamento continua contando a caixa como
aberta enquanto a linha existe.

Seams: `closeout.scan` com a linha "Bloqueada:" presente, e os manifestos de texto da referência da etapa 6, do
modelo de issue e do protocolo.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'
sys.path.insert(0, str(SKILL / 'scripts'))
import closeout

BLOCKED_LINE = '  - Bloqueada: falta o endpoint do produto, com a equipe do back.\n'
BODY = ('## Critérios de aceitação\n\n'
        '- [x] S1. Primeira slice.\n  - Entrega: algo.\n'
        '- [ ] S2. Segunda slice.\n  - Entrega: algo.\n  - Depende de: S1.\n' + BLOCKED_LINE +
        '- [ ] S3. Terceira slice.\n')


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def flat(text):
    return ' '.join(text.split())


def section(text, heading):
    match = re.search(r'(?m)^(#+) [^\n]*' + re.escape(heading) + r'[^\n]*\n', text)
    if not match:
        return None
    rest = text[match.end():]
    following = re.search(r'(?m)^#{1,%d} ' % len(match.group(1)), rest)
    return rest[:following.start()] if following else rest


class BlockedSliceCountTests(unittest.TestCase):
    def test_the_blocked_sub_item_is_not_a_criterion_and_the_box_stays_open(self):
        self.assertEqual(closeout.scan(BODY), ((1, 3), 0))

    def test_removing_the_line_and_ticking_the_box_closes_the_slice(self):
        released = BODY.replace(BLOCKED_LINE, '')
        self.assertEqual(closeout.scan(released), ((1, 3), 0))
        self.assertEqual(closeout.scan(released.replace('- [ ] S2.', '- [x] S2.')), ((2, 3), 0))

    def test_the_template_body_still_counts_one_box_with_the_optional_line(self):
        template = read('skills', 'frontlights', 'templates', 'issue.md')
        self.assertEqual(closeout.scan(template), ((0, 1), 0))


class BlockedSliceTextTests(unittest.TestCase):
    def test_the_reference_writes_the_line_when_parking_and_removes_it_before_the_tick(self):
        body = flat(section(read('skills', 'frontlights', 'references', 'development.md'), 'Slices in order') or '')
        for phrase in ('**A parked slice.**', '`- Bloqueada: <what is missing and from whom>`',
                       'last sub-item of its box', 'append only', 'the only removal allowed in a body',
                       'before the box is ticked', 'never a criterion', 'the reason of a blocked part'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body)

    def test_the_issue_template_shows_the_optional_sub_item(self):
        criteria = section(read('skills', 'frontlights', 'templates', 'issue.md'), 'Critérios de aceitação') or ''
        self.assertRegex(criteria, r'(?m)^  - Bloqueada:')
        self.assertIn('apagada ao destravar', flat(criteria))

    def test_the_protocol_names_the_line_as_the_only_removal(self):
        protocol = flat(read('skills', 'frontlights', 'docs', 'protocol.md'))
        self.assertIn('- Bloqueada:', protocol)
        self.assertIn('única remoção permitida', protocol)


if __name__ == '__main__':
    unittest.main()
