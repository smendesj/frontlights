"""Fonte única das regras da etapa 6 e descrição curta da skill (refatoração dos textos, melhorias 4 e 6).

Cada regra que a etapa 6 aplica (os merges cobertos, as operações negadas, os três portões, a pergunta da release)
vive num lugar só, `references/development.md`; os outros textos (SKILL.md, docs, README, CLAUDE.md) apontam para
ela. Uma cópia literal num segundo arquivo volta a ser pega aqui. A descrição do frontmatter, carregada em toda
sessão de todo projeto, fica curta: diz o que a skill é e traz os gatilhos.

Seam: o texto dos arquivos, achatado pelos espaços (`flat`), como nos outros testes de texto.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / 'skills' / 'frontlights'
SOURCE = SKILL_DIR / 'references' / 'development.md'
FILES = sorted(SKILL_DIR.rglob('*.md')) + [ROOT / 'README.md', ROOT / 'CLAUDE.md']

# fragmento que só a fonte pode ter -> o que ele marca
SINGLE = {
    'into the local main by `homolog sync`': 'a lista dos merges cobertos',
    'turning on a setting, key or flag in production': 'a lista das operações negadas',
    '`{"suite_gate": "current", "review_gate": "current", "browser_gate": "answered"}`': 'os três portões',
    'Lançar a release com as issues': 'a pergunta da release',
    '"Mesclar a PR #<n> em <base>?"': 'a pergunta do merge da release',
    '"Dar destino pela escada"': 'a pergunta do limite de rodadas da revisão',
    '**Run the whole suite on the local main.**': 'a suíte inteira da release na main local (issue 52, S3)',
}

# cópias em português que deram lugar a um ponteiro
GONE = {
    'chave ou flag em produção': 'a lista das negadas copiada em português',
    'na branch da prévia pelo `serve preview refresh`': 'a lista dos merges cobertos copiada em português',
    '`review-gate` `current` for it': 'os portões repetidos fora da fonte',
    '`review-gate` em dia e `browser-gate` respondido': 'os portões repetidos em português',
    '"full_suite": "green"': 'o portão da suíte inteira, que virou suite_gate (issue 52)',
    'full_suite: green': 'o portão da suíte inteira copiado em português (issue 52)',
}

DESCRIPTION_MAX_WORDS = 80


def flat(text):
    return ' '.join(text.split())


def texts():
    return {path: flat(path.read_text(encoding='utf-8')) for path in FILES if path.exists()}


class SingleSourceTests(unittest.TestCase):
    def test_each_rule_lives_once_in_development(self):
        found = texts()
        for fragment, rule in SINGLE.items():
            with self.subTest(rule=rule):
                homes = {path.relative_to(ROOT).as_posix(): text.count(fragment)
                         for path, text in found.items() if fragment in text}
                self.assertEqual(homes, {SOURCE.relative_to(ROOT).as_posix(): 1},
                                 f'{rule} deve aparecer uma vez, só em references/development.md')

    def test_portuguese_copies_point_to_the_source(self):
        found = texts()
        for fragment, copy in GONE.items():
            with self.subTest(copy=copy):
                homes = [path.relative_to(ROOT).as_posix() for path, text in found.items() if fragment in text]
                self.assertEqual(homes, [], f'{copy} deve virar um ponteiro para references/development.md')


class DescriptionTests(unittest.TestCase):
    def test_description_is_short_and_keeps_the_triggers(self):
        front = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8').split('---')[1]
        match = re.search(r'^description: (.*)$', front, re.M)
        self.assertIsNotNone(match)
        description = match.group(1)
        self.assertLessEqual(len(description.split()), DESCRIPTION_MAX_WORDS)
        for trigger in ('frontlights, ataque a issue', 'ativar frontlights', 'with or without the slash',
                        'not a session or project of the same name'):
            self.assertIn(trigger, description)


class ReleaseAdoptionTextTests(unittest.TestCase):
    """Issue 54, S4: a regra da release manda adotar com `--from` a suíte inteira verde, limpa e de mesma árvore de
    uma issue da release, e rodar nos outros casos; o `protocol.md` descreve `adoptedFrom`. A regra vive só em
    `references/development.md`."""

    COMMAND = ('homolog suite --release --mode full --from <record> --base <base> --root <main worktree> '
               '--config <config>')

    def test_the_release_adopts_a_green_run_of_the_same_tree(self):
        text = flat(SOURCE.read_text(encoding='utf-8'))
        item = text.split('**Run the whole suite on the local main.**')[1].split('**Offer it.**')[0]
        for phrase in (self.COMMAND, 'which runs nothing',
                       'has a record of the whole suite that is green (exit code 0, no timeout), ran on a clean '
                       'tree, and whose commit tree (`<head>^{tree}`) is the tree of the tip of the local main',
                       "The session gives the path of the record (the `suite.json` of an issue, in that issue's "
                       'worktree, or the per-tip record `release/suite-<sha>.json` of another release) and never '
                       'searches for one',
                       'before the cleanup of the worktrees (stage 7)',
                       'A refusal writes nothing.',
                       'A refusal of the record (an impact record, a red or timed-out run, a run with a diff or a '
                       'file outside the commit, a head the repository does not know, another commit tree or other '
                       "evidence files than the tip's) means the session runs the suite as below",
                       "A refusal of the place (a tip that is not the local main's, or a dirty main) is fixed first, "
                       'by going to the tip or by committing or discarding the change, and the adoption is tried again',
                       '`--from` with `--argv` or `--timeout-seconds` is a mistake of the call, redone without them',
                       'Without such a record, the session runs the suite as below',
                       'then `release-plan` again, as after a run'):
            with self.subTest(file='development.md', phrase=phrase):
                self.assertIn(phrase, item)
        adopt, run = item.find(self.COMMAND), item.find('In the main worktree, on the local main, run')
        self.assertTrue(0 <= adopt < run, 'a adoção vem antes da execução da suíte inteira')

    def test_the_protocol_describes_adopted_from(self):
        text = flat((SKILL_DIR / 'docs' / 'protocol.md').read_text(encoding='utf-8'))
        for phrase in ('com `homolog suite --release --mode full --from <registro>`, o registro da release é '
                       'adotado sem rodar',
                       'guarda a execução original e a evidência atual da main local',
                       '`adoptedFrom` {path, head, tree, adoptedAt} nomeia a origem',
                       'os juízes o leem como um rodado',
                       'copia o registro da origem inteiro (warnings incluídos), menos base, head e evidence'):
            with self.subTest(file='protocol.md', phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_adoption_rule_lives_once_in_development(self):
        references = {path.relative_to(ROOT).as_posix(): flat(path.read_text(encoding='utf-8')).count(
            'homolog suite --release --mode full --from')
            for path in sorted((SKILL_DIR / 'references').glob('*.md'))}
        homes = {path: count for path, count in references.items() if count}
        self.assertEqual(homes, {SOURCE.relative_to(ROOT).as_posix(): 1},
                         'a adoção com --from deve aparecer só em references/development.md entre as referências')
        rule = 'whose commit tree (`<head>^{tree}`) is the tree of the tip of the local main'
        homes = {path.relative_to(ROOT).as_posix(): text.count(rule) for path, text in texts().items() if rule in text}
        self.assertEqual(homes, {SOURCE.relative_to(ROOT).as_posix(): 1},
                         'a regra da adoção deve aparecer uma vez, só em references/development.md')


if __name__ == '__main__':
    unittest.main()
