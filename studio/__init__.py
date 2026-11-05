import os

from flask import Flask, render_template

from config import Config


def create_app(config_class=Config):
    """Фабрика приложения: создаёт и настраивает экземпляр Flask."""
    app = Flask(__name__, instance_path=config_class.INSTANCE_DIR)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from . import db, utils
    db.init_app(app)
    utils.init_app(app)

    from .main import bp as main_bp
    from .auth import bp as auth_bp
    from .cabinet import bp as cabinet_bp
    from .admin import bp as admin_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp, url_prefix='/cabinet')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    error_texts = {
        400: ('Некорректный запрос', 'Сессия устарела или форма заполнена неверно. Обновите страницу и попробуйте ещё раз.'),
        403: ('Доступ запрещён', 'У вас недостаточно прав для просмотра этой страницы.'),
        404: ('Страница не найдена', 'Возможно, она была удалена или вы перешли по неверной ссылке.'),
        413: ('Файл слишком большой', 'Максимальный размер загружаемого файла — 5 МБ.'),
    }

    def handle_error(error):
        title, text = error_texts[error.code]
        return render_template('error.html', code=error.code, title=title, text=text), error.code

    for code in error_texts:
        app.register_error_handler(code, handle_error)

    # При первом запуске база данных создаётся и заполняется демонстрационными данными
    with app.app_context():
        if not os.path.exists(app.config['DATABASE']):
            db.init_db()
            from .seed import seed_db
            seed_db()

    return app
