# Modelo do corpo da PR

Este é o modelo do corpo da PR que o Frontlights abre: a PR única da release, que leva da main local ao
GitHub as issues homologadas (etapa 6, `references/development.md`). Escreva em português, curto e sem
preâmbulo, na língua do domínio do projeto. Preencha cada seção, apague estas orientações e os marcadores
`<...>`. O modelo é adaptado, em palavras nossas, de um modelo de PR de terceiros, sob a licença MIT
(`references/LICENSE-pr.md`).

A PR cita a issue pelo número, sem palavra de fechamento (`Closes`, `Fixes`, `Resolves` ou variante), no
corpo e nos commits: fechar uma issue tem aprovação própria. E o corpo da PR nunca é destino de um achado:
um achado sem correção sai antes, como critério de aceitação novo da issue de origem ou como issue de topo, e
o corpo só cita esse destino.

## Resumo

Um bloco por issue: uma frase com o que ela entrega e o menor visual que deixa o ponto claro. Escolha a forma
pelo ponto: pseudocódigo para uma lógica, árvore de chamadas para o fluxo em execução, árvore de componentes
para uma tela, árvore de arquivos para a responsabilidade dos arquivos ou uma refatoração ampla, Mermaid para
a interação entre partes, e um `diff` sobre uma dessas formas quando o ponto é o que muda. Um ou dois visuais
por issue, cada um ao lado da frase que sustenta, só com o que responde à pergunta de quem revisa.

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
sessão nunca inventa evidência nem descreve um teste que não rodou.

### Issue #<a>

- **Antes:** <print do teste assistido, ou o teste vermelho: comando e falha>
  **Depois:** <print do teste assistido, ou o mesmo teste verde: comando e resultado>
- **Portões:** suíte inteira <comando, contagem, saída>; revisão independente <rodadas, `review-gate`
  atual>; teste assistido <resposta do usuário, ou `not_needed`>.

## Risco do merge

Um só, consolidado para a release inteira.

**Porta:** <mão única ou mão dupla>

<opcional: por quê> Mão dupla: o merge se desfaz barato, revertendo o commit de merge. Mão única: há
migration, dado apagado ou outra decisão difícil de desfazer; diga qual e o que um retorno exigiria.

**Raio de impacto:** <uma palavra>

<opcional: o que o merge pode atingir> Considere todas as possibilidades: quem consome o que mudou, telas e
layout, as outras issues da mesma release, configuração, scripts e documentação.
