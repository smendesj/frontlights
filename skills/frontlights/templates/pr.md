# Modelo do corpo da PR

Corpo da PR única da release (`references/development.md`, "The release"), na língua do usuário, com o vocabulário
do domínio do projeto; apague estas orientações e os `<...>`. O Resumo é adaptado da skill show-me
(`references/LICENSE-pr.md`).

Cada issue do `closes` do `release-plan` ganha uma linha como a linha-modelo logo antes de `## Resumo`, copiada da
lista, nunca contada à mão, uma linha simples por issue, fora de bloco de código; essas linhas ficam quando estas
orientações são apagadas (com `closes` vazio, apague a linha-modelo), e só o merge aprovado da PR a fecha. As outras
a PR cita pelo número, sem palavra de fechamento (`Closes`, `Fixes`, `Resolves`), e elas seguem a pergunta de
fechamento da etapa 7; e o corpo da PR nunca é destino de um achado.

Closes #<n>

## Resumo

Um bloco por issue: uma frase e o menor visual que deixa o ponto claro (pseudocódigo, árvore de chamadas, árvore de
arquivos, Mermaid, `diff`: as formas da skill `pr`); sem issue, `### Melhoria <slug>`.

### Issue #<a>: <título>

<uma frase>

```text
<o menor visual>
```

## Evidência

A evidência só aponta registros que já existem e a sessão nunca inventa: os prints do teste assistido, o teste que
falhava e passou a passar, o checkpoint, a revisão independente pedida e o portão do merge na main local, o teste
assistido. Um print é citado pelo nome do arquivo e pela pasta `.frontlights/issues/<n>/browser/` da worktree da
issue (a da issue líder, numa família), com uma frase do que ele mostra; quem revisa o abre no projeto local: nunca
caminho absoluto, imagem anexada ou commitada, login ou dado de pessoa.

### Issue #<a>

- **Antes:** <print `antes-<cover>-S<n>.png`, ou o teste vermelho>
  **Depois:** <print `depois-<cover>-S<n>.png`, ou o teste verde>
- **Portões:** teste assistido <resposta do usuário, ou `not_needed`>.
- **Testes e revisão:** só quando rodaram: <comando, contagem, `review-gate`>. Apague a linha quando nenhum rodou.

## Risco do merge

Um só, consolidado. A porta é de mão única quando há migration ou dado apagado (diga qual). Nos outros casos é de
mão dupla. O raio de impacto é uma palavra.

**Porta:** <mão única ou mão dupla>

<opcional: por quê>

**Raio de impacto:** <uma palavra>

<opcional: o que o merge pode atingir>
