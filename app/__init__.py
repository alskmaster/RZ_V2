# app/__init__.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from .utils import get_text_color_for_bg
# --- 1. IMPORTAÇÃO ADICIONADA ---
# Importa a classe de proteção CSRF
from flask_wtf.csrf import CSRFProtect

# --- Inicialização das Extensões ---
db = SQLAlchemy()
login_manager = LoginManager()
# --- 2. INSTÂNCIA DA PROTEÇÃO CSRF ---
csrf = CSRFProtect()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- O user_loader é essencial para o Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return db.session.get(User, int(user_id))

# --- A FÁBRICA DA APLICAÇÃO ---
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Vincula as extensões à instância da aplicação
    db.init_app(app)
    login_manager.init_app(app)
    # --- 3. INICIALIZAÇÃO DO CSRF ---
    # Ativa a proteção CSRF na aplicação
    csrf.init_app(app)

    # --- ATIVAÇÃO DOS BLUEPRINTS ---
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    app.jinja_env.filters['text_color_for_bg'] = get_text_color_for_bg

    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['GENERATED_REPORTS_FOLDER'], exist_ok=True)
        
        from . import models
        
        db.create_all()
        
        if not models.Role.query.first():
            db.session.add_all([models.Role(name='super_admin'), models.Role(name='admin'), models.Role(name='client')])
            db.session.commit()
        if not models.User.query.filter_by(username='superadmin').first():
            super_admin_role = models.Role.query.filter_by(name='super_admin').first()
            admin_user = models.User(username='superadmin', role=super_admin_role)
            admin_user.set_password(app.config['SUPERADMIN_PASSWORD'])
            db.session.add(admin_user)
            db.session.commit()
            
    return app