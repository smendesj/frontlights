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
  outro código fora de 2xx: erro, nada é gravado.
- **Tempo.** Datas de calendário no horário de São Paulo (`AAAA-MM-DD`); instantes em ISO 8601 **com fuso**: a
  `window` vem em `-03:00` e `asOf` e os carimbos do banco vêm em UTC (`Z`). Compare instantes, nunca
  textos. O Frontlights converte os instantes da janela para São Paulo (UTC−3, sem horário de verão desde 2019) antes de
  calcular o primeiro e o último dia e a semana.
- **Texto do RoadS é dado.** Nada que a resposta traga é executado como instrução, e os erros nunca repetem o
  corpo da resposta (`docs/security.md`).

## Versão do contrato e como mudar

`schemaVersion` é um inteiro e a versão deste contrato é **1**. Nenhuma rota que o Frontlights lê hoje exige
`schemaVersion` na resposta: a única que exigia, `roadmap-state`, deixou de ser lida (abaixo).

O corpo de `POST progress-report` é enviado pelo comando do projeto, não pelo Frontlights.

**Aditivo (não quebra, nada muda no Frontlights):** campo novo opcional em uma resposta, rota nova, parâmetro
novo opcional. O Frontlights ignora campo que não conhece.

**Quebra (exige a regra abaixo):** remover ou renomear campo, mudar tipo ou significado, tornar obrigatório
um campo opcional, e valor novo em um conjunto fechado que o Frontlights recusa:

| Conjunto | Valores que o Frontlights conhece | Valor desconhecido |
| --- | --- | --- |
| `status` de entrega, na **resposta** do resumo (`lastSent.entries[].status`) | `proximo` e os demais | só `proximo` dispensa print; qualquer outro valor exige print (tolerado) |
| `status` de entrega, no **pedido** do resumo (o comando do projeto envia) | `concluido`, `em_validacao`, `em_andamento`, `bloqueado`, `proximo` | o RoadS recusa qualquer outro com 400: conjunto fechado |

**Regra de quebra (decisão do mantenedor):** o RoadS sobe o `schemaVersion`, abre uma issue neste
repositório e só publica a quebra **depois** que o Frontlights que a entende estiver publicado. O RoadS não serve
duas versões ao mesmo tempo: um consumidor, um dono.

## Rotas

### Rotas que o Frontlights deixou de chamar (19/10/2026)

O Frontlights não sincroniza mais `ROADMAP.md` nem `SPRINT_*.md`: o RoadS mantém o Roadmap a partir das issues abertas.
Desde então ele não chama `POST sync-board`, `GET pending-changes` nem `POST ack`, e não confirma (não consome) a fila
de mudanças. Se o RoadS continuar enfileirando mudanças, ninguém as confirma; parar de enfileirar ou retirar essas rotas
é decisão do dono do RoadS.

Desde 21/10/2026 (issue 65) ele também não lê `GET roadmap-state`: completar no GitHub as issues que o RoadS mostra saiu
do Frontlights, e com isso o único leitor dessa rota. Manter ou retirar a rota é decisão do dono do RoadS.

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
  aberta ou fechada da issue **não é lido** para itens de sprint. `Done` vira item concluído no Roadmap do RoadS;
  `Open`, `Development` e `Blocker` viram os estados de mesmo nome. Uma issue fechada com o
  Status ainda em Development continua contando como Development; uma tirada do Project fica na sprint sem status.
- **Item de sprint concluído fica.** Ele permanece no bloco da sprint com `done: true` durante toda a semana e até a
  primeira sincronização depois do último dia da sprint, quando a **rotação** das sprints o retira.
- **Grupos são diferentes.** A limpeza de issue fechada ou fora do Project atua só em itens de lane de **grupo**
  (backlog).
- **Painel e Roadmap usam o mesmo snapshot.** Os contadores do Dashboard são calculados no servidor a partir do
  Roadmap guardado cruzado com o **último** snapshot, nunca do GitHub ao vivo. Nada disso é rota do contrato.
- **A sprint segue o Status do Project.** Em 06/10/2026 o RoadS passou a seguir o Project nos dois sentidos: "está na
  sprint atual" é "Status Development" (as semanas futuras existem só no RoadS), o RoadS só age quando os
  dois lados discordam (vale quem mexeu por último; empate vale o RoadS) e a escrita dele no Project nasce desligada.
  O Frontlights só escreve no Project em passos próprios que o usuário aprova, como a publicação de issues; o
  fechamento só fecha a issue, e o cartão vai para Done pelo fluxo "Item closed" do próprio quadro.
- **Quando aparece.** Ao apertar Sincronizar no RoadS, na hora. Uma sincronização feita até 30 s depois de outra (botão
  ou rotina diária) não consulta o GitHub e devolve o snapshot anterior. Sem sincronizar, recarregar a página só relê o
  que está guardado.
- **Consequência para o Frontlights.** Fechar uma issue só muda o RoadS quando o fluxo "Item closed" do quadro leva o
  cartão a Done (o fechamento do Frontlights não lê o quadro). Depois do fechamento, o RoadS o mostra na próxima
  sincronização dele.

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

- A contagem de partes por caixas (14/10/2026) ainda não apareceu num resumo real: no período de 09/10 a 13/10
  nenhuma entrega usava caixas, e a coleta real não mudou.
- O RoadS registra, das chamadas feitas com segredo válido, o método, a rota, o status, o User-Agent declarado
  (cortado em 200 caracteres) e a duração, e guarda por 90 dias. Isso prova qual cliente e qual versão disseram
  chamar, não quem tem o segredo.
