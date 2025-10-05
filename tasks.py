# tasks.py
import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import telegram
import db_data
from db_utils import get_db_connection

# Загружаем переменные окружения
load_dotenv()

# --- Настройка Celery ---
celery_app = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND")
)

# --- ИНИЦИАЛИЗАЦИЯ ДВУХ БОТОВ ---

# 1. Бот-уведомитель для ПОЛЬЗОВАТЕЛЕЙ
try:
    user_notifier_bot = telegram.Bot(token=os.getenv("NOTIFICATION_BOT_TOKEN"))
    print("✅ API бота-уведомителя для ПОЛЬЗОВАТЕЛЕЙ инициализировано.")
except Exception as e:
    print(f"❌ Не удалось инициализировать API бота-уведомителя для пользователей: {e}")
    user_notifier_bot = None

# 2. Бот-аудитор для АДМИНИСТРАТОРА
try:
    admin_notifier_bot = telegram.Bot(token=os.getenv("ADMIN_NOTIFICATION_BOT_TOKEN"))
    ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))
    print("✅ API бота-аудитора для АДМИНА инициализировано.")
except Exception as e:
    print(f"❌ Не удалось инициализировать API бота-аудитора для админа: {e}")
    admin_notifier_bot = None

# --- НОВЫЕ, СПЕЦИАЛИЗИРОВАННЫЕ ЗАДАЧИ ---

@celery_app.task
def notify_user(user_id: int, text: str, category: str = 'system'):
    """Сохраняет и отправляет уведомление КОНКРЕТНОМУ ПОЛЬЗОВАТЕЛЮ через Bot-Notifier."""
    if not user_notifier_bot:
        print(f"❌ Bot-Notifier недоступен. Уведомление для user_id={user_id} не отправлено.")
        return

    try:
        with get_db_connection() as conn:
            # Сначала сохраняем уведомление в БД, чтобы оно не потерялось
            db_data.create_notification(conn, user_id=user_id, text=text, category=category)
            # Затем получаем telegram_id для отправки
            telegram_id = db_data.get_telegram_id_by_user_id(conn, user_id)
        
        user_notifier_bot.send_message(chat_id=telegram_id, text=text, parse_mode='Markdown')
        print(f"✅ Уведомление '{category}' для user_id={user_id} отправлено на telegram_id={telegram_id}.")
    except Exception as e:
        print(f"❌ Ошибка в задаче notify_user для user_id={user_id}: {e}")

@celery_app.task
def notify_admin(text: str, category: str = 'audit'):
    """Отправляет системное уведомление АДМИНИСТРАТОРУ через Bot-Auditor."""
    if not admin_notifier_bot:
        print(f"❌ Bot-Auditor недоступен. Системное уведомление не отправлено.")
        return
    try:
        # Для админа мы не сохраняем уведомления в БД, а шлём их напрямую
        admin_notifier_bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text=text, parse_mode='Markdown')
        print(f"✅ Аудит-уведомление '{category}' для админа отправлено.")
    except Exception as e:
        print(f"❌ Ошибка в задаче notify_admin: {e}")

# --- ПЕРИОДИЧЕСКАЯ ЗАДАЧА (пока без изменений) ---
@celery_app.task
def check_due_dates_and_notify():
    """
    Проверяет книги с истекшим сроком и те, у которых срок скоро истечет,
    и отправляет соответствующие уведомления.
    """
    print("Выполняется периодическая задача: проверка сроков сдачи книг...")
    try:
        with get_db_connection() as conn:
            # --- Блок 1: Проверка просроченных книг (уже реализован) ---
            overdue_entries = db_data.get_users_with_overdue_books(conn)
            if overdue_entries:
                print(f"Найдено просроченных книг: {len(overdue_entries)}")
                for entry in overdue_entries:
                    # ... (логика отправки уведомлений о просрочке остается без изменений)
                    user_id, username, book_name, due_date = entry['user_id'], entry['username'], entry['book_name'], entry['due_date']
                    due_date_str = due_date.strftime('%d.%m.%Y')
                    user_text = f"❗️ **Просрочка:** Срок возврата книги «{book_name}» истек {due_date_str}! Пожалуйста, верните ее как можно скорее."
                    notify_user.delay(user_id=user_id, text=user_text, category='due_date')
                    admin_text = f"❗️Пользователь @{username} просрочил книгу «{book_name}» (срок: {due_date_str})."
                    notify_admin.delay(text=admin_text, category='overdue')

            # --- Блок 2: Проверка книг, у которых скоро истекает срок ---
            due_soon_entries = db_data.get_users_with_books_due_soon(conn, days_ahead=2)
            if due_soon_entries:
                print(f"Найдено книг с подходящим сроком возврата: {len(due_soon_entries)}")
                for entry in due_soon_entries:
                    user_id, book_name, due_date = entry['user_id'], entry['book_name'], entry['due_date']
                    due_date_str = due_date.strftime('%d.%m.%Y')
                    user_text = f"🔔 **Напоминание:** Срок возврата книги «{book_name}» истекает {due_date_str}. Пожалуйста, не забудьте ее вернуть."
                    notify_user.delay(user_id=user_id, text=user_text, category='due_date_reminder')
        
            if not overdue_entries and not due_soon_entries:
                print("Книг для отправки уведомлений не найдено.")

    except Exception as e:
        error_message = f"❗️ **Критическая ошибка в периодической задаче**\n\n`check_due_dates_and_notify`:\n`{e}`"
        print(f"❌ {error_message}")
        notify_admin.delay(text=error_message, category='error')

@celery_app.task
def notify_user(user_id: int, text: str, category: str = 'system', button_text: str = None, button_callback: str = None):
    """Сохраняет и отправляет уведомление КОНКРЕТНОМУ ПОЛЬЗОВАТЕЛЮ через Bot-Notifier."""
    if not user_notifier_bot:
        print(f"❌ Bot-Notifier недоступен. Уведомление для user_id={user_id} не отправлено.")
        return

    try:
        with get_db_connection() as conn:
            db_data.create_notification(conn, user_id=user_id, text=text, category=category)
            telegram_id = db_data.get_telegram_id_by_user_id(conn, user_id)

        # --- НОВАЯ ЛОГИКА ДЛЯ КНОПОК ---
        reply_markup = None
        if button_text and button_callback:
            keyboard = [[telegram.InlineKeyboardButton(button_text, callback_data=button_callback)]]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        user_notifier_bot.send_message(
            chat_id=telegram_id, 
            text=text, 
            parse_mode='Markdown',
            reply_markup=reply_markup # Добавляем клавиатуру
        )
        print(f"✅ Уведомление '{category}' для user_id={user_id} отправлено на telegram_id={telegram_id}.")
    except Exception as e:
        print(f"❌ Ошибка в задаче notify_user для user_id={user_id}: {e}")