# Recuperação e reversão

1. Pare de distribuir novas tarefas; permita que operações seguras em andamento
   salvem seus pontos de retomada. Não encerre processos alheios nem remova a
   worktree de outra sessão.
2. Preserve alterações não salvas em commits, evidências, branches e `.frontlights/`.
   Confira o estado real do Git e a responsabilidade pela worktree antes de retomar.
   Não execute limpeza ou restauração automática.
3. Inicie uma nova sessão do Claude com o mesmo projeto e a skill instalada. Leia a issue,
   a autorização e o documento de passagem de contexto. Consulte novamente o GitHub
   e compare a saída de `resume`.
4. Trate as divergências na sessão coordenadora. Autorização vencida, critérios de
   aceitação alterados, novas permissões ou credenciais ausentes exigem decisão humana.
5. Se uma publicação no GitHub exceder o tempo de espera, confira o conteúdo e os
   links das issues existentes antes de tentar novamente. Registre planos publicados
   parcialmente e atualize os identificadores somente com resultados verificados.
   Não duplique tickets para contornar respostas incertas.
6. Restabeleça o Remote Control na própria sessão atual e obtenha confirmação pelo
   celular ou pela alternativa escolhida. Não presuma que a conexão anterior continua ativa.

Para deixar de usar a skill, encerre a sessão e remova a junção `~/.claude/skills/frontlights`
(`rmdir`, que apaga só o atalho, nunca o repositório). Se o Frontlights ainda estiver instalado
como plugin de uma versão antiga, use `claude plugin uninstall frontlights@frontlights` depois
de conferir a lista de instalações. Preserve worktrees, registros e issues do
usuário. Este repositório não possui instalador ou desinstalador que altere o GuardianS.

A troca do fluxo padrão e a desativação do GuardianS são decisões humanas separadas,
tomadas após a revisão das evidências de aceitação. O Frontlights não as executa.
