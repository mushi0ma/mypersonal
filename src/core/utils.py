import logging
from functools import wraps
from time import time
from collections import defaultdict
import threading

from telegram import Update
from telegram.ext import ContextTypes

from src.core import tasks

logger = logging.getLogger(__name__)

# --- Данные для ограничения скорости ---
user_last_request = {}
user_violations = defaultdict(int)
violation_timestamps = defaultdict(float)

# --- Настройки очистки ---
CLEANUP_INTERVAL = 3600
VIOLATION_RESET_TIME = 86400

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

def rate_limit(seconds=2, alert_admins=False):
    """Декоратор для ограничения скорости запросов."""
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

# Запуск фоновой задачи очистки
cleanup_rate_limit_data()