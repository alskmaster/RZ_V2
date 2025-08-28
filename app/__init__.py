# app/__init__.py
import os
import uuid
import time
from datetime import timedelta

from flask import Flask, g, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from .utils import get_text_color_for_bg

# --- Extensões ---
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"


# --- Loader do usuário (Flask-Login) ---
@login_manager.user_loader
def load_user(user_id):
    from .models import User
    # get() é mais eficiente nas versões recentes / evita depreciação
    return db.session.get(User, int(user_id))


def _ensure_request_id():
    """Gera um request-id por requisição (debug e correlação de logs)."""
    rid = getattr(g, "request_id", None)
    if not rid:
        rid = uuid.uuid4().hex
        g.request_id = rid
    return rid


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Hardening e defaults sensatos (não invadem config existente) ---
    # Aviso útil se SECRET_KEY não estiver definido (impacta CSRF/sessões)
    if not app.config.get("SECRET_KEY"):
        app.logger.warning("[boot] SECRET_KEY ausente! CSRF/sessões podem falhar.")

    # Cookies e sessão
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    # Em produção atrás de HTTPS, considere forçar Secure:
    if app.config.get("PREFERRED_URL_SCHEME", "").lower() == "https":
        app.config.setdefault("SESSION_COOKIE_SECURE", True)
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))

    # Uploads e limites
    app.config.setdefault("MAX_CONTENT_LENGTH", 32 * 1024 * 1024)  # 32 MB por request
    app.config.setdefault("UPLOAD_FOLDER", os.path.join(os.getcwd(), "uploads"))
    app.config.setdefault("GENERATED_REPORTS_FOLDER", os.path.join(os.getcwd(), "generated_reports"))

    # CSRF (mantendo sua escolha atual; apenas reforçando opções)
    app.config.setdefault("WTF_CSRF_TIME_LIMIT", None)  # tokens sem expiração rígida
    # app.config.setdefault("WTF_CSRF_CHECK_DEFAULT", True)  # padrão já é True

    # Dev experience
    if app.config.get("DEBUG"):
        app.config.setdefault("TEMPLATES_AUTO_RELOAD", True)

    # --- Middlewares úteis ---
    # Corrige headers de proxy (X-Forwarded-For/Proto/Host), importante atrás de Nginx/ELB
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # --- Inicializa extensões ---
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # --- Blueprints ---
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    # --- Filtros Jinja ---
    app.jinja_env.filters['text_color_for_bg'] = get_text_color_for_bg

    # --- Hooks de observabilidade (debug por função/rota) ---
    @app.before_request
    def _obs_before():
        # request-id, início, tamanhos de payload
        _ensure_request_id()
        g._t0 = time.perf_counter()
        # Nunca logar senha/cookies/headers sensíveis; aqui só metadados
        try:
            clen = request.content_length or 0
        except Exception:
            clen = 0
        current_app.logger.debug(
            "REQ | %s | %s %s | q=%s | clen=%s | rid=%s",
            request.remote_addr,
            request.method,
            request.path,
            bool(request.query_string),
            clen,
            g.request_id
        )

    @app.after_request
    def _obs_after(response):
        # latência e status
        try:
            dt_ms = int((time.perf_counter() - getattr(g, "_t0", time.perf_counter())) * 1000)
        except Exception:
            dt_ms = -1
        current_app.logger.debug(
            "RES | %s %s | status=%s | bytes=%s | t_ms=%s | rid=%s",
            request.method,
            request.path,
            response.status_code,
            response.calculate_content_length(),
            dt_ms,
            getattr(g, "request_id", "-")
        )
        # Segurança básica de headers (pode ajustar conforme front)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response

    # Handlers de erro com logs detalhados
    @app.errorhandler(400)
    def _err_400(e):
        current_app.logger.warning("ERR400 | path=%s | rid=%s | %s", request.path, getattr(g, "request_id", "-"), e)
        return ("Bad Request", 400)

    @app.errorhandler(403)
    def _err_403(e):
        current_app.logger.warning("ERR403 | path=%s | rid=%s | %s", request.path, getattr(g, "request_id", "-"), e)
        return ("Forbidden", 403)

    @app.errorhandler(404)
    def _err_404(e):
        current_app.logger.info("ERR404 | path=%s | rid=%s", request.path, getattr(g, "request_id", "-"))
        return ("Not Found", 404)

    @app.errorhandler(500)
    def _err_500(e):
        current_app.logger.error("ERR500 | path=%s | rid=%s", request.path, getattr(g, "request_id", "-"), exc_info=True)
        return ("Internal Server Error", 500)

    # --- Boot de pastas, modelos e seeds ---
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['GENERATED_REPORTS_FOLDER'], exist_ok=True)

        from . import models  # evita import circular
        db.create_all()

        # Seeds idempotentes (sem duplicar)
        if not models.Role.query.first():
            db.session.add_all([
                models.Role(name='super_admin'),
                models.Role(name='admin'),
                models.Role(name='client')
            ])
            db.session.commit()

        if not models.User.query.filter_by(username='superadmin').first():
            super_admin_role = models.Role.query.filter_by(name='super_admin').first()
            admin_user = models.User(username='superadmin', role=super_admin_role)
            admin_user.set_password(app.config.get('SUPERADMIN_PASSWORD', 'change-me-now'))
            db.session.add(admin_user)
            db.session.commit()

    return app
