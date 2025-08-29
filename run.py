import os
import logging
from app import create_app
from rz_debug import with_debug  # Decorador de debug centralizado

# ----------------------------------------------------------------------------
# Configuração de logging estruturado
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("RZ_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s"
)
logger = logging.getLogger("rz.run")

# ----------------------------------------------------------------------------
# Criação da aplicação Flask
# ----------------------------------------------------------------------------
app = create_app()

# ----------------------------------------------------------------------------
# Exemplo de aplicação do debug decorator na inicialização
# ----------------------------------------------------------------------------
@with_debug("app_startup")
def startup_log():
    logger.info("Aplicação inicializada com sucesso.")

startup_log()

# ----------------------------------------------------------------------------
# Bloco de execução (apenas para desenvolvimento!)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")

    if debug:
        logger.warning("⚠️ Rodando em modo DEBUG. Não use em produção!")

    app.run(host=host, port=port, debug=debug)
    # 🚨 Em produção use: gunicorn -w 4 -b 0.0.0.0:5000 'run:app'
