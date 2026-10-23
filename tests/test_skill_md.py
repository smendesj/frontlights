"""O `SKILL.md` roteiro (redesenho, issue 3): comandos reais e teto de tamanho.

O `SKILL.md` fica no contexto em todos os turnos. Ele cita os comandos pela forma curta `<script>.py <verbo>`
(`frontlights.py open`, `homolog.py release plan`, `serve.py window brief`) e por alguns verbos soltos que o texto
já ligou a um script (`homolog sync`, `release go`, `stamp --check`). Todo verbo, subverbo e flag citado precisa
existir no `--help` real do script: uma flag adivinhada no roteiro vira erro de ferramenta em toda sessão. Comando que
ainda não existe fica na forma manual até a issue que o entrega.

O teto é catraca: `CEILING` é o número de palavras do dia em que o arquivo entrou (meta `GOAL`) e só desce; quem
encolhe o `SKILL.md` baixa o número no mesmo commit. A contagem é a do `wc -w` (palavras separadas por espaço).

Seam: o texto do `SKILL.md` e a saída de `--help` dos scripts. Teste que só relata; nenhum hook o roda.
"""
import re
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skilltext  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'frontlights' / 'scripts'

CEILING = 2000  # folga para a onda 4 (regra Windows da issue 9 e as linhas das etapas 3, 5 e 7); a issue 10 desce à contagem do dia
GOAL = 1700     # meta da proposta do redesenho, seção 3

# verbos soltos que o texto liga a um script: palavra -> o comando do script que a recebe
BARE = {'homolog': ['frontlights.py', 'homolog'], 'release': ['homolog.py', 'release'],
        'stamp': ['frontlights.py', 'stamp']}
SPAN = re.compile(r'`([^`]+)`')
WORD = re.compile(r'^[a-z][a-z-]*$')


@lru_cache(maxsize=None)
def usage(*argv):
    done = subprocess.run([sys.executable, str(SCRIPTS / argv[0]), *argv[1:], '--help'], capture_output=True,
                          encoding='utf-8', errors='replace', timeout=60)
    return done.stdout + done.stderr


def choices(text):
    found = set()
    for group in re.findall(r'\{([a-z,-]+)\}', text):
        found.update(group.split(','))
    return found


def commands():
    """Cada citação de comando do corpo: (o texto citado, a lista de tokens)."""
    body = skilltext.text().split('---', 2)[2]
    for span in SPAN.findall(body):
        tokens = span.split()
        if not tokens:
            continue
        head = tokens[0]
        if head.endswith('.py') and (SCRIPTS / head).is_file():
            yield span, [head] + tokens[1:]
        elif head in BARE and len(tokens) > 1 and (WORD.match(tokens[1]) or tokens[1].startswith('--')):
            yield span, BARE[head] + tokens[1:]


def check(tokens):
    """O que não existe no `--help`: uma lista de mensagens, vazia quando o comando é real."""
    script, rest = tokens[0], tokens[1:]
    path = [script]
    problems = []
    verbs = [t for t in rest if WORD.match(t)]
    flags = [t for t in rest if t.startswith('--')]
    for verb in verbs:
        known = choices(usage(*path))
        if not known:
            break  # the command takes no further verb; the word is an argument
        if verb not in known:
            problems.append(f'{" ".join(path)}: verbo {verb!r} fora de {sorted(known)}')
            return problems
        path.append(verb)
    help_text = usage(*path)
    for flag in flags:
        if not re.search(rf'(?<![\w-]){re.escape(flag)}(?![\w-])', help_text):
            problems.append(f'{" ".join(path)}: flag {flag} fora do --help')
    return problems


class SkillCommandTests(unittest.TestCase):
    def test_every_cited_command_exists_in_the_help(self):
        cited = list(commands())
        self.assertGreater(len(cited), 15)
        problems = []
        for span, tokens in cited:
            for problem in check(tokens):
                problems.append(f'`{span}`: {problem}')
        self.assertEqual(problems, [])

    def test_the_check_catches_a_guessed_verb_and_flag(self):
        self.assertTrue(check(['frontlights.py', 'publish-issue']))
        self.assertTrue(check(['cleanup.py', 'run', '--from-everywhere']))
        self.assertEqual(check(['cleanup.py', 'run', '--from-authorizations', '--yes']), [])
        self.assertEqual(check(['homolog.py', 'release', 'landed']), [])


class SkillSizeTests(unittest.TestCase):
    def test_the_skill_stays_under_its_ceiling(self):
        words = len(skilltext.text().split())
        self.assertLessEqual(words, CEILING, f'SKILL.md tem {words} palavras; o teto é {CEILING} (meta {GOAL})')
        self.assertLessEqual(GOAL, CEILING)

    def test_the_skill_has_the_three_parts_and_portuguese_first(self):
        text = skilltext.text()
        for heading in ('## Rules in every stage', '## Stages', '## Pointers'):
            with self.subTest(heading=heading):
                self.assertEqual(text.count(f'\n{heading}\n'), 1)
        self.assertTrue(skilltext.rules().strip().startswith('- **Portuguese.**'))
        for number in range(8):
            with self.subTest(stage=number):
                self.assertTrue(skilltext.stage(number))


if __name__ == '__main__':
    unittest.main()
