"""Сборка статической версии публичной части сайта для GitHub Pages.

GitHub Pages отдаёт только статические файлы и не запускает Python, поэтому
на Pages публикуется копия публичных страниц (главная, услуги, портфолио,
калькулятор, о студии, контакты). Регистрация, вход, личный кабинет,
оформление заказов, обратная связь и панель управления работают при
локальном запуске проекта (python run.py).

Запуск:
    python build_pages.py
    python build_pages.py --base /webstudio --repo https://github.com/Mr-Lokan/webstudio

Результат - папка docs/ (в настройках GitHub Pages: ветка main, папка /docs).
"""
import argparse
import os
import re
import shutil

from config import BASE_DIR, Config
from studio import create_app
from studio.db import query

BANNER_JS = r"""/* WebCraft - статическая версия для GitHub Pages */
(function () {
  'use strict';
  var root = document.documentElement.getAttribute('data-site-root') || '';
  var localPage = root + '/local/';

  var bar = document.createElement('div');
  bar.className = 'static-bar';
  bar.innerHTML = 'Демо-версия на GitHub Pages: вход, личный кабинет, заказы и CRM работают при ' +
    '<a href="' + localPage + '">локальном запуске проекта</a>.';
  document.body.insertBefore(bar, document.body.firstChild);

  function notice(text) {
    var box = document.querySelector('.flashes');
    if (!box) { box = document.createElement('div'); box.className = 'flashes'; document.body.appendChild(box); }
    var alert = document.createElement('div');
    alert.className = 'alert alert--warning';
    alert.setAttribute('role', 'alert');
    alert.innerHTML = '<span>' + text + '</span><button type="button" class="alert__close" aria-label="Закрыть">&times;</button>';
    alert.querySelector('.alert__close').addEventListener('click', function () { alert.remove(); });
    box.appendChild(alert);
    setTimeout(function () { alert.remove(); }, 9000);
  }

  document.querySelectorAll('form[method=post], form[method=POST]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      notice('В статической версии на GitHub Pages формы не отправляются. ' +
        '<a href="' + localPage + '">Как запустить полную версию</a>.');
    });
  });
})();
"""

BANNER_CSS = """
/* Статическая версия для GitHub Pages */
.static-bar { background: #2d2654; color: #fff; font-size: 14px; text-align: center; padding: 8px 16px; }
.static-bar a { color: #c9c2ff; text-decoration: underline; }
.local-steps { margin: 0 0 8px; padding-left: 22px; line-height: 1.7; }
.local-steps code, .local-table code { background: #f0efff; border-radius: 6px; padding: 2px 6px; font-size: 14px; }
.local-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 15px; }
.local-table th, .local-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
"""

LOCAL_PAGE = """{% extends 'base.html' %}
{% block title %}Полная версия сайта - WebCraft{% endblock %}
{% block content %}
<section class="page-head">
  <div class="container">
    <h1>Полная версия работает при локальном запуске</h1>
    <p class="lead">На GitHub Pages размещена статическая копия публичной части сайта: услуги, портфолио,
      калькулятор и информация о студии. Регистрация, вход, личный кабинет клиента, оформление заказов,
      обратная связь и панель управления (CRM) требуют сервера с Python и базой данных SQLite.</p>
  </div>
</section>
<section class="section section--tight">
  <div class="container grid grid--2">
    <div class="card">
      <h2>Как запустить</h2>
      <ol class="local-steps">
        <li>Скачайте исходный код: <a href="{{ repo }}">{{ repo_short }}</a> → Code → Download ZIP.</li>
        <li>Установите Python 3.10 или новее.</li>
        <li>В папке проекта выполните <code>pip install -r requirements.txt</code>.</li>
        <li>Запустите <code>python run.py</code> (или <code>start.bat</code> в Windows).</li>
        <li>Откройте <code>http://127.0.0.1:5000</code>.</li>
      </ol>
      <p class="muted small">База данных с демонстрационными данными создаётся автоматически при первом запуске.</p>
    </div>
    <div class="card">
      <h2>Демонстрационные учётные записи</h2>
      <table class="local-table">
        <tr><th>Роль</th><th>E-mail</th><th>Пароль</th></tr>
        <tr><td>Администратор</td><td><code>admin@webcraft.ru</code></td><td><code>admin123</code></td></tr>
        <tr><td>Дизайнер</td><td><code>anna@webcraft.ru</code></td><td><code>designer123</code></td></tr>
        <tr><td>Клиент</td><td><code>client@mail.ru</code></td><td><code>client123</code></td></tr>
      </table>
    </div>
  </div>
  <div class="container">
    <div class="btn-row" style="margin-top: 24px">
      <a class="btn btn--primary" href="{{ repo }}">Исходный код на GitHub</a>
      <a class="btn btn--ghost" href="{{ url_for('main.index') }}">На главную</a>
    </div>
  </div>
</section>
{% endblock %}
"""


def make_config(db_path):
    class BuildConfig(Config):
        DATABASE = db_path
        INSTANCE_DIR = os.path.dirname(db_path)
    return BuildConfig


def collect_pages(app):
    """Список адресов публичных страниц: (адрес запроса, путь файла в docs)."""
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


def rewrite(html, base, repo):
    q = re.escape(base)
    # фильтры по категориям: ?category=slug -> /category/slug/
    html = re.sub(rf'"{q}/(services|portfolio)\?category=([\w-]+)"', rf'"{base}/\1/category/\2/"', html)
    # личный кабинет и панель управления есть только в полной версии
    html = re.sub(rf'"{q}/(?:cabinet|admin)[^"]*"', f'"{base}/local/"', html)
    # адреса страниц -> папки с index.html (без лишнего перенаправления на Pages)
    html = re.sub(rf'"({q}(?:/(?!static/)[^"?#.]*[^"?#./])?)"', r'"\1/"', html)
    # корень сайта для скрипта статической версии
    html = html.replace('<html lang="ru">', f'<html lang="ru" data-site-root="{base}">', 1)
    html = html.replace('</body>', f'<script src="{base}/static/js/static-pages.js"></script>\n</body>', 1)
    return html


def save(out_dir, rel, html):
    path = os.path.join(out_dir, rel, 'index.html') if not rel.endswith('.html') else os.path.join(out_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='/webstudio', help='путь сайта на Pages: /<имя репозитория> или пусто')
    parser.add_argument('--repo', default='https://github.com/Mr-Lokan/webstudio', help='ссылка на репозиторий')
    parser.add_argument('--db', default=Config.DATABASE, help='база данных SQLite (создаётся, если её нет)')
    parser.add_argument('--out', default=os.path.join(BASE_DIR, 'docs'), help='папка результата')
    args = parser.parse_args()

    base = args.base.rstrip('/')
    app = create_app(make_config(os.path.abspath(args.db)))
    client = app.test_client()
    base_url = 'http://localhost' + base + '/'

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out)

    count = 0
    for url, rel in collect_pages(app):
        resp = client.get(url, base_url=base_url)
        if resp.status_code != 200:
            raise SystemExit(f'{url}: HTTP {resp.status_code}')
        save(args.out, rel, rewrite(resp.get_data(as_text=True), base, args.repo))
        count += 1

    # страница «полная версия работает локально»
    from flask import render_template_string
    with app.test_request_context('/local', base_url=base_url):
        app.preprocess_request()
        html = render_template_string(LOCAL_PAGE, repo=args.repo, repo_short=args.repo.split('://', 1)[-1])
    save(args.out, 'local', rewrite(html, base, args.repo))

    # 404 для GitHub Pages
    resp = client.get('/__not_found__', base_url=base_url)
    save(args.out, '404.html', rewrite(resp.get_data(as_text=True), base, args.repo))

    # статика: стили, скрипты, изображения
    static_out = os.path.join(args.out, 'static')
    shutil.copytree(os.path.join(BASE_DIR, 'studio', 'static'), static_out)
    with open(os.path.join(static_out, 'js', 'static-pages.js'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(BANNER_JS)
    with open(os.path.join(static_out, 'css', 'style.css'), 'a', encoding='utf-8', newline='\n') as f:
        f.write(BANNER_CSS)
    open(os.path.join(args.out, '.nojekyll'), 'w').close()

    print(f'Готово: {count + 2} страниц в {args.out}')


if __name__ == '__main__':
    main()
