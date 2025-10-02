# -*- coding: utf-8 -*-
import os
from celery import Celery
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

# --- Инициализация Telegram Bot API ---
bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

@celery_app.task
def send_telegram_message(chat_id: int, text: str, parse_mode: str = None):
    """Универсальная задача для отправки сообщения в Telegram."""
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except telegram.error.TelegramError as e:
        print(f"❌ Ошибка отправки Telegram пользователю {chat_id}: {e}")