# tasks.py
import os
import logging
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import telegram
import db_data
from db_utils import get_db_connection
from datetime import datetime
from backup_db import backup_database
from celery import group
from celery.exceptions import SoftTimeLimitExceeded
# Загружаем переменные окружения и настраиваем логгер
load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройка Celery ---
celery_app = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND")
)

celery_app.conf.task_annotations = {
    'tasks.notify_user': {
        'rate_limit': '10/s',  # 10 задач в секунду
        'time_limit': 30,      # Максимум 30 секунд на задачу
    },
    'tasks.broadcast_new_book': {
        'rate_limit': '1/m',   # 1 раз в минуту
        'time_limit': 600,
    },
}

# --- ИНИЦИАЛИЗАЦИЯ ДВУХ БОТОВ ---
try:
    user_notifier_bot = telegram.Bot(token=os.getenv("NOTIFICATION_BOT_TOKEN"))
    logger.info("API бота-уведомителя для ПОЛЬЗОВАТЕЛЕЙ инициализировано.")
except Exception as e:
    logger.error(f"Не удалось инициализировать API бота-уведомителя для пользователей: {e}")
    user_notifier_bot = None

try:
    admin_notifier_bot = telegram.Bot(token=os.getenv("ADMIN_NOTIFICATION_BOT_TOKEN"))
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))
    logger.info("API бота-аудитора для АДМИНА инициализировано.")
except Exception as e:
    logger.error(f"Не удалось инициализировать API бота-аудитора для админа: {e}")
    admin_notifier_bot = None

# --- НИЗКОУРОВНЕВЫЕ ЗАДАЧИ ОТПРАВКИ ---

@celery_app.task
def notify_user(user_id: int, text: str, category: str = 'system', button_text: str = None, button_callback: str = None):
    """Сохраняет и отправляет уведомление КОНКРЕТНОМУ ПОЛЬЗОВАТЕЛЮ через Bot-Notifier."""
    if not user_notifier_bot:
        logger.warning(f"Bot-Notifier недоступен. Уведомление для user_id={user_id} не отправлено.")
        return

    try:
        with get_db_connection() as conn:
            db_data.create_notification(conn, user_id=user_id, text=text, category=category)
            telegram_id = db_data.get_telegram_id_by_user_id(conn, user_id)

        reply_markup = None
        if button_text and button_callback:
            keyboard = [[telegram.InlineKeyboardButton(button_text, callback_data=button_callback)]]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        user_notifier_bot.send_message(
            chat_id=telegram_id, 
            text=text, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info(f"Уведомление '{category}' для user_id={user_id} отправлено на telegram_id={telegram_id}.")
    except Exception as e:
        logger.error(f"Ошибка в задаче notify_user для user_id={user_id}: {e}")

@celery_app.task
def notify_admin(text: str, category: str = 'audit'):
    """Отправляет системное уведомление АДМИНИСТРАТОРУ через Bot-Auditor."""
    if not admin_notifier_bot:
        logger.warning(f"Bot-Auditor недоступен. Системное уведомление не отправлено.")
        return
    try:
        admin_notifier_bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=text, parse_mode='Markdown')
        logger.info(f"Аудит-уведомление '{category}' для админа отправлено.")
    except Exception as e:
        logger.error(f"Ошибка в задаче notify_admin: {e}")

# --- ВЫСОКОУРОВНЕВЫЕ И ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ---

@celery_app.task(bind=True, max_retries=3)
def broadcast_new_book(self, book_id: int):
    """Рассылает уведомление о новой книге ПАЧКАМИ."""
    logger.info(f"Запущена рассылка о новой книге с ID: {book_id}")
    try:
        with get_db_connection() as conn:
            book = db_data.get_book_card_details(conn, book_id)
            all_user_ids = db_data.get_all_user_ids(conn)
        
        text = f"🆕 **В библиотеке пополнение!**\n\nКнига «{book['name']}» от автора {book['author']} была добавлена в каталог."
        button_text = "📖 Посмотреть карточку книги"
        button_callback = f"view_book_{book_id}"

        # ✅ ОТПРАВЛЯЕМ ПАЧКАМИ ПО 50 ШТУК
        BATCH_SIZE = 50
        total_sent = 0
        
        for i in range(0, len(all_user_ids), BATCH_SIZE):
            batch = all_user_ids[i:i + BATCH_SIZE]
            
            # Создаем группу задач
            job = group(
                notify_user.s(
                    user_id=uid,
                    text=text,
                    category='new_arrival',
                    button_text=button_text,
                    button_callback=button_callback
                ) for uid in batch
            )
            
            # Запускаем пачку
            job.apply_async()
            total_sent += len(batch)
            
            logger.info(f"Отправлено {total_sent}/{len(all_user_ids)} уведомлений")
        
        logger.info(f"Рассылка о новой книге завершена для {total_sent} пользователей.")
        notify_admin.delay(f"🚀 Успешно разослано уведомление о новой книге «{book['name']}» для {total_sent} пользователей.")
        
    except SoftTimeLimitExceeded:
        logger.error("Превышен лимит времени для рассылки")
        self.retry(countdown=60)  # Повторить через минуту
    except Exception as e:
        logger.error(f"Ошибка в задаче broadcast_new_book: {e}")
        notify_admin.delay(f"❗️ Ошибка при рассылке о новой книге (ID: {book_id}): {e}")
        raise self.retry(exc=e, countdown=30)

@celery_app.task
def check_due_dates_and_notify():
    """Проверяет сроки сдачи книг и уведомляет должников и администратора."""
    logger.info("Выполняется периодическая задача: проверка сроков сдачи книг...")
    try:
        with get_db_connection() as conn:
            overdue_entries = db_data.get_users_with_overdue_books(conn)
            if overdue_entries:
                logger.info(f"Найдено просроченных книг: {len(overdue_entries)}")
                for entry in overdue_entries:
                    # ... (логика отправки та же)
                    user_id, username, book_name, due_date = entry['user_id'], entry['username'], entry['book_name'], entry['due_date']
                    due_date_str = due_date.strftime('%d.%m.%Y')
                    user_text = f"❗️ **Просрочка:** Срок возврата «{book_name}» истек {due_date_str}! Пожалуйста, верните ее."
                    notify_user(user_id=user_id, text=user_text, category='due_date')
                    admin_text = f"❗️Пользователь @{username} просрочил «{book_name}» (срок: {due_date_str})."
                    notify_admin(text=admin_text, category='overdue')

            due_soon_entries = db_data.get_users_with_books_due_soon(conn, days_ahead=2)
            if due_soon_entries:
                logger.info(f"Найдено книг с подходящим сроком возврата: {len(due_soon_entries)}")
                for entry in due_soon_entries:
                    user_id, book_name, borrow_id = entry['user_id'], entry['book_name'], entry['borrow_id']
                    user_text = f"🔔 **Напоминание:** Срок возврата книги «{book_name}» истекает через 2 дня."
                    notify_user(
                        user_id=user_id, 
                        text=user_text, 
                        category='due_date_reminder',
                        button_text="♻️ Продлить на 7 дней",
                        button_callback=f"extend_borrow_{borrow_id}"
                    )
        
            if not overdue_entries and not due_soon_entries:
                logger.info("Книг для отправки уведомлений не найдено.")

    except Exception as e:
        error_message = f"❗️ **Критическая ошибка в периодической задаче**\n\n`check_due_dates_and_notify`:\n`{e}`"
        logger.error(error_message)
        notify_admin(text=error_message, category='error')

@celery_app.task
def check_overdue_books():
    """Проверяет просроченные книги и отправляет напоминания."""
    with get_db_connection() as conn:
        overdue_users = db_data.get_users_with_overdue_books(conn)
    
    for user_info in overdue_users:
        days_overdue = (datetime.now().date() - user_info['due_date']).days
        message = (
            f"⚠️ **Напоминание о возврате**\n\n"
            f"Книга «{user_info['book_name']}» просрочена на **{days_overdue} дн.**\n\n"
            f"Пожалуйста, верните её как можно скорее."
        )
        notify_user.delay(user_id=user_info['user_id'], text=message, category='overdue')

@celery_app.task
def remind_due_soon():
    """Напоминает о скором истечении срока возврата."""
    with get_db_connection() as conn:
        users_due_soon = db_data.get_users_with_books_due_soon(conn, days_ahead=2)
    
    for user_info in users_due_soon:
        message = (
            f"📅 **Напоминание**\n\n"
            f"Через 2 дня истекает срок возврата книги «{user_info['book_name']}».\n\n"
            f"Дата возврата: **{user_info['due_date'].strftime('%d.%m.%Y')}**"
        )
        # Добавляем кнопку продления
        notify_user.delay(
            user_id=user_info['user_id'], 
            text=message, 
            category='reminder',
            button_text="⏰ Продлить срок",
            button_callback=f"extend_borrow_{user_info['borrow_id']}"
        )

@celery_app.task
def backup_database_task():
    """Celery задача для backup базы данных."""
    return backup_database()

@celery_app.task
def health_check_task():
    """Периодическая проверка здоровья системы."""
    from health_check import run_health_check
    all_ok, message = run_health_check()
    if not all_ok:
        logger.error("Health check failed!")
    return all_ok

# --- Расписание для периодических задач (Celery Beat) ---
celery_app.conf.beat_schedule = {
    'check-due-dates-every-day': {
        'task': 'tasks.check_due_dates_and_notify',
        'schedule': crontab(hour=10, minute=0),
    },
    'check-overdue-books': {
        'task': 'tasks.check_overdue_books',
        'schedule': crontab(hour=10, minute=0),  # Каждый день в 10:00
    },
    'daily-database-backup': {
        'task': 'celery_tasks.backup_database_task',
        'schedule': crontab(hour=3, minute=0),  # Каждый день в 3:00
    },
    'health-check-every-hour': {
    'task': 'tasks.health_check_task',
    'schedule': crontab(minute=0),  # Каждый час
    },
}