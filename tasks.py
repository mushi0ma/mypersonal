# -*- coding: utf-8 -*-
import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import telegram

# Загружаем переменные окружения
load_dotenv()

# --- Настройка Celery ---
celery_app = Celery(
    'tasks',
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND")
)

# --- ИНИЦИАЛИЗАЦИЯ API НОВОГО БОТА-УВЕДОМИТЕЛЯ ---
try:
    # Используем новый токен из .env
    notifier_bot = telegram.Bot(token=os.getenv("NOTIFICATION_BOT_TOKEN"))
    print("✅ Notifier Bot API initialized for Celery.")
except Exception as e:
    print(f"❌ Failed to initialize Notifier Bot API for Celery: {e}")
    # Если токен не найден, бот будет None, и отправка не будет работать
    notifier_bot = None

# --- Описание задач ---

@celery_app.task
def send_telegram_message(chat_id: int, text: str, parse_mode: str = None):
    """Задача для отправки сообщения через бота-уведомителя."""
    if not notifier_bot:
        print(f"❌ Notifier bot is not available. Cannot send message to {chat_id}")
        return

    try:
        # Теперь сообщения отправляет notifier_bot
        notifier_bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        print(f"✅ Message successfully sent to user {chat_id} via Notifier Bot.")
    except telegram.error.TelegramError as e:
        print(f"❌ Error sending message to user {chat_id} via Notifier Bot: {e}")

# Пример периодической задачи для рассылки уведомлений (остается без изменений)
@celery_app.task
def check_due_dates_and_notify():
    """Проверяет сроки сдачи книг и уведомляет должников."""
    print("Выполняется периодическая задача: проверка сроков сдачи книг...")
    # Здесь должна быть логика получения должников из db_data
    # overdue_users = db_data.get_users_with_overdue_books()
    # for user in overdue_users:
    #     text = f"Уважаемый {user['full_name']}, напоминаем, что вам нужно вернуть книгу '{user['book_name']}'."
    #     send_telegram_message.delay(user['telegram_id'], text)


# --- Расписание для периодических задач (Celery Beat) ---
celery_app.conf.beat_schedule = {
    'check-due-dates-every-day': {
        'task': 'tasks.check_due_dates_and_notify',
        'schedule': crontab(hour=10, minute=0), # Каждый день в 10:00
    },
}