# Fila offline e sincronização (uso no telemóvel)

Este documento explica como o CheckHouse se comporta quando a rede é má — o
caso típico é a lista de compras usada dentro do supermercado — e como ativar o
modo "abrir sem rede" no iPhone através do Tailscale.

---

## 1. O problema que isto resolve

Antes, cada toque (adicionar item, marcar como comprado, mexer na quantidade)
fazia:

1. `POST` ao servidor e espera da resposta;
2. `302` de volta para a página;
3. download da página inteira (~30 KB) + revalidação do CSS/JS.

Com 5G fraco no supermercado isso são **duas idas ao servidor por toque**, e a
interface só mudava no fim. Resultado: parecia que a app tinha "travado".

## 2. Como funciona agora

```
toque do utilizador
   │
   ├─ 1. a interface atualiza NA HORA (linha nova, risco no item, quantidade)
   │
   └─ 2. a operação entra na fila (localStorage do telemóvel)
            │
            └─ 3. envio automático quando há rede:
                  agora, ao voltar a rede, ao trazer a app para a frente,
                  ao abrir a app ou no botão "Sincronizar"
```

- **Uma operação = um pedido pequeno.** As ações passam por uma API JSON
  (`POST /api/locais/<id>/lista/itens`, `PATCH /api/itens/<id>`, …) que responde
  com ~1 KB em vez de recarregar a página.
- **Nada se perde.** A fila fica gravada no aparelho (`ch:fila:v1`) e sobrevive a
  recarregar a página, fechar o Safari ou o telemóvel reiniciar.
- **Sem duplicados.** Cada operação leva um identificador único
  (`X-Idempotency-Key`). O servidor guarda a resposta desse identificador na
  tabela `operacao_cliente`, por isso reenviar a mesma operação devolve o mesmo
  resultado em vez de criar outro item ou somar a quantidade duas vezes.
- **Sem inversões erradas.** "Marcar como comprado" envia o **estado desejado**
  (`comprado: true`), não uma inversão: repetir o pedido não volta a desmarcar.
  O mesmo para a quantidade (valor absoluto, não "+1").
- **Fila curta.** Toques repetidos no `+`/`−` do mesmo item são juntados numa só
  operação (fica o último valor). Criar e remover antes de sincronizar cancela
  as duas coisas.
- **A interface confere com o servidor.** Assim que a fila esvazia, a página
  volta a ler a lista (`GET /api/...`) e acerta o que estiver diferente.
- **Sessão expirada não perde nada.** Se o login tiver expirado, o servidor
  responde `401` em JSON (em vez de redirecionar) e a fila fica parada com o
  aviso "Sessão expirada · N guardada(s)" e um atalho para entrar novamente.
- **Erros de dados são visíveis.** Um pedido inválido (400) é descartado, a
  alteração otimista é revertida e aparece um aviso ("Não foi possível
  adicionar «…»").

### O que o iOS permite (e o que não permite)

| Recurso | iPhone | Consequência prática |
| --- | --- | --- |
| Fila local + reenvio com a app aberta | ✅ | O toque é instantâneo mesmo sem rede |
| [Background Sync API](https://caniuse.com/background-sync) | ❌ não existe no Safari | A fila sobe quando a app está aberta (ao voltar a rede, ao mudar de app, ao abrir) — não com a app fechada |
| `Service Worker` (cache completo da app) | ⚠️ exige HTTPS | Em `http://IP:5000` não existe, mas a página da Lista/Despensa fica no **cache HTTP** do navegador (secção 4) — na prática também abre sem rede |
| Guardar dados no aparelho | ⚠️ o iOS pode limpar armazenamento de sites pouco usados | Adicionar ao ecrã principal ajuda; a fila deve sincronizar assim que houver rede |

## 3. O que o utilizador vê

- Uma barra no fundo do ecrã, igual em qualquer página:
  - `3 por sincronizar` + botão **Sincronizar**;
  - `Sem rede · 3 guardada(s)` quando o telemóvel está sem ligação;
  - `Tudo sincronizado` (verde, desaparece sozinha);
  - `Sessão expirada · 2 guardada(s)` + **Entrar novamente**.
- Linhas criadas no telemóvel e ainda não confirmadas têm uma **barra amarela à
  esquerda** até receberem o `id` do servidor.
- Sem JavaScript tudo continua a funcionar como antes (os formulários POST
  originais continuam na página).

## 4. Abrir a app sem rede

### 4.1 Acesso por `http://IP` (sem HTTPS) — funciona com o cache do navegador

Um Service Worker exige contexto seguro (HTTPS ou localhost), por isso em
`http://100.x.y.z:5000` ele **não** é registado. Mesmo assim a Lista e a
Despensa abrem sem rede, porque essas duas páginas são devolvidas com:

```
Cache-Control: private, max-age=3600, stale-while-revalidate=604800, stale-if-error=604800
Vary: Cookie
```

- o Safari guarda a página e volta a usá-la quando não consegue contactar o
  servidor (dentro da hora, ou mais além disso graças ao `stale-if-error`);
- como a página pode vir "velha", o JavaScript volta a ler a lista no servidor
  assim que há rede (`reconciliar()` em `static/js/pagina-*.js`) e acerta as
  linhas — inclusive acrescenta itens que tenham sido criados noutro aparelho;
- `Vary: Cookie` garante que a página guardada pertence àquela sessão (depois de
  sair da conta, a página não é reaproveitada);
- as restantes páginas (Início, Configurações, login) continuam sem cache.

Verificado em teste: com o servidor desligado, a lista abre na mesma a partir do
cache e as ações continuam a funcionar, entrando na fila.

### 4.2 Acesso por HTTPS (`*.ts.net`) — cache completo com Service Worker

Se preferir o comportamento "app instalada", use o nome do Tailscale em vez do
IP. O certificado do domínio `*.ts.net` é válido, por isso o iPhone aceita-o.

1. No painel do Tailscale, ative **MagicDNS** e **HTTPS Certificates**
   ([instruções](https://tailscale.com/docs/how-to/set-up-https-certificates)).
2. No servidor onde o CheckHouse corre (porta 5000), execute:

   ```bash
   tailscale serve --bg --https=443 http://127.0.0.1:5000
   tailscale serve status
   ```

   (A sintaxe varia ligeiramente entre versões do Tailscale; `tailscale serve --help`
   mostra as opções disponíveis. Em alternativa, `tailscale cert` gera os
   ficheiros de certificado para usar num proxy à sua escolha.)

3. No iPhone, com o Tailscale ligado, abra
   `https://<nome-da-maquina>.<tailnet>.ts.net` (note que o certificado é emitido
   para o **nome**, não para o IP — por isso este caminho exige o nome). No Safari: **Partilhar → Adicionar
   ao ecrã principal**.
4. Confirme no Safari (Web Inspector) que o Service Worker ficou ativo. A partir
   daí, a Lista e a Despensa abrem com a última versão guardada mesmo sem rede,
   e as alterações continuam a entrar na fila.

Para desativar: `tailscale serve --https=443 off`.

## 5. Como testar

Durante o desenvolvimento correram 102 verificações automáticas (API, fila e
páginas em DOM real) mais 14 verificações do cenário "página em cache sem rede",
num ambiente de teste local que **não faz parte do repositório**. O que cada uma
cobre, para poder ser repetido:

| Suite | O que cobre |
| --- | --- |
| API (33) | API JSON: idempotência (reenvio não duplica), estado absoluto de `comprado`/quantidade, criar/remover, despensa a zero entra na lista, isolamento entre utilizadores, `401` em JSON, validação |
| Fila (36) | Fila no aparelho: ordem, junção de operações, sem rede, falha 5xx com nova tentativa, `401` (fila preservada), `400` (descarta e avisa), resolução de `id` temporário, cancelar criação+remoção, persistência entre sessões |
| Páginas (33) | Páginas em DOM real (jsdom): item aparece na hora, marcar comprado, quantidades, barra de estado, sincronização ao voltar a rede e reconciliação com o servidor, e o funcionamento sem JavaScript |
| Cache sem rede (14) | Página guardada em cache abre sem servidor, aceita alterações, fila sobe quando a rede volta (sem duplicar) e a página velha corrige-se sozinha |

Teste manual rápido no telemóvel:

1. Abrir a Lista, ativar o **modo avião**.
2. Adicionar 2 itens, marcar 1 como comprado, mudar uma quantidade.
3. Confirmar que tudo acontece na hora e que a barra mostra `3 por sincronizar`.
4. Desligar o modo avião: a barra passa a `Tudo sincronizado` e os itens
   aparecem no desktop.

## 6. Limites conhecidos

- **App fechada:** o iOS não tem sincronização em segundo plano, por isso uma
  operação pendente só sobe quando a app voltar a ser aberta.
- **Duas janelas no mesmo telemóvel** (ex.: Safari + app no ecrã principal) têm
  filas separadas até a página ser recarregada.
- **Armazenamento limpo pelo iOS:** se o site não for usado durante muitos dias
  (ou o aparelho fizer pressão de armazenamento), a fila pode ser apagada.
  Adicionar ao ecrã principal reduz muito esta probabilidade.
- **Segurança:** continua sem proteção CSRF e existem verificações de dono em
  falta nas rotas antigas (`/atualizar_qtd`, `/compras`) — ver
  `RELATORIO-SEGURANCA.md`. A API nova valida o dono em todas as rotas.

## 7. Manutenção

- **Cache dos assets:** `SEND_FILE_MAX_AGE_DEFAULT` guarda CSS/JS por 30 dias no
  telemóvel, mas a versão (`?v=`) é calculada a partir do **conteúdo** dos
  ficheiros, por isso basta alterar/rodar de novo para invalidar. Também se pode
  forçar com a variável de ambiente `CH_VERSAO_ASSETS` ou desativar com
  `CH_CACHE_ASSETS=0`.
- **Service Worker:** o `static/sw.js` é servido em `/sw.js` (raiz, para ter
  âmbito em todo o site) com `Cache-Control: no-cache`, e usa a versão recebida
  no registo para nomear as caches — um deploy novo descarta as antigas.
- **Cache das páginas Lista/Despensa:** a janela é definida por
  `CH_CACHE_PAGINA` (segundos, por omissão 3600). Aumentar dá mais tempo de uso
  sem rede; diminuir mostra dados mais frescos. A reconciliação no arranque
  corrige a página de qualquer forma.
- **Registo de idempotência:** linhas com mais de 7 dias são apagadas no arranque
  da aplicação. Se precisar de mais tempo (telemóvel muito tempo offline), ajuste
  o `timedelta(days=7)` em `app.py`.
