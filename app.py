import os
from flask import Flask, render_template, request, redirect, url_for
from models import db, Local, Produto
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
    quantidade = request.form.get('quantidade')
    data_validade_str = request.form.get('data_validade')

    data_validade = None
    if data_validade_str:
        data_validade = datetime.strptime(data_validade_str, '%Y-%m-%d').date()

    novo_produto = Produto(
        nome=nome,
        quantidade=quantidade,
        data_validade=data_validade,
        local_id=local_id #liga o produto a casa correta
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

@app.route('/atualizar_qtd/<int:produto_id>/<acao>', methods=['POST'])
def atualizar_qtd(produto_id, acao):
    produto = Produto.query.get_or_404(produto_id)

    if acao == 'mais':
        produto.quantidade += 1
    elif acao == 'menos' and produto.quantidade > 0:
        produto.quantidade -= 1

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

if __name__ == '__main__':
    # o host='0.0.0.0' permite que você acesse de outros dispositivos na sua rede local
    app.run(debug=True, host='0.0.0.0', port=5000)
