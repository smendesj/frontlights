# Handoff — <canonical issue URL>

- Approved acceptance criteria and GitHub fetched-at timestamp:
- Authorization reference, expiration, concurrency and permitted operations:
- Monitoring arrangement, confirmation and phone-connection evidence:
- Repository path, branch, base and HEAD:
- Repository map and approved decisions:
- Files changed / diff hash / files hash:

| Command (actual argv and cwd) | Phase | Exit code / measured result | Evidence path |
| --- | --- | --- | --- |
| | red / green / broader / typecheck | | |

- TDD exception, if any, and rationale:
- Independent reviewer evidence tied to exact HEAD/diff, and the `review-gate` result (current or stale) for it:
- Teste assistido do lote (o `browser-gate`: status, `situacao`, as `roots` e o caminho do `result.json`). Fatias que mudam a tela e ainda estão no ciclo (ou ainda não começaram): liste aqui, e nada é perguntado. Só quando a pergunta está devida (a última fatia de tela fechou o ciclo e não há resposta, ou foi "Ainda não") ela vai em `checkpoint --pending teste_assistido`, e a próxima sessão começa por ela:
- Achados sem correção e destino de cada um (critério de aceitação novo na issue de origem, sub-issue ou issue de topo, com o número e o texto escrito; texto no PR nunca é destino; só ficam sem destino o ruído que não é defeito, com a evidência, e o que o usuário descartou, com a resposta literal e "descartado pelo usuário"):
- Aguardando o merge (cada PR com a issue, a branch de cabeça e a base aprovada, e desde quando; ou "não aguardar" com a resposta literal do usuário):
- Fechamento e limpeza (a lista aprovada de cada um, a resposta literal, os comandos rodados e o resultado de `closeout.py verify`, `tick-check` e `cleanup.py verify`):
- Session identity, accumulated token measurement and next-step reserve:
- Open risks/blockers and exact pending user question:
- Next concrete step:

Resume in a fresh context: reread the current GitHub issue, this file, authorization
and actual working diff. Compare machine checkpoint; surface drift before acting.
