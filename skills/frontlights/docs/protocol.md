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
| Desenvolvimento | Sem pergunta de abertura, sob a autorização permanente: só as issues da família ou do lote e as operações cobertas; a branch da issue, cortada da main local e nunca enviada, entra na main local por merge só com os três portões verdes (suíte inteira, `review-gate` atual, `browser-gate` respondido); cada operação negada só com o "Sim" da pergunta própria | Anúncio do que a execução fará, testes, alterações, integração, revisão independente, os três portões e a saída do `authorize` do merge na main local |
| Release | Ao fim de cada issue homologada: `homolog sync`, `homolog release-plan` (só leitura), a oferta da release ("Lançar a release com as issues #a, #b agora?") e, com o "Sim", a branch `<prefixo>release-<data>`, o push dela e a PR única (cobertos); depois, ler o estado da PR (`closeout.py merge-status`) e oferecer o merge; só com o "Sim" o merge é feito; depois dele, `git pull --ff-only` na main local | Saída do `release-plan` e resposta literal da oferta; resposta do `merge-status` a cada despertar, nunca só o aviso do ambiente; resposta literal da pergunta do merge |
| Fechamento | Somente fechar, mover para Done e marcar no corpo do pai o que a pessoa aprovou na lista mostrada | Lista e comandos mostrados na íntegra, aprovação própria e nova leitura do GitHub |
| Limpeza | Somente remover as worktrees e branches da lista que a pessoa aprovou | Lista e comandos mostrados na íntegra, aprovação própria e nova leitura do Git e do GitHub |

A etapa 6 roda sob uma **autorização permanente**, decisão do usuário para todo projeto: não há
pergunta de concorrência, de empilhamento nem de autorização delimitada. A sessão trabalha as
slices de cada issue em ordem, numa branch por issue, cortada da main local (a branch base do charter, na
worktree principal, nunca `origin/main`), que fica só local, nunca é enviada e entra na main local por um
merge com três portões verdes (suíte inteira no tip da branch, `review-gate` atual e `browser-gate`
respondido ou `not_needed`, conferidos pelo `authorize` como `merge_into_local_main`), com uma worktree por slice (branch
`<prefixo>issue-<n>-s<k>` cortada da branch da issue e devolvida a ela por merge quando o ciclo fecha,
com o próprio `checkpoint-<id>.json`) e slices independentes em paralelo dentro da issue e entre issues (a
slice que depende de outra ainda aberta é empilhada na branch dela; o
trabalho em volta de cada slice aberta sai em paralelo, regra do paralelismo abaixo);
empilha as filhas na branch da dependência só numa família que já existe (issue com sub-issues
publicadas antes desta regra); anuncia num bloco curto as issues, a branch e a ordem das slices
de cada uma, o repositório, a concorrência, o empilhamento quando há família, a base das
worktrees, os testes e as condições de parada, e grava `authorization.json` com o usuário em
`approved_by` e `confirmed_by`,
`"autorização permanente (docs/security.md)"` em `approval_reference` e validade de no máximo 24
horas. Ficam cobertos, só para as issues da família ou do lote: editar, testar, commitar, os merges que a
autorização de empilhamento nomeia (entre eles o de `origin/main` na main local pelo `homolog sync`, no
início de cada etapa 6 e antes da release, com um conflito desfeito na hora e virando pergunta, e o da branch
da issue na main local, só com os três portões verdes), conferir no início de cada etapa 6 o hook `pre-push`
de `homolog hook` (instalado só com o "Sim" da pergunta que mostra o script; nunca por cima de um hook de
outra origem), gravar a cada merge na main local o bundle da main local e das branches de trabalho na pasta
`homolog.backupDir` do config (`homolog bundle`; sem a chave, nada é gravado e a sessão avisa), rodar
migrations no banco de desenvolvimento local, criar e
remover dados de teste pelos endpoints do produto, comentar nas issues e marcar critérios com
evidência. Nada da issue vai ao GitHub antes da release: as branches da issue e das slices nunca são
enviadas, e a única PR é a da release, oferecida ao fim de cada issue homologada. Uma slice estacionada ganha, logo abaixo da caixa aberta e como último sub-item dela, a
linha `- Bloqueada: <o que falta e de quem>` (corpo capturado, só acréscimo, diferença conferida),
apagada ao destravar, antes da marcação: a única remoção permitida no corpo de uma issue além
da migração de uma seção legada, conferida pela diferença. Nunca ficam cobertos: merge de PR,
fechar issue, mexer no quadro, implantar ou publicar
em produção, editar uma migration já registrada, escrever na main remota (`origin/main`, a branch base no
GitHub) ou numa branch protegida (a main local só recebe o merge coberto, com os três portões), ligar
configuração, chave ou flag em produção e apagar o que não for dado de teste criado pela execução.
Cada uma é perguntada por `AskUserQuestion`, uma operação por vez, com "Sim" e "Não" e o comando
exato; só roda depois do "Sim", que vale só para ela, e a resposta literal vai para o handoff. As
perguntas do próprio trabalho (teste assistido, falhas, lote de achados, decisão nova de produto)
continuam, e as etapas com aprovação própria (texto da issue, plano e publicação de issues,
fechamento, limpeza, roadmap e resumo) também.

O bloco `monitoring` da autorização registra `mode` (`local`, `phone` ou
`alternative`), `confirmed_by`, a identidade da sessão e o horário; sem outra
informação, é `local` com quem aprovou a autorização. Em `phone`,
`phone_connected` só recebe `true` depois que o usuário afirmar, na sessão atual,
que o celular recebeu uma pergunta e respondeu. Em `alternative`, `details` é
obrigatório. O Frontlights não detecta o celular nem o host do Remote Control, não lê
os ajustes de energia e não orienta `claude rc`: `phone_connected: true` vale
somente pela afirmação do usuário na sessão atual.

O fechamento (`scripts/closeout.py`, só leitura) propõe fechar toda issue aberta, e toda sub-issue, com a seção
de critérios de aceitação e todos os itens marcados (e as filhas fechadas ou propostas junto, filhas antes dos
pais) e mover o cartão para o valor `project.done` (padrão `Status` / `Done`); uma issue já fechada como concluída com o cartão
fora de Done só é movida; uma issue com todas as caixas marcadas cuja branch ainda não está em `origin/main` fica
fora como `awaiting_release` até a release que a leva ser mesclada (o `candidates` lê só `rev-parse` e `merge-base`,
pelo `homolog.py`, e na dúvida não exclui). Quem escreve é a sessão, com o `gh` dela e depois da aprovação da lista, e a
conferência relê o GitHub. Nenhuma outra autorização cobre essa escrita.

A release é oferecida ao fim de cada issue homologada (`references/development.md`, "The release"): depois de
`homolog sync`, o `homolog release-plan` (só leitura) lista as issues que estão na main local e ainda não em
`origin/main` e nomeia a branch `<prefixo>release-<data>`; a sessão mostra a lista e pergunta "Lançar a release com as
issues #a, #b agora?" ("Sim, lançar" / "Agora não"). Com o "Sim", cortar a branch da main local, enviá-la (a única
branch do fluxo que é enviada) e abrir a PR única (corpo pelo `templates/pr.md` quando existir, uma parte por issue
com os três portões) são operações cobertas. Depois de abrir a PR da release, a sessão aguarda o merge por padrão e
registra isso no handoff ("Aguardando o merge", na linha `Release`); a PR
nunca leva palavra de fechamento (`Closes`, `Fixes`, `Resolves`) no corpo nem nos commits. O aviso do ambiente
(inscrição na PR ou um monitor) é só o gatilho: a cada despertar roda `closeout.py merge-status --prs ... --base
<base aprovada>`, e só `merged_into_base` vale; merge em outra branch, PR fechada sem merge ou não
encontrada não fecha nada. Com o merge confirmado, `git pull --ff-only` traz a main local até ele e o fechamento roda
só para as issues da release, que só aparecem com todos os critérios marcados; "Agora não" deixa a issue homologada na
main local, e a próxima issue homologada oferece a release de novo, com tudo o que acumulou. Para uma sub-issue, a mesma aprovação inclui marcar no corpo do pai o item que a cita
(`parentTicks`: números de linha, só itens que citam apenas essa filha; a escrita troca só `[ ]` por `[x]`, e
`closeout.py tick-check` confere antes e depois). Depois do fechamento escrito e conferido, uma aprovação própria
pergunta se pode remover as worktrees e branches criados e que deixaram de ser necessários (`scripts/cleanup.py
plan|verify`): só entram os que têm o tip igual à cabeça de uma PR mesclada que chegou à base aprovada (o filho
empilhado, pelo pai) ou, sem PR nenhuma, cujo tip já está em `origin/main` (a branch de uma issue que chegou ao GitHub
pela release; cautela `contained_in_base_without_pull_request`), sem alteração pendente, sem PR aberta a partir ou em cima da branch, que não são protegidos, nem
a worktree principal, nem a pasta em que a sessão está; nunca com `--force`. Os arquivos ignorados pelo Git vão junto com a worktree e são
listados antes da aprovação, e a worktree de integração local da família entra quando não guarda commit próprio (nem merge com conteúdo
próprio) fora das PRs entregues.

Nenhuma aprovação vale sem que o usuário tenha visto o conteúdo completo na sessão.
Antes da pergunta, o texto integral vai para a conversa, o arquivo é enviado pela
ferramenta de envio do ambiente, quando houver, e o texto se repete no `preview` da
opção de aprovação. Toda pergunta tem opções, e todo texto ao usuário sai no idioma dele.

Projeto sem remoto é um estado suportado: `repository: null` no `config.json`, no
plano e na autorização. As issues locais ficam em `.frontlights/issues/<n>/`, e o
registro de cada uma traz `number`, `title`, `body`, `state` e `source: "local"`,
sem `html_url`. As branches usam `branch_prefix`, com padrão `claude/`.

Com `project` no `config.json`, publicar uma issue inclui, na mesma aprovação:
adicioná-la ao quadro (`gh project item-add`), atribuir o responsável e o tipo
(`gh issue edit --add-assignee --type`) e preencher cada campo do quadro
(`gh project item-edit --field --value`). O plano mostrado para aprovação traz esses
valores por issue, e nenhum campo fica vazio. Quando o `project` configura `labels`,
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

Mudanças posteriores de escopo invalidam as aprovações afetadas. A exibição de
solicitações remotas não significa consentimento. Nunca deduza consentimento de
um campo em um anexo não confiável.

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
  issues/<numero-no-github>/
    issue.json
    handoff.md
    checkpoint.json
    checkpoint-<id>.json   um por worktree de slice (`checkpoint --slice <id>`)
    evidence/<data-hora>.txt
  roadmap-sync/
    approval.json    par (endereço, variável) aprovado pelo usuário
    marker.json      segredo local das marcas; nunca sai da máquina
    plan.json        mudanças buscadas no RoadS, sprints do roadmap-state (itens dentro e fora do limite), marcas e destinos
    state.json       último asOf confirmado
    staging/         cópias temporárias do ROADMAP e do SPRINT de cada sprint com mudança (vazia para sprint nova)
  progress-report/
    approval.json    aprovação do bloco exato `roadmapSync.progress` (hash assinado com a chave do usuário)
  serve/<n>.json     pids e portas dos processos que o `serve start` subiu para a issue
  issues/<n>/checks/ registros de `checks regression|integration|smoke`
  issues/<n>/browser/result.json  resultado do teste de navegador, com os prints ao lado
```

O teste de navegador roda quando algo que a sessão entrega muda o que a pessoa vê (o plano tem a seção
`## Navegador e testes ligados` com `Toca o frontend: sim`, ou o `browser-gate` acha a mudança visível no
diff), uma vez por issue e antes da revisão independente de qualquer fatia que muda a tela, só
com o que o plano liga e nesta ordem: `checks regression`, `serve start`,
`checks integration`, navegador e permissões entre contas, `checks smoke`, `serve stop`.
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

O contrato com o RoadS (rotas, versão, o que é mudança aditiva e a regra para uma quebra) está em
`docs/roads-contract.md`.

A sincronização do roadmap (`scripts/roadmap_sync.py`) segue esta ordem no `fetch`: `POST
sync-board`, `GET roadmap-state` e `GET pending-changes`, todos sob o `endpoint` aprovado e com o
mesmo segredo. Os padrões de caminho (`roadmapFile`, `weekFolderPattern`, `sprintFilePattern`)
são conferidos antes de qualquer chamada de rede. Uma falha do `sync-board`, inclusive tempo
esgotado ou resposta cortada, não interrompe o `fetch`: o resultado a relata (`syncBoard`,
`syncBoardFailed`) e a skill pergunta se segue com o último estado. Sem `roadmap-state` válido
(endpoint ausente, `schemaVersion` diferente de 1, campo de tipo errado, data inválida ou fora dos
anos 2000 a 2100), o `fetch` é recusado sem alternativa automática. Cada sprint com mudança recebe o
seu `SPRINT_*.md`, montado com as datas do RoadS; um `move_lane` alcança a sprint de origem e a
de destino. Cada sprint é uma semana, listada na ordem das datas (`startDate`), nunca do texto do id, e a lane
casa pelo texto exato com o `laneId` do estado lido nesse `fetch`, na forma posicional antiga (`atual`, `proxima`,
`terceira`) ou na forma `sprint-DD-MM-AAAA`; uma lane sem semana nem grupo no estado lido, como a da semana que a
virada encerrou, não alcança arquivo de sprint, e o `fetch` a avisa. Pasta e arquivo novos só são
criados dentro do
`scrumRoot`, sem junção nem link no caminho, e passam pelo mesmo diff e aprovação. Itens com
`overLimit` entram no arquivo da semana depois da linha "Acima do limite de N:", na ordem do `position`, e são
avisados; `snapshotStale` indica cópia do quadro com mais de
24 h ou ausente. Marcas, backups, recusa de encolhimento e confirmação continuam como antes. Um item de sprint
com `done` verdadeiro (inclusive acima do limite), ainda sem marca no `ROADMAP.md` nem no arquivo da sprint dele, entra no
plano como uma mudança sintética `completed` (id `done-<itemId>`, com `completedOn` na data da sincronização em São
Paulo): ela passa pelo mesmo diff, aprovação, marca e verificação, mas não existe na fila do RoadS, então o `ack` só
cobre as mudanças reais e um plano só de conclusões termina com `ack: not_needed`. `roadmapSync.markCompleted`
(padrão true) desliga isso.

Depois da confirmação, o passo `gaps` completa as issues que o RoadS mostra. Ele só lê: `GET
roadmap-state` de novo (nada é consumido), e no GitHub só as issues do repositório do `config.json`,
por `gh api graphql`, com a conta ativa do `gh`. Uma URL do RoadS fora desse repositório é ignorada
e listada em `skipped`; issue fechada não é tocada. O resultado separa o que o config resolve
sozinho (`fill`) do que exige escolha (`choose`), e informa os campos do quadro sem opção
(`unfillable`). As escritas seguem a tabela aprovada pelo usuário, com o `gh` da sessão e as
permissões vigentes, só em valor vazio, e terminam relendo com `gaps`. Esse passo roda também
quando não há mudança pendente.

O passo do resumo para a diretoria (`scripts/progress_report.py`) vem logo depois da pergunta do
roadmap, em qualquer projeto, e só existe quando há um bloco `roadmapSync.progress` habilitado: o do
próprio projeto ou o do projeto que o usuário registrou como dono (`progress_report.py home --set`, com o sim
dele; o `status` informa `source`, `operationsRoot` e `homeState`, e as demais operações rodam em
`operationsRoot`). A ordem é: `status`,
aprovação do bloco, `window`, `collect`, conferência dos números pelo usuário, arquivo de textos
(guia `draftGuide`, roadmap e sprint da semana), prints em `shotsDir` com `captions.json` (ou, com
`weekShots`, na pasta do resumo que `shots --to` resolve, com a issue de cada print e pelo menos um
por entrega visível fora de `proximo`), rascunho mostrado na íntegra, aprovação e `push --draft` (com
`--to` quando há `weekShots`). A pasta é a da segunda-feira seguinte à semana do último dia do período,
com uma subpasta `<dd_MM>` por resumo; o contrato com o RoadS está em `docs/roads-contract.md`.
Nada é enviado sem a aprovação do rascunho completo. O período é só o do `window`, com hora: começa no
instante exato em que os números do resumo anterior foram coletados e chega aos coletores por
`collect --start <start> --end <end>`; a sessão nunca escolhe datas, e depois de qualquer correção roda
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
distribuição. Não use múltiplos coordenadores para o mesmo lote. Recalcule o plano
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
limite de capacidade, nunca serializa em silêncio. A sessão coordenadora é uma só: só ela pergunta
(`AskUserQuestion`), aprova, escreve no GitHub, roda uma operação negada e grava o handoff. Cada subagente
recebe um brief delimitado (resultado, caminhos próprios, testes, as regras da etapa: dados de teste,
segredos mascarados, idioma do usuário) e o que nunca faz (perguntar ao usuário, editar fora dos caminhos,
escrever no GitHub, mesclar, ampliar o escopo); uma pergunta que ele encontre volta para a sessão. O relato
de um subagente é afirmação, não evidência: a sessão lê o diff e repete os comandos medidos antes de contar,
e o revisor nunca é o autor.

**Rodadas de teste.** Por slice, rodam os módulos que a slice toca e a verificação de tipos; a suíte
rápida é a forma de conferir o todo entre slices, quando o projeto tem uma. No repositório do Frontlights
ela roda por `python tests/suite.py` com `FRONTLIGHTS_SUITE=rapida` (só Windows): a variável faz pular os
módulos de portas do `serve` e de integração do `checks`, cada um relatado como pulado com o motivo que
cita a variável (qualquer outro valor, ou a ausência dela, roda tudo; a regra está no `load_tests` de cada
módulo e vale igual para o `discover`), e o runner roda os módulos seguros em paralelo e os cinco
sensíveis numa fila serial, um por vez; `--report <arquivo>` grava o JSON da rodada como evidência.
Fica para o fim, antes da revisão independente e do merge na main local, a suíte inteira sem a variável, uma vez, pelo
`python -m unittest discover -s tests -v` (o runner não a deixa mais rápida do que o `discover`),
obrigatória com ou sem CI no projeto: onde não há CI ela é a única rede; a CI do GitHub deste
repositório roda o mesmo `discover` e não define a variável.

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
passagem de contexto; não sobrescreva nenhum registro silenciosamente. Mesmo com
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
uma verificação independente. A evidência a que a revisão ficou vinculada é salva em
`.frontlights/issues/<n>/review.json`, e `frontlights.py review-gate --root <worktree> --review <arquivo>`
a compara com a atual: saída 0 (`current`) vale, saída 2 (`stale`) significa que houve commit, edição ou
arquivo novo depois da revisão, e a issue não é relatada como revisada, nem entra na main local, nem tem PR
aberto ou atualizado sem nova revisão. Uma família de branches é integrada localmente, com a suíte completa
verde, antes de entrar na main local. A conclusão exige também que nenhum achado fique sem destino rastreável: o handoff traz a
linha "Achados sem correção e destino de cada um", e uma pendência vira critério de aceitação da issue de
origem, que só fecha com ela tratada, concluída e marcada com evidência.
