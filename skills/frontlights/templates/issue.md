# <Um resultado observável>

## Problema

<O que acontece hoje, para quem, a dor observada e a fonte (observação, issue ou pedido), com data.>

## Solução

<O que passa a acontecer, do ponto de vista de quem usa, e a medida de sucesso.>

## Decisões de implementação

- Abordagem: <a escolhida, numa frase>; alternativas rejeitadas: <alternativa — motivo>; <alternativa — motivo>
- Convenções: <padrão seguido, pelo nome>; quebra aprovada: <qual — motivo e custo>, ou nenhuma
- Contratos, esquema e arquitetura: <interfaces, campos, migração>, ou não se aplica

A prosa não cita arquivo nem trecho de código, porque envelhece (os caminhos ficam na propriedade e no rastreio); a exceção é um trecho de protótipo que registra a decisão melhor que a prosa, cortado ao essencial e dito como tal.

## Decisões de teste

- Os seams sob teste, confirmados na etapa 4: <seam — comportamento de aceitação observado nele>
- Arte prévia: <teste parecido que já existe no código>
- Comandos: <regressão> · <integração> · <checagem de tipos>

Só comportamento observável pela interface pública; só os seams acima recebem testes, e seam ausente ou errado volta ao usuário.

## Fora de escopo

- <O que foi recusado — motivo>

## Critérios de aceitação

As slices: uma caixa por slice, em ordem de dependência, bloqueadoras primeiro; no máximo cinco `S<n>` (a sexta vira issues de topo ligadas por `--blocked-by`, nunca sub-issue; a slice de um achado não conta). Prefactoring é a primeira slice; refatoração larga é expandir, migrar por lotes e contrair, um passo por slice. Todo critério falha no commit de partida. No roteiro, a persona é rótulo (`conta 1`, `conta 2`, usuário de teste criado ou `sem tela`), nunca login, e o antes é o que o reconhecimento gravou no commit de partida.

- [ ] S1. <resultado observável de ponta a ponta desta slice>
  - Entrega: <o que dá para demonstrar quando ela termina>
  - Seams: <interfaces públicas em que o comportamento é observado>
  - Camadas: <as camadas que ela toca>
  - Depende de: <slices anteriores, ou nenhuma>
  - Roteiro: <persona> · <passos>
    → antes: <o que os passos mostram no commit de partida>; depois: <o que mostram quando a slice entra>

Slice estacionada: último sub-item `- Bloqueada: <o que falta e de quem>`, apagado ao destravar, só nela (o RoadS lê qualquer caixa aberta com ele como bloqueada). Achado não corrigido no PR: uma slice nova, `- [ ] S<k>. <resultado observável> (achado da revisão)`, nunca numa seção à parte nem caixa `P<k>`; só esta seção conta para fechar a issue, e a slice fecha quando está tratada, concluída e marcada com evidência.

## Camadas da fatia

Uma linha por camada; camada que ninguém leu é lacuna do plano. "Não tocada" só com evidência: motivo sem evidência não é aceito, e linha sem evidência bloqueia a aprovação do plano. Camada que o projeto não tem: `não existe`, evidência `inspect`.

| Camada | Situação | Onde ou motivo | Evidência |
| --- | --- | --- | --- |
| Tela | tratada (S<n>) / não tocada / não existe | esta issue, #<filha>, ou o motivo | arquivo:linha, coluna, consumidor ou teste |
| API | | | |
| Banco e migração | | | |
| Testes | | | |
| Integração | | | |
| Documentação | | | |

Com tela, o rastreio por busca no código de cada campo, botão ou ação. Campo sem consumidor no back, ou capacidade do back sem ação na tela, vira critério desta issue; rastreio inconclusivo vira a tarefa "provar o consumo por teste ou por leitura da execução" e bloqueia a aprovação do plano até ter evidência.

| Campo ou ação | Consumidor no back (arquivo:linha) | Coluna no banco | Teste |
| --- | --- | --- | --- |
| <campo> | | | |

## Navegador e testes ligados

- Toca o frontend: <sim | não>
- Conta: <conta 1 | contas 1 e 2>
- Fluxo: <telas e ações, o resultado esperado e o efeito no back e no banco depois de salvar; usuário de teste movido de perfil pelo produto: qual, e que será desfeito>
- Testes ligados: <navegador, integração, regressão, permissões entre contas, smoke>; casos extras: <nenhum>

Contas e processos vêm de `browserTest` no `.frontlights/config.json`; aqui não entra login, senha nem URL.

## Propriedade

- Caminhos que a issue pode tocar (pasta ou arquivo; `*` quando desconhecido): <src/..., tests/...>
- Recursos compartilhados: <migrations, portas, serviços de teste>, ou nenhum

## Dependências

Depends on: none

## Riscos e dependências

- <risco, dependência externa ou tamanho da sessão — como se trata>
