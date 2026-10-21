"""O hook opcional `UserPromptSubmit`: lembra o modelo de abrir o /frontlights quando a pessoa cita a skill em
linguagem comum, e fica calado em todo o resto. Nunca bloqueia: a saída é sempre 0.

Seam: o script `templates/frontlights-prompt-hook.py` (entrada JSON na entrada padrão, JSON de contexto na saída).
Isto prova o comportamento do script; que o Claude Code o execute em cada prompt só se confere numa sessão real.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'skills' / 'frontlights' / 'templates' / 'frontlights-prompt-hook.py'


class HookTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transcript = Path(self.tmp.name) / 'session.jsonl'
        self.transcript.write_text('{"type":"user","message":{"content":"bom dia"}}\n', encoding='utf-8')

    def run_hook(self, prompt, raw=None, **extra):
        data = {'session_id': 's', 'hook_event_name': 'UserPromptSubmit', 'prompt': prompt,
                'transcript_path': str(self.transcript), 'cwd': self.tmp.name, **extra}
        # raw UTF-8 bytes on stdin, as the host sends them: the console code page must not be used to read them
        sent = raw.encode('utf-8') if raw is not None else json.dumps(data, ensure_ascii=False).encode('utf-8')
        done = subprocess.run([sys.executable, str(HOOK)], input=sent, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, b'')
        text = done.stdout.decode('utf-8')
        return json.loads(text) if text.strip() else None

    def reminded(self, prompt, **extra):
        return self.run_hook(prompt, **extra) is not None


class ReminderTests(HookTestCase):
    def test_a_plain_request_for_the_skill_gets_the_reminder_as_additional_context(self):
        for prompt in ('frontlights ataque a issue 123', 'Frontlights ativar! Vamos atuar no roads.', 'ativar o FRONTLIGHTS',
                       'vamos usar o frontlights, retomar a família #123', 'Agir com frontlights, ele tem toda permissão.',
                       'frontlights, por favor.'):
            with self.subTest(prompt=prompt):
                output = self.run_hook(prompt)
                self.assertEqual(output['hookSpecificOutput']['hookEventName'], 'UserPromptSubmit')
                context = output['hookSpecificOutput']['additionalContext']
                self.assertIn('/frontlights', context)
                self.assertIn('etapa 1', context)
                self.assertIn('resumo', context)
                self.assertNotIn('issues do RoadS', context)   # issue 65: no RoadS question at the opening
                self.assertIn('mesmo nome', context)    # says it is the plugin, not a session or project of the same name

    def test_a_prompt_that_does_not_mention_it_gets_nothing(self):
        for prompt in ('bom dia', 'rode os testes', 'retomar a família #123', '', '   '):
            with self.subTest(prompt=prompt):
                self.assertFalse(self.reminded(prompt))

    def test_the_command_itself_needs_no_reminder(self):
        for prompt in ('/frontlights retomar a família #123', '  /Frontlights', '/frontlights',
                       '/frontlights:frontlights ataque a issue 5', '/frontlights ataque, use o frontlights'):
            with self.subTest(prompt=prompt):
                self.assertFalse(self.reminded(prompt))

    def test_a_path_a_file_name_or_an_identifier_is_not_a_request(self):
        for prompt in ('veja o arquivo .frontlights/config.json', 'abra scripts/frontlights.py', 'rode frontlights.py update-check',
                       'cd <pasta>/Frontlights', r'C:\algum\Frontlights\README.md', 'o dir .frontlights-old',
                       r'cd C:\x\frontlights', 'use meu-frontlights agora', 'o pacote frontlights-plugin', 'veja frontlights/docs/x.md',
                       'use o /frontlights agora'):
            with self.subTest(prompt=prompt):
                self.assertFalse(self.reminded(prompt))

    def test_a_session_that_already_opened_the_skill_is_left_alone(self):
        for marker in ('<command-name>/frontlights</command-name>', 'Localize `skills/frontlights/SKILL.md` do Frontlights'):
            self.transcript.write_text('{"type":"user","message":{"content":"' + marker.replace('"', "'") + '"}}\n', encoding='utf-8')
            with self.subTest(marker=marker):
                self.assertFalse(self.reminded('frontlights, continue'))

    def test_the_marker_is_found_even_deep_in_a_large_transcript_and_across_a_chunk_edge(self):
        marker = 'skills/frontlights/SKILL.md'
        for pad in (10, 1024 * 1024 - 5, 3 * 1024 * 1024):
            self.transcript.write_text('x' * pad + marker + 'y' * 50, encoding='utf-8')
            with self.subTest(pad=pad):
                self.assertFalse(self.reminded('frontlights, continue'))

    def test_a_transcript_path_with_accents_is_read_as_utf8_not_as_the_console_code_page(self):
        folder = Path(self.tmp.name) / 'João Ávila'
        folder.mkdir()
        path = folder / 'sessão.jsonl'
        path.write_text('{"type":"user","message":{"content":"skills/frontlights/SKILL.md"}}\n', encoding='utf-8')
        self.assertFalse(self.reminded('frontlights, continue', transcript_path=str(path)))
        self.assertFalse(self.reminded('frontlights, continue', cwd=str(folder), transcript_path=str(path)))

    def test_the_marker_in_its_json_escaped_windows_form_counts(self):
        self.transcript.write_text(r'{"x":"p\\skills\\frontlights\\SKILL.md"}' + '\n', encoding='utf-8')
        self.assertFalse(self.reminded('frontlights, continue'))

    def test_a_skill_file_saved_with_a_byte_order_mark_is_still_the_skills_own_repository(self):
        repo = Path(self.tmp.name) / 'bom'
        (repo / 'skills' / 'frontlights').mkdir(parents=True)
        (repo / 'skills' / 'frontlights' / 'SKILL.md').write_text('---\nname: frontlights\n---\n', encoding='utf-8-sig')
        self.assertFalse(self.reminded('frontlights ataque', cwd=str(repo)))

    def test_a_missing_or_unreadable_transcript_still_reminds(self):
        self.assertTrue(self.reminded('frontlights ataque', transcript_path=str(Path(self.tmp.name) / 'none.jsonl')))
        self.assertTrue(self.reminded('frontlights ataque', transcript_path=None))

    def test_the_skills_own_repository_is_left_alone(self):
        repo = Path(self.tmp.name) / 'repo'
        skill = repo / 'skills' / 'frontlights'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: frontlights\ndescription: x\n---\n# Frontlights\n', encoding='utf-8')
        self.assertFalse(self.reminded('frontlights ataque', cwd=str(repo)))
        (skill / 'SKILL.md').write_text('---\nname: other\n---\n', encoding='utf-8')
        self.assertTrue(self.reminded('frontlights ataque', cwd=str(repo)))
        self.assertTrue(self.reminded('frontlights ataque', cwd=str(skill)))   # inside the skill, not the repository root

class NeverBlocksTests(HookTestCase):
    def test_garbage_on_the_input_is_exit_zero_with_no_output(self):
        for raw in ('', 'not json', '[1, 2]', '{"prompt": 5}', '{"prompt": null}', '{}', '[' * 200000):
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_hook(None, raw=raw))


class HookDocumentationTests(unittest.TestCase):
    def test_the_readme_and_the_security_notes_describe_the_opt_in_hook(self):
        readme = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
        for phrase in ('frontlights-prompt-hook.py', 'UserPromptSubmit', 'Início por linguagem natural', 'settings.json'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        security = ' '.join((ROOT / 'skills' / 'frontlights' / 'docs' / 'security.md').read_text(encoding='utf-8').split())
        self.assertIn('frontlights-prompt-hook.py', security)
        self.assertIn('O Frontlights não instala hook nenhum.', security)
        self.assertIn('é um modelo que o usuário copia para o `~/.claude/hooks/`', security)
        self.assertNotIn('é o único hook que o Frontlights instala', security)
        self.assertIn('há um hook **opcional**, que a skill não instala', readme)

    def test_the_skill_description_names_the_plain_language_triggers(self):
        text = (ROOT / 'skills' / 'frontlights' / 'SKILL.md').read_text(encoding='utf-8')
        head = text.split('---')[1]
        for phrase in ('frontlights, ataque a issue', 'ativar frontlights', 'with or without the slash', 'same name'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, head)
        self.assertIn('disable-model-invocation: false', head)
        self.assertIn('not a session or a project of the same name', text.split('---', 2)[2])

if __name__ == '__main__':
    unittest.main()
