# Handoff — <canonical issue URL>

- Approved acceptance criteria and GitHub fetched-at timestamp:
- Authorization reference, expiration, concurrency and permitted operations:
- Monitoring arrangement, confirmation and phone-connection evidence:
- Repository path, branch, base and HEAD:
- Merge na main local (a branch da issue é cortada da main local e nunca enviada; a main local trazida para a branch da issue; o portão, o `browser-gate` respondido ou `not_needed`, com a evidência; os testes e a revisão só quando rodaram; a saída do `authorize` para `merge_into_local_main`; o commit do merge na main local):
- Teste livre na main local (só numa issue com tela: a janela aberta sem pergunta depois do merge na main local e do bundle, o `serve start` na worktree principal, o horário em que a janela fechada acordou a sessão, o `serve stop`; "pulado" quando o usuário fechou a janela logo que ela abriu; só depois dele vem a oferta da release):
- Repository map and approved decisions:
- Files changed / diff hash / files hash:
- Slice em andamento (id da caixa, também em `checkpoint --slice`, com a worktree e a branch dela) e slices já marcadas com evidência (id, commit, worktree e comandos de cada uma):

| Command (actual argv and cwd) | Phase | Exit code / measured result | Evidence path |
| --- | --- | --- | --- |
| | red / green / broader / typecheck | | |

- TDD exception, if any, and rationale ("só com teste assistido" when the user asked for it: no test written or run):
- Independent review, only when the user asked for one: evidence tied to exact HEAD/diff, the `review-gate` result (current or stale) for it, and each round (its HEAD and its counts `sérios/médios/baixos`):
- Roteiros rodados sem tela (o `browser-gate` em `not_needed`, ou a caixa com persona `sem tela`): uma linha por caixa, com o arquivo `.frontlights/issues/<n>/walkthroughs/S<k>.md`; caixa sem arquivo segura o merge na main local:

| Caixa | Antes | Depois | Arquivo |
| --- | --- | --- | --- |
| | | | |

- Teste assistido da issue (o `browser-gate`: status, `situacao`, as `roots` e o caminho do `result.json`). Fatias que mudam a tela e ainda estão no ciclo (ou ainda não começaram): liste aqui, e nada é perguntado. Só quando a pergunta está devida (a última fatia de tela fechou o ciclo e não há resposta, ou foi "Ainda não") ela vai em `checkpoint --pending teste_assistido`, e a próxima sessão começa por ela:
- Achados sem correção e destino de cada um (critério de aceitação novo na issue de origem ou issue de topo, nunca sub-issue nova, com o número e o texto escrito; texto no PR nunca é destino; só ficam sem destino o ruído que não é defeito, com a evidência, e o que o usuário descartou, com a resposta literal e "descartado pelo usuário"):
- Release (a saída do `release-plan`: issues acumuladas e branch de release; a suíte inteira na ponta da main local só quando o usuário a pediu, com o comando, a contagem e a saída; a resposta literal à oferta; Aguardando o merge da PR única, com as issues, a branch de cabeça, a base aprovada e desde quando, ou "não aguardar" com a resposta literal do usuário; o `merge-status` e o `git pull --ff-only` depois do merge):
- Fechamento e limpeza (a lista aprovada do fechamento e a resposta literal; da limpeza, que roda antes e sem pergunta, o plano, os comandos rodados e a resposta de cada candidato com `ask`; os comandos rodados e o resultado de `closeout.py verify`, `tick-check` e `cleanup.py verify`):
- Session identity, accumulated token measurement and next-step reserve:
- Open risks/blockers and exact pending user question:
- Next concrete step:

Resume in a fresh context: reread the current GitHub issue, this file, authorization
and actual working diff. Compare machine checkpoint; surface drift before acting.
