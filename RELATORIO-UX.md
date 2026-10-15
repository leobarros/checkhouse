# Relatório de UX — CheckHouse

Este documento descreve a auditoria e a uniformização de experiência feita sobre
o projeto CheckHouse: **tema claro/escuro**, **tipografia e ícones**, e
**comportamento em desktop e telemóvel**.

Evidências em imagem: [`docs/ux/`](docs/ux/).

---

## 1. Método

| O que foi validado | Como |
| --- | --- |
| Tema claro e tema escuro | Firefox 157 headless com perfis que forçam `prefers-color-scheme` claro/escuro (simula o sistema do utilizador) |
| Contraste de texto/ícones | (a) cálculo WCAG 2.1 das variáveis CSS servidas; (b) medição **no browser**, sobre o DOM renderizado, com `getComputedStyle` + composição de alfa |
| Tipografia e fonte de ícones | verificação de `getComputedStyle(body).fontFamily` e `document.fonts.check('16px "bootstrap-icons"')` |
| Desktop e telemóvel | capturas em 320 / 390 / 1024 / 1366 px, claro e escuro, e medição de `scrollWidth` vs `innerWidth` (scroll horizontal), alvos de toque e rótulos acessíveis por página |
| Imagens | favicon SVG renderizado nos dois esquemas de cor do navegador |

Foram auditadas as 9 rotas com interface: `/`, `/despensa/<id>` (com e sem
itens), `/lista/<id>` (com e sem itens), `/configuracoes`, `/compras/<id>`,
`/login` e `/registrar`.

---

## 2. Resultados (antes → depois)

| Indicador (nas 9 páginas) | Antes | Depois |
| --- | --- | --- |
| Páginas com scroll horizontal a 320/390 px | 0 | **0** |
| Pares texto/fundo abaixo de WCAG AA — tema claro | 4 | **0** |
| Pares texto/fundo abaixo de WCAG AA — tema escuro | 3 | **0** |
| Falhas de contraste medidas no browser (390 px) | 1–7 por página | **0** |
| Controles só com ícone sem nome acessível | 48 | **0** |
| Alvos de toque < 40 px em ecrã estreito/toque | 20+ | **0** (ligações em linha de texto são isentas pela WCAG 2.5.8) |
| Páginas que respeitavam o tema do sistema | 0 (tema forçado em claro) | **9** |
| Flash de tema claro ao abrir uma página em modo escuro | em todas | **nenhum** |

### Evidências em imagem

| Ficheiro | O que mostra |
| --- | --- |
| [`antes-depois-index-escuro.png`](docs/ux/antes-depois-index-escuro.png) | Página inicial em modo escuro (desktop): tema ignorado → tema aplicado |
| [`antes-depois-despensa-escuro.png`](docs/ux/antes-depois-despensa-escuro.png) | Despensa no telemóvel: tabela apertada → cartões com alvos grandes |
| [`antes-depois-lista-escuro.png`](docs/ux/antes-depois-lista-escuro.png) | Lista de compras no telemóvel: item concluído, quantidades e lixo |
| [`antes-depois-configuracoes-escuro.png`](docs/ux/antes-depois-configuracoes-escuro.png) | Configurações: um botão "Alternar Tema" → Claro/Escuro/Sistema e formulários rotulados |
| [`antes-depois-compras-escuro.png`](docs/ux/antes-depois-compras-escuro.png) | Página "Em falta": cartões brancos (`bg-light`) e checkboxes sem ação → lista coerente |
| [`antes-depois-login-escuro.png`](docs/ux/antes-depois-login-escuro.png) | Login: cartão claro em página escura e emoji → hierarquia e ícones consistentes |
| [`antes-depois-despensa-vazia-claro.png`](docs/ux/antes-depois-despensa-vazia-claro.png) | Estado vazio padronizado (despensa sem produtos) |
| [`antes-depois-lista-vazia-escuro.png`](docs/ux/antes-depois-lista-vazia-escuro.png) | Estado vazio padronizado (lista sem itens) |
| [`auditoria-claro-390px.png`](docs/ux/auditoria-claro-390px.png) · [`auditoria-escuro-390px.png`](docs/ux/auditoria-escuro-390px.png) · [`auditoria-escuro-320px.png`](docs/ux/auditoria-escuro-320px.png) · [`auditoria-claro-1024px.png`](docs/ux/auditoria-claro-1024px.png) | Saída da auditoria no browser por rota: scroll horizontal, alvos de toque, contraste, nomes acessíveis, fonte de ícones e pilha tipográfica |
| [`favicon-modo-claro.png`](docs/ux/favicon-modo-claro.png) · [`favicon-modo-escuro.png`](docs/ux/favicon-modo-escuro.png) | Favicon SVG nos dois esquemas de cor do navegador |
| [`fila-offline-modo-claro.png`](docs/ux/fila-offline-modo-claro.png) · [`fila-offline-modo-escuro.png`](docs/ux/fila-offline-modo-escuro.png) | Barra de estado da fila offline e avisos, nos dois temas |
| [`lista-com-fila-offline.png`](docs/ux/lista-com-fila-offline.png) | Lista de compras no telemóvel já com a fila offline (linhas, alvos de toque e item concluído) |

---

## 3. Tema claro / escuro

### O que estava errado

1. **O tema do sistema era ignorado.** O `data-bs-theme="light"` do HTML só era
   trocado por JavaScript no fim do `<body>`, e apenas se existisse uma
   preferência gravada em `localStorage`. Quem usava o telemóvel/desktop em modo
   escuro via a aplicação sempre em claro (ver `docs/ux/antes-depois-*.png`).
2. **Flash de tema (FOUC).** Mesmo com preferência gravada, a página era pintada
   em claro e só depois trocava para escuro — um "flash branco" a cada clique.
3. **Cores fixas de um só tema:** `bg-light` (cartões brancos no meio do escuro,
   texto de baixo contraste), `text-light` sobre botões amarelos (`btn-warning`)
   e `opacity-75` em itens concluídos (baixava o contraste abaixo do mínimo).
4. **Texto amarelo sobre fundo branco** nos títulos de *Lista* e *Despensa*
   (`text-warning` = 1,66:1 de contraste — praticamente ilegível no modo claro).
5. **Barra de navegação azul saturada** também no modo escuro, sem relação com as
   superfícies escuras do resto da página.

### O que foi feito

- **Arranque do tema antes do CSS.** Um pequeno script no `<head>` define o
  `data-bs-theme` antes de qualquer folha de estilo — não há flash nem
  re-pintura.
- **Passou a seguir o sistema** (`prefers-color-scheme`) quando o utilizador
  ainda não escolheu, e a acompanhar mudanças do sistema em tempo real.
- **Preferência explícita em Configurações**: `Claro`, `Escuro` e `Sistema`
  (com estado ativo e `aria-pressed`), persistida em `localStorage` e
  sincronizada entre separadores. O item do menu continua a ser um atalho de
  dois estados (ícone e texto passam a "Modo claro"/"Modo escuro").
- **`<meta name="theme-color">` dinâmico** (cor da barra do navegador no
  telemóvel acompanha o tema) e `<meta name="color-scheme">` para que controlos
  nativos (scrollbars, inputs, date pickers) sigam o tema.
- **Tokens por tema** em `static/css/app.css`: fundo da barra, cor do texto da
  barra, cor de destaque e cor de borda dos campos — uma única fonte de verdade
  para os dois temas.
- **Regra de cor semântica:** texto/ícones com significado usam as variantes
  `*-emphasis` do Bootstrap (`text-danger-emphasis`, `text-warning-emphasis`, …),
  que são recalibradas por tema; as cores base ficam reservadas a fundos e
  botões. Isso eliminou os casos de vermelho/amarelo "vivos" sobre fundo claro e
  escuro.
- **Superfícies elevadas coerentes:** itens concluídos usam `--bs-secondary-bg`
  (em vez de `opacity`), e o texto secundário no escuro foi reforçado
  (`--bs-secondary-color`) porque o cinza predefinido do Bootstrap ficava em
  3,8:1 sobre essas superfícies.

### Contraste (amostra da auditoria WCAG)

| Elemento | Claro | Escuro | Mínimo |
| --- | --- | --- | --- |
| Texto normal | 15,43:1 | 7,43:1 | 4,5 |
| Texto secundário (metadados) | 6,76:1 | 12,43:1 | 4,5 |
| Título/ícone `text-warning-emphasis` | 7,99:1 | 11,38:1 | 4,5 |
| Título/ícone `text-danger-emphasis` | 13,65:1 | 6,10:1 | 4,5 |
| Botão primário / perigo / aviso | 4,50 / 4,53 / 12,88 | 4,50 / 4,53 / 12,88 | 4,5 |
| Barra de navegação | 4,50:1 | 5,55:1 | 4,5 |
| Borda dos campos de formulário | 3,03:1 | 3,29:1 | 3,0 |

Casos corrigidos por esta auditoria, medidos no estado anterior:

**Tema claro**

- `btn-warning` com `text-light` (branco sobre amarelo, botão "Lista"): **1,63:1**;
- títulos `text-warning` (amarelo sobre branco, *Lista* e *Despensa*): **1,63:1**;
- metadados de item concluído (`text-muted` + `opacity-75` sobre `bg-body-secondary`): **2,63:1**;
- borda dos campos de formulário: **1,30:1** (mínimo 3,0 para limites de controlo).

**Tema escuro**

- `bg-light` na página *Compras* (texto do tema escuro sobre cartão branco): **1,99:1**;
- botões `btn-outline-secondary` (voltar, +/−): **3,43:1**;
- borda dos campos de formulário: **1,89:1**.

---

## 4. Fontes e imagens

### Tipografia

- Uma única pilha tipográfica em todas as páginas
  (`system-ui, -apple-system, "Segoe UI", Roboto, …`), aplicada em `body` no
  `static/css/app.css` e confirmada no browser (`fonte:system-ui` em todas as
  rotas). Evita que o texto mude de desenho/métrica entre Linux, Windows, macOS,
  Android e iOS.
- Números em quantidades e datas com `font-variant-numeric: tabular-nums`, para
  as colunas não "dançarem" ao mudar de valor.
- Hierarquia uniformizada: uma `h1` por página (antes os títulos eram `h3`/`h5`
  misturados e a página inicial não tinha título), cartões com `h2.h5`, e
  `<small>`/`.ch-item-meta` para metadados.

### Ícones e imagens

- **A fonte de ícones (Bootstrap Icons) era carregada por CDN**: sem internet —
  o cenário natural numa Home Lab — a página perdia o CSS e o botão do menu
  ficava um quadrado vazio. Os ficheiros passaram a ser servidos localmente
  (`static/vendor/`), com um *fallback* automático para CDN caso faltem (ver
  `static/vendor/LEIA-ME.md`). A carga da fonte é hoje verificável no browser:
  `document.fonts.check('16px "bootstrap-icons"')` → `carregada` nas 9 rotas.
  As capturas `antes` mostram justamente um ícone de lixo que não renderizou.
- **Emojis substituídos por ícones vetoriais:** `🏠`, `🛒` e `⬅` desenham de
  forma diferente em cada sistema operativo (e a preto/branco ou a cores). Foram
  trocados por `bi-house-door-fill`, `bi-cart` e `bi-arrow-left`, ficando iguais
  nos dois temas e em qualquer dispositivo.
- **Novo favicon SVG adaptativo** ([`static/icons/favicon.svg`](static/icons/favicon.svg)):
  em barra de abas clara usa azul + casa branca; em barra escura usa azul claro +
  casa azul-escura, ficando legível nos dois casos (ver
  `docs/ux/favicon-modo-claro.png` e `docs/ux/favicon-modo-escuro.png`). O
  favicon anterior dependia de um emoji.
- **Não existem imagens raster no projeto** — não há `<img>`, logótipos ou
  fotografias; as únicas "imagens" eram o emoji do favicon/marca e os ícones da
  fonte, ambos tratados acima.

---

## 5. Desktop e mobile

- **Uma largura de conteúdo por tipo de página** (`46rem` para páginas normais,
  `30rem` para login/cadastro), em vez de `col-md-6 offset-md-3` numa página e
  `col-md-8 offset-md-2` noutra: a interface deixou de "saltar" de largura ao
  navegar.
- **Cabeçalho de página padrão** (voltar + título + ação) em todas as páginas
  internas, incluindo Configurações (que antes não tinha caminho de volta).
- **Alvos de toque de 44 px** sempre que o dispositivo é de toque **ou** a janela
  tem menos de 576 px. Os `+`/`−` da despensa e os ícones de lixo/lápis tinham
  ~30×25 px — difíceis de acertar com o dedo. A auditoria no browser confirma
  **0 alvos < 40 px** a 320 e 390 px.
- **Formulários que se empilham**: o campo de nome ocupa a linha toda e o botão
  de adicionar também (em ecrãs muito estreitos), em vez de espremer o texto num
  `input-group`.
- **A tabela da despensa passou a lista de cartões**, com a mesma estrutura de
  linha da Lista de compras: acabou o *scroll* horizontal, os controlos ficaram
  grandes e as duas páginas passaram a ser reconhecíveis entre si.
- **Sem scroll horizontal:** medido em 320, 390 e 1024 px nas 9 rotas
  (`scrollWidth == innerWidth` em todas).
- **`autofocus` só em desktop** (o teclado do telemóvel já não abre sozinho ao
  entrar numa página) e o foco em modais passa a ser feito ao abrir o modal, em
  vez de no `<input>` escondido.
- **Sem submissões duplicadas:** tocar duas vezes em "Adicionar" já não cria dois
  itens.
- **Posição de scroll preservada** ao marcar/remover itens numa lista longa (a
  página já não volta ao topo).
- **Menu igual em desktop e mobile** (hambúrguer sempre no mesmo sítio, com
  largura limitada a `calc(100vw - 1.5rem)` para nunca sair do ecrã).

---

## 6. Consistência de linguagem e componentes

- **Português do Brasil unificado**: "Palavra-passe" → "Senha", "Guardar
  Alterações" → "Salvar alterações", "utilizador" → "usuário", "a sua conta" →
  "a sua conta" (pt-BR), "tem a certeza" → "tem certeza", "ficheiros" →
  "arquivos", entre outros. (`lang="pt-BR"` no `<html>`.)
- **Estados vazios padronizados** com um componente único
  (`_macros.html → vazio(ícone, título, texto)`), antes feitos com `alert-info`,
  `alert-success` e `text-muted` misturados.
- **Semântica de botões uniforme**: primário = ação principal (adicionar),
  aviso = lista de compras, perigo = destrutivo, outline = secundário/navegação.
  Antes o mesmo "adicionar" era azul numa página e verde na outra, e o
  "Adicionar à lista" era amarelo.
- **Espaçamento ícone/texto** consistente (`<i class="bi bi-cart me-1">`), antes
  havia `<i class="bi bi-cart"></i>Lista` colado.
- **Avisos (flash) passaram a ser globais**, no `base.html`, com ícone por tipo,
  botão de fechar e `role="alert"`/`aria-live` — antes só apareciam em três
  páginas e cada uma repetia o próprio bloco.
- **HTML corrigido**: `login.html` tinha tags de fecho duplicadas/órfãs
  (`</form></div></div></div>`) no fim do ficheiro.
- **Textos de confirmação mais claros**: o modal "Limpar" explica que os produtos
  já foram somados à despensa; os modais de exclusão dizem o que vai ser apagado.
- O botão "Limpar comprados" só aparece quando existe algo comprado (antes estava
  sempre visível e não fazia nada quando não havia nada para limpar).

---

## 7. Acessibilidade

- Todos os botões só com ícone têm `aria-label` e `title` descritivos. Contagem
  nas 9 páginas (com o mesmo conteúdo de teste): **48 → 0** controlos sem nome
  acessível — incluindo os `+`/`−` da despensa e da lista, que antes eram só um
  ícone sem texto alternativo.
- Modais com `aria-labelledby` a apontar para o título e `.btn-close` com
  `aria-label="Fechar"`.
- Ligação "Ir para o conteúdo" (skip link) e `<main id="conteudo">` focável.
- Foco visível reforçado nos botões só com ícone e na barra de navegação.
- `prefers-reduced-motion` respeitado (animações/transições reduzidas).
- Campos de formulário com `<label>` (alguns visualmente escondidos, para não
  perder a densidade visual) e `autocomplete` correto
  (`username`, `current-password`, `new-password`).
- Erros/avisos anunciados por leitores de ecrã (`role="alert"` + `aria-live="polite"`).

---

## 8. Ficheiros alterados

| Ficheiro | Alteração |
| --- | --- |
| `static/css/app.css` | **novo** — tokens, temas, componentes (cabeçalho, itens, estados vazios, alvos de toque) |
| `static/js/app.js` | **novo** — tema (claro/escuro/sistema), autofocus, foco em modais, scroll, anti-duplo-envio |
| `static/icons/favicon.svg` | **novo** — favicon adaptativo ao tema do navegador |
| `static/vendor/**` | **novo** — Bootstrap 5.3.0 + Bootstrap Icons 1.11.1 locais (+ `LEIA-ME.md`) |
| `templates/_macros.html` | **novo** — componentes reutilizáveis (estado vazio, quantidade) |
| `templates/base.html` | arranque do tema sem flash, navbar por tema, avisos globais, rodapé, assets locais, skip link |
| `templates/index.html` | cabeçalho, cartão de adicionar, cartões de local com ícones e nomes longos |
| `templates/despensa.html` | tabela → lista de cartões, modais acessíveis, formulário uniformizado |
| `templates/lista.html` | cabeçalho, formulário uniformizado, linhas de item com alvos grandes, modais |
| `templates/configuracoes.html` | seletor de tema (3 opções), rótulos e dicas nos formulários, backup empilhável |
| `templates/login.html` | HTML corrigido, marca em ícone, rótulos, autocomplete |
| `templates/registrar.html` | marca em ícone, rótulos, dica de senha |
| `templates/compras.html` | modo escuro corrigido, ícones e estado vazio consistentes |
| `static/js/fila.js` | **novo** — fila offline durável (com junção de operações, novas tentativas e idempotência) |
| `static/js/estado-fila.js` | **novo** — barra de estado da fila e avisos rápidos |
| `static/js/pagina-lista.js` | **novo** — Lista com atualização imediata da interface |
| `static/js/pagina-despensa.js` | **novo** — Despensa com atualização imediata da interface |
| `static/sw.js`, `static/offline.html`, `static/manifest.webmanifest`, `static/icons/*.png` | **novos** — Service Worker, página sem ligação, instalação no ecrã principal |
| `templates/base.html`, `lista.html`, `despensa.html` | ganchos para a fila offline, indicador de estado, assets com versão |
| `app.py` | **alterado nesta 2.ª intervenção** — API JSON, idempotência, `401` em JSON, `/sw.js`, manifest, cache dos assets |
| `models.py` | **alterado nesta 2.ª intervenção** — tabela nova `operacao_cliente` (criada pelo `db.create_all()`, sem alterar tabelas existentes) |

A primeira intervenção não tocou em `app.py`/`models.py`; a segunda (fila
offline, pedida depois) acrescentou a API JSON e a tabela de idempotência. Os
dados existentes não são alterados: `db.create_all()` apenas cria a tabela nova.

---

## 9. Fila offline no telemóvel (2.ª intervenção)

Depois de usar a app no supermercado com rede fraca, ficou claro que a demora
não era só da rede: cada toque fazia `POST` + redirect + download da página
inteira (duas idas ao servidor por toque) e a interface só reagia no fim.

Foi acrescentada uma **fila offline** com atualização imediata da interface:

- ações da **Lista** e da **Despensa** passam por uma API JSON (~1 KB em vez de
  ~30 KB por página);
- a operação é guardada no telemóvel e enviada quando há rede (agora, ao voltar
  a rede, ao trazer a app para a frente, ao abrir, ou no botão *Sincronizar*);
- **reenvios seguros**: identificador único por operação + tabela
  `operacao_cliente`, para nunca duplicar um item nem somar a quantidade duas
  vezes; `comprado` e `quantidade` são enviados como estado desejado (não como
  inversão/incremento);
- **barra de estado** única em todas as páginas (`3 por sincronizar`,
  `Sem rede · 3 guardada(s)`, `Tudo sincronizado`, `Sessão expirada · …`);
- **Service Worker** (só em HTTPS) para abrir a Lista/Despensa sem rede, com
  manifest e ícones para instalar no ecrã principal do iPhone;
- sem JavaScript nada muda: os formulários POST continuam a funcionar.

Detalhes, limites do iOS e como ativar o HTTPS com Tailscale:
[`docs/FILA-OFFLINE.md`](docs/FILA-OFFLINE.md).

Como o acesso no iPhone é feito por `http://<IP do Tailscale>:5000` (sem HTTPS,
onde não existe Service Worker), as páginas da Lista e da Despensa passaram
também a ser devolvidas com `Cache-Control: private, max-age=3600,
stale-while-revalidate, stale-if-error` + `Vary: Cookie`. É isso que permite
**abrir a lista sem rede** mesmo sem Service Worker, com a reconciliação no
arranque a corrigir os dados assim que houver ligação (ver
[`docs/ux/lista-sem-rede-http.png`](docs/ux/lista-sem-rede-http.png)).

Verificação: 33 testes da API (idempotência, dono, regras da despensa),
36 testes da fila (sem rede, erros, junção de operações, persistência) e
33 testes de página em DOM real (item aparece na hora, sincronização ao voltar
a rede e reconciliação).

---

## 10. Como revalidar

1. Abrir a aplicação e alternar o tema em **Configurações → Aparência**
   (Claro/Escuro/Sistema) e pelo menu hambúrguer.
2. Verificar contraste de forma automática (script de apoio usado na auditoria,
   não incluído no projeto): percorre as variáveis CSS de `bootstrap.min.css` +
   `app.css`, resolve `var()`/`rgba()` e calcula os rácios WCAG de cada par
   texto/fundo. Resultado final: **0 pares abaixo de AA** nos dois temas.
3. No browser, com o modo escuro do sistema ativo, abrir cada página e confirmar
   que não há flash branco nem texto de baixo contraste.
4. Reduzir a janela até 320 px e percorrer as páginas: não deve existir scroll
   horizontal nem botões pequenos nos controlos de quantidade.

---

## 11. Limitações e sugestões

- **Ferramenta de captura:** o `firefox --headless --screenshot` não pinta
  alterações de estilo feitas por JavaScript após a carga. O estado *ativo* do
  seletor de tema foi validado por CSS estático equivalente (`.btn.active`
  preenche corretamente) e pela presença confirmada da classe/`aria-pressed` no
  DOM; num browser normal a troca é imediata.
- **Não faz parte do âmbito:** CSRF e a verificação de dono em
  `POST /atualizar_qtd` e `GET /compras/<id>` (ver `RELATORIO-SEGURANCA.md`).
- **Sugestões para uma próxima iteração:**
  - mensagem de confirmação ("Produto adicionado", "Item removido") após cada
    ação, hoje silenciosa — a barra da fila já dá o estado geral;
  - pesquisa/filtro por produto em despensas grandes;
  - datas de validade e painel de vencimentos (previsto em `requisitos.md`).

As imagens em `docs/ux/` são evidência desta auditoria e podem ser removidas sem
qualquer impacto na aplicação.
