import csv
import io
import sqlite3
from datetime import date

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from .db import execute, query
from .utils import (ACTIVE_STATUSES, DESIGNER_STATUSES, EMAIL_RE, MONTHS_SHORT, ORDER_STATUSES, PAYMENT_METHODS,
                    ROLES, STAFF_ROLES, Pagination, add_comment, delete_upload, order_comments, order_history,
                    order_payments, parse_date, parse_int, role_required, save_upload, set_order_status, slugify)

bp = Blueprint('admin', __name__)

staff_required = role_required(*STAFF_ROLES)
admin_required = role_required('admin')


def _is_admin():
    return g.user['role'] == 'admin'


def _flash_errors(errors):
    for error in errors:
        flash(error, 'error')


@bp.context_processor
def inject_badges():
    """Счётчики для бокового меню панели управления."""
    if g.get('user') is None or g.user['role'] not in STAFF_ROLES:
        return {}
    if _is_admin():
        badges = query('''SELECT
                (SELECT COUNT(*) FROM orders WHERE status = 'new')         AS orders,
                (SELECT COUNT(*) FROM feedback WHERE is_processed = 0)     AS feedback,
                (SELECT COUNT(*) FROM reviews WHERE is_approved = 0)       AS reviews''', one=True)
    else:
        badges = query(f'''SELECT COUNT(*) AS orders FROM orders
                           WHERE designer_id = ? AND status IN ({",".join("?" * len(ACTIVE_STATUSES))})''',
                       (g.user['id'], *ACTIVE_STATUSES), one=True)
    return {'badges': dict(badges), 'is_admin': _is_admin()}


# ======================================================================= дашборд

def _last_months(count=6):
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append((f'{year}-{month:02d}', f'{MONTHS_SHORT[month - 1]} {str(year)[2:]}'))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


@bp.route('/')
@staff_required
def index():
    scope, scope_args = ('', ()) if _is_admin() else (' WHERE designer_id = ?', (g.user['id'],))

    by_status = {row['status']: row['cnt'] for row in
                 query('SELECT status, COUNT(*) AS cnt FROM orders' + scope + ' GROUP BY status', scope_args)}
    total = sum(by_status.values())
    status_chart = [(key, label, by_status.get(key, 0)) for key, label in ORDER_STATUSES.items()]

    latest = query('SELECT * FROM order_summary' + scope + ' ORDER BY created_at DESC LIMIT 6', scope_args)
    overdue = query('SELECT * FROM order_summary' + (scope + ' AND' if scope else ' WHERE') +
                    f''' deadline < date('now', 'localtime')
                         AND status IN ({",".join("?" * len(ACTIVE_STATUSES))}) ORDER BY deadline''',
                    (*scope_args, *ACTIVE_STATUSES))

    context = dict(total=total, by_status=by_status, status_chart=status_chart, latest=latest, overdue=overdue,
                   active=sum(by_status.get(s, 0) for s in ACTIVE_STATUSES))

    if _is_admin():
        months = _last_months()
        revenue_rows = {row['ym']: row['total'] for row in query(
            '''SELECT strftime('%Y-%m', created_at) AS ym, SUM(amount) AS total
               FROM payments WHERE strftime('%Y-%m', created_at) >= ? GROUP BY ym''', (months[0][0],))}
        revenue = [(label, revenue_rows.get(key, 0)) for key, label in months]
        context.update(
            revenue=revenue,
            revenue_max=max([value for _, value in revenue] + [1]),
            finance=query('''SELECT
                    IFNULL((SELECT SUM(amount) FROM payments), 0) AS total,
                    IFNULL((SELECT SUM(amount) FROM payments
                            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')), 0) AS month,
                    IFNULL((SELECT SUM(price - paid) FROM order_summary
                            WHERE status != 'cancelled' AND price > paid), 0) AS debt,
                    (SELECT COUNT(*) FROM users WHERE role = 'client') AS clients''', one=True),
            workload=query('''SELECT u.id, u.name, u.position,
                    SUM(CASE WHEN o.status IN ('discussion', 'in_progress', 'review') THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN o.status = 'done' THEN 1 ELSE 0 END) AS done
                FROM users u LEFT JOIN orders o ON o.designer_id = u.id
                WHERE u.role = 'designer' AND u.is_active = 1
                GROUP BY u.id ORDER BY active DESC, u.name'''),
            popular=query('''SELECT s.title, COUNT(o.id) AS cnt, IFNULL(SUM(o.price), 0) AS amount
                FROM services s JOIN orders o ON o.service_id = s.id AND o.status != 'cancelled'
                GROUP BY s.id ORDER BY cnt DESC, amount DESC LIMIT 5'''),
        )
    return render_template('admin/dashboard.html', **context)


# ======================================================================= заказы

def _get_order(order_id):
    order = query('SELECT * FROM order_summary WHERE id = ?', (order_id,), one=True)
    if order is None:
        abort(404)
    if not _is_admin() and order['designer_id'] != g.user['id']:
        abort(403)
    return order


def _designers():
    return query("SELECT id, name, position FROM users WHERE role = 'designer' AND is_active = 1 ORDER BY name")


@bp.route('/orders')
@staff_required
def orders():
    status = request.args.get('status', '')
    designer = request.args.get('designer', '')
    q = request.args.get('q', '').strip()

    where, args = [], []
    if not _is_admin():
        where.append('designer_id = ?')
        args.append(g.user['id'])
    elif designer == 'none':
        where.append('designer_id IS NULL')
    elif designer.isdigit():
        where.append('designer_id = ?')
        args.append(int(designer))
    if status == 'active':
        where.append(f'status IN ({",".join("?" * len(ACTIVE_STATUSES))})')
        args.extend(ACTIVE_STATUSES)
    elif status in ORDER_STATUSES:
        where.append('status = ?')
        args.append(status)
    if q:
        like = f'%{q.lower()}%'
        where.append('(py_lower(title) LIKE ? OR py_lower(client_name) LIKE ? OR py_lower(client_email) LIKE ? '
                     'OR CAST(id AS TEXT) = ?)')
        args.extend([like, like, like, q.lstrip('#№')])
    where_sql = ' WHERE ' + ' AND '.join(where) if where else ''

    total = query('SELECT COUNT(*) FROM order_summary' + where_sql, args, one=True)[0]
    pager = Pagination(request.args.get('page', 1, type=int), current_app.config['PER_PAGE'], total)
    rows = query('SELECT * FROM order_summary' + where_sql + ' ORDER BY created_at DESC LIMIT ? OFFSET ?',
                 [*args, pager.per_page, pager.offset])
    return render_template('admin/orders.html', orders=rows, pager=pager, designers=_designers(),
                           filters={'status': status, 'designer': designer, 'q': q})


@bp.route('/orders/<int:order_id>', methods=('GET', 'POST'))
@staff_required
def order(order_id):
    order = _get_order(order_id)
    allowed_statuses = list(ORDER_STATUSES) if _is_admin() else list(DESIGNER_STATUSES)

    if request.method == 'POST':
        errors = []
        new_status = request.form.get('status', order['status'])
        if new_status != order['status'] and new_status not in allowed_statuses:
            errors.append('Недопустимый статус.')

        if _is_admin():
            designer_id = price = deadline = None
            try:
                designer_id = parse_int(request.form.get('designer_id'))
                if designer_id and not query("SELECT 1 FROM users WHERE id = ? AND role = 'designer'",
                                             (designer_id,), one=True):
                    errors.append('Исполнитель не найден.')
            except ValueError:
                errors.append('Некорректный исполнитель.')
            try:
                price = parse_int(request.form.get('price'), minimum=0)
            except ValueError:
                errors.append('Стоимость должна быть неотрицательным целым числом.')
            try:
                deadline = parse_date(request.form.get('deadline'))
            except ValueError:
                errors.append('Некорректная дата сдачи.')
            if new_status in ('in_progress', 'review', 'done') and not (designer_id and price):
                errors.append('Чтобы перевести заказ в работу, назначьте исполнителя и стоимость.')
            if not errors:
                execute('UPDATE orders SET designer_id = ?, price = ?, deadline = ? WHERE id = ?',
                        (designer_id, price, deadline, order_id))

        if errors:
            _flash_errors(errors)
        else:
            if new_status != order['status']:
                set_order_status(order_id, order['status'], new_status)
            flash('Изменения сохранены.', 'success')
        return redirect(url_for('admin.order', order_id=order_id))

    review = query('SELECT * FROM reviews WHERE order_id = ?', (order_id,), one=True)
    return render_template('admin/order.html', order=order, review=review, designers=_designers(),
                           allowed_statuses=allowed_statuses, comments=order_comments(order_id),
                           history=order_history(order_id), payments=order_payments(order_id))


@bp.route('/orders/<int:order_id>/comment', methods=('POST',))
@staff_required
def order_comment(order_id):
    _get_order(order_id)
    text = request.form.get('text', '').strip()
    if text:
        add_comment(order_id, text[:3000])
        flash('Сообщение отправлено клиенту.', 'success')
    else:
        flash('Сообщение не может быть пустым.', 'error')
    return redirect(url_for('admin.order', order_id=order_id) + '#comments')


@bp.route('/orders/<int:order_id>/payment', methods=('POST',))
@admin_required
def order_payment(order_id):
    order = _get_order(order_id)
    method = request.form.get('method', 'transfer')
    try:
        amount = parse_int(request.form.get('amount'), minimum=1)
    except ValueError:
        amount = None
    if not amount:
        flash('Укажите сумму оплаты (целое положительное число).', 'error')
    elif method not in PAYMENT_METHODS:
        flash('Некорректный способ оплаты.', 'error')
    else:
        execute('INSERT INTO payments (order_id, amount, method, note, created_by) VALUES (?, ?, ?, ?, ?)',
                (order_id, amount, method, request.form.get('note', '').strip() or None, g.user['id']))
        if order['price'] and order['paid'] + amount > order['price']:
            flash('Платёж добавлен. Внимание: сумма оплат превышает стоимость заказа.', 'warning')
        else:
            flash('Платёж добавлен.', 'success')
    return redirect(url_for('admin.order', order_id=order_id) + '#payments')


@bp.route('/payments/<int:payment_id>/delete', methods=('POST',))
@admin_required
def payment_delete(payment_id):
    payment = query('SELECT * FROM payments WHERE id = ?', (payment_id,), one=True)
    if payment is None:
        abort(404)
    execute('DELETE FROM payments WHERE id = ?', (payment_id,))
    flash('Платёж удалён.', 'info')
    return redirect(url_for('admin.order', order_id=payment['order_id']) + '#payments')


@bp.route('/orders/<int:order_id>/delete', methods=('POST',))
@admin_required
def order_delete(order_id):
    _get_order(order_id)
    execute('DELETE FROM orders WHERE id = ?', (order_id,))
    flash(f'Заказ №{order_id} удалён.', 'info')
    return redirect(url_for('admin.orders'))


@bp.route('/orders/export')
@admin_required
def orders_export():
    """Выгрузка реестра заказов в CSV (открывается в Excel)."""
    rows = query('SELECT * FROM order_summary ORDER BY id')
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['№', 'Дата создания', 'Клиент', 'E-mail', 'Телефон', 'Услуга', 'Проект', 'Исполнитель',
                     'Статус', 'Стоимость', 'Оплачено', 'Остаток', 'Срок сдачи'])
    for r in rows:
        writer.writerow([r['id'], r['created_at'], r['client_name'], r['client_email'], r['client_phone'] or '',
                         r['service_title'] or '', r['title'], r['designer_name'] or '',
                         ORDER_STATUSES[r['status']], r['price'] or '', r['paid'],
                         max((r['price'] or 0) - r['paid'], 0), r['deadline'] or ''])
    filename = f'orders_{date.today().isoformat()}.csv'
    return Response('﻿' + out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


# ======================================================================= услуги

@bp.route('/services')
@admin_required
def services():
    rows = query('''SELECT s.*, c.name AS category,
                           (SELECT COUNT(*) FROM orders o WHERE o.service_id = s.id) AS orders_count
                    FROM services s JOIN categories c ON c.id = s.category_id
                    ORDER BY c.id, s.price_from''')
    return render_template('admin/services.html', services=rows)


@bp.route('/services/new', methods=('GET', 'POST'))
@bp.route('/services/<int:service_id>/edit', methods=('GET', 'POST'))
@admin_required
def service_form(service_id=None):
    service = None
    if service_id is not None:
        service = query('SELECT * FROM services WHERE id = ?', (service_id,), one=True)
        if service is None:
            abort(404)
    categories = query('SELECT * FROM categories ORDER BY name')
    form = dict(service) if service else {'is_active': 1, 'duration_days': 14}

    if request.method == 'POST':
        form = request.form.to_dict()
        errors = []
        title = form.get('title', '').strip()
        if len(title) < 3:
            errors.append('Укажите название услуги.')
        category_id = price_from = duration = None
        try:
            category_id = parse_int(form.get('category_id'))
            if not category_id or not query('SELECT 1 FROM categories WHERE id = ?', (category_id,), one=True):
                errors.append('Выберите категорию.')
        except ValueError:
            errors.append('Выберите категорию.')
        try:
            price_from = parse_int(form.get('price_from'), minimum=0)
            if price_from is None:
                errors.append('Укажите стоимость.')
        except ValueError:
            errors.append('Стоимость должна быть неотрицательным целым числом.')
        try:
            duration = parse_int(form.get('duration_days'), minimum=1)
            if duration is None:
                errors.append('Укажите срок выполнения.')
        except ValueError:
            errors.append('Срок выполнения должен быть положительным числом.')

        if errors:
            _flash_errors(errors)
        else:
            values = (category_id, title, form.get('short_description', '').strip(),
                      form.get('description', '').strip(), price_from, duration, 1 if form.get('is_active') else 0)
            if service:
                execute('''UPDATE services SET category_id = ?, title = ?, short_description = ?, description = ?,
                           price_from = ?, duration_days = ?, is_active = ? WHERE id = ?''', (*values, service_id))
                flash('Услуга обновлена.', 'success')
            else:
                execute('''INSERT INTO services (category_id, title, short_description, description, price_from,
                           duration_days, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)''', values)
                flash('Услуга добавлена.', 'success')
            return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=service, form=form, categories=categories)


@bp.route('/services/<int:service_id>/delete', methods=('POST',))
@admin_required
def service_delete(service_id):
    execute('DELETE FROM services WHERE id = ?', (service_id,))
    flash('Услуга удалена.', 'info')
    return redirect(url_for('admin.services'))


# ======================================================================= категории

@bp.route('/categories', methods=('GET', 'POST'))
@admin_required
def categories():
    if request.method == 'POST':
        category_id = request.form.get('id', type=int)
        name = request.form.get('name', '').strip()
        slug = slugify(request.form.get('slug', '').strip() or name)
        description = request.form.get('description', '').strip() or None
        if len(name) < 2:
            flash('Укажите название категории.', 'error')
        else:
            try:
                if category_id:
                    execute('UPDATE categories SET name = ?, slug = ?, description = ? WHERE id = ?',
                            (name, slug, description, category_id))
                    flash('Категория обновлена.', 'success')
                else:
                    execute('INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)',
                            (name, slug, description))
                    flash('Категория добавлена.', 'success')
            except sqlite3.IntegrityError:
                flash('Категория с таким названием или адресом уже существует.', 'error')
        return redirect(url_for('admin.categories'))

    rows = query('''SELECT c.*,
                           (SELECT COUNT(*) FROM services s WHERE s.category_id = c.id)  AS services_count,
                           (SELECT COUNT(*) FROM portfolio p WHERE p.category_id = c.id) AS works_count
                    FROM categories c ORDER BY c.id''')
    return render_template('admin/categories.html', categories=rows)


@bp.route('/categories/<int:category_id>/delete', methods=('POST',))
@admin_required
def category_delete(category_id):
    try:
        execute('DELETE FROM categories WHERE id = ?', (category_id,))
        flash('Категория удалена.', 'info')
    except sqlite3.IntegrityError:
        flash('Нельзя удалить категорию, к которой привязаны услуги.', 'error')
    return redirect(url_for('admin.categories'))


# ======================================================================= портфолио

@bp.route('/portfolio')
@admin_required
def portfolio():
    rows = query('''SELECT p.*, c.name AS category FROM portfolio p
                    LEFT JOIN categories c ON c.id = p.category_id ORDER BY p.year DESC, p.id DESC''')
    return render_template('admin/portfolio.html', works=rows)


@bp.route('/portfolio/new', methods=('GET', 'POST'))
@bp.route('/portfolio/<int:work_id>/edit', methods=('GET', 'POST'))
@admin_required
def portfolio_form(work_id=None):
    work = None
    if work_id is not None:
        work = query('SELECT * FROM portfolio WHERE id = ?', (work_id,), one=True)
        if work is None:
            abort(404)
    categories = query('SELECT * FROM categories ORDER BY name')
    form = dict(work) if work else {'is_published': 1, 'year': date.today().year}

    if request.method == 'POST':
        form = request.form.to_dict()
        errors = []
        title = form.get('title', '').strip()
        if len(title) < 2:
            errors.append('Укажите название работы.')
        category_id = year = None
        try:
            category_id = parse_int(form.get('category_id'))
        except ValueError:
            errors.append('Некорректная категория.')
        try:
            year = parse_int(form.get('year'), minimum=2000)
        except ValueError:
            errors.append('Укажите корректный год.')
        url = form.get('url', '').strip()
        if url and not url.startswith(('http://', 'https://')):
            errors.append('Ссылка на проект должна начинаться с http:// или https://')
        image = work['image'] if work else None
        if not errors:
            try:
                uploaded = save_upload(request.files.get('image'))
                if uploaded:
                    if image:
                        delete_upload(image)
                    image = uploaded
            except ValueError as exc:
                errors.append(str(exc))
        if not image and not errors:
            errors.append('Загрузите изображение работы.')

        if errors:
            _flash_errors(errors)
        else:
            values = (category_id, title, form.get('client', '').strip() or None,
                      form.get('description', '').strip(), image, url or None,
                      year, 1 if form.get('is_published') else 0)
            if work:
                execute('''UPDATE portfolio SET category_id = ?, title = ?, client = ?, description = ?, image = ?,
                           url = ?, year = ?, is_published = ? WHERE id = ?''', (*values, work_id))
                flash('Работа обновлена.', 'success')
            else:
                execute('''INSERT INTO portfolio (category_id, title, client, description, image, url, year,
                           is_published) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', values)
                flash('Работа добавлена в портфолио.', 'success')
            return redirect(url_for('admin.portfolio'))
    return render_template('admin/portfolio_form.html', work=work, form=form, categories=categories)


@bp.route('/portfolio/<int:work_id>/delete', methods=('POST',))
@admin_required
def portfolio_delete(work_id):
    work = query('SELECT * FROM portfolio WHERE id = ?', (work_id,), one=True)
    if work is None:
        abort(404)
    execute('DELETE FROM portfolio WHERE id = ?', (work_id,))
    delete_upload(work['image'])
    flash('Работа удалена.', 'info')
    return redirect(url_for('admin.portfolio'))


# ======================================================================= пользователи

@bp.route('/users')
@admin_required
def users():
    role = request.args.get('role', '')
    q = request.args.get('q', '').strip()
    where, args = [], []
    if role in ROLES:
        where.append('u.role = ?')
        args.append(role)
    if q:
        like = f'%{q.lower()}%'
        where.append('(py_lower(u.name) LIKE ? OR py_lower(u.email) LIKE ? OR u.phone LIKE ?)')
        args.extend([like, like, like])
    where_sql = ' WHERE ' + ' AND '.join(where) if where else ''

    total = query('SELECT COUNT(*) FROM users u' + where_sql, args, one=True)[0]
    pager = Pagination(request.args.get('page', 1, type=int), current_app.config['PER_PAGE'], total)
    rows = query('''SELECT u.*,
                           (SELECT COUNT(*) FROM orders o WHERE o.client_id = u.id OR o.designer_id = u.id) AS orders_count
                    FROM users u''' + where_sql + ' ORDER BY u.created_at DESC LIMIT ? OFFSET ?',
                 [*args, pager.per_page, pager.offset])
    return render_template('admin/users.html', users=rows, pager=pager, filters={'role': role, 'q': q})


@bp.route('/users/new', methods=('GET', 'POST'))
@bp.route('/users/<int:user_id>/edit', methods=('GET', 'POST'))
@admin_required
def user_form(user_id=None):
    user = None
    if user_id is not None:
        user = query('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if user is None:
            abort(404)
    form = dict(user) if user else {'role': 'client', 'is_active': 1}
    form.pop('password_hash', None)

    if request.method == 'POST':
        form = request.form.to_dict()
        errors = []
        name = form.get('name', '').strip()
        email = form.get('email', '').strip().lower()
        role = form.get('role', 'client')
        password = form.get('password', '')
        is_active = 1 if form.get('is_active') else 0
        if len(name) < 2:
            errors.append('Укажите имя.')
        if not EMAIL_RE.match(email):
            errors.append('Некорректный e-mail.')
        elif query('SELECT 1 FROM users WHERE email = ? AND id != ?', (email, user_id or 0), one=True):
            errors.append('Пользователь с таким e-mail уже существует.')
        if role not in ROLES:
            errors.append('Некорректная роль.')
        if (not user or password) and len(password) < 6:
            errors.append('Пароль должен содержать не менее 6 символов.')
        if user and user['id'] == g.user['id'] and (role != 'admin' or not is_active):
            errors.append('Нельзя снять с себя права администратора или заблокировать свою учётную запись.')

        if errors:
            _flash_errors(errors)
        else:
            values = (name, email, form.get('phone', '').strip() or None, role,
                      form.get('position', '').strip() or None, form.get('bio', '').strip() or None, is_active)
            if user:
                execute('''UPDATE users SET name = ?, email = ?, phone = ?, role = ?, position = ?, bio = ?,
                           is_active = ? WHERE id = ?''', (*values, user_id))
                if password:
                    execute('UPDATE users SET password_hash = ? WHERE id = ?',
                            (generate_password_hash(password), user_id))
                flash('Данные пользователя сохранены.', 'success')
            else:
                execute('''INSERT INTO users (name, email, phone, role, position, bio, is_active, password_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (*values, generate_password_hash(password)))
                flash('Пользователь создан.', 'success')
            return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user, form=form)


@bp.route('/users/<int:user_id>/delete', methods=('POST',))
@admin_required
def user_delete(user_id):
    if user_id == g.user['id']:
        flash('Нельзя удалить собственную учётную запись.', 'error')
    elif query('SELECT 1 FROM orders WHERE client_id = ? OR designer_id = ?', (user_id, user_id), one=True):
        flash('У пользователя есть заказы — удаление невозможно. Заблокируйте учётную запись вместо удаления.', 'error')
    else:
        execute('DELETE FROM users WHERE id = ?', (user_id,))
        flash('Пользователь удалён.', 'info')
    return redirect(url_for('admin.users'))


# ======================================================================= обращения и отзывы

@bp.route('/feedback')
@admin_required
def feedback():
    show = request.args.get('show', 'new')
    sql = 'SELECT * FROM feedback' + (' WHERE is_processed = 0' if show == 'new' else '') + ' ORDER BY created_at DESC'
    return render_template('admin/feedback.html', items=query(sql), show=show)


@bp.route('/feedback/<int:item_id>/toggle', methods=('POST',))
@admin_required
def feedback_toggle(item_id):
    execute('UPDATE feedback SET is_processed = 1 - is_processed WHERE id = ?', (item_id,))
    return redirect(request.referrer or url_for('admin.feedback'))


@bp.route('/feedback/<int:item_id>/delete', methods=('POST',))
@admin_required
def feedback_delete(item_id):
    execute('DELETE FROM feedback WHERE id = ?', (item_id,))
    flash('Обращение удалено.', 'info')
    return redirect(request.referrer or url_for('admin.feedback'))


@bp.route('/reviews')
@admin_required
def reviews():
    rows = query('''SELECT r.*, u.name AS author, u.email AS author_email, o.title AS order_title
                    FROM reviews r JOIN users u ON u.id = r.user_id LEFT JOIN orders o ON o.id = r.order_id
                    ORDER BY r.is_approved, r.created_at DESC''')
    return render_template('admin/reviews.html', reviews=rows)


@bp.route('/reviews/<int:review_id>/toggle', methods=('POST',))
@admin_required
def review_toggle(review_id):
    execute('UPDATE reviews SET is_approved = 1 - is_approved WHERE id = ?', (review_id,))
    flash('Статус отзыва изменён.', 'success')
    return redirect(request.referrer or url_for('admin.reviews'))


@bp.route('/reviews/<int:review_id>/delete', methods=('POST',))
@admin_required
def review_delete(review_id):
    execute('DELETE FROM reviews WHERE id = ?', (review_id,))
    flash('Отзыв удалён.', 'info')
    return redirect(request.referrer or url_for('admin.reviews'))
