import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Настройки приложения."""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'webcraft-dev-secret-key-change-in-production')
    INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
    DATABASE = os.path.join(INSTANCE_DIR, 'studio.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'studio', 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # ограничение размера загружаемого файла — 5 МБ
    PER_PAGE = 10
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
