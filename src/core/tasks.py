# src/core/tasks.py
import os
import logging
import asyncio
import subprocess
from celery import Celery
from celery.schedules import crontab
import telegram
from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from datetime import datetime
from celery import group
from celery.exceptions import SoftTimeLimitExceeded

from src.core import config

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройка Celery ---
celery_app = Celery(
    'tasks',
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_always_eager=config.CELERY_TASK_ALWAYS_EAGER
)

celery_app.conf.task_annotations = {
    'src.core.tasks.notify_user': {'rate_limit': '10/s', 'time_limit': 30},
    'src.core.tasks.broadcast_new_book': {'rate_limit': '1/m', 'time_limit': 600},
}

# --- АСИНХРОННЫЕ ВЕРСИИ НИЗКОУРОВНЕВЫХ ЗАДАЧ ---

async def _async_notify_user(user_id: int, text: str, category: str, button_text: str | None, button_callback: str | None):
    """Асинхронная логика для отправки уведомления пользователю."""
    try:
        user_notifier_bot = telegram.Bot(token=config.NOTIFICATION_BOT_TOKEN)
        async with get_db_connection() as conn:
            await db_data.create_notification(conn, user_id=user_id, text=text, category=category)
            telegram_id = await db_data.get_telegram_id_by_user_id(conn, user_id)

        reply_markup = None
        if button_text and button_callback:
            keyboard = [[telegram.InlineKeyboardButton(button_text, callback_data=button_callback)]]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        await user_notifier_bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"Уведомление '{category}' для user_id={user_id} отправлено на telegram_id={telegram_id}.")
    except db_data.NotFoundError:
        logger.warning(f"Не удалось отправить уведомление: telegram_id для user_id={user_id} не найден.")
    except Exception as e:
        logger.error(f"Ошибка в _async_notify_user для user_id={user_id}: {e}", exc_info=True)

async def _async_notify_admin(text: str, category: str = 'audit'):
    """Асинхронная логика для отправки уведомления администратору."""
    try:
        admin_notifier_bot = telegram.Bot(token=config.ADMIN_NOTIFICATION_BOT_TOKEN)
        await admin_notifier_bot.send_message(chat_id=config.ADMIN_TELEGRAM_ID, text=text, parse_mode='Markdown')
        logger.info(f"Аудит-уведомление '{category}' для админа отправлено.")
    except Exception as e:
        logger.error(f"Ошибка в _async_notify_admin: {e}", exc_info=True)


# --- СИНХРОННЫЕ ОБЕРТКИ ДЛЯ CELERY ---

@celery_app.task
def notify_user(user_id: int, text: str, category: str = 'system', button_text: str = None, button_callback: str = None):
    """Синхронная Celery задача, которая запускает асинхронную логику."""
    asyncio.run(_async_notify_user(user_id, text, category, button_text, button_callback))

@celery_app.task
def notify_admin(text: str, category: str = 'audit'):
    """Синхронная Celery задача для отправки уведомления админу."""
    asyncio.run(_async_notify_admin(text, category))


# --- ВЫСОКОУРОВНЕВЫЕ И ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ---

async def _async_broadcast_new_book(book_id: int):
    """Асинхронная логика рассылки о новой книге."""
    logger.info(f"Запущена рассылка о новой книге с ID: {book_id}")
    async with get_db_connection() as conn:
        book = await db_data.get_book_card_details(conn, book_id)
        all_user_ids = await db_data.get_all_user_ids(conn)

    text = f"🆕 **В библиотеке пополнение!**\n\nКнига «{book['name']}» от автора {book['author']} была добавлена в каталог."
    button_text = "📖 Посмотреть карточку книги"
    button_callback = f"view_book_{book_id}"

    BATCH_SIZE = 50
    total_sent = 0

    for i in range(0, len(all_user_ids), BATCH_SIZE):
        batch = all_user_ids[i:i + BATCH_SIZE]
        job = group(
            notify_user.s(
                user_id=uid,
                text=text,
                category='new_arrival',
                button_text=button_text,
                button_callback=button_callback
            ) for uid in batch
        )
        job.apply_async()
        total_sent += len(batch)
        logger.info(f"Отправлено {total_sent}/{len(all_user_ids)} уведомлений")

    logger.info(f"Рассылка о новой книге завершена для {total_sent} пользователей.")
    notify_admin.delay(f"🚀 Успешно разослано уведомление о новой книге «{book['name']}» для {total_sent} пользователей.")

@celery_app.task(bind=True, max_retries=3)
def broadcast_new_book(self, book_id: int):
    """Синхронная обертка для рассылки."""
    try:
        asyncio.run(_async_broadcast_new_book(book_id))
    except SoftTimeLimitExceeded:
        logger.error("Превышен лимит времени для рассылки")
        self.retry(countdown=60)
    except Exception as e:
        logger.error(f"Ошибка в задаче broadcast_new_book: {e}")
        notify_admin.delay(f"❗️ Ошибка при рассылке о новой книге (ID: {book_id}): {e}")
        raise self.retry(exc=e, countdown=30)


async def _async_check_due_dates():
    """Асинхронная логика проверки сроков."""
    logger.info("Выполняется периодическая задача: проверка сроков сдачи книг...")
    async with get_db_connection() as conn:
        overdue_entries = await db_data.get_users_with_overdue_books(conn)
        due_soon_entries = await db_data.get_users_with_books_due_soon(conn, days_ahead=2)

    if overdue_entries:
        logger.info(f"Найдено просроченных книг: {len(overdue_entries)}")
        for entry in overdue_entries:
            due_date_str = entry['due_date'].strftime('%d.%m.%Y')
            user_text = f"❗️ **Просрочка:** Срок возврата «{entry['book_name']}» истек {due_date_str}! Пожалуйста, верните ее."
            notify_user.delay(user_id=entry['user_id'], text=user_text, category='due_date')
            admin_text = f"❗️Пользователь @{entry['username']} просрочил «{entry['book_name']}» (срок: {due_date_str})."
            notify_admin.delay(text=admin_text, category='overdue')

    if due_soon_entries:
        logger.info(f"Найдено книг с подходящим сроком возврата: {len(due_soon_entries)}")
        for entry in due_soon_entries:
            user_text = f"🔔 **Напоминание:** Срок возврата книги «{entry['book_name']}» истекает через 2 дня."
            notify_user.delay(
                user_id=entry['user_id'],
                text=user_text,
                category='due_date_reminder',
                button_text="♻️ Продлить на 7 дней",
                button_callback=f"extend_borrow_{entry['borrow_id']}"
            )

    if not overdue_entries and not due_soon_entries:
        logger.info("Книг для отправки уведомлений не найдено.")


@celery_app.task
def check_due_dates_and_notify():
    """Синхронная обертка для проверки сроков."""
    try:
        asyncio.run(_async_check_due_dates())
    except Exception as e:
        error_message = f"❗️ **Критическая ошибка в периодической задаче**\n\n`check_due_dates_and_notify`:\n`{e}`"
        logger.error(error_message, exc_info=True)
        notify_admin.delay(text=error_message, category='error')

# --- ЗАДАЧИ РЕЗЕРВНОГО КОПИРОВАНИЯ И ПРОВЕРКИ ЗДОРОВЬЯ ---

def cleanup_old_backups(backup_dir, days=30):
    """Удаляет бэкапы старше заданного количества дней."""
    import time

    now = time.time()
    cutoff = now - (days * 86400)

    for filename in os.listdir(backup_dir):
        if filename.startswith('backup_') and filename.endswith('.sql'):
            filepath = os.path.join(backup_dir, filename)
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                logger.info(f"🗑️ Удален старый backup: {filename}")

def backup_database():
    """Создает резервную копию базы данных PostgreSQL."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Путь для бэкапов внутри контейнера, доступный для appuser
        backup_dir = os.getenv('BACKUP_DIR', '/app/backups')
        os.makedirs(backup_dir, exist_ok=True)
        filename = f"{backup_dir}/backup_{timestamp}.sql"

        command = [
            'pg_dump',
            '-h', os.getenv('DB_HOST', 'localhost'),
            '-U', os.getenv('DB_USER', 'postgres'),
            '-d', os.getenv('DB_NAME', 'library_db'),
            '-f', filename,
            '--no-password'
        ]

        env = os.environ.copy()
        env['PGPASSWORD'] = os.getenv('DB_PASSWORD', '')

        result = subprocess.run(command, env=env, capture_output=True, text=True)

        if result.returncode == 0:
            file_size = os.path.getsize(filename) / (1024 * 1024)
            notify_admin.delay(
                text=f"✅ **Backup успешно создан**\n\n"
                     f"📁 Файл: `{filename}`\n"
                     f"📊 Размер: {file_size:.2f} MB",
                category='backup'
            )
            logger.info(f"✅ Backup успешно создан: {filename}")
            cleanup_old_backups(backup_dir, days=30)
            return filename
        else:
            error_msg = f"❌ Ошибка создания backup: {result.stderr}"
            logger.error(error_msg)
            notify_admin.delay(text=f"❌ **Ошибка создания backup**\n\n{result.stderr}", category='backup_error')
            return None

    except Exception as e:
        error_msg = f"❌ Исключение при создании backup: {e}"
        logger.error(error_msg, exc_info=True)
        notify_admin.delay(text=f"❌ **Критическая ошибка backup**\n\n`{e}`", category='backup_error')
        return None

@celery_app.task
def backup_database_task():
    """Celery задача для backup базы данных."""
    return backup_database()

@celery_app.task
def health_check_task():
    """Периодическая проверка здоровья системы."""
    from src.health_check import run_health_check
    all_ok, message = asyncio.run(run_health_check())
    if not all_ok:
        logger.error(f"Health check failed! Reason: {message}")
        notify_admin.delay(text=f"🌡️ **Health Check FAILED**\n\n`{message}`")
    return all_ok

# --- Расписание для периодических задач (Celery Beat) ---
celery_app.conf.beat_schedule = {
    'check-due-dates-every-day': {
        'task': 'src.core.tasks.check_due_dates_and_notify',
        'schedule': crontab(hour=10, minute=0),
    },
    'daily-database-backup': {
        'task': 'src.core.tasks.backup_database_task',
        'schedule': crontab(hour=3, minute=0),
    },
    'health-check-every-hour': {
        'task': 'src.core.tasks.health_check_task',
        'schedule': crontab(minute=0),
    },
}