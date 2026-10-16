# Frontlights — skill para Claude Code

Uma skill do Claude Code que conduz **qualquer pedido seu** — uma funcionalidade,
um bug, uma refatoração, uma pesquisa, um script pontual, um documento — por
descoberta do problema, o corpo da issue aprovado (a spec é a issue), issues
verticais no GitHub e implementação com testes e autorização delimitada. O
caminho é dimensionado ao pedido: trabalho pequeno é feito direto, sem
issue. Observações do RoadS são uma entrada **opcional**, usada quando
configurada; nada exige RoadS para começar. Uma única skill, com um arquivo de
referência por etapa e os scripts, modelos e exemplos dentro dela. Não depende do GuardianS nem
altera sua instalação. O Frontlights se chamava Workflows, renomeado para não colidir com os
workflows do próprio Claude Code, e foi um plugin até a 0.28.1; desde então é uma skill avulsa.

**Situação:** versão candidata à 1.0, para **uso supervisionado no Windows**. O núcleo do fluxo, o
teste de navegador assistido (aplicado à mão na versão anterior) e a integração com o RoadS foram
exercitados em sessões reais de um projeto de produto; as [evidências de aceitação](docs/acceptance.md) dizem o que está provado, o que
falta e os limites. A 1.0 sai depois de uma sessão real que cumpra os itens 12 e 13 do
[roteiro](evals/runbook.md) com esta versão. **Não** são garantidos: a execução sem supervisão (a
skill instala só o hook `pre-push` da homologação, com o seu "Sim", e nenhum hook de permissão, então o teto de
contexto e o escopo exato das permissões não são impostos por ela), o `authorize` (apenas consultivo) e
qualquer sistema fora do Windows.

## Idioma

A documentação, os modelos, os exemplos e os conteúdos apresentados ao usuário
são em português. As skills, destinadas ao modelo, são escritas em inglês, mas
orientam a produção de respostas e documentos em português. Comandos, caminhos,
chaves de configuração e identificadores técnicos mantêm sua grafia original.

## Instalar

Requer Claude Code com suporte a skills e `AskUserQuestion`, Python 3.11+, Git e, para
consultar o GitHub, GitHub CLI autenticado. Não exige pacotes Python adicionais.

A skill é a pasta `skills/frontlights` deste repositório, com tudo o que uma sessão usa:
`SKILL.md`, `references/`, `scripts/`, `templates/`, `examples/` e `docs/` (protocolo e
segurança). Instale-a apontando a pasta de skills do usuário para o clone, por uma junção:

```powershell
git clone https://github.com/smendesj/frontlights.git <pasta-do-clone>
cmd /c mklink /J "$HOME\.claude\skills\frontlights" "<pasta-do-clone>\skills\frontlights"
```

A junção não copia nada: `~/.claude/skills/frontlights` passa a ser a própria pasta do clone,
então `git pull` no clone já atualiza a skill instalada, e uma sessão nova a lê. Para desinstalar,
`rmdir "$HOME\.claude\skills\frontlights"` apaga só o atalho. Quem prefere uma cópia pode copiar
a pasta `skills/frontlights` para `~/.claude/skills/frontlights`, lembrando de recopiar a cada
atualização. `tests/`, `evals/` e a documentação da raiz servem a quem desenvolve o Frontlights
e ficam fora da skill.

Até a 0.28.1 o Frontlights era um plugin instalado por marketplace; esse caminho não existe
mais. Quem o tem instalado assim remove com `claude plugin uninstall frontlights@frontlights`
antes de criar a junção, para não carregar os dois.

### Invocar com `/frontlights`

Em qualquer sessão:

```text
/frontlights
```

A skill define a ordem das etapas e lê o arquivo de cada etapa em `skills/frontlights/references/`
só quando chega nela. O `CLAUDE.md` da raiz orienta quem trabalha neste repositório; o Claude não
o carrega nos projetos que usam a skill.

Preserve os pontos de retomada e as cópias de trabalho isoladas do Git (worktrees). O único hook que a skill
instala é o `pre-push` da homologação (`homolog hook`), depois do seu "Sim" a uma pergunta que mostra o script;
nenhuma configuração ou rotina automática de interceptação de permissões é instalada.

#### Início por linguagem natural

Uma frase comum ("frontlights, ataque a issue <n>", "ativar frontlights") pode abrir o mesmo estágio 1,
se o modelo decidir invocar a skill: a `description` dela lista esses gatilhos e a skill aceita a
invocação pelo modelo. Isso reduz a falha, mas não a elimina: já houve a frase lida como pedido à
sessão vizinha do próprio Frontlights, com o estágio 1 só abrindo quando a pessoa escreveu de novo.

Para um lembrete a cada prompt há um hook **opcional**, que a skill não instala: o modelo
`skills/frontlights/templates/frontlights-prompt-hook.py` (evento `UserPromptSubmit`). Ele só injeta um lembrete de abrir o
`/frontlights` quando o prompt cita a skill; não decide nada pelo modelo, nunca bloqueia (sai sempre com
0) e fica calado se o prompt já é o comando, se a palavra está num caminho ou nome de arquivo, se a
sessão está aberta no repositório do próprio Frontlights ou se o transcrito já mostra o Frontlights aberto. Para ligar:

```powershell
New-Item -ItemType Directory -Force "$HOME/.claude/hooks" | Out-Null
Copy-Item skills/frontlights/templates/frontlights-prompt-hook.py "$HOME/.claude/hooks/frontlights-prompt-hook.py"
```

e acrescente ao `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python \"$HOME/.claude/hooks/frontlights-prompt-hook.py\"" } ] }
    ]
  }
}
```

Ajuste o caminho se o seu shell não expandir `$HOME`. Os testes cobrem o script; a execução dele pelo
Claude Code a cada prompt ainda não foi homologada numa sessão real.

## Acompanhar pelo celular (máquina fixa no app)

O `/frontlights` não verifica o Remote Control ao começar e não faz pergunta
sobre celular. Para deixar o PC disponível no app Claude do celular, siga estes
passos por conta própria:

1. Abra um PowerShell, fora do app desktop, e entre na pasta do projeto.
2. Rode `claude rc` nessa pasta. Se pedir para confiar na pasta, aceite. Se não
   pedir e o comando não iniciar, rode `claude` na pasta para confiar, saia com
   `/exit` e rode `claude rc` de novo.
3. Deixe a janela aberta, uma por projeto.
4. No celular, inicie uma sessão pelo dispositivo e escolha o repositório. A
   sessão fica sincronizada entre o celular e o desktop.

```powershell
cd "C:\caminho\do\projeto"
claude rc
```

Fechar a janela tira o dispositivo do ar. Depois de reiniciar o PC ou o Claude,
repita os passos 1 e 2 em cada pasta: as sessões voltam sincronizadas (observado
em um teste em uma máquina, sem garantia).

O Frontlights não lê nem altera os ajustes de energia do PC. Com a tampa fechada ou o
PC em suspensão, o dispositivo pode sair do ar.

## Configurar um projeto

Copie `examples/config.json` para `.frontlights/config.json` no projeto de destino,
defina o repositório exato no formato `proprietario/repositorio` e mantenha
`.frontlights/` ignorado pelo Git desse projeto. Um projeto sem remoto usa
`"repository": null`: o GitHub aparece como `unconfigured`, o plano usa
`url: null` e as issues ficam em `.frontlights/issues/<n>/`, com `source: "local"`.
As branches de trabalho usam o `branch_prefix` da autorização, com padrão `claude/`, são cortadas da main local do
projeto (a homologação) e ficam só locais até a release. Para o backup da homologação, a chave `homolog.backupDir`
aponta uma pasta sua, por caminho absoluto (por exemplo `"C:\\PASTA\\DE\\BACKUP"`, de preferência sincronizada
com a nuvem): a cada merge na main local o Frontlights grava ali um bundle Git da main local e das branches de
trabalho (`homolog bundle`); sem a chave, nada é gravado e a sessão só avisa. Configure o RoadS somente quando o
endereço real de consulta autenticada e o formato da resposta forem conhecidos:

```json
{
  "repository": "PROPRIETARIO/REPOSITORIO",
  "roads": {
    "observations_url": "https://SEU-APLICATIVO.example/api/SUA-ROTA-DE-CONSULTA",
    "token_env": "FRONTLIGHTS_ROADS_TOKEN"
  }
}
```

O endereço acima é ilustrativo; não representa uma API garantida do RoadS.

### Quadro de projeto do GitHub

Quando as issues do repositório são controladas num quadro (GitHub Projects), configure
`project`. Com ele definido, toda issue de topo entra no quadro; sub-issue entra só pelo pai.
Cada issue de topo criada pelo Frontlights entra com responsável, tipo, labels e campos preenchidos,
e é relida para conferir:

```json
{
  "repository": "PROPRIETARIO/REPOSITORIO",
  "project": {
    "owner": "PROPRIETARIO",
    "number": 1,
    "assignee": "@me",
    "issue_type": "Task",
    "fields": {"Status": "Open", "Area": null}
  }
}
```

- `owner` e `number` identificam o quadro (`github.com/orgs/<owner>/projects/<number>`).
- `fields` associa cada campo do quadro a um valor padrão; `null` obriga a escolher o valor
  de cada issue no plano aprovado (`project_fields` da issue no `plan.json`).
- `issue_type` é o tipo nativo da issue (`gh issue edit --type`); uma issue do plano pode
  trocá-lo com `issue_type`. `assignee` usa `@me` para quem está autenticado no `gh`.
- `python scripts/frontlights.py validate-plan --plan plan.json --config .frontlights/config.json`
  recusa o plano enquanto faltar valor para algum campo.
- `done` é opcional e diz qual campo e valor significam "concluída": `{"field": "Status", "value": "Done"}`
  é o padrão. O fechamento de issues move o cartão para esse valor; o campo precisa ser de escolha única
  e o valor precisa existir entre as opções.
- O token do `gh` precisa do escopo `project` (`gh auth refresh -s project`).
- Um campo do quadro sem nenhuma opção cadastrada não aceita valor: não o declare em `fields`,
  que passaria a recusar todo plano.

Para que a issue nasça com tudo preenchido, o `project` aceita três blocos opcionais. O vocabulário
do projeto (nomes de label, de tipo e de linha) fica só no `config.json` do projeto de destino:

```json
{
  "project": {
    "owner": "PROPRIETARIO",
    "number": 1,
    "assignee": "@me",
    "issue_type": "Task",
    "fields": {"Status": "Open", "Area": null, "Prioridade": null},
    "labels": {
      "require_prefix": ["tipo:"],
      "by_field": {
        "Area": {"Backend": ["area:backend"], "Frontend": ["area:frontend"]},
        "Prioridade": {"High": ["prioridade:alta"], "Critical": ["prioridade:alta"]}
      }
    },
    "issue_type_by_label": {"tipo:bug": "Bug", "tipo:feature": "Feature"},
    "body_fields": {"Esforço estimado": ["Low", "Medium", "High", "Very High"]}
  }
}
```

- `labels.require_prefix`: cada issue de topo precisa trazer ao menos um label de cada família
  (`labels` da issue no plano). `labels.by_field` acrescenta, sozinho, os labels que o valor de
  um campo implica. A família exigida nunca é deduzida de um campo.
- `issue_type_by_label`: o tipo nativo que um label implica. A ordem de escolha é a do plano
  (`issue_type`), depois o do label, depois o `issue_type` padrão do quadro.
- `body_fields`: uma linha `**Nome:** valor` no corpo, com lista fechada de valores
  (`body_fields` da issue no plano), para o que o quadro não tem como guardar, como um esforço.
- Com qualquer um dos três, o `validate-plan --config` imprime também `resolved`: por issue de
  topo, os valores do quadro, os labels finais, o tipo nativo e as linhas do corpo. A publicação
  usa exatamente isso. Sem os blocos, a saída e as regras são as de antes. Sub-issue não leva
  `labels` nem `body_fields`: herda do pai. Uma issue que já existe (o plano traz o `url` dela) não
  precisa de `body_fields`, porque o texto que já estava no corpo nunca é editado (a spec e as
  slices entram só por acréscimo).
- Um label (do plano ou do `config.json`) usa só letras, números e `: . / + -` ou espaço no meio,
  até 50 caracteres, sem terminar em `: . / -` nem em espaço e sem hífen depois de espaço: nada que
  um terminal interprete (aspas, `$`, crase, `;`, `&`, `|`, vírgula). Letras acentuadas precisam
  estar na forma composta (não decomposta). Labels são comparados sem diferenciar maiúsculas, como o
  GitHub faz; duas issues com `area:backend` e `Area:Backend` são o mesmo label.
- O texto que o `config.json` manda digitar em comandos `gh` (`issue_type`, valores de
  `issue_type_by_label`, nomes e padrões de `fields`, `labels.require_prefix`) tem até 100 caracteres
  e não pode ter `$`, crase, aspas duplas (as retas e as tipográficas `“ ” „`, que o Windows
  PowerShell também trata como aspas; `‟ ″ ＂` também são recusadas, por precaução, só porque
  parecem aspas), `\` nem caractere de controle. `assignee` é `@me`, `@copilot` ou um login do GitHub
  (letras, números, `-`, `_` e o sufixo `[bot]`). O mesmo vale, no plano, para os valores de
  `project_fields` (sem limite de tamanho, mas numa linha só: reescreva o texto se ele trouxer
  aspas ou `$`) e para `issue_type`. Não se cobrem o `cmd.exe` (`%`), que o Frontlights não usa, nem a
  expansão `!` do bash interativo. O título da issue segue o que já valia: o plano aprovado o define
  e a sessão o digita como um único argumento entre aspas duplas; um título com esses caracteres
  deve ser criado por `gh api` com o corpo num arquivo JSON.
- Um label que um campo implica não pode deixar a issue com dois labels da mesma família (o trecho
  até o primeiro `:` ou `/`, como `area:` ou `area/`; famílias separadas por outro caractere, como
  `area-backend`, não são reconhecidas): no plano isso é recusado, nomeado ou não o label implícito
  e também quando dois campos diferentes implicam labels da mesma família (um único valor, como
  `Both`, pode implicar `area:frontend` e `area:backend` de propósito), e no `gaps` vira `labelConflicts`
  para você decidir.
- `roadmapSync.issueTargets` só conhece `repository` e `project` (`owner` e `number`); chave a mais,
  por exemplo um `project` copiado do bloco do topo com `assignee` ou `fields`, passa a ser recusada em
  toda operação de sincronização. O `owner` segue a mesma regra de login do `project` do topo (letras,
  números e `-`) e o `number` é um inteiro positivo, porque o `owner` é digitado em `gh project
  item-add`. As regras do quadro são as do `project` do topo.
- O `project` recusa chave desconhecida, para que um erro de digitação (`label_rules` em vez de
  `labels`) não desligue a regra em silêncio. O `inspect` mostra as regras lidas.

Achados de revisão, de testes ou de conferência ligados a uma issue não viram uma issue
de topo cada. O Frontlights propõe o destino de cada achado, nesta ordem, com três
destinos: corrigir no mesmo PR, critério de aceitação novo na issue de origem e, só para
escopo novo ou problema que atravessa várias issues, issue de topo, nunca uma sub-issue
nova. O lote inteiro é decidido numa única pergunta.

**Conversão de famílias.** Antes de agir numa família (pai com sub-issues abertas), o Frontlights
oferece convertê-la numa issue só, com uma CA por filha aberta; um pedido como "arrume as issues
do MVP" faz a mesma conversão em lote, uma família por vez. O antes e o depois são mostrados por
inteiro, há uma aprovação por família, o corpo do pai é substituído (o anterior fica guardado), as
filhas são fechadas como "Convertida em CA S<k> da #<n>" e saem do quadro só com o "Sim" de cada
operação, e uma família com mais de cinco filhas vira duas ou mais issues de topo ligadas por
blocked-by. Nunca uma sub-issue nova.

O Frontlights não cria sub-issues: uma família que já existe (filhas publicadas antes
desta regra) continua lida, trabalhada e fechada como antes, filhas antes dos pais, e o
`validate-plan` recusa uma issue proposta com `parent` ou `parent_external`, ou sem o `url`
dela. No
`plan.json`, uma filha já publicada leva `parent` com o id do pai, que precisa estar no
mesmo plano, e dispensa `project_fields`; o `validate-plan` recusa `parent` igual ao
próprio id, pai fora do plano, mais de 100 filhas por pai no plano e mais de 8 níveis de
aninhamento. As dependências entre as issues de um plano nascem como relação nativa do
GitHub (`gh issue create --blocked-by`), com as bloqueadoras publicadas primeiro, na ordem
que `frontlights.py publish-order --plan <plano>` imprime, e são relidas em `blockedBy`;
a linha `Depends on:` do corpo é texto de apoio. O pai só é dado como concluído com as
filhas fechadas; um achado depois do fechamento de uma issue vira issue de topo que a
cita, e o Frontlights nunca reabre uma issue.

Uma pendência que não é corrigida no PR não fica só no texto do PR, que ninguém
acompanha e que some depois do merge: ela vira um critério `- [ ] Pendência (achado da
revisão): ...` dentro da seção de critérios de aceitação da issue de origem, com a
evidência que o fechará. Como altera o escopo da issue, o texto exato é mostrado e
aprovado no lote antes de ser escrito (corpo anterior guardado, só acréscimo, releitura e
diferença conferidas; só a migração de uma seção legada também remove linhas). A issue só fecha com a pendência tratada, concluída e marcada com
evidência, como qualquer critério, e o fechamento (veja abaixo) já a enxerga; enquanto
houver uma aberta, o PR cita a issue sem palavra de fechamento (`Closes`, `Fixes`). Antes
de relatar uma issue como revisada ou concluída, antes do merge na main local e antes de abrir ou atualizar um PR,
todo achado em aberto tem destino rastreável; "citado no corpo do PR" nunca é destino, e
só ruído que não é defeito (um 404 de arquivo que só falta no disco local, dado de teste)
pode ficar como texto, dito como "não é defeito" com a evidência. O `handoff` registra
"Achados sem correção e destino de cada um". Isso é regra da skill, não barreira do
Frontlights: o que o Frontlights garante é que o fechamento conta a pendência como critério.

Sem `project`, ou com `"project": null`, as issues não entram em quadro nenhum; num
repositório de organização, o Frontlights pergunta qual quadro usar antes de publicar.
O utilitário envia somente GET, obtém o token da variável de ambiente indicada,
recusa redirecionamentos e não confirma nem consome filas. Verifique se o endereço
real permite apenas leitura. Nenhum endereço ou credencial do RoadS foi presumido
a partir de outro plugin. A consulta ao quadro e ao planejamento de entregas exige
ferramentas configuradas separadamente; o utilitário consulta issues do GitHub e
uma rota JSON de observações. Integrações ausentes são informadas explicitamente.

### Sincronizar sprint e roadmap com o RoadS

Toda sessão `/frontlights` começa perguntando se a sprint e o roadmap devem ser atualizados
de acordo com o RoadS. Com a resposta "sim", o Frontlights:

1. pede ao RoadS que sincronize o quadro (o mesmo "Sincronizar" do botão) e informa quantos
   itens entraram e saíram (e quantos foram renomeados, quando o RoadS informa). Se o RoadS
   sincronizou há menos de 30 s, só avisa. Se a sincronização falhar, pergunta se você quer
   seguir com o último estado;
2. lê o estado do roadmap (sprints, datas, itens e limite) e busca as mudanças que um Scrum
   Master fez no Roadmap do RoadS. Sem esse estado, a sincronização para com um erro claro: não há
   alternativa automática. Se a cópia do quadro no RoadS tiver mais de 24 h, ou nunca tiver sido
   feita, você é avisado;
3. escreve a prosa em cópias temporárias do `ROADMAP.md` do ano e do `SPRINT_*.md` de cada
   sprint que tem mudança. A pasta e o arquivo de uma sprint nova são criados dentro do
   `scrumRoot`, seguindo os títulos e as seções do `SPRINT_*.md` mais recente. O mesmo vale para as conclusões: um item de sprint que o RoadS mostra como concluído (`done`, inclusive acima do
   limite da sprint) e que ainda não foi registrado entra no plano como "concluída", com a data da **sincronização** (não a da
   entrega), no `ROADMAP.md` e no arquivo da sprint dele. Isso vem só do `done` do estado, nunca de a issue estar
   fechada, não existe na fila do RoadS e por isso nunca é confirmado ao RoadS: um plano só de conclusões termina
   sem `ack` (`not_needed`). `roadmapSync.markCompleted: false` desliga;
4. mostra o diff para aprovação;
5. grava, com backup ao lado de cada arquivo;
6. confere as marcas ocultas de cada mudança;
7. só então confirma ao RoadS;
8. completa as issues que o RoadS mostra: o RoadS cria a issue com labels, Status, Prioridade,
   Repositório, Stack, Description e o esforço, mas não define responsável nem tipo nativo, e as
   issues que nasceram em outro lugar chegam ao quadro com o que tinham. O utilitário `gaps`
   (somente leitura) lista, nas issues dos sprints e dos grupos, o que falta contra as regras do
   `project`: o que o config resolve sozinho (padrão de campo, label que um valor implica,
   responsável e tipo do quadro, entrar no quadro) e o que exige escolha. O Frontlights propõe os
   valores, mostra a tabela inteira, e você aprova antes de qualquer escrita. Só se preenche o que
   está vazio, nunca se sobrescreve valor existente, e o texto do corpo de uma issue nunca é
   editado. Ao final, `gaps` roda de novo para conferir. Campo sem opção no quadro é apenas
   informado.

Quem decide o limite de itens por sprint é o RoadS, e o limite é só informação: o Frontlights
escreve no arquivo da semana as mudanças dos itens acima do limite como as dos demais, na ordem do
`position` (a ordem que o Scrum Master arrastou no RoadS): os itens dentro do limite primeiro e, só
quando algum item acima do limite tem entrada no arquivo, a linha "Acima do limite de N:" uma única vez
(atualizada quando o N muda e tirada quando não sobra entrada depois dela) e depois os demais; a entrada de
um item que saiu da semana (por `move_lane` ou `remove`) fica onde está, com a saída registrada, e mantém a linha
enquanto estiver depois dela, e quando o item volta à semana, a mesma entrada registra a volta e vai para o lugar
dela pelo `position` (um `add` cujo `#N` já tem entrada vira pergunta: reaproveitar a entrada ou abrir outra); e
avisa, sem
perguntar, quais passaram do limite. Cada sprint é
uma semana, listada na ordem das datas; uma semana sem mudança não ganha arquivo.

Quando uma issue é renomeada no GitHub, o RoadS faz o item acompanhar o título e enfileira um `modify` só com o
título novo. O Frontlights acha a entrada pelo número da issue que a mudança traz (o `#N` ou o link que os arquivos
citam), e não pelo título, que nos arquivos pode ser o antigo: troca o título antigo pelo novo no `ROADMAP.md` e em
cada `SPRINT_*.md` do plano, sem tocar no resto, e diz quantos `modify` de título o plano tem. Sem número (um item
ainda sem issue, por exemplo), acha pelo título e pela lane. Se um `modify` ou `move_lane` não achar entrada no roadmap,
se um `add` achar entrada do mesmo `#N`, ou se qualquer mudança achar mais de uma, ele pergunta em vez de abrir uma
segunda.

Quem escreve os arquivos é sempre esta máquina: o RoadS não alcança a pasta onde eles ficam.

Configure o bloco `roadmapSync` no `.frontlights/config.json` do projeto (veja
`examples/config.json`):

- `endpoint` é a base `/api/frontlights` do RoadS, que responde `POST sync-board`,
  `GET roadmap-state`, `GET pending-changes` e `POST ack`. A aprovação vale para essa base, com
  o mesmo segredo para os quatro;
- `secretEnvVar` nomeia a variável do segredo, que precisa começar por `FRONTLIGHTS_`. Defina o
  valor no seu próprio terminal, com
  `setx FRONTLIGHTS_API_SECRET "<valor emitido pelo RoadS>"`, e reinicie o Claude;
- `scrumRoot` é a pasta onde ficam os arquivos, e aceita `%USERPROFILE%`;
- `roadmapFile`, `weekFolderPattern` e `sprintFilePattern` montam os caminhos. As datas de
  início e fim de cada sprint vêm do RoadS; o `ROADMAP.md` usa o ano da semana atual. `{yyyy}` vem
  do início da sprint. Em cada padrão, o primeiro `{dd_MM}` é o início e o seguinte, o fim;
- `maxSprintItems` é o limite local, usado só quando o RoadS não informa o dele (4);
- `markCompleted` é opcional (padrão `true`): registra como "concluída" os itens de sprint que o RoadS mostra em `done`,
  uma vez cada, com a data da sincronização; um registro nunca é retirado (se o cartão sair de Done, o `.md` continua
  "concluída"). `false` desliga;
- `issueTargets` diz, para cada produto do RoadS, o repositório e o quadro onde a issue nasce.
  Produto sem destino não gera issue.

Na primeira vez, o envio do segredo para aquele endereço precisa da sua aprovação. O estado da
sincronização (aprovação, marca, plano e cópias temporárias) fica em `.frontlights/roadmap-sync/`,
fora do Git. O utilitário é `python scripts/roadmap_sync.py status|approve|fetch|apply|ack|rotate-markers|gaps --root <projeto>`.
O `gaps` só lê, usa o `gh` da própria máquina (a conta ativa precisa enxergar o repositório e o
quadro) e aceita `--only-sprints` para deixar os grupos do backlog de fora.

Limites conhecidos do `gaps`: só enxerga o repositório e o quadro do `config.json` (issues de
outros produtos em `issueTargets` são ignoradas); lê até 100 labels, 20 responsáveis, 20 cartões e 50
valores de quadro por issue (uma issue maior é ignorada e listada em `skipped`, nunca lida como vazia);
campos de seleção múltipla, de usuário e outros tipos além de seleção única, texto, número, data e
iteração não são lidos, e um campo desses configurado em `fields` aparece em `unfillable` e sempre
vazio; um
campo de iteração é reconhecido mas não é escrito. Valores de campo ou de opção com `<`, `>` ou
caracteres que um terminal interpretaria são mostrados limpos e listados em `unwritable`: o Frontlights
não os digita. Um `project` com chave desconhecida passa a ser recusado: se o seu `config.json` tinha
chaves extras ali, remova-as.

### Resumo para a diretoria (opcional)

O bloco `roadmapSync.progress` mora em um projeto só (por exemplo, o RoadS), e a pergunta aparece
em qualquer projeto: logo depois da pergunta do roadmap (inclusive quando não havia nada pendente, ou
quando você respondeu "não") o `/frontlights` pergunta: "Atualizar também o Resumo para a diretoria no
RoadS?". O projeto que tem o próprio bloco usa o dele (mesmo desabilitado); os outros usam o projeto que
você registrou uma vez como dono do bloco, com `python scripts/progress_report.py home --set <projeto>`,
só depois do seu sim. O registro fica no diretório pessoal, assinado com a chave do usuário, nunca num
repositório, e diz só onde o bloco está: o bloco lá continua precisando da própria aprovação. O
`status` informa `source`, `operationsRoot` (o projeto em que as demais operações rodam), `home` e
`homeState`; sem bloco e sem registro a pergunta não aparece e, se o projeto usa a sincronização do
roadmap, o Frontlights pergunta uma vez por sessão se você quer registrar o projeto dono do bloco
(e oferece como opção cada pasta vizinha que tenha um). Com a resposta "sim", o Frontlights:

1. pergunta ao RoadS qual período coletar;
2. roda os coletores que o próprio projeto configurou e mostra a tabela de conferência dos números;
3. só segue depois da sua confirmação desses números;
4. redige o arquivo de textos em linguagem simples, seguindo o guia que o projeto indica
   (`draftGuide`) e a partir dos fatos coletados, dos registros locais e, quando a sincronização do
   roadmap está configurada, do roadmap e da sprint da semana (que alimentam os próximos passos); o
   próprio projeto monta o rascunho final com fatos, uso, dados de acesso locais e prints. O resumo é
   do produto que o `facts.json` nomeia em `scope` (entregas, dificuldades e próximos passos só dele; o uso
   do Claude cobre todos os projetos conectados). Cada entrega é uma issue de topo e representa a família
   inteira, em qualquer profundidade, ou, sem sub-issues, as caixas de critério de aceitação como partes: o
   e-mail e a visão semanal mostram sozinhos "X de Y partes prontas", e o texto diz o que ficou pronto no
   período e o que bloqueia (uma caixa com o sub-item "Bloqueada:" é uma dificuldade), sem repetir a
   contagem (campos `subIssues` e `slices` do coletor, contrato em `docs/roads-contract.md`);
5. cuida dos prints e, para cada um, oferece capturar a tela do produto rodando neste computador (só
   dados de teste, nunca dados reais nem produção, sem a barra do navegador nem a identidade de quem
   está logado; JPEG ou PNG, até 1 MB e cerca de 1920 px de largura, no máximo 40). Antes de perguntar,
   lista os prints que os testes assistidos guardaram para o resumo (`progress_report.py candidates`,
   só leitura) e, por entrega, pergunta se usa esses, captura novos ou mistura; o print guardado só é
   oferecido enquanto o código que ele mostra é o código entregue, e é copiado (nunca movido) com o
   número da entrega, não o da parte. Grava as imagens
   na pasta dos prints e reescreve o `captions.json` a cada execução, nunca acrescentando ao anterior
   (imagens que não estão nele são ignoradas). Cada item é `{"file", "caption", "issue"}`, com
   `issue` opcional: o número inteiro da issue da entrega. Com `weekShots`, a pasta é a do resumo (`<semana>/<weekShots>/<dd_MM do último dia>`) e
   os prints são obrigatórios (veja abaixo); sem ele, a skill pergunta se o resumo leva prints;
6. mostra o rascunho completo, com cada print e sua legenda, e, com a sua aprovação, envia ao RoadS
   com `push --draft <arquivo>` (mais `--to <último dia do período>` com `weekShots`); o comando do
   projeto escolhe os prints na pasta e monta a linha de acesso do e-mail a partir dos arquivos
   locais do projeto, nunca da conversa, e a skill informa o link para revisar.

Revisar, editar, conferir os números, copiar para o e-mail e marcar como enviado acontece no
RoadS. O Frontlights não envia e-mail. Reenviar o rascunho atualiza o conteúdo coletado e mantém as
edições feitas no RoadS.

**Período de cada resumo.** Cada resumo cobre tudo o que foi feito, em todas as issues e sub-issues e
no uso do Claude, desde o instante exato em que os números do anterior foram coletados até agora: o de
quarta começa onde o de sexta terminou, e o de sexta onde o de quarta terminou. O período vem só do
RoadS (`window`), com hora, e chega aos coletores por `--start`/`--end`; a skill nunca escolhe datas.
Se o RoadS ainda guarda o resumo anterior como rascunho (esqueceram de marcá-lo como enviado), o
Frontlights para e pergunta antes de coletar, porque o envio substituiria esse rascunho; com ele
marcado, lê o período de novo. Depois do envio do resumo de sexta, a apresentação da semana soma os
dois, e a lista do RoadS mostra os dois resumos e a apresentação.

O bloco fica dentro de `roadmapSync` (veja `examples/config.json`) e reaproveita `endpoint` e
`secretEnvVar`:

- `enabled` liga o passo; `path` é a rota sob o `endpoint` (só segmentos simples, nunca `..`);
- `collectors` é a lista de comandos, cada um com `name`, `command` (lista de argumentos, nunca uma
  linha de shell; `{start}` e `{end}` viram os instantes exatos do período, com fuso, e `{from}` e `{to}`
  viram os dias `AAAA-MM-DD` desse mesmo período) e `timeoutSeconds` (padrão 300);
- `pushCommand` é o comando de envio (lista de argumentos; `{draft}` vira o caminho do rascunho),
  com `pushTimeoutSeconds` opcional;
- `factsFile` e `usageFile` são opcionais: apontam os arquivos que os coletores gravam, para a
  skill ler;
- `draftGuide` e `shotsDir` são opcionais e devem ser caminhos relativos dentro do projeto (sem caminho
  absoluto, letra de unidade, `..` nem `~` no início; até 200 caracteres): `draftGuide` é o guia em
  que o projeto descreve o arquivo de textos, e `shotsDir` é a pasta dos prints e do `captions.json`.
  Os dois entram na aprovação do bloco: mudar qualquer um pede nova aprovação.
- `weekShots` é opcional e substitui `shotsDir` (os dois juntos são recusados). Ele guarda os prints
  na pasta do resumo, fora do projeto: `<scrumRoot>/<weekFolderPattern>/<weekShots>/<dd_MM>`, por exemplo
  `"weekShots": "summary"`. É um único nome de pasta (letras, dígitos, `-` e `_`).
  - **Qual semana:** a pasta é a da segunda-feira seguinte à semana do ÚLTIMO dia do período, o dia em que
    o resumo é apresentado, e cada resumo tem a sua subpasta, nomeada pelo dia em que o período termina:
    o resumo de 28/09 a 02/10 vai para `05_10/summary/02_10`, e o de sáb 03/10 a qua 07/10 para
    `12_10/summary/07_10`. Dois resumos da mesma semana (quarta e sexta) nunca dividem o `captions.json`.
    O `window` informa `weekMeeting` e `summaryFolder`, lendo a janela no calendário de São Paulo; se o RoadS
    mandar o campo `weekMeeting` e ele divergir do cálculo do Frontlights, o do RoadS vale para essa janela e o
    Frontlights avisa. Um `weekMeeting` ou `--meeting` fora do intervalo plausível (depois do último dia e até oito
    semanas depois da segunda-feira usual) é recusado. Prints salvos antes
    da subpasta, direto em `weekShots`, ainda são lidos pelo `push` (com aviso) quando a subpasta do dia não existe e só a pasta plana tem
    `captions.json`; com a subpasta do dia criada, só ela vale.
  - **Como chega ao comando:** `shots --to <último dia>` cria a pasta quando falta e informa o caminho
    (`--meeting <weekMeeting>` só quando o período é o da janela do `window`; `--from` não nomeia mais a pasta).
    O `pushCommand` precisa trazer `{shotsDir}` como argumento inteiro, que vira esse caminho, por
    exemplo `"--shots-dir", "{shotsDir}"` (`"--shots-dir={shotsDir}"` é recusado). O `scrumRoot`
    precisa ser um caminho completo.
  - **Exige `factsFile`:** antes do envio, o `push` confere o `captions.json` e as imagens. Também
    recusa quando uma entrega visível do `factsFile`, com status diferente de `proximo`, não tem
    print com a issue dela, e também quando uma entrega tem mais de um: o resumo leva um único print por
    entrega. O `hidden` booleano do arquivo de textos prevalece sobre o do coletor.
  - **Aprovação:** `scrumRoot`, `weekFolderPattern` e `weekShots` entram no bloco aprovado.
    Ativar o `weekShots` pede nova aprovação.
  - **Mesmas travas da sincronização do roadmap:** nada fora do `scrumRoot`, sem junção nem link no
    caminho.

Como esse bloco faz o Frontlights executar comandos lidos de um arquivo de configuração, nada roda e
nenhuma chamada é feita antes de você aprovar o bloco exato (endereço, variável, rota e cada
comando). Qualquer mudança nele pede nova aprovação. Os coletores não recebem o segredo; só o
comando de envio o recebe, pela variável de ambiente. Este repositório não traz coletor nenhum. O
utilitário é `python scripts/progress_report.py status|approve|window|collect|shots|push|candidates --root <projeto>` (e `home --set|--clear`, sem `--root`, que registra o projeto dono do bloco).

### Teste de navegador e verificações (opcional)

Quando algo que a sessão entrega muda o que a pessoa vê (o plano liga o teste de navegador, ou o
`browser-gate` acha a mudança visível no diff), o Frontlights sobe o ambiente da branch entregue, roda as verificações e entra no app com as contas de teste. Os blocos
`browserTest` e `checks` ficam no `.frontlights/config.json` do projeto (veja
`examples/config.json`):

- `python scripts/serve.py start|status|stop --config <config> --root <worktree> --issue <n>`
  sobe, consulta ou derruba os processos de `browserTest.processes` (lista de argumentos, sem
  shell), espera o `health` de cada um e grava os pids em `.frontlights/serve/<n>.json`;
- `python scripts/serve.py preview start|status|stop|refresh --config <config> --root <worktree principal>`
  cuida da prévia ao vivo do bloco `preview` (worktree, branch, `baseUrl` e processos próprios): sobe, consulta,
  derruba ou refaz a branch da prévia a partir da main local com as branches de issue dadas em `--branch`
  (opcional, repetível; `--base` troca a main local), com registro em `.frontlights/preview/registry.json`;
  `serve.py relay` é interno, aberto pelo `preview start` para gravar o log mascarado de cada processo em
  `.frontlights/preview/log/`, e nunca se roda à mão;
- `"port": "auto"` reserva uma porta livre por processo na pasta comum do Git, vista por todas
  as worktrees (fora do Git, em `.frontlights/serve/ports/`, e repositórios diferentes não veem
  as reservas uns dos outros), e a entrega em `PORT`, `FRONTLIGHTS_PORT_<NOME>` e `{port}` no argv; o `health`
  precisa ter `{port}` no lugar da porta (`http://127.0.0.1:{port}/health`). Um projeto cujo
  servidor fixa a própria porta usa `port` fixo, e aí só uma issue por vez pode subi-lo;
- `python scripts/checks.py regression|integration|smoke --config <config> --root <worktree> --issue <n>`
  roda a suíte na base e na branch (só falha nova bloqueia; `regression` pede também
  `--base <checkout-da-base>`), o comando de integração contra o backend da branch e os
  caminhos de smoke. Códigos: 0 passou, 1 falha de produto, 2 config recusada (nada rodou),
  3 infraestrutura;
- o `checks` recusa host fora de `127.0.0.1`, `localhost` e `::1` antes de requisitar (no `smoke`,
  `health` e `baseUrl`; no `integration`, o backend); o `serve` não confere o host do `health`,
  então mantenha `health` e `baseUrl` em host local e nunca aponte um teste para homologação ou
  produção.

`browserTest.users` traz a conta 1 e, para o teste de permissões entre contas, a conta 2, com
login e senha **em texto** no `.frontlights/config.json` do projeto de destino, fora do Git. É
um risco aceito só para contas de teste: nunca use uma conta real ou de produção. Login e senha
são mascarados em toda saída e registro, e um valor com menos de 4 caracteres é recusado pelo
`serve` e por `checks integration` e `checks smoke` (o `checks regression` não recusa). Sem
navegador ou rede, o teste é relatado como não executado e nunca conta como aprovado. O app de
exemplo em `examples/browser-app/` mostra o fluxo de ponta a ponta.

**Dados de teste que o teste cria.** Regra permanente, para todo projeto: o teste de navegador e o de
permissões entre contas criam os usuários, contas ou tenants, empresas, perfis, concessões e demais dados
que o `Fluxo:` precisa para rodar completo (o não-dono da mesma conta, um login de outra conta, um perfil
restrito) e os removem no fim. Falta de login nunca é motivo para pular um caso, e nenhum texto delegado a
um subagente proíbe a criação. Só no banco local e descartável, pelos endpoints do próprio produto, nunca em
produção nem com dado de pessoa ou cliente real. Os ids criados ficam em `dados-de-teste.json` (nunca login
ou senha), a remoção é conferida item a item, e o que o produto não apaga (excluir um usuário só o
anonimiza) é listado com o `DELETE` exato, só dos ids criados, para você aprovar.

**Prints para o resumo.** O teste assistido guarda só um print da ANTES e um da DEPOIS por issue (a tela que
melhor mostra o que mudou, no mesmo ponto nas duas), nunca um por passo ou por repetição; um caso que falha pode guardar
a sua imagem de falha. Na passada DEPOIS ele também guarda, para cada entrega, um único
print limpo (sem a faixa, sem a barra do navegador, sem identidade nem dado de pessoa) em
`.frontlights/issues/<n>/browser/resumo/` da worktree principal (a limpeza das worktrees entregues leva o
`.frontlights` delas), com um `candidates.json` que diz a parte, a entrega (`cover`), o repositório, o instante e os arquivos visíveis com o id Git que tinham. Nada sai do projeto nessa hora: o resumo só copia o
que você escolher na etapa dos prints.

Antes de abrir o navegador, o Frontlights pergunta (uma vez por issue) se você está
pronto para assistir. Com o sim, o teste roda em um Chrome de janela visível, nunca oculta e com
perfil descartável, em duas passagens do mesmo cenário, com a mesma conta: primeiro a base (faixa
na página "ANTES: main") e depois a branch entregue ("DEPOIS: branch X"). Cada caso roda duas
vezes, os avisos ficam na tela o tempo necessário para serem lidos e a janela de cada passagem
permanece aberta cerca de 5 minutos no fim. Fechar a janela (ou os 5 minutos acabarem) avisa quem
conduz o teste: ao fechar a janela da ANTES, a DEPOIS começa; ao fechar a da DEPOIS, o relatório
chega, sem ninguém ficar esperando à toa. Prefere-se o back real e, quando o assunto é permissão, um perfil restrito
real: o usuário de teste muda de perfil pelo endpoint do próprio produto, depois de você confirmar
que o banco por trás é descartável, e volta no fim. O valor original fica salvo em disco antes da
mudança (só o campo de perfil, nunca a linha inteira) e é conferido depois de desfazer. Resposta
forçada por interceptação de rede só complementa e é declarada no relatório. O servidor de teste
usa porta própria e o Frontlights encerra só o que ele mesmo subiu. Se a sua resposta for "rodar
sem assistir", o registro traz `assistido: false`.

Com os resultados no texto, o Frontlights pergunta o que fazer com o que você viu: "Assistir de novo"
(repete as duas passagens numa janela nova, sem repetir a pergunta de pronto), "Aprovado" (você
confirma que a DEPOIS fez o esperado), "Precisa de alteração" (você diz o que mudar e a issue volta
para o ajuste, sem seguir para as próximas etapas) ou "Pode prosseguir" (segue sem aprovar, e o
relatório diz que foi assistido, não aprovado). Ele nunca escolhe por você nem trata o silêncio como
resposta. O registro traz `rodadas` e `aprovacao`. Se um caso da DEPOIS falhar, a pergunta de falha
vem antes e substitui esta.

**Um teste por issue, antes da revisão.** O teste assistido é um por issue (a issue e as sub-issues
que ela já tem), nunca um por CA, branch ou worktree. A pergunta sai quando a última fatia que muda a tela fecha o ciclo de testes
e toda fatia já fechada está mesclada na branch da issue (um merge depois do registro reabre a pergunta,
como `stale`), antes da revisão independente de qualquer uma delas: as fatias só de API ou só de testes não seguram a
pergunta, e um `pending` antes disso é esperado e não pergunta nada. O DEPOIS roda no estado entregue das
fatias que já fecharam o ciclo: a branch da issue, quando toda fatia de tela já está mesclada nela, ou uma worktree de integração
local, nunca enviada, que junta a branch da issue e as fatias ainda abertas; a integração da família reaproveita essa worktree e não repete o teste.

O `python scripts/frontlights.py browser-gate --config <config> --base <base> --root <worktree> ...
[--stacked <branch>=<alvo> ...] --toca <sim|nao|ausente> --record <result.json>` lê o diff, não o texto do plano, e devolve
`not_needed`, `answered`, `pending`, `stale`, `contradiction` ou `unconfigured` (código 0 para os dois
primeiros, 2 para os demais). Os caminhos visíveis vêm de `browserTest.frontPaths` (globs a partir da raiz do repositório: `*` não
atravessa pasta, então `**/*.html` pega todas as páginas; testes e documentos nunca contam); sem ele, a
estimativa sai do nome do arquivo e o `inspect` avisa. Cada fatia empilhada entra com `--stacked
<sua branch>=<a branch em que ela se apoia>`, e cada CA com `--stacked <sua branch>=<a branch da issue>`, para só o
trabalho dela contar. O `result.json` é um por issue e fica na pasta dela (numa família que já existe, na
pasta da issue líder) e traz `situacao` (`pendente`, `ainda-nao`, `aprovado`, `prosseguir`,
`sem-assistir`, `dispensado` ou `alteracao`), `lote` (`issues` e `roots`) e `pergunta`; `dispensado` é a sua
decisão explícita de não rodar o teste, gravada com a resposta literal. Depois de uma decisão, só
código que não é teste nem documento volta a abrir a pergunta (`stale`). "Ainda não" mantém a pendência:
ela segue em `checkpoint --pending teste_assistido` e `context --pending teste_assistido`, o `resume` a
lista primeiro e uma janela perto do limite pergunta antes de gastar mais. Revisão de fatia que muda a tela, "completa" e PR só
seguem com `answered` (inclusive `dispensado`). É uma regra da skill conferida por um script,
não uma barreira técnica: nada impede um modelo de deixar de chamá-lo.

Limites: só o Windows foi exercitado (POSIX não). O `inspect` confere nesses blocos as regras do
`serve` e do `checks` que dependem só do config: formato dos blocos, shell embutido nos argv de
`checks`, hosts locais, `{port}` com porta `auto` e segredos de teste mascaráveis. Confere também
`browserTest.isolated` (portas que nunca são as da prévia nem do serve, `baseUrl` na porta de um processo
isolado, `cwd` relativo desses processos, passos do banco sem shell) e o bloco `preview` (worktree dentro do
`--root`, branch, `baseUrl` local e processos, com as regras do `serve preview`). Ele recusa o
config inválido com a mensagem mascarada; sem os blocos, a saída dele não muda. O `cwd` de
`checks` e de `browserTest.processes` (`checks.run_directory`, `serve.process_cwd`), o de `preview.processes`
(`serve.process_cwd`, quando a prévia sobe), o `.cmd`/`.bat` com metacaractere e os nomes
`checks.backend`/`checks.smoke.target` contra `browserTest.processes` só são conferidos na
execução, antes de qualquer processo subir. Um `browserTest` que declara só as contas (e a
`baseUrl`), porque o projeto sobe o próprio ambiente, é válido: o `inspect` mostra um aviso em
`warnings` e segue, e o `serve` recusa subir sem `processes`, dizendo o que fazer.

### Fechar o que terminou

Depois da pergunta do roadmap e da do resumo, o Frontlights lê o GitHub (só leitura) e, quando acha issues
que ele trabalhou neste projeto e que já têm **todos os critérios de aceitação marcados**, pergunta se pode
fechá-las e mover os cartões para Done. A lista vem completa, com as sub-issues antes dos pais, os PRs
ligados (aberto, mesclado ou nenhum), o status atual do cartão e os comandos exatos; só depois da sua
aprovação dessa lista ele fecha (`gh issue close --reason completed`) e move, e relê o GitHub para conferir.
Uma issue sem a seção de critérios, com critério desmarcado ou com filha ainda aberta que não esteja na mesma lista
nunca entra; uma issue cuja branch ainda não está em `origin/main` (a release que a leva não foi mesclada) fica fora
como `awaiting_release`, e o Frontlights só avisa. Uma issue já fechada só é movida se foi fechada como concluída. Um corpo escrito antes da regra das
pendências, com uma seção "Pendências conhecidas" fora dos critérios e item aberto nela, entra na lista com o
aviso "fecha com N pendências fora dos critérios": a decisão de fechar assim é sua, e, se você pedir, mover
essas pendências para os critérios é uma escrita à parte, com texto aprovado antes.
O RoadS lê só o **Status** do cartão no Project, nunca se a issue está fechada: fechar sem mover o cartão não muda nada
lá, e um item concluído fica na sprint (marcado como concluído) até a rotação semanal removê-lo; por isso, depois de mover
cartões, o Frontlights oferece sincronizar de novo. Nenhuma autorização de implementação, merge ou teste verde
substitui essa aprovação. Os utilitários são
`python scripts/closeout.py candidates|verify|merge-status|tick-check ...` e
`python scripts/cleanup.py plan|verify ...`, e só leem.

#### Homologar na main local, lançar a release, fechar e limpar

Cada issue entra na **main local** do projeto, a homologação, por um merge com três portões verdes (suíte inteira,
`review-gate` em dia e `browser-gate` respondido), e um bundle da main local e das branches vai para a pasta de
backup configurada. Ao fim de cada issue homologada o Frontlights oferece a **release**: `homolog release-plan` lista
as issues que estão na main local e ainda não em `origin/main`, e a pergunta "Lançar a release com as issues #a, #b
agora?" tem "Sim, lançar" e "Agora não". Com o "Sim", ele corta a branch `<prefixo>release-<data>` da main local,
envia só ela e abre a PR única pelo modelo `templates/pr.md`: Resumo (o menor visual) e Evidência (antes e depois) por issue,
com os prints do teste assistido, os testes do checkpoint e os três portões de cada uma, e o Risco do merge consolidado (porta
de mão única ou de mão dupla e raio de impacto). Depois de abrir a PR da release, o
Frontlights **aguarda o seu merge por padrão** (você pode dizer "não aguardar" a qualquer
momento): ele avisa em uma linha o que espera, registra "Aguardando o merge" no handoff e segue com o trabalho
independente. Quando a PR fica pronta (os portões de cada issue registrados, sem conflito com a base e
nenhum achado sem destino), ele pergunta "Mesclar a PR #<n> em <base>?", com "Sim, mesclar" e "Não, aguardar o
merge"; só com o "Sim" roda `gh pr ready` e `gh pr merge --merge` (merge com commit, nunca `--admin`, `--auto` nem
`--delete-branch`), e com o "Não" a espera continua. Depois do merge, `git pull --ff-only` traz a main local até ele. A PR nunca leva palavra de fechamento (`Closes`, `Fixes`, `Resolves`) no corpo nem nos commits, porque
fechar uma issue tem aprovação própria. O aviso do ambiente (uma inscrição na PR ou um monitor em segundo plano) é só o
gatilho: a cada despertar roda `closeout.py merge-status`, e só vale o merge **na branch base aprovada**. Merge de uma
issue na main local, PR fechada sem merge ou PR não encontrada não fecham nada: a issue fecha com a release que a leva. Se o ambiente não oferece gatilho, ou
a sessão acaba, a pergunta de fechamento do início da próxima sessão encontra o trabalho mesclado.

Com o merge confirmado, em aprovações separadas, nesta ordem:

1. **Issue** com todos os critérios marcados: pergunta se pode fechá-la e mover o cartão para Done.
   **Sub-issue** com todos os critérios marcados: pergunta se pode fechá-la e marcar, no corpo da issue pai, o item que a
   cita. Só entra um item que cita apenas essa filha (`parentTicks`, por número de linha); a escrita troca somente `[ ]`
   por `[x]`, com o corpo anterior guardado e conferido por `closeout.py tick-check` antes e depois. Sem item citando a
   filha, ela só fecha. Depois, o pai pode passar a ser candidato e entra na mesma pergunta. Issue com critério
   desmarcado não é oferecida: o Frontlights diz quais faltam.
2. **Limpeza**, só depois de o fechamento ser escrito e conferido: pergunta se pode remover as worktrees e branches criados
   que deixaram de ser necessários (`cleanup.py plan`). Só entram os que têm o tip igual à cabeça de uma PR mesclada que
   chegou à base aprovada (o filho empilhado, pelo pai) ou, sem PR nenhuma, cujo tip já está em `origin/main` (a branch
   de uma issue que chegou ao GitHub pela release), sem alteração pendente, sem PR aberta a partir ou em cima da
   branch, que não são protegidos, nem a worktree principal, nem a pasta em que a sessão está. A branch remota só é
   apagada se `origin` é o repositório configurado e ela ainda aponta para esse mesmo commit. Nunca usa `--force`; a
   lista e os comandos são mostrados na íntegra antes, e `cleanup.py verify` confere depois. Uma worktree com registros
   do `.frontlights` dentro leva esses registros junto, e os arquivos que o Git ignora (um `.env`, `node_modules`)
   também: o aviso lista os nomes antes da pergunta. A worktree de integração local da família (nunca enviada, sem PR)
   entra quando não guarda commit próprio (nem merge com conteúdo, como um conflito resolvido à mão) fora das PRs já entregues.

Responder "Não agora" ao fechamento não gera a pergunta da limpeza. A espera é regra da skill, não barreira do Frontlights:
nada a impõe mecanicamente, e o gatilho do ambiente nunca vale como prova do merge.

## Fluxo de trabalho e utilitários

Verificação de atualização da skill (sem pergunta; mostra o comando de atualização
quando há versão nova no GitHub) →
pedido e dimensionamento → inspeção → entrevista de decisões (com um artefato visual, uma página privada
na mesma URL do início ao fim) → corpo da issue escrito sem nova
entrevista (só a pergunta dos seams), mostrado na íntegra e aprovado →
slices cortadas como critérios de aceitação (uma caixa por slice), lista numerada com o quiz
antes do corpo, plano aprovado e publicado numa escrita por issue → autorização permanente de
implementação, anunciada sem pergunta → prévia ao vivo numa aba do seu Chrome, refeita a cada CA (quando o projeto a
configura) → desenvolvimento orientado a testes (TDD), revisão e evidências →
merge na main local com três portões verdes e bundle de backup → oferta da release (branch de release e PR única),
espera do merge dela e, com ele confirmado, `pull --ff-only`, fechamento, marcação no pai e limpeza das worktrees (cada um com aprovação própria).

**Autorização permanente.** A etapa 6 não pergunta concorrência, empilhamento nem autorização: o
Frontlights trabalha as slices de cada issue em ordem, numa branch por issue, cortada da main local (nunca de
`origin/main`), que fica só local, nunca é enviada e entra na main local por um merge com três portões verdes
(suíte inteira, `review-gate` em dia e `browser-gate` respondido), cada CA na própria
worktree (branch cortada da branch da issue e devolvida a ela por merge quando o ciclo fecha), com CAs independentes
em paralelo dentro da issue e entre issues, anuncia num bloco curto as issues, a branch e a ordem das slices de cada uma, a
concorrência, o empilhamento (só numa família que já existe), a base das worktrees e os testes,
e começa; antes, no início de cada etapa 6, confere o hook `pre-push` da homologação (`homolog hook`, instalado
só com o seu "Sim" a uma pergunta que mostra o script) e traz `origin/main` para a main local (`homolog sync`;
um conflito é desfeito e vira pergunta). Cada slice
é um ciclo de TDD, um ponto de retomada (`checkpoint --slice`) e uma caixa marcada com evidência; uma
sessão nova retoma pela primeira caixa aberta. Ficam autorizados, só para as issues da família ou
do lote: editar, testar,
commitar, mesclar a branch da issue na main local com os três portões verdes, mesclar a main local e as
branches das issues em andamento na branch da prévia pelo `serve preview refresh` (um conflito é desfeito e vira
pergunta; a branch da prévia nunca é enviada), rodar a migration no banco de
desenvolvimento local, criar e remover dados de teste pelos endpoints do produto e comentar ou
marcar critérios nas issues; nada da issue vai ao GitHub antes da release, cuja PR é a única PR do
fluxo. Merge de PR, fechar issue, mexer no quadro, publicar em produção, editar
migration já registrada, escrever na main remota (`origin/main`) ou numa branch protegida, ligar configuração, chave ou flag em
produção e apagar o que não for dado de teste viram, cada um, uma pergunta própria com "Sim" e
"Não" e o comando exato; só o "Sim" libera aquela operação. As perguntas do próprio trabalho (teste
assistido, falhas, achados, decisão nova) continuam, assim como as aprovações do texto da issue,
do plano de issues, do fechamento, da limpeza, do roadmap e do resumo. Os pedidos de permissão do
próprio Claude Code não são do Frontlights e continuam valendo.

**Paralelismo máximo.** Em toda etapa, e em todo projeto, o Frontlights lança ao mesmo tempo tudo o que
não depende de outra coisa, com tantos subagentes quantas forem as partes: as leituras do início da
sessão, a leitura do código e o rastreio por camada na entrevista e no plano, as issues independentes na
implementação (cada uma na própria worktree) e, dentro de uma issue, as CAs independentes ao mesmo tempo, cada uma na própria worktree,
mais o trabalho em volta de cada CA aberta
(leitura para a próxima, suíte ampla, verificação de tipos, teste assistido e revisão independente),
respeitada a ordem de dependência. Só espera o que depende de verdade:
uma aprovação, um `Depende de`, um arquivo ou um recurso compartilhado (porta, banco, pasta de reservas).
As perguntas, as aprovações, as escritas no GitHub e o handoff continuam na sessão coordenadora, que é uma
só; o relato de um subagente é conferido antes de virar evidência.

**Prévia ao vivo.** Num projeto com o bloco `preview` no `.frontlights/config.json`, a sessão sobe a prévia logo
depois da aprovação do plano, antes da primeira CA, e a abre numa aba do Claude in Chrome: uma worktree fixa
numa branch local de prévia (nunca enviada) com a main local e as branches das issues em andamento, refeita pelo
`serve preview refresh` a cada CA pronta, para você testar à mão minutos depois de a CA ficar verde, só
recarregando a aba. O log dos processos fica salvo e mascarado; um build quebrado vem numa linha com o arquivo e o
erro. A prévia só para quando você pede, e a aba é sua: o teste assistido roda em outra janela e nunca nas portas
dela. A prévia usa portas fixas, com a `baseUrl` na porta de um dos processos dela, para a aba continuar válida a
cada refresh: o `serve preview` e o `inspect` recusam `"port": "auto"` nos processos da prévia, `{port}` no argv ou no
`cwd` dos processos dela (escreva a porta fixa), `{port}` na `baseUrl` dela e uma `baseUrl` numa porta que nenhum processo dela usa; com o bloco `preview`, o `inspect` também
recusa uma porta fixa de `browserTest.processes` ou da `browserTest.baseUrl` igual a uma porta da prévia.

**Artefato visual.** A entrevista deixa de ser só texto: há um artefato por entrevista, na mesma URL (uma
página privada publicada pela ferramenta de artefatos do Claude, que também abre no celular), criado na
primeira rodada que toca tela, fluxo ou camadas e atualizado a cada rodada que toca uma delas, com uma seção
por pergunta: o antes da tela montado do template real do componente, o depois por abordagem e, sem tela, o
diagrama de fluxo e de camadas; na lista numerada das CAs (o quiz da etapa 5), cada CA com a seção do artefato
que mostra o que ela entrega. Só dados fictícios entram na página; a URL fica no log de descoberta (ou "artefato
indisponível", ou "não se aplica", quando nenhuma rodada toca tela, fluxo ou camadas, e aí a lista das CAs segue
sem seção); "preview" continua sendo só o campo das opções da pergunta. Sem a ferramenta, a sessão avisa numa
linha e segue em texto.

Uma issue vertical entrega um resultado observável de ponta a ponta, incluindo as
camadas necessárias, em vez de separar tickets apenas por banco de dados, API ou tela.
As slices da issue são os critérios de aceitação: uma caixa por slice, em ordem de dependência,
com Entrega, Seams, Camadas e Depende de em sub-itens; a etapa 5 mostra primeiro a lista numerada
e pergunta se a granularidade está certa, se as dependências são reais e o que unir ou dividir, e
só depois o corpo completo; prefactoring vem primeiro, refatoração larga vai em expandir, migrar e
contrair, e todo critério falha no commit de partida. Uma issue curta tem no máximo cinco CAs,
cada uma uma fatia vertical completa e curta; a sexta vira issues de topo ligadas por blocked-by, e a
caixa de pendência não conta no teto.
Uma issue e as sub-issues abertas dela andam juntas: ao agir sobre uma issue, o Frontlights
lê as filhas no GitHub e leva todas na mesma execução (entrevista, plano e implementação),
nunca só o pai; nenhuma sub-issue nova é criada. A fatia vertical é a issue mais as filhas, e
juntas elas cobrem todas as
camadas que o requisito pede (tela, API, banco e migração, testes, integração, documentação e
as do projeto); a seção `## Camadas da fatia` de cada issue registra as camadas analisadas e,
para as que não serão tocadas, o motivo com a evidência do rastreio de cada campo de tela até o
consumidor no back e a coluna no banco (um rastreio inconclusivo bloqueia a aprovação do plano até ser provado). Uma filha com `needs-decision`, ou sem abordagem
definida, entra na entrevista da mesma sessão. Numa família que já existe (issue com sub-issues
publicadas antes da regra das slices), quando uma filha depende do pai, a
autorização permanente usa **branches empilhadas** (você pode pedir para esperar o pai chegar à main local): a filha sai
da branch do pai assim que ele está verificado nela; a filha verificada é mesclada na branch do pai, e a família
entra na main local pela branch do pai, com as filhas dentro, pelos três portões, sem PR por filha e sem push
(nunca rebase nem push forçado; conflitos nos trechos que uma filha divide com outra são resolvidos no merge
e mostrados ao revisor). A concorrência usada é o número de filhas independentes
cujos arquivos não se sobrepõem. Sem a empilhada, a filha espera o pai estar na main local.
Na entrevista, depois de confirmar o problema (numa só pergunta quando a issue já
o define), a skill levanta as convenções do código afetado e propõe ao menos três
abordagens de implementação realmente diferentes. Cada uma informa se segue ou
quebra o padrão do projeto e o custo disso. Em seguida, a skill percorre os ramos
de decisão da abordagem escolhida, e é o usuário quem decide quando parar. O
padrão existente é o preferido; ele só é quebrado quando for comprovadamente pior
para o caso.
A mesma pergunta que define a profundidade oferece o modo aprendizado, desligado
por padrão, para quem ainda está aprendendo a programar e quer entender as
decisões enquanto as toma. Ligado, antes de cada decisão técnica a skill explica
em texto o conceito em linguagem simples, por que o projeto faz assim, um trecho
comentado do próprio código e o que cada opção muda, e fecha cada rodada com um
"Ficou claro?". Desligado, a última opção de cada pergunta técnica é "Explicar
antes de decidir". Depois de duas reexplicações da mesma rodada, aparece "Seguir
a recomendação": a decisão fica marcada como "a revisar" e entra no corpo da issue como
suposição, não como decisão aprovada. O modo pode ser ligado ou desligado a
qualquer momento, e os conceitos explicados ficam registrados no `discovery.md`.
Toda pergunta ao usuário usa `AskUserQuestion`, sempre com opções. A conversa
segue no idioma do usuário. Nada é aprovado sem que o texto completo tenha
sido mostrado antes. O GitHub é a fonte oficial;
os arquivos Markdown e JSON locais são registros e pontos de retomada, não um
segundo sistema de tickets.

Execute estes comandos na raiz do repositório (os quatro primeiros também valem de dentro de
`skills/frontlights`, sem o prefixo):

```powershell
python skills/frontlights/scripts/frontlights.py validate-plan --plan skills/frontlights/examples/plan.json
python skills/frontlights/scripts/frontlights.py schedule --plan skills/frontlights/examples/plan.json --limit 2
python skills/frontlights/scripts/frontlights.py context --used 85000 --reserve 15000
python skills/frontlights/scripts/frontlights.py update-check
python -m unittest discover -s tests -v
python -m compileall -q skills/frontlights/scripts tests
```

A suíte inteira leva dezenas de minutos, quase tudo em dois módulos que sobem processos e portas de
verdade. Para conferir o todo entre slices, defina `FRONTLIGHTS_SUITE=rapida` (no PowerShell,
`$env:FRONTLIGHTS_SUITE = 'rapida'` antes do comando): os módulos `tests.test_serve_ports`,
`tests.test_checks_integration` e `tests.test_serve_preview` são pulados, cada um relatado como um teste pulado com o motivo, que cita
a variável; qualquer outro valor, ou a ausência dela, roda tudo. A regra está no `load_tests` de cada
módulo, então vale igual para o `discover` e para o runner. A suíte rápida roda por `python tests/suite.py`
(só Windows): os módulos seguros rodam em paralelo, num pool de 4 trabalhadores, e os seis sensíveis
(portas, servidores reais, Chromium, asserções de tempo) numa fila serial, um por vez; cada módulo tem um
prazo (`--module-timeout`), e o runner sai com 1 quando um teste falha e com 2 num erro de infraestrutura
(prazo estourado, módulo que não importa). `--report <arquivo>` grava um JSON com início, fim, HEAD,
variável, trabalhadores e, por módulo, fila, tempo, contagens e resultado, como evidência da rodada. Por
slice, rode os módulos que a slice toca; antes da revisão independente e do merge na main local, a suíte inteira sem a
variável, uma vez, com ou sem CI no projeto, pelo `python -m unittest discover -s tests -v`: o runner não
deixa a suíte inteira mais rápida do que o `discover` (na issue 27, de 964 s a 1241 s pelo runner contra 934 s
pelo `discover`). A CI do GitHub não define a variável e continua rodando tudo: ela roda o mesmo `discover`.

Uma sub-issue de uma issue já publicada que não está no plano leva `parent_external` (o número do
pai) no lugar de `parent`. `python scripts/frontlights.py review-gate --root <worktree> --review <arquivo>`
compara a evidência salva na hora da revisão independente com a atual e sai com código 2 quando houve
commit, edição ou arquivo novo depois dela.

O exemplo seleciona `[1, 2]`; a issue 3 depende da issue 1, e a issue 4, sub-issue da 3
(`parent: 3`), é uma filha já publicada de uma família que já existe. As issues 1 e 3 trazem
`slices` (a segunda slice depende da
primeira); o `validate-plan` confere `delivers`, seams, camadas e a ordem das dependências. O
planejador escolhe o
maior conjunto seguro de issues prontas, respeita o trabalho em andamento e verifica
sobreposição de caminhos sem distinguir maiúsculas de minúsculas, para compatibilidade
com Windows. Ele recomenda um lote; a skill distribui o trabalho entre os agentes
ou sessões disponíveis do Claude, respeitando a autorização e a capacidade reais.
A validação estrutural não determina se o texto descreve uma entrega realmente
vertical. Isso exige a revisão de conteúdo da skill e a avaliação fornecida.

Leia o [protocolo](skills/frontlights/docs/protocol.md), o [contrato com o RoadS](docs/roads-contract.md), os [limites de segurança](skills/frontlights/docs/security.md),
o [roteiro de homologação](evals/runbook.md) e a [recuperação](docs/recovery.md).

## Fontes da documentação

O formato e os comandos seguem a referência oficial de
[skills do Claude Code](https://code.claude.com/docs/en/skills). Os passos para acompanhar pelo celular seguem a documentação
de [Remote Control](https://code.claude.com/docs/en/remote-control). O desenho de
permissões foi conferido na [referência de hooks](https://code.claude.com/docs/en/hooks).
Essas fontes externas estão em inglês. Consulta realizada em 24/09/2026; versão da
CLI testada localmente: 2.1.278. A validação nativa avisa que o CLAUDE.md da raiz não
é carregado nos projetos consumidores; isso é tratado pela skill principal.
