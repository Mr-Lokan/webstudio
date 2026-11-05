from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query
from .utils import EMAIL_RE, STAFF_ROLES

bp = Blueprint('auth', __name__)


def _redirect_after_login(user):
    next_url = request.values.get('next', '')
    # разрешаем переход только на относительные адреса этого же сайта
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)
    if user['role'] in STAFF_ROLES:
        return redirect(url_for('admin.index'))
    return redirect(url_for('cabinet.index'))


@bp.route('/register', methods=('GET', 'POST'))
def register():
    if g.user:
        return redirect(url_for('cabinet.index'))
    form = {}
    if request.method == 'POST':
        form = request.form.to_dict()
        name = form.get('name', '').strip()
        email = form.get('email', '').strip().lower()
        phone = form.get('phone', '').strip()
        password = form.get('password', '')

        errors = []
        if len(name) < 2:
            errors.append('Укажите имя (не короче 2 символов).')
        if not EMAIL_RE.match(email):
            errors.append('Укажите корректный адрес электронной почты.')
        elif query('SELECT id FROM users WHERE email = ?', (email,), one=True):
            errors.append('Пользователь с таким e-mail уже зарегистрирован.')
        if len(password) < 6:
            errors.append('Пароль должен содержать не менее 6 символов.')
        if password != form.get('password2', ''):
            errors.append('Пароли не совпадают.')
        if not form.get('agree'):
            errors.append('Необходимо согласие на обработку персональных данных.')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            user_id = execute('INSERT INTO users (name, email, phone, password_hash) VALUES (?, ?, ?, ?)',
                              (name, email, phone or None, generate_password_hash(password)))
            session.clear()
            session['user_id'] = user_id
            flash('Регистрация прошла успешно. Добро пожаловать в личный кабинет!', 'success')
            return redirect(url_for('cabinet.index'))
    return render_template('auth/register.html', form=form)


@bp.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        return _redirect_after_login(g.user)
    email = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = query('SELECT * FROM users WHERE email = ?', (email,), one=True)
        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Неверный e-mail или пароль.', 'error')
        elif not user['is_active']:
            flash('Учётная запись заблокирована. Обратитесь к администратору студии.', 'error')
        else:
            session.clear()
            session['user_id'] = user['id']
            session.permanent = request.form.get('remember') == 'on'
            flash(f'Здравствуйте, {user["name"]}!', 'success')
            return _redirect_after_login(user)
    return render_template('auth/login.html', email=email)


@bp.route('/logout', methods=('POST',))
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('main.index'))
