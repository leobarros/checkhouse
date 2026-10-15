import os
import json
from datetime import datetime, timedelta
from flask import (Flask, render_template, request, redirect, url_for, flash, Response,
                   send_file, send_from_directory, jsonify, make_response)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Local, Produto, ItemCompra, Usuario, OperacaoCliente


app = Flask(__name__)
app.config['SECRET_KEY'] = 'y&qyY7ZRc%RQ&EbtU49LSQKWEQ%&^#@!$%&*()_+'
#criando pasta para o banco de dados
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PASTA_DADOS = os.path.join(BASE_DIR, 'dados')
os.makedirs('dados', exist_ok=True)

# banco
CAMINHO_BANCO = os.path.join(PASTA_DADOS, 'checkouse.db')

# config sqlalchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{CAMINHO_BANCO}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Assets estáticos (CSS/JS/ícones) podem ser guardados em cache pelo navegador
# do telemóvel: sem isto o Safari revalida ~700 KB em cada navegação. As URLs
# levam ?v=<versao>, calculada a partir do conteúdo dos ficheiros do projeto,
# por isso uma alteração invalida o cache automaticamente (sem passos manuais).
def _calcular_versao_assets():
    import hashlib

    ficheiros = [
        'css/app.css',
        'js/app.js',
        'js/fila.js',
        'js/estado-fila.js',
        'js/pagina-lista.js',
        'js/pagina-despensa.js',
    ]
    resumo = hashlib.sha256()
    for relativo in ficheiros:
        caminho = os.path.join(BASE_DIR, 'static', relativo)
        try:
            with open(caminho, 'rb') as fh:
                resumo.update(fh.read())
        except OSError:
            resumo.update(relativo.encode())
    return resumo.hexdigest()[:10]


VERSAO_ASSETS = os.environ.get('CH_VERSAO_ASSETS') or _calcular_versao_assets()
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = int(os.environ.get('CH_CACHE_ASSETS', 60 * 60 * 24 * 30))
# A fila offline nunca deve ficar presa a uma resposta antiga guardada em cache.
app.config['JSON_SORT_KEYS'] = False

# conecta o banco de dados ao nosso app flask
db.init_app(app)

# Configuração do Gerenciador de Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Se não estiver logado, redireciona para cá
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


@login_manager.unauthorized_handler
def usuario_nao_autenticado():
    """A fila offline precisa de saber a diferença entre "sem rede" e "sessão
    expirada". Para as rotas /api/ devolvemos 401 em JSON (o cliente mantém as
    operações guardadas); nas páginas normais mantém-se o redirect para login."""
    if request.path.startswith('/api/'):
        return jsonify({'erro': 'sessao_expirada'}), 401
    flash(login_manager.login_message, login_manager.login_message_category)
    return redirect(url_for('login', next=request.full_path if request.query_string else request.path))


@app.context_processor
def injetar_versao_assets():
    return {'versao_assets': VERSAO_ASSETS}


with app.app_context():
    db.create_all()

# antes da primeira requisição, cria as tabelas no banco de dados se não existirem
with app.app_context():
    db.create_all()
    # Limpeza do registo de idempotência: passados alguns dias já não há filas
    # antigas para reenviar (o telemóvel sincroniza muito antes disto).
    try:
        limite = datetime.now() - timedelta(days=7)
        OperacaoCliente.query.filter(OperacaoCliente.criado_em < limite).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        # Verifica se o usuário existe e se a senha bate com o hash salvo
        if usuario and check_password_hash(usuario.senha_hash, senha):
            login_user(usuario)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')
            
    return render_template('login.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    # Rota temporária/oculta para você criar seu primeiro usuário
    if request.method == 'POST':
        username = request.form.get('username')
        senha = request.form.get('senha')
        
        if Usuario.query.filter_by(username=username).first():
            flash('Usuário já existe.', 'danger')
            return redirect(url_for('registrar'))
            
        # Cria um HASH forte da senha em vez de salvar em texto limpo
        nova_senha_hash = generate_password_hash(senha)
        novo_usuario = Usuario(username=username, senha_hash=nova_senha_hash)
        
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Usuário criado com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('registrar.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Rota para a página inicial (Apenas mostra os locais do utilizador logado)
@app.route('/')
@login_required
def index():
    locais = Local.query.filter_by(usuario_id=current_user.id).all()
    return render_template('index.html', locais=locais)

# Rota para adicionar um novo local vinculado ao utilizador
@app.route('/adicionar_local', methods=['POST'])
@login_required
def adicionar_local():
    nome = request.form.get('nome')
    if nome:
        # Associa o novo local ao ID do utilizador atual
        novo_local = Local(nome=nome, usuario_id=current_user.id)
        db.session.add(novo_local)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/despensa/<int:local_id>')
@login_required
def ver_despensa(local_id):
    # Verifica se o local existe E se pertence ao utilizador atual
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()
    
    produtos = Produto.query.filter_by(local_id=local_id).order_by(Produto.nome).all()
    itens = ItemCompra.query.filter_by(local_id=local_id).all()
    sugestoes = sorted(list(set([p.nome for p in produtos] + [i.nome for i in itens])))
    
    return _pagina_cacheavel(render_template('despensa.html', local=local, produtos=produtos, sugestoes=sugestoes))

@app.route('/adicionar_produto/<int:local_id>', methods=['POST'])
@login_required
def adicionar_produto(local_id):

    # BARREIRA DE SEGURANÇA: Garante que o utilizador é dono da casa onde está a adicionar o produto
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()

    nome = request.form.get('nome')
    quantidade = request.form.get('quantidade', 1, type=int)
    
    if nome:
        novo_produto = Produto(
            nome=nome,
            quantidade=quantidade,
            local_id=local.id
        )
        db.session.add(novo_produto)
        db.session.commit()
        
    return redirect(url_for('ver_despensa', local_id=local.id))

@app.route('/eliminar_produto/<int:produto_id>', methods=['POST'])
@login_required
def eliminar_produto(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    
    # BARREIRA DE SEGURANÇA: O local deste produto pertence a este utilizador?
    if produto.local.usuario_id != current_user.id:
        return "Acesso Negado", 403 # Retorna erro de permissão
        
    db.session.delete(produto)
    db.session.commit()
    return redirect(url_for('ver_despensa', local_id=produto.local_id))

# Rota para incrementar ou decrementar a quantidade na despensa
@app.route('/atualizar_qtd/<int:produto_id>/<acao>', methods=['POST'])
@login_required
def atualizar_qtd(produto_id, acao):
    produto = Produto.query.get_or_404(produto_id)
    
    if acao == 'mais':
        produto.quantidade += 1
    elif acao == 'menos' and produto.quantidade > 0:
        produto.quantidade -= 1
        
        # --- LÓGICA AUTOMÁTICA DA LISTA DE COMPRAS ---
        if produto.quantidade == 0:
            # Verifica se o item já está na lista de compras (e ainda não foi comprado)
            # Usamos ilike para ignorar diferenças entre maiúsculas e minúsculas
            item_existente = ItemCompra.query.filter(
                ItemCompra.nome.ilike(produto.nome),
                ItemCompra.local_id == produto.local_id,
                ItemCompra.comprado == False
            ).first()
            
            # Se não estiver na lista, adiciona automaticamente
            if not item_existente:
                novo_item_lista = ItemCompra(
                    nome=produto.nome,
                    quantidade=1, # Sugere 1 para a próxima compra
                    local_id=produto.local_id
                )
                db.session.add(novo_item_lista)
        # ----------------------------------------------
        
    db.session.commit()
    return redirect(url_for('ver_despensa', local_id=produto.local_id))

@app.route('/eliminar_local/<int:local_id>', methods=['POST'])
@login_required
def eliminar_local(local_id):
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()
    Produto.query.filter_by(local_id=local_id).delete()

    db.session.delete(local)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/compras/<int:local_id>')
@login_required
def lista_compras(local_id):
    local = Local.query.get_or_404(local_id)
    produtos_em_falta = Produto.query.filter_by(local_id=local_id, quantidade=0).all()

    return render_template('compras.html', local=local, produtos=produtos_em_falta)

# Rota para ver a Lista de Compras de um local
@app.route('/lista/<int:local_id>')
@login_required
def ver_lista(local_id):
    # Verifica se o local existe E se pertence ao utilizador atual
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()
    
    itens = ItemCompra.query.filter_by(local_id=local_id).order_by(ItemCompra.comprado, ItemCompra.nome).all()
    produtos = Produto.query.filter_by(local_id=local_id).all()
    sugestoes = sorted(list(set([p.nome for p in produtos] + [i.nome for i in itens])))
    
    return _pagina_cacheavel(render_template('lista.html', local=local, itens=itens, sugestoes=sugestoes))

# Rota para adicionar item na lista
@app.route('/adicionar_lista/<int:local_id>', methods=['POST'])
@login_required
def adicionar_lista(local_id):
    # BARREIRA DE SEGURANÇA: Garante que o utilizador é dono da casa onde está a adicionar o item
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()
    nome = request.form.get('nome')
    quantidade = request.form.get('quantidade', 1, type=int)
    
    if nome:
        novo_item = ItemCompra(nome=nome, quantidade=quantidade, local_id=local.id)
        db.session.add(novo_item)
        db.session.commit()
    return redirect(url_for('ver_lista', local_id=local.id))

# Rota para alterar a quantidade na lista (+ e -)
@app.route('/atualizar_lista_qtd/<int:item_id>/<acao>', methods=['POST'])
@login_required
def atualizar_lista_qtd(item_id, acao):
    item = ItemCompra.query.get_or_404(item_id)

    # BARREIRA DE SEGURANÇA: O local deste produto pertence a este utilizador?
    if item.local.usuario_id != current_user.id:
        return "Acesso Negado", 403 # Retorna erro de permissão
    
    if not item.comprado:
        if acao == 'mais':
            item.quantidade += 1
        elif acao == 'menos' and item.quantidade > 1:
            item.quantidade -= 1
        db.session.commit()
    return redirect(url_for('ver_lista', local_id=item.local_id))

# Rota para Marcar/Desmarcar item (MÁGICA REVERSÍVEL)
@app.route('/toggle_compra/<int:item_id>', methods=['POST'])
@login_required
def toggle_compra(item_id):
    item = ItemCompra.query.get_or_404(item_id)
    produto_existente = Produto.query.filter(Produto.nome.ilike(item.nome), Produto.local_id == item.local_id).first()

    # BARREIRA DE SEGURANÇA: O local deste produto pertence a este utilizador?
    if item.local.usuario_id != current_user.id:
        return "Acesso Negado", 403 # Retorna erro de permissão
    
    if not item.comprado:
        item.comprado = True
        if produto_existente:
            # BUG CORRIGIDO: Agora ele soma corretamente a quantidade comprada com o que já existe (mesmo se for 0)
            produto_existente.quantidade = produto_existente.quantidade + item.quantidade
        else:
            novo_produto = Produto(nome=item.nome, quantidade=item.quantidade, local_id=item.local_id)
            db.session.add(novo_produto)
    else:
        item.comprado = False
        if produto_existente:
            # Subtrai a quantidade, garantindo que não fique negativa
            produto_existente.quantidade = max(0, produto_existente.quantidade - item.quantidade)
                
    db.session.commit()
    return redirect(url_for('ver_lista', local_id=item.local_id))

# Rota para excluir um item específico da lista
@app.route('/excluir_item_lista/<int:item_id>', methods=['POST'])
@login_required
def excluir_item_lista(item_id):
    item = ItemCompra.query.get_or_404(item_id)

    # BARREIRA DE SEGURANÇA: O local deste produto pertence a este utilizador?
    if item.local.usuario_id != current_user.id:
        return "Acesso Negado", 403 # Retorna erro de permissão

    local_id = item.local_id
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('ver_lista', local_id=local_id))

# Rota para limpar todos os itens comprados (Limpar Lixo)
@app.route('/limpar_lista/<int:local_id>', methods=['POST'])
@login_required
def limpar_lista(local_id):

    # BARREIRA DE SEGURANÇA: Garante que o utilizador é dono da casa onde está a limpar a lista
    local = Local.query.filter_by(id=local_id, usuario_id=current_user.id).first_or_404()

    # Apaga apenas os itens que já foram comprados
    ItemCompra.query.filter_by(local_id=local.id, comprado=True).delete()
    db.session.commit()
    return redirect(url_for('ver_lista', local_id=local.id))

# Rota para editar o nome do produto na despensa
@app.route('/editar_produto/<int:produto_id>', methods=['POST'])
@login_required
def editar_produto(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    novo_nome = request.form.get('nome')

    # BARREIRA DE SEGURANÇA: O local deste produto pertence a este utilizador?
    if produto.local.usuario_id != current_user.id:
        return "Acesso Negado", 403 # Retorna erro de permissão
    
    if novo_nome:
        produto.nome = novo_nome
        db.session.commit()
        
    return redirect(url_for('ver_despensa', local_id=produto.local_id))

# Administracao do usuário
@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html')

@app.route('/alterar_senha', methods=['POST'])
@login_required
def alterar_senha():
    senha_atual = request.form.get('senha_atual')
    nova_senha = request.form.get('nova_senha')
    
    if check_password_hash(current_user.senha_hash, senha_atual):
        current_user.senha_hash = generate_password_hash(nova_senha)
        db.session.commit()
        flash('Palavra-passe atualizada com sucesso!', 'success')
    else:
        flash('A palavra-passe atual está incorreta.', 'danger')
    return redirect(url_for('configuracoes'))

@app.route('/exportar_dados')
@login_required
def exportar_dados():
    locais = Local.query.filter_by(usuario_id=current_user.id).all()
    dados = []
    for local in locais:
        dados_local = {
            'nome': local.nome,
            'produtos': [{'nome': p.nome, 'quantidade': p.quantidade} for p in local.produtos],
            'lista': [{'nome': i.nome, 'quantidade': i.quantidade, 'comprado': i.comprado} for i in local.itens_compra]
        }
        dados.append(dados_local)
        
    json_str = json.dumps(dados, indent=4)
    return Response(json_str, mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=checkhouse_backup.json'})

@app.route('/importar_dados', methods=['POST'])
@login_required
def importar_dados():
    arquivo = request.files.get('arquivo')
    if arquivo and arquivo.filename.endswith('.json'):
        dados = json.load(arquivo)
        for l_data in dados:
            novo_local = Local(nome=l_data['nome'], usuario_id=current_user.id)
            db.session.add(novo_local)
            db.session.flush() # Obtém o ID do novo local imediatamente
            
            for p_data in l_data.get('produtos', []):
                db.session.add(Produto(nome=p_data['nome'], quantidade=p_data['quantidade'], local_id=novo_local.id))
            for i_data in l_data.get('lista', []):
                db.session.add(ItemCompra(nome=i_data['nome'], quantidade=i_data['quantidade'], comprado=i_data['comprado'], local_id=novo_local.id))
        
        db.session.commit()
        flash('Backup restaurado com sucesso!', 'success')
    return redirect(url_for('configuracoes'))

@app.route('/excluir_conta', methods=['POST'])
@login_required
def excluir_conta():
    # Como a relação "Local" tem cascade="all, delete-orphan", tudo é apagado automaticamente
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    return redirect(url_for('login'))

# ===========================================================================
# API JSON para a fila offline (telemóvel)
#
# Porquê: cada ação no supermercado fazia POST + redirect + download da página
# inteira (2 idas ao servidor, ~30 KB). Estas rotas respondem em JSON (~1 KB) e
# aceitam reenvios: o cabeçalho X-Idempotency-Key (ou o campo "uid" no corpo)
# identifica a operação e a tabela operacao_cliente garante que uma repetição
# devolve a mesma resposta, sem duplicar item nem somar quantidades duas vezes.
# ===========================================================================

LIMITE_TEXTO = 100

# As páginas da Lista e da Despensa podem ser guardadas no cache do navegador:
# é o que permite ao Safari abrir a lista sem rede em http://IP (onde não há
# Service Worker, porque não é contexto seguro). A página pode chegar 5 minutos
# "velha", mas o JavaScript volta a ler a lista no servidor quando há rede
# (ver reconciliar() em static/js/pagina-*.js), por isso corrige-se sozinha.
SEGUNDOS_CACHE_PAGINA = int(os.environ.get('CH_CACHE_PAGINA', 3600))


def _pagina_cacheavel(resposta):
    resposta = make_response(resposta)
    resposta.headers['Cache-Control'] = (
        'private, max-age={0}, stale-while-revalidate=604800, stale-if-error=604800'
    ).format(SEGUNDOS_CACHE_PAGINA)
    return resposta


def _json_item(item):
    return {
        'id': item.id,
        'nome': item.nome,
        'quantidade': item.quantidade,
        'comprado': bool(item.comprado),
        'data_criacao': item.data_criacao.strftime('%d/%m/%Y às %H:%M') if item.data_criacao else '',
        'local_id': item.local_id,
    }


def _json_produto(produto):
    return {
        'id': produto.id,
        'nome': produto.nome,
        'quantidade': produto.quantidade,
        'local_id': produto.local_id,
    }


def _dados():
    dados = request.get_json(silent=True)
    return dados if isinstance(dados, dict) else {}


def _uid():
    """Identificador único da operação, gerado pelo cliente."""
    bruto = request.headers.get('X-Idempotency-Key') or _dados().get('uid') or ''
    return str(bruto).strip()[:64]


def _repeticao(uid):
    """Se este uid já foi processado, devolve a resposta guardada."""
    if not uid:
        return None
    registo = OperacaoCliente.query.filter_by(uid=uid).first()
    if not registo:
        return None
    corpo = json.loads(registo.resposta) if registo.resposta else {}
    corpo['repetido'] = True
    return jsonify(corpo), registo.status or 200


def _registar_operacao(uid, tipo, recurso_id, corpo, status=200):
    if not uid:
        return
    db.session.add(OperacaoCliente(
        uid=uid,
        tipo=tipo,
        recurso_id=recurso_id,
        resposta=json.dumps(corpo),
        status=status,
    ))


def _local_do_usuario(local_id):
    """Devolve o local apenas se pertencer ao utilizador autenticado."""
    return Local.query.filter_by(id=local_id, usuario_id=current_user.id).first()


def _texto(valor, limite=LIMITE_TEXTO):
    return str(valor or '').strip()[:limite]


def _quantidade(valor, minimo=1):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return max(minimo, numero)


def _somar_a_despensa(item):
    """Espelha o comportamento de /toggle_compra ao marcar como comprado."""
    produto = Produto.query.filter(
        Produto.nome.ilike(item.nome), Produto.local_id == item.local_id
    ).first()
    if produto:
        produto.quantidade = produto.quantidade + item.quantidade
    else:
        produto = Produto(nome=item.nome, quantidade=item.quantidade, local_id=item.local_id)
        db.session.add(produto)
    return produto


def _retirar_da_despensa(item):
    """Espelha o comportamento de /toggle_compra ao desmarcar (comprado=False)."""
    produto = Produto.query.filter(
        Produto.nome.ilike(item.nome), Produto.local_id == item.local_id
    ).first()
    if produto:
        produto.quantidade = max(0, produto.quantidade - item.quantidade)
    return produto


@app.route('/api/ping')
@login_required
def api_ping():
    """Verificação leve de conectividade usada pelo indicador de estado."""
    return jsonify({'ok': True, 'hora': datetime.now().isoformat(timespec='seconds')})


@app.route('/api/locais/<int:local_id>/lista')
@login_required
def api_ver_lista(local_id):
    local = _local_do_usuario(local_id)
    if not local:
        return jsonify({'erro': 'local_nao_encontrado'}), 404
    itens = ItemCompra.query.filter_by(local_id=local.id).order_by(
        ItemCompra.comprado, ItemCompra.nome
    ).all()
    resposta = jsonify({'local': {'id': local.id, 'nome': local.nome},
                        'itens': [_json_item(i) for i in itens]})
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta


@app.route('/api/locais/<int:local_id>/lista/itens', methods=['POST'])
@login_required
def api_criar_item(local_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    local = _local_do_usuario(local_id)
    if not local:
        return jsonify({'erro': 'local_nao_encontrado'}), 404

    dados = _dados()
    nome = _texto(dados.get('nome'))
    quantidade = _quantidade(dados.get('quantidade', 1))
    if not nome or not quantidade:
        return jsonify({'erro': 'dados_invalidos'}), 400

    item = ItemCompra(nome=nome, quantidade=quantidade, local_id=local.id)
    db.session.add(item)
    db.session.flush()

    corpo = {'item': _json_item(item)}
    _registar_operacao(uid, 'item_criado', item.id, corpo, 201)
    db.session.commit()
    return jsonify(corpo), 201


@app.route('/api/itens/<int:item_id>', methods=['PATCH'])
@login_required
def api_atualizar_item(item_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    item = ItemCompra.query.get(item_id)
    if not item or item.local.usuario_id != current_user.id:
        return jsonify({'erro': 'item_nao_encontrado'}), 404

    dados = _dados()
    alterou = False

    # "comprado" é enviado como estado desejado (true/false), não como inversão:
    # repetir o pedido não volta a marcar/desmarcar.
    if 'comprado' in dados:
        desejado = bool(dados.get('comprado'))
        if desejado != bool(item.comprado):
            if desejado:
                item.comprado = True
                _somar_a_despensa(item)
            else:
                item.comprado = False
                _retirar_da_despensa(item)
            alterou = True

    if 'quantidade' in dados and not item.comprado:
        quantidade = _quantidade(dados.get('quantidade', 1))
        if not quantidade:
            return jsonify({'erro': 'dados_invalidos'}), 400
        if quantidade != item.quantidade:
            item.quantidade = quantidade
            alterou = True

    if 'nome' in dados:
        nome = _texto(dados.get('nome'))
        if not nome:
            return jsonify({'erro': 'dados_invalidos'}), 400
        if nome != item.nome:
            item.nome = nome
            alterou = True

    if alterou:
        db.session.flush()

    corpo = {'item': _json_item(item)}
    _registar_operacao(uid, 'item_atualizado', item.id, corpo, 200)
    db.session.commit()
    return jsonify(corpo)


@app.route('/api/itens/<int:item_id>', methods=['DELETE'])
@login_required
def api_remover_item(item_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    item = ItemCompra.query.get(item_id)
    if not item:
        # Já não existe (ex.: reenvio depois de removido): sucesso na mesma.
        corpo = {'ok': True, 'ja_removido': True}
        _registar_operacao(uid, 'item_removido', item_id, corpo, 200)
        db.session.commit()
        return jsonify(corpo)

    if item.local.usuario_id != current_user.id:
        return jsonify({'erro': 'item_nao_encontrado'}), 404

    db.session.delete(item)
    corpo = {'ok': True, 'id': item_id}
    _registar_operacao(uid, 'item_removido', item_id, corpo, 200)
    db.session.commit()
    return jsonify(corpo)


@app.route('/api/locais/<int:local_id>/lista/limpar', methods=['POST'])
@login_required
def api_limpar_lista(local_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    local = _local_do_usuario(local_id)
    if not local:
        return jsonify({'erro': 'local_nao_encontrado'}), 404

    removidos = ItemCompra.query.filter_by(local_id=local.id, comprado=True).delete()
    corpo = {'ok': True, 'removidos': removidos}
    _registar_operacao(uid, 'lista_limpa', local.id, corpo, 200)
    db.session.commit()
    return jsonify(corpo)


@app.route('/api/locais/<int:local_id>/despensa')
@login_required
def api_ver_despensa(local_id):
    local = _local_do_usuario(local_id)
    if not local:
        return jsonify({'erro': 'local_nao_encontrado'}), 404
    produtos = Produto.query.filter_by(local_id=local.id).order_by(Produto.nome).all()
    resposta = jsonify({'local': {'id': local.id, 'nome': local.nome},
                        'produtos': [_json_produto(p) for p in produtos]})
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta


@app.route('/api/locais/<int:local_id>/despensa/produtos', methods=['POST'])
@login_required
def api_criar_produto(local_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    local = _local_do_usuario(local_id)
    if not local:
        return jsonify({'erro': 'local_nao_encontrado'}), 404

    dados = _dados()
    nome = _texto(dados.get('nome'))
    quantidade = _quantidade(dados.get('quantidade', 1))
    if not nome or not quantidade:
        return jsonify({'erro': 'dados_invalidos'}), 400

    produto = Produto(nome=nome, quantidade=quantidade, local_id=local.id)
    db.session.add(produto)
    db.session.flush()

    corpo = {'produto': _json_produto(produto)}
    _registar_operacao(uid, 'produto_criado', produto.id, corpo, 201)
    db.session.commit()
    return jsonify(corpo), 201


@app.route('/api/produtos/<int:produto_id>', methods=['PATCH'])
@login_required
def api_atualizar_produto(produto_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    produto = Produto.query.get(produto_id)
    if not produto or produto.local.usuario_id != current_user.id:
        return jsonify({'erro': 'produto_nao_encontrado'}), 404

    dados = _dados()
    alterou = False

    if 'nome' in dados:
        nome = _texto(dados.get('nome'))
        if not nome:
            return jsonify({'erro': 'dados_invalidos'}), 400
        if nome != produto.nome:
            produto.nome = nome
            alterou = True

    if 'quantidade' in dados:
        quantidade = _quantidade(dados.get('quantidade', 0), minimo=0)
        if quantidade is None:
            return jsonify({'erro': 'dados_invalidos'}), 400
        if quantidade != produto.quantidade:
            anterior = produto.quantidade
            produto.quantidade = quantidade
            alterou = True
            # Mesma regra de /atualizar_qtd: ao chegar a zero, o produto entra
            # na lista de compras (se ainda não estiver lá).
            if quantidade == 0 and anterior != 0:
                existente = ItemCompra.query.filter(
                    ItemCompra.nome.ilike(produto.nome),
                    ItemCompra.local_id == produto.local_id,
                    ItemCompra.comprado == False,  # noqa: E712 (comparação SQL)
                ).first()
                if not existente:
                    db.session.add(ItemCompra(
                        nome=produto.nome, quantidade=1, local_id=produto.local_id
                    ))

    if alterou:
        db.session.flush()

    corpo = {'produto': _json_produto(produto)}
    _registar_operacao(uid, 'produto_atualizado', produto.id, corpo, 200)
    db.session.commit()
    return jsonify(corpo)


@app.route('/api/produtos/<int:produto_id>', methods=['DELETE'])
@login_required
def api_remover_produto(produto_id):
    uid = _uid()
    repetido = _repeticao(uid)
    if repetido:
        return repetido

    produto = Produto.query.get(produto_id)
    if not produto:
        corpo = {'ok': True, 'ja_removido': True}
        _registar_operacao(uid, 'produto_removido', produto_id, corpo, 200)
        db.session.commit()
        return jsonify(corpo)

    if produto.local.usuario_id != current_user.id:
        return jsonify({'erro': 'produto_nao_encontrado'}), 404

    db.session.delete(produto)
    corpo = {'ok': True, 'id': produto_id}
    _registar_operacao(uid, 'produto_removido', produto_id, corpo, 200)
    db.session.commit()
    return jsonify(corpo)


# --- Ficheiros que precisam de viver na raiz do site -------------------------
# O Service Worker só controla o âmbito de onde é servido; estando em /static/
# ficaria limitado a /static/. O manifest e o ícone do iOS também são servidos
# na raiz por conveniência.

@app.route('/sw.js')
def service_worker():
    resposta = send_from_directory(app.static_folder, 'sw.js', mimetype='text/javascript')
    resposta.headers['Cache-Control'] = 'no-cache'
    resposta.headers['Service-Worker-Allowed'] = '/'
    return resposta


@app.route('/manifest.webmanifest')
def manifest():
    return send_from_directory(app.static_folder, 'manifest.webmanifest',
                               mimetype='application/manifest+json')


@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory(os.path.join(app.static_folder, 'icons'), 'apple-touch-icon.png',
                               mimetype='image/png')


# Sevidor local para desenvolvimento. Em produção, use um servidor WSGI como Gunicorn ou uWSGI.
if __name__ == '__main__':
    # o host='0.0.0.0' permite que você acesse de outros dispositivos na sua rede local
    app.run(debug=True, host='0.0.0.0', port=5000)
