# src/core/tasks.py
"""
This module defines asynchronous background tasks managed by Celery.
These tasks include sending notifications, database maintenance, and periodic checks.
The use of Celery allows the main application to remain responsive by offloading long-running operations.
"""
import os
import logging
import asyncio
import subprocess
import asyncpg
from celery import Celery
from celery.schedules import crontab
import telegram
from telegram.request import HTTPXRequest
from src.core.db import data_access as db_data
from datetime import datetime
from celery import group
from celery.exceptions import SoftTimeLimitExceeded

from src.core import config

# --- Logging Configuration ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Celery Application Setup ---
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

# --- Telegram Bot Configuration ---

def create_telegram_bot(token: str) -> telegram.Bot:
    """
    Creates and configures a `telegram.Bot` instance with optimized timeouts.

    Args:
        token: The Telegram API token for the bot.

    Returns:
        A configured `telegram.Bot` instance.
    """
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    return telegram.Bot(token=token, request=request)

# --- Database Connection Helper ---

async def get_connection():
    """
    Establishes a new asynchronous connection to the database.
    Each Celery task should use its own connection to ensure process safety.

    Returns:
        An `asyncpg.Connection` object.
    """
    return await asyncpg.connect(
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT
    )

# --- Core Asynchronous Task Logic ---

async def _async_notify_user(user_id: int, text: str, category: str, button_text: str | None, button_callback: str | None):
    """
    Handles the asynchronous logic of sending a notification to a single user.
    """
    conn = None
    try:
        user_notifier_bot = create_telegram_bot(config.NOTIFICATION_BOT_TOKEN)
        conn = await get_connection()
        
        await db_data.create_notification(conn, user_id=user_id, text=text, category=category)
        telegram_id = await db_data.get_telegram_id_by_user_id(conn, user_id)

        reply_markup = None
        if button_text and button_callback:
            keyboard = [[telegram.InlineKeyboardButton(button_text, callback_data=button_callback)]]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        await user_notifier_bot.send_message(
            chat_id=telegram_id, text=text, parse_mode='Markdown', reply_markup=reply_markup
        )
        logger.info(f"Notification '{category}' for user_id={user_id} sent to telegram_id={telegram_id}.")
    except db_data.NotFoundError:
        logger.warning(f"Failed to send notification: telegram_id for user_id={user_id} not found.")
    except telegram.error.Forbidden:
        logger.warning(f"Failed to send notification to user_id={user_id}: Bot was blocked by the user.")
    except telegram.error.TimedOut:
        logger.warning(f"Timeout while sending notification to user_id={user_id}. Retrying might be necessary.")
    except telegram.error.TelegramError as e:
        logger.error(f"A Telegram error occurred while notifying user_id={user_id}: {e}", exc_info=True)
    except asyncpg.PostgresError as e:
        logger.error(f"A database error occurred while notifying user_id={user_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred in _async_notify_user for user_id={user_id}: {e}", exc_info=True)
    finally:
        if conn:
            await conn.close()

def escape_markdown(text: str) -> str:
    """
    Escapes special characters in text to be compatible with Telegram's MarkdownV2 parsing.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

async def _async_notify_admin(text: str, category: str = 'audit', user_id: int | None = None):
    """
    Handles the asynchronous logic of sending a formatted notification to the administrator.
    """
    try:
        admin_notifier_bot = create_telegram_bot(config.ADMIN_NOTIFICATION_BOT_TOKEN)
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        
        header = f"🔔 **Уведомление:** `{category}`\n🕐 **Время:** `{timestamp}`\n{'─' * 30}\n"
        formatted_text = header + (text if '```' in text else escape_markdown(text))
        
        reply_markup = None
        if user_id:
            keyboard = [[
                telegram.InlineKeyboardButton("👤 Профиль", callback_data=f"admin_view_user_{user_id}"),
                telegram.InlineKeyboardButton("🚫 Забанить", callback_data=f"admin_ban_user_{user_id}")
            ]]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        await admin_notifier_bot.send_message(
            chat_id=config.ADMIN_TELEGRAM_ID, text=formatted_text, parse_mode='Markdown', reply_markup=reply_markup
        )
        logger.info(f"Admin notification '{category}' sent successfully.")
    except telegram.error.BadRequest as e:
        if "can't parse entities" in str(e).lower():
            logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
            plain_text = f"Notification: {category}\nTime: {timestamp}\n---\n{text}"
            await admin_notifier_bot.send_message(
                chat_id=config.ADMIN_TELEGRAM_ID, text=plain_text, reply_markup=reply_markup
            )
    except telegram.error.Forbidden:
        logger.error(f"Failed to send admin notification: Bot might be blocked by the admin.")
    except telegram.error.TimedOut:
        logger.warning(f"Timeout sending admin notification for category: {category}")
    except telegram.error.TelegramError as e:
        logger.error(f"A Telegram error occurred while notifying admin: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred in _async_notify_admin: {e}", exc_info=True)

# --- Synchronous Celery Task Wrappers ---

@celery_app.task(bind=True, max_retries=3)
def notify_user(self, user_id: int, text: str, category: str = 'system', button_text: str = None, button_callback: str = None):
    """
    Synchronous Celery task that wraps the async user notification logic.
    """
    try:
        asyncio.run(_async_notify_user(user_id, text, category, button_text, button_callback))
    except Exception as exc:
        logger.error(f"Error in notify_user for user_id={user_id}: {exc}")
        self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True, max_retries=3)
def notify_admin(self, text: str, category: str = 'audit', user_id: int | None = None):
    """
    Synchronous Celery task that wraps the async admin notification logic.
    """
    try:
        asyncio.run(_async_notify_admin(text, category, user_id))
    except Exception as exc:
        logger.error(f"Error in notify_admin: {exc}")
        self.retry(exc=exc, countdown=60)

# --- High-Level and Periodic Tasks ---

async def _async_broadcast_new_book(book_id: int):
    """
    Asynchronous logic for broadcasting a new book notification to all users.
    """
    logger.info(f"Starting new book broadcast for book_id: {book_id}")
    conn = None
    try:
        conn = await get_connection()
        book = await db_data.get_book_card_details(conn, book_id)
        all_user_ids = await db_data.get_all_user_ids(conn)
    finally:
        if conn:
            await conn.close()

    text = f"🆕 **В библиотеке пополнение!**\n\nКнига «{book['name']}» от автора {book['author']} была добавлена в каталог."
    button_text = "📖 Посмотреть карточку книги"
    button_callback = f"view_book_{book_id}"

    BATCH_SIZE = 50
    for i in range(0, len(all_user_ids), BATCH_SIZE):
        batch = all_user_ids[i:i + BATCH_SIZE]
        job = group(
            notify_user.s(user_id=uid, text=text, category='new_arrival', button_text=button_text, button_callback=button_callback)
            for uid in batch
        )
        job.apply_async()
        logger.info(f"Sent {i + len(batch)}/{len(all_user_ids)} notifications.")

    notify_admin.delay(f"🚀 New book broadcast for '{book['name']}' completed for {len(all_user_ids)} users.")

@celery_app.task(bind=True, max_retries=3)
def broadcast_new_book(self, book_id: int):
    """
    Synchronous Celery wrapper for the new book broadcast task.
    """
    try:
        asyncio.run(_async_broadcast_new_book(book_id))
    except SoftTimeLimitExceeded:
        logger.error("Broadcast task timed out, will retry.")
        self.retry(countdown=60)
    except Exception as e:
        logger.error(f"Error in broadcast_new_book task: {e}")
        notify_admin.delay(f"❗️ Error broadcasting new book (ID: {book_id}): {e}")
        self.retry(exc=e, countdown=30)

async def _async_check_due_dates():
    """
    Asynchronous logic for checking book due dates and sending reminders.
    """
    logger.info("Running periodic task: checking book due dates...")
    conn = None
    try:
        conn = await get_connection()
        overdue_entries = await db_data.get_users_with_overdue_books(conn)
        due_soon_entries = await db_data.get_users_with_books_due_soon(conn, days_ahead=2)
    finally:
        if conn:
            await conn.close()

    for entry in overdue_entries:
        user_text = f"❗️ **Просрочка:** Срок возврата «{entry['book_name']}» истек {entry['due_date'].strftime('%d.%m.%Y')}!"
        notify_user.delay(user_id=entry['user_id'], text=user_text, category='due_date')

    for entry in due_soon_entries:
        user_text = f"🔔 **Напоминание:** Срок возврата «{entry['book_name']}» истекает через 2 дня."
        notify_user.delay(user_id=entry['user_id'], text=user_text, category='due_date_reminder', button_text="♻️ Продлить на 7 дней", button_callback=f"extend_borrow_{entry['borrow_id']}")

@celery_app.task
def check_due_dates_and_notify():
    """
    Synchronous Celery wrapper for the due date checking task.
    """
    try:
        asyncio.run(_async_check_due_dates())
    except asyncpg.PostgresError as e:
        error_message = f"❗️ A database error occurred in `check_due_dates_and_notify`: {e}"
        logger.error(error_message, exc_info=True)
        notify_admin.delay(text=error_message, category='error')
    except Exception as e:
        error_message = f"❗️ Critical error in periodic task `check_due_dates_and_notify`: {e}"
        logger.error(error_message, exc_info=True)
        notify_admin.delay(text=error_message, category='error')

# --- Database Backup and Health Check Tasks ---

def cleanup_old_backups(backup_dir, days=30):
    """
    Removes database backups older than a specified number of days.
    """
    import time
    cutoff = time.time() - (days * 86400)
    for filename in os.listdir(backup_dir):
        if filename.startswith('backup_') and filename.endswith('.sql'):
            filepath = os.path.join(backup_dir, filename)
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                logger.info(f"🗑️ Deleted old backup: {filename}")

@celery_app.task
def backup_database_task():
    """
    Performs a backup of the PostgreSQL database using pg_dump.
    """
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.getenv('BACKUP_DIR', '/app/backups')
        os.makedirs(backup_dir, exist_ok=True)
        filename = f"{backup_dir}/backup_{timestamp}.sql"

        command = ['pg_dump', '-h', config.DB_HOST, '-U', config.DB_USER, '-d', config.DB_NAME, '-f', filename, '--no-password']
        env = {**os.environ, 'PGPASSWORD': config.DB_PASSWORD}

        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)

        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        notify_admin.delay(text=f"✅ **Backup created successfully**\n\n📁 File: `{filename}`\n📊 Size: {file_size_mb:.2f} MB", category='backup')
        cleanup_old_backups(backup_dir)
    except subprocess.CalledProcessError as e:
        error_msg = f"❌ Backup creation failed with exit code {e.returncode}:\n{e.stderr}"
        logger.error(error_msg)
        notify_admin.delay(text=f"❌ **Backup creation error**\n\n{error_msg}", category='backup_error')
    except FileNotFoundError as e:
        error_msg = f"❌ Backup command not found: {e}. Is pg_dump installed and in the system's PATH?"
        logger.error(error_msg)
        notify_admin.delay(text=f"❌ **Backup configuration error**\n\n{error_msg}", category='backup_error')
    except IOError as e:
        error_msg = f"❌ A file system error occurred during backup: {e}"
        logger.error(error_msg, exc_info=True)
        notify_admin.delay(text=f"❌ **Backup file system error**\n\n`{e}`", category='backup_error')
    except Exception as e:
        logger.error(f"❌ An unhandled exception occurred during backup: {e}", exc_info=True)
        notify_admin.delay(text=f"❌ **Critical backup error**\n\n`{e}`", category='backup_error')

@celery_app.task
def health_check_task():
    """
    Runs a periodic health check of the system's components.
    """
    from src.health_check import run_health_check
    all_ok, message = asyncio.run(run_health_check())
    if not all_ok:
        logger.error(f"Health check failed! Reason: {message}")
        notify_admin.delay(text=f"🌡️ **Health Check FAILED**\n\n`{message}`")
    return all_ok

# --- Celery Beat Schedule ---
# Defines the schedule for periodic tasks.
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
