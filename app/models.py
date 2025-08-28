# app/models.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import datetime as dt
from . import db  # Importa a instância 'db' do nosso __init__.py

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
    logo_size = db.Column(db.Integer, default=50)
    login_media_path = db.Column(db.String(255), nullable=True)
    login_media_fill_mode = db.Column(db.String(10), default='cover')
    login_media_bg_color = db.Column(db.String(7), default='#2c3e50')
    report_cover_path = db.Column(db.String(255), nullable=True)
    report_final_page_path = db.Column(db.String(255), nullable=True)
    color_scheme = db.Column(db.String(50), default="dark")
    color_bg_main = db.Column(db.String(7), default="#2a2f34")
    color_bg_card = db.Column(db.String(7), default="#3c424a")
    color_text_light = db.Column(db.String(7), default="#e1e2e3")
    color_border = db.Column(db.String(7), default="#54595f")

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class ClientZabbixGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    zabbix_group_id = db.Column(db.String(50), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    sla_contract = db.Column(db.Float, nullable=False, default=99.9)
    logo_path = db.Column(db.String(255), nullable=True)
    reports = db.relationship('Report', backref='client', lazy=True, cascade="all, delete-orphan")
    zabbix_groups = db.relationship('ClientZabbixGroup', backref='client', lazy=True, cascade="all, delete-orphan")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref='users')
    reports = db.relationship('Report', backref='author', lazy=True)
    clients = db.relationship('Client', secondary=user_client_association, lazy='subquery',
                              backref=db.backref('users', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
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

# NOVO MODELO - TEMPLATES DE RELATÓRIO
# Este modelo permite que os usuários salvem e reutilizem layouts de relatórios complexos.
class ReportTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    layout_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    
    def __repr__(self):
        return f"<ReportTemplate {self.name}>"