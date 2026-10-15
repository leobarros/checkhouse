from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# NOVA TABELA: Usuários
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)

    # Relação: Um utilizador pode ter vários locais
    locais = db.relationship('Local', backref='dono', lazy=True, cascade="all, delete-orphan")

class Local(db.Model):
    __tablename__ = 'local'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)

    # NOVO: Chave estrangeira para associar o local ao utilizador
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    produtos = db.relationship('Produto', backref='local', lazy=True, cascade="all, delete-orphan")
    itens_compra = db.relationship('ItemCompra', backref='local', lazy=True, cascade="all, delete-orphan")

class Produto(db.Model):
    __tablename__ = 'produto'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    local_id = db.Column(db.Integer, db.ForeignKey('local.id'), nullable=False)

class ItemCompra(db.Model):
    __tablename__ = 'item_compra'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    comprado = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=datetime.now) # Nova coluna de data
    local_id = db.Column(db.Integer, db.ForeignKey('local.id'), nullable=False)


class OperacaoCliente(db.Model):
    """Registo de operações enviadas pelo telemóvel (fila offline).

    O cliente gera um identificador único (uid) por operação e repete o envio
    enquanto não tiver rede. Esta tabela guarda a resposta original de cada uid,
    para que um reenvio devolva exatamente o mesmo resultado em vez de executar
    a operação duas vezes (ex.: item duplicado, quantidade somada a dobrar).

    É uma tabela nova, criada automaticamente pelo db.create_all(); não altera
    nenhuma tabela existente.
    """

    __tablename__ = 'operacao_cliente'
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False)
    recurso_id = db.Column(db.Integer)
    resposta = db.Column(db.Text)           # JSON devolvido na primeira execução
    status = db.Column(db.Integer, default=200)
    criado_em = db.Column(db.DateTime, default=datetime.now, index=True)