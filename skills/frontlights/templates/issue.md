# <Um resultado observável>

PRD: <revisão aprovada ou link>

## Resultado

## Limites e fora de escopo

## Critérios de aceitação

- [ ] <resultado observável>

Achado de revisão, de teste ao vivo ou de conferência que não for corrigido no PR entra
aqui como mais um critério (`- [ ] Pendência (achado da revisão): <resultado observável>.
Evidência que fecha: <teste, medição ou diff revisado>`), nunca numa seção à parte: só
esta seção conta para fechar a issue, e a issue só fecha com a pendência tratada,
concluída e marcada com evidência.

## Abordagem e convenções

Abordagem escolhida (as alternativas rejeitadas ficam no PRD ou no registro de descoberta)
e as convenções do projeto a seguir, com caminhos de exemplo. Toda quebra de padrão
aprovada é nomeada aqui com o motivo.

## Seams sob teste

- <interface pública> — <comportamento de aceitação observado ali>

Só estes seams recebem testes. Seam ausente ou errado volta ao usuário.

## Expectativas de teste

Regressão focada, integração mais ampla e os comandos reais de checagem de tipos.

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
critério de aceitação desta issue ou sub-issue, nunca "não tocada". Rastreio inconclusivo
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
com `não` vira pergunta. O teste assistido é um por lote de trabalho, antes da revisão, não um por
issue nem por branch.

## Dependências

Depends on: none
Parent: none

Troque `none` pelos links canônicos #issue depois da publicação aprovada. `Depends on:` e
`Parent:` são marcadores lidos pelos scripts e ficam como estão.

`Parent` é a issue de origem de uma sub-issue (parte da mesma fatia, achado de revisão
ou de conferência); `none` numa issue de topo. Toda issue de topo entra no quadro;
sub-issue entra só pelo pai, que mostra o progresso das filhas. `Parent` é
pertencimento, não dependência: uma filha que precisa do código do pai também o lista
em `Depends on`, e na etapa 6 ela pode ser empilhada na branch dele, sem esperar o merge.

## Propriedade e contenção

Arquivos e componentes, arquivos gerados, migrations, portas, serviços de teste compartilhados.

## Verificação da fatia vertical

O que funciona de ponta a ponta e como um revisor observa isso. Um pré-requisito
nomeia o seam que funciona, o teste e o consumidor que depende dele.

## Riscos e tamanho da sessão

## Pontos de evidência

Data e hora, branch/PR, hashes exatos de `HEAD` e do diff, comandos e resultados, revisão
independente, bloqueios restantes e próximo passo. O GitHub continua a fonte oficial; links
de evidência local não são tickets à parte. Não fechar automaticamente.
