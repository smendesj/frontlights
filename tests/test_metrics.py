"""Medição das sessões (redesenho, issue 9, S4): `evals/metrics/metrics.py` sobre um `.jsonl` sintético.

Seam: a função `medir` e o script por subprocesso, sobre linhas montadas aqui (nenhuma sessão real, nenhum caminho
de máquina). O script só lê o arquivo que o argumento aponta e imprime o JSON.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'evals' / 'metrics' / 'metrics.py'
sys.path.insert(0, str(SCRIPT.parent))
import metrics  # noqa: E402


def assistant(mid, minute, ctx, tools=(), side=False, out=10):
    content = [{'type': 'tool_use', 'id': tid, 'name': name, 'input': data} for tid, name, data in tools]
    return {'type': 'assistant', 'isSidechain': side, 'timestamp': f'2000-01-01T10:{minute:02d}:00Z',
            'message': {'id': mid, 'usage': {'input_tokens': 1, 'cache_read_input_tokens': ctx - 1,
                                             'cache_creation_input_tokens': 0, 'output_tokens': out},
                        'content': content}}


def result(tid, minute, error=False):
    return {'type': 'user', 'timestamp': f'2000-01-01T10:{minute:02d}:00Z',
            'message': {'content': [{'type': 'tool_result', 'tool_use_id': tid, 'is_error': error}]}}


LINES = [
    assistant('m1', 0, 1000, [('t1', 'Bash', {'command': 'python frontlights.py update-check'})]),
    result('t1', 1),
    assistant('m2', 2, 2000, [('t2', 'Read', {'file_path': 'skills/frontlights/references/grilling.md'})]),
    result('t2', 2),
    assistant('m2', 2, 2000),   # the same response split in two lines counts once
    assistant('m3', 3, 3000, [('t3', 'AskUserQuestion', {'questions': []})]),
    result('t3', 13),           # ten minutes waiting for the answer
    assistant('m4', 14, 5000, [('t4', 'Read', {'file_path': 'skills\\frontlights\\references\\development.md'})]),
    result('t4', 14, error=True),
    assistant('s1', 15, 9000, side=True),
    assistant('m5', 16, 6000, [('t5', 'Read', {'file_path': 'skills/frontlights/references/grilling.md'})]),
    'linha que não é JSON',
]


class MetricsTests(unittest.TestCase):
    def measure(self, por_turno=False):
        return metrics.medir((json.dumps(x) if isinstance(x, dict) else x for x in LINES), por_turno)

    def test_turns_context_questions_wait_and_errors(self):
        m = self.measure()
        self.assertEqual((m['turnos'], m['turnos_subagentes']), (5, 1))
        self.assertEqual(m['contexto_por_turno'], {'media': 3400, 'pico': 6000, 'primeiro': 1000})
        self.assertEqual((m['processado'], m['saida']), (17000, 50))
        self.assertEqual((m['perguntas'], m['espera_min'], m['erros_de_ferramenta']), (1, 10.0, 1))

    def test_tokens_by_stage_only_move_forward(self):
        stages = self.measure()['tokens_por_etapa']
        self.assertEqual(stages, {'0-2': {'turnos': 1, 'tokens': 1000},
                                  '0 update-check': {'turnos': 1, 'tokens': 2000},
                                  '3 grilling': {'turnos': 2, 'tokens': 8000},
                                  '6 desenvolvimento': {'turnos': 1, 'tokens': 6000}})

    def test_the_series_only_on_request(self):
        self.assertNotIn('serie', self.measure()['contexto_por_turno'])
        self.assertEqual(self.measure(True)['contexto_por_turno']['serie'], [1000, 2000, 3000, 5000, 6000])

    def test_the_script_prints_by_file_name_never_the_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sessao-sintetica.jsonl'
            path.write_text('\n'.join(json.dumps(x) if isinstance(x, dict) else x for x in LINES), encoding='utf-8')
            done = subprocess.run([sys.executable, '-I', str(SCRIPT), str(path)], capture_output=True,
                                  encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual(list(printed), ['sessao-sintetica.jsonl'])
        self.assertNotIn(folder, done.stdout)
        self.assertEqual(printed['sessao-sintetica.jsonl']['turnos'], 5)

    def test_without_a_file_it_says_how_to_use(self):
        done = subprocess.run([sys.executable, '-I', str(SCRIPT)], capture_output=True, encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn('metrics.py', done.stderr)

    def test_no_session_output_is_versioned_with_the_script(self):
        self.assertEqual(sorted(p.name for p in SCRIPT.parent.iterdir() if p.name != '__pycache__'), ['metrics.py'])


if __name__ == '__main__':
    unittest.main()
