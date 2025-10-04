# tasks.py
import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import telegram
import db_data
from db_utils import get_db_connection # Импортируем функцию для получения соединения

# Загружаем переменные окружения
load_dotenv()

# --- Настройка Celery ---
celery_app = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND")
)

# --- Инициализация API бота-уведомителя ---
try:
    notifier_bot = telegram.Bot(token=os.getenv("NOTIFICATION_BOT_TOKEN"))
    print("✅ Notifier Bot API initialized for Celery.")
except Exception as e:
    print(f"❌ Failed to initialize Notifier Bot API for Celery: {e}")
    notifier_bot = None

# --- НОВАЯ УМНАЯ ЗАДАЧА ---
@celery_app.task
def create_and_send_notification(user_id: int, text: str, category: str):
    """
    Главная задача: сохраняет уведомление в БД и отправляет его пользователю.
    """
    if not notifier_bot:
        print(f"❌ Notifier bot is not available. Cannot process notification for user {user_id}")
        return

    try:
        with get_db_connection() as conn:
            # 1. Сохраняем уведомление в базу данных
            db_data.create_notification(conn, user_id=user_id, text=text, category=category)

            # 2. Получаем telegram_id для отправки
            telegram_id = db_data.get_telegram_id_by_user_id(conn, user_id)
        
        # 3. Отправляем сообщение
        notifier_bot.send_message(chat_id=telegram_id, text=text, parse_mode='Markdown')
        print(f"✅ Notification for user {user_id} saved and sent to {telegram_id}.")

    except db_data.NotFoundError as e:
        print(f"❌ Error processing notification for user {user_id}: {e}")
    except telegram.error.TelegramError as e:
        # Мы не можем получить telegram_id здесь, если он не был получен ранее
        print(f"❌ Error sending notification to user {user_id}: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred in create_and_send_notification: {e}")


# ... (остальные задачи, такие как check_due_dates_and_notify, остаются без изменений) ...
@celery_app.task
def check_due_dates_and_notify():
    """Проверяет сроки сдачи книг и уведомляет должников."""
    print("Выполняется периодическая задача: проверка сроков сдачи книг...")
    # В будущем здесь будет логика, которая будет вызывать create_and_send_notification
    # with get_db_connection() as conn:
    #     users = db_data.get_users_with_overdue_books(conn)
    # for user in users:
    #     text = "Напоминание о сроке сдачи книги!"
    #     create_and_send_notification.delay(user['id'], text, 'due_date')

# --- Расписание для периодических задач (Celery Beat) ---
celery_app.conf.beat_schedule = {
    'check-due-dates-every-day': {
        'task': 'tasks.check_due_dates_and_notify',
        'schedule': crontab(hour=10, minute=0),
    },
}