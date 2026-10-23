"""`tests/doctext.py`, o helper único de texto dos testes de documento (redesenho, issue 10).

Seam: as funções do helper sobre textos inventados e sobre um ponteiro real do protocolo.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctext

TEXT = '# T\n\n## Um\n\nprimeiro\n\n### Um.a\n\nsub\n\n## Dois\n\nsegundo\n'


class SectionTests(unittest.TestCase):
    def test_a_section_runs_to_the_next_heading_of_its_level(self):
        self.assertEqual(doctext.flat(doctext.section(TEXT, 'Um')), 'primeiro ### Um.a sub')
        self.assertEqual(doctext.flat(doctext.section(TEXT, 'Um.a')), 'sub')
        self.assertEqual(doctext.flat(doctext.section(TEXT, 'Dois')), 'segundo')
        self.assertEqual(doctext.section(TEXT, 'Três'), '')


class PointsToTests(unittest.TestCase):
    def test_a_real_pointer_passes(self):
        doctext.assertPointsTo(self, doctext.read('skills', 'frontlights', 'docs', 'protocol.md'),
                               'references/development.md', 'The release')

    def test_a_missing_pointer_or_a_missing_section_fails(self):
        with self.assertRaises(AssertionError):
            doctext.assertPointsTo(self, 'nada aqui', 'references/development.md', 'The release')
        with self.assertRaises(AssertionError):
            doctext.assertPointsTo(self, '`references/development.md`, "Não existe"', 'references/development.md',
                                   'Não existe')


if __name__ == '__main__':
    unittest.main()
