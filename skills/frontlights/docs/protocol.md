# Protocolo persistente e formatos dos registros

## Autoridade e pontos de aprovação

| Etapa | Permitido antes da próxima aprovação | Evidência exigida |
| --- | --- | --- |
| Atualização da skill (sem pergunta) | Consultar o commit publicado no remoto Git e mostrar o comando de atualização, sem executá-lo | Resultado do `update-check` |
| Inspeção | Ler o projeto atual e as fontes configuradas | Fontes, horários e limitações |
| Descoberta | Entrevistar, ler código, registrar decisões e publicar o artefato (uma página por grilling, na mesma URL, só com dados fictícios) | Resultado, limites e escolhas aprovados; a URL do artefato no log de descoberta (ou "artefato indisponível", sem a ferramenta; "não se aplica", quando nenhuma rodada toca tela, fluxo ou camadas) |
| Issue | Redigir o corpo da issue a partir da descoberta, sem nova entrevista; a única pergunta é a dos seams | Texto integral mostrado e aprovação humana da revisão exata; nada publicado |
| Slices | Cortar o corpo aprovado em slices (uma caixa de critério por slice, bloqueadoras primeiro, até cinco por issue; o excedente vira issues de topo ligadas por blocked-by), mostrar a lista numerada com o quiz (cada slice com a seção do artefato que mostra o que ela entrega, na mesma URL do grilling; sem seção, dito uma vez, quando o log do grilling diz "não se aplica") e depois o corpo completo; etapas 4 e 5 na mesma janela | Lista numerada e quiz respondidos, corpos mostrados; aprovação das gravações específicas, uma escrita por issue (só acréscimo numa issue que já existe) |
| Publicação | Somente criações e atualizações aprovadas | Nova leitura dos links, conteúdos e dependências reais |
| Desenvolvimento | Sem pergunta de abertura, sob a autorização permanente (`references/development.md`, "Standing authorization and the denied operations"): só as issues da família ou do lote e as operações cobertas; a branch da issue, cortada da main local e nunca enviada, entra na main local por merge só com os três portões verdes ("Into the local main"); cada operação negada só com o "Sim" da pergunta própria; a prévia sobe logo depois da aprovação do plano, antes da primeira CA, numa aba do Claude in Chrome do usuário, é refeita a cada CA pronta (`serve preview refresh`) e só para a pedido | Anúncio do que a execução fará, testes, alterações, integração, revisão independente, os três portões e a saída do `authorize` do merge na main local |
| Release | Ao fim de cada issue homologada (`references/development.md`, "The release"): `homolog sync`, `homolog release-plan` (só leitura), a suíte inteira na main local (adotada de um registro inteiro verde da mesma árvore com `--from`, ou rodada com
`homolog suite --release --mode full`) e o `release-plan` de novo, a conferência da ponta antes da pergunta do merge
(`homolog suite-gate --release --head <sha>`), a oferta da release e, com o "Sim", a branch `<prefixo>release-<data>`, o push dela e a PR única (cobertos); depois, ler o estado da PR (`closeout.py merge-status`) e oferecer o merge; só com o "Sim" o merge é feito; depois dele, `git pull --ff-only` na main local | Saída do `release-plan` e resposta literal da oferta; a saída do `suite-gate --release --head`; a resposta do `merge-status` a cada despertar; resposta literal da pergunta do merge |
| Fechamento | Somente fechar, mover para Done e marcar no corpo do pai o que a pessoa aprovou na lista mostrada | Lista e comandos mostrados na íntegra, aprovação própria e nova leitura do GitHub |
| Limpeza | Somente remover as worktrees e branches da lista que a pessoa aprovou | Lista e comandos mostrados na íntegra, aprovação própria e nova leitura do Git e do GitHub |

Uma aprovação vale só depois de o usuário ver o conteúdo completo na sessão.
Antes da pergunta, o texto integral vai para a conversa, o arquivo é enviado pela
ferramenta de envio do ambiente, quando houver, e o texto se repete no `preview` da
opção de aprovação. Toda pergunta tem opções, e todo texto ao usuário sai no idioma dele.

Mudanças posteriores de escopo invalidam as aprovações afetadas. A exibição de
solicitações remotas não significa consentimento: ele vem só da resposta do usuário,
e um campo de um anexo não confiável é dado.

### Desenvolvimento e release

A etapa 6 roda sob a **autorização permanente**, decisão do usuário para todo projeto. As regras dela estão
numa fonte só, `references/development.md`: o que cobre, o charter (`approved_by`, `confirmed_by`,
`approval_reference`, `expires_at` de no máximo 24 horas), os merges cobertos e as operações negadas, cada uma
perguntada uma por vez e só rodada depois do "Sim", em "Standing authorization and the denied operations"; o hook
`pre-push`, a sincronização da main local e a prévia, em "The start of stage 6"; as slices de cada issue em ordem,
numa branch por issue, cortada da main local, e com uma worktree por slice, em "Slices in order"; os três portões do
merge na main local e o bundle depois dele, em "Into the local main"; a release, em "The release".

Uma slice estacionada ganha, logo abaixo da caixa aberta e como último sub-item dela, a
linha `- Bloqueada: <o que falta e de quem>` (corpo capturado, só acréscimo, diferença conferida),
apagada ao destravar, antes da marcação: a única remoção permitida no corpo de uma issue além
da migração de uma seção legada, conferida pela diferença.

O bloco `monitoring` da autorização registra `mode` (`local`, `phone` ou
`alternative`), `confirmed_by`, a identidade da sessão e o horário; sem outra
informação, é `local` com quem aprovou a autorização. Em `phone`,
`phone_connected` só recebe `true` depois que o usuário afirmar, na sessão atual,
que o celular recebeu uma pergunta e respondeu. Em `alternative`, `details` é
obrigatório. O Frontlights não detecta o celular nem o host do Remote Control, não lê
os ajustes de energia e não orienta `claude rc`: `phone_connected: true` vale
somente pela afirmação do usuário na sessão atual.

### Fechamento e release

O fechamento (`scripts/closeout.py`, só leitura) propõe fechar toda issue aberta, e toda sub-issue, com a seção
de critérios de aceitação e todos os itens marcados (e as filhas fechadas ou propostas junto, filhas antes dos
pais) e mover o cartão para o valor `project.done` (padrão `Status` / `Done`); uma issue já fechada como concluída com o cartão
fora de Done só é movida; uma issue com todas as caixas marcadas cuja branch ainda não está em `origin/main` fica
fora como `awaiting_release` até a release que a leva ser mesclada (o `candidates` lê só `rev-parse` e `merge-base`,
pelo `homolog.py`, e na dúvida não exclui). Quem escreve é a sessão, com o `gh` dela e depois da aprovação da lista, e a
conferência relê o GitHub. Só a aprovação dessa lista cobre essa escrita.

A release é oferecida ao fim de cada issue homologada e segue `references/development.md`, "The release": o
`homolog release-plan` (só leitura) nomeia a branch `<prefixo>release-<data>` (o prefixo do registro de autorização
mais recente por `issued_at`; os registros sem `issued_at` válido ficam abaixo dos que têm, e o empate vai para o
último nome de arquivo), a PR única leva o corpo do modelo
`templates/pr.md`, e a sessão age só sobre a resposta do `closeout.py merge-status`, em que só `merged_into_base`
vale (merge em outra branch, PR fechada sem merge ou não encontrada não fecha nada). Com o merge confirmado, `git
pull --ff-only` traz a main local até ele e o fechamento roda só para as issues da release; "Agora não" deixa a issue
homologada na main local, e a próxima issue homologada oferece a release de novo, com tudo o que acumulou. Para uma
sub-issue, a mesma aprovação do fechamento inclui marcar no corpo do pai o item que a cita (`parentTicks`; o
`closeout.py tick-check` confere antes e depois), e a limpeza das worktrees e branches (`scripts/cleanup.py
plan|verify`, nunca com `--force`) tem aprovação própria, depois do fechamento escrito e conferido
(`references/closeout.md`).

### Quadro e publicação

Projeto sem remoto é um estado suportado: `repository: null` no `config.json`, no
plano e na autorização. As issues locais ficam em `.frontlights/issues/<n>/`, e o
registro de cada uma traz `number`, `title`, `body`, `state` e `source: "local"`,
sem `html_url`. As branches usam `branch_prefix`, com padrão `claude/`.

Com `project` no `config.json`, publicar uma issue inclui, na mesma aprovação:
adicioná-la ao quadro (`gh project item-add`), atribuir o responsável e o tipo
(`gh issue edit --add-assignee --type`) e preencher cada campo do quadro
(`gh project item-edit --field --value`). O plano mostrado para aprovação traz esses
valores por issue, e todo campo recebe valor. Quando o `project` configura `labels`,
`issue_type_by_label` ou `body_fields`, o plano nomeia também os labels e as linhas do corpo, o
`validate-plan` imprime os valores finais (`resolved`) e a publicação usa só eles. A conclusão da publicação exige reler,
pelo GitHub, que a issue está no quadro com os valores aprovados. Projeto local
(`repository: null`) não tem quadro.

Regra do quadro: toda issue de topo entra no quadro; sub-issue entra só pelo pai.
Nenhuma sub-issue nova é criada: uma família que já existe (filhas publicadas antes desta
regra) é lida, trabalhada e fechada como antes, e o `validate-plan` recusa uma issue
proposta com `parent`. A conversão de família em issue + CAs (`references/issues.md`), oferecida
antes de agir numa família e feita em lote a pedido, é a única escrita que substitui um corpo: uma
aprovação por família, o corpo anterior guardado, as filhas fechadas como convertidas e o quadro
ajustado só com o "Sim" de cada operação. As dependências entre as issues de um plano nascem como relação
nativa do GitHub (`gh issue create --blocked-by`, bloqueadoras publicadas primeiro, na
ordem de `frontlights.py publish-order`) e são relidas em `blockedBy`; a linha `Depends
on:` do corpo é texto de apoio. Achados de revisão, testes ou conferência seguem a seção
Follow-ups de `skills/frontlights/references/issues.md`, com três destinos: corrigir no
PR, critério de aceitação novo na issue de origem, e issue de topo só para escopo novo ou
problema que atravessa várias issues; nunca uma sub-issue nova. O lote é decidido numa
única pergunta. Toda pendência que não
for corrigida no PR vira, na issue de origem, um critério `- [ ]` dentro da seção de
critérios de aceitação (nunca numa seção à parte, que o fechamento não conta), com
a evidência que o fechará; como altera o escopo, o texto exato é mostrado e aprovado no
lote antes de a sessão escrever o corpo (`gh issue edit --body-file`, com o corpo anterior
guardado, só acréscimo, exceto na migração de uma seção legada, releitura e diferença
conferidas) e a escrita é registrada no
documento de passagem de contexto. Antes de relatar uma issue como revisada ou concluída,
antes do merge na main local e antes de abrir ou atualizar um PR, todo achado em aberto precisa de destino rastreável
(corrigido, critério novo ou issue de topo); "citado no corpo do PR" nunca é
destino, e só ruído que não é defeito pode ficar como texto, dito como tal e com a
evidência. O pai de uma família que já existe só é dado como concluído com as filhas
fechadas; um achado tardio, depois de a issue fechar, vira issue de topo que a cita,
nunca sub-issue, e o Frontlights nunca reabre uma issue.

## Registros

Mantenha os registros privados de execução em `.frontlights/` no projeto de destino,
fora do versionamento, salvo revisão explícita para publicação. Não altere o código
do Frontlights enquanto ele executa trabalho no projeto consumidor. Estrutura recomendada:

```text
.frontlights/
  config.json
  discovery.md
  issue.md         corpo da issue aprovado na etapa 4, até a publicação da etapa 5
  plan.json
  authorization.json
  authorization-<AAAA-MM-DD>-issue-<n>.json   charters anteriores, guardados (nunca apagados): release-plan,
                   bundle, closeout e cleanup leem todo `authorization*.json`
  issues/<numero-no-github>/
    issue.json
    handoff.md
    checkpoint.json
    checkpoint-<id>.json   um por worktree de slice (`checkpoint --slice <id>`)
    evidence/<data-hora>.txt
    review.json            evidência a que a revisão independente ficou vinculada (`review-gate`)
    merge-local-main.json  operação do merge na main local, conferida pelo `authorize`
    body-before|body-new|body-after-<carimbo>.md   cópias do corpo que o `closeout.py tick` guarda
  direct/<branch-com-hifens>/   trabalho sem issue (caminho Direto, ou Curto sem publicar issue): handoff,
                                revisão, merge-local-main.json; no charter, a entrada de worktrees leva
                                `direct` (slug listado em `direct_ids`) no lugar de `issue`
  roadmap-sync/
    approval.json    par (endereço, variável) aprovado pelo usuário; marker.json, plan.json, state.json e
                     staging/ são sobras da antiga sincronização do roadmap, que nada mais lê
  progress-report/
    approval.json    aprovação do bloco exato `roadmapSync.progress` (hash assinado com a chave do usuário)
  serve/<n>.json     pids e portas dos processos que o `serve start` subiu para a issue
  preview/registry.json  pids, portas, branch e merges da prévia (`serve preview`), que sobrevive à issue e à sessão
  preview/log/<nome>.log  log mascarado de cada processo da prévia
  preview/branch.json    nome da branch da prévia, que o `preview stop` não apaga (o primeiro refresh reconhece a branch como da prévia)
  issues/<n>/checks/ registros de `checks regression|integration|smoke`
  issues/<n>/suite.json  última execução de `homolog suite` (impacto ou completa): mode, source (config ou
                         argument), base, argv, head e evidence (a mesma do `review-gate`), exitCode, timedOut,
                         seconds, output (o log), concurrent, startedAt e finishedAt; o `homolog suite-gate` a
                         compara com a ponta (current, stale, red, missing ou unconfigured); campos opcionais
                         `error` e `warnings`; fica na worktree da issue, não na principal. Com o marcador
                         `{report}` no argv de `homolog.suites.impact` (só lá, como argumento inteiro, uma vez),
                         ganha `report` (o caminho do relatório da execução) e, se o relatório for válido, `ran`
                         e `complete` (os ids que rodaram e os que rodaram por inteiro); relatório ausente, grande
                         demais ou inválido vira um aviso em `warnings`, sem `ran` nem `complete`, e o exitCode
                         fica o da execução; sem o marcador, nenhum desses campos
  issues/<n>/suite-report-<data-hora>.json  relatório que a suíte de impacto grava no caminho do `{report}`:
                         objeto com `ran` e `complete` (`{"ran": [ids], "complete": [ids]}`), listas de textos não
                         vazios sem NUL e sem repetição, todo id de `complete` também em `ran`; as outras chaves
                         (as de sempre do `--report` do `tests/suite.py`: version, modules, totals, mode...) são
                         ignoradas, e o registro guarda só `ran` e `complete`
  issues/<n>/suite-<modo>-<data-hora>.log  saída mascarada de cada execução de `homolog suite`
  release/suite.json     a suíte inteira da release (`homolog suite --release`), no mesmo formato, na worktree
                         principal; o `release-plan` a julga na ponta da main local (`fullSuite`;
                         `references/development.md`, "The release"); com `homolog suite --release --mode full
                         --from <registro>`, o registro da release é adotado sem rodar: guarda a execução
                         original e a evidência atual da main local (copia o registro da origem inteiro
                         (warnings incluídos), menos base, head e evidence: mode, source, argv, exitCode,
                         timedOut, seconds, output, concurrent, startedAt e finishedAt vêm dela), e
                         `adoptedFrom` {path, head, tree, adoptedAt} nomeia a origem (as recusas da adoção
                         estão em `references/development.md`, "The release"); os juízes o leem como
                         um rodado. Com o marcador `{covered}` no argv de `homolog.suites.full` (só lá, como
                         argumento inteiro, uma vez), ganha `covered` {complete, from [{issue, path, head, tree}],
                         refused [{issue, path, reason}], file}: `complete` lista os ids que os registros de
                         impacto das issues da release rodaram inteiros e verdes na mesma árvore da ponta (a
                         suíte os pulou), `from` os registros que contaram, `refused` os que não contaram e o
                         motivo, e `file` o `release/suite-covered-<data-hora>.json` (`{"complete": [ids]}`) que a
                         suíte recebeu; quando a lista das issues da release não sai (sem
                         `refs/remotes/<remoto>/<base>`, ou sem registro de autorização que nomeie uma delas),
                         `warnings` diz por que nada foi pulado; os juízes o leem como a suíte inteira da ponta. Na suíte inteira de uma
                         issue, o arquivo (`issues/<n>/suite-covered-<data-hora>.json`) vem com a lista vazia; sem
                         o marcador, nenhum desses campos nem arquivos
  release/suite-<sha>.json  cópia do mesmo registro por ponta (o sha completo do head), que a execução numa
                         ponta seguinte não sobrescreve; `homolog suite-gate --release --head <sha>` a julga,
                         e a PR da release fica pronta por ela (`references/development.md`, "The release")
  release/suite-full-<data-hora>.log  saída mascarada de cada execução dela
  issues/<n>/browser/result.json  resultado do teste de navegador; `pastaDosPrints` diz onde estão os prints da
                         rodada: a pasta da issue na sprint (`progress_report.py evidence-dir`), ou esta
                         mesma pasta num projeto sem `scrumRoot` e `weekFolderPattern`
```

### Teste no navegador

O teste de navegador roda quando algo que a sessão entrega muda o que a pessoa vê (o plano tem a seção
`## Navegador e testes ligados` com `Toca o frontend: sim`, ou o `browser-gate` acha a mudança visível no
diff), uma vez por issue e antes da revisão independente de qualquer fatia que muda a tela, só
com o que o plano liga e nesta ordem: `checks regression`, `serve start`,
`checks integration`, navegador e permissões entre contas, `checks smoke`, `serve stop` da issue (nunca o da prévia).
O `frontlights.py browser-gate --config <config> --base <base> --root <worktree> ... [--stacked <branch>=<alvo> ...] --toca <sim|nao|ausente>
--record <result.json>` lê o diff, devolve `not_needed`, `answered`, `pending`, `stale`, `contradiction` ou
`unconfigured` (saída 0 para os dois primeiros, 2 para os demais) e roda onde o `review-gate` roda. O
`result.json` é um por issue e fica na pasta dela (numa família que já existe, na pasta da issue líder) e traz `situacao` (`pendente`, `ainda-nao`, `aprovado`,
`prosseguir`, `sem-assistir`, `dispensado` ou `alteracao`), `lote` (`issues` e `roots`; as `roots` vêm do `browser-gate`) e
`pergunta.resposta`; só código que não é teste nem documento, depois da decisão, a torna `stale`. A pendência
`teste_assistido`, só quando a pergunta está devida (a última fatia de tela fechou o ciclo e não há resposta), atravessa janelas: `checkpoint --pending teste_assistido`, `resume` (o campo `pending` traz a lista, e a sessão a lê antes de tudo) e
`context --pending teste_assistido` (com `ask_before_continuing` em `handoff` e `stop`).
O passo do navegador começa com a pergunta "pronto para assistir?"; com o sim, roda em janela
visível em duas passagens do mesmo cenário e da mesma conta, a base ("ANTES") e depois a branch
("DEPOIS"), com cada caso duas vezes e a janela de cada passagem aberta cerca de 5 minutos no fim, presa por um processo em segundo plano
cujo término avisa quem conduz o teste: o usuário fechar a janela (ou os 5 minutos acabarem) é o aviso para iniciar a DEPOIS e,
depois dela, para entregar o relatório. Com os resultados no texto, o
usuário decide por `AskUserQuestion`: "Assistir de novo" (nova rodada das duas passagens, sem repetir
"pronto para assistir?"), "Aprovado", "Precisa de alteração" (nenhuma etapa seguinte roda; a mudança
volta ao laço de testes, ou segue a escada de destinos se ampliar o escopo) ou "Pode prosseguir" (sem
aprovar). Uma falha de produto na DEPOIS faz a pergunta de falha vir antes e substituir esta. O
`result.json` registra `assistido`, `rodadas`, `aprovacao` (`aprovado`, `prosseguir` ou `alteracao`,
com a resposta literal), cada passagem com a branch e o `head` servidos, a origem de cada resposta
(`back real` ou `interceptada`) e, quando um perfil de teste foi movido, só o campo de perfil antes
e depois de desfazer (nunca a linha inteira); o valor original fica antes em
`.frontlights/issues/<n>/browser/perfil-original.json`. O `ANTES` sobe a base com `serve start
--root <checkout-da-base> --issue <n>`, que guarda o registro dele no próprio checkout, e esse
registro é encerrado com `serve stop` antes do relato. As reservas de `"port": "auto"` ficam na pasta comum do Git (`frontlights-serve/ports/`),
compartilhada pelas worktrees; fora do Git, em `.frontlights/serve/ports/`, e repositórios
diferentes não veem as reservas uns dos outros. Os códigos de `checks` são 0 passou, 1 falha de produto, 2
config recusada e 3 infraestrutura. Toda falha vira pergunta por `AskUserQuestion`; sem
navegador ou rede, o teste é registrado como não executado e não conta como aprovado. Os
registros nunca trazem login nem senha: a conta aparece como `conta 1` ou `conta 2`. A evidência fica atada ao `head` em que
rodou: no teste assistido, quem diz se ela ainda vale é o `browser-gate`; os registros de `checks` ficam
antigos depois de qualquer commit.

### RoadS e resumo

O contrato com o RoadS (rotas, versão, o que é mudança aditiva e a regra para uma quebra) está em
`docs/roads-contract.md`.

O Frontlights não sincroniza roadmap nem sprint: o RoadS mantém o Roadmap a partir das issues abertas, e
`ROADMAP.md` e `SPRINT_*.md` não são escritos. As pastas da semana sob `roadmapSync.scrumRoot` (nomeadas por
`weekFolderPattern`) guardam só arquivos pontuais: os prints do resumo e os do teste assistido (`evidencias/`). As chaves da antiga sincronização
(`roadmapFile`, `sprintFilePattern`, `maxSprintItems`, `markCompleted`, `issueTargets`) são ignoradas, e o
`status` de `scripts/roads.py` as lista em `obsoleteKeys`; a aprovação do par (URL, variável) continua em
`.frontlights/roadmap-sync/approval.json`.

A pergunta da etapa 1 sobre as issues do RoadS roda o passo `gaps` (`references/issue-gaps.md`). Ele só lê: `GET
roadmap-state` (nada é consumido), e no GitHub só as issues do repositório do `config.json`,
por `gh api graphql`, com a conta ativa do `gh`. Uma URL do RoadS fora desse repositório é ignorada
e listada em `skipped`; issue fechada não é tocada. O resultado separa o que o config resolve
sozinho (`fill`) do que exige escolha (`choose`), e informa os campos do quadro sem opção
(`unfillable`). As escritas seguem a tabela aprovada pelo usuário, com o `gh` da sessão e as
permissões vigentes, só em valor vazio, e terminam relendo com `gaps`. Sem `roadmap-state` válido
(endpoint ausente, `schemaVersion` diferente de 1, campo de tipo errado, data inválida ou fora dos
anos 2000 a 2100), o passo é recusado; `snapshotStale` indica cópia do quadro com mais de 24 h ou ausente.

O passo do resumo para a diretoria (`scripts/progress_report.py`) vem logo depois da pergunta das
issues do RoadS, em qualquer projeto, e só existe quando há um bloco `roadmapSync.progress` habilitado: o do
próprio projeto ou o do projeto que o usuário registrou como dono (`progress_report.py home --set`, com o sim
dele; o `status` informa `source`, `operationsRoot` e `homeState`, e as demais operações rodam em
`operationsRoot`). A ordem é: `status`,
aprovação do bloco, `window`, `collect`, conferência dos números pelo usuário, arquivo de textos
(guia `draftGuide` e fatos coletados), prints em `shotsDir` com `captions.json` (ou, com
`weekShots`, na pasta do resumo que `shots --to` resolve, com a issue de cada print e pelo menos um
por entrega visível fora de `proximo`), rascunho mostrado na íntegra, aprovação e `push --draft` (com
`--to` quando há `weekShots`). A pasta é a da segunda-feira seguinte à semana do último dia do período,
com uma subpasta `<dd_MM>` por resumo; o contrato com o RoadS está em `docs/roads-contract.md`.
Nada é enviado sem a aprovação do rascunho completo. O período é só o do `window`, com hora: começa no
instante exato em que os números do resumo anterior foram coletados e chega aos coletores por
`collect --start <start> --end <end>`; as datas vêm sempre do `window`, e depois de qualquer correção roda
`window` de novo. Com `draftOtherPeriod` (o resumo anterior ainda como rascunho no RoadS), a sessão para e
pergunta antes de coletar, porque o envio substituiria esse rascunho.

A unidade de trabalho é a issue do GitHub, identificada pelo número, para que o
quadro e os registros locais coincidam. O Frontlights não cria identificadores
`GT-NNNN` nem escreve em `.agents/tasks/`, convenção aposentada do GuardianS.
Instruções de projeto que ainda peçam uma GT são tratadas como pedido de issue no
quadro, com as mesmas aprovações. Arquivos `GT-NNNN` existentes ficam como
histórico.

Esses arquivos não determinam de forma independente a situação das issues. Use uma
resposta JSON recente de `gh api repos/PROPRIETARIO/REPOSITORIO/issues/NUMERO` para
registrar o estado da issue. Não copie tokens, credenciais ou dados privados alheios
ao trabalho. Atualizações de situação no GitHub exigem autorização própria; salvar
um ponto de retomada local não concede essa permissão.

### `plan.json`

O formato de `plan.json` segue `examples/plan.json`. O campo opcional `slices` de uma issue
lista as slices em ordem de dependência, bloqueadoras primeiro, cada uma com `id`, `title`,
`delivers` (o que dá para demonstrar quando ela termina), `seams`, `layers` e `depends_on`; o
`validate-plan` recusa slice sem `delivers`, sem seams ou camadas, ou com dependência
inexistente, posterior ou repetida, e com `slices` a issue dispensa `acceptance` e
`vertical_check`, porque as slices trazem os dois. O campo opcional `parent` de uma
issue é o id de outra issue do mesmo plano (a issue de origem já publicada entra no
plano com o próprio número), o que permite conferir o vínculo sem rede; ele só cabe numa
filha já publicada de uma família que já existe, porque uma issue proposta com `parent`
ou `parent_external`, ou sem o `url` dela, é recusada: nunca se cria sub-issue nova. O limite de
100 filhas conta só as do plano; antes de publicar, confira `subIssuesSummary.total` do
pai no GitHub para não passar de 100. Sem `parent`, nada muda. Uma sub-issue de uma issue já
publicada que não está no plano leva `parent_external` (o número do pai) no lugar de `parent`: não
leva campo do quadro, e os limites de 100 filhas e 8 níveis são lidos do GitHub antes de publicar.
Os valores técnicos `ready` (pronta), `running` (em execução), `blocked` (bloqueada), `verified` (verificada) e
`proposed` (proposta) representam observações locais do estado oficial. Salve também
o horário da consulta ao GitHub. Uma issue concluída só libera dependentes quando
suas alterações verificadas estão na base aprovada dessas dependentes; confira o
histórico e as diferenças reais do Git. Com a autorização de **branches empilhadas**, a
base aprovada de uma dependente é a branch da própria dependência: a filha sai dela quando a
dependência está `verified` ali, a filha verificada é mesclada na branch do pai (merge coberto), e a
família entra na main local pela branch do pai, com as filhas dentro, pelos três portões; nenhuma PR por
filha, nenhum push (nunca rebase nem push forçado). O `schedule` só lê `status` e não vê uma issue que depende de
duas branches sem merge: essa conferência é manual. Uma issue e as sub-issues abertas dela
entram juntas no plano e na autorização; `Parent` é pertencimento e só `Depends on` impede o
início. Responsabilidade desconhecida usa `*` e
conflita com tudo. Represente recursos compartilhados por caminhos de responsabilidade
comuns ou dependências explícitas. Os validadores conferem caminhos e estrutura de
dependências; não detectam disputas ocultas por recursos nem validam aprovação humana.

O planejador limita cada lote a 24 issues para manter sua busca exata dentro de um
custo limitado. Ele não altera situações, inicia agentes nem reserva recursos.
A única sessão coordenadora registra o trabalho em execução antes da próxima
distribuição. Recalcule o plano
após conclusões ou descobertas.

**Paralelismo.** Em toda etapa, o trabalho que não depende de outro sai ao mesmo tempo, um subagente por
parte e tantos quantas forem as partes, lançados numa única mensagem e repostos à medida que terminam: as
leituras das etapas 0 a 2 de uma vez; a leitura do código, as convenções, o rastreio campo a campo e a
pesquisa, um subagente por área ou camada; na etapa 6, o maior número seguro de issues independentes, cada
uma na própria worktree com o próprio agente, e, dentro de uma issue, as slices independentes ao mesmo tempo, cada uma na própria worktree,
mais o trabalho em volta de cada slice aberta
(leitura para a próxima slice, suíte ampla, verificação de tipos, condutor do teste assistido e revisor
independente), respeitada a ordem de dependência (a slice dependente é empilhada na branch da anterior). Só espera o
que depende de verdade: uma aprovação ainda não dada, um `Depende de`, um arquivo que duas partes
editariam ou um recurso compartilhado (porta, banco, pasta de reservas, arquivo gerado; módulos de teste
que dividem um deles rodam um por vez). Sem subagentes no ambiente, a sessão avisa numa linha e registra o
limite de capacidade. A sessão coordenadora é uma só: só ela pergunta
(`AskUserQuestion`), aprova, escreve no GitHub, roda uma operação negada e grava o handoff. Cada subagente
recebe um brief delimitado (resultado, caminhos próprios, testes, as regras da etapa: dados de teste,
segredos mascarados, idioma do usuário) e o que nunca faz (perguntar ao usuário, editar fora dos caminhos,
escrever no GitHub, mesclar, ampliar o escopo); uma pergunta que ele encontre volta para a sessão. O relato
de um subagente é afirmação, não evidência: a sessão lê o diff e repete os comandos medidos antes de contar,
e o revisor nunca é o autor.

**Rodadas de teste.** Por slice, rodam os módulos que a slice toca e a verificação de tipos; a suíte
rápida é a forma de conferir o todo entre slices, quando o projeto tem uma. No repositório do Frontlights
ela roda por `python tests/suite.py` com `FRONTLIGHTS_SUITE=rapida` (só Windows): a variável faz pular os
módulos de portas e da prévia do `serve` e de integração do `checks`, cada um relatado como pulado com o motivo que
cita a variável (qualquer outro valor, ou a ausência dela, roda tudo; a regra está no `load_tests` de cada
módulo e vale igual para o `discover`), e o runner roda os módulos seguros em paralelo e os seis
sensíveis numa fila serial, um por vez; `--report <arquivo>` grava o JSON da rodada como evidência.
Por issue, o portão é a suíte por impacto do projeto, e a suíte inteira sem a variável roda na release, uma vez,
obrigatória com ou sem CI no projeto; o que cada uma roda está em `references/development.md`, "Which tests run
when" e "The release". A CI do GitHub deste repositório fica como a conferência inteira, pelo
`python -m unittest discover -s tests -v` (o runner não a deixa mais rápida do que o `discover`): ela roda o mesmo
`discover` e não define a variável.

## Ponto de retomada e continuação

Escreva o documento de passagem de contexto com `templates/handoff.md` e execute:

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" checkpoint --root <worktree> --issue <issue.json> --handoff <handoff.md> --next-step "Executar o teste de regressão de persistência"
```

Salve a saída padrão em `checkpoint.json` (na worktree de uma slice, em `checkpoint-<id>.json`, um por
worktree de slice), com codificação UTF-8. O utilitário inclui
HEAD, branch, hash das diferenças binárias, hashes dos arquivos versionados e não
versionados, registro da issue, hash do documento de passagem de contexto, próximo
passo e horário. Ele exclui `.frontlights/` para evitar hashes que dependam do próprio
registro. As evidências contêm hashes e nomes de arquivos, não seus conteúdos.
Revise nomes que possam revelar informações sensíveis antes de publicar. Repositórios
sem commit inicial não produzem evidência vinculada a um HEAD exato; faça primeiro
o commit inicial aprovado.

Em uma sessão nova, consulte a issue novamente e execute:

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/frontlights.py" resume --root <worktree> --issue <issue-atual.json> --handoff <handoff.md> --checkpoint <checkpoint.json>
```

O resultado `reconcile` indica divergências no Git, na issue ou no documento de
passagem de contexto; relate cada divergência e, ao substituir um registro, diga qual substituiu. Mesmo com
`unchanged`, é necessário ler a issue, o documento e as alterações atuais. A CLI
retorna os dados na saída padrão; salvá-los é uma ação local explícita do coordenador.
Nenhum utilitário grava registros externos ou inicia outra sessão do modelo.

## Contexto e conclusão

Use o consumo acumulado medido da sessão e uma reserva conservadora para o próximo
passo. O comando `context` retorna `handoff` ao atingir 100 mil tokens com a reserva,
`stop` ao atingir 150 mil com a reserva e `stop` quando o consumo é desconhecido.
Ele não mede nem intercepta os tokens do modelo. Se não for possível aplicar medição
e renovação de sessão, não garanta o teto de 150 mil nem inicie uma fase sem supervisão
que dependa dele. Crie o contexto novo com os controles suportados pelo ambiente;
renomear uma sessão compactada não a torna nova.

A conclusão exige cobertura dos critérios de aceitação, alterações completas e
atuais, verificações específicas e abrangentes, verificação de tipos quando aplicável
e revisão independente vinculada às mesmas evidências. Se não houver suporte à
revisão, registre explicitamente a pendência. O relatório do autor nunca substitui
uma verificação independente.

O revisor julga pelo padrão de `references/review.md` (o que é defeito e em que gravidade, o que é só estilo e
nunca vira achado, como relata), que só o brief do revisor cita. Quando a revisão termina, o limite de rodadas, a
pergunta do limite, a rodada que só reconfere a base e o destino dos baixos estão numa fonte só,
`references/development.md`, "When the review is done".

A evidência a que a revisão ficou vinculada é salva em
`.frontlights/issues/<n>/review.json`, e `frontlights.py review-gate --root <worktree> --review <arquivo>`
a compara com a atual: saída 0 (`current`) vale, saída 2 (`stale`) significa que houve commit, edição ou
arquivo novo depois da revisão, e pede nova revisão antes de a issue ser relatada como revisada, entrar na
main local ou ter PR aberto ou atualizado; os três portões do merge na main local estão em
`references/development.md`, "Into the local main". Uma família de branches é integrada localmente, com a suíte por
impacto verde, antes de entrar na main local (`references/development.md`, "Integrating a family before the local main"). A conclusão exige também que nenhum achado fique sem destino rastreável: o handoff traz a
linha "Achados sem correção e destino de cada um", e uma pendência vira critério de aceitação da issue de
origem, que só fecha com ela tratada, concluída e marcada com evidência.
