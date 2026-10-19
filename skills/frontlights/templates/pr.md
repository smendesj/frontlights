# Modelo do corpo da PR

Este é o modelo do corpo da PR que o Frontlights abre: a PR única da release, que leva da main local ao
GitHub as issues homologadas (etapa 6, `references/development.md`). Escreva na língua do usuário (em
português para quem fala português, como este modelo), curto, sem preâmbulo e com o vocabulário do domínio do
projeto. Preencha cada seção, apague estas orientações e os marcadores `<...>`. A guia do Resumo é adaptada,
em palavras nossas, da skill show-me, sob a licença MIT (`references/LICENSE-pr.md`).

A PR cita a issue pelo número, sem palavra de fechamento (`Closes`, `Fixes`, `Resolves` ou variante), no
corpo e nos commits: fechar uma issue tem aprovação própria. E o corpo da PR nunca é destino de um achado:
um achado sem correção sai antes, como critério de aceitação novo da issue de origem ou como issue de topo, e
o corpo só cita esse destino.

## Resumo

Um bloco por issue: uma frase com o que ela entrega e o menor visual que deixa o ponto claro. Escolha a forma
pelo ponto: pseudocódigo para uma lógica, árvore de chamadas para o fluxo em execução, árvore de componentes
para uma tela, árvore de arquivos para a responsabilidade dos arquivos ou uma refatoração ampla, Mermaid para
a interação entre partes, e um `diff` sobre uma dessas formas quando o ponto é o que muda. Um ou dois visuais
por issue, cada um ao lado da frase que sustenta, só com o que responde à pergunta de quem revisa. O trabalho
sem issue da release (o `releaseDirect` do `release-plan`) leva um bloco igual, com o título `### Melhoria <slug>`.

### Issue #<a>: <título>

<uma frase: o que a issue entrega>

```text
<o menor visual>
```

## Evidência

Por issue, o antes e o depois concretos. Os prints do teste assistido valem mais, quando a mudança aparece na
tela; depois vem o teste que falhava e passou a passar (o nome dele ou um pseudocódigo do caso), com o comando
e o resultado medidos. A evidência só aponta registros que já existem: os prints do teste assistido, o
checkpoint e os comandos de cada CA, a revisão independente e os três portões do merge na main local. A
sessão nunca inventa evidência nem descreve um teste que não rodou. Um print é citado pelo nome do arquivo e
pela pasta `.frontlights/issues/<n>/browser/` da worktree da issue (a da issue líder, numa família), com uma
frase do que ele mostra, e quem revisa o abre no projeto local: nunca caminho absoluto, imagem anexada ou commitada, login ou dado de pessoa.
O trabalho sem issue leva o bloco `### Melhoria <slug>`, com os registros em `.frontlights/direct/<branch>/`
(barras como hífens) no lugar da pasta da issue.

### Issue #<a>

- **Antes:** <print do teste assistido, ou o teste vermelho: comando e falha>
  **Depois:** <print do teste assistido, ou o mesmo teste verde: comando e resultado>
- **Portões:** suíte por impacto <`suite-gate`, contagem, saída>; revisão independente <rodadas, `review-gate`
  atual>; teste assistido <resposta do usuário, ou `not_needed`>.

## Risco do merge

Um só, consolidado para a release inteira. A porta é de mão única quando há migration ou dado apagado: diga
qual e o que um retorno exigiria. Nos outros casos é de mão dupla: o merge se desfaz barato, revertendo o
commit de merge. O raio de impacto é uma palavra e, se preciso, o que o merge pode atingir; considere todas as
possibilidades: quem consome o que mudou, telas e layout, as outras issues da mesma release, configuração,
scripts e documentação.

**Porta:** <mão única ou mão dupla>

<opcional: por quê>

**Raio de impacto:** <uma palavra>

<opcional: o que o merge pode atingir>
