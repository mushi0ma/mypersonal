# src/core/config.py
import os

# --- Токены для ботов ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN")
ADMIN_NOTIFICATION_BOT_TOKEN = os.getenv("ADMIN_NOTIFICATION_BOT_TOKEN")

# --- Идентификаторы ---
# Преобразуем к int сразу, чтобы избежать ошибок в других местах
try:
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))
except (ValueError, TypeError):
    ADMIN_TELEGRAM_ID = None

NOTIFICATION_BOT_USERNAME = os.getenv("NOTIFICATION_BOT_USERNAME", "YourNotificationBot")

# --- Настройки базы данных ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db") # 'db' - имя сервиса в docker-compose
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Настройки Celery & Redis ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").lower() in ('true', '1', 't')

# --- Настройки для отправки Email (SendGrid) ---
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")

# --- Валидация ключевых переменных ---
def validate_config():
    """Проверяет, что все критически важные переменные установлены."""
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "ADMIN_BOT_TOKEN": ADMIN_BOT_TOKEN,
        "NOTIFICATION_BOT_TOKEN": NOTIFICATION_BOT_TOKEN,
        "ADMIN_NOTIFICATION_BOT_TOKEN": ADMIN_NOTIFICATION_BOT_TOKEN,
        "ADMIN_TELEGRAM_ID": ADMIN_TELEGRAM_ID,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
    }
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        raise ValueError(f"Отсутствуют необходимые переменные окружения: {', '.join(missing_vars)}")

# Валидацию следует вызывать в основной точке входа в приложение (например, в main.py)
# validate_config()