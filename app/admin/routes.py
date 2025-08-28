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
                        ClientZabbixGroup, AuditLog, MetricKeyProfile, CalculationType)
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange

from app.services import AuditService
# --- IMPORTAÇÃO CORRIGIDA ---
# Importando as funções corretas do seu módulo zabbix_api.py
from app.zabbix_api import obter_config_e_token_zabbix, get_host_groups, fazer_request_zabbix
from app.utils import admin_required, allowed_file


class MetricKeyProfileForm(FlaskForm):
    metric_type = SelectField(
        'Tipo de Métrica',
        choices=[('memory', 'Memória'), ('cpu', 'CPU'), ('disk', 'Disco')],
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


def save_file_for_model(model_instance, attribute_name, file_key):
    file = request.files.get(file_key)
    if file and allowed_file(file.filename):
        old_path = getattr(model_instance, attribute_name, None)
        if old_path and os.path.exists(os.path.join(current_app.config['UPLOAD_FOLDER'], old_path)):
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], old_path))
            except OSError as e:
                current_app.logger.error(f"Erro ao remover arquivo antigo {old_path}: {e}")

        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        setattr(model_instance, attribute_name, filename)

@admin.route('/')
@admin_required
def dashboard():
    current_app.logger.debug("Acessando dashboard do admin.")
    try:
        stats = {
            'users': User.query.count(),
            'clients': Client.query.count(),
            'reports': Report.query.count()
        }
        current_app.logger.debug(f"Estatísticas carregadas: {stats}")
    except Exception as e:
        current_app.logger.error(f"Erro ao carregar estatísticas do dashboard: {e}", exc_info=True)
        stats = {'users': 0, 'clients': 0, 'reports': 0}
        flash('Não foi possível carregar as estatísticas do dashboard.', 'warning')
        
    return render_template('admin/dashboard.html', title="Dashboard", stats=stats)

@admin.route('/clients')
@admin_required
def list_clients():
    clients = Client.query.all()
    return render_template('admin/clients.html', clients=clients, title="Clientes")

@admin.route('/client/add', methods=['GET', 'POST'])
@admin_required
def add_client():
    if request.method == 'POST':
        name = request.form.get('name')
        zabbix_url = request.form.get('zabbix_url')
        zabbix_user = request.form.get('zabbix_user')
        zabbix_password = request.form.get('zabbix_password')
        
        if not all([name, zabbix_url, zabbix_user, zabbix_password]):
            flash('Todos os campos são obrigatórios.', 'danger')
            return redirect(url_for('admin.add_client'))

        new_client = Client(name=name, zabbix_url=zabbix_url, zabbix_user=zabbix_user, zabbix_password=zabbix_password)
        
        if 'logo' in request.files:
            save_file_for_model(new_client, 'logo_path', 'logo')

        db.session.add(new_client)
        db.session.commit()

        group_ids = request.form.getlist('zabbix_groups[]')
        for group_id in group_ids:
            if group_id:
                new_group = ClientZabbixGroup(client_id=new_client.id, group_id=group_id)
                db.session.add(new_group)
        db.session.commit()

        AuditService.log(f'Adicionou novo cliente: {name}')
        flash('Cliente adicionado com sucesso!', 'success')
        return redirect(url_for('admin.list_clients'))
    
    return render_template('admin/client_form.html', title="Adicionar Cliente", client=None, action="Adicionar", zabbix_groups=[], zabbix_groups_selecionados=[])

# --- FUNÇÃO CORRIGIDA ---
@admin.route('/client/edit/<int:client_id>', methods=['GET', 'POST'])
@admin_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == 'POST':
        client.name = request.form.get('name')
        client.zabbix_url = request.form.get('zabbix_url')
        client.zabbix_user = request.form.get('zabbix_user')
        if request.form.get('zabbix_password'):
            client.zabbix_password = request.form.get('zabbix_password')

        save_file_for_model(client, 'logo_path', 'logo')

        ClientZabbixGroup.query.filter_by(client_id=client_id).delete()
        group_ids = request.form.getlist('zabbix_groups[]')
        for group_id in group_ids:
            if group_id:
                new_group = ClientZabbixGroup(client_id=client_id, group_id=group_id)
                db.session.add(new_group)

        db.session.commit()
        AuditService.log(f'Editou o cliente: {client.name}')
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('admin.list_clients'))

    all_zabbix_groups = []
    try:
        # Usa a função do zabbix_api.py para obter config e token do cliente salvo
        config, error = obter_config_e_token_zabbix(client.id)
        if error:
            flash(f'Erro ao obter configuração do Zabbix: {error}', 'danger')
        elif config and config.get('ZABBIX_TOKEN'):
            # Passa a URL e o token para a função get_host_groups
            all_zabbix_groups = get_host_groups(config, config.get('ZABBIX_URL'))
    except Exception as e:
        flash(f'Não foi possível conectar ao Zabbix para listar os grupos: {e}', 'warning')
        current_app.logger.error(f"Falha ao buscar grupos Zabbix para o cliente {client.id}: {e}")

    zabbix_groups_selecionados = [g.group_id for g in client.zabbix_groups]
    return render_template('admin/client_form.html', title="Editar Cliente", client=client, action="Editar", zabbix_groups=all_zabbix_groups, zabbix_groups_selecionados=zabbix_groups_selecionados)


@admin.route('/client/delete/<int:client_id>', methods=['POST'])
@admin_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    client_name = client.name
    ClientZabbixGroup.query.filter_by(client_id=client_id).delete()
    db.session.delete(client)
    db.session.commit()
    AuditService.log(f'Excluiu o cliente: {client_name}')
    flash('Cliente excluído com sucesso!', 'success')
    return redirect(url_for('admin.list_clients'))

@admin.route('/users')
@admin_required
def list_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users, title="Usuários")

@admin.route('/user/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role_id = request.form.get('role')
        
        new_user = User(username=username, email=email, role_id=role_id)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        AuditService.log(f'Adicionou novo usuário: {username}')
        flash('Usuário adicionado com sucesso!', 'success')
        return redirect(url_for('admin.list_users'))

    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Adicionar Usuário", user=None, roles=roles, action="Adicionar")

@admin.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role_id = request.form.get('role')
        if request.form.get('password'):
            user.set_password(request.form.get('password'))
        db.session.commit()
        AuditService.log(f'Editou o usuário: {user.username}')
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('admin.list_users'))

    roles = Role.query.all()
    return render_template('admin/user_form.html', title="Editar Usuário", user=user, roles=roles, action="Editar")

@admin.route('/user/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    AuditService.log(f'Excluiu o usuário: {username}')
    flash('Usuário excluído com sucesso!', 'success')
    return redirect(url_for('admin.list_users'))

@admin.route('/user/<int:user_id>/vincular_cliente', methods=['GET', 'POST'])
@admin_required
def vincular_cliente_usuario(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        client_ids = request.form.getlist('clients')
        user.clients = Client.query.filter(Client.id.in_(client_ids)).all()
        db.session.commit()
        AuditService.log(f'Atualizou vínculos de clientes para o usuário: {user.username}')
        flash('Vínculos atualizados com sucesso!', 'success')
        return redirect(url_for('admin.list_users'))

    clients = Client.query.all()
    user_clients = [client.id for client in user.clients]
    return render_template('admin/vincular.html', user=user, clients=clients, user_clients=user_clients)

@admin.route('/metric_keys')
@admin_required
def list_metric_keys():
    current_app.logger.debug("Acessando a lista de perfis de métricas.")
    try:
        keys = MetricKeyProfile.query.order_by(MetricKeyProfile.metric_type, MetricKeyProfile.priority).all()
        current_app.logger.debug(f"Encontrados {len(keys)} perfis de métricas no banco de dados.")
    except Exception as e:
        current_app.logger.error(f"Erro ao consultar perfis de métricas: {e}", exc_info=True)
        flash('Erro ao carregar os perfis de métricas.', 'danger')
        keys = []
    return render_template('admin/metric_keys.html', keys=keys, title="Perfis de Coleta de Métricas")

@admin.route('/metric_key/add', methods=['GET', 'POST'])
@admin_required
def add_metric_key():
    current_app.logger.debug(f"Acessando rota add_metric_key com método {request.method}.")
    form = MetricKeyProfileForm()
    if form.validate_on_submit():
        current_app.logger.debug("Formulário de novo perfil de métrica validado com sucesso.")
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
            current_app.logger.error(f"Erro ao salvar novo perfil de métrica: {e}", exc_info=True)
            db.session.rollback()
            flash('Erro ao salvar o novo perfil de métrica. Consulte os logs.', 'danger')
    else:
        if request.method == 'POST':
            current_app.logger.warning(f"Validação do formulário de novo perfil falhou: {form.errors}")
            
    return render_template('admin/metric_key_form.html', form=form, title="Adicionar Perfil de Métrica", action="Adicionar")

@admin.route('/metric_key/edit/<int:key_id>', methods=['GET', 'POST'])
@admin_required
def edit_metric_key(key_id):
    current_app.logger.debug(f"Acessando rota edit_metric_key para ID {key_id} com método {request.method}.")
    key_profile = MetricKeyProfile.query.get_or_404(key_id)
    form = MetricKeyProfileForm(obj=key_profile)
    
    if request.method == 'GET':
        form.calculation_type.data = key_profile.calculation_type.name

    if form.validate_on_submit():
        current_app.logger.debug(f"Formulário de edição para o perfil {key_id} validado com sucesso.")
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
            current_app.logger.error(f"Erro ao atualizar perfil de métrica ID {key_id}: {e}", exc_info=True)
            db.session.rollback()
            flash('Erro ao atualizar o perfil de métrica. Consulte os logs.', 'danger')
    else:
        if request.method == 'POST':
            current_app.logger.warning(f"Validação do formulário de edição para o perfil {key_id} falhou: {form.errors}")

    return render_template('admin/metric_key_form.html', form=form, title="Editar Perfil de Métrica", action="Editar")

@admin.route('/metric_key/delete/<int:key_id>', methods=['POST'])
@admin_required
def delete_metric_key(key_id):
    current_app.logger.debug(f"Recebida requisição POST para excluir perfil de métrica ID {key_id}.")
    key_profile = MetricKeyProfile.query.get_or_404(key_id)
    key_string_log = key_profile.key_string
    try:
        db.session.delete(key_profile)
        db.session.commit()
        AuditService.log(f'Excluiu o perfil de métrica: {key_string_log}')
        flash('Perfil de métrica excluído com sucesso!', 'success')
    except Exception as e:
        current_app.logger.error(f"Erro ao excluir perfil de métrica ID {key_id}: {e}", exc_info=True)
        db.session.rollback()
        flash('Erro ao excluir o perfil de métrica. Consulte os logs.', 'danger')
        
    return redirect(url_for('admin.list_metric_keys'))

@admin.route('/customize', methods=['GET', 'POST'])
@admin_required
def customize():
    config = SystemConfig.query.first()
    if not config:
        config = SystemConfig()
        db.session.add(config)
        db.session.commit()

    if request.method == 'POST':
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
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return render_template('admin/audit_log.html', title="Log de Auditoria", logs=logs)

# --- ROTA CORRIGIDA ---
@admin.route('/test_zabbix', methods=['POST'])
@admin_required
def test_zabbix():
    data = request.get_json()
    if not data or not all(k in data for k in ['zabbix_url', 'zabbix_user', 'zabbix_password']):
        return jsonify({'success': False, 'message': 'Requisição inválida. Faltam dados de conexão.'})

    try:
        zabbix_url = data['zabbix_url']
        # Usa a função fazer_request_zabbix para obter o token
        login_body = {'jsonrpc': '2.0', 'method': 'user.login', 'params': {'username': data['zabbix_user'], 'password': data['zabbix_password']}, 'id': 1}
        token = fazer_request_zabbix(login_body, zabbix_url)

        if token and 'error' not in token:
            # Se o token foi obtido com sucesso, busca os grupos
            config_temp = {'ZABBIX_TOKEN': token}
            host_groups = get_host_groups(config_temp, zabbix_url)
            return jsonify({
                'success': True, 
                'message': 'Conexão com Zabbix bem-sucedida!',
                'groups': host_groups
            })
        else:
            error_details = token.get('details', 'Verifique as credenciais.') if isinstance(token, dict) else 'Erro desconhecido.'
            return jsonify({'success': False, 'message': f'Falha na autenticação: {error_details}'})
    except Exception as e:
        current_app.logger.error(f"Erro ao testar conexão Zabbix: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Erro de conexão: {e}'})