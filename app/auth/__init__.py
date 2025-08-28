# app/auth/__init__.py
from flask import Blueprint

# Cria uma instância de Blueprint chamada 'auth'
auth = Blueprint('auth', __name__)

# Importa as rotas para que o Blueprint as conheça
from . import routes