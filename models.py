from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Local(db.Model):
    __tablename__ = 'local'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    
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