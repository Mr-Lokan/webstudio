from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query
from .utils import (ACTIVE_STATUSES, EMAIL_RE, STAFF_ROLES, add_comment, login_required, order_comments,
                    order_history, order_payments, parse_date, parse_int, role_required, set_order_status)

bp = Blueprint('cabinet', __name__)

client_required = role_required('client')


def _get_own_order(order_id):
    order = query('SELECT * FROM order_summary WHERE id = ? AND client_id = ?', (order_id, g.user['id']), one=True)
    if order is None:
        abort(404)
    return order


@bp.route('/')
@login_required
def index():
    if g.user['role'] in STAFF_ROLES:
        return redirect(url_for('admin.index'))
    orders = query('SELECT * FROM order_summary WHERE client_id = ? ORDER BY created_at DESC', (g.user['id'],))
    summary = {
        'active': sum(1 for o in orders if o['status'] in ACTIVE_STATUSES),
        'done': sum(1 for o in orders if o['status'] == 'done'),
        'paid': sum(o['paid'] for o in orders),
        'debt': sum(max((o['price'] or 0) - o['paid'], 0) for o in orders if o['status'] != 'cancelled'),
    }
    return render_template('cabinet/index.html', orders=orders, summary=summary)


@bp.route('/orders/new', methods=('GET', 'POST'))
@client_required
def order_new():
    services = query('SELECT id, title, price_from, duration_days FROM services WHERE is_active = 1 ORDER BY title')
    # форма может быть предзаполнена из карточки услуги или из калькулятора стоимости
    form = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()

    if request.method == 'POST':
        errors = []
        title = form.get('title', '').strip()
        description = form.get('description', '').strip()
        service_id = budget = deadline = None
        try:
            service_id = parse_int(form.get('service_id'))
            if service_id and not query('SELECT 1 FROM services WHERE id = ? AND is_active = 1', (service_id,), one=True):
                errors.append('Выбранная услуга недоступна.')
        except ValueError:
            errors.append('Некорректная услуга.')
        try:
            budget = parse_int(form.get('budget'), minimum=0)
        except ValueError:
            errors.append('Бюджет должен быть целым неотрицательным числом.')
        try:
            deadline = parse_date(form.get('deadline'))
            if deadline and deadline <= date.today().isoformat():
                errors.append('Желаемый срок должен быть позже сегодняшней даты.')
        except ValueError:
            errors.append('Некорректная дата.')
        if len(title) < 3:
            errors.append('Укажите название проекта (не короче 3 символов).')
        if len(description) < 20:
            errors.append('Опишите задачу подробнее (не менее 20 символов).')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            order_id = execute('''INSERT INTO orders (client_id, service_id, title, description, budget, deadline)
                                  VALUES (?, ?, ?, ?, ?, ?)''',
                               (g.user['id'], service_id, title, description, budget, deadline))
            execute('INSERT INTO order_status_history (order_id, user_id, old_status, new_status) VALUES (?, ?, NULL, ?)',
                    (order_id, g.user['id'], 'new'))
            flash(f'Заказ №{order_id} оформлен. Менеджер свяжется с вами для уточнения деталей.', 'success')
            return redirect(url_for('cabinet.order', order_id=order_id))
    return render_template('cabinet/order_new.html', services=services, form=form)


@bp.route('/orders/<int:order_id>')
@client_required
def order(order_id):
    order = _get_own_order(order_id)
    review = query('SELECT * FROM reviews WHERE order_id = ?', (order_id,), one=True)
    return render_template('cabinet/order.html', order=order, review=review,
                           comments=order_comments(order_id), history=order_history(order_id),
                           payments=order_payments(order_id))


@bp.route('/orders/<int:order_id>/comment', methods=('POST',))
@client_required
def order_comment(order_id):
    order = _get_own_order(order_id)
    text = request.form.get('text', '').strip()
    if not text:
        flash('Сообщение не может быть пустым.', 'error')
    elif order['status'] == 'cancelled':
        flash('Заказ отменён, переписка закрыта.', 'error')
    else:
        add_comment(order_id, text[:3000])
        flash('Сообщение отправлено.', 'success')
    return redirect(url_for('cabinet.order', order_id=order_id) + '#comments')


@bp.route('/orders/<int:order_id>/cancel', methods=('POST',))
@client_required
def order_cancel(order_id):
    order = _get_own_order(order_id)
    if order['status'] not in ('new', 'discussion'):
        flash('Заказ, который уже находится в работе, можно отменить только через менеджера.', 'error')
    else:
        set_order_status(order_id, order['status'], 'cancelled')
        flash('Заказ отменён.', 'info')
    return redirect(url_for('cabinet.order', order_id=order_id))


@bp.route('/orders/<int:order_id>/decision', methods=('POST',))
@client_required
def order_decision(order_id):
    """Клиент принимает работу или возвращает её на доработку."""
    order = _get_own_order(order_id)
    if order['status'] != 'review':
        flash('Сейчас заказ не ожидает вашей проверки.', 'error')
        return redirect(url_for('cabinet.order', order_id=order_id))

    if request.form.get('action') == 'accept':
        set_order_status(order_id, 'review', 'done')
        add_comment(order_id, 'Работа принята. Спасибо!')
        flash('Работа принята. Будем рады вашему отзыву!', 'success')
    else:
        remarks = request.form.get('remarks', '').strip()
        if len(remarks) < 5:
            flash('Опишите, что нужно доработать.', 'error')
        else:
            set_order_status(order_id, 'review', 'in_progress')
            add_comment(order_id, 'Требуется доработка: ' + remarks[:3000])
            flash('Заказ возвращён на доработку.', 'info')
    return redirect(url_for('cabinet.order', order_id=order_id))


@bp.route('/orders/<int:order_id>/review', methods=('POST',))
@client_required
def order_review(order_id):
    order = _get_own_order(order_id)
    if order['status'] != 'done':
        flash('Отзыв можно оставить только по завершённому заказу.', 'error')
    elif query('SELECT 1 FROM reviews WHERE order_id = ?', (order_id,), one=True):
        flash('Вы уже оставили отзыв по этому заказу.', 'error')
    else:
        try:
            rating = parse_int(request.form.get('rating'))
        except ValueError:
            rating = None
        text = request.form.get('text', '').strip()
        if rating not in range(1, 6):
            flash('Поставьте оценку от 1 до 5.', 'error')
        elif len(text) < 10:
            flash('Текст отзыва должен содержать не менее 10 символов.', 'error')
        else:
            execute('INSERT INTO reviews (user_id, order_id, rating, text) VALUES (?, ?, ?, ?)',
                    (g.user['id'], order_id, rating, text[:2000]))
            flash('Спасибо за отзыв! Он появится на сайте после проверки модератором.', 'success')
    return redirect(url_for('cabinet.order', order_id=order_id))


@bp.route('/profile', methods=('GET', 'POST'))
@login_required
def profile():
    if request.method == 'POST':
        if request.form.get('action') == 'password':
            current = request.form.get('current_password', '')
            new = request.form.get('new_password', '')
            if not check_password_hash(g.user['password_hash'], current):
                flash('Текущий пароль указан неверно.', 'error')
            elif len(new) < 6:
                flash('Новый пароль должен содержать не менее 6 символов.', 'error')
            elif new != request.form.get('new_password2', ''):
                flash('Новые пароли не совпадают.', 'error')
            else:
                execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new), g.user['id']))
                flash('Пароль изменён.', 'success')
        else:
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            if len(name) < 2:
                flash('Укажите имя.', 'error')
            elif not EMAIL_RE.match(email):
                flash('Некорректный e-mail.', 'error')
            elif query('SELECT 1 FROM users WHERE email = ? AND id != ?', (email, g.user['id']), one=True):
                flash('Этот e-mail уже используется другим пользователем.', 'error')
            else:
                execute('UPDATE users SET name = ?, email = ?, phone = ? WHERE id = ?',
                        (name, email, phone or None, g.user['id']))
                flash('Данные профиля сохранены.', 'success')
        return redirect(url_for('cabinet.profile'))
    stats = query('''SELECT COUNT(*) AS total, SUM(status = 'done') AS done
                     FROM orders WHERE client_id = ? OR designer_id = ?''', (g.user['id'], g.user['id']), one=True)
    return render_template('cabinet/profile.html', stats=stats)
