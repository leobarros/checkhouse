import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, Local, Produto, ItemCompra
from datetime import datetime

app = Flask(__name__)

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

# antes da primeira requisição, cria as tabelas no banco de dados se não existirem
with app.app_context():
    db.create_all()

# nossa primeira rota (url principal)

@app.route('/')
def index():
    todos_locais = Local.query.all()
    return render_template('index.html', locais=todos_locais)

@app.route('/adicionar_local', methods=['POST'])
def adicionar_local():
    nome_do_local = request.form.get('nome')

    if nome_do_local:
        novo_local = Local(nome=nome_do_local)
        db.session.add(novo_local)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/despensa/<int:local_id>')
def ver_despensa(local_id):
    local = Local.query.get_or_404(local_id)
    produtos = Produto.query.filter_by(local_id=local_id).all()

    return render_template('despensa.html', local=local, produtos=produtos)

@app.route('/adicionar_produto/<int:local_id>', methods=['POST'])
def adicionar_produto(local_id):
    nome = request.form.get('nome')
    quantidade = request.form.get('quantidade', 1, type=int)
    
    if nome:
        novo_produto = Produto(
            nome=nome,
            quantidade=quantidade,
            local_id=local_id
        )
        db.session.add(novo_produto)
        db.session.commit()
        
    return redirect(url_for('ver_despensa', local_id=local_id))

@app.route('/eliminar_produto/<int:produto_id>', methods=['POST'])
def eliminar_produto(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    local_id = produto.local_id

    db.session.delete(produto)
    db.session.commit()

    return redirect(url_for('ver_despensa', local_id=local_id))

# Rota para incrementar ou decrementar a quantidade na despensa
@app.route('/atualizar_qtd/<int:produto_id>/<acao>', methods=['POST'])
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
def eliminar_local(local_id):
    local = Local.query.get_or_404(local_id)
    Produto.query.filter_by(local_id=local_id).delete()

    db.session.delete(local)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/compras/<int:local_id>')
def lista_compras(local_id):
    local = Local.query.get_or_404(local_id)
    produtos_em_falta = Produto.query.filter_by(local_id=local_id, quantidade=0).all()

    return render_template('compras.html', local=local, produtos=produtos_em_falta)

# Rota para ver a Lista de Compras de um local
@app.route('/lista/<int:local_id>')
def ver_lista(local_id):
    local = Local.query.get_or_404(local_id)
    itens = ItemCompra.query.filter_by(local_id=local_id).order_by(ItemCompra.comprado).all()
    return render_template('lista.html', local=local, itens=itens)

# Rota para adicionar item na lista
@app.route('/adicionar_lista/<int:local_id>', methods=['POST'])
def adicionar_lista(local_id):
    nome = request.form.get('nome')
    quantidade = request.form.get('quantidade', 1, type=int)
    
    if nome:
        novo_item = ItemCompra(nome=nome, quantidade=quantidade, local_id=local_id)
        db.session.add(novo_item)
        db.session.commit()
    return redirect(url_for('ver_lista', local_id=local_id))

# Rota para alterar a quantidade na lista (+ e -)
@app.route('/atualizar_lista_qtd/<int:item_id>/<acao>', methods=['POST'])
def atualizar_lista_qtd(item_id, acao):
    item = ItemCompra.query.get_or_404(item_id)
    if not item.comprado:
        if acao == 'mais':
            item.quantidade += 1
        elif acao == 'menos' and item.quantidade > 1:
            item.quantidade -= 1
        db.session.commit()
    return redirect(url_for('ver_lista', local_id=item.local_id))

# Rota para Marcar/Desmarcar item (MÁGICA REVERSÍVEL)
@app.route('/toggle_compra/<int:item_id>', methods=['POST'])
def toggle_compra(item_id):
    item = ItemCompra.query.get_or_404(item_id)
    produto_existente = Produto.query.filter(Produto.nome.ilike(item.nome), Produto.local_id == item.local_id).first()
    
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
def excluir_item_lista(item_id):
    item = ItemCompra.query.get_or_404(item_id)
    local_id = item.local_id
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('ver_lista', local_id=local_id))

# Rota para limpar todos os itens comprados (Limpar Lixo)
@app.route('/limpar_lista/<int:local_id>', methods=['POST'])
def limpar_lista(local_id):
    # Apaga apenas os itens que já foram comprados
    ItemCompra.query.filter_by(local_id=local_id, comprado=True).delete()
    db.session.commit()
    return redirect(url_for('ver_lista', local_id=local_id))

if __name__ == '__main__':
    # o host='0.0.0.0' permite que você acesse de outros dispositivos na sua rede local
    app.run(debug=True, host='0.0.0.0', port=5000)
