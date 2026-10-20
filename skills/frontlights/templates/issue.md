# <Um resultado observável>

As seções até "Fora de escopo" são a spec: registram, em português, o que a entrevista da
etapa 3 decidiu, sem nova pergunta além da dos seams. Seção que não se aplica fica marcada
com o motivo, nunca preenchida por obrigação. Nada aqui que o usuário não tenha decidido.

## Problema

O problema do ponto de vista de quem usa: o que acontece hoje, a dor observada e a fonte
(observação, issue, pedido), com data.

## Solução

A solução do ponto de vista de quem usa: o que passa a acontecer e a medida de sucesso.

## Decisões de implementação

A abordagem escolhida; as alternativas rejeitadas, cada uma com o motivo; as convenções do
projeto que a abordagem segue, nomeadas pelo padrão (os caminhos ficam na propriedade e no
rastreio), e toda quebra de padrão aprovada, com o motivo e o custo; interfaces, contratos,
esquema e decisões de arquitetura. A prosa das
decisões não cita arquivo nem trecho de código, porque envelhece; a exceção é um trecho de
protótipo que registra uma decisão melhor do que a prosa, cortado ao essencial e dito como tal.

## Decisões de teste

O que é um bom teste aqui: só comportamento observável pela interface pública, nunca detalhe
interno. Os seams sob teste, confirmados na etapa 4, cada um com o comportamento de aceitação
observado nele: só eles recebem testes, e seam ausente ou errado volta ao usuário. A arte
prévia (testes parecidos que já existem no código) e os comandos reais de regressão,
integração e checagem de tipos.

## Fora de escopo

O que foi recusado, com o motivo. São as linhas mais úteis da página.

## Critérios de aceitação

As slices, em ordem de dependência, bloqueadoras primeiro: uma caixa por slice, com o
resultado observável de ponta a ponta, e logo abaixo os sub-itens sem caixa. Prefactoring,
quando houver, é a primeira slice e nomeia o seam que funciona, o teste e o consumidor que
depende dele; refatoração larga é a exceção declarada: expandir, migrar por lotes e contrair,
cada passo uma slice. Uma issue curta tem no máximo cinco caixas `S<n>`: a sexta vira issues de
topo ligadas por blocked-by (nunca uma sub-issue nova), e a caixa de pendência não conta no
teto. Todo critério falha no commit de partida; o que já é verdadeiro antes
do trabalho não é critério. Cada caixa fecha só com evidência. Uma slice estacionada ganha, como
último sub-item da caixa, `- Bloqueada: <o que falta e de quem>`, apagado ao destravar, antes da
marcação; não copie esse sub-item para uma slice que não está estacionada, porque o RoadS lê
qualquer caixa aberta com ele como bloqueada.

- [ ] S1. <resultado observável de ponta a ponta desta slice>
  - Entrega: <o que dá para demonstrar quando ela termina>
  - Seams: <interfaces públicas em que o comportamento é observado>
  - Camadas: <as camadas que ela toca>
  - Depende de: <slices anteriores, ou nenhuma>

Achado de revisão, de teste ao vivo ou de conferência que não for corrigido no PR entra
aqui como mais um critério (`- [ ] Pendência (achado da revisão): <resultado observável>.
Evidência que fecha: <teste, medição ou diff revisado>`), nunca numa seção à parte: só
esta seção conta para fechar a issue, e a issue só fecha com a pendência tratada,
concluída e marcada com evidência.

## Camadas da fatia

A fatia é esta issue mais as sub-issues dela, e juntas cobrem todas as camadas que
o requisito pede. Liste as camadas lidas do código (no mínimo as seis abaixo, mais as
do projeto, como permissões, configuração, tradução, observabilidade, tarefas em
segundo plano). Uma camada que ninguém analisou é lacuna do plano, não "não tocada".
Uma sub-issue copia só as linhas que ela cobre.

A fatia só é definida depois da leitura de todas as camadas (front: componentes, serviços,
modelos, rotas e specs; back: controllers, services, contratos e DTOs, repositories,
mapeamentos e validadores; migrations e schema; testes; documentação), com certeza de que
não sobra ponta solta. "Não tocada" só vale com a evidência do rastreio abaixo; motivo sem
evidência não é aceito, e linha sem evidência impede aprovar o plano.

| Camada | Situação | Onde ou motivo | Evidência |
| --- | --- | --- | --- |
| Tela | tratada / não tocada | esta issue, #<filha>, ou o motivo | arquivo:linha, coluna, consumidor ou teste |
| API | | | |
| Banco e migração | | | |
| Testes | | | |
| Integração | | | |
| Documentação | | | |

Rastreio dos campos, botões e ações que a fatia toca na tela, feito por busca no código:

| Campo ou ação | Consumidor no back (arquivo:linha) | Coluna no banco | Teste |
| --- | --- | --- | --- |
| <campo> | | | |

Campo sem consumidor no back, ou capacidade do back sem ação na tela, é achado: vira
critério de aceitação desta issue (numa família que já existe, da filha que cobre a camada),
nunca sub-issue nova nem "não tocada". Rastreio inconclusivo
(consumo dinâmico, reflexão, nome de coluna montado em texto) vira a tarefa "provar o
consumo por teste ou por leitura da execução" e bloqueia a aprovação do plano até ser
resolvida com evidência; nunca fica só como nota.

## Navegador e testes ligados

- Toca o frontend: <sim | não>
- Conta: <conta 1 | contas 1 e 2>
- Fluxo: <telas e ações a exercitar, com o resultado esperado e o efeito no back e no banco depois de salvar; se mover um usuário de teste de perfil pelo endpoint do produto, diga qual e que será desfeito>
- Testes ligados: <navegador, integração, regressão, permissões entre contas, smoke>; casos extras: <nenhum>

Contas e processos vêm de `browserTest` no `.frontlights/config.json` do projeto,
nunca deste texto: aqui não entram login, senha nem URL.

`Toca o frontend:` é uma declaração, e o `browser-gate` a confere com o diff: uma mudança visível
com `não` vira pergunta. O teste assistido é um por issue, antes da revisão, não um por CA, branch
ou worktree; a pergunta sai quando a última CA que muda a tela fecha o ciclo e toda CA já fechada
está mesclada na branch da issue.

## Dependências

Depends on: none

Troque `none` pelos links canônicos #issue depois da publicação aprovada. `Depends on:` é
texto de apoio: a dependência entre issues do plano nasce no GitHub como relação nativa
(`gh issue create --blocked-by`, relida em `blockedBy`), com as bloqueadoras publicadas
primeiro. Nenhuma sub-issue nova é criada: um achado vira critério desta issue ou issue de
topo. Toda issue de topo entra no quadro; uma filha já publicada de uma família que já
existe entra só pelo pai e mantém a linha `Parent: #<pai>` que tem: `Parent` é
pertencimento, não dependência, e na etapa 6 ela pode ser empilhada na branch do pai, sem
esperar o merge.

## Propriedade e contenção

Arquivos e componentes, arquivos gerados, migrations, portas, serviços de teste compartilhados.

## Riscos e dependências

Riscos, dependências externas (outro sistema, outra equipe) e o tamanho da sessão.

## Pontos de evidência

Data e hora, branch/PR, hashes exatos de `HEAD` e do diff, comandos e resultados, revisão
independente, bloqueios restantes e próximo passo. O GitHub continua a fonte oficial; links
de evidência local não são tickets à parte. Não fechar automaticamente: só a linha `Closes #<n>` da PR da
release, para uma issue do `closes` do `release-plan`, a fecha, no merge que o usuário aprovou.
