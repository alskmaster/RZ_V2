# app/models.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import datetime as dt
from . import db  # Importa a instância 'db' do nosso __init__.py
import enum

# --- Tabela de Associação (Muitos-para-Muitos entre User e Client) ---
user_client_association = db.Table('user_client_association',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('client_id', db.Integer, db.ForeignKey('client.id'), primary_key=True)
)

# --- Modelos Principais ---

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default="Conversys IT Solutions")
    footer_text = db.Column(db.String(255), default=f"Conversys IT Solutions Copyright {dt.datetime.now().year} – Todos os direitos Reservados | Política de privacidade")
    primary_color = db.Column(db.String(7), default="#2c3e50")
    secondary_color = db.Column(db.String(7), default="#3498db")
    logo_dark_bg_path = db.Column(db.String(255), nullable=True)
    logo_light_bg_path = db.Column(db.String(255), nullable=True)
    login_background_path = db.Column(db.String(255), nullable=True)
    default_cover_path = db.Column(db.String(255), nullable=True)
    # Campos que parecem estar faltando baseados no routes.py, adicionados para consistência
    color_scheme = db.Column(db.String(10), default="light")
    color_bg_main = db.Column(db.String(7), default="#f8f9fa")
    color_bg_card = db.Column(db.String(7), default="#ffffff")
    color_text_light = db.Column(db.String(7), default="#212529")
    color_border = db.Column(db.String(7), default="#dee2e6")
    login_media_path = db.Column(db.String(255), nullable=True)
    report_cover_path = db.Column(db.String(255), nullable=True)
    report_final_page_path = db.Column(db.String(255), nullable=True)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    users = db.relationship('User', backref='role', lazy='dynamic')

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    zabbix_url = db.Column(db.String(255), nullable=False)
    zabbix_user = db.Column(db.String(100), nullable=False)
    zabbix_password = db.Column(db.String(255), nullable=False)

    # === (Reintroduzido) Meta de SLA por cliente ===
    sla_contract = db.Column(db.Float, nullable=False, default=99.9)

    logo_path = db.Column(db.String(255))
    reports = db.relationship('Report', backref='client', lazy='dynamic')
    users = db.relationship('User', secondary=user_client_association, back_populates='clients')
    # Relacionamento com os grupos do Zabbix
    zabbix_groups = db.relationship('ClientZabbixGroup', backref='client', lazy='dynamic', cascade="all, delete-orphan")


# --- MODELO CORRIGIDO/ADICIONADO ---
class ClientZabbixGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    # Coluna real utilizada atualmente
    group_id = db.Column(db.String(50), nullable=False)

    # --- Alias para compatibilidade com backups/views antigas ---
    @property
    def zabbix_group_id(self):
        return self.group_id

    @zabbix_group_id.setter
    def zabbix_group_id(self, value):
        self.group_id = value

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'))
    reports = db.relationship('Report', backref='user', lazy='dynamic')
    clients = db.relationship('Client', secondary=user_client_association, back_populates='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role.name == 'Admin'
    
    def has_role(self, role_name):
        return self.role.name == role_name

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    reference_month = db.Column(db.String(7), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    report_type = db.Column(db.String(50), default='custom', nullable=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=dt.datetime.utcnow)
    user = db.relationship('User', backref='audit_logs')

# --- MODELOS PARA TEMPLATES DE RELATÓRIO ---
class ReportTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='report_templates')
    modules = db.relationship('ReportTemplateModule', backref='template', lazy='dynamic', cascade="all, delete-orphan")

class ReportTemplateModule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('report_template.id'), nullable=False)
    module_name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    config = db.Column(db.Text, nullable=True)

# --- NOVO MODELO PARA GERENCIAMENTO DINÂMICO DE CHAVES (KEYS) ---
class CalculationType(enum.Enum):
    DIRECT = "direct"
    INVERSE = "inverse"

class MetricKeyProfile(db.Model):
    __tablename__ = 'metric_key_profile'
    id = db.Column(db.Integer, primary_key=True)
    metric_type = db.Column(db.String(50), nullable=False, index=True) 
    key_string = db.Column(db.String(255), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=10)
    calculation_type = db.Column(db.Enum(CalculationType), nullable=False, default=CalculationType.DIRECT)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<MetricKeyProfile {self.metric_type} - {self.key_string} (Prio: {self.priority})>"
