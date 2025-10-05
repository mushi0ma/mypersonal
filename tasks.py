# tasks.py
import os
import logging
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import telegram
import db_data
from db_utils import get_db_connection

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

@celery_app.task
def broadcast_new_book(book_id: int):
    """Рассылает уведомление о новой книге всем пользователям."""
    logger.info(f"Запущена рассылка о новой книге с ID: {book_id}")
    try:
        with get_db_connection() as conn:
            book = db_data.get_book_card_details(conn, book_id)
            all_user_ids = db_data.get_all_user_ids(conn)
        
        text = f"🆕 **В библиотеке пополнение!**\n\nКнига «{book['name']}» от автора {book['author']} была добавлена в каталог."
        button_text = "📖 Посмотреть карточку книги"
        button_callback = f"view_book_{book_id}"

        for user_id in all_user_ids:
            notify_user(
                user_id=user_id,
                text=text,
                category='new_arrival',
                button_text=button_text,
                button_callback=button_callback
            )
        logger.info(f"Рассылка о новой книге завершена для {len(all_user_ids)} пользователей.")
        notify_admin(f"🚀 Успешно разослано уведомление о новой книге «{book['name']}» для {len(all_user_ids)} пользователей.")
    except Exception as e:
        logger.error(f"Ошибка в задаче broadcast_new_book: {e}")
        notify_admin(f"❗️ Ошибка при рассылке о новой книге (ID: {book_id}): {e}")

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

# --- Расписание для периодических задач (Celery Beat) ---
celery_app.conf.beat_schedule = {
    'check-due-dates-every-day': {
        'task': 'tasks.check_due_dates_and_notify',
        'schedule': crontab(hour=10, minute=0),
    },
}