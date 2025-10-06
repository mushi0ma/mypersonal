import logging
import re
from functools import wraps
from time import time
from collections import defaultdict
import threading

from telegram import Update
from telegram.ext import ContextTypes

from src import tasks

logger = logging.getLogger(__name__)

# --- Данные для ограничения скорости ---
user_last_request = {}
user_violations = defaultdict(int)
violation_timestamps = defaultdict(float)

# --- Настройки очистки ---
CLEANUP_INTERVAL = 3600  # Очистка каждый час
VIOLATION_RESET_TIME = 86400  # Сброс нарушений через 24 часа

def cleanup_rate_limit_data():
    """Периодическая очистка устаревших данных для rate limiting."""
    now = time()
    expired_users = [
        user_id for user_id, timestamp in violation_timestamps.items()
        if now - timestamp > VIOLATION_RESET_TIME
    ]
    for user_id in expired_users:
        user_violations.pop(user_id, None)
        violation_timestamps.pop(user_id, None)
        user_last_request.pop(user_id, None)
    if expired_users:
        logger.info(f"Очищено {len(expired_users)} записей rate limit")
    threading.Timer(CLEANUP_INTERVAL, cleanup_rate_limit_data).start()

# --- Декоратор для ограничения скорости запросов ---
def rate_limit(seconds=2, alert_admins=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            now = time()
            if user_id in user_last_request:
                time_passed = now - user_last_request[user_id]
                if time_passed < seconds:
                    user_violations[user_id] += 1
                    violation_timestamps[user_id] = now
                    logger.warning(
                        f"Rate limit exceeded by user {user_id} "
                        f"({update.effective_user.username}). "
                        f"Violations: {user_violations[user_id]}"
                    )
                    if alert_admins and user_violations[user_id] > 10:
                        tasks.notify_admin.delay(
                            text=f"⚠️ **Подозрительная активность**\n\n"
                                 f"**User ID:** `{user_id}`\n"
                                 f"**Username:** @{update.effective_user.username or 'неизвестно'}\n"
                                 f"**Нарушений rate limit:** {user_violations[user_id]}\n"
                                 f"**Функция:** `{func.__name__}`",
                            category='security_alert'
                        )
                        user_violations[user_id] = 0
                    wait_time = int(seconds - time_passed) + 1
                    if update.message:
                        await update.message.reply_text(
                            f"⏱ **Пожалуйста, подождите**\n\n"
                            f"Вы отправляете запросы слишком часто. "
                            f"Попробуйте снова через {wait_time} сек.",
                            parse_mode='Markdown'
                        )
                    elif update.callback_query:
                        await update.callback_query.answer(
                            f"⏱ Подождите {wait_time} сек.",
                            show_alert=True
                        )
                    return
            user_last_request[user_id] = now
            user_violations[user_id] = 0
            return await func(update, context)
        return wrapper
    return decorator

# --- Вспомогательные функции ---

def normalize_phone_number(contact: str) -> str:
    """Приводит номер телефона к стандартному формату +7."""
    clean_digits = re.sub(r'\D', '', contact)
    if clean_digits.startswith('8') and len(clean_digits) == 11:
        return '+7' + clean_digits[1:]
    if clean_digits.startswith('7') and len(clean_digits) == 11:
        return '+' + clean_digits
    if re.match(r"^\+\d{1,14}$", contact):
        return contact
    return contact

def get_user_borrow_limit(status: str) -> int:
    """Возвращает лимит книг для пользователя в зависимости от его статуса."""
    return {'студент': 3, 'учитель': 5}.get(status.lower(), 0)

# Запуск фоновой задачи очистки
cleanup_rate_limit_data()