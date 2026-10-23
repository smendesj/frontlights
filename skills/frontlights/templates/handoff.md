# Passagem da issue #<n>

Escrita em `.frontlights/issues/<n>/handoff.md` da worktree principal a cada fronteira de janela, antes de
`frontlights.py checkpoint`. Só ponteiros: o que já está na issue, num commit ou num registro vai pelo caminho. Segredos mascarados. O GitHub vence esta passagem.

- Issue: <URL>
- Charter: `.frontlights/authorization.json` (validade, operações, `branch_prefix`)
- Checkpoints: `.frontlights/issues/<n>/checkpoint*.json`; a janela nova roda `frontlights.py resume --issue <n>`
- Branch, worktree e HEAD: <branch da issue>, <pasta>, <sha curto>
- Janela ANTES: `.frontlights/issues/<n>/browser/window.json` aberta (`serve.py window attach`) ou "fechada"
- Plano resumido: uma linha por slice (S<k>, entrega, estado)
- Slice em andamento: S<k> (o `--slice` do checkpoint), a worktree e a branch dela
- Slices fechadas: S<k>, commit, evidência (`browser-gate`, o roteiro sem tela `.frontlights/issues/<n>/walkthroughs/S<k>.md`; `review-gate` só com revisão, cada rodada com o HEAD e `sérios/médios/baixos`)
- Merge na main local (`merge-local-main-<data-hora>.json`, com o `authorize` de `merge_into_local_main` e o bundle) ou "ainda não"
- Teste livre na main local: janela fechada ou pulado, `serve stop`; sem tela, no terminal: os comandos dados e a resposta literal; o lote `.frontlights/issues/<n>/teste-livre-cas.md` ou "sem correções"
- Release: `release/pending.json` ou `release/current.json`; Aguardando o merge da PR #<n>, ou "não aguardar" com a resposta literal do usuário
- Fechamento e limpeza: `.frontlights/closeout-<data>.md` e `.frontlights/cleanup-<data>.json`
- Achados sem correção e destino de cada um: critério novo da issue de origem ou issue de topo, com o número; "descartado pelo usuário" com a resposta literal
- Pergunta pendente e resposta literal: <a pergunta exata, ou a resposta do usuário palavra por palavra>
- Próximo passo: <o mesmo `--next-step` do checkpoint>
