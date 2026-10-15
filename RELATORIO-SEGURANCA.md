# Relatório de Segurança — CheckHouse

**Data:** 2026-10-08
**Alvo:** `app.py` (394 linhas), `models.py`, `dockerfile`, `docker-compose.yml`, templates Jinja2
**Método:** revisão estática de código + testes de exploração dinâmica com o test client do Flask, executados numa **cópia isolada** do projeto (a base de dados real não foi alterada)
**Versões em análise:** Flask 3.0.0, Flask-Login 0.6.3, Flask-SQLAlchemy 3.1.1, Werkzeug 3.1.8, SQLAlchemy 2.1.1, Jinja2 3.1.6

> **Aviso:** a aplicação **não está segura para exposição em rede neste momento**. Foram encontradas 3 falhas críticas que, em conjunto, permitem a um atacante **assumir o controlo de qualquer conta e executar código no servidor**, sem conhecer nenhuma palavra-passe.

---

## 1. Resumo executivo

| # | Gravidade | Falha | Impacto |
|---|-----------|-------|---------|
| 1 | 🔴 **Crítica** | `SECRET_KEY` fixa no código, num repositório GitHub **público** e numa imagem Docker **pública** | Falsificação de cookies de sessão → **tomada de conta de qualquer utilizador** |
| 2 | 🔴 **Crítica** | `debug=True` com `host='0.0.0.0'` — é o comando de arranque do contentor | Consola interativa do Werkzeug exposta → **execução remota de código (RCE)** |
| 3 | 🔴 **Crítica** | Consola de depuração alcançável **sem autenticação** via `POST /registrar` sem username | Caminho não autenticado para o RCE do ponto 2 |
| 4 | 🟠 **Alta** | IDOR em `POST /atualizar_qtd/<id>` — sem verificação de dono | Qualquer utilizador altera o stock de outros |
| 5 | 🟠 **Alta** | IDOR em `GET /compras/<id>` — sem verificação de dono | Fuga de dados privados de outros utilizadores |
| 6 | 🟠 **Alta** | Palavras-passe vazias aceites; campos em falta causam HTTP 500 | Contas sem credencial / erros não tratados |
| 7 | 🟡 **Média** | `/registrar` totalmente aberto, sem convite nem limite | Criação ilimitada de contas por qualquer anónimo |
| 8 | 🟡 **Média** | Sem limite de tentativas de login | Ataque de força bruta às palavras-passe |
| 9 | 🟡 **Média** | `/importar_dados`: JSON não validado, sem limite de tamanho | HTTP 500 e consumo ilimitado de disco/memória |
| 10 | 🟡 **Média** | Sessões não são revogadas ao mudar a palavra-passe | Um cookie roubado continua válido após a mudança |
| 11 | 🟡 **Média** | Ausência total de cabeçalhos de segurança | Clickjacking, MIME sniffing, sem CSP |
| 12 | 🟡 **Média** | Cookie de sessão sem `Secure` nem `SameSite` | Exposição do cookie em HTTP; CSRF |
| 13 | 🔵 **Baixa** | Sem proteção CSRF, dependências não fixadas, contentor corre como `root`, `/logout` por GET | Higiene e robustez |

**Pontos positivos a manter:** palavras-passe com hash `scrypt` (padrão do Werkzeug), mensagem de erro de login genérica (não permite enumerar utilizadores), 12 de 14 rotas com controlo de propriedade correto, base de dados fora do Git (`.gitignore`), autoescape do Jinja2 ativo (não há XSS por injeção de template).

---

## 2. Falhas críticas (corrigir antes de qualquer exposição)

### 🔴 Crítica 1 — `SECRET_KEY` fixa e publicamente conhecida → tomada de conta

`app.py:10`

```python
app.config['SECRET_KEY'] = 'y&qyY7ZRc%RQ&EbtU49LSQKWEQ%&^#@!$%&*()_+'
```

Esta chave assina os cookies de sessão. Como está no código-fonte e este está exposto em **dois canais públicos**:

- Repositório Git público: `github.com/leobarros/checkhouse` (`"private": false`, confirmado via API do GitHub)
- Imagem Docker pública: `hub.docker.com/r/nickolback/checkhouse` (`"is_private": false`, 332 pulls). Qualquer pessoa pode fazer `docker pull` e ler `app.py` **dentro da imagem**.

O Flask-Login guarda apenas `_user_id` no cookie. Com a chave conhecida, o atacante **fabrica um cookie válido para qualquer utilizador**, sem palavra-passe.

**Exploração confirmada** (atacante nunca soube a palavra-passe — sessão forjada apenas com a chave pública):

```
=== 1) Atacante anónimo, SEM cookie ===
   GET /  -> HTTP 302                      (bloqueado)
=== 2) Atacante com cookie FORJADO ===
   GET /  -> HTTP 200
   dados privados da vitima visiveis na pagina: 2
=== 3) Acesso a despensa privada da vitima com o cookie forjado ===
   GET /despensa/1 -> HTTP 200
   produto privado 'Caviar Secreto' exposto: 4
```

Isto é uma **falha total de autenticação**: o atacante lê, altera e apaga os dados de qualquer casa. Dado que `excluir_conta` e `eliminar_local` são destrutivos, o impacto inclui destruição de dados.

**Correção:**
```python
# app.py
import secrets

secret = os.environ.get('SECRET_KEY')
if not secret:
    raise RuntimeError(
        "SECRET_KEY não definida. Gere uma com:\n"
        "  python -c 'import secrets; print(secrets.token_hex(32))'"
    )
app.config['SECRET_KEY'] = secret
```
```yaml
# docker-compose.yml
services:
  checkhouse:
    environment:
      - SECRET_KEY=${SECRET_KEY:?defina SECRET_KEY no ficheiro .env}
```
Coloque `SECRET_KEY=...` num ficheiro `.env` (já coberto pelo `.gitignore`, linha 153) e nunca no código.

⚠️ **A chave atual deve considerar-se comprometida para sempre.** Rodá-la invalida todas as sessões existentes — o que é desejável. Note que **rodar a chave não basta**: qualquer pessoa que já a tenha lido pode voltar a forjá-la se o repositório ou a imagem continuarem a expô-la. É obrigatório também **tornar o repositório privado** e/ou **reescrever o histórico do Git** (`git filter-repo`) e **remover a imagem antiga do Docker Hub**.

---

### 🔴 Crítica 2 — Consola de depuração do Werkzeug exposta na rede (RCE)

`app.py:392-394`

```python
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

E o `dockerfile` arranca exatamente este caminho:

```dockerfile
CMD ["python", "app.py"]
```

Ou seja, **o modo de depuração é o modo de produção**. O `docker-compose.yml` publica a porta em todas as interfaces (`"5000:5000"`), deixando a consola acessível a toda a rede local (e à Internet, se houver port forwarding).

Com `debug=True`, o Werkzeug ativa o *interactive debugger*, que permite **executar código Python arbitrário** no servidor. Confirmado contra um servidor real:

```
POST /registrar (sem username) -> HTTP 500
Marcadores encontrados na pagina de erro:
   5 pin            4 Traceback (most recent call last)    3 __debugger__
   3 PIN            2 console     1 Werkzeug Debugger      1 CONSOLE
```

A página expõe ainda o *traceback* completo com **caminhos absolutos do sistema e código-fonte** (`/home/lsales/.../app.py`, `senha_hash`, `generate_password_hash`).

Além da consola, o modo de depuração expõe o *reloader* e um servidor de desenvolvimento não preparado para produção.

**Correção:**
```python
if __name__ == '__main__':
    # Apenas para desenvolvimento local, nunca exposto à rede
    app.run(debug=True, host='127.0.0.1', port=5000)
```
Em produção, use um servidor WSGI e **nunca** `debug=True`:
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt gunicorn
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
```
Adicione também um *error handler* para que nenhum detalhe interno chegue ao cliente:
```python
@app.errorhandler(Exception)
def erro_interno(e):
    if isinstance(e, HTTPException):
        return e
    app.logger.exception('Erro não tratado')
    db.session.rollback()
    return render_template('erro.html'), 500
```

---

### 🔴 Crítica 3 — Caminho não autenticado para a consola de depuração

`app.py:62-82` — a rota `/registrar` não valida os campos:

```python
username = request.form.get('username')   # pode ser None
senha = request.form.get('senha')         # pode ser None
```

Um `POST /registrar` **sem username** provoca `IntegrityError` (`nullable=False`) e devolve **HTTP 500 a um utilizador anónimo** — que, com `debug=True`, é exatamente o gatilho que abre a consola do Werkzeug. Confirmado:

```
sem username   -> HTTP 500
sem senha      -> HTTP 500
```

Isto transforma a Crítica 2 numa vulnerabilidade **explorável sem qualquer autenticação**, e revela também falta de validação de entrada em geral.

**Correção:** validar sempre e devolver 400 em vez de 500 (ver também Crítica 6).

---

## 3. Falhas de autorização (IDOR) — Alta

Foi construída uma matriz de autorização completa: um utilizador autenticado (`atacante`) a tentar aceder a objetos de outro (`vitima`).

```
METODO ROTA (objeto da VITIMA)            HTTP   VEREDITO
------------------------------------------------------------------------
POST   /atualizar_qtd/<vitima>/mais       302    *** FALHA: PERMITE ***
POST   /atualizar_qtd/<vitima>/menos      302    *** FALHA: PERMITE ***
GET    /compras/<vitima>                  200    *** FALHA: PERMITE ***
POST   /eliminar_produto/<vitima>         403    OK (bloqueado)
POST   /editar_produto/<vitima>           403    OK (bloqueado)
GET    /despensa/<vitima>                 404    OK (bloqueado)
POST   /adicionar_produto/<vitima>        404    OK (bloqueado)
GET    /lista/<vitima>                    404    OK (bloqueado)
POST   /adicionar_lista/<vitima>          404    OK (bloqueado)
POST   /limpar_lista/<vitima>             404    OK (bloqueado)
POST   /eliminar_local/<vitima>           404    OK (bloqueado)
POST   /atualizar_lista_qtd/<vitima>/mais 403    OK (bloqueado)
POST   /toggle_compra/<vitima>            403    OK (bloqueado)
POST   /excluir_item_lista/<vitima>       403    OK (bloqueado)
```

**12 de 14 rotas estão corretas.** Apenas 2 famílias de rotas (3 endpoints) esqueceram a barreira de segurança que as restantes têm.

### 🟠 Alta 4 — `POST /atualizar_qtd/<produto_id>` (app.py:156-187)

```python
produto = Produto.query.get_or_404(produto_id)   # ❌ falta verificar o dono
```

O comentário do próprio ficheiro, noutras rotas, chama a isto "BARREIRA DE SEGURANÇA" — aqui está ausente. Explorado com sucesso:

```
qtd produto da vitima ANTES : 5
qtd produto da vitima DEPOIS: 6      <- alterado por outro utilizador
HTTP status: 302 (302 = alteracao aceite)
```

**Impacto:** manipulação silenciosa do inventário alheio. Ao levar um produto a zero, o atacante **injeta automaticamente um item na lista de compras da vítima** (lógica nas linhas 166-184), o que permite *spam* nos dados de terceiros.

**Correção** (igual ao padrão já usado em `eliminar_produto`):
```python
@app.route('/atualizar_qtd/<int:produto_id>/<acao>', methods=['POST'])
@login_required
def atualizar_qtd(produto_id, acao):
    produto = Produto.query.get_or_404(produto_id)
    if produto.local.usuario_id != current_user.id:
        abort(403)
    ...
```

### 🟠 Alta 5 — `GET /compras/<local_id>` (app.py:199-205)

```python
local = Local.query.get_or_404(local_id)   # ❌ falta filter_by(usuario_id=...)
```

A rota irmã `ver_lista` (linha 212) faz a verificação corretamente; esta não. Confirmado:

```
GET /compras/1 como atacante -> HTTP 200
vazou nome do local da vitima : True
vazou produto da vitima       : True
```

**Impacto:** fuga de dados privados — nome das casas e lista de produtos em falta de qualquer utilizador.

**Correção:**
```python
local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()
```

> **Recomendação estrutural:** existem 7 repetições de `if X.local.usuario_id != current_user.id: return "Acesso Negado", 403`. Extraia um helper para eliminar o risco de esquecer a verificação em código futuro:
> ```python
> def obter_produto_do_usuario(produto_id):
>     return (Produto.query.join(Local)
>             .filter(Produto.id == produto_id, Local.usuario_id == current_user.id)
>             .first_or_404())
> ```
> Note ainda a inconsistência: umas rotas devolvem `403` e outras `404`. Padronize em `404` — não confirma a existência do recurso a quem não é dono.

---

## 4. Falhas altas de autenticação

### 🟠 Alta 6 — Palavras-passe vazias aceites; falta de validação

`app.py:62-82` e `332-344` não impõem qualquer política de palavra-passe. Confirmado:

```
  senha vazia    -> HTTP 302
  senha "1"      -> HTTP 302
  conta criada com senha vazia: True
  login com senha vazia valida: True      <- conta sem credencial efetiva
```

**Impacto:** contas criadas com palavra-passe vazia (ou de 1 caractere) — qualquer pessoa entra com `Enter`. A rota `alterar_senha` permite ainda definir uma palavra-passe vazia numa conta existente.

**Correção:**
```python
def validar_credenciais(username, senha):
    if not username or not senha:
        return 'Preencha o utilizador e a palavra-passe.'
    if len(username) > 50 or len(senha) > 128:
        return 'Dados demasiado longos.'
    if len(senha) < 10:
        return 'A palavra-passe deve ter pelo menos 10 caracteres.'
    return None
```
Aplique em `/registrar` **e** em `/alterar_senha`; devolva `400`/flash em vez de 500.

---

## 5. Falhas médias

### 🟡 Média 7 — Registo de contas totalmente aberto

`/registrar` está ligado a partir do ecrã de login (`templates/login.html:34`), ou seja, é um caminho público intencional. O comentário no código diz "Rota temporária/oculta", mas está exposta e **não existe qualquer conceito de administrador** no código (confirmado por pesquisa: sem `is_admin`, sem *roles*), nem convite, nem verificação por email, nem limite de criação. Qualquer pessoa na rede cria contas sem limite, e não há forma de desativar o registo.

**Correção** — feche o registo por omissão e permita-o apenas enquanto não existir nenhum utilizador:
```python
ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', 'false').lower() == 'true'

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if not ALLOW_REGISTRATION and Usuario.query.count() > 0:
        abort(404)          # esconde a rota
    ...
```
A longo prazo, adicione uma coluna `is_admin` e uma página de gestão de utilizadores (o commit `11147ec` menciona "administracao", mas o conceito não chegou ao código).

### 🟡 Média 8 — Sem limite de tentativas de login

`/login` (app.py:45-60) não tem *rate limiting*. Combinado com o registo aberto e a ausência de política de palavra-passe, a força bruta é trivial.

**Correção:**
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, app=app, default_limits=['200/hour'])

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    ...
```
Adicione `Flask-Limiter` ao `requirements.txt` com versão fixada.

### 🟡 Média 9 — `/importar_dados` sem validação nem limite de tamanho

`app.py:362-380` — `arquivo.filename.endswith('.json')` é a única validação. Confirmado:

```
objeto JSON em vez de lista      -> HTTP 500      (TypeError)
JSON sintaticamente invalido     -> HTTP 500      (JSONDecodeError)
campos obrigatorios ausentes     -> HTTP 500      (KeyError)
quantidade como texto            -> HTTP 302      (aceite sem validação)
quantidade negativa gigante      -> HTTP 302      (aceite sem validação)
tamanho do payload: 640029 bytes (0.6 MB)
aceito -> HTTP 302
registos criados por UM unico upload: 20000
```

**Impacto:** três vetores de negação de serviço (500 por entrada malformada, esgotamento de disco com `20 000` registos num só pedido, memória do processo) e corrupção de dados (`quantidade` negativa ou não-numérica).

**Correção:**
```python
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024      # 2 MB
LIMITE_REGISTOS = 5000

@app.route('/importar_dados', methods=['POST'])
@login_required
def importar_dados():
    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename.lower().endswith('.json'):
        flash('Envie um ficheiro .json válido.', 'danger')
        return redirect(url_for('configuracoes'))
    try:
        dados = json.load(arquivo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash('Ficheiro JSON inválido.', 'danger')
        return redirect(url_for('configuracoes'))
    if not isinstance(dados, list):
        flash('Formato inesperado.', 'danger')
        return redirect(url_for('configuracoes'))
    if sum(len(l.get('produtos', [])) + len(l.get('lista', []))
           for l in dados if isinstance(l, dict)) > LIMITE_REGISTOS:
        flash('Backup demasiado grande.', 'danger')
        return redirect(url_for('configuracoes'))
    # validar cada campo: nome str com limite, quantidade int >= 0
```
Também `quantidade` deve ser coagida com `int()` e validada (`0 <= q <= 100000`) antes de gravar.

### 🟡 Média 10 — Sessões não são revogadas ao mudar a palavra-passe

`app.py:332-344` — depois de `alterar_senha`, a sessão antiga continua válida. Confirmado:

```
  sessao da vitima antes da mudanca  -> /configuracoes HTTP 200
  vitima muda a propria senha...
  sessao ANTIGA reutilizada          -> /configuracoes HTTP 200
  (200 = sessao NAO foi revogada pela mudanca de senha)
```

**Impacto:** se um cookie for roubado, mudar a palavra-passe **não expulsa o atacante**. O utilizador não tem forma de terminar sessões ativas.

**Correção** — versão de sessão por utilizador:
```python
# models.py — nova coluna
class Usuario(db.Model, UserMixin):
    ...
    sessao_versao = db.Column(db.Integer, nullable=False, default=1)
```
```python
@login_manager.user_loader
def load_user(user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    u = db.session.get(Usuario, uid)
    if u and session.get('sessao_versao') != u.sessao_versao:
        return None
    return u
```
Incremente `sessao_versao` (e grave em `session`) em `alterar_senha` e em `excluir_conta`. Isto resolve a Crítica 1 se a chave for rodada, e dá ao utilizador um botão "terminar todas as sessões".

### 🟡 Média 11 — Ausência total de cabeçalhos de segurança

Confirmado numa resposta real (`GET /login`):

```
content-security-policy:       *** AUSENTE ***
x-frame-options:               *** AUSENTE ***
x-content-type-options:        *** AUSENTE ***
strict-transport-security:     *** AUSENTE ***
referrer-policy:               *** AUSENTE ***
permissions-policy:            *** AUSENTE ***
```

**Impacto:** clickjacking (a app pode ser embutida num `iframe`), *MIME sniffing*, e nenhuma mitigação de XSS.

Nota importante para a CSP: `templates/base.html` carrega Bootstrap de um CDN (`cdn.jsdelivr.net`, linhas 9, 11, 87) e usa **JavaScript inline** (`<script>` na linha 88 e `onclick="alternarTema()"` na linha 44). Uma CSP restritiva exige tratar isto primeiro.

**Correção:**
```python
@app.after_request
def cabecalhos_seguranca(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'same-origin'
    resp.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'"
    )
    return resp
```
`'unsafe-inline'` nos estilos é necessário pelo Bootstrap. Para remover a necessidade de scripts inline, mova o bloco `<script>` de `base.html` e o handler `onclick` para um ficheiro em `static/js/` (a pasta `static/` não existe ainda). Considere ainda **hospedar o Bootstrap localmente** (com SRI se mantiver o CDN) — elimina dependência de terceiros e reduz a superfície de ataque da cadeia de fornecimento.

### 🟡 Média 12 — Cookie de sessão sem `Secure` nem `SameSite`

Confirmado no `Set-Cookie` emitido pelo login:

```
session=...; HttpOnly; Path=/          <- sem Secure, sem SameSite
SESSION_COOKIE_SECURE   = False
SESSION_COOKIE_SAMESITE = None
```

`HttpOnly` está ativo (bom, é o padrão do Flask). Mas o cookie trafega em HTTP simples (porta 5000) e não tem `SameSite` explícito.

**Correção** (requer HTTPS — coloque um *reverse proxy* com TLS, ex. Caddy ou Nginx + Let's Encrypt, à frente da app):
```python
app.config.update(
    SESSION_COOKIE_SECURE=True,       # apenas sobre HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
```
Se o acesso é só por IP na LAN e sem TLS, note que **o cookie de sessão viaja em texto limpo** e qualquer dispositivo na mesma rede o pode capturar (Wi-Fi partilhado, ARP spoofing). Para um *home lab*, vale a pena configurar HTTPS mesmo que com certificado auto-assinado.

---

## 6. Falhas baixas / higiene

| # | Falha | Local | Nota |
|---|-------|-------|------|
| 13 | Sem proteção CSRF | todos os POST | Mitigado pelo padrão `SameSite=Lax` dos navegadores modernos (o cookie não acompanha POST cross-site), mas é frágil e não deve ser a única defesa. Adote `Flask-WTF` (`CSRFProtect(app)`) e `{{ csrf_token() }}` nos 17 formulários. |
| 14 | `/logout` por GET | `app.py:84-88` | Deve ser POST, para não ser acionável por `<img src>` ou pré-carregamento. |
| 15 | Dependências não fixadas | `requirements.txt` | Apenas `Flask`, `Flask-SQLAlchemy`, `Flask-Login`, sem versões → builds não reprodutíveis. Fixe versões e adicione um `requirements.lock`. |
| 16 | CVE-2026-27205 (Flask < 3.1.3) | instalado 3.0.0 | `Vary: Cookie` em falta em alguns acessos à sessão → risco de cache com dados sensíveis. **Só relevante com cache/proxy à frente**; este app não tem. Baixo. |
| 17 | CVE-2026-102598 (Werkzeug < 3.1.9) | instalado 3.1.8 | `safe_join` e nomes de dispositivo Windows. **Não aplicável** (Linux e o app não usa `safe_join` com nomes de ficheiro do utilizador). Informativo. |
| 18 | Contentor corre como `root` | `dockerfile` | Sem `USER`. Adicione `RUN useradd -m app && USER app`. |
| 19 | Sem healthcheck nem limites de recursos | `docker-compose.yml` | Adicione `healthcheck` e `deploy.resources.limits` (útil em Raspberry Pi). |
| 20 | `db.create_all()` duplicado | `app.py:37-42` | Bloco repetido duas vezes; remova um. |
| 21 | `os.makedirs('dados')` com caminho relativo | `app.py:14` | Cria `dados/` no *cwd*, mas a BD usa caminho absoluto (`PASTA_DADOS`). Se arrancado de outro diretório, a pasta não é criada onde é precisa → erro na abertura da BD. Use `os.makedirs(PASTA_DADOS, exist_ok=True)`. |
| 22 | `Usuario.query.get(int(user_id))` | `app.py:35` | API legada em SQLAlchemy 2.x; `int()` sobre um cookie adulterado devolve 500. Use `db.session.get(Usuario, uid)` com `try/except` (incluído na correção da Média 10). |
| 23 | Sem registo de auditoria | global | Sem *logging* de logins falhados, alterações de senha ou exportações. Dificulta detetar abuso. |

---

## 7. Plano de correção sugerido

**Fase 1 — parar a hemorragia (hoje, antes de expor em rede)**
1. Desativar `debug=True`; passar a `127.0.0.1` + gunicorn no contentor. *(Críticas 2 e 3)*
2. Mover a `SECRET_KEY` para variável de ambiente e **rodá-la**. *(Crítica 1)*
3. Adicionar as duas verificações de dono em falta (`atualizar_qtd`, `lista_compras`). *(Altas 4 e 5)*
4. Validar `username`/`senha` (sem vazios) e nunca devolver 500. *(Alta 6)*

**Fase 2 — fechar o acesso (esta semana)**
5. Tornar o repositório GitHub **privado** e remover/atualizar a imagem do Docker Hub. *(Crítica 1)*
6. Fechar o registo público por omissão. *(Média 7)*
7. `MAX_CONTENT_LENGTH` + validação do JSON de importação. *(Média 9)*
8. Cabeçalhos de segurança + flags de cookie. *(Médias 11 e 12)*
9. Rate limiting no login. *(Média 8)*

**Fase 3 — robustez (a seguir)**
10. Revogação de sessões + `is_admin` + página de gestão de utilizadores. *(Média 10)*
11. CSRF, `/logout` por POST, versões fixadas, contentor não-root. *(Baixas)*
12. HTTPS por reverse proxy, hospedar Bootstrap localmente, logs de auditoria.

---

## 8. Como revalidar

Depois das correções, confirme:
- `curl -s -X POST -d "senha=x" http://IP:5000/registrar` → **não** deve devolver 500 nem página com "Werkzeug Debugger"
- `curl -sI http://IP:5000/login` → deve conter `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`
- `docker exec checkhouse_app env | grep SECRET_KEY` e `grep -r "SECRET_KEY" app.py` → nada hardcoded
- Repetir a matriz de autorização da secção 3: **todas** as linhas devem dar `403`/`404`
- `POST /registrar` com senha vazia → deve ser rejeitado
- Após mudar a palavra-passe, a sessão antiga deve devolver `302` para `/login`

---

*Este relatório documenta vulnerabilidades exploradas em ambiente de teste isolado. Todos os testes de exploração foram executados sobre uma cópia do projeto; a base de dados real em `dados/checkouse.db` (2 utilizadores, 2 locais, 2 produtos, 1 item) permaneceu inalterada.*
