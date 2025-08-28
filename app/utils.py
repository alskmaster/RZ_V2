# app/utils.py
from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user, login_required

def admin_required(f):
    """
    Decorador que verifica se o usuário logado tem a função 'admin' ou 'super_admin'.
    Se não tiver, redireciona para a página principal com uma mensagem de erro.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.has_role('admin') or current_user.has_role('super_admin')):
            flash('Acesso negado. Você não tem permissão para acessar esta área.', 'danger')
            return redirect(url_for('main.gerar_form'))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    """Verifica se a extensão de um arquivo está na lista de extensões permitidas."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def get_text_color_for_bg(hex_color):
    """
    Calcula se a cor de texto ideal para um fundo de cor hexadecimal é
    preta ou branca, com base na luminância.
    """
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return '#212529' if luminance > 0.6 else '#ffffff'
    except (ValueError, TypeError):
        # Retorna branco como padrão em caso de erro
        return '#ffffff'