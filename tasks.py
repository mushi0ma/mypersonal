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
    """Проверяет сроки сдачи книг и уведомляет должников и администратора."""
    print("Выполняется периодическая задача: проверка сроков сдачи книг...")
    try:
        with get_db_connection() as conn:
            overdue_entries = db_data.get_users_with_overdue_books(conn)

        if not overdue_entries:
            print("Просроченных книг не найдено.")
            return

        print(f"Найдено просроченных книг: {len(overdue_entries)}")
        for entry in overdue_entries:
            user_id = entry['user_id']
            username = entry['username']
            book_name = entry['book_name']
            due_date_str = entry['due_date'].strftime('%d.%m.%Y')

            # Уведомление для пользователя
            user_text = f"⏰ **Напоминание:** Срок возврата книги «{book_name}» истек {due_date_str}! Пожалуйста, верните ее в библиотеку."
            notify_user.delay(user_id=user_id, text=user_text, category='due_date')

            # Уведомление для администратора
            admin_text = f"❗️Пользователь @{username} просрочил книгу «{book_name}» (срок: {due_date_str})."
            notify_admin.delay(text=admin_text, category='overdue')

    except Exception as e:
        print(f"❌ Ошибка в периодической задаче check_due_dates: {e}")
        # Отправляем уведомление об ошибке в самой задаче
        notify_admin.delay(text=f"❗ Критическая ошибка в периодической задаче `check_due_dates_and_notify`: {e}", category='error')