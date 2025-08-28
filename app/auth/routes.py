# app/auth/routes.py
from flask import render_template, redirect, url_for, flash, request, g
from flask_login import login_user, logout_user, current_user
from app.models import User
from app.services import AuditService
from . import auth

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Redireciona para a página principal, que estará no Blueprint 'main'
        return redirect(url_for('main.gerar_form')) 

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            AuditService.log("Login bem-sucedido", user=user)
            # Redireciona para a página principal
            return redirect(url_for('main.gerar_form'))
        else:
            AuditService.log(f"Tentativa de login falhou para o usuário '{request.form['username']}'")
            flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@auth.route('/logout')
def logout():
    # A sessão do usuário é limpa no logout, então logamos antes
    if current_user.is_authenticated:
        AuditService.log("Logout realizado")
    logout_user()
    # Redireciona para a própria página de login deste Blueprint
    return redirect(url_for('auth.login'))