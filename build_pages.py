"""Сборка сайта для GitHub Pages.

GitHub Pages отдаёт только статические файлы и не запускает Python. Поэтому:
  1. публичные страницы заранее собираются в статический HTML (открываются сразу);
  2. то же Flask-приложение упаковывается в docs/pyapp/app.zip и запускается
     прямо в браузере посетителя через Pyodide (Python в WebAssembly), так что
     регистрация, вход, личный кабинет и панель управления тоже работают.
     Данные каждого посетителя хранятся в его браузере (IndexedDB).

Запуск:
    python build_pages.py
    python build_pages.py --base /webstudio --db instance/studio.db

Результат - папка docs/ (в настройках GitHub Pages: ветка main, папка /docs).
Файлы Pyodide (docs/pyodide) при пересборке сохраняются; если их нет,
они скачиваются с cdn.jsdelivr.net.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import urllib.request
import zipfile

from config import BASE_DIR, Config
from studio import create_app
from studio.db import query

PAGES_DIR = os.path.join(BASE_DIR, 'pages')
PYODIDE_VERSION = '0.27.2'
PYODIDE_FILES = [
    'pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json',
    'sqlite3-1.0.0-py2.py3-none-any.whl', 'hashlib-1.0.0-py2.py3-none-any.whl', 'openssl-1.1.1w.zip',
    'MarkupSafe-2.1.5-cp312-cp312-pyodide_2024_0_wasm32.whl',
]


def make_config(db_path):
    class BuildConfig(Config):
        DATABASE = db_path
        INSTANCE_DIR = os.path.dirname(db_path)
    return BuildConfig


def collect_pages(app):
    """Список публичных страниц: (адрес запроса, путь в docs)."""
    with app.app_context():
        service_ids = [r['id'] for r in query('SELECT id FROM services WHERE is_active = 1')]
        work_ids = [r['id'] for r in query('SELECT id FROM portfolio WHERE is_published = 1')]
        categories = [r['slug'] for r in query('SELECT slug FROM categories')]

    pages = [('/', ''), ('/services', 'services'), ('/portfolio', 'portfolio'), ('/about', 'about'),
             ('/calculator', 'calculator'), ('/contacts', 'contacts'), ('/login', 'login'),
             ('/register', 'register')]
    for slug in categories:
        pages.append((f'/services?category={slug}', f'services/category/{slug}'))
        pages.append((f'/portfolio?category={slug}', f'portfolio/category/{slug}'))
    pages += [(f'/services/{i}', f'services/{i}') for i in service_ids]
    pages += [(f'/portfolio/{i}', f'portfolio/{i}') for i in work_ids]
    return pages


def rewrite(html, base, version, page=None):
    q = re.escape(base)
    # фильтры по категориям: ?category=slug -> /category/slug/
    html = re.sub(rf'"{q}/(services|portfolio)\?category=([\w-]+)"', rf'"{base}/\1/category/\2/"', html)
    # адреса страниц -> папки с index.html (без лишнего перенаправления на Pages)
    html = re.sub(rf'"({q}(?:/(?!static/)[^"?#.]*[^"?#./])?)"', r'"\1/"', html)
    attrs = f' data-site-root="{base}"' + (f' data-page="{page}"' if page else '')
    html = html.replace('<html lang="ru">', f'<html lang="ru"{attrs}>', 1)
    html = html.replace('</body>', f'<script src="{base}/pyapp/runtime.js?v={version}"></script>\n</body>', 1)
    return html


def save(out_dir, rel, html):
    path = os.path.join(out_dir, rel) if rel.endswith('.html') else os.path.join(out_dir, rel, 'index.html')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)


def clean_output(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        if name == 'pyodide':
            continue
        path = os.path.join(out_dir, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)


def ensure_pyodide(out_dir):
    target = os.path.join(out_dir, 'pyodide')
    os.makedirs(target, exist_ok=True)
    for name in PYODIDE_FILES:
        path = os.path.join(target, name)
        if not os.path.exists(path):
            url = f'https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/{name}'
            print('скачиваю', url)
            with urllib.request.urlopen(url, timeout=120) as r, open(path, 'wb') as f:
                shutil.copyfileobj(r, f)


def build_app_zip(db_path):
    """Архив для Pyodide: исходники приложения, начальная база и пакеты Flask."""
    buf = io.BytesIO()

    def add(z, name, data):
        # фиксированная дата: одинаковые исходники дают одинаковый архив
        info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, data)

    def read(path):
        with open(path, 'rb') as f:
            return f.read()

    with zipfile.ZipFile(buf, 'w') as z:
        add(z, 'config.py', read(os.path.join(BASE_DIR, 'config.py')))
        add(z, 'webapp.py', read(os.path.join(PAGES_DIR, 'webapp.py')))
        studio = os.path.join(BASE_DIR, 'studio')
        for root, dirs, files in os.walk(studio):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            rel_root = os.path.relpath(root, BASE_DIR).replace(os.sep, '/')
            if rel_root.startswith('studio/static') and not rel_root.startswith('studio/static/uploads'):
                continue  # стили и скрипты отдаёт сам GitHub Pages
            for name in sorted(files):
                if not name.endswith('.pyc'):
                    add(z, f'{rel_root}/{name}', read(os.path.join(root, name)))
        # начальная база в виде SQL: из неё в браузере создаётся studio.db
        src = sqlite3.connect(db_path)
        mem = sqlite3.connect(':memory:')
        src.backup(mem)
        src.close()
        add(z, 'initial.sql', '\n'.join(mem.iterdump()).encode('utf-8'))
        mem.close()
        wheels = os.path.join(PAGES_DIR, 'wheels')
        for wheel in sorted(os.listdir(wheels)):
            with zipfile.ZipFile(os.path.join(wheels, wheel)) as w:
                for item in w.infolist():
                    if not item.is_dir():
                        add(z, 'site-packages/' + item.filename, w.read(item))
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='/webstudio', help='путь сайта на Pages: /<имя репозитория> или пусто')
    parser.add_argument('--db', default=Config.DATABASE, help='база данных SQLite (создаётся, если её нет)')
    parser.add_argument('--out', default=os.path.join(BASE_DIR, 'docs'), help='папка результата')
    args = parser.parse_args()

    base = args.base.rstrip('/')
    db_path = os.path.abspath(args.db)
    app = create_app(make_config(db_path))
    client = app.test_client()
    base_url = 'http://localhost' + base + '/'

    clean_output(args.out)
    ensure_pyodide(args.out)

    app_zip = build_app_zip(db_path)
    version = hashlib.sha256(app_zip + open(os.path.join(PAGES_DIR, 'runtime.js'), 'rb').read()).hexdigest()[:10]
    os.makedirs(os.path.join(args.out, 'pyapp'))
    with open(os.path.join(args.out, 'pyapp', 'app.zip'), 'wb') as f:
        f.write(app_zip)

    uploads = sorted(os.listdir(os.path.join(BASE_DIR, 'studio', 'static', 'uploads')))
    with open(os.path.join(PAGES_DIR, 'runtime.js'), encoding='utf-8') as f:
        runtime = f.read().replace('__VERSION__', version).replace('__SHIPPED_UPLOADS__', json.dumps(uploads))
    with open(os.path.join(args.out, 'pyapp', 'runtime.js'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(runtime)

    count = 0
    for url, rel in collect_pages(app):
        resp = client.get(url, base_url=base_url)
        if resp.status_code != 200:
            raise SystemExit(f'{url}: HTTP {resp.status_code}')
        save(args.out, rel, rewrite(resp.get_data(as_text=True), base, version))
        count += 1

    # 404.html: GitHub Pages отдаёт его для всех адресов, которых нет в сборке
    # (личный кабинет, панель управления) - их показывает приложение в браузере
    resp = client.get('/__not_found__', base_url=base_url)
    save(args.out, '404.html', rewrite(resp.get_data(as_text=True), base, version, page='404'))

    shutil.copytree(os.path.join(BASE_DIR, 'studio', 'static'), os.path.join(args.out, 'static'))
    open(os.path.join(args.out, '.nojekyll'), 'w').close()

    print(f'Готово: {count + 1} страниц, app.zip {len(app_zip) // 1024} КБ, версия {version}')


if __name__ == '__main__':
    main()
