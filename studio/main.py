from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import execute, query
from .utils import EMAIL_RE

bp = Blueprint('main', __name__)

SERVICES_SQL = '''SELECT s.*, c.name AS category, c.slug AS category_slug
                  FROM services s JOIN categories c ON c.id = s.category_id'''
PORTFOLIO_SQL = '''SELECT p.*, c.name AS category, c.slug AS category_slug
                   FROM portfolio p LEFT JOIN categories c ON c.id = p.category_id'''


@bp.route('/')
def index():
    services = query(SERVICES_SQL + ' WHERE s.is_active = 1 ORDER BY s.price_from DESC LIMIT 6')
    works = query(PORTFOLIO_SQL + ' WHERE p.is_published = 1 ORDER BY p.year DESC, p.id DESC LIMIT 6')
    reviews = query('''SELECT r.*, u.name AS author, s.title AS service
                       FROM reviews r
                       JOIN users u ON u.id = r.user_id
                       LEFT JOIN orders o ON o.id = r.order_id
                       LEFT JOIN services s ON s.id = o.service_id
                       WHERE r.is_approved = 1 ORDER BY r.created_at DESC LIMIT 3''')
    stats = query('''SELECT
            (SELECT COUNT(*) FROM orders WHERE status = 'done')
              + (SELECT COUNT(*) FROM portfolio WHERE is_published = 1)                 AS projects,
            (SELECT COUNT(*) FROM users WHERE role = 'client')                          AS clients,
            (SELECT COUNT(*) FROM users WHERE role != 'client' AND is_active = 1)       AS team,
            (SELECT ROUND(AVG(rating), 1) FROM reviews WHERE is_approved = 1)           AS rating''', one=True)
    return render_template('index.html', services=services, works=works, reviews=reviews, stats=stats)


@bp.route('/services')
def services():
    slug = request.args.get('category', '')
    sql, args = SERVICES_SQL + ' WHERE s.is_active = 1', []
    if slug:
        sql += ' AND c.slug = ?'
        args.append(slug)
    categories = query('''SELECT c.* FROM categories c
                          WHERE EXISTS (SELECT 1 FROM services s WHERE s.category_id = c.id AND s.is_active = 1)
                          ORDER BY c.id''')
    return render_template('services.html', services=query(sql + ' ORDER BY c.id, s.price_from', args),
                           categories=categories, current=slug)


@bp.route('/services/<int:service_id>')
def service_detail(service_id):
    service = query(SERVICES_SQL + ' WHERE s.id = ? AND s.is_active = 1', (service_id,), one=True)
    if service is None:
        abort(404)
    works = query(PORTFOLIO_SQL + ' WHERE p.is_published = 1 AND p.category_id = ? ORDER BY p.year DESC LIMIT 3',
                  (service['category_id'],))
    others = query(SERVICES_SQL + ' WHERE s.is_active = 1 AND s.id != ? ORDER BY RANDOM() LIMIT 3', (service_id,))
    return render_template('service.html', service=service, works=works, others=others)


@bp.route('/portfolio')
def portfolio():
    slug = request.args.get('category', '')
    sql, args = PORTFOLIO_SQL + ' WHERE p.is_published = 1', []
    if slug:
        sql += ' AND c.slug = ?'
        args.append(slug)
    categories = query('''SELECT c.* FROM categories c
                          WHERE EXISTS (SELECT 1 FROM portfolio p WHERE p.category_id = c.id AND p.is_published = 1)
                          ORDER BY c.id''')
    return render_template('portfolio.html', works=query(sql + ' ORDER BY p.year DESC, p.id DESC', args),
                           categories=categories, current=slug)


@bp.route('/portfolio/<int:work_id>')
def portfolio_item(work_id):
    work = query(PORTFOLIO_SQL + ' WHERE p.id = ? AND p.is_published = 1', (work_id,), one=True)
    if work is None:
        abort(404)
    more = query(PORTFOLIO_SQL + ' WHERE p.is_published = 1 AND p.id != ? ORDER BY RANDOM() LIMIT 3', (work_id,))
    return render_template('portfolio_item.html', work=work, more=more)


@bp.route('/about')
def about():
    team = query('''SELECT * FROM users WHERE role != 'client' AND is_active = 1 AND position IS NOT NULL
                    ORDER BY role = 'admin' DESC, id''')
    return render_template('about.html', team=team)


@bp.route('/calculator')
def calculator():
    return render_template('calculator.html')


@bp.route('/contacts', methods=('GET', 'POST'))
def contacts():
    form = {}
    if g.user:
        form = {'name': g.user['name'], 'email': g.user['email'], 'phone': g.user['phone'] or ''}
    if request.method == 'POST':
        form = request.form.to_dict()
        name = form.get('name', '').strip()
        email = form.get('email', '').strip().lower()
        phone = form.get('phone', '').strip()
        message = form.get('message', '').strip()

        errors = []
        if len(name) < 2:
            errors.append('Укажите ваше имя.')
        if not email and not phone:
            errors.append('Укажите e-mail или телефон для связи.')
        if email and not EMAIL_RE.match(email):
            errors.append('Некорректный адрес электронной почты.')
        if len(message) < 10:
            errors.append('Сообщение должно содержать не менее 10 символов.')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            execute('INSERT INTO feedback (name, email, phone, message) VALUES (?, ?, ?, ?)',
                    (name, email or None, phone or None, message))
            flash('Спасибо! Ваше сообщение отправлено, менеджер свяжется с вами в течение рабочего дня.', 'success')
            return redirect(url_for('main.contacts'))
    return render_template('contacts.html', form=form)
