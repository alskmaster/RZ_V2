# config.py
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

class Config:
    # Chave secreta para segurança da sessão
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mude-esta-chave-secreta-em-producao-agora'
    
    # Configuração do Banco de Dados
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///zabbix_reporter_v20.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configurações de Pastas
    UPLOAD_FOLDER = 'uploads'
    GENERATED_REPORTS_FOLDER = 'relatorios_gerados'
    
    # Configurações de Upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'html', 'pdf'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB
    
    # Credenciais da API do Zabbix (do arquivo .env)
    ZABBIX_URL = os.getenv('ZABBIX_URL')
    ZABBIX_USER = os.getenv('ZABBIX_USER')
    ZABBIX_PASSWORD = os.getenv('ZABBIX_PASSWORD')
    ZABBIX_TOKEN = os.getenv('ZABBIX_TOKEN') # Token opcional para debug
    
    # Senha padrão para o superadmin, caso não esteja no .env
    SUPERADMIN_PASSWORD = os.getenv('SUPERADMIN_PASSWORD') or 'admin123'

    # --- LINHA NOVA ---
    # Caminho para o executável wkhtmltoimage, lido do .env
    WKHTMLTOIMAGE_PATH = os.getenv('WKHTMLTOIMAGE_PATH')