"""Medição de sessões do Frontlights a partir do transcript `.jsonl` do Claude Code (redesenho, issue 9, S4).

Uso: python -I evals/metrics/metrics.py <sessão.jsonl> [<outra.jsonl> ...] [--per-turn]

Lê só os arquivos que os argumentos apontam e imprime um JSON por arquivo (chave: o nome do arquivo, nunca o
caminho): turnos da conversa principal e dos subagentes, contexto por turno (média, pico, primeiro, e a série com
`--per-turn`), tokens por etapa, perguntas (`AskUserQuestion`), espera pelo usuário em minutos e erros de
ferramenta. Nada é gravado; nenhuma saída de sessão real fica neste repositório.

Contexto de um turno = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` da resposta do
modelo. Uma resposta dividida em várias linhas (mesmo `message.id`) conta uma vez. A etapa avança (nunca volta) no
primeiro sinal da etapa seguinte num comando ou numa leitura da conversa principal (`ETAPAS`); antes de qualquer
sinal, a etapa é `0-2`.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# (número da etapa, rótulo, padrão procurado na entrada de uma ferramenta da conversa principal)
ETAPAS = [
    (0, '0 update-check', re.compile(r'update-check')),
    (1, '1 abertura', re.compile(r'frontlights\.py"?\s+open\b|cleanup\.py"?\s+run\b')),
    (2, '2 inspect', re.compile(r'frontlights\.py"?\s+inspect\b')),
    (3, '3 grilling', re.compile(r'references[\\/]+grilling\.md')),
    (4, '4 issue', re.compile(r'references[\\/]+issue\.md')),
    (5, '5 slices', re.compile(r'references[\\/]+issues\.md|publish-issue')),
    (6, '6 desenvolvimento', re.compile(r'references[\\/]+development\.md|frontlights\.py"?\s+charter\b')),
    (7, '7 fechamento', re.compile(r'references[\\/]+closeout\.md|closeout\.py"?\s+(run|apply)\b')),
]
INICIO = (-1, '0-2')


def instante(entry):
    value = entry.get('timestamp')
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def contexto(usage):
    return sum(int(usage.get(k) or 0) for k in ('input_tokens', 'cache_read_input_tokens',
                                                 'cache_creation_input_tokens'))


def medir(linhas, por_turno=False):
    """As métricas de um transcript, dado como iterável de linhas JSON (uma linha inválida é ignorada)."""
    vistos = set()
    turnos, sub_turnos, perguntas, erros, saida = 0, 0, 0, 0, 0
    serie, etapas = [], {}
    etapa = INICIO
    espera, pendentes = 0.0, {}
    ferramentas = Counter()
    for linha in linhas:
        try:
            entry = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        quando = instante(entry)
        lateral = bool(entry.get('isSidechain'))
        msg = entry.get('message') if isinstance(entry.get('message'), dict) else {}
        conteudo = msg.get('content') if isinstance(msg.get('content'), list) else []
        if entry.get('type') == 'assistant':
            chave = msg.get('id') or entry.get('uuid')
            novo = chave not in vistos
            vistos.add(chave)
            usage = msg.get('usage') if isinstance(msg.get('usage'), dict) else {}
            if novo and usage:
                if lateral:
                    sub_turnos += 1
                else:
                    turnos += 1
                    ctx = contexto(usage)
                    saida += int(usage.get('output_tokens') or 0)
                    serie.append(ctx)
                    soma = etapas.setdefault(etapa[1], {'turnos': 0, 'tokens': 0})
                    soma['turnos'] += 1
                    soma['tokens'] += ctx
            for parte in conteudo:
                if not isinstance(parte, dict) or parte.get('type') != 'tool_use':
                    continue
                nome = parte.get('name') or '?'
                ferramentas[nome] += 1
                if lateral:
                    continue
                texto = json.dumps(parte.get('input') or {}, ensure_ascii=False)
                for numero, rotulo, padrao in ETAPAS:
                    if numero > etapa[0] and padrao.search(texto):
                        etapa = (numero, rotulo)
                if nome == 'AskUserQuestion':
                    perguntas += 1
                    pendentes[parte.get('id')] = quando
        elif entry.get('type') == 'user':
            for parte in conteudo:
                if isinstance(parte, dict) and parte.get('type') == 'tool_result' and parte.get('is_error'):
                    erros += 1
                if isinstance(parte, dict) and parte.get('type') == 'tool_result' and not lateral:
                    pergunta = pendentes.pop(parte.get('tool_use_id'), None)
                    if pergunta and quando:   # the answer to a question arrives as its tool result
                        espera += max((quando - pergunta).total_seconds(), 0)
    resultado = {
        'turnos': turnos, 'turnos_subagentes': sub_turnos,
        'contexto_por_turno': {'media': round(sum(serie) / len(serie)) if serie else 0,
                               'pico': max(serie, default=0), 'primeiro': serie[0] if serie else 0},
        'processado': sum(serie), 'saida': saida,
        'tokens_por_etapa': etapas,
        'perguntas': perguntas, 'espera_min': round(espera / 60, 1),
        'erros_de_ferramenta': erros, 'chamadas_de_ferramenta': sum(ferramentas.values()),
    }
    if por_turno:
        resultado['contexto_por_turno']['serie'] = serie
    return resultado


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8')
    argv = list(sys.argv[1:] if argv is None else argv)
    por_turno = '--per-turn' in argv
    arquivos = [a for a in argv if a != '--per-turn']
    if not arquivos:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    saida = {}
    for arquivo in arquivos:
        with open(arquivo, encoding='utf-8', errors='replace') as fonte:
            saida[Path(arquivo).name] = medir(fonte, por_turno)
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
