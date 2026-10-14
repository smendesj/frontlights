# Frontlights

Skill avulsa para Claude Code, antes chamada Workflows e, até a 0.28.1, distribuída como plugin.
Entrada: `/frontlights`, ou uma frase que cite o Frontlights. A skill inteira é a pasta
`skills/frontlights`: `SKILL.md` define a ordem das etapas, as instruções detalhadas de cada
etapa ficam em `references/`, e `scripts/`, `templates/`, `examples/` e `docs/` (protocolo e
segurança) vivem dentro dela, referidos por `${CLAUDE_SKILL_DIR}`. Leia a skill antes de
alterar o fluxo. `tests/`, `evals/` e a documentação da raiz são ferramental de quem desenvolve
o Frontlights e ficam fora da skill.

Idioma: mantenha README, documentação, modelos, exemplos e textos apresentados ao
usuário em português. Somente as skills são redigidas em inglês; elas devem orientar
respostas e documentos em português. Preserve comandos e identificadores técnicos.

O GitHub é a fonte oficial de escopo, critérios de aceitação, dependências e situação
das issues. Registros locais são evidências e cópias de referência, nunca tickets
duplicados. Informe divergências. Faça todas as perguntas por `AskUserQuestion`;
não invente aprovação. Descoberta, texto da issue e publicação de issues têm aprovações
separadas. A implementação (etapa 6) roda sob a autorização permanente, decisão do
mantenedor para todo projeto: abre sem pergunta, e cada operação negada (merge,
fechar issue, quadro, produção, migration registrada, branch base ou protegida) só
roda depois do "Sim" de uma pergunta própria (`skills/frontlights/docs/security.md`).

Este repositório é público. Nunca versione endpoint real, segredo, token, nome de
organização, produto, cliente ou pessoa, caminho local de máquina, nem saída
capturada de sessão real. Exemplos, modelos, testes e documentação usam apenas
marcadores genéricos (`OWNER/REPOSITORY`, `roads: null`). Configuração real vive
fora deste repositório, no `.frontlights/config.json` do projeto de destino.

Instalação e atualização são o Git: `~/.claude/skills/frontlights` é uma junção para
`skills/frontlights` do clone, então um commit na `main` já é a versão instalada em quem
fez `git pull`, e uma sessão nova a lê. Não há número de versão a subir; o `update-check`
da etapa 0 compara o `HEAD` do clone com o remoto, e o User-Agent enviado ao RoadS leva o
commit.

Use worktrees isoladas. A autorização comum de implementação não permite escrever
em branches protegidas, fazer merge, implantar ou publicar versões sem o "Sim" da
pergunta própria de cada operação. Preserve o
GuardianS e os dados do usuário. Leia `skills/frontlights/docs/protocol.md` para execução e
retomada, e `skills/frontlights/docs/security.md` para os limites de aplicação das permissões.
Execute `python -m unittest discover -s tests -v` e
`python -m compileall -q skills/frontlights/scripts tests`.
Não apresente testes com dados simulados como homologação de integrações reais.
