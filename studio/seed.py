"""Заполнение базы данных демонстрационными данными."""
import os
import random
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from flask import current_app
from werkzeug.security import generate_password_hash

from .db import get_db

rnd = random.Random(2026)


def _ts(days_ago, hour=None):
    dt = datetime.now() - timedelta(days=days_ago)
    dt = dt.replace(hour=hour if hour is not None else rnd.randint(9, 19), minute=rnd.randint(0, 59), second=0)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _day(days_from_now):
    return (datetime.now() + timedelta(days=days_from_now)).strftime('%Y-%m-%d')


# ------------------------------------------------------------------ обложки портфолио (SVG)

def _cover_svg(title, subtitle, c1, c2, layout):
    t, s = escape(title), escape(subtitle)
    font = 'font-family="Segoe UI, Arial, sans-serif"'
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>
<linearGradient id="h" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>
<rect width="1200" height="800" fill="url(#g)"/>
<circle cx="1080" cy="110" r="230" fill="#fff" opacity=".08"/><circle cx="90" cy="760" r="260" fill="#fff" opacity=".07"/>'''

    if layout == 'brand':
        body = f'''<g transform="translate(600 330)">
<circle r="150" fill="#fff" opacity=".95"/><circle r="110" fill="url(#h)"/>
<path d="M-55 25 Q0 -95 55 25 Q0 -15 -55 25Z" fill="#fff"/>
</g>
<text x="600" y="590" text-anchor="middle" {font} font-size="64" font-weight="700" fill="#fff">{t}</text>
<text x="600" y="645" text-anchor="middle" {font} font-size="28" fill="#fff" opacity=".85">{s}</text>
<g transform="translate(390 690)"><rect width="90" height="40" rx="8" fill="#fff"/><rect x="110" width="90" height="40" rx="8" fill="#fff" opacity=".7"/>
<rect x="220" width="90" height="40" rx="8" fill="{c1}" stroke="#fff" stroke-width="3"/><rect x="330" width="90" height="40" rx="8" fill="#1d2033"/></g>'''
    elif layout == 'app':
        phones = ''
        for i, x in enumerate((300, 520, 740)):
            y = 150 if i == 1 else 190
            phones += f'''<g transform="translate({x} {y})"><rect width="180" height="370" rx="28" fill="#1d2033"/>
<rect x="9" y="9" width="162" height="352" rx="21" fill="#fff"/>
<rect x="24" y="34" width="70" height="10" rx="5" fill="#c9cdd9"/>
<rect x="24" y="60" width="132" height="{90 + i * 20}" rx="14" fill="url(#h)"/>
<rect x="24" y="{170 + i * 20}" width="132" height="12" rx="6" fill="#e3e6ef"/>
<rect x="24" y="{192 + i * 20}" width="100" height="12" rx="6" fill="#e3e6ef"/>
<rect x="24" y="{220 + i * 20}" width="60" height="44" rx="10" fill="{c1}" opacity=".25"/>
<rect x="96" y="{220 + i * 20}" width="60" height="44" rx="10" fill="{c2}" opacity=".25"/>
<rect x="44" y="330" width="92" height="8" rx="4" fill="#1d2033"/></g>'''
        body = phones + f'''<text x="600" y="640" text-anchor="middle" {font} font-size="54" font-weight="700" fill="#fff">{t}</text>
<text x="600" y="690" text-anchor="middle" {font} font-size="26" fill="#fff" opacity=".85">{s}</text>'''
    else:
        if layout == 'shop':
            content = ''.join(
                f'''<rect x="{40 + i * 210}" y="230" width="190" height="150" rx="12" fill="{c1 if i % 2 else c2}" opacity=".18"/>
<circle cx="{135 + i * 210}" cy="305" r="42" fill="{c1 if i % 2 else c2}" opacity=".55"/>
<rect x="{40 + i * 210}" y="395" width="140" height="12" rx="6" fill="#1d2033" opacity=".75"/>
<rect x="{40 + i * 210}" y="418" width="90" height="12" rx="6" fill="{c1}"/>
<rect x="{40 + i * 210}" y="445" width="190" height="36" rx="18" fill="url(#h)"/>''' for i in range(4))
            content += f'<text x="40" y="190" {font} font-size="38" font-weight="700" fill="#1d2033">{t}</text>'
        elif layout == 'dashboard':
            bars = ''.join(f'<rect x="{360 + i * 52}" y="{470 - h}" width="34" height="{h}" rx="6" fill="url(#h)"/>'
                           for i, h in enumerate((90, 140, 110, 190, 160, 220, 180, 240, 200)))
            content = f'''<rect x="0" y="44" width="200" height="516" fill="#1d2033"/>
<rect x="30" y="80" width="120" height="14" rx="7" fill="#fff" opacity=".9"/>
{''.join(f'<rect x="30" y="{130 + i * 40}" width="{140 - i * 12}" height="10" rx="5" fill="#fff" opacity=".35"/>' for i in range(6))}
<text x="240" y="115" {font} font-size="30" font-weight="700" fill="#1d2033">{t}</text>
{''.join(f'<rect x="{240 + i * 215}" y="140" width="195" height="80" rx="12" fill="{c1 if i == 0 else "#f1f2f8"}"/><rect x="{258 + i * 215}" y="160" width="80" height="10" rx="5" fill="{"#fff" if i == 0 else "#c9cdd9"}"/><rect x="{258 + i * 215}" y="185" width="120" height="18" rx="6" fill="{"#fff" if i == 0 else "#1d2033"}" opacity=".85"/>' for i in range(3))}
<rect x="240" y="240" width="620" height="290" rx="12" fill="#f7f8fc"/>{bars}'''
        else:  # landing / corporate
            content = f'''<text x="40" y="200" {font} font-size="46" font-weight="700" fill="#1d2033">{t}</text>
<text x="40" y="245" {font} font-size="22" fill="#6b7089">{s}</text>
<rect x="40" y="280" width="320" height="14" rx="7" fill="#e3e6ef"/><rect x="40" y="306" width="260" height="14" rx="7" fill="#e3e6ef"/>
<rect x="40" y="350" width="180" height="52" rx="26" fill="url(#h)"/><rect x="236" y="350" width="150" height="52" rx="26" fill="none" stroke="{c1}" stroke-width="3"/>
<rect x="520" y="120" width="340" height="300" rx="20" fill="url(#h)"/>
<circle cx="690" cy="270" r="80" fill="#fff" opacity=".3"/><circle cx="760" cy="200" r="36" fill="#fff" opacity=".45"/>
{''.join(f'<rect x="{40 + i * 280}" y="450" width="260" height="80" rx="12" fill="#f3f4f9"/><circle cx="{80 + i * 280}" cy="490" r="18" fill="{c1}" opacity=".7"/><rect x="{110 + i * 280}" y="478" width="140" height="10" rx="5" fill="#c9cdd9"/><rect x="{110 + i * 280}" y="496" width="100" height="10" rx="5" fill="#e3e6ef"/>' for i in range(3))}'''
        body = f'''<g transform="translate(150 110)">
<rect width="900" height="560" rx="18" fill="#fff"/>
<path d="M18 0H882A18 18 0 0 1 900 18V44H0V18A18 18 0 0 1 18 0Z" fill="#eef0f7"/>
<circle cx="26" cy="22" r="7" fill="#ff5f57"/><circle cx="50" cy="22" r="7" fill="#febc2e"/><circle cx="74" cy="22" r="7" fill="#28c840"/>
<rect x="250" y="12" width="400" height="20" rx="10" fill="#fff"/>
{'' if layout == 'dashboard' else f'<rect x="40" y="72" width="110" height="18" rx="9" fill="url(#h)"/>' + "".join(f'<rect x="{560 + i * 80}" y="76" width="60" height="10" rx="5" fill="#c9cdd9"/>' for i in range(4))}
{content}
</g>'''
    return head + body + '</svg>'


# ------------------------------------------------------------------ данные

CATEGORIES = [
    ('Веб-сайты', 'sites', 'Лендинги, корпоративные сайты и сайты-визитки'),
    ('Интернет-магазины', 'shops', 'E-commerce проекты любой сложности'),
    ('UI/UX дизайн', 'ui-ux', 'Интерфейсы веб-сервисов и мобильных приложений'),
    ('Брендинг', 'branding', 'Логотипы, фирменный стиль, брендбуки'),
    ('Продвижение и поддержка', 'support', 'SEO, контекстная реклама, техническая поддержка'),
]

SERVICES = [
    ('sites', 'Лендинг', 'Одностраничный продающий сайт под рекламную кампанию',
     'Проектируем структуру, пишем продающие тексты, разрабатываем уникальный дизайн и адаптивную вёрстку.\n\n'
     'В стоимость входит: прототип, дизайн-макет для ПК и смартфонов, вёрстка, подключение формы заявок '
     'и систем аналитики, публикация на хостинге.', 25000, 10),
    ('sites', 'Корпоративный сайт', 'Многостраничный сайт компании с системой управления',
     'Сайт компании до 15 страниц: о компании, услуги, проекты, новости, контакты.\n\n'
     'Разрабатываем фирменный дизайн, подключаем систему управления содержимым, '
     'обучаем сотрудников клиента работе с сайтом.', 70000, 30),
    ('sites', 'Редизайн сайта', 'Обновление дизайна и юзабилити существующего сайта',
     'Анализируем текущий сайт и поведение посетителей, выявляем слабые места и создаём новый дизайн '
     'с сохранением наработанных позиций в поисковых системах.', 40000, 21),
    ('shops', 'Интернет-магазин', 'Магазин с каталогом, корзиной и онлайн-оплатой',
     'Каталог с фильтрами, карточки товаров, корзина, личный кабинет покупателя, '
     'подключение онлайн-оплаты и служб доставки, интеграция с 1С.', 120000, 45),
    ('ui-ux', 'Дизайн мобильного приложения', 'UX-исследование и дизайн интерфейсов iOS и Android',
     'Проводим интервью с пользователями, строим пользовательские сценарии, создаём интерактивный '
     'прототип и итоговый дизайн с UI-китом для разработчиков.', 80000, 30),
    ('ui-ux', 'UX-аудит', 'Экспертная оценка удобства сайта или приложения',
     'Проверяем интерфейс по 100+ критериям юзабилити, анализируем данные веб-аналитики и записи сессий. '
     'Результат — отчёт с приоритизированным списком рекомендаций.', 20000, 7),
    ('branding', 'Логотип', 'Разработка логотипа в трёх вариантах',
     'Изучаем бизнес и конкурентов, предлагаем 3 концепции логотипа, дорабатываем выбранную. '
     'Передаём исходники во всех необходимых форматах.', 15000, 7),
    ('branding', 'Фирменный стиль', 'Логотип, цвета, шрифты, носители и брендбук',
     'Полный комплекс айдентики: логотип, палитра, типографика, визитки, бланки, '
     'шаблоны для соцсетей и брендбук с правилами использования.', 45000, 20),
    ('support', 'SEO-продвижение', 'Вывод сайта в топ поисковых систем',
     'Техническая оптимизация, сбор семантического ядра, оптимизация контента, '
     'ежемесячная отчётность о позициях и трафике.', 25000, 30),
    ('support', 'Техническая поддержка', 'Обновления, резервное копирование и доработки сайта',
     'Ежемесячное обслуживание сайта: обновление ПО, резервные копии, мониторинг доступности, '
     'до 5 часов мелких доработок в месяц.', 10000, 30),
]

USERS = [
    # name, email, phone, role, position, bio, password
    ('Петров Иван', 'admin@webcraft.ru', '+7 (900) 100-00-01', 'admin', 'Руководитель студии',
     'Основатель студии, 12 лет в веб-разработке. Отвечает за стратегию и работу с ключевыми клиентами.', 'admin123'),
    ('Смирнова Анна', 'anna@webcraft.ru', '+7 (900) 100-00-02', 'designer', 'Ведущий UI/UX-дизайнер',
     'Проектирует интерфейсы веб-сервисов и мобильных приложений, проводит UX-исследования.', 'designer123'),
    ('Козлов Дмитрий', 'dmitry@webcraft.ru', '+7 (900) 100-00-03', 'designer', 'Веб-дизайнер, верстальщик',
     'Создаёт корпоративные сайты и интернет-магазины, отвечает за адаптивную вёрстку.', 'designer123'),
    ('Волкова Мария', 'maria@webcraft.ru', '+7 (900) 100-00-04', 'designer', 'Графический дизайнер',
     'Специализируется на брендинге: логотипы, фирменный стиль, полиграфия.', 'designer123'),
    ('Иванов Сергей', 'client@mail.ru', '+7 (912) 345-67-89', 'client', None, None, 'client123'),
    ('Кузнецова Ольга', 'olga.k@mail.ru', '+7 (913) 222-33-44', 'client', None, None, 'client123'),
    ('Морозов Алексей', 'morozov@technomarket.ru', '+7 (914) 555-66-77', 'client', None, None, 'client123'),
    ('Новикова Екатерина', 'ekaterina.n@yandex.ru', '+7 (915) 888-99-00', 'client', None, None, 'client123'),
    ('Соколов Павел', 'p.sokolov@gmail.com', '+7 (916) 123-45-67', 'client', None, None, 'client123'),
]

# client_email, service_title, designer_email, title, description, budget, price, deadline_offset, status, days_ago
ORDERS = [
    ('morozov@technomarket.ru', 'Интернет-магазин', 'dmitry@webcraft.ru', 'Интернет-магазин «ТехноМаркет»',
     'Нужен интернет-магазин электроники на 3000 товаров с фильтрами, сравнением товаров, онлайн-оплатой '
     'и выгрузкой из 1С.', 150000, 165000, -60, 'done', 170),
    ('client@mail.ru', 'Лендинг', 'anna@webcraft.ru', 'Лендинг кофейни «Бодрое утро»',
     'Одностраничный сайт для кофейни: меню, акции, карта, форма бронирования столика.', 30000, 32000, -95, 'done', 140),
    ('olga.k@mail.ru', 'Фирменный стиль', 'maria@webcraft.ru', 'Фирменный стиль эко-фермы «Зелёный луг»',
     'Логотип, фирменные цвета, упаковка для молочной продукции и шаблоны для соцсетей.', 50000, 48000, -40, 'done', 120),
    ('ekaterina.n@yandex.ru', 'Корпоративный сайт', 'dmitry@webcraft.ru', 'Сайт стоматологии «Улыбка»',
     'Корпоративный сайт клиники: услуги и цены, врачи, онлайн-запись, отзывы пациентов.', 80000, 85000, -10, 'done', 95),
    ('p.sokolov@gmail.com', 'Дизайн мобильного приложения', 'anna@webcraft.ru', 'Приложение FitLife',
     'Дизайн мобильного приложения для фитнес-клуба: расписание, запись на тренировки, абонементы, прогресс.',
     90000, 95000, 12, 'review', 70),
    ('client@mail.ru', 'SEO-продвижение', 'dmitry@webcraft.ru', 'SEO-продвижение сайта кофейни',
     'Хотим, чтобы сайт кофейни находился по запросам «кофейня рядом», «завтраки в центре».', 25000, 25000, 20,
     'in_progress', 45),
    ('morozov@technomarket.ru', 'UX-аудит', 'anna@webcraft.ru', 'UX-аудит корзины «ТехноМаркет»',
     'Много брошенных корзин, нужно найти проблемы в оформлении заказа.', 20000, 22000, 5, 'in_progress', 30),
    ('olga.k@mail.ru', 'Лендинг', 'maria@webcraft.ru', 'Промо-страница сыров «Зелёный луг»',
     'Лендинг под новую линейку фермерских сыров, нужен к ярмарке.', 35000, 30000, 25, 'discussion', 14),
    ('ekaterina.n@yandex.ru', 'Техническая поддержка', None, 'Поддержка сайта стоматологии',
     'Требуется ежемесячная поддержка сайта: обновления, резервные копии и мелкие правки.', 10000, None, None,
     'new', 3),
    ('p.sokolov@gmail.com', 'Логотип', None, 'Логотип для сети спортзалов',
     'Нужен лаконичный логотип для сети спортзалов «Сила», варианты в тёмной и светлой теме.', 15000, None, 30,
     'new', 1),
    ('client@mail.ru', 'Редизайн сайта', None, 'Редизайн старого сайта пекарни',
     'Сайт пекарни сделан 8 лет назад, нужен современный дизайн. Проект отложили.', 40000, None, None,
     'cancelled', 60),
    ('morozov@technomarket.ru', 'Техническая поддержка', 'dmitry@webcraft.ru', 'Техподдержка «ТехноМаркет»',
     'Обслуживание интернет-магазина после запуска.', 10000, 12000, -3, 'in_progress', 75),
]

# (автор: 'c' — клиент, 's' — студия; текст)
COMMENTS = {
    'done': [('s', 'Здравствуйте! Подготовили бриф, ответьте, пожалуйста, на вопросы в документе.'),
             ('c', 'Бриф заполнил, отправляю вместе с примерами сайтов, которые нравятся.'),
             ('s', 'Первая версия дизайна готова, ссылка на макет в Figma отправлена на почту.'),
             ('c', 'Всё отлично, принимаем!')],
    'review': [('s', 'Добрый день! Прикрепили интерактивный прототип для согласования.'),
               ('c', 'Прототип посмотрели, всё нравится. Можно переходить к дизайну.'),
               ('s', 'Итоговые макеты готовы и отправлены вам на проверку, ждём обратной связи.')],
    'in_progress': [('s', 'Приступили к работе, промежуточный отчёт будет в пятницу.'),
                    ('c', 'Хорошо, ждём.')],
    'discussion': [('s', 'Здравствуйте! Подскажите, есть ли у вас готовые фотографии продукции?'),
                   ('c', 'Фото есть, пришлю архив до конца недели.')],
    'new': [],
    'cancelled': [('c', 'Решили отложить проект до следующего года, отменяем заказ.')],
}

PATHS = {
    'new': ['new'],
    'discussion': ['new', 'discussion'],
    'in_progress': ['new', 'discussion', 'in_progress'],
    'review': ['new', 'discussion', 'in_progress', 'review'],
    'done': ['new', 'discussion', 'in_progress', 'review', 'done'],
    'cancelled': ['new', 'cancelled'],
}

PORTFOLIO = [
    ('sites', 'Кофейня «Бодрое утро»', 'Кофейня «Бодрое утро»', 'Промо-сайт кофейни с меню и онлайн-бронированием',
     'Лендинг для городской кофейни: меню с фотографиями, акции, бронирование столиков и карта проезда. '
     'После запуска количество бронирований через сайт выросло в 2,5 раза.', '#ff9a6c', '#d6457a', 'landing', 2026),
    ('shops', 'ТехноМаркет', 'ООО «ТехноМаркет»', 'Интернет-магазин электроники на 3000 товаров',
     'Интернет-магазин с умными фильтрами, сравнением товаров, онлайн-оплатой и синхронизацией с 1С. '
     'Конверсия выросла на 38 % по сравнению со старым сайтом.', '#4facfe', '#3b4bdb', 'shop', 2026),
    ('branding', 'Зелёный луг', 'Эко-ферма «Зелёный луг»', 'Фирменный стиль и упаковка',
     'Айдентика для фермерского хозяйства: логотип, палитра, упаковка молочной продукции, шаблоны для соцсетей.',
     '#43e97b', '#1f9d7a', 'brand', 2026),
    ('ui-ux', 'FitLife', 'Сеть фитнес-клубов', 'Мобильное приложение для фитнес-клуба',
     'Приложение для записи на тренировки, покупки абонементов и отслеживания прогресса. '
     'Средняя оценка в магазинах приложений — 4,8.', '#a18cd1', '#6c5ce7', 'app', 2026),
    ('sites', 'Стоматология «Улыбка»', 'Клиника «Улыбка»', 'Корпоративный сайт клиники с онлайн-записью',
     'Сайт клиники с каталогом услуг и цен, страницами врачей и онлайн-записью на приём.',
     '#38d6d9', '#2b7de9', 'landing', 2025),
    ('ui-ux', 'Финтех-дашборд', 'FinPoint', 'Интерфейс личного кабинета для финансового сервиса',
     'Дашборд для управления финансами малого бизнеса: платежи, аналитика, отчёты для бухгалтерии.',
     '#5b5bf7', '#1d2b64', 'dashboard', 2025),
    ('shops', 'Книжная лавка', 'Книжная лавка «Переплёт»', 'Интернет-магазин независимого книжного',
     'Магазин с подборками, отзывами читателей, подарочными сертификатами и самовывозом.',
     '#f6d365', '#fd7e3c', 'shop', 2025),
    ('sites', 'Автосервис «МоторДом»', 'Автосервис «МоторДом»', 'Сайт автосервиса с калькулятором ТО',
     'Сайт с онлайн-калькулятором стоимости техобслуживания и записью на сервис. Продвигается в топ-3 по городу.',
     '#434343', '#e5484d', 'landing', 2025),
    ('branding', 'Сила', 'Сеть спортзалов «Сила»', 'Логотип и айдентика сети спортзалов',
     'Энергичный фирменный стиль для сети спортзалов: логотип, навигация в залах, мерч.',
     '#f857a6', '#ff5858', 'brand', 2024),
]

REVIEWS = [
    ('morozov@technomarket.ru', 'Интернет-магазин «ТехноМаркет»', 5,
     'Магазин запустили точно в срок. Отдельное спасибо за интеграцию с 1С — сэкономили кучу времени '
     'на обновлении остатков. Продажи с сайта выросли почти на 40 %.', 1),
    ('client@mail.ru', 'Лендинг кофейни «Бодрое утро»', 5,
     'Очень довольны лендингом: красиво, быстро, удобно бронировать столики с телефона. '
     'Гости часто хвалят сайт.', 1),
    ('olga.k@mail.ru', 'Фирменный стиль эко-фермы «Зелёный луг»', 5,
     'Мария тонко почувствовала, чего мы хотим. Упаковка выделяется на полке, покупатели узнают нас издалека.', 1),
    ('ekaterina.n@yandex.ru', 'Сайт стоматологии «Улыбка»', 4,
     'Хороший сайт, пациенты записываются онлайн. Было немного задержек с правками, но результат того стоил.', 0),
]

FEEDBACK = [
    ('Григорьев Андрей', 'grigoriev@mail.ru', '+7 (917) 111-22-33',
     'Добрый день! Сколько будет стоить сайт для строительной компании примерно на 10 страниц?', 0, 1),
    ('Лебедева Ирина', 'irina.l@yandex.ru', None,
     'Здравствуйте, интересует редизайн интернет-магазина одежды. Можно созвониться на неделе?', 0, 2),
    ('ООО «Вектор»', None, '+7 (495) 123-45-67',
     'Нужен логотип и фирменный стиль для новой IT-компании. Перезвоните, пожалуйста.', 1, 9),
    ('Фёдоров Николай', 'fedorov.n@gmail.com', None,
     'Работаете ли вы с клиентами из других городов? Нужен сайт для турагентства.', 1, 15),
]


def seed_db():
    db = get_db()
    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)

    cat_ids = {}
    for name, slug, desc in CATEGORIES:
        cat_ids[slug] = db.execute('INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)',
                                   (name, slug, desc)).lastrowid

    service_ids = {}
    for slug, title, short, desc, price, days in SERVICES:
        service_ids[title] = db.execute(
            '''INSERT INTO services (category_id, title, short_description, description, price_from, duration_days,
               created_at) VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (cat_ids[slug], title, short, desc, price, days, _ts(200))).lastrowid

    user_ids = {}
    for i, (name, email, phone, role, position, bio, password) in enumerate(USERS):
        days_ago = 400 - i * 10 if role != 'client' else 180 - i * 8
        user_ids[email] = db.execute(
            '''INSERT INTO users (name, email, phone, password_hash, role, position, bio, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, email, phone, generate_password_hash(password), role, position, bio, _ts(days_ago))).lastrowid
    admin_id = user_ids['admin@webcraft.ru']

    order_ids = {}
    for client, service, designer, title, desc, budget, price, deadline, status, days_ago in ORDERS:
        created = _ts(days_ago)
        order_id = db.execute(
            '''INSERT INTO orders (client_id, service_id, designer_id, title, description, budget, price, deadline,
               status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_ids[client], service_ids[service], user_ids.get(designer), title, desc, budget, price,
             _day(deadline) if deadline is not None else None, status, created, created)).lastrowid
        order_ids[title] = order_id

        # журнал статусов
        path = PATHS[status]
        step = max(days_ago // max(len(path), 1), 1)
        last_change = created
        for n, (old, new) in enumerate(zip([None] + path[:-1], path)):
            author = user_ids[client] if new in ('new', 'done', 'cancelled') else admin_id
            last_change = created if n == 0 else _ts(days_ago - n * step)
            db.execute('''INSERT INTO order_status_history (order_id, user_id, old_status, new_status, created_at)
                          VALUES (?, ?, ?, ?, ?)''', (order_id, author, old, new, last_change))
        if last_change != created:
            db.execute('UPDATE orders SET updated_at = ? WHERE id = ?', (last_change, order_id))

        # переписка — сообщения распределены по сроку жизни заказа
        messages = COMMENTS[status]
        for n, (who, text) in enumerate(messages):
            author = user_ids[client] if who == 'c' else (user_ids.get(designer) or admin_id)
            days = days_ago - (n + 1) * days_ago // (len(messages) + 1)
            db.execute('INSERT INTO comments (order_id, user_id, text, created_at) VALUES (?, ?, ?, ?)',
                       (order_id, author, text, _ts(max(days, 0))))

        # оплаты: предоплата 50 % после согласования, остаток — после сдачи
        if price and status in ('in_progress', 'review', 'done'):
            first = price // 2
            db.execute('''INSERT INTO payments (order_id, amount, method, note, created_by, created_at)
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (order_id, first, 'transfer', 'Предоплата 50 %', admin_id, _ts(max(days_ago - 5, 0))))
            if status == 'done':
                db.execute('''INSERT INTO payments (order_id, amount, method, note, created_by, created_at)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (order_id, price - first, rnd.choice(['card', 'transfer']), 'Окончательный расчёт',
                            admin_id, _ts(max(days_ago - 25, 1))))
            elif service == 'Техническая поддержка':
                db.execute('''INSERT INTO payments (order_id, amount, method, note, created_by, created_at)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (order_id, price - first, 'card', 'Оплата поддержки за текущий месяц', admin_id,
                            _ts(0, hour=9)))

    for n, (slug, title, client, short, desc, c1, c2, layout, year) in enumerate(PORTFOLIO, start=1):
        filename = f'portfolio-{n}.svg'
        with open(os.path.join(upload_dir, filename), 'w', encoding='utf-8') as f:
            f.write(_cover_svg(title, short, c1, c2, layout))
        db.execute('''INSERT INTO portfolio (category_id, title, client, description, image, year, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                   (cat_ids[slug], title, client, short + '. ' + desc, filename, year, _ts(300 - n * 20)))

    for email, order_title, rating, text, approved in REVIEWS:
        db.execute('''INSERT INTO reviews (user_id, order_id, rating, text, is_approved, created_at)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (user_ids[email], order_ids[order_title], rating, text, approved, _ts(rnd.randint(5, 40))))

    for name, email, phone, message, processed, days_ago in FEEDBACK:
        db.execute('''INSERT INTO feedback (name, email, phone, message, is_processed, created_at)
                      VALUES (?, ?, ?, ?, ?, ?)''', (name, email, phone, message, processed, _ts(days_ago)))

    db.commit()
