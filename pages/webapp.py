"""Запуск Flask-приложения WebCraft внутри браузера (Pyodide) для GitHub Pages.

Браузерный скрипт pages/runtime.js загружает Pyodide, распаковывает приложение
в /app, подключает постоянную папку /data (IndexedDB) и передаёт сюда запросы.
Ответы формирует то же Flask-приложение, что и при локальном запуске.
"""
import json
import os
import shutil
from urllib.parse import urlsplit

APP_DIR = '/app'
DATA_DIR = '/data'
DB_PATH = DATA_DIR + '/studio.db'
UPLOADS = DATA_DIR + '/uploads'

client = None
BASE = ''
BASE_URL = 'http://localhost/'


def _prepare_data():
    os.makedirs(UPLOADS, exist_ok=True)
    shipped = os.path.join(APP_DIR, 'studio', 'static', 'uploads')
    for name in os.listdir(shipped):
        target = os.path.join(UPLOADS, name)
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(shipped, name), target)
    initial = os.path.join(APP_DIR, 'initial.sql')
    if not os.path.exists(DB_PATH) and os.path.exists(initial):
        import sqlite3
        with open(initial, encoding='utf-8') as f:
            script = f.read()
        con = sqlite3.connect(DB_PATH)
        con.executescript(script)
        con.close()


def boot(base, session_cookie=None):
    """Создаёт приложение. base - путь сайта на Pages, например /webstudio."""
    global client, BASE, BASE_URL
    _prepare_data()

    from config import Config
    from studio import create_app

    class BrowserConfig(Config):
        INSTANCE_DIR = DATA_DIR
        DATABASE = DB_PATH
        UPLOAD_FOLDER = UPLOADS

    app = create_app(BrowserConfig)
    client = app.test_client()
    BASE = base
    BASE_URL = 'http://localhost' + base + '/'
    if session_cookie:
        client.set_cookie('session', session_cookie)


def handle(method, url, content_type=None, body=None):
    """Выполняет запрос к приложению и возвращает ответ в виде JSON.

    url - адрес внутри приложения (без корня сайта), например /cabinet/.
    Перенаправления обрабатываются здесь: адреса без корня сайта (например,
    параметр next после входа) считаются адресами внутри приложения.
    """
    data = None
    if body is not None:
        data = body.to_bytes() if hasattr(body, 'to_bytes') else bytes(body)
    for _ in range(10):
        kwargs = {'data': data, 'content_type': content_type} if data is not None else {}
        resp = client.open(url, method=method, base_url=BASE_URL, **kwargs)
        if resp.status_code not in (301, 302, 303, 307, 308) or not resp.location:
            break
        loc = urlsplit(resp.location)
        if loc.netloc and loc.netloc != 'localhost':
            break
        path = loc.path or '/'
        if path == BASE or path.startswith(BASE + '/'):
            path = path[len(BASE):] or '/'
        url = path + ('?' + loc.query if loc.query else '')
        if resp.status_code not in (307, 308):
            method, data = 'GET', None
    final = BASE + url if url != '/' else BASE + '/'
    cookie = client.get_cookie('session')
    return json.dumps({
        'status': resp.status_code,
        'url': final,
        'type': resp.mimetype or '',
        'disposition': resp.headers.get('Content-Disposition', ''),
        'body': resp.get_data(as_text=True),
        'session': cookie.value if cookie else None,
    })


def read_upload(name):
    """Возвращает загруженное через панель управления изображение (bytes) или None."""
    path = os.path.join(UPLOADS, os.path.basename(name))
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as f:
        return f.read()


def reset():
    """Удаляет демо-данные этого браузера: при следующем запуске база создастся заново."""
    for name in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
