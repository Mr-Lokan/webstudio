-- =====================================================================
--  База данных информационной системы веб-студии «WebCraft»
--  СУБД: SQLite 3
-- =====================================================================

PRAGMA foreign_keys = OFF;

DROP VIEW    IF EXISTS order_summary;
DROP TRIGGER IF EXISTS trg_orders_updated_at;
DROP TABLE   IF EXISTS feedback;
DROP TABLE   IF EXISTS reviews;
DROP TABLE   IF EXISTS portfolio;
DROP TABLE   IF EXISTS payments;
DROP TABLE   IF EXISTS comments;
DROP TABLE   IF EXISTS order_status_history;
DROP TABLE   IF EXISTS orders;
DROP TABLE   IF EXISTS services;
DROP TABLE   IF EXISTS categories;
DROP TABLE   IF EXISTS users;

PRAGMA foreign_keys = ON;

-- Пользователи системы: клиенты, дизайнеры и администраторы
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    phone         TEXT,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'client'
                          CHECK (role IN ('client', 'designer', 'admin')),
    position      TEXT,                       -- должность (для сотрудников)
    bio           TEXT,                       -- краткая информация о сотруднике
    is_active     INTEGER NOT NULL DEFAULT 1, -- 0 — учётная запись заблокирована
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Категории услуг и работ портфолио
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    slug        TEXT NOT NULL UNIQUE,
    description TEXT
);

-- Каталог услуг студии
CREATE TABLE services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id       INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
    title             TEXT    NOT NULL,
    short_description TEXT,
    description       TEXT,
    price_from        INTEGER NOT NULL CHECK (price_from >= 0),
    duration_days     INTEGER NOT NULL DEFAULT 14 CHECK (duration_days > 0),
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Заказы клиентов
CREATE TABLE orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    service_id  INTEGER REFERENCES services (id) ON DELETE SET NULL,
    designer_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL,
    budget      INTEGER CHECK (budget IS NULL OR budget >= 0), -- бюджет, указанный клиентом
    price       INTEGER CHECK (price IS NULL OR price >= 0),   -- согласованная стоимость
    deadline    TEXT,
    status      TEXT    NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'discussion', 'in_progress', 'review', 'done', 'cancelled')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Журнал изменения статусов заказов
CREATE TABLE order_status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    user_id    INTEGER REFERENCES users (id) ON DELETE SET NULL,
    old_status TEXT,
    new_status TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Переписка по заказу между клиентом и студией
CREATE TABLE comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    user_id    INTEGER REFERENCES users (id) ON DELETE SET NULL,
    text       TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Оплаты по заказам
CREATE TABLE payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    amount     INTEGER NOT NULL CHECK (amount > 0),
    method     TEXT    NOT NULL DEFAULT 'transfer' CHECK (method IN ('card', 'transfer', 'cash')),
    note       TEXT,
    created_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Работы портфолио
CREATE TABLE portfolio (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    title        TEXT    NOT NULL,
    client       TEXT,
    description  TEXT,
    image        TEXT,
    url          TEXT,
    year         INTEGER,
    is_published INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Отзывы клиентов (публикуются после модерации)
CREATE TABLE reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    order_id    INTEGER UNIQUE REFERENCES orders (id) ON DELETE SET NULL,
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text        TEXT    NOT NULL,
    is_approved INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Обращения через форму обратной связи
CREATE TABLE feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    email        TEXT,
    phone        TEXT,
    message      TEXT    NOT NULL,
    is_processed INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Индексы для ускорения выборок
CREATE INDEX idx_orders_client    ON orders (client_id);
CREATE INDEX idx_orders_designer  ON orders (designer_id);
CREATE INDEX idx_orders_status    ON orders (status);
CREATE INDEX idx_services_cat     ON services (category_id);
CREATE INDEX idx_portfolio_cat    ON portfolio (category_id);
CREATE INDEX idx_comments_order   ON comments (order_id);
CREATE INDEX idx_payments_order   ON payments (order_id);
CREATE INDEX idx_history_order    ON order_status_history (order_id);

-- Триггер: автоматическое обновление даты изменения заказа
CREATE TRIGGER trg_orders_updated_at
AFTER UPDATE ON orders
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE orders SET updated_at = datetime('now', 'localtime') WHERE id = NEW.id;
END;

-- Представление: сводная информация о заказе (клиент, исполнитель, услуга, сумма оплат)
CREATE VIEW order_summary AS
SELECT o.*,
       c.name  AS client_name,
       c.email AS client_email,
       c.phone AS client_phone,
       d.name  AS designer_name,
       s.title AS service_title,
       IFNULL((SELECT SUM(p.amount) FROM payments p WHERE p.order_id = o.id), 0) AS paid
FROM orders o
JOIN users c         ON c.id = o.client_id
LEFT JOIN users d    ON d.id = o.designer_id
LEFT JOIN services s ON s.id = o.service_id;
