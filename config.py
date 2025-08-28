# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do .env cedo para não depender de ordem de import
load_dotenv()

# --- Helpers de parsing/compat ---
def _bool(env_value: str | None, default: bool = False) -> bool:
    if env_value is None:
        return default
    return env_value.strip().lower() in {"1", "true", "on", "yes", "y"}

def _int(env_value: str | None, default: int) -> int:
    try:
        return int(env_value) if env_value is not None else default
    except ValueError:
        return default

def _normalize_db_url(url: str | None) -> str:
    """
    Conserta 'postgres://' -> 'postgresql+psycopg2://' para SQLAlchemy.
    Mantém sqlite e outros esquemas como estão.
    """
    if not url:
        return "sqlite:///zabbix_reporter_v20.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url

# Diretório base do projeto (absoluto) — evita caminhos relativos inconsistentes
BASE_DIR = Path(os.getenv("BASE_DIR") or Path.cwd()).resolve()

class Config:
    """Configuração base (produção por padrão)."""

    # --- Segurança básica / sessão ---
    SECRET_KEY = os.environ.get("SECRET_KEY") or "mude-esta-chave-secreta-em-producao-agora"
    # Cookies de sessão — valores finais podem ser reforçados em app/__init__.py
    SESSION_COOKIE_HTTPONLY = _bool(os.getenv("SESSION_COOKIE_HTTPONLY"), True)
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), False)  # ative em HTTPS

    # --- Flask-WTF / CSRF ---
    WTF_CSRF_ENABLED = _bool(os.getenv("WTF_CSRF_ENABLED"), True)
    WTF_CSRF_TIME_LIMIT = None  # não expira rigidamente; tokens trocados a cada request
    # Caso use header personalizado, mantenha integração no front (X-CSRFToken)

    # --- Banco de Dados ---
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Engine tuning para alto volume (ajuste conforme seu banco)
    SQLALCHEMY_ENGINE_OPTIONS = {
        # pool_pre_ping evita quedas por conexões mortas
        "pool_pre_ping": True,
        # tamanhos/reciclagem padrão; ajuste por ambiente
        "pool_size": _int(os.getenv("DB_POOL_SIZE"), 10),
        "max_overflow": _int(os.getenv("DB_MAX_OVERFLOW"), 20),
        "pool_recycle": _int(os.getenv("DB_POOL_RECYCLE"), 1800),  # 30 min
    }

    # --- Pastas (absolutas) ---
    UPLOAD_FOLDER = str((BASE_DIR / (os.getenv("UPLOAD_FOLDER") or "uploads")).resolve())
    GENERATED_REPORTS_FOLDER = str((BASE_DIR / (os.getenv("GENERATED_REPORTS_FOLDER") or "relatorios_gerados")).resolve())

    # --- Uploads / tamanhos ---
    ALLOWED_EXTENSIONS = set(
        (os.getenv("ALLOWED_EXTENSIONS") or "png,jpg,jpeg,gif,html,pdf")
        .replace(" ", "")
        .split(",")
    )
    MAX_CONTENT_LENGTH = _int(os.getenv("MAX_CONTENT_LENGTH"), 32 * 1024 * 1024)  # 32 MB

    # --- Zabbix (padrões lidos do .env; token só para debug/hotfix) ---
    ZABBIX_URL = os.getenv("ZABBIX_URL")
    ZABBIX_USER = os.getenv("ZABBIX_USER")
    ZABBIX_PASSWORD = os.getenv("ZABBIX_PASSWORD")
    ZABBIX_TOKEN = os.getenv("ZABBIX_TOKEN")  # opcional (debug)

    # --- Superadmin ---
    SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD") or "admin123"

    # --- wkhtmltoimage (relatórios/prints) ---
    WKHTMLTOIMAGE_PATH = os.getenv("WKHTMLTOIMAGE_PATH")  # deixar vazio -> PATH do SO

    # --- Logging / observabilidade ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # INFO/DEBUG/WARNING/ERROR
    LOG_JSON = _bool(os.getenv("LOG_JSON"), True)  # preferir JSON em produção

    # --- Proxy / URL building ---
    # Se estiver atrás de proxy/ingress com HTTPS, isso ajuda a gerar URLs corretas
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https" if SESSION_COOKIE_SECURE else "http")
    SERVER_NAME = os.getenv("SERVER_NAME")  # ex.: "app.exemplo.com" (defina se necessário)

    # --- Flags de ambiente ---
    DEBUG = _bool(os.getenv("DEBUG"), False)
    TESTING = _bool(os.getenv("TESTING"), False)


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    # Em dev normalmente não usamos cookie secure
    SESSION_COOKIE_SECURE = False
    PREFERRED_URL_SCHEME = "http"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Em testes, limite de upload reduzido acelera execuções e falhas
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    LOG_JSON = False  # logs legíveis durante testes locais


# Export de mapeamento opcional para factory escolher por env
CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": Config,
}
