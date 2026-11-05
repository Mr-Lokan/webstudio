import sqlite3

import click
from flask import current_app, g


def _lower(value):
    return value.lower() if isinstance(value, str) else value


def get_db():
    """Возвращает соединение с БД, открытое для текущего запроса."""
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        # встроенная lower() в SQLite не работает с кириллицей, поэтому регистрируем свою
        g.db.create_function('py_lower', 1, _lower, deterministic=True)
    return g.db


def close_db(e=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    """Выполняет SELECT-запрос и возвращает список строк (или одну строку при one=True)."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """Выполняет изменяющий запрос (INSERT/UPDATE/DELETE) и фиксирует транзакцию."""
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def init_db():
    conn = get_db()
    with current_app.open_resource('schema.sql') as f:
        conn.executescript(f.read().decode('utf-8'))


@click.command('init-db')
def init_db_command():
    """Пересоздать базу данных и заполнить её демонстрационными данными."""
    init_db()
    from .seed import seed_db
    seed_db()
    click.echo('База данных создана и заполнена демонстрационными данными.')


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
