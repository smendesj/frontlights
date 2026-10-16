# Contrato Frontlights ↔ RoadS (versão 1)

Este é o contrato do ponto de vista de quem consome: o que o Frontlights envia, o que espera
receber e como reage ao que não entende. O dono do lado servidor é o RoadS, que documenta a parte dele
no próprio repositório. Se os dois textos divergirem, abra uma issue neste repositório **antes** de
publicar qualquer mudança. Todo endereço, segredo e valor deste documento é um marcador genérico;
o endereço real fica no `.frontlights/config.json` do projeto, fora do Git.

## Regras gerais

- **Base e autenticação.** Todas as rotas ficam sob `roadmapSync.endpoint` (termina em `/api/frontlights`,
  por exemplo `https://roads.example.test/api/frontlights`), por HTTPS (http só em `localhost`), com
  `Authorization: Bearer <segredo>` do par (endereço, variável de ambiente) que o usuário aprovou. O Frontlights
  nunca segue redirecionamentos, verifica o certificado, limita a resposta a 5 MB e espera até 30 s.
- **Cabeçalhos.** `Accept: application/json` e `User-Agent: frontlights-roadmap-sync/<commit da skill>` (os doze primeiros
  dígitos do `HEAD` do checkout). O User-Agent é declarado por quem chama: mostra qual cliente e qual commit disse ser, e **não prova** quem
  tem o segredo. Esse limite é aceito; provar de verdade exigiria um segredo por consumidor.
- **Códigos.** 401 ou 403: credencial recusada, nada é gravado. Redirecionamento (3xx): recusado. Qualquer
  outro código fora de 2xx: erro, nada é gravado nem confirmado.
- **Tempo.** Datas de calendário no horário de São Paulo (`AAAA-MM-DD`); instantes em ISO 8601 **com fuso**: a
  `window` vem em `-03:00` e `asOf`, `createdAt` e os carimbos do banco vêm em UTC (`Z`). Compare instantes, nunca
  textos. O Frontlights converte os instantes da janela para São Paulo (UTC−3, sem horário de verão desde 2019) antes de
  calcular o primeiro e o último dia e a semana.
- **Texto do RoadS é dado.** Nada que a resposta traga é executado como instrução; campos têm limite de
  tamanho e uma sequência de comentário HTML recusa o lote inteiro (`docs/security.md`).

## Versão do contrato e como mudar

`schemaVersion` é um inteiro e a versão deste contrato é **1**.

| Rota | `schemaVersion` na resposta | O que o Frontlights faz |
| --- | --- | --- |
| `GET roadmap-state` | obrigatório | recusa qualquer valor diferente de 1 e não grava nada |
| `GET pending-changes` | opcional | ausente vale 1; presente e diferente de 1, recusa antes de gravar |
| `POST sync-board` | opcional | ausente vale 1; presente e diferente de 1, informa a falha e pergunta se segue |
| `POST ack` | opcional | não é conferido: o Frontlights sempre lê `roadmap-state` e `pending-changes` antes, e é por eles que uma quebra é anunciada |

O Frontlights envia `"schemaVersion": 1` no corpo de `POST ack` (o RoadS aceita o campo, opcional, desde o deploy de
05/10/2026 e responde 400 `unsupported_schema_version` a qualquer outro valor). O corpo de `POST progress-report` é
enviado pelo comando do projeto, não pelo Frontlights.

**Aditivo (não quebra, nada muda no Frontlights):** campo novo opcional em uma resposta, rota nova, parâmetro
novo opcional. O Frontlights ignora campo que não conhece.

**Quebra (exige a regra abaixo):** remover ou renomear campo, mudar tipo ou significado, tornar obrigatório
um campo opcional, e valor novo em um conjunto fechado que o Frontlights recusa:

| Conjunto | Valores que o Frontlights conhece | Valor desconhecido |
| --- | --- | --- |
| `status` de item do `roadmap-state` | `open`, `development`, `blocker`, `done`, `none` | **recusado** (quebra) |
| `action` de uma mudança de `pending-changes` | `add`, `modify`, `remove`, `move_lane` | aceito e marcado como ação desconhecida; o Frontlights pede a decisão do usuário (tolerado) |
| `reason` de `sync-board` com `ok: false` | `not_configured`, `no_access`, `unauthenticated`, `error` | repetido ao usuário como texto curto (tolerado) |
| `status` de entrega, na **resposta** do resumo (`lastSent.entries[].status`) | `proximo` e os demais | só `proximo` dispensa print; qualquer outro valor exige print (tolerado) |
| `status` de entrega, no **pedido** do resumo (o comando do projeto envia) | `concluido`, `em_validacao`, `em_andamento`, `bloqueado`, `proximo` | o RoadS recusa qualquer outro com 400: conjunto fechado |

**Regra de quebra (decisão do mantenedor):** o RoadS sobe o `schemaVersion`, abre uma issue neste
repositório e só publica a quebra **depois** que o Frontlights que a entende estiver publicado. O RoadS não serve
duas versões ao mesmo tempo: um consumidor, um dono.

**Decisão de 15/10/2026 (exceção à regra de quebra):** as sprints passaram a ser semanas identificadas pela data, e o
`laneId` deixou de ser posicional, o que é mudar o significado de um campo. Por decisão do mantenedor, o
`schemaVersion` continua 1 em `roadmap-state`, `pending-changes` e `POST ack`: o Frontlights publica primeiro a versão
que aceita as duas formas, e só depois o RoadS faz a migração, numa transação única que também reescreve as linhas
da fila ainda sem ack. Cada resposta vem inteira numa forma só, nunca as duas na mesma resposta; o que pode mudar de
forma é uma resposta para a seguinte (o último estado lido antes da migração e o primeiro depois).

## Rotas

### `POST sync-board`

Sem corpo. Executa o mesmo "Sincronizar" do botão do RoadS. Há um tempo de espera de 30 s compartilhado com
o botão e com a rotina diária: uma segunda chamada dentro dele responde `ran: false` e só informa.

```json
{ "schemaVersion": 1, "ok": true, "ran": true, "syncedAt": "2026-01-01T11:59:00Z",
  "roadmap": { "added": 2, "removed": 1, "issuesCreated": 0 } }
```

Campos opcionais que o RoadS acrescentou em 06/10/2026 (aditivos, `schemaVersion` continua 1) no resumo `roadmap`:
`retitled` (inteiro: itens cujo título acompanhou uma issue renomeada no GitHub, cada um como um `modify` na fila) e
`sprint` (contagens: `pulled`, `released`, `written`, `wouldWrite`, `failed`, `stuck` e, opcionalmente, `error`). O Frontlights
relata `retitled` e ignora `sprint`.

Falha de negócio, com HTTP 200: `{ "schemaVersion": 1, "ok": false, "reason": "no_access", "message": "texto curto" }`. A falha do
`sync-board` nunca interrompe a busca: o Frontlights a relata e pergunta se segue com o último estado.

### `GET roadmap-state`

Somente leitura; não consome nada. Sem ele não há plano: não existe alternativa automática.

```json
{ "schemaVersion": 1, "asOf": "2026-01-01T12:00:00Z", "snapshotSyncedAt": "2026-01-01T11:55:00Z",
  "maxSprintItems": 4, "timezone": "America/Sao_Paulo",
  "sprints": [ { "sprintId": "sprint-05-01-2026", "laneId": "sprint-05-01-2026", "title": "Sprint exemplo",
                 "startDate": "2026-01-05", "endDate": "2026-01-09", "items": [ "item (abaixo)" ] } ],
  "groups": [ { "laneId": "g1", "title": "Grupo exemplo", "items": [ "item, sem overLimit" ] } ],
  "removedPending": [ { "changeId": "id", "itemId": null, "title": "Item removido", "laneId": "g1" } ] }
```

Item: `id`, `position` (1 é o primeiro), `title`, `description`, `produto`, `prioridade`, `effort`,
`githubIssueUrl` e `issueNumber` (nulos sem issue), `status`, `done`, `overLimit` (só nas sprints, do
5º item em diante), `updatedAt` e `pendingChangeIds`. `snapshotSyncedAt` com mais de 24 h, ou nulo, é avisado ao
usuário.

- **Semanas por data.** Cada sprint é uma semana: `laneId` e `sprintId` são os dois `sprint-DD-MM-AAAA` (a data de
  início). Antes da migração do RoadS (decisão de 15/10/2026, acima) o `sprintId` era `sprint-AAAA-MM-DD` e o `laneId` era posicional
  (`atual`, `proxima`, `terceira`); o Frontlights aceita as duas formas e casa cada lane pelo texto exato com o
  `laneId` do estado lido no mesmo `fetch`. As semanas são tratadas na ordem de `startDate`, nunca pelo texto do id.
- **N semanas.** `sprints[]` traz a semana atual (sempre, mesmo vazia), todas as futuras que têm item e toda semana
  citada por uma mudança ainda sem ack (`lane_id` ou `from_lane_id`, inclusive a semana que a virada encerrou e a que
  perdeu o último item), estas com `items: []` quando não têm mais item e com `startDate` e `endDate` da semana
  (segunda a sexta); depois do ack, a semana vazia some na resposta seguinte. Por isso pode vir semana com
  `items: []`. As semanas vazias que a tela do RoadS mostra (a do fim, para receber o próximo arraste, e os buracos)
  nunca entram no `roadmap-state`. Semana sem mudança não ganha arquivo.
- **Ordem e limite.** `position` segue a ordem que o scrum master arrastou no RoadS (`sort_order` normalizado), e o
  arquivo da semana segue o `position`. `overLimit` continua só informativo: o Frontlights escreve no arquivo da
  semana as mudanças dos itens acima do limite como as dos demais, com os itens 1 a N primeiro e, só quando algum
  item acima do limite tem entrada no arquivo, a linha "Acima do limite de N:" uma única vez e depois os demais.

### `GET pending-changes[?since=<instante>]`

```json
{ "schemaVersion": 1, "asOf": "2026-01-01T12:00:00.000Z",
  "changes": [ { "id": "id", "action": "add", "itemId": "id", "createdAt": "2026-01-01T11:00:00Z",
                 "item": { "title": "Item", "description": "...", "produto": "...", "prioridade": "...",
                           "effort": "Medium", "githubIssueUrl": null, "lane": "...", "laneId": "..." },
                 "payload": { "from_lane_id": "lane-a", "lane_id": "lane-b", "reason": "replanning", "title": "Item" } } ] }
```

Uma mudança sem `id` utilizável, com `id` repetido ou sem título (exceto um `remove` identificado por
`itemId`) recusa a resposta inteira, sem gravar nem confirmar. O `payload` é informativo e livre por ação:
`add` traz `lane_id` e `title`; `modify` traz os campos alterados; `remove` traz `item_id`, `lane_id` e `title` (essa
parte é contrato); `move_lane` traz `lane_id` (a lane de destino) e `from_lane_id` (a de origem), as duas contrato desde
05/10/2026, mais `title` e `reason` informativos (e pode vir `github_issue_url`). Um `move_lane` feito por uma
pessoa e enfileirado antes dessa data pode não ter `from_lane_id`. Um `remove` chega com `item` e `itemId` nulos. O prefixo `done-` nos ids de mudança da fila é reservado ao Frontlights (as
conclusões que ele registra); uma mudança da fila com esse prefixo faz o Frontlights recusar a busca, então o RoadS não
deve usá-lo. Nas lanes de sprint, o `lane_id` (de `add`, `remove` e `move_lane`) e o `from_lane_id` (de
`move_lane`) citam `sprint-DD-MM-AAAA`; nas lanes de grupo continuam `tipo-*` e `g1..g6`, e o `groups[]` não muda.
Como o RoadS mantém no estado toda semana citada por mudança sem ack, uma lane que não casa com nenhuma semana nem
grupo do estado lido é inesperada: a mudança não alcança arquivo de sprint por essa lane, vai para o roadmap (e
para os arquivos das outras lanes dela), e o Frontlights avisa e pergunta antes do `apply`. O Frontlights lê de um `move_lane` o
`from_lane_id` e o `lane_id` para saber que sprints ele atinge (`from` e `to` são a grafia antiga, só usada quando a
chave nova falta); sem eles (uma fila antiga, ou um desvio futuro), o Frontlights vê só o destino, pelo que `pendingChangeIds` de
`roadmap-state` já diz. O `asOf` vem do servidor,
nunca do relógio local.

### `POST ack`

Corpo: `{ "asOf": "<o asOf devolvido por pending-changes>" }` (o RoadS também aceita `"schemaVersion": 1` e recusa
qualquer outro valor com 400 `unsupported_schema_version`). Resposta: `{ "schemaVersion": 1, "acked": N }`. O `ack` consome
**para sempre** toda mudança até `asOf`, então só vem depois de os arquivos serem gravados e de todas as
marcas serem conferidas, e o `asOf` é sempre o que `pending-changes` devolveu, nunca "agora": senão engole
uma mudança que entrou na fila entre as duas chamadas. O RoadS só sabe que o `ack` chegou, não que os
arquivos foram escritos.

### `GET progress-report` (resumo para a diretoria)

Devolve a janela a resumir, o rascunho atual e o último envio:

```json
{ "window": { "start": "2026-10-03T00:00:00-03:00", "end": "2026-10-08T00:00:00-03:00" },
  "draft": null, "lastSent": null, "weekMeeting": "2026-10-12" }
```

- `window.end` é exclusivo; o último dia do período é o dia do **último instante** da janela, não o do `window.end`:
  uma janela que termina na quinta 00:00 tem a quarta como último dia.
- **Corte por instante.** `window.start` é o `period_end` exato do último resumo marcado como enviado, e o
  `period_end` de um resumo é o instante em que os números dele foram coletados (o `window.end` que o
  Frontlights passou aos coletores com `--start`/`--end`), nunca arredondado para a meia-noite. Assim o resumo
  de quarta cobre desde o fim do de sexta, o de sexta desde o fim do de quarta, e nada fica entre dois
  e-mails nem conta duas vezes. A apresentação da semana soma os resumos enviados cujo período termina
  nela, e a lista do RoadS mostra os dois resumos e a apresentação.
- `draft`, quando existe, traz `period_start` e `period_end`. Um rascunho cujo `period_start` difere de
  `window.start` é outro resumo, quase sempre o anterior ainda não marcado como enviado: o Frontlights o
  informa em `draftOtherPeriod` e a skill para e pergunta. O RoadS guarda um rascunho por produto, e o
  `POST progress-report` de outro período responde `409` com `other_draft_pending` e não grava nada
  (mudança aditiva: um código de erro novo, sem campo removido); o mesmo `period_start` atualiza o
  rascunho, como antes. O corpo é `{ "schemaVersion": 1, "error": "other_draft_pending", "draft": {
  "period_start", "period_end" } }`, e `period_already_sent` continua sendo conferido antes.
- Os coletores do projeto recebem `--start <instante> --end <instante>` (com fuso; o início entra, o fim
  não) e gravam essa mesma janela nos arquivos de fatos e de uso; `--from`/`--to` por dias continuam
  aceitos. O Frontlights passa os mesmos valores a todos os coletores de uma coleta.
- `weekMeeting` (opcional para o Frontlights; ausente ou `null` valem como ausente): sempre uma segunda-feira, no calendário de São Paulo, e descreve
  **apenas a janela devolvida na mesma resposta**. É a segunda-feira seguinte à semana (segunda a domingo)
  do último instante da janela. Se o Frontlights enviar um período diferente do da janela, ele calcula o dia
  localmente pela mesma regra e não usa o valor do RoadS. Quando o valor vem e difere do cálculo local, o
  Frontlights avisa e usa o do RoadS para essa janela. O valor precisa ser posterior ao último dia do período e
  vir no máximo oito semanas depois da segunda-feira usual; fora disso o Frontlights o recusa, porque um valor velho
  escolheria uma pasta longe da semana.

O Frontlights não envia o rascunho: quem chama a rota de envio e a de prints (`POST progress-report`,
`POST progress-report/shots` e `POST progress-report/<id>/shots`) é o comando do projeto, que recebe o
segredo pela variável de ambiente. O formato do rascunho e dos prints é o do documento do RoadS.

## O que o RoadS faz com o Status do Project e com issues fechadas

Informado pelo RoadS a partir do código dele; vale como contrato do lado de quem consome.

- **Só o Status do Project conta.** O "Sincronizar" consulta o campo Status do Project e grava o snapshot; o estado
  aberta ou fechada da issue **não é lido** para itens de sprint. `Done` vira `status: done` e `done: true` no
  `roadmap-state`; `Open`, `Development` e `Blocker` viram `open`, `development` e `blocker`. Uma issue fechada com o
  Status ainda em Development continua contando como Development; uma tirada do Project fica na sprint sem status.
- **Item de sprint concluído fica.** Ele permanece no bloco da sprint com `done: true`, sem nenhuma mudança `remove`,
  durante toda a semana e até a primeira sincronização depois do último dia da sprint. Só a **rotação** das sprints
  o remove: quando o último dia da sprint atual já passou e a issue do item está em Done, sai uma mudança `remove`
  (`payload` com `item_id`, `lane_id`, `title`, `github_issue_url` e `reason` "sprint ended, issue done"). Na virada,
  só a semana que termina mexe: o que está em Done sai com `remove`, e o resto vai com `move_lane` (`lane_id` e
  `from_lane_id`) para o topo da semana seguinte; itens de semanas futuras não recebem `move_lane` de virada. A
  rotação roda dentro de toda sincronização (botão, rotina diária ou `sync-board`), uma vez por passagem de semana.
  Desde as semanas por data, um `remove` pode trazer também o `reason` "issue closed before its sprint"; o `reason`
  é texto livre e informativo, e o Frontlights trata esse `remove` como qualquer outro.
- **Grupos são diferentes.** A limpeza de issue fechada ou fora do Project atua só em itens de lane de **grupo**
  (backlog), onde o item sai com uma mudança `remove`.
- **Painel e Roadmap usam o mesmo snapshot.** Os contadores do Dashboard são calculados no servidor a partir do
  Roadmap guardado cruzado com o **último** snapshot, nunca do GitHub ao vivo: "Development" (itens da sprint atual em
  desenvolvimento), "Concluídas" (X de Y: Y são os itens da sprint atual agora e X os que estão em Done; um item
  removido pela rotação sai das duas contas), "Bloqueios" (a coluna Blocker do Project inteiro) e "Sprint". Em
  06/10/2026 o RoadS tirou do Dashboard os blocos "Em paralelo" e "Próxima semana" e o card "Resumo" (o Resumo
  continua na aba Resumo), renomeou "Concluídas na sprint" e "Esta sprint" e acrescentou o bloco "Slices" (as
  sub-issues das issues da sprint atual, lidas do GitHub na mesma sincronização). Nada disso é rota do contrato.
- **A sprint segue o Status do Project.** Em 06/10/2026 o RoadS passou a seguir o Project nos dois sentidos: "está na
  sprint atual" é "Status Development" (as semanas futuras existem só no RoadS), o RoadS só age quando os
  dois lados discordam (vale quem mexeu por último; empate vale o RoadS) e a escrita dele no Project nasce desligada.
  A fila de mudanças (`fetch`, `apply` e `ack`) não escreve no Project, e o Frontlights só escreve nele em passos próprios
  que o usuário aprova, como o `gaps` e o fechamento: um `move_lane` com `payload.origin` `project` (o conjunto de valores,
  `app`, `rotation`, `label` e `project`, é aberto e informativo) vai para os arquivos como qualquer outro e nunca volta
  ao Project. Um `add` pode trazer `lane_id` de uma semana (`sprint-DD-MM-AAAA`, ou `atual` antes da migração), e um `modify` pode só trocar o título: os arquivos ainda têm o
  título antigo, então a entrada se acha pelo número da issue e não pelo título.
- **Quando aparece.** Ao apertar Sincronizar, na hora. Uma sincronização feita até 30 s depois de outra (de qualquer
  origem: botão, rotina diária, `sync-board` do Frontlights) não consulta o GitHub e devolve o snapshot anterior. Sem
  sincronizar, recarregar a página só relê o que está guardado.
- **Consequência para o Frontlights.** Fechar uma issue sem mover o cartão para Done não muda nada no RoadS. Os arquivos
  `.md` recebem a fila de mudanças (`add`, `modify`, `remove`, `move_lane`) e, a partir da 0.18.0, a conclusão de um
  item de sprint lida só do `done` do `roadmap-state` (`roadmapSync.markCompleted`, padrão true): o Frontlights a registra
  como "concluída", com a data da sincronização, mesmo sem mudança na fila, e nunca a confirma ao RoadS. Um item
  concluído que fica na sprint tem, então, o registro de conclusão e, depois da rotação, o `remove`.

## Fatos do resumo: a família inteira de cada entrega

O `facts.json` é gerado pelo coletor do projeto (no RoadS, `scripts/progress/github.ts`); o Frontlights só o lê. Uma entrega
é uma issue de topo e **representa a família inteira**: ela e todas as sub-issues abaixo dela, em qualquer profundidade.
Os campos abaixo são **aditivos** (o Frontlights ignora o que falta e não quebra com o que sobra); a regra de quebra desta
página não se aplica a eles, mas o que o Frontlights faz com cada um está na referência `progress-report.md`.

- `scope` (texto): o produto do resumo. Entregas, dificuldades e próximos passos saem só dele; o uso do Claude é a única
  exceção e cobre os projetos conectados.
- `entries[].subIssues` (`{ "total", "done" }`): as **partes** da família, contadas pelas folhas da árvore inteira (uma
  sub-issue que tem filhas conta pelas filhas; folha fechada como não planejada fica fora dos dois números), e
  quantas estão prontas. Numa entrega **sem sub-issues**, as partes são as caixas da seção de critérios de aceitação
  do corpo (as slices da etapa 5): `total` = caixas, `done` = marcadas, lidas com as regras do `closeout.py` do
  Frontlights (título da seção, itens com ou sem recuo, código cercado e comentários ignorados); uma família com
  sub-issues segue pelas folhas e as duas contagens nunca se misturam; sem filhas e sem caixas, `null` (conta 1 em
  `delivered`). Decisão de 14/10/2026, em produção no RoadS. O e-mail e a visão semanal do RoadS escrevem "X de Y
  partes prontas" sozinhos, então o texto do Frontlights não repete a contagem; número de issue nunca vai ao texto.
- `entries[].slices` (em entrega com sub-issues ou com caixas): `{ "closed": [{ "title", "closedAt" }], "blocked":
  [{ "title", "reason" }] }`, as partes de qualquer nível fechadas como concluídas no período e as bloqueadas (aberta
  com o rótulo `status:blocker`, ou com cartão em Blocker no fim do período), só como evidência para quem escreve: não
  vão ao e-mail nem ao conteúdo montado. Numa entrega por caixas, `closed` traz as caixas marcadas no período, com
  `title` = o texto da caixa até a primeira frase (um rótulo curto como "S1." não conta como frase; até 120
  caracteres) e `closedAt` = a edição do corpo que a marcou, lida do histórico de edições do GitHub
  (`userContentEdits`, até 100 edições), em instante com fuso; uma caixa cuja marcação o histórico não alcança, ou um
  histórico que não pôde ser lido, conta sem data e nunca como "marcada no período" (o coletor avisa). `blocked` traz
  as caixas abertas com o sub-item "Bloqueada:" logo abaixo, e `blocked[].reason` (campo opcional, aditivo,
  14/10/2026) é o resto dessa linha. A convenção "Bloqueada:" é do Frontlights: um sub-item sem caixa, mais recuado
  que uma caixa aberta e logo abaixo dela (uma linha de lista no mesmo nível ou acima desfaz o vínculo), cujo texto
  começa com "Bloqueada:" sem importar acento, maiúsculas, negrito ou itálico. Se o RoadS cortar a leitura da árvore,
  `ignored.cut` conta quantas issues ficaram sem leitura completa e a entrada traz a linha de evidência dizendo isso:
  o Frontlights repassa o aviso ao usuário.
- `sprint` (bloco) e `delivered`: as capas da sprint são os itens do Project em Development (épicos incluídos) e **não
  são entregas**. `sprint.epics[]` traz, por capa, `issue`, `title`, `issues` (`total`, `done`), `parts` (`total`, `done`,
  `remaining`, contadas pelas folhas da árvore ou, numa capa sem sub-issues, pelas caixas de critério) e `open` (as
  issues que faltam; vazio numa capa sem filhas, que traz `issues` `{ total: 1, done: 0 }`); `delivered` traz `issues`
  (as entregas concluídas no período, esteja ou não na sprint) e `parts` (a soma das partes prontas, em que uma
  entrega sem filhas e sem caixas conta 1). Os dois vão ao conteúdo montado: o e-mail e a visão semanal mostram
  **"Concluído: N partes em M issues"** (tudo o que foi entregue na janela) e **"Em andamento: N partes em K issues"**
  (o que resta das capas da sprint), sem o chip "Em validação". Decisão de 07/10/2026; vale para todo resumo; desde
  14/10/2026 os textos do RoadS dizem "partes" no lugar de "sub-issues" (o e-mail já enviado não muda). O texto do
  Frontlights não repete esses números, e os próximos passos saem do que resta em cada capa.
- **Atividade da família.** PR mesclado ou aberto, commit e fechamento de qualquer descendente dentro do período contam
  como atividade da entrega. Uma entrega com partes entregues no período nunca fica em `proximo` (que dispensa o print).
  O `status` continua vindo do coletor e só dele.
- **Entrega por caixas.** A situação segue o PR e o fechamento, como numa issue avulsa: caixa aberta não é "filha
  pendente", e caixa marcada no período conta como atividade e trabalho feito (nunca `proximo`). Uma issue fechada com
  caixas abertas mostra o que está marcado e ganha na evidência "Concluída com N caixas dos critérios de aceitação
  ainda abertas". No Dashboard, o bloco Slices mostra uma linha por caixa (CONCLUÍDO, A FAZER ou BLOQUEADO) para a
  issue da sprint sem sub-issues; nada disso é rota do contrato.
- **Prints.** O print é exigido por entrega (a issue de topo). O Frontlights guarda o print de uma parte com o número da
  entrega em `captions.json`, então o RoadS não precisa aceitar número de sub-issue ali.

## Pasta dos prints do resumo (`weekShots`)

`<scrumRoot>/<weekFolderPattern da segunda>/<weekShots>/<dd_MM do último dia do período>`, em que a segunda
é a de `weekMeeting`. Cada resumo tem a sua subpasta, com o seu `captions.json` e os seus prints: dois
resumos da mesma semana (quarta e sexta) nunca dividem arquivo. Prints salvos antes da subpasta, direto em
`weekShots`, ainda são lidos (com aviso) quando a subpasta do dia não existe e a pasta plana tem `captions.json`.

## O que ainda não está provado

- Os caminhos de erro (tempo esgotado do `sync-board`, 401 com segredo trocado, `schemaVersion` desconhecido,
  marcas recusadas) só têm cobertura simulada nos testes; a produção real exercitou o caminho
  feliz.
- As semanas por data (15/10/2026: ids `sprint-DD-MM-AAAA`, N semanas, excedente escrito, lane sem par avisada) só
  têm cobertura simulada até a primeira sincronização real depois da migração do RoadS, e a semana encerrada vir
  vazia no estado até o ack é promessa do RoadS ainda não vista numa resposta real.
- A contagem de partes por caixas (14/10/2026) ainda não apareceu num resumo real: no período de 09/10 a 13/10
  nenhuma entrega usava caixas, e a coleta real não mudou.
- O RoadS registra, das chamadas feitas com segredo válido, o método, a rota, o status, o User-Agent declarado
  (cortado em 200 caracteres) e a duração, e guarda por 90 dias. Isso prova qual cliente e qual versão disseram
  chamar, não quem tem o segredo.
- O `sync-board` ainda não declara um tempo máximo no RoadS e a duração dele não foi medida: o Frontlights espera 30 s,
  e um tempo esgotado é erro tolerado (o Frontlights relata e pergunta se segue com o último estado).
