import functools
import math
import os
import re
import secrets
import uuid
from datetime import date, datetime

from flask import abort, current_app, flash, g, redirect, request, session, url_for
from markupsafe import Markup, escape

from .db import execute, query

ROLES = {
    'client': 'Клиент',
    'designer': 'Дизайнер',
    'admin': 'Администратор',
}
STAFF_ROLES = ('designer', 'admin')

ORDER_STATUSES = {
    'new': 'Новый',
    'discussion': 'Согласование ТЗ',
    'in_progress': 'В работе',
    'review': 'На проверке у клиента',
    'done': 'Завершён',
    'cancelled': 'Отменён',
}
ACTIVE_STATUSES = ('new', 'discussion', 'in_progress', 'review')
# статусы, которые может выставлять дизайнер (остальные — только администратор или клиент)
DESIGNER_STATUSES = ('discussion', 'in_progress', 'review')

PAYMENT_METHODS = {
    'card': 'Банковская карта',
    'transfer': 'Безналичный перевод',
    'cash': 'Наличные',
}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$')
MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']


# ---------------------------------------------------------------- авторизация

def load_logged_in_user():
    """Загружает текущего пользователя из сессии в g.user перед каждым запросом."""
    g.user = None
    user_id = session.get('user_id')
    if user_id is not None:
        user = query('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if user is not None and user['is_active']:
            g.user = user
        else:
            session.clear()


def _login_redirect():
    flash('Войдите в систему, чтобы продолжить.', 'warning')
    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for('auth.login', next=next_url))


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return _login_redirect()
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    """Пропускает к представлению только пользователей с указанными ролями."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return _login_redirect()
            if g.user['role'] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------- защита от CSRF

def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']


def csrf_protect():
    if request.method == 'POST':
        token = request.form.get('csrf_token', '')
        if not token or not secrets.compare_digest(token, session.get('_csrf', '')):
            abort(400)


# ---------------------------------------------------------------- проверка ввода

def parse_int(value, minimum=None):
    """Преобразует строку в целое число; пустая строка — None, ошибка — ValueError."""
    value = (value or '').replace(' ', '').replace(' ', '').strip()
    if not value:
        return None
    number = int(value)
    if minimum is not None and number < minimum:
        raise ValueError
    return number


def parse_date(value):
    value = (value or '').strip()
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date().isoformat()


TRANSLIT = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
                    ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p',
                     'r', 's', 't', 'u', 'f', 'h', 'ts', 'ch', 'sh', 'sch', '', 'y', '', 'e', 'yu', 'ya']))


def slugify(text):
    text = ''.join(TRANSLIT.get(ch, ch) for ch in text.lower())
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-') or uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- файлы

def save_upload(file_storage):
    """Сохраняет загруженное изображение под случайным именем и возвращает это имя."""
    if file_storage is None or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in current_app.config['ALLOWED_EXTENSIONS']:
        raise ValueError('Допустимые форматы изображений: ' + ', '.join(sorted(current_app.config['ALLOWED_EXTENSIONS'])))
    filename = f'{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
    return filename


def delete_upload(filename):
    if not filename:
        return
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], os.path.basename(filename))
    if os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------- заказы

def set_order_status(order_id, old_status, new_status):
    """Меняет статус заказа и записывает изменение в журнал."""
    execute('UPDATE orders SET status = ? WHERE id = ?', (new_status, order_id))
    execute('INSERT INTO order_status_history (order_id, user_id, old_status, new_status) VALUES (?, ?, ?, ?)',
            (order_id, g.user['id'] if g.user else None, old_status, new_status))


def add_comment(order_id, text):
    execute('INSERT INTO comments (order_id, user_id, text) VALUES (?, ?, ?)', (order_id, g.user['id'], text))


def order_comments(order_id):
    return query('''SELECT c.*, u.name AS author, u.role AS author_role
                    FROM comments c LEFT JOIN users u ON u.id = c.user_id
                    WHERE c.order_id = ? ORDER BY c.created_at, c.id''', (order_id,))


def order_history(order_id):
    return query('''SELECT h.*, u.name AS author
                    FROM order_status_history h LEFT JOIN users u ON u.id = h.user_id
                    WHERE h.order_id = ? ORDER BY h.created_at, h.id''', (order_id,))


def order_payments(order_id):
    return query('SELECT * FROM payments WHERE order_id = ? ORDER BY created_at, id', (order_id,))


# ---------------------------------------------------------------- постраничный вывод

class Pagination:
    def __init__(self, page, per_page, total):
        self.per_page = per_page
        self.total = total
        self.pages = max(math.ceil(total / per_page), 1)
        self.page = min(max(page, 1), self.pages)
        self.offset = (self.page - 1) * per_page
        self.has_prev = self.page > 1
        self.has_next = self.page < self.pages

    def iter_pages(self):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= 2 or num > self.pages - 2 or abs(num - self.page) <= 1:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def page_url(page):
    args = request.args.to_dict()
    args['page'] = page
    return url_for(request.endpoint, **(request.view_args or {}), **args)


# ---------------------------------------------------------------- шаблонные фильтры

def _to_datetime(value):
    if isinstance(value, (datetime, date)):
        return value
    for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, pattern)
        except (TypeError, ValueError):
            continue
    return None


def format_date(value, with_time=False):
    dt = _to_datetime(value)
    if dt is None:
        return value or '—'
    return dt.strftime('%d.%m.%Y %H:%M' if with_time and isinstance(dt, datetime) else '%d.%m.%Y')


def format_money(value):
    if value is None or value == '':
        return '—'
    return f'{int(value):,}'.replace(',', ' ') + ' ₽'


def nl2br(value):
    if not value:
        return ''
    paragraphs = [p.strip() for p in str(value).split('\n\n') if p.strip()]
    return Markup(''.join(f'<p>{escape(p)}</p>'.replace('\n', '<br>') for p in paragraphs))


def plural(n, one, few, many):
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def initials(name):
    parts = [p for p in (name or '?').replace('«', '').replace('»', '').split() if p]
    return ''.join(p[0] for p in parts[:2]).upper()


def avatar_hue(name):
    return sum(ord(ch) for ch in (name or '')) * 37 % 360


def is_overdue(order):
    return bool(order['deadline']) and order['status'] in ACTIVE_STATUSES \
        and order['deadline'] < date.today().isoformat()


def init_app(app):
    app.before_request(load_logged_in_user)
    app.before_request(csrf_protect)
    app.jinja_env.filters.update(date=format_date, money=format_money, nl2br=nl2br)
    app.jinja_env.globals.update(
        csrf_token=csrf_token, page_url=page_url, plural=plural, initials=initials,
        avatar_hue=avatar_hue, is_overdue=is_overdue,
        ROLES=ROLES, ORDER_STATUSES=ORDER_STATUSES, PAYMENT_METHODS=PAYMENT_METHODS,
    )

    @app.context_processor
    def inject_common():
        return {'current_year': date.today().year, 'today': date.today().isoformat()}
