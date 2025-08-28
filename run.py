# run.py
from app import create_app

# Cria a instância da nossa aplicação Flask a partir da nossa futura fábrica
app = create_app()

# Bloco que executa o servidor de desenvolvimento
if __name__ == '__main__':
    # O debug=True é ótimo para desenvolvimento, mas deve ser False em produção
    app.run(host='0.0.0.0', port=5000, debug=True)