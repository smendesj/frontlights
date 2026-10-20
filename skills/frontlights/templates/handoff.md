# Handoff — <canonical issue URL>

- Approved acceptance criteria and GitHub fetched-at timestamp:
- Authorization reference, expiration, concurrency and permitted operations:
- Monitoring arrangement, confirmation and phone-connection evidence:
- Repository path, branch, base and HEAD:
- Merge na main local (a branch da issue é cortada da main local e nunca enviada; os três portões com a evidência de cada um: `suite-gate` `current` no tip da branch da issue (e a segunda rodada sozinha, se houve `--concurrent`), `review-gate` atual, `browser-gate` respondido ou `not_needed`; a saída do `authorize` para `merge_into_local_main`; o commit do merge na main local):
- Repository map and approved decisions:
- Files changed / diff hash / files hash:
- Slice em andamento (id da caixa, também em `checkpoint --slice`, com a worktree e a branch dela) e slices já marcadas com evidência (id, commit, worktree e comandos de cada uma):

| Command (actual argv and cwd) | Phase | Exit code / measured result | Evidence path |
| --- | --- | --- | --- |
| | red / green / broader / typecheck | | |

- TDD exception, if any, and rationale:
- Independent reviewer evidence tied to exact HEAD/diff, and the `review-gate` result (current or stale) for it, and each round (its HEAD and its counts `sérios/médios/baixos`):
- Teste assistido da issue (o `browser-gate`: status, `situacao`, as `roots` e o caminho do `result.json`). Fatias que mudam a tela e ainda estão no ciclo (ou ainda não começaram): liste aqui, e nada é perguntado. Só quando a pergunta está devida (a última fatia de tela fechou o ciclo e não há resposta, ou foi "Ainda não") ela vai em `checkpoint --pending teste_assistido`, e a próxima sessão começa por ela:
- Achados sem correção e destino de cada um (critério de aceitação novo na issue de origem ou issue de topo, nunca sub-issue nova, com o número e o texto escrito; texto no PR nunca é destino; só ficam sem destino o ruído que não é defeito, com a evidência, e o que o usuário descartou, com a resposta literal e "descartado pelo usuário"):
- Release (a saída do `release-plan`: issues acumuladas, branch de release e o `fullSuite` do `release-plan`, a suíte inteira na ponta da main local (com os módulos pulados e os registros de impacto de onde vieram, quando ela rodou só o complemento: `covered`), e a adoção da suíte inteira, quando houve (`adoptedFrom`: o registro de origem, a ponta e a árvore); um tempo esgotado e a nova rodada com `--timeout-seconds`, quando houve; a resposta literal à oferta; a saída do `suite-gate --release --head <sha>` antes da pergunta do merge; Aguardando o merge da PR única, com as issues, a branch de cabeça, a base aprovada e desde quando, ou "não aguardar" com a resposta literal do usuário; o `merge-status` e o `git pull --ff-only` depois do merge):
- Fechamento e limpeza (a lista aprovada do fechamento e a resposta literal; da limpeza, que roda antes e sem pergunta, o plano, os comandos rodados e a resposta de cada candidato com `ask`; os comandos rodados e o resultado de `closeout.py verify`, `tick-check` e `cleanup.py verify`):
- Session identity, accumulated token measurement and next-step reserve:
- Open risks/blockers and exact pending user question:
- Next concrete step:

Resume in a fresh context: reread the current GitHub issue, this file, authorization
and actual working diff. Compare machine checkpoint; surface drift before acting.
