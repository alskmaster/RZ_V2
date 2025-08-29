from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.models import User
from app.services import AuditService
from . import auth
import logging

logger = logging.getLogger("app.auth.routes")

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        logger.debug("Usuário já autenticado → redirecionando para main.gerar_form")
        return redirect(url_for('main.gerar_form')) 

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        csrf = request.form.get('csrf_token')

        logger.debug({"evt": "login_attempt", "username": username, "has_csrf": bool(csrf)})

        if not csrf:
            logger.warning("Falha no login: token CSRF ausente.")
            flash('Erro de segurança: token CSRF ausente.', 'danger')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            AuditService.log("Login bem-sucedido", user=user)
            logger.info(f"Login OK para usuário {username}")
            return redirect(url_for('main.gerar_form'))
        else:
            AuditService.log(f"Tentativa de login falhou para '{username}'")
            logger.warning(f"Login falhou para '{username}'")
            flash('Usuário ou senha inválidos.', 'danger')

    return render_template('login.html')

@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        AuditService.log("Logout realizado")
        logger.info("Usuário fez logout")
    logout_user()
    return redirect(url_for('auth.login'))
