import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Local, Produto, ItemCompra, Usuario

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

with app.app_context():
    db.create_all()

# antes da primeira requisição, cria as tabelas no banco de dados se não existirem
with app.app_context():
    db.create_all()


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
    
    return render_template('despensa.html', local=local, produtos=produtos, sugestoes=sugestoes)

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
    
    return render_template('lista.html', local=local, itens=itens, sugestoes=sugestoes)

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

if __name__ == '__main__':
    # o host='0.0.0.0' permite que você acesse de outros dispositivos na sua rede local
    app.run(debug=True, host='0.0.0.0', port=5000)
