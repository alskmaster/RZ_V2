# app/admin/routes.py
import os
import re
import datetime as dt
import uuid
import logging

from flask import (
    render_template, redirect, url_for, flash, request,
    jsonify, g, current_app
)
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from . import admin
from app import db
from app.models import (
    User, Client, Report, SystemConfig, Role,
    ClientZabbixGroup, AuditLog, MetricKeyProfile, CalculationType
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SubmitField, BooleanField, SelectField,
    IntegerField, TextAreaField
)
from wtforms.validators import DataRequired, Length, NumberRange

from app.services import AuditService
# --- IMPORTAÇÃO CORRIGIDA ---
# Importando as funções corretas do seu módulo zabbix_api.py
from app.zabbix_api import obter_config_e_token_zabbix, get_host_groups, fazer_request_zabbix
from app.utils import admin_required, allowed_file
from sqlalchemy.orm import joinedload


# ===== Helpers de Debug / Observabilidade ====================================

def _ensure_request_id():
    """Gera um request-id por requisição (debug e correlação de logs)."""
    if not getattr(g, "request_id", None):
        g.request_id = uuid.uuid4().hex
    return g.request_id


def _log_debug(msg, **extra):
    """Log estruturado nivel DEBUG com request-id."""
    rid = _ensure_request_id()
    payload = {"rid": rid, **extra}
    try:
        current_app.logger.debug(f"{msg} | {payload}")
    except Exception:
        # fallback ultra-seguro caso logger quebre
        print(f"DEBUG {msg} | {payload}")


def _sanitize_url(url: str) -> str:
    """Normaliza URL do Zabbix; não força, mas tenta corrigir faltas comuns."""
    if not url:
        return url
    url = url.strip()
    # se for base do zabbix, tenta acrescentar endpoint da API
    if url.endswith("/"):
        url = url[:-1]
    # heurística: se não contém api_jsonrpc, sugere acrescentar (não obrigatório)
    if not url.lower().endswith("api_jsonrpc.php"):
        # não alteramos silenciosamente, apenas registramos no log
        _log_debug("Zabbix URL sem api_jsonrpc.php (pode estar ok se já inclui)", url=url)
    return url


# ===== Form (já existia) ======================================================

class MetricKeyProfileForm(FlaskForm):
    metric_type = SelectField(
        'Tipo de Métrica',
        choices=[
            ('memory', 'Memória'),
            ('cpu', 'CPU'),
            ('disk', 'Disco'),
            ('wifi_clients', 'Wi-Fi (Contagem de Clientes)')  # <-- NOVO
        ],
        validators=[DataRequired(message="Selecione o tipo de métrica.")]
    )
    key_string = StringField(
        'Chave (Key) do Zabbix',
        validators=[DataRequired(message="A chave do item é obrigatória."), Length(min=1, max=255)]
    )
    priority = IntegerField(
        'Prioridade',
        validators=[DataRequired(message="A prioridade é obrigatória."), NumberRange(min=1, max=100)],
        default=10
    )
    calculation_type = SelectField(
        'Tipo de Cálculo',
        choices=[(calc.name, calc.value) for calc in CalculationType],
        validators=[DataRequired(message="O tipo de cálculo é obrigatório.")]
    )
    description = TextAreaField(
        'Descrição',
        validators=[Length(max=255)]
    )
    is_active = BooleanField('Ativo', default=True)
    submit = SubmitField('Salvar')


# ===== Utilitário de upload (já existia, com logs adicionais) ================

def save_file_for_model(model_instance, attribute_name, file_key):
    file = request.files.get(file_key)
    if file and allowed_file(file.filename):
        old_path = getattr(model_instance, attribute_name, None)
        uploads_dir = current_app.config.get('UPLOAD_FOLDER', '')
        _log_debug("save_file_for_model: recebendo arquivo",
                   attribute=attribute_name, filename=file.filename, uploads_dir=uploads_dir)

        if old_path and os.path.exists(os.path.join(uploads_dir, old_path)):
            try:
                os.remove(os.path.join(uploads_dir, old_path))
                _log_debug("Arquivo antigo removido com sucesso", old_path=old_path)
            except OSError as e:
                current_app.logger.error(
                    f"[{_ensure_request_id()}] Erro ao remover arquivo antigo {old_path}: {e}",
                    exc_info=True
                )

        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        dest_path = os.path.join(uploads_dir, filename)
        file.save(dest_path)
        setattr(model_instance, attribute_name, filename)
        _log_debug("Arquivo salvo", new_path=filename)


# ===== Rotas Admin ============================================================

@admin.route('/')
@admin_required
def dashboard():
    rid = _ensure_request_id()
    _log_debug("Acessando dashboard do admin")
    try:
        stats = {
            'users': User.query.count(),
            'clients': Client.query.count(),
            'reports': Report.query.count()
        }
        _log_debug("Estatísticas carregadas", **stats)
    except Exception as e:
        current_app.logger.error(
            f"[{rid}] Erro ao carregar estatísticas do dashboard: {e}", exc_info=True
        )
        stats = {'users': 0, 'clients': 0, 'reports': 0}
        flash('Não foi possível carregar as estatísticas do dashboard.', 'warning')
    return render_template('admin/dashboard.html', title="Dashboard", stats=stats)


@admin.route('/clients')
@admin_required
def list_clients():
    _ensure_request_id()
    _log_debug("Listando clientes")
    clients = Client.query.all()
    return render_template('admin/clients.html', clients=clients, title="Clientes")


@admin.route('/client/add', methods=['GET', 'POST'])
@admin_required
def add_client():
    rid = _ensure_request_id()
    if request.method == 'POST':
        # Nunca logar senha
        name = (request.form.get('name') or '').strip()
        zabbix_url = _sanitize_url(request.form.get('zabbix_url') or '')
        zabbix_user = (request.form.get('zabbix_user') or '').strip()
        zabbix_password = request.form.get('zabbix_password')  # não logar

        # --- NOVO: SLA contract ---
        raw_sla = (request.form.get('sla_contract') or '').strip()
        sla_value = 99.9
        if raw_sla:
            raw_sla = raw_sla.replace(',', '.')
            try:
                sla_value = float(raw_sla)
            except ValueError:
                sla_value = 99.9
        _log_debug("Valor SLA recebido no add_client", raw=raw_sla, parsed=sla_value)

        _log_debug(
            "POST /client/add recebido",
            method=request.method,
            has_pw=bool(zabbix_password),
            form_keys=sorted(list(request.form.keys())),
            files=list(request.files.keys())
        )

        # Validações mínimas
        if not all([name, zabbix_url, zabbix_user, zabbix_password]):
            flash('Todos os campos são obrigatórios.', 'danger')
            _log_debug("Validação falhou: campos obrigatórios ausentes",
                       name=bool(name), url=bool(zabbix_url), user=bool(zabbix_user), pw=bool(zabbix_password))
            return redirect(url_for('admin.add_client'))

        # Idempotência básica por nome (evita duplicatas acidentais)
        existing = Client.query.filter(Client.name.ilike(name)).first()
        if existing:
            flash('Já existe um cliente com esse nome.', 'warning')
            _log_debug("Cliente duplicado detectado", client_id=existing.id, name=name)
            return redirect(url_for('admin.add_client'))

        new_client = Client(
            name=name,
            zabbix_url=zabbix_url,
            zabbix_user=zabbix_user,
            zabbix_password=zabbix_password,  # Considerar criptografar/secret manager no futuro
            sla_contract=sla_value
        )

        group_ids = [g for g in request.form.getlist('zabbix_groups[]') if g]
        _log_debug("Grupos recebidos no cadastro", group_count=len(group_ids))

        try:
            # Upload (se houver)
            if 'logo' in request.files:
                save_file_for_model(new_client, 'logo_path', 'logo')

            # Persistência atômica (uma transação)
            db.session.add(new_client)
            db.session.flush()  # obtém new_client.id antes

            for group_id in group_ids:
                db.session.add(ClientZabbixGroup(client_id=new_client.id, group_id=group_id))

            db.session.commit()
            AuditService.log(f'Adicionou novo cliente: {name}')
            flash('Cliente adicionado com sucesso!', 'success')
            _log_debug("Cliente criado com sucesso", client_id=new_client.id, name=name, groups=len(group_ids))
            return redirect(url_for('admin.list_clients'))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[{rid}] Erro ao salvar cliente: {e}", exc_info=True)
            flash('Erro ao salvar o cliente. Tente novamente ou consulte os logs.', 'danger')
            return redirect(url_for('admin.add_client'))

    # GET
    _log_debug("GET /client/add renderizando formulário")
    return render_template(
        'admin/client_form.html',
        title="Adicionar Cliente",
        client=None,
        action="Adicionar",
        zabbix_groups=[],
        zabbix_groups_selecionados=[]
    )


# --- FUNÇÃO CORRIGIDA ---
@admin.route('/client/edit/<int:client_id>', methods=['GET', 'POST'])
@admin_required
def edit_client(client_id):
    rid = _ensure_request_id()
    client = Client.query.get_or_404(client_id)
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        zabbix_url = _sanitize_url(request.form.get('zabbix_url') or '')
        zabbix_user = (request.form.get('zabbix_user') or '').strip()
        zabbix_password = request.form.get('zabbix_password')  # opcional

        # --- NOVO: SLA contract ---
        raw_sla = (request.form.get('sla_contract') or '').strip()
        if raw_sla:
            raw_sla = raw_sla.replace(',', '.')
            try:
                client.sla_contract = float(raw_sla)
            except ValueError:
                _log_debug("Valor SLA inválido no edit, mantendo atual", raw=raw_sla)

        _log_debug(
            "POST /client/edit recebido",
            client_id=client_id,
            method=request.method,
            has_pw=bool(zabbix_password),
            form_keys=sorted(list(request.form.keys())),
            files=list(request.files.keys()),
            sla=client.sla_contract
        )

        if not all([name, zabbix_url, zabbix_user]):
            flash('Nome, URL do Zabbix e Usuário são obrigatórios.', 'danger')
            _log_debug("Validação falhou no edit: campos obrigatórios ausentes",
                       name=bool(name), url=bool(zabbix_url), user=bool(zabbix_user))
            return redirect(url_for('admin.edit_client', client_id=client_id))

        # Idempotência por nome (exceto o próprio)
        existing = Client.query.filter(Client.name.ilike(name), Client.id != client_id).first()
        if existing:
            flash('Já existe outro cliente com esse nome.', 'warning')
            _log_debug("Conflito de nome em edição", other_client_id=existing.id, name=name)
            return redirect(url_for('admin.edit_client', client_id=client_id))

        try:
            client.name = name
            client.zabbix_url = zabbix_url
            client.zabbix_user = zabbix_user
            if zabbix_password:
                client.zabbix_password = zabbix_password

            # Upload (se houver)
            if 'logo' in request.files:
                save_file_for_model(client, 'logo_path', 'logo')

            # Atualiza grupos (reset simples)
            ClientZabbixGroup.query.filter_by(client_id=client_id).delete()
            group_ids = [g for g in request.form.getlist('zabbix_groups[]') if g]
            for group_id in group_ids:
                db.session.add(ClientZabbixGroup(client_id=client_id, group_id=group_id))

            db.session.commit()
            AuditService.log(f'Editou o cliente: {client.name}')
            flash('Cliente atualizado com sucesso!', 'success')
            _log_debug("Cliente atualizado", client_id=client_id, groups=len(group_ids))
            return redirect(url_for('admin.list_clients'))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[{rid}] Erro ao atualizar cliente {client_id}: {e}", exc_info=True)
            flash('Erro ao atualizar o cliente. Tente novamente ou consulte os logs.', 'danger')
            return redirect(url_for('admin.edit_client', client_id=client_id))

    # GET - carrega grupos do Zabbix (best-effort)
    all_zabbix_groups = []
    try:
        config, error = obter_config_e_token_zabbix(client.id)
        if error:
            flash(f'Erro ao obter configuração do Zabbix: {error}', 'danger')
            _log_debug("Erro obter_config_e_token_zabbix", client_id=client.id, error=str(error))
        elif config and config.get('ZABBIX_TOKEN'):
            all_zabbix_groups = get_host_groups(config, config.get('ZABBIX_URL'))
            _log_debug("Grupos retornados do Zabbix", count=len(all_zabbix_groups))
    except Exception as e:
        flash(f'Não foi possível conectar ao Zabbix para listar os grupos: {e}', 'warning')
        current_app.logger.error(
            f"[{rid}] Falha ao buscar grupos Zabbix para o cliente {client.id}: {e}", exc_info=True
        )

    zabbix_groups_selecionados = [g.group_id for g in client.zabbix_groups]
    return render_template(
        'admin/client_form.html',
        title="Editar Cliente",
        client=client,
        action="Editar",
        zabbix_groups=all_zabbix_groups,
        zabbix_groups_selecionados=zabbix_groups_selecionados
    )


@admin.route('/client/delete/<int:client_id>', methods=['POST'])
@admin_required
def delete_client(client_id):
    rid = _ensure_request_id()
    _log_debug("POST /client/delete", client_id=client_id)
    client = Client.query.get_or_404(client_id)
    client_name = client.name
    try:
        ClientZabbixGroup.query.filter_by(client_id=client_id).delete()
        db.session.delete(client)
        db.session.commit()
        AuditService.log(f'Excluiu o cliente: {client_name}')
        flash('Cliente excluído com sucesso!', 'success')
        _log_debug("Cliente excluído", client_id=client_id, name=client_name)
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"[{rid}] Erro ao excluir cliente {client_id}: {e}", exc_info=True)
        flash('Erro ao excluir o cliente. Consulte os logs.', 'danger')
    return redirect(url_for('admin.list_clients'))


@admin.route('/users')
@admin_required
def list_users():
    _ensure_request_id()
    _log_debug("Listando usuários")
    users = User.query.all()
    return render_template('admin/users.html', users=users, title="Usuários")


@admin.route('/user/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    rid = _ensure_request_id()
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password')
        role_id = request.form.get('role')

        _log_debug("POST /user/add", username=username, email=email, role_id=role_id, has_pw=bool(password))

        try:
            new_user = User(username=username, email=email, role_id=role_id)
            if password:
                new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            AuditService.log(f'Adicionou novo usuário: {username}')
            flash('Usuário adicionado com sucesso!', 'success')
            return redirect(url_for('admin.list_users'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[{rid}] Erro ao adicionar usuário: {e}", exc_info=True)
            flash('Erro ao adicionar usuário. Consulte os logs.', 'danger')
            return redirect(url_for('admin.add_user'))

    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Adicionar Usuário", user=None, roles=roles, action="Adicionar")


@admin.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    rid = _ensure_request_id()
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        role_id = request.form.get('role')
        password = request.form.get('password')

        _log_debug("POST /user/edit", user_id=user_id, username=username, email=email, role_id=role_id, has_pw=bool(password))

        try:
            user.username = username
            user.email = email
            user.role_id = role_id
            if password:
                user.set_password(password)
            db.session.commit()
            AuditService.log(f'Editou o usuário: {user.username}')
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('admin.list_users'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[{rid}] Erro ao atualizar usuário {user_id}: {e}", exc_info=True)
            flash('Erro ao atualizar usuário. Consulte os logs.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))

    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Editar Usuário", user=user, roles=roles, action="Editar")


@admin.route('/user/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    rid = _ensure_request_id()
    _log_debug("POST /user/delete", user_id=user_id)
    user = User.query.get_or_404(user_id)
    username = user.username
    try:
        db.session.delete(user)
        db.session.commit()
        AuditService.log(f'Excluiu o usuário: {username}')
        flash('Usuário excluído com sucesso!', 'success')
        _log_debug("Usuário excluído", user_id=user_id, username=username)
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"[{rid}] Erro ao excluir usuário {user_id}: {e}", exc_info=True)
        flash('Erro ao excluir o usuário. Consulte os logs.', 'danger')
    return redirect(url_for('admin.list_users'))


@admin.route('/user/<int:user_id>/vincular_cliente', methods=['GET', 'POST'])
@admin_required
def vincular_cliente_usuario(user_id):
    rid = _ensure_request_id()
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        client_ids = request.form.getlist('clients')
        _log_debug("POST /user/vincular_cliente", user_id=user_id, clients_count=len(client_ids))
        try:
            user.clients = Client.query.filter(Client.id.in_(client_ids)).all()
            db.session.commit()
            AuditService.log(f'Atualizou vínculos de clientes para o usuário: {user.username}')
            flash('Vínculos atualizados com sucesso!', 'success')
            return redirect(url_for('admin.list_users'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"[{rid}] Erro ao vincular clientes para user {user_id}: {e}", exc_info=True)
            flash('Erro ao atualizar vínculos. Consulte os logs.', 'danger')
            return redirect(url_for('admin.vincular_cliente_usuario', user_id=user_id))

    clients = Client.query.all()
    user_clients = [client.id for client in user.clients]
    return render_template('admin/vincular.html', user=user, clients=clients, user_clients=user_clients)


@admin.route('/metric_keys')
@admin_required
def list_metric_keys():
    _ensure_request_id()
    _log_debug("Acessando a lista de perfis de métricas")
    try:
        keys = MetricKeyProfile.query.order_by(MetricKeyProfile.metric_type, MetricKeyProfile.priority).all()
        _log_debug("Perfis de métricas carregados", count=len(keys))
    except Exception as e:
        current_app.logger.error(f"[{g.request_id}] Erro ao consultar perfis de métricas: {e}", exc_info=True)
        flash('Erro ao carregar os perfis de métricas.', 'danger')
        keys = []
    return render_template('admin/metric_keys.html', keys=keys, title="Perfis de Coleta de Métricas")


@admin.route('/metric_key/add', methods=['GET', 'POST'])
@admin_required
def add_metric_key():
    _ensure_request_id()
    _log_debug("Acessando rota add_metric_key", method=request.method)
    form = MetricKeyProfileForm()
    if form.validate_on_submit():
        _log_debug("Formulário de novo perfil de métrica validado")
        try:
            new_key = MetricKeyProfile(
                metric_type=form.metric_type.data,
                key_string=form.key_string.data,
                priority=form.priority.data,
                calculation_type=CalculationType[form.calculation_type.data],
                description=form.description.data,
                is_active=form.is_active.data
            )
            db.session.add(new_key)
            db.session.commit()
            AuditService.log(f'Adicionou novo perfil de métrica: {new_key.key_string}')
            flash('Novo perfil de métrica adicionado com sucesso!', 'success')
            return redirect(url_for('admin.list_metric_keys'))
        except Exception as e:
            current_app.logger.error(f"[{g.request_id}] Erro ao salvar novo perfil de métrica: {e}", exc_info=True)
            db.session.rollback()
            flash('Erro ao salvar o novo perfil de métrica. Consulte os logs.', 'danger')
    else:
        if request.method == 'POST':
            _log_debug("Validação do formulário de novo perfil falhou", errors=form.errors)

    return render_template('admin/metric_key_form.html', form=form, title="Adicionar Perfil de Métrica", action="Adicionar")


@admin.route('/metric_key/edit/<int:key_id>', methods=['GET', 'POST'])
@admin_required
def edit_metric_key(key_id):
    _ensure_request_id()
    _log_debug("Acessando rota edit_metric_key", key_id=key_id, method=request.method)
    key_profile = MetricKeyProfile.query.get_or_404(key_id)
    form = MetricKeyProfileForm(obj=key_profile)

    if request.method == 'GET':
        form.calculation_type.data = key_profile.calculation_type.name

    if form.validate_on_submit():
        _log_debug("Formulário de edição de perfil validado", key_id=key_id)
        try:
            key_profile.metric_type = form.metric_type.data
            key_profile.key_string = form.key_string.data
            key_profile.priority = form.priority.data
            key_profile.calculation_type = CalculationType[form.calculation_type.data]
            key_profile.description = form.description.data
            key_profile.is_active = form.is_active.data
            db.session.commit()
            AuditService.log(f'Editou o perfil de métrica ID {key_id}: {key_profile.key_string}')
            flash('Perfil de métrica atualizado com sucesso!', 'success')
            return redirect(url_for('admin.list_metric_keys'))
        except Exception as e:
            current_app.logger.error(f"[{g.request_id}] Erro ao atualizar perfil de métrica ID {key_id}: {e}", exc_info=True)
            db.session.rollback()
            flash('Erro ao atualizar o perfil de métrica. Consulte os logs.', 'danger')
    else:
        if request.method == 'POST':
            _log_debug("Validação do formulário de edição falhou", key_id=key_id, errors=form.errors)

    return render_template('admin/metric_key_form.html', form=form, title="Editar Perfil de Métrica", action="Editar")


@admin.route('/metric_key/delete/<int:key_id>', methods=['POST'])
@admin_required
def delete_metric_key(key_id):
    _ensure_request_id()
    _log_debug("POST /metric_key/delete", key_id=key_id)
    key_profile = MetricKeyProfile.query.get_or_404(key_id)
    key_string_log = key_profile.key_string
    try:
        db.session.delete(key_profile)
        db.session.commit()
        AuditService.log(f'Excluiu o perfil de métrica: {key_string_log}')
        flash('Perfil de métrica excluído com sucesso!', 'success')
    except Exception as e:
        current_app.logger.error(f"[{g.request_id}] Erro ao excluir perfil de métrica ID {key_id}: {e}", exc_info=True)
        db.session.rollback()
        flash('Erro ao excluir o perfil de métrica. Consulte os logs.', 'danger')

    return redirect(url_for('admin.list_metric_keys'))


@admin.route('/customize', methods=['GET', 'POST'])
@admin_required
def customize():
    _ensure_request_id()
    config = SystemConfig.query.first()
    if not config:
        config = SystemConfig()
        db.session.add(config)
        db.session.commit()

    if request.method == 'POST':
        _log_debug("POST /customize recebido", files=list(request.files.keys()))
        config.company_name = request.form['company_name']
        config.footer_text = request.form['footer_text']
        config.primary_color = request.form['primary_color']
        config.secondary_color = request.form['secondary_color']
        config.color_scheme = request.form['color_scheme']
        config.color_bg_main = request.form['color_bg_main']
        config.color_bg_card = request.form['color_bg_card']
        config.color_text_light = request.form['color_text_light']
        config.color_border = request.form['color_border']

        save_file_for_model(config, 'logo_dark_bg_path', 'logo_dark')
        save_file_for_model(config, 'logo_light_bg_path', 'logo_light')
        save_file_for_model(config, 'login_media_path', 'login_media')
        save_file_for_model(config, 'report_cover_path', 'report_cover')
        save_file_for_model(config, 'report_final_page_path', 'report_final_page')

        db.session.commit()
        flash('Customizações salvas com sucesso!', 'success')
        return redirect(url_for('admin.customize'))

    return render_template('admin/customize.html', title="Customização", config=config)


@admin.route('/audit')
@admin_required
def audit_log():
    _ensure_request_id()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    _log_debug("Audit log listado", count=len(logs))
    return render_template('admin/audit_log.html', title="Log de Auditoria", logs=logs)


# --- ROTA CORRIGIDA ---
@admin.route('/test_zabbix', methods=['POST'])
@admin_required
def test_zabbix():
    rid = _ensure_request_id()
    # Flask-WTF CSRF: token deve vir no header 'X-CSRFToken' (já enviado pelo front)
    data = request.get_json(silent=True) or {}
    _log_debug(
        "POST /test_zabbix recebido",
        has_json=bool(data),
        keys=list(data.keys())
    )

    required = ['zabbix_url', 'zabbix_user', 'zabbix_password']
    if not all(k in data and data[k] for k in required):
        return jsonify({'success': False, 'message': 'Requisição inválida. Faltam dados de conexão.'})

    try:
        zabbix_url = _sanitize_url(data['zabbix_url'])
        # Nunca logar senha
        login_body = {
            'jsonrpc': '2.0',
            'method': 'user.login',
            'params': {'username': data['zabbix_user'], 'password': data['zabbix_password']},
            'id': 1
        }
        token = fazer_request_zabbix(login_body, zabbix_url)

        if token and isinstance(token, dict) and 'error' in token:
            error_details = token.get('details') or token.get('error') or 'Verifique as credenciais.'
            _log_debug("Falha na autenticação do Zabbix", details=str(error_details))
            return jsonify({'success': False, 'message': f'Falha na autenticação: {error_details}'})

        if not token:
            _log_debug("Token vazio/None retornado pelo Zabbix")
            return jsonify({'success': False, 'message': 'Não foi possível obter token do Zabbix.'})

        # Busca grupos com config temporária
        config_temp = {'ZABBIX_TOKEN': token}
        host_groups = get_host_groups(config_temp, zabbix_url) or []
        _log_debug("test_zabbix grupos obtidos", count=len(host_groups))

        return jsonify({
            'success': True,
            'message': 'Conexão com Zabbix bem-sucedida!',
            'groups': host_groups
        })

    except Exception as e:
        current_app.logger.error(f"[{rid}] Erro ao testar conexão Zabbix: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro de conexão: {e}'})
