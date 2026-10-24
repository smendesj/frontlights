# Protocolo persistente e formatos dos registros

## Autoridade e pontos de aprovação

| Etapa | Permitido antes da próxima aprovação | Evidência exigida |
| --- | --- | --- |
| Atualização da skill | Consultar o remoto e mostrar o comando, sem rodá-lo | `update-check` |
| Inspeção | Ler o projeto e as fontes configuradas | Fontes, horários e limites |
| Descoberta | Entrevistar, ler código e publicar o artefato (uma página por grilling, na mesma URL; trecho de código real com segredo mascarado, nunca dado real) | Escolhas aprovadas; a URL do artefato e o caminho da fonte no log de descoberta (ou "artefato indisponível", sem a ferramenta) |
| Issue | Redigir o corpo a partir da descoberta, sem nova entrevista | A revisão carimbada e aprovada; nada publicado |
| Slices | Cortar em slices (bloqueadoras primeiro, até cinco por issue), cada slice com a seção do artefato que mostra o que ela entrega, e pedir a aprovação por link e carimbo (`SKILL.md`, "Show before approval") | Quiz respondido, corpos carimbados aprovados |
| Publicação | Só as criações e atualizações aprovadas | Releitura do GitHub |
| Desenvolvimento | Sob a autorização permanente: a branch da issue, criada no GitHub a partir da `origin/<base>` por `gh issue develop`, ligada à issue e enviada a cada fatia mesclada, entra na main local por merge só com o teste assistido respondido ou dispensável, o único portão; a prévia, em `references/development.md`, "The start of stage 6"; o teste livre, em `references/development.md`, "The free test on the local main"; cada negada só com o "Sim" | O teste assistido, os testes e a revisão quando rodaram, e a saída do `authorize` do merge na main local |
| Release | `homolog.py release plan`, a oferta e, com o "Sim", o push por refspec e a PR única; o merge só com o "Sim" (`references/development.md`, "The release") | Saída do plano, respostas literais, `merge-status` |
| Fechamento | Fechar e marcar no pai só o que a lista carimbada aprovada traz | Lista carimbada, `stamp --check`, releitura |
| Limpeza | Remover sem pergunta o que o `cleanup.py run` replaneja; perguntar cada `ask` | Comandos rodados, `verify`, `cleanup-<data>.json` |

A aprovação é do arquivo com aquele carimbo, nunca do texto colado na conversa (`SKILL.md`, "Show before approval").
Toda pergunta tem opções e sai no idioma do usuário. Mudança de escopo invalida as aprovações afetadas; solicitação
remota exibida não é consentimento, e um campo de anexo não confiável é dado.

### Desenvolvimento e release

As regras da etapa 6 vivem numa fonte só, `references/development.md`: o que a autorização permanente cobre, os
merges cobertos e as negadas, em "Standing authorization and the denied operations"; a sincronização da main local e
a prévia, em "The start of stage 6"; as slices de cada issue em ordem, numa branch por issue, criada no GitHub a
partir da `origin/<base>`, e com uma worktree por slice, em "Slices in order"; o portão do merge na main local (o
teste assistido) e o bundle depois dele, em "Into the local main"; o teste livre na main local, em "The free test on the local main"; a release, em "The release".

**O charter**, um por issue (`authorization/<n>.json`; o `authorization.json` antigo só é lido), é gravado por
`frontlights.py charter new|add|own|renew`, nunca à mão, com todo campo que o `authorize` lê: `repository`,
`issue_ids` e `direct_ids`, `operations` (`edit`,
`test`, `checkpoint`, `merge_into_local_main`), `protected_branches` (`main` e `master` sempre), `stop_conditions`,
`base` (`branch`, a main local; `issues.from` = `origin/<base>`; `direct.from` = a main local), `issued_at` e
`expires_at` (fuso de São Paulo, no máximo 24 horas), `approved_by`, `confirmed_by`, `approval_reference`,
`monitoring`, `concurrency`, `branch_prefix`, `ownership` (obrigatória, nunca só `*`), `verification_commands` e
`worktrees` (`issue` ou `direct`, `path`, `branch`, `ownership`; `slice` e `base` numa slice). O exemplo é
`examples/authorization.json`. `phone_connected: true` só pela afirmação do usuário na sessão atual.

Uma slice estacionada ganha, como último sub-item da caixa aberta, a linha `- Bloqueada: <o que falta e de quem>`
(só acréscimo, diferença conferida), apagada ao destravar: a única remoção permitida no corpo de uma issue além da
migração de uma seção legada.

### Fechamento e release

O fechamento (`scripts/closeout.py`) segue `references/closeout.md`. Uma issue com todas as caixas marcadas cuja
branch ainda não está em `origin/<base>` fica fora como `awaiting_release` até a release que a leva ser mesclada. O
`homolog.py release plan` nomeia a branch `<prefixo>release-<data>` (o prefixo do registro de autorização mais
recente por `issued_at`; os registros sem `issued_at` válido ficam abaixo dos que têm, e o empate vai para o último
nome de arquivo) e devolve `closes`, e a PR única leva o corpo do modelo `templates/pr.md`, com uma linha `Closes #n`
por issue de `closes`. A sessão age só sobre a resposta do `merge-status`, em que só `merged_into_base` vale. Para
uma sub-issue, a aprovação do fechamento inclui marcar no pai o item que a cita (`parentTicks`; o `closeout.py
tick-check` confere antes e depois). A limpeza (`scripts/cleanup.py run`, nunca com `--force`) roda antes do
fechamento, logo depois do `git pull --ff-only`, sem pergunta (`references/closeout.md`, passo 5); o único `git push
origin --delete` é o da branch da issue, quando `origin/<base>` já contém a ponta dela no GitHub, e é a sessão quem o
roda.

### Quadro e publicação

Projeto sem remoto é suportado: `repository: null` no config, no plano e na autorização, e o `publish-issue` grava
`issues/<n>/issue.json` com `source: "local"`. As regras vivem em `references/issues.md`. "Project board": toda issue de topo entra no quadro; sub-issue entra só pelo pai; o `publish-issue` publica os valores que o
`validate-plan` resolveu, com as dependências nativas por `--blocked-by`, e relê o GitHub (`blockedBy` incluído).
"Follow-ups": corrigir no PR, slice nova na issue de origem (nunca numa seção à parte) ou issue de
topo, nunca uma sub-issue nova; "citado no corpo do PR" nunca é destino. A conversão de família que já existe
(`references/family.md`, "Converting a family") é uma aprovação por família.

## Registros

Os registros ficam em `.frontlights/` no projeto de destino, fora do Git. Não altere o código do Frontlights enquanto
ele trabalha num projeto consumidor.

```text
.frontlights/
  config.json
  out/<verbo>-<AAAAMMDD-HHMMSS>-<pid>.json   saída longa que o script resumiu (_cli.emit), os 5 últimos por verbo
  discovery.md
  notes/<nome>.md          nota de exploração antes de a issue ter número
  evidencias-pendentes/    janela e prints antes do número (antes-pendente-<rótulo>.png, window.json)
  artifact.html            fonte local do artefato do grilling, publicada inteira na mesma URL
  issue.md                 corpo aprovado na etapa 4, até a publicação
  <documento>-r<N>.md      revisão anterior (`issue-r1.md` ao lado de `issue.md`), para o diff de "Show before approval"
  approvals.json           gravado por `frontlights.py stamp --approve`: path, revision, sha256 de 12 caracteres,
                           bytes, answer literal, bodies (plano: carimbo de cada body_file), stage e at
                           (ISO-8601 em -03:00)
  stamps.json              gravado por `frontlights.py stamp --revision`: a revisão e o carimbo mostrados na
                           pergunta, por caminho; o `--approve` sem `--revision` leva essa revisão
  plan.json
  authorization/<n>.json   charter de cada issue (direct-<slug>.json)
  authorization-<AAAA-MM-DD>-issue-<n>.json   charters anteriores, nunca apagados
  pitfalls.md              uma linha por critério que entrou depois da aprovação, só acréscimo
  publish/<carimbo>.json   estado do publish-issue por aprovação (o --resume lê daqui); <carimbo>-<id>.md, o corpo
  closeout-<data>.md       lista do closeout.py run; .result.json, o que o apply fez
  cleanup-<data>.json      evidência do cleanup.py run
  issues/<n>/
    worktrees/<pasta>-<tip curto>/  cópia do `.frontlights` de cada worktree da issue, feita pela limpeza
    issue.json, handoff.md, artifact.html
    notes/<nome>.md        notas depois do número
    checkpoint.json        de `checkpoint --issue <n>`; `checkpoint-<id>.json`, um por worktree de slice
    review.json            evidência da revisão a pedido (`review-gate`)
    merge-local-main-<data-hora>.json   operação do merge na main local, conferida pelo `authorize`
    *-r<k>.json            registros de uma rodada anterior, renomeados por `frontlights.py archive`
    walkthroughs/S<k>.md   roteiro rodado de uma caixa que o teste assistido não percorre
    teste-livre-cas.md     rascunho das slices novas do teste livre
    body-<tipo>-<carimbo>.md   capturas do corpo (capture, append, tick)
    browser/result.json, browser/window.json, browser/perfil-original.json, browser/brief-<passada>.md
    checks/, suite.json, suite-report-<data-hora>.json, suite-<modo>-<data-hora>.log
  direct/<branch-com-hifens>/   trabalho sem issue (o slug em `direct_ids`)
  release/pending.json, current.json, landed-<carimbo>.json   estado da release por `homolog.py release go|landed`
  release/suite.json     a suíte inteira da release (`homolog suite --release`, só a pedido do usuário), na principal
  release/suite-<sha>.json  cópia do mesmo registro por ponta (o sha completo do head), que a execução numa ponta
                         seguinte não sobrescreve; `homolog suite-gate --release --head <sha>` a julga
  release/suite-full-<data-hora>.log  saída mascarada de cada execução dela
  serve/<n>.json, preview/registry.json, preview/branch.json, preview/log/<nome>.log
  roadmap-sync/approval.json, progress-report/approval.json
```

Regras que nenhum script expressa:

- `notes/`: no máximo 300 palavras, cada achado com `caminho:linha` e o comando que o provou; sempre no
  `.frontlights` da worktree principal; o `publish-issue` a move para `issues/<n>/notes/` da primeira issue publicada. A nota é mapa, não evidência:
  quem a lê confere cada `caminho:linha` e roda o próprio teste vermelho antes de corrigir.
- `approvals.json` e as revisões `-r<N>`: a aprovação vale para os bytes daquele carimbo; um arquivo mudado pede
  aprovação nova.
- `pitfalls.md`: formato em `references/issues.md`, "A pitfall line"; o reconhecimento o lê primeiro.
- `authorization*.json`, `authorization/*.json`: release-plan, bundle, closeout e cleanup leem todos.
- `browser/result.json`: um por issue (numa família que já existe, na pasta da líder); `pastaDosPrints` diz onde
  estão os prints da rodada.
- `issues/<n>/suite.json` fica na worktree da issue; `release/suite.json`, na principal; com `homolog suite --release
  --mode full --from <registro>`, o registro da release é adotado sem rodar: guarda a execução original e a evidência
  atual da main local (copia o registro da origem inteiro (warnings incluídos), menos base, head e evidence), e
  `adoptedFrom` {path, head, tree, adoptedAt} nomeia a origem; os juízes o leem como um rodado. Os marcadores
  `{report}` e `{covered}` e os campos que acrescentam estão no `homolog.py --help`.
- `out/` fica fora da cópia que a limpeza faz; `preview/registry.json` sobrevive à issue e à sessão.

### Teste no navegador

O teste no navegador roda quando algo que a sessão entrega muda o que a pessoa vê, uma vez por issue e antes da
revisão independente (quando o usuário pede uma); é o único portão do merge na main local, na ordem `checks
regression`, `serve start`, `checks integration`, navegador e permissões entre contas, `checks smoke`, `serve stop`
da issue (nunca o da prévia). Duas passagens do mesmo cenário e da mesma conta, cada janela depois de "pronto para
assistir?": a ANTES, aberta no grilling, e no fim, só a DEPOIS. A pergunta de fechamento tem "Assistir de novo",
"Aprovado", "Precisa de alteração" e "Pode prosseguir"; o resto é de `references/browser-testing.md`.

O `frontlights.py browser-gate` lê o diff e devolve `not_needed`, `answered`, `pending`, `stale`, `contradiction` ou
`unconfigured` (saída 0 nos dois primeiros, 2 nos demais). Três comandos gravam o registro, e nenhum julga: `serve.py
window open|attach|hold|shot|close|brief` (o `shot` grava o `print` do critério e a janela guarda `cdpUrl`, `pid` e
`profileDir` em `browser/window.json`); `browser-gate ... --answer "<literal>"` (`situacao`, `aprovacao`,
`pergunta`, `lote`); `browser-gate record --pass antes|depois --criterion S<n> --head <sha>`. Antes de a issue ter número, janela e prints ficam em
`evidencias-pendentes/` e vão para a pasta da issue no primeiro comando com `--issue <n>`. A pendência
`teste_assistido` atravessa janelas por `checkpoint --pending` e `resume`.

Campos do `result.json` (esta é a única descrição; um teste os compara com o código):

- no topo: `situacao`, `aprovacao`, `pergunta`, `lote`, `assistido`, `rodadas`, `pastaDosPrints`, `criterios`, `passadas`, `registradoEm`;
- em cada passada (`passadas.antes`, `passadas.depois`): `branch`, `head`, `repeticoes`, `criterios`;
- em cada critério (`passadas.<passada>.criterios.S<n>`): `head`, `print`, `casos`, `tipoDeFalha`, `conta`, `perfil`, `origem`, `registradoEm`.

`situacao` é `pendente`, `ainda-nao`, `aprovado`, `prosseguir`, `sem-assistir`, `dispensado` ou `alteracao`;
`pergunta` traz `resposta` (literal), `opcao` e `em`; `lote` traz `issues`, `roots` (`patch-id:` do diff da
raiz; o formato antigo é remedido) e `bases` (a origem de cada medida); `criterios` no topo lista as
caixas da rodada; `casos` mapeia cada caso a `ok` ou `falha: <o que aconteceu>`; `tipoDeFalha` é `infraestrutura`,
`produto` ou `config`; `conta` é `conta 1` ou `conta 2` (nunca login nem senha); `perfil` é só `campo`, `antes` e
`depois`; `origem` é `back real` ou `interceptada`; os instantes são de São Paulo, com o fuso. Os códigos de `checks`
são 0 passou, 1 falha de produto, 2 config recusada e 3 infraestrutura. As reservas de `"port": "auto"` ficam em
`frontlights-serve/ports/` na pasta comum do Git.

### RoadS e resumo

O contrato com o RoadS (rotas, versão, mudança aditiva e quebra) está em `docs/roads-contract.md`. O Frontlights
não sincroniza roadmap nem sprint, não grava `ROADMAP.md` nem `SPRINT_*.md` e não completa as issues que o RoadS
mostra; as pastas da semana sob `roadmapSync.scrumRoot` guardam só os prints do resumo e os do teste assistido
(`evidencias/`), e as chaves da antiga sincronização são ignoradas (`roads.py status`, `obsoleteKeys`).

O resumo para a diretoria (`scripts/progress_report.py`) roda só a pedido e segue `references/progress-report.md`:
o período é só o do `window`, com hora, e chega aos coletores por `collect --start <start> --end <end>`; nada é
enviado sem o rascunho carimbado aprovado.

A unidade de trabalho é a issue do GitHub, pelo número; o Frontlights não cria `GT-NNNN` nem escreve em
`.agents/tasks/`, e um pedido de GT vira pedido de issue. O estado oficial é o do GitHub
(`gh api repos/PROPRIETARIO/REPOSITORIO/issues/NUMERO`); salvar um ponto de retomada não dá permissão de escrita lá.

### `plan.json`

O formato segue `examples/plan.json`; o `validate-plan` confere a forma e nomeia o campo que falha. Regras:

- `slices`, em ordem de dependência, bloqueadoras primeiro, cada uma com `id`, `title`, `delivers` (o que dá para
  demonstrar), `seams`, `layers`, `depends_on` e `walkthrough` (`persona`, `steps`, `before` e `after`: o roteiro da
  caixa, `references/issues.md`); recusa slice sem `delivers`, sem seams ou camadas, sem `walkthrough` ou com `before`
  vazio, e dependência inexistente, posterior ou repetida. Com `slices`, a issue dispensa `acceptance` e
  `vertical_check`.
- `parent` (uma issue do plano) ou `parent_external` (o número do pai publicado) só cabem numa filha já publicada,
  com `url`: nunca se cria sub-issue nova. Os limites de 100 filhas e 8 níveis são lidos do GitHub antes de publicar.
- `ready`, `running`, `blocked`, `verified` e `proposed` são observações locais, com o horário da consulta; uma issue
  só libera dependentes quando as alterações verificadas estão na base delas. Com branches empilhadas, a filha sai da
  branch do pai e é mesclada nela (merge coberto), e a família entra na main local pela branch do pai, com as filhas
  dentro, pelo teste assistido; nenhum push, rebase nem PR por filha (`references/family.md`, "Stacking").
- Responsabilidade desconhecida usa `*` e conflita com tudo; o planejador limita o lote a 24 issues e não detecta
  disputa oculta por recurso.

**Paralelismo.** Em toda etapa, o que não depende de outro sai ao mesmo tempo, um subagente por parte, lançados numa
única mensagem: as leituras das etapas 0 a 2, a leitura do código por área, e na etapa 6 as issues independentes e,
dentro de uma issue, as slices independentes ao mesmo tempo, cada uma na própria worktree. Só espera o que depende de
verdade: uma aprovação, um `Depende de`, um arquivo que duas partes editariam ou um recurso compartilhado (porta,
banco, pasta de reservas). Sem subagentes, a sessão avisa numa linha e registra o limite de capacidade. A sessão
coordenadora é uma só: só ela pergunta, aprova, escreve no GitHub, roda uma negada e grava o handoff; o brief segue
`references/worker.md`. O relato de um subagente é afirmação, não evidência, e o revisor nunca é o autor.

**Rodadas de teste.** O que roda em cada slice e quando está em `references/development.md`, "Which tests run when":
nenhuma suíte é portão, e as mais amplas rodam só a pedido do usuário.

## Ponto de retomada e continuação

Em cada fronteira de janela (SKILL.md, regra "Windows"), escreva `.frontlights/issues/<n>/handoff.md` na worktree
principal por `templates/handoff.md` e rode `frontlights.py checkpoint --issue <n> --next-step "<etapa, passo>"`
(`--slice S<k>` numa slice, `--pending teste_assistido` com o teste devido): ele grava `checkpoint.json` com HEAD,
branch, hashes das diferenças e dos arquivos (sem conteúdo), a issue, o hash do handoff e o próximo passo.

Na janela nova, `frontlights.py resume --issue <n>` acha o checkpoint mais recente e o handoff, e imprime
`next_step`, `slice`, `pending`, o drift (`issue_drift`, `git_drift`, `handoff_changed`) e, com `browser/window.json`,
o `serve.py window attach` da janela ANTES. O GitHub vence o handoff: em `reconcile`, releia a issue, diga cada
divergência e siga pelo GitHub; mesmo em `unchanged`, leia a issue, o handoff e o diff antes de agir.

## Contexto e conclusão

Esta seção é a casa única dos limiares de contexto; os outros textos apontam para ela. Some ao consumo medido da
sessão uma reserva para o próximo passo e rode `frontlights.py context --used <tokens> --reserve <tokens>` a cada 50
turnos. Os limiares são 100 mil, 150 mil e 200 mil tokens: abaixo de 100 mil, `continue`; de 100 mil, `handoff` (a
passagem e o checkpoint fecham a janela no próximo ponto seguro); de 150 mil, `stop` (nenhum passo novo começa); de
200 mil, `cut` (a janela termina já). Consumo desconhecido é `stop`. Com `--pending teste_assistido`, `handoff`,
`stop` e `cut` respondem também `ask_before_continuing`. Um fechamento que começa acima de ~300 mil abre em janela
nova. A base do host conta em todo turno: `update-check` e `open` com `--base <tokens do primeiro turno>` e um
`--connector <nome>` por conector devolvem `hostBase`; acima de 80 mil, a sessão diz numa linha os conectores que
não estão em `connectors` do config. O `context` confere os números informados, não o medidor do host.

A conclusão exige os critérios cobertos, as alterações completas, o teste assistido respondido (ou dispensável),
verificação de tipos quando aplicável, e os testes e a revisão só quando rodaram, cada evidência dita pelo que é.

A revisão independente roda só a pedido do usuário. O revisor julga pelo padrão de `references/review.md`, que só o
brief do revisor cita. Quando a revisão termina, a pergunta depois de uma rodada com sério ou médio e o destino dos
baixos estão numa fonte só, `references/development.md`, "When the review is done". O `frontlights.py review-gate`
compara a evidência salva em `issues/<n>/review.json` com a atual: `stale` quer dizer que houve mudança depois, e a
issue não é relatada como revisada com ela; o portão do merge na main local (o teste assistido) está em
`references/development.md`, "Into the local main". Nenhum achado fica sem destino: o handoff traz a linha "Achados
sem correção e destino de cada um", e um achado vira slice da issue de origem.
