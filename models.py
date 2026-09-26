from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Local(db.Model):
    __tablename__ = 'local'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)

    # Isso cria uma relação. Permite acessar os produtos de um local facilmente
    produtos = db.relationship('Produto', backref='local', lazy=True)

class Produto(db.Model):
    __tablename__ = 'produto'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False, default=1)
    data_validade = db.Column(db.Date, nullable=True) #pode ser nulo se não houver validade

    # chave estrangeira ligando este produto a um local específico
    local_id = db.Column(db.Integer, db.ForeignKey('local.id'), nullable=False)