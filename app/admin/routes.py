# app/admin/routes.py
import os
import datetime as dt
import uuid
from flask import (render_template, redirect, url_for, flash, request,
                   jsonify, g, current_app)
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user

from . import admin
from app import db
from app.models import (User, Client, Report, SystemConfig, Role,
                        ClientZabbixGroup, AuditLog)
from app.services import AuditService
# --- INÍCIO DA MODIFICAÇÃO ---
# Importando a nova função get_host_groups e removendo a importação desnecessária do ReportGenerator
from app.zabbix_api import obter_config_e_token_zabbix, get_host_groups
# --- FIM DA MODIFICAÇÃO ---
from app.utils import admin_required, allowed_file


def save_file_for_model(model_instance, attribute_name, file_key):
    """Salva um arquivo enviado e associa ao modelo, removendo o antigo se existir."""
    file = request.files.get(file_key)
    if file and allowed_file(file.filename):
        old_path = getattr(model_instance, attribute_name, None)
        if old_path and os.path.exists(os.path.join(current_app.config['UPLOAD_FOLDER'], old_path)):
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], old_path))
            except OSError as e:
                current_app.logger.error(f"Erro ao remover arquivo antigo {old_path}: {e}")
        
        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        setattr(model_instance, attribute_name, filename)
        return True
    return False


@admin.route('/')
@admin_required
def dashboard():
    stats = {
        'users': User.query.count(),
        'clients': Client.query.count(),
        'reports_total': Report.query.count(),
        'reports_month': Report.query.filter(Report.created_at >= dt.datetime.now().replace(day=1)).count()
    }
    latest_reports = Report.query.order_by(Report.created_at.desc()).limit(5).all()
    latest_users = User.query.order_by(User.id.desc()).limit(5).all()
    return render_template('admin/dashboard.html', title="Dashboard Admin", stats=stats, latest_reports=latest_reports, latest_users=latest_users)

# --- Gestão de Usuários (sem alterações) ---

@admin.route('/users')
@admin_required
def users():
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', title="Gerenciar Usuários", users=users)

@admin.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        if User.query.filter_by(username=username).first():
            flash(f"Usuário '{username}' já existe.", "danger")
        else:
            user = User(username=username, role_id=int(request.form['role_id']))
            user.set_password(request.form['password'])
            db.session.add(user)
            db.session.commit()
            AuditService.log(f"Adicionou novo usuário '{username}'")
            flash('Usuário adicionado!', 'success')
            return redirect(url_for('admin.users'))
    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Adicionar Usuário", roles=roles, user=None)

@admin.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if request.method == 'POST':
        AuditService.log(f"Editou o usuário '{user.username}' (ID: {user_id})")
        user.username = request.form['username']
        if request.form['password']:
            user.set_password(request.form['password'])
        user.role_id = int(request.form['role_id'])
        db.session.commit()
        flash('Usuário atualizado!', 'success')
        return redirect(url_for('admin.users'))
    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Editar Usuário", user=user, roles=roles)

@admin.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash('Você não pode excluir a si mesmo.', 'danger')
        return redirect(url_for('admin.users'))
    user = db.session.get(User, user_id)
    AuditService.log(f"Excluiu o usuário '{user.username}' (ID: {user_id})")
    db.session.delete(user)
    db.session.commit()
    flash('Usuário excluído.', 'success')
    return redirect(url_for('admin.users'))

# --- Gestão de Clientes ---
    
@admin.route('/clients')
@admin_required
def clients():
    clients = Client.query.order_by(Client.name).all()
    return render_template('admin/clients.html', title="Gerenciar Clientes", clients=clients)

@admin.route('/clients/add', methods=['GET', 'POST'])
@admin_required
def add_client():
    if request.method == 'POST':
        name = request.form['name']
        client = Client(name=name, sla_contract=float(request.form['sla_contract']))
        save_file_for_model(client, 'logo_path', 'logo')
        
        db.session.add(client)
        db.session.flush()

        group_ids = request.form.getlist('zabbix_group_ids')
        for group_id in group_ids:
            if group_id:
                new_group = ClientZabbixGroup(zabbix_group_id=group_id, client_id=client.id)
                db.session.add(new_group)

        db.session.commit()
        AuditService.log(f"Adicionou novo cliente '{name}'")
        flash('Cliente adicionado!', 'success')
        return redirect(url_for('admin.clients'))
    
    # --- INÍCIO DA MODIFICAÇÃO ---
    # Usando a nova função get_host_groups para buscar os grupos do Zabbix
    config_zabbix, erro = obter_config_e_token_zabbix(current_app.config, 'admin_task')
    zabbix_groups = []
    if not erro:
        zabbix_groups = get_host_groups(config_zabbix, config_zabbix['ZABBIX_URL'])
    else:
        flash(f"Aviso: Não foi possível carregar grupos do Zabbix. {erro}", "warning")
    # --- FIM DA MODIFICAÇÃO ---
    
    return render_template('admin/client_form.html', title="Adicionar Cliente", client=None, zabbix_groups=zabbix_groups)

@admin.route('/clients/edit/<int:client_id>', methods=['GET', 'POST'])
@admin_required
def edit_client(client_id):
    client = db.session.get(Client, client_id)
    if request.method == 'POST':
        AuditService.log(f"Editou o cliente '{client.name}' (ID: {client_id})")
        client.name = request.form['name']
        client.sla_contract = float(request.form['sla_contract'])
        save_file_for_model(client, 'logo_path', 'logo')
        
        ClientZabbixGroup.query.filter_by(client_id=client.id).delete()
        
        group_ids = request.form.getlist('zabbix_group_ids')
        for group_id in group_ids:
            if group_id:
                new_group = ClientZabbixGroup(zabbix_group_id=group_id, client_id=client.id)
                db.session.add(new_group)
        
        db.session.commit()
        flash('Cliente atualizado!', 'success')
        return redirect(url_for('admin.clients'))
        
    # --- INÍCIO DA MODIFICAÇÃO ---
    # Usando a nova função get_host_groups também na tela de edição
    config_zabbix, erro = obter_config_e_token_zabbix(current_app.config, 'admin_task')
    zabbix_groups = []
    if not erro:
        zabbix_groups = get_host_groups(config_zabbix, config_zabbix['ZABBIX_URL'])
    else:
        flash(f"Aviso: Não foi possível carregar grupos do Zabbix. {erro}", "warning")
    # --- FIM DA MODIFICAÇÃO ---
        
    return render_template('admin/client_form.html', title="Editar Cliente", client=client, zabbix_groups=zabbix_groups)

@admin.route('/clients/delete/<int:client_id>', methods=['POST'])
@admin_required
def delete_client(client_id):
    client = db.session.get(Client, client_id)
    AuditService.log(f"Excluiu o cliente '{client.name}' (ID: {client_id})")
    db.session.delete(client)
    db.session.commit()
    flash('Cliente excluído.', 'success')
    return redirect(url_for('admin.clients'))

# --- Vínculos (sem alterações) ---

@admin.route('/vincular', methods=['GET', 'POST'])
@admin_required
def vincular():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        client_ids = request.form.getlist('client_ids')
        user = db.session.get(User, int(user_id))
        if user:
            user.clients = [db.session.get(Client, int(cid)) for cid in client_ids]
            db.session.commit()
            AuditService.log(f"Atualizou vínculos para o usuário '{user.username}'")
            flash(f"Vínculos para {user.username} atualizados.", "success")
        return redirect(url_for('admin.vincular'))
    
    users = User.query.filter(User.role.has(name='client')).order_by(User.username).all()
    return render_template('admin/vincular.html', title="Vínculos", users=users)

@admin.route('/get_user_clients/<int:user_id>')
@admin_required
def get_user_clients(user_id):
    user = db.session.get(User, user_id)
    all_clients = Client.query.order_by(Client.name).all()
    linked_client_ids = [c.id for c in user.clients] if user else []
    return jsonify({
        "all_clients": [{"id": c.id, "name": c.name} for c in all_clients],
        "linked_clients": linked_client_ids
    })

# --- Configurações e Auditoria (sem alterações) ---

@admin.route('/customize')
@admin_required
def customize():
    return render_template('admin/customize.html', title="Configurações")

@admin.route('/customize/save', methods=['POST'])
@admin_required
def customize_save():
    AuditService.log("Atualizou as configurações do sistema")
    config = g.sys_config
    config.company_name = request.form['company_name']
    config.footer_text = request.form['footer_text']
    config.primary_color = request.form['primary_color']
    config.secondary_color = request.form['secondary_color']
    config.logo_size = int(request.form.get('logo_size', 50))
    config.login_media_fill_mode = request.form.get('login_media_fill_mode', 'cover')
    config.login_media_bg_color = request.form.get('login_media_bg_color', '#2c3e50')
    
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

@admin.route('/audit')
@admin_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return render_template('admin/audit_log.html', title="Log de Auditoria", logs=logs)

@admin.route('/test_zabbix', methods=['POST'])
@admin_required
def test_zabbix():
    _, error = obter_config_e_token_zabbix(current_app.config, 'admin_task')
    if not error:
        flash("Conexão com a API do Zabbix bem-sucedida!", "success")
        AuditService.log("Teste de conexão Zabbix: SUCESSO")
    else:
        flash(f"Falha na conexão com Zabbix: {error}", "danger")
        AuditService.log(f"Teste de conexão Zabbix: FALHA ({error})")
    return redirect(url_for('admin.customize'))