# Autorização e limites de aplicação das permissões

Cada referência de etapa abre dizendo quais seções deste arquivo lê. O que a etapa 6 faz sozinha e o que pergunta
antes está em `references/development.md`, "Standing authorization and the denied operations"; aqui ficam os limites
de aplicação dessas regras.

**Regra da skill, não barreira.** Uma regra marcada "(regra da skill)" orienta o modelo e é conferida, quando muito,
por um script que a sessão chama: um modelo que não o chame não é impedido, e os pedidos de permissão nativos do host
continuam valendo.

## Hooks e escritas em `.git/`

O Frontlights não instala hook nenhum. A main local, a homologação, nunca é enviada à main remota: o conteúdo dela
só sai para o nome da branch da release, pelo push da release (regra da skill). O hook de lembrete,
`templates/frontlights-prompt-hook.py`, é um modelo que o usuário copia para o `~/.claude/hooks/` e registra no
próprio `settings.json`; só injeta um texto, lê o prompt e o transcrito (atrás de duas marcas de abertura) e sai com
0. As escritas da skill dentro de `.git/` são duas: a linha `/.frontlights/` em `.git/info/exclude` quando a pasta
`.workflows/` é renomeada (`SKILL.md`, etapa 2), e as reservas de porta do `serve` em `frontlights-serve/ports/`.
Nenhum hook de permissão, configuração global ou modo de contorno; os controles do Claude e do GuardianS ficam.

## Autorização permanente

O usuário decidiu, de forma permanente e para todo projeto, que a etapa 6 abre sem pergunta: a sessão anuncia o que
fará e grava a autorização com `approval_reference` `"autorização permanente (docs/security.md)"`. O que ela cobre,
os merges cobertos e as negadas estão em `references/development.md`, "Standing authorization and the denied
operations". A decisão está escrita no Frontlights, não no `.frontlights/config.json`, para que um repositório
clonado não consiga ligá-la nem ampliá-la (regra da skill): os pedidos de permissão nativos do Claude Code continuam
valendo.

## Utilitários: o que cada um lê, grava e chama

Todo script importa `scripts/_cli.py`: `--root` é a worktree principal, a árvore é a da pasta atual, `--config` o
`<root>/.frontlights/config.json` e `--issue` sai só da entrada do charter cuja `path` é a árvore (sem ela, recusa
com `hint`). Saída acima de 4 KB ou 80 linhas vira resumo, e o JSON inteiro vai para `<árvore>/.frontlights/out/`.
Nenhum script roda shell. Os limites longos estão nas seções abaixo.

| Utilitário | Lê | Grava | Rede | Não prova |
|---|---|---|---|---|
| `frontlights.py inspect`, `validate-plan`, `schedule`, `publish-order`, `drift`, `context`, `evidence`, `review-gate`, `update-check` | config, plano, charter, Git | nada | `gh`, RoadS (`inspect` sem `--offline`); remoto da skill | que o config é seguro |
| `frontlights.py open` | o do `cleanup.py plan` e do `closeout.py candidates` | nada | `git fetch --prune`, `gh` | — |
| `frontlights.py init-config` | remotos, `gh project list` | o primeiro config (nunca `project`) | `gh` | o quadro certo |
| `frontlights.py authorize` | charter, operação | nada | nada | o Git |
| `frontlights.py charter new\|add\|own\|renew\|check\|map` | config, charters, portas | `authorization/<n>.json`, o anterior copiado | nada | — |
| `frontlights.py slice open\|merge` | charter, Git | branch e worktrees; merge `--no-ff` na worktree da issue | `git fetch`; imprime `gh issue develop` e o push | o teste certo |
| `frontlights.py artifact init\|section\|choose` | o template | só a fonte `artifact.html` | nada | o conteúdo |
| `frontlights.py publish-issue` | plano, aprovado (`stamp --check`) | issues e quadro; `publish/`; move `notes/` para a issue | `gh`, conta conferida a cada escrita | a intenção |
| `frontlights.py render-criteria`, `issue-lint` | plano, corpo | só o `--out` | `gh` | o mérito |
| `frontlights.py browser-gate` (`--answer`, `record`) | diff, `result.json` | `result.json` | nada | que o teste aconteceu |
| `frontlights.py checkpoint`, `resume`, `archive` | issue, handoff, registros | `checkpoint*.json`; `-r<k>` | `gh api` | o handoff |
| `stamp.py` (`frontlights.py stamp`) | o documento | `approvals.json` (`--approve`) | nada | quem respondeu |
| `homolog.py sync`, `bundle`, `suite`, `suite-gate`, `release-plan` | config, registros, Git | merge coberto; bundle; registro da suíte | `fetch`; `gh` | a suíte certa |
| `homolog.py merge` | charter, critérios, gate | `-integra`, main local, `merge-local-main-*.json`, bundle | `gh` | o teste assistido |
| `homolog.py release plan\|body-check\|go\|status\|landed` | registros, corpo, GitHub | `release/*.json`; `landed`: `pull --ff-only` | `gh`; imprime o push e o `gh pr create` | o merge |
| `closeout.py candidates\|verify\|merge-status\|tick-check` | issues e PRs | nada | `gh` | o quadro |
| `closeout.py run\|apply` | candidatos, lista carimbada | lista; `apply`: fecha e marca pais | `gh`, conta conferida | — |
| `closeout.py tick\|capture\|append` | corpo, aprovação | caixa, linhas, `pitfalls.md`, capturas | `gh`, conta conferida | compare-and-swap |
| `cleanup.py plan\|verify` | worktrees, branches, PRs | nada | `gh` | — |
| `cleanup.py run\|archive\|unlink` | o plano fresco | remove; copia registros; `out/` velho | `git fetch --prune` | processo de fora |
| `serve.py start\|stop\|status\|preview\|relay`, `checks.py` | config, árvore | `serve/`, `preview/`, registros | os `argv` | o argv |
| `serve.py window` | config (`browserTest.baseUrl`, `users`, `login`, `playwright`), `window.json` | `window.json`, prints (antes do número, `evidencias-pendentes/`), `print` no `result.json` | Chrome e o Playwright do projeto; nunca instala nada, para só o Chrome que abriu e não julga a passada | a passada |
| `serve.py free-test start\|stop\|commands` | config, registros | `teste-livre-cas.md`; processos | os `argv` | o fim do teste |
| `progress_report.py` (`keep` incluído), `roads.py` | config, fatos | aprovações, rascunhos; `resumo/` | RoadS | o print limpo |
| `skill_lint.py --shingles` | os textos da skill | nada | nada | que um trecho repetido é erro: só relata |

## Regras da sessão (nenhum script confere)

Em vigor desde 23/10/2026:

- Rode os scripts de dentro da worktree do trabalho, sem `--root`, `--config` nem `--issue`; numa recusa, passe o
  que o `hint` pede. Nunca adivinhe uma flag: o `--help` é a lista.
- De uma saída resumida (`summary: true`), leia de `full` só a chave que a etapa precisa; `--full` imprime tudo.
- Prefixo: `--prefix`, senão `branchPrefix` do config (na falta dela, o `branch_prefix` antigo do config, com
  `prefixSource: config:branch_prefix`; as duas divergentes: vale `branchPrefix`, com aviso
  `branch_prefix_conflict`), senão `branch_prefix` do charter; um registro antigo sem a chave é lido com
  `prefixSource: legacy`.
- Antes de cada escrita pelo `gh`, o script confere de novo a conta e o repositório; `account_mismatch` ou
  `repository_mismatch` viram a pergunta "Trocar para <conta> com `gh auth switch --user <conta>` e repetir" ou
  "Parar". A troca é do usuário.
- Nenhum script faz `git push`, `gh auth switch`, `gh pr merge` ou apaga registro; o que imprimem segue as regras da
  etapa. Nenhum mascara a senha do rascunho do config: ela não entra nele (`references/setup.md`).

## Recusas do `inspect`

O `inspect` confere só o que depende do config. A lista é a do código (`INSPECT_REFUSALS`, impressa no `inspect
--help`), e um teste compara as três; barra erro de configuração, não comando mal-intencionado.

<!-- inspect-refusals -->
- `repository` ausente, ou que não é `dono/nome` nem `null`
- `browserTest.users` com login ou senha de menos de 4 caracteres ou com o texto do marcador de máscara
- `health` ou `baseUrl` de `browserTest` e `checks` fora de `127.0.0.1`, `localhost` ou `::1`
- shell embutido nos `argv` de `checks` (cmd, sh, powershell, `.bat`, `&&`, `|`, `python -c`, `env`, `xargs`)
- `{port}` sem um processo de porta `auto`
- `browserTest.isolated` que ainda declara `copyDatabase` ou `dropDatabase` (mesmo `null`)
- `browserTest.isolated` com host que não é local, porta fixa igual à da prévia ou do `serve`, `baseUrl` fixa que não é a porta de um processo isolado, ou `cwd` de processo que sai da worktree
- `preview` com worktree fora do `--root`, sem branch, `baseUrl` fora da porta fixa local de um processo dela, ou processo com porta `auto` ou `{port}` no argv ou no `cwd`
- porta fixa de `browserTest.processes` ou da `browserTest.baseUrl` igual a uma porta da prévia
- `homolog` com chave além de `backupDir` e `suites`, e `homolog.suites` com chave além de `impact` e `full`
- `homolog.backupDir` relativo, com `..`, `~` ou marcador `{}`
<!-- /inspect-refusals -->

## Artefato do grilling

A entrevista publica um artefato, uma página privada da ferramenta de artefatos do host, na mesma URL em todas as
rodadas, e essa página fica fora da máquina: por isso separa código de dado. Código entra: um trecho real do código
do projeto, de até 15 linhas e com o caminho, com o valor de todo segredo (senha, token, chave, string de conexão)
trocado por `***`. Dado nunca entra: com tela, a base é um print do sistema rodando na base, tirado com conta de
teste e dados de teste, limpo pela regra de `references/browser-testing.md`, "Prints kept for the progress summary",
item "Clean", e cada opção é o mesmo print com marcações (na página, "base" e "com a opção", nunca antes/depois, que
são as janelas do teste assistido); nenhum registro real, dado de pessoa, endpoint real, nome de cliente ou
organização entra na página, nem num print nem num trecho de código. A fonte fica em `.frontlights/artifact.html`,
fora do Git. Sem a ferramenta, a sessão segue em texto e registra "artefato indisponível" no log de descoberta. O
esqueleto vem do script (`frontlights.py artifact`, que só grava a fonte local); conteúdo, publicação e URL são da
sessão, que publica a fonte inteira uma vez por rodada, nunca por `edits` (regra da skill).

## Subagentes

No paralelismo (`docs/protocol.md`), um subagente trabalha sob as mesmas permissões nativas da sessão que o lançou,
e o "Sim" de uma operação negada vale para a sessão coordenadora que o perguntou, nunca para um agente que a execute
por ela. O que o agente nunca faz está em `references/worker.md`, "What a worker never does" (regra da skill): os
pedidos de permissão continuam valendo para cada agente, e o relato dele é conferido (diff lido, comandos repetidos)
antes de virar evidência.

## `authorize` e a main local

O `authorize` confere uma operação contra a autorização registrada: repositório, issue, branch, worktree, validade,
monitoramento, tipo, caminhos da tarefa e argumentos de verificação; confere `edit`, `test`, `checkpoint` e
`merge_into_local_main` (numa worktree de slice, só a que nomeia a slice) e rejeita branch protegida, caminho fora
do escopo, arquivo de controle, implantação, publicação, operação destrutiva e qualquer outro merge; com branches
empilhadas, valem os merges cobertos de `references/development.md` ("Standing authorization and the denied
operations"), os únicos permitidos. Sempre retorna `permission_granted: false`.

**Main local e main remota.** A main local (a base do charter, na worktree principal) é a homologação. O `authorize`
aceita `merge_into_local_main` só com `target` igual a `base.branch` do charter, sem barra (`origin/main` e
`refs/remotes/...` são recusados como main remota), só da worktree de integração da issue (`<prefixo>issue-<n>-integra`,
cortada da branch da issue, local e nunca enviada) ou do trabalho sem issue (`issue` ou `direct`, nunca os dois;
nunca de uma slice) e com o `gates` de "Into the local main" (`references/development.md`), só o `browser_gate`, o
único portão; um `browser_gate` fora de `answered` ou `not_needed` é recusado nomeando o portão, e `suite_gate` e
`review_gate`, quando vêm, são aceitos sem exigência. `edit` e `test` na main local são recusados, e a main remota
só recebe a PR da release, operação negada. A branch da issue é a única branch de trabalho enviada antes da release
(criada por `gh issue develop`, só com os commits da issue); slices, prévia e main local nunca são enviadas. É
conferência prévia, não barreira: o `authorize` não lê o Git e não prova que o teste assistido foi respondido (quem
prova é o `browser-gate`).

## `homolog sync` e `homolog bundle`

**Sincronização da main local (`homolog sync`).** Trazer `origin/<base>` para a main local é merge coberto
(`references/development.md`, "Standing authorization and the denied operations"), sem shell e com prazo: exige a
principal na `<base>`, limpa, sem merge em andamento; um conflito é desfeito na hora e vira pergunta. Nunca envia,
nunca usa `--force`, `reset` nem `rebase`; o `fetch` do remoto configurado é a única rede.

**Merge na main local (`homolog merge`).** Os passos de "Into the local main" num comando, só pela coordenadora.
Recusa (saída 1) a principal suja ou fora da `<base>`, slice fora da branch da issue, caixa aberta e caixa sem tela
sem roteiro; o conflito fica na `-integra` (saída 2 com `files`) e um gate que não passa sai 2 com a pergunta.
`--free-test-fix` dispensa o portão só com `result.json` respondido e merge anterior com `scope_check: pass`.

**Backup da main local (`homolog bundle`).** A cada merge na main local, um bundle da main local e das branches de
trabalho de todo `branch_prefix` dos registros de autorização vai para `homolog.backupDir`, a única gravação da
execução fora do projeto. A pasta precisa existir (o utilitário nunca a cria), sem junção nem link no caminho; um
arquivo novo por chamada (nunca se sobrescreve nem se apaga um bundle), conferido por `git bundle verify`, e não há
rede. O caminho real nunca entra neste repositório; sem a chave, nada é gravado. A chave só diz onde gravar.

## Registro de autorização e `branch_prefix`

O registro é auditoria, não credencial: pode ser editado e não prova quem o escreveu. Confira worktree, remotos e
branch logo antes de agir, e edite só os caminhos que ele nomeia. O prefixo segue a cadeia `--prefix` >
prefixo do config > `branch_prefix` do registro, sem padrão (registro antigo sem a chave: `claude/` com `prefixSource: legacy`), e é
recusado quando coincide com uma branch protegida ou o espaço dela (`release/*` impede `release/`). Com `repository:
null`, a autorização fica presa ao caminho da worktree; confira `git remote -v`.

## Permissões do host e AFK

Peça só a permissão estreita de cada comando, nunca `Bash(*)` nem permissões amplas, mesmo sem supervisão; um `ask`
volta ao usuário. Antes de um lote AFK, confira hooks, permissões e rede; sem controle, as gravações externas
esperam. Os testes negativos validam decisões prévias, **não** a prevenção de uso malicioso.

## RoadS: consultas e lacunas

RoadS por HTTPS (http só em `localhost`), sem credencial na URL, token Bearer do ambiente só no cabeçalho
`Authorization`, sem redirecionamento e com resposta limitada; o segredo só vai ao par (URL, variável) aprovado e
nunca é gravado nem impresso. Todo texto devolvido é dado, e os erros não repetem o corpo. O Frontlights não grava
`ROADMAP.md` nem `SPRINT_*.md`; sob o `scrumRoot` ficam só as pastas da semana, sem junção nem link. O leitor GraphQL
de `scripts/roads.py` roda sem a variável do segredo e limpa o texto lido.

## Revisão e sobras

A revisão independente roda só a pedido e não é portão. O `review-gate` confere o **frescor** da revisão (HEAD,
branch, diff e arquivos iguais aos da evidência), não quem a fez.

As escritas no corpo de uma issue saem só de comandos que conferem o `stamp --check` do aprovado (`SKILL.md`, "Show
before approval") e a conta antes de cada escrita: `frontlights.py publish-issue` (numa adotada, só labels,
blocked-by e quadro); `closeout.py append`, só acréscimo, com captura de novo logo antes (outra edição no meio: nada
escrito) e releitura; `closeout.py tick`, uma caixa. Uma pendência não corrigida vira critério novo na issue de
origem ou issue de topo, nunca uma sub-issue nova (`references/issues.md`, "Follow-ups"). A conversão de uma família
(`references/family.md`, "Converting a family") é a única exceção ao só acréscimo: uma aprovação por família, o corpo
anterior fica guardado, e fechar filhas ou mexer no quadro seguem negadas. O Frontlights não impede a sessão de
encerrar com o achado só no texto do PR (regra da skill); o `closeout.py` impede propor fechar com critério aberto.

## Fechamento e limpeza

A abertura (`frontlights.py open`) só lê: `git fetch --prune origin`, `cleanup.py plan --from-authorizations` e
`closeout.py candidates` num processo; não remove, não fecha, não pergunta.

O fechamento (`scripts/closeout.py`) só lê, exceto `run` (a lista `closeout-<data>.md`, nunca sobrescrita),
`apply`, `tick`, `capture` e `append`; o que vem do GitHub é dado. Candidata é a issue aberta com todos os critérios
marcados cuja branch já está em `origin/<base>` (senão `awaiting_release`; as únicas leituras de Git são `rev-parse`
e `merge-base`); uma seção legada fora dos critérios só vira o aviso `pending_outside_criteria` (`pendingOutside`).
Nunca lê nem move um cartão. Fechar é aprovação própria; a exceção é a linha `Closes #n` da PR da release.

O `apply` (`--expect <carimbo> --answer "<resposta literal>" [--only n…]`) confere o carimbo da pergunta; recalcula e
recusa (`lista mudou: …`, nada escrito), sem gravar nem a aprovação; recusa um `--only` que deixe um pai escolhido sem a filha da
lista; só então grava a aprovação e roda o `stamp --check`; fecha filhas antes do pai, marca no pai o item da filha (um item que cita outras issues junto nunca é
marcado) e grava `.frontlights/closeout-<data>.result.json`. O `tick` troca um `[ ]` da seção de critérios, recusa a
caixa com `- Bloqueada:` e nunca regrava. O GitHub não tem compare-and-swap: uma edição de outra pessoa entre captura
e gravação é sobrescrita.

A espera do merge é regra da skill: a sessão age só sobre a resposta do `merge-status`, e o gatilho do ambiente
(inscrição na PR ou monitor) só a acorda.

A limpeza de worktrees e branches (`scripts/cleanup.py`) só lê, exceto o `archive`, o `unlink` e o `run`:
- usa `git --no-optional-locks` sem shell; razões e cautelas de cada candidato estão no `cleanup.py --help`;
- propõe a worktree registrada (ou branch sem worktree) que não é a principal, travada, em uso nem suja, numa branch
  não protegida, cujo tip é a cabeça de uma PR mesclada que chegou à base aprovada ou, sem PR nenhuma, cujo tip já
  está contido em `origin/<base>`; das branches remotas, só a da issue (a entrada da issue sem `slice`, nunca a
  `-integra`, a da release ou uma protegida) entra; nenhuma outra branch remota entra: o GitHub apaga a branch de
  cabeça da PR mesclada; o aviso `ignored_files` lista os nomes; a worktree de integração local (`--integration`) só
  entra sem PR;
- os comandos levam só caminhos registrados e nomes simples, nunca com `--force`;
- o `archive` copia o `.frontlights` de uma worktree (nunca a pasta `out/`) para a principal; recusa um destino com
  arquivo diferente ou a mais (nada é copiado, nada é sobrescrito), link no caminho e destino fora do `.frontlights`
  da worktree principal daquele repositório (lida do Git);
- o `run` replaneja e roda item a item: `archive`, junções e links de pasta desfeitos com `os.rmdir` (só o link; nunca
  o alvo, nunca dentro de `.frontlights`), `git worktree remove`, `git branch -D`; nunca roda `git push`: o `git push
  origin --delete` da branch da issue lançada e o `branch -D` dela ficam em `sessionCommands`; worktree presa fica em
  `excluded` como `in_use`; sem enxergar junção, nada entra (`junction_unverifiable`); grava
  `.frontlights/cleanup-<data>.json` como evidência;
- o `unlink` apaga só os arquivos do `emit` com mais de 30 dias em `.frontlights/out`;
- a limpeza do trabalho mesclado roda sem pergunta (a exceção escrita a "apagar qualquer coisa" das operações
  negadas): só pergunta o candidato com arquivo ignorado que não é dependência, build nem cópia byte a byte do mesmo
  caminho na worktree principal, e o candidato `out`.

## Resumo para a diretoria

O `scripts/progress_report.py` executa comandos do config, que um repositório clonado poderia trazer. Por isso:

- **Bloco aprovado:** `window`, `collect` e `push` só rodam com o bloco `roadmapSync.progress` inteiro aprovado
  (endereço, variável, rota, comandos, prazos, `scrumRoot`, `weekFolderPattern`, `weekShots`); mudou, volta a
  `changed`. A aprovação e o registro do projeto dono (`home --set`) são assinados com uma chave do diretório do
  usuário: copiado ou sem assinatura vale `invalid`.
- **Comandos e segredo:** listas de argumentos com prazo; só o envio recebe o segredo, e um comando que o traga nos
  argumentos é recusado; a rota fica dentro do endpoint aprovado.
- **Prints do teste assistido na pasta da sprint (`evidence-dir`):** decisão do mantenedor (19/10/2026): com
  `scrumRoot` e `weekFolderPattern`, os prints da rodada (`antes-<cover>-S<n>.png` e os do DEPOIS) e os do resumo vão
  para `<scrumRoot>/<semana>/evidencias/<repositório>/<issue>`, sem junção nem link. A pasta é compartilhada com a
  empresa: só dados de teste, nenhuma senha, dado real ou caminho local na tela.
- **Prints do resumo:** só com consentimento e dados de teste; nada é enviado antes do rascunho aprovado. Com
  `weekShots`, a pasta da semana é a única gravação do resumo fora do projeto; o `push` confere `captions.json` e as
  imagens antes do envio, e quem sobe é o comando do projeto.

Os testes usam transporte e datas simulados e não homologam o RoadS real.

## `serve`, `checks` e o teste no navegador

O `scripts/serve.py`, o `scripts/checks.py` e as suítes da homologação (`homolog suite`) executam comandos do config
(blocos `browserTest`, `checks` e `homolog.suites`; no `homolog suite`, também o `--argv` que a sessão passa):

- **Sem shell:** o filtro de shell dos `argv` de `checks` barra erro de configuração, não prova inocuidade; o
  `serve.py` só recusa metacaractere em `.cmd` ou `.bat`. O `homolog suite` aplica ao argv de `homolog.suites` e ao
  `--argv` o mesmo filtro de shell do `checks`, roda sem shell e, no prazo, mata a árvore inteira de processos.
- **Senha em texto:** `browserTest.users` guarda login e senha de contas **de teste** no config, fora do Git, risco
  aceito pelo mantenedor; mascarados em toda saída.
- **Dados que o teste cria:** decisão permanente do usuário: o teste usa as contas de teste que existem e cria sob
  demanda o que o `Fluxo:` pede, e esses dados ficam para reuso no banco de desenvolvimento local; apagar continua
  negada. Nunca produção, staging nem banco compartilhado. A senha de um login criado nunca é impressa nem gravada.
- **Instância isolada do teste assistido (`browserTest.isolated`):** processos e portas próprios, nunca nas portas da
  prévia, no próprio banco de desenvolvimento local, que é o de homologação, nunca numa cópia; sem shell, nunca
  produção, e o `inspect` recusa o bloco que ainda declare `copyDatabase` ou `dropDatabase`.
- **Teste assistido:** cada janela abre depois de "pronto para assistir?", com contas de teste e perfil descartável;
  perfil de usuário só muda pelo endpoint do produto, com o original em `browser/perfil-original.json`. A aba da
  prévia é do usuário e fica fora dessa regra: o teste assistido nunca usa a prévia nem as portas dela (a prévia, sem
  `{port}` no argv nem no `cwd`). A aprovação é só a resposta ("Aprovado", "Pode prosseguir", "Assistir de novo",
  "Precisa de alteração"): o Frontlights nunca grava `aprovacao: "aprovado"` por conta própria. O teste é um por
  issue, o único portão do merge na main local; a dispensa (`dispensado`) é decisão explícita do usuário.

## Limites conhecidos

Os testes rodaram só no Windows. O celular exige confirmação do usuário na sessão; nada detecta o dispositivo nem
grava tarefa agendada. Limiares de contexto: `docs/protocol.md`, "Contexto e conclusão"; nenhum hook garante teto.
A interceptação real de permissões é verificação manual; mantenha o GuardianS ativo até ela.
