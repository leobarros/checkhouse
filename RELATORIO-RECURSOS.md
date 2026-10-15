# Relatório de recursos — memória e CPU do CheckHouse

> **Resumo:** a aplicação rodava com o servidor de desenvolvimento do Flask e
> `debug=True`, o que mantinha **dois processos Python** e gastava **92 MB** em
> repouso. Passou a rodar em um único processo (`gunicorn`, 1 worker, 4 threads)
> com **~58 MB** em repouso — **−38 % de memória** — e um pico de **~136 MB**
> com os 2 usuários previstos entrando ao mesmo tempo, contra **328 MB** antes
> (**−58 % no pico**). Com 8 clientes simultâneos (4× o previsto) a aplicação
> serve **216 requisições/s com 0 erros** e p95 de 57 ms. Os limites do
> container foram dimensionados a partir dessas medições: **256 MB de RAM** e
> **1,5 núcleos**.

Máquina alvo: home lab com 6 GB de RAM e 2 núcleos, no máximo 2 usuários
logados. Fuso horário: **America/Sao_Paulo**.

---

## 1. Como foi medido

Tudo o que está neste relatório vem de testes executados nesta máquina, com o
container limitado a **2 CPUs** (igual ao home lab) e uma carga gerada por um
cliente próprio.

| Peça | Arquivo | O que faz |
|---|---|---|
| Gerador de carga | [`bench/carga.py`](bench/carga.py) | 2 usuários logados, ciclo realista (lista, despensa, páginas, marcar/criar itens) e rajada de 8 clientes simultâneos |
| Medidor | [`bench/sampler.py`](bench/sampler.py) | lê `memory.current`, `memory.stat` (anon/cache) e `cpu.stat` do cgroup do container, **por fora**, a cada 0,25 s |
| Comparador | [`bench/executar.py`](bench/executar.py) | sobe cada configuração, mede em repouso, prepara dados, mede sob carga e salva tudo em JSON |

Distinção importante usada nos números:

* **anon** — memória realmente ocupada pelo processo. É essa que importa para
  dimensionar um limite de container.
* **cache** — páginas de arquivos lidos pelo container. O kernel devolve essas
  páginas sozinho quando falta RAM, então não são consumo real (mas aparecem no
  `docker stats`, o que explica a diferença entre os dois valores).

Carga: 2 usuários, ~11 requisições/s, cada um percorrendo o ciclo normal da app
(API da lista, API da despensa, página inicial, página da lista, marcar item e
criar item). Rajada: 8 clientes sem pausas — 4× mais do que os 2 usuários
previstos — para ver o comportamento no pico.

---

## 2. Resultados

### 2.1 Todas as configurações testadas

Tabela da primeira rodada (memória = RSS do container, inclui cache; o anon
dessa rodada está na tabela seguinte):

| Configuração | Mem. repouso | Mem. sob carga | CPU 2 usuários | CPU rajada (8) | p95 2 usuários | p95 rajada (8) | req/s | erros |
|---|---|---|---|---|---|---|---|---|
| `flask_debug` — **o que estava publicado** | 92,3 MB | 94,9 MB | 17,5 % | 101,2 % | 56,1 ms | 211,6 ms | 10,2 | 0 |
| `flask_sem_debug` | 44,8 MB | 47,8 MB | 13,6 % | 102,8 % | 41,9 ms | 181,4 ms | 10,2 | 0 |
| `gunicorn_sync_1w` (1 worker síncrono) | 58,4 MB | 59,6 MB | 22,7 % | 83,0 % | **216,4 ms** | 127,1 ms | 8,5 | 0 |
| `gunicorn_gthread_1w_4t` | 58,7 MB | 61,4 MB | 11,7 % | 101,5 % | 38,6 ms | 115,7 ms | 10,9 | 0 |
| `gunicorn_gthread_1w_8t` | 58,8 MB | 61,7 MB | 21,4 % | 115,7 % | 141,6 ms | 116,2 ms | 9,8 | 0 |
| `gunicorn_sync_2w` (2 workers) | 62,6 MB | **89,2 MB** | 16,5 % | **169,7 %** | 81,8 ms | 34,4 ms | 10,8 | 0 |
| `waitress_1w_4t` | 45,4 MB | 48,0 MB | 7,9 % | 110,2 % | 19,5 ms | 83,8 ms | 11,7 | 0 |
| `gthread_arena2` (4 threads + `MALLOC_ARENA_MAX=2`) | 58,7 MB | 60,6 MB | 10,2 % | 109,8 % | 34,6 ms | 69,9 ms | 11,4 | 0 |

Segunda rodada, já com a memória do processo separada do cache (e sem o registro
de acessos no gunicorn, para comparar os servidores em igualdade):

| Configuração | anon repouso | anon sob carga | anon pico | CPU 2 usuários | CPU rajada | p95 2 usuários | p95 rajada | req/s | erros |
|---|---|---|---|---|---|---|---|---|---|
| `flask_debug` | 90,0 MB | 93,2 MB | **328,0 MB** | 10,4 % | 118,9 % | 28,5 ms | 111,9 ms | 11,3 | 0 |
| `waitress_1w_4t` | **43,3 MB** | 46,7 MB | 173,5 MB | 15,3 % | 109,2 % | 142,3 ms¹ | 89,2 ms | 10,7 | 0 |
| `gthread_4t_semlog` ← **escolhida** | 56,4 MB | 58,8 MB | 185,2 MB | 12,3 % | 108,7 % | 19,5 ms | 70,7 ms | 11,2 | 0 |
| `gthread_2t_semlog` | 56,4 MB | 58,3 MB | 122,3 MB | 8,5 % | 101,4 % | 19,9 ms | 62,8 ms | 11,7 | 0 |
| `waitress_2t` | **43,3 MB** | 45,3 MB | 109,3 MB | 9,2 % | 102,4 % | 30,3 ms | 71,4 ms | 11,3 | 0 |
| `waitress_4t_arena2` | 43,3 MB | 45,3 MB | 173,3 MB | 11,5 % | 110,5 % | 20,0 ms | 92,9 ms | 11,2 | 0 |

¹ O valor alto é **inicialização a frio**: a primeira página renderizada obriga o
Jinja a compilar os templates. Repetindo a mesma medição três vezes seguidas na
configuração final, o p95 foi **62,8 ms na primeira volta** e **19,5 ms / 16,1 ms**
nas seguintes (p50 ≈ 5 ms). Todas as configurações foram medidas da mesma forma,
então a comparação entre elas continua válida — mas o número "a quente" é o que
o usuário sente no dia a dia.

### 2.2 Validação com os limites finais (compose real)

Container já com os limites aplicados (`cpus: 1.5`, `mem_limit: 256m`,
`read_only`, `tmpfs`, `TZ`), 2 usuários e depois rajada de 8 clientes:

| Medida | Valor |
|---|---|
| Requisições na rajada | 3 254 requisições, **0 erros** |
| Capacidade na rajada | **216 requisições/s** |
| Latências na rajada | p50 31 ms · p95 57 ms · p99 71 ms |
| CPU na rajada | 101 % de um núcleo (16 períodos com throttling em 404 → 4 %) |
| Memória em repouso (`docker stats`) | 65 MB / 256 MB (25 %) |
| Memória anon em repouso depois de usar | 66 MB |
| Memória no pior instante (8 logins ao mesmo tempo) | 201 MB anon — **sem OOM** |
| Estado | `healthy`, `OOMKilled=false`, 0 reinícios |
| Reciclagem de worker (`--max-requests=2000`) | aconteceu no meio da rajada, sem um único erro |

Depois da correção de fuso horário, a mesma bateria foi repetida: **11,4 req/s
com 2 usuários (p50 7,9 ms, p95 26,2 ms, 0 erros)** e **132 req/s na rajada de 8
(1 594 requisições, 0 erros)**, container `healthy` e 64,8 MB em repouso.

---

## 3. Análise

### 3.1 O maior gasto era o modo de desenvolvimento

`app.py` termina com `app.run(debug=True, host='0.0.0.0')`. O `debug=True` liga o
*reloader* do Werkzeug: fica **um processo vigiando os arquivos e outro
servindo**, e cada um carrega Flask + SQLAlchemy + Jinja. Resultado: **~90 MB**
em repouso, **~328 MB de pico** e o dobro de trabalho do sistema de arquivos.

Só desligar o debug já derruba para ~45 MB. Isso confirma, em memória, o que o
[RELATORIO-SEGURANCA.md](RELATORIO-SEGURANCA.md) diz sobre `debug=True` (console
interativo exposto = execução remota de código).

### 3.2 Um worker com threads, não vários workers

* **1 worker síncrono** faz p95 de **216 ms** com 2 usuários: enquanto uma
  requisição está sendo atendida, a outra espera na fila. É o pior cenário medido.
* **2 workers síncronos** resolvem a concorrência mas **dobram a memória sob
  carga (89 MB)** e **quase dobram a CPU na rajada (170 %)**, porque cada worker
  tem seu próprio interpretador Python. Em um dual-core isso tira o segundo
  núcleo do resto do home lab.
* **1 worker `gthread` com 4 threads** (escolhido): 58 MB, p95 ~20 ms a quente,
  ~10-12 % de um núcleo com 2 usuários. As threads compartilham o mesmo espaço
  de memória — é a forma mais barata de atender 2 usuários.
* **8 threads** pioram tudo (141 ms de p95 e 21 % de CPU): mais threads só
  aumentam a disputa pelo GIL. 4 threads já sobram para 2 usuários e absorvem
  bem as 6 conexões paralelas que um navegador costuma abrir.

### 3.3 O pico de memória vem das senhas, não das requisições

Cada `generate_password_hash` / `check_password_hash` usa **scrypt com 32 MB**
(parâmetros padrão do Werkzeug). Em repouso a app usa 58 MB; durante um login
salta para ~90 MB; **dois logins ao mesmo tempo ficam na casa dos 120-136 MB**.
Medido numa série temporal:

```
t=0,6 s  anon= 45,0 MB   (repouso)
t=1,9 s  anon=109,9 MB   (dois cadastros simultâneos)
t=2,1 s  anon= 46,1 MB   (memória devolvida)
```

É esse o número que manda no limite de memória do container — não o tráfego.

### 3.4 O que foi testado e **não** ajudou

* **`MALLOC_ARENA_MAX=2`**: resultado igual ao byte (58,7 MB → 58,7 MB, CPU
  dentro do ruído). Não foi aplicado.
* **`waitress`** (servidor WSGI puro Python) é a alternativa mais leve:
  **43,3 MB** em vez de 56,4 MB (−13 MB, −23 %) com CPU equivalente e rajada um
  pouco pior (p95 89 ms vs 71 ms). Ficou de fora por ser 13 MB a menos em um
  total de 6 GB, e porque o gunicorn já era a recomendação do relatório de
  segurança e traz `--max-requests` (reciclagem do worker) e `--timeout`.
  Para trocar, basta usar
  `CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=4", "app:app"]`
  e `waitress==3.0.2` no `requirements.txt`.
* **Tuning de SQLite/SQLAlchemy**: não foi preciso. Com 8 clientes simultâneos
  não houve um único erro de banco bloqueado, e as conexões não aparecem na
  memória medida. Menos alterações = menos risco.

---

## 4. O que foi alterado

### 4.1 [`dockerfile`](dockerfile)

* `CMD` passa de `python app.py` para
  `gunicorn --workers=1 --threads=4 --worker-class=gthread --timeout=60 --max-requests=2000 --no-control-socket app:app`.
* **`TZ=America/Sao_Paulo`**: as datas gravadas por `datetime.now()` passam a ser
  a hora local em vez de UTC (ver 4.4).
* `COPY . .` deu lugar a copiar apenas `app.py`, `models.py`, `templates/` e
  `static/` (menos lixo na imagem).
* Bytecode compilado no build (`python -m compileall`) + `PYTHONDONTWRITEBYTECODE=1`:
  a inicialização não gasta CPU compilando e funciona com o sistema de arquivos
  somente leitura.
* `--no-control-socket`: o gunicorn 26 tentava criar `/root/.gunicorn` e
  registrava um erro com o sistema de arquivos somente leitura.

### 4.2 [`requirements.txt`](requirements.txt)

Versões fixadas (deixam de mudar sozinhas de build para build) e entrou o
`gunicorn`:

```
Flask==3.1.3
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
gunicorn==26.2.0
```

### 4.3 [`docker-compose.yml`](docker-compose.yml) — limites aplicados

| Definição | Valor | Por quê |
|---|---|---|
| `mem_limit` | **256m** | O pior caso real medido (2 logins ao mesmo tempo) é ~136 MB; o pior caso artificial (8 logins) chegou a 201 MB. 256 MB dá ~2× de folga e protege o home lab: se algo disparar, morre o container e não a máquina. **128 MB seria arriscado** (um par de logins simultâneos já chega perto). |
| `memswap_limit` | **256m** | Igual ao `mem_limit` = sem swap. Em um home lab com 6 GB, paginar a app só a deixa lenta e empurra o problema para o resto do sistema. |
| `cpus` | **1.5** | A app é limitada pelo GIL: mesmo com 8 clientes simultâneos não passa de ~1,0-1,1 núcleos. 1,5 é trava de segurança, deixando ≥0,5 núcleo livre no dual-core. |
| `TZ` | **America/Sao_Paulo** | Horário correto nas datas da lista/despensa. Sobrescrevível: `TZ=America/Manaus docker compose up -d`. |
| `pids_limit` | 64 | Impede uma explosão de processos (a app usa 2). |
| `read_only` + `tmpfs /tmp` | 32 MB | O container só escreve no volume `./dados` e em `/tmp`. Validado rodando com carga. |
| `security_opt` | `no-new-privileges` | Sem custo de memória. |
| `logging` | 5 MB × 3 | Sem isso o arquivo de logs do Docker cresce sem limite no disco. |
| `healthcheck` | 60 s, via `/login` | Página servida sem tocar no banco de dados. |

Sem limite, a app em repouso ocupava ~90 MB e podia chegar aos 328 MB; com os
limites fica em **~58-66 MB** com um teto de 256 MB.

### 4.4 Fuso horário (corrigido)

O container rodava em **UTC**, então as datas mostradas na lista ("dd/mm/aaaa às
HH:MM") ficavam 3 horas adiantadas em relação ao horário de Brasília.

* `TZ=America/Sao_Paulo` no `dockerfile` (padrão da imagem) e no
  `docker-compose.yml` (sobrescrevível por variável de ambiente).
* O `tzdata` já vem na imagem `python:3.11-slim`, não foi preciso instalar nada.
* Verificado dentro do container e na app:

```
container: 15/10/2026 12:01:14 -03
São Paulo: 15/10/2026 12:01:14 -03
item criado pela API -> data_criacao: 15/10/2026 às 11:58   (UTC era 14:58)
```

Observação: as datas já gravadas antes da correção continuam em UTC (a app
guarda hora local sem fuso). Só as novas ficam certas — como são só os itens da
lista/despensa e o registro de idempotência expira em 7 dias, o desvio some
sozinho.

### 4.5 [`install.sh`](install.sh)

`docker compose pull` passou a `docker compose build --pull` + `up -d`. Com a
mudança de servidor, continuar baixando a imagem publicada (que ainda roda
`python app.py` com `debug=True`) anularia toda a economia em silêncio. O
`image:` continua no compose, então publicar (`docker compose push`) continua
funcionando.

### 4.6 [`.dockerignore`](.dockerignore)

Passou a ignorar `bench/`, `docs/` e `*.md` — os dados dos testes não entram no
contexto de build nem na imagem.

---

## 5. Como repetir os testes

```bash
# construir a imagem de teste (traz gunicorn e waitress)
docker build -f bench/Dockerfile.bench -t checkhouse-bench:latest .

# comparar todas as configurações (≈10 min) — resultado em bench/out/resultados.json
python3 bench/executar.py

# ou só algumas
python3 bench/executar.py flask_debug gunicorn_gthread_1w_4t

# validar os limites reais do compose, sem tocar no banco de dados verdadeiro
docker compose -f docker-compose.yml -f bench/compose-validacao.yml up -d
python3 bench/carga.py setup  --url http://127.0.0.1:5057 --usuarios 2
python3 bench/carga.py real   --url http://127.0.0.1:5057 --usuarios 2 --segundos 25
python3 bench/carga.py stress --url http://127.0.0.1:5057 --concorrencia 8 --segundos 15
docker compose -f docker-compose.yml -f bench/compose-validacao.yml down
```

Os arquivos de medição ficam em `bench/out/` (`resultados_fase1.json`,
`resultados.json`, `bench.log`, `bench_fase2.log`).

---

## 6. Observações e próximos passos (opcionais)

1. **A imagem publicada continua rodando `python app.py` com `debug=True`.**
   Enquanto não for reconstruída e publicada, quem fizer `docker compose pull`
   recebe a versão pesada e insegura. O `install.sh` já constrói localmente.
2. **Repetir o teste depois de mexer no compose.** Os números de CPU e memória
   desta máquina (8 núcleos) com limite de 2 CPUs são representativos, mas o
   home lab tem disco e rede diferentes.
3. **Rodar como usuário sem privilégios** (`user: "1000:1000"` no compose)
   elimina o root dentro do container. Não foi aplicado porque a pasta `./dados`
   pode ter arquivos pertencentes a root de execuções anteriores; se for
   aplicado, é preciso ajustar o dono dessa pasta.
4. **Se um dia houver mais usuários**, o ponto de virada é a memória das senhas:
   cada login simultâneo pede ~32 MB. Com 4-5 logins simultâneos, subir o
   `mem_limit` para 384m antes de mexer no número de workers.
