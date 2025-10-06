# -*- coding: utf-8 -*-
import logging
from logging.handlers import RotatingFileHandler
import uuid
import os
import random
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram import Bot
from functools import wraps
from time import time
from collections import defaultdict
import threading

# --- ИМПОРТ ФУНКЦИЙ БАЗЫ ДАННЫХ И ХЕШИРОВАНИЯ ---
import db_data
from db_utils import get_db_connection, hash_password
import tasks

# --- ИМПОРТ СЕРВИСОВ ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

handler = RotatingFileHandler('librarybot.log', maxBytes=10485760, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# --- Загрузка конфигурации из .env ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN")  # ✅ ДОБАВЛЕНО
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

# Создаем отдельный экземпляр для бота-уведомителя
notification_bot = Bot(token=NOTIFICATION_BOT_TOKEN)

# --- СОСТОЯНИЯ ДИАЛОГА ---
(
    START_ROUTES,
    REGISTER_NAME, REGISTER_DOB, REGISTER_CONTACT,
    REGISTER_VERIFY_CODE, REGISTER_STATUS,
    REGISTER_USERNAME, REGISTER_PASSWORD, REGISTER_CONFIRM_PASSWORD,
    LOGIN_CONTACT, LOGIN_PASSWORD,
    FORGOT_PASSWORD_CONTACT, FORGOT_PASSWORD_VERIFY_CODE,
    FORGOT_PASSWORD_SET_NEW, FORGOT_PASSWORD_CONFIRM_NEW,
    USER_MENU, USER_BORROW_BOOK_SELECT,
    USER_RETURN_BOOK,
    USER_RATE_BOOK_SELECT, USER_RATE_BOOK_RATING, USER_DELETE_CONFIRM,
    USER_RESERVE_BOOK_CONFIRM,
    USER_VIEW_HISTORY, USER_NOTIFICATIONS,
    SHOWING_GENRES, SHOWING_GENRE_BOOKS,
    GETTING_SEARCH_QUERY, SHOWING_SEARCH_RESULTS,

    # --- Новые состояния для редактирования профиля ---
    EDIT_PROFILE_MENU, EDITING_FULL_NAME, EDITING_CONTACT,
    EDITING_PASSWORD_CURRENT, EDITING_PASSWORD_NEW, EDITING_PASSWORD_CONFIRM,
    AWAITING_NOTIFICATION_BOT,
    AWAIT_CONTACT_VERIFICATION_CODE,
    VIEWING_TOP_BOOKS, SHOWING_AUTHORS_LIST, VIEWING_AUTHOR_CARD, 
    SEARCHING_AUTHORS
) = range(40)

user_last_request = {}
user_violations = defaultdict(int)
violation_timestamps = defaultdict(float)

# Настройки очистки
CLEANUP_INTERVAL = 3600  # Очистка каждый час
VIOLATION_RESET_TIME = 86400  # Сброс нарушений через 24 часа

def cleanup_rate_limit_data():
    """Периодическая очистка устаревших данных."""
    now = time()
    
    # Очищаем старые нарушения
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
    
    # Запланировать следующую очистку
    threading.Timer(CLEANUP_INTERVAL, cleanup_rate_limit_data).start()

# Запустить очистку при старте
cleanup_rate_limit_data()


# --------------------------
# --- Вспомогательные функции ---
# --------------------------

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
                    violation_timestamps[user_id] = now  # ✅ ОБНОВЛЯЕМ TIMESTAMP
                    
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

def normalize_phone_number(contact: str) -> str:
    clean_digits = re.sub(r'\D', '', contact)
    if clean_digits.startswith('8') and len(clean_digits) == 11:
        return '+7' + clean_digits[1:]
    if clean_digits.startswith('7') and len(clean_digits) == 11:
        return '+' + clean_digits
    if re.match(r"^\+\d{1,14}$", contact):
        return contact
    return contact

def get_user_borrow_limit(status):
    return {'студент': 3, 'учитель': 5}.get(status.lower(), 0)

@rate_limit(seconds=5, alert_admins=True)
async def send_verification_message(contact_info: str, code: str, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    """
    Отправляет код верификации:
    1. На email (если это email)
    2. Через notification_bot в Telegram (если пользователь уже привязал telegram_id)
    3. Через основного бота (fallback для первичной регистрации)
    """
    # Попытка отправить на Email
    if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", contact_info):
        try:
            message_body = f"Ваш код для библиотеки: {code}"
            message = Mail(
                from_email=os.getenv("FROM_EMAIL"), 
                to_emails=contact_info, 
                subject='Код верификации', 
                html_content=f'<strong>{message_body}</strong>'
            )
            sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
            sg.send(message)
            context.user_data['verification_method'] = 'email'
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке email: {e}")
            # Продолжаем попытку отправки через Telegram
    
    # ✅ ИСПРАВЛЕНИЕ: Пытаемся отправить через notification_bot
    try:
        # Проверяем, есть ли у пользователя привязанный telegram_id
        # Это актуально для восстановления пароля и смены контакта
        user_telegram_id = None
        try:
            with get_db_connection() as conn:
                # Пытаемся найти пользователя по контакту
                user = db_data.get_user_by_login(conn, contact_info)
                user_telegram_id = user.get('telegram_id')
        except db_data.NotFoundError:
            # Пользователь еще не существует (первичная регистрация)
            pass
        
        if user_telegram_id:
            # Отправляем через notification_bot
            message_body = f"🔐 **Код верификации**\n\nВаш код для библиотеки: `{code}`"
            await notification_bot.send_message(
                chat_id=user_telegram_id, 
                text=message_body,
                parse_mode='Markdown'
            )
            context.user_data['verification_method'] = 'notification_bot'
            logger.info(f"Код отправлен через notification_bot пользователю {user_telegram_id}")
            return True
        else:
            # Fallback: отправляем через основного бота (для первичной регистрации)
            return await send_self_code_telegram(code, context, telegram_id)
            
    except Exception as e:
        logger.error(f"Ошибка при отправке через notification_bot: {e}")
        # Последний fallback - через основного бота
        return await send_self_code_telegram(code, context, telegram_id)

def get_back_button(current_state_const: int) -> list:
    """Генерирует кнопку 'Назад', используя имя константы состояния."""
    state_name = [name for name, val in globals().items() if val == current_state_const and name.isupper() and '_' in name][0]
    return [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_{state_name}")]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик команды /cancel. 
    Используется как fallback для выхода из вложенного ConversationHandler.
    """
    if update.message:
        message = update.message
        # Отправка сообщения пользователю
        await message.reply_text("❌ Действие отменено. Возвращаемся в меню.")
        
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        # Редактирование или отправка нового сообщения (зависит от контекста)
        await query.edit_message_text("❌ Действие отменено. Возвращаемся в меню.")
    
    return ConversationHandler.END

async def send_self_code_telegram(code: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Отправляет код верификации от имени текущего (основного) бота."""
    try:
        message_body = f"📲 Ваш код для библиотеки: `{code}`\n\n_Для получения уведомлений рекомендуем подписаться на бота-уведомителя._"
        await context.bot.send_message(
            chat_id=chat_id, 
            text=message_body,
            parse_mode='Markdown'
        )
        context.user_data['verification_method'] = 'self_telegram'
        logger.info(f"Код отправлен через основного бота пользователю {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке кода самому себе: {e}")
        return False
    

# --------------------------
# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начальная точка диалога, показывает кнопки входа/регистрации."""
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("Войти", callback_data="login")],
        [InlineKeyboardButton("Зарегистрироваться", callback_data="register")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text("Добро пожаловать в библиотеку! 📚", reply_markup=reply_markup)
    else:
        if update.message:
            await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Добро пожаловать в библиотеку! 📚", reply_markup=reply_markup)
        
    return START_ROUTES

# --- ФУНКЦИИ РЕГИСТРАЦИИ ---

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс регистрации."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['registration'] = {}
    await query.edit_message_text("📝 Начинаем регистрацию. Введите ваше **ФИО**:", parse_mode='Markdown')
    return REGISTER_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает ФИО и запрашивает дату рождения."""
    context.user_data['registration']['full_name'] = update.message.text
    await update.message.reply_text("🎂 Введите **дату рождения** (ДД.ММ.ГГГГ):", parse_mode='Markdown')
    return REGISTER_DOB

async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает дату рождения и запрашивает контакт."""
    dob = update.message.text
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", dob):
        await update.message.reply_text("❌ Неверный формат. Используйте **ДД.ММ.ГГГГ**.")
        return REGISTER_DOB
    context.user_data['registration']['dob'] = dob
    await update.message.reply_text("📞 Введите ваш **контакт** (email, телефон или @username):", parse_mode='Markdown')
    return REGISTER_CONTACT

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    try:
        with get_db_connection() as conn:
            if db_data.get_user_by_login(conn, contact_processed):
                await update.message.reply_text("🤔 Пользователь с такими данными уже существует. Попробуйте войти или введите другой контакт.")
                return REGISTER_CONTACT
    except db_data.NotFoundError:
        pass
    context.user_data['registration']['contact_info'] = contact_processed
    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code
    sent = await send_verification_message(contact_processed, code, context, update.effective_user.id)
    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_CONTACT)])
    if sent:
        await update.message.reply_text(f"📲 На ваш контакт ({contact_processed}) отправлен **код верификации**. Введите его:", reply_markup=reply_markup, parse_mode='Markdown')
        return REGISTER_VERIFY_CODE
    else:
        await update.message.reply_text("⚠️ Не удалось отправить код. Проверьте правильность введенных данных.", reply_markup=reply_markup)
        return REGISTER_CONTACT

async def verify_registration_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет код верификации и запрашивает статус."""
    if update.message.text == context.user_data.get('verification_code'):
        keyboard = [
            [InlineKeyboardButton("Студент", callback_data="студент"), InlineKeyboardButton("Преподаватель", callback_data="учитель")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("✅ Код верный! Теперь выберите ваш статус:", reply_markup=reply_markup)
        context.user_data.pop('verification_code', None)
        return REGISTER_STATUS
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте еще раз.")
        return REGISTER_VERIFY_CODE

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает статус и запрашивает юзернейм."""
    query = update.callback_query
    await query.answer()
    context.user_data['registration']['status'] = query.data
    await query.edit_message_text("🧑‍💻 Придумайте **юзернейм** (на английском, без пробелов, например: `ivanov21`):", parse_mode='Markdown')
    return REGISTER_USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает юзернейм и запрашивает пароль."""
    username = update.message.text
    if not re.match(r"^[a-zA-Z0-9_]{3,}$", username):
        await update.message.reply_text("❌ Неверный формат. Юзернейм должен быть не короче 3 символов и состоять из английских букв, цифр и знака '_'.")
        return REGISTER_USERNAME
    context.user_data['registration']['username'] = username
    await update.message.reply_text("🔑 Создайте **пароль** (минимум 8 символов):", parse_mode='Markdown')
    return REGISTER_PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает первый пароль, сохраняет его и запрашивает подтверждение."""
    password = update.message.text
    
    # ✅ НЕМЕДЛЕННО УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с паролем: {e}")
    
    # Валидация...
    if len(password) < 8:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароль слишком короткий. Минимум **8 символов**.\n\nПопробуйте снова:",
            parse_mode='Markdown'
        )
        return REGISTER_PASSWORD
    
    has_letter = any(c.isalpha() for c in password)
    has_digit_or_special = any(c.isdigit() or not c.isalnum() for c in password)
    
    if not (has_letter and has_digit_or_special):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароль должен содержать:\n"
                 "• Минимум 8 символов\n"
                 "• Буквы (A-Z, a-z)\n"
                 "• Цифры (0-9) или спецсимволы (!@#$...)\n\n"
                 "Попробуйте снова:",
            parse_mode='Markdown'
        )
        return REGISTER_PASSWORD
    
    context.user_data['registration']['password_temp'] = password
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👍 Отлично. Теперь **введите пароль еще раз** для подтверждения:", 
        parse_mode='Markdown'
    )
    return REGISTER_CONFIRM_PASSWORD

async def get_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает сбор данных, создает пользователя в БД
    и отправляет его на подписку к боту-уведомителю.
    """
    password_confirm = update.message.text
    
    # ✅ НЕМЕДЛЕННО УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с подтверждением пароля: {e}")

    # Проверка совпадения паролей
    if context.user_data['registration'].get('password_temp') != password_confirm:
        # Отправляем новое сообщение вместо ответа на удаленное
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароли не совпадают. Пожалуйста, придумайте пароль заново."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔑 Создайте **пароль** (минимум 8 символов):",
            parse_mode='Markdown'
        )
        return REGISTER_PASSWORD

    context.user_data['registration']['password'] = context.user_data['registration'].pop('password_temp')
    
    # Отправляем новое сообщение
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✅ Пароль сохранен!\n\n⏳ Создаю ваш аккаунт...",
        parse_mode='Markdown'
    )
    
    # --- НАЧАЛО НОВОЙ ЛОГИКИ ---
    user_data = context.user_data['registration']
    
    try:
        with get_db_connection() as conn:
            # 1. Создаем пользователя БЕЗ telegram_id
            user_id = db_data.add_user(conn, user_data) 
            db_data.log_activity(conn, user_id=user_id, action="registration_start")
            
            # 2. Генерируем и сохраняем уникальный код для привязки
            reg_code = db_data.set_registration_code(conn, user_id)
            context.user_data['user_id_for_activation'] = user_id

        # 3. Получаем юзернейм бота-уведомителя из .env
        notifier_bot_username = os.getenv("NOTIFICATION_BOT_USERNAME", "ВашБотУведомитель")
        
        # 4. Формируем "глубокую ссылку" и кнопки
        keyboard = [
            [InlineKeyboardButton("🤖 Подписаться на уведомления", url=f"https://t.me/{notifier_bot_username}?start={reg_code}")],
            [InlineKeyboardButton("✅ Я подписался", callback_data="confirm_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 5. Отправляем финальное сообщение и переходим в состояние ожидания
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🎉 **Отлично! Аккаунт создан.**\n\n"
                "**Последний шаг:** подпишитесь на нашего бота-уведомителя. "
                "Он будет присылать вам коды верификации и важные оповещения.\n\n"
                "👉 Нажмите на кнопку ниже, запустите бота, "
                "а затем вернитесь сюда и нажмите **'Я подписался'**."
            ),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return AWAITING_NOTIFICATION_BOT

    except db_data.UserExistsError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ошибка: этот юзернейм или контакт уже заняты."
        )
        context.user_data.clear()
        return await start(update, context)
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при регистрации: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при регистрации**\n\n**Функция:** `get_password_confirmation`\n**Ошибка:** `{e}`")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Произошла системная ошибка. Администратор уже уведомлен."
        )
        context.user_data.clear()
        return await start(update, context)

async def check_notification_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет, привязал ли пользователь telegram_id через бота-уведомителя."""
    query = update.callback_query
    await query.answer()
    
    user_id = context.user_data.get('user_id_for_activation')
    if not user_id:
        await query.edit_message_text(
            "❌ Произошла ошибка сессии. Пожалуйста, начните регистрацию заново с /start."
        )
        return ConversationHandler.END

    try:
        with get_db_connection() as conn:
            user = db_data.get_user_by_id(conn, user_id)
        
        if user.get('telegram_id'):
            # ✅ Пользователь успешно привязал Telegram
            with get_db_connection() as conn:
                db_data.log_activity(conn, user_id=user_id, action="registration_finish")

            # Отправляем уведомление админу
            admin_text = (
                f"✅ **Новая регистрация**\n\n"
                f"**Пользователь:** @{user.get('telegram_username', user.get('username'))}\n"
                f"**ID:** {user_id}\n"
                f"**ФИО:** {user.get('full_name')}\n"
                f"**Статус:** {user.get('status')}"
            )
            tasks.notify_admin.delay(text=admin_text, category='new_user')

            await query.edit_message_text(
                "🎉 **Регистрация завершена!**\n\n"
                "Теперь вы можете войти в систему."
            )
            context.user_data.clear()
            return await start(update, context)
        else:
            # Пользователь еще не запустил notification_bot
            await query.answer(
                "⚠️ Вы еще не запустили бота-уведомителя. Пожалуйста, нажмите на кнопку выше.", 
                show_alert=True
            )
            return AWAITING_NOTIFICATION_BOT
            
    except Exception as e:
        user_id_str = context.user_data.get('user_id_for_activation', 'Неизвестно')
        logger.error(f"Ошибка при проверке подписки для user_id {user_id_str}: {e}", exc_info=True)
        tasks.notify_admin.delay(
            text=f"❗️ **Критическая ошибка при проверке подписки**\n\n"
                 f"**UserID:** `{user_id_str}`\n"
                 f"**Ошибка:** `{e}`"
        )
        await query.edit_message_text("❌ Произошла системная ошибка. Администратор уведомлен.")
        return ConversationHandler.END

# --- ФУНКЦИИ ВХОДА ---

async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🤔 Забыли пароль?", callback_data="forgot_password")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👤 Введите ваш **юзернейм** или **контакт** для входа:", reply_markup=reply_markup, parse_mode='Markdown')
    return LOGIN_CONTACT

async def get_login_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    try:
        with get_db_connection() as conn:
            user = db_data.get_user_by_login(conn, contact_processed)
        context.user_data['login_user'] = user

        context.user_data['login_attempts'] = 0

        await update.message.reply_text("🔑 Введите ваш **пароль**:", parse_mode='Markdown')
        return LOGIN_PASSWORD
    except db_data.NotFoundError:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте еще раз или зарегистрируйтесь.")
        return LOGIN_CONTACT

# В librarybot.py, добавить:

login_lockouts = {}  # {user_id: (lockout_until_timestamp, attempts)}

async def check_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = context.user_data['login_user']
    user_id = user['id']
    stored_hash = user['password_hash']
    input_password = update.message.text
    
    # ✅ ПРОВЕРКА БЛОКИРОВКИ
    if user_id in login_lockouts:
        lockout_until, _ = login_lockouts[user_id]
        if time() < lockout_until:
            remaining = int(lockout_until - time())
            await update.message.reply_text(
                f"🔒 Вход заблокирован на {remaining} секунд из-за множественных неудачных попыток."
            )
            return LOGIN_PASSWORD
        else:
            # Блокировка истекла
            login_lockouts.pop(user_id, None)

    # Удаляем пароль
    try:
        await update.message.delete()
    except:
        pass

    if hash_password(input_password) == stored_hash:
        # Успешный вход
        with get_db_connection() as conn:
            db_data.log_activity(conn, user_id=user['id'], action="login")
        
        context.user_data.pop('login_attempts', None)
        login_lockouts.pop(user_id, None)  # ✅ УБИРАЕМ БЛОКИРОВКУ
        
        await update.message.reply_text(f"🎉 Добро пожаловать, {user['full_name']}!")
        context.user_data['current_user'] = user
        context.user_data.pop('login_user')
        return await user_menu(update, context)
    else:
        attempts = context.user_data.get('login_attempts', 0) + 1
        context.user_data['login_attempts'] = attempts

        if attempts >= 3:
            # ✅ БЛОКИРУЕМ НА 5 МИНУТ
            lockout_duration = 300  # 5 минут
            lockout_until = time() + lockout_duration
            login_lockouts[user_id] = (lockout_until, attempts)
            
            admin_text = (
                f"🔒 **[АУДИТ БЕЗОПАСНОСТИ]**\n\n"
                f"Замечено {attempts} неудачных попытки входа для пользователя "
                f"@{user.get('username', user.get('contact_info'))}.\n\n"
                f"Вход заблокирован на 5 минут."
            )
            tasks.notify_admin.delay(text=admin_text, category='security_alert')
            
            context.user_data['login_attempts'] = 0
            
            await update.message.reply_text(
                f"❌ Неверный пароль. Вы исчерпали количество попыток.\n\n"
                f"🔒 Вход заблокирован на 5 минут."
            )
            return await start_login(update, context)
        else:
            await update.message.reply_text(f"❌ Неверный пароль. Осталось попыток: {3 - attempts}.")
            return LOGIN_PASSWORD

# --- ФУНКЦИИ ВОССТАНОВЛЕНИЯ ПАРОЛЯ ---

async def start_forgot_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔑 Введите ваш **юзернейм** или **контакт** для сброса пароля:", parse_mode='Markdown')
    return FORGOT_PASSWORD_CONTACT

async def get_forgot_password_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    try:
        with get_db_connection() as conn:
            user = db_data.get_user_by_login(conn, contact_processed)
    except db_data.NotFoundError:
        await update.message.reply_text("❌ Пользователь с такими данными не найден.")
        return FORGOT_PASSWORD_CONTACT
    contact_to_verify = user['contact_info']
    user_telegram_id = user['telegram_id'] if user['telegram_id'] else update.effective_user.id
    code = str(random.randint(100000, 999999))
    context.user_data['forgot_password_code'] = code
    context.user_data['forgot_password_contact'] = user['contact_info'] # Используем основной контакт
    sent = await send_verification_message(contact_to_verify, code, context, user_telegram_id)
    if sent:
        await update.message.reply_text(f"📲 Код верификации отправлен на {contact_to_verify}. Введите его:")
        return FORGOT_PASSWORD_VERIFY_CODE
    else:
        await update.message.reply_text("⚠️ Не удалось отправить код верификации. Попробуйте еще раз.")
        return FORGOT_PASSWORD_CONTACT

async def verify_forgot_password_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == context.user_data.get('forgot_password_code'):
        await update.message.reply_text("✅ Код верный! Введите **новый пароль**:", parse_mode='Markdown')
        context.user_data.pop('forgot_password_code', None)
        return FORGOT_PASSWORD_SET_NEW
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте еще раз.")
        return FORGOT_PASSWORD_VERIFY_CODE

async def set_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_password = update.message.text
    hidden_password_text = "•" * len(new_password)
    await update.message.edit_text(f"(пароль скрыт) {hidden_password_text}")
    if not re.match(r"^(?=.*[A-Za-z])(?=.*\d|.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$", new_password):
        await update.message.reply_text("❌ Пароль не соответствует требованиям (минимум 8 символов, буквы и цифры/спецсимволы). Попробуйте снова.")
        return FORGOT_PASSWORD_SET_NEW
    context.user_data['forgot_password_temp'] = new_password
    await update.message.reply_text("👍 Пожалуйста, **введите новый пароль еще раз**:", parse_mode='Markdown')
    return FORGOT_PASSWORD_CONFIRM_NEW

async def confirm_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password_confirm = update.message.text
    hidden_password_text = "•" * len(password_confirm)
    await update.message.edit_text(f"(пароль скрыт) {hidden_password_text}")
    if context.user_data.get('forgot_password_temp') != password_confirm:
        await update.message.reply_text("❌ Пароли не совпадают. Пожалуйста, введите новый пароль заново.")
        return FORGOT_PASSWORD_SET_NEW
    login_query = context.user_data['forgot_password_contact']
    final_password = context.user_data.pop('forgot_password_temp')
    try:
        with get_db_connection() as conn:
            db_data.update_user_password(conn, login_query, final_password)
        await update.message.reply_text("🎉 Пароль успешно обновлен! Теперь вы можете войти.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении пароля: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при обновлении пароля**\n\n**Функция:** `confirm_new_password`\n**Ошибка:** `{e}`")
        await update.message.reply_text("❌ Произошла ошибка. Администратор уведомлен. Попробуйте позже.")
        return FORGOT_PASSWORD_SET_NEW
    context.user_data.clear()
    return await start(update, context)

# --- ФУНКЦИИ ПОЛЬЗОВАТЕЛЬСКОГО МЕНЮ ---

async def user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Если мы только что отредактировали профиль, покажем его вместо меню
    if context.user_data.pop('just_edited_profile', False):
        return await view_profile(update, context)

    user = context.user_data.get('current_user')
    if not user:
        return await start(update, context)
    
    try:
        with get_db_connection() as conn:
            borrowed_books = db_data.get_borrowed_books(conn, user['id'])
            # Обновляем данные пользователя в сессии
            context.user_data['current_user'] = db_data.get_user_by_id(conn, user['id'])
            user = context.user_data['current_user']
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных меню: {e}")
        borrowed_books = []

    borrow_limit = get_user_borrow_limit(user['status'])

    message_text = (
        f"**🏠 Главное меню**\n"
        f"Добро пожаловать, {user['full_name']}!\n\n"
        f"📖 У вас на руках: **{len(borrowed_books)}/{borrow_limit}** книг."
    )
    keyboard = [
        [
            InlineKeyboardButton("🔎 Поиск книг", callback_data="search_book"),
            InlineKeyboardButton("📚 По жанру", callback_data="find_by_genre")
        ],
        [
            InlineKeyboardButton("👥 Все авторы", callback_data="show_authors"),
            InlineKeyboardButton("🏆 Топ книг", callback_data="top_books")
        ],
        [
            InlineKeyboardButton("📥 Взять книгу", callback_data="search_book"),
            InlineKeyboardButton("📤 Вернуть книгу", callback_data="user_return")
        ],
        [
            InlineKeyboardButton("⭐ Оценить книгу", callback_data="user_rate"),
            InlineKeyboardButton("📜 История", callback_data="user_history")
        ],
        [
            InlineKeyboardButton("👤 Профиль", callback_data="user_profile"),
            InlineKeyboardButton("📬 Уведомления", callback_data="user_notifications")
        ],
        [
            InlineKeyboardButton("🚪 Выйти", callback_data="logout")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            message_text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
    return USER_MENU

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = context.user_data.get('current_user')
    with get_db_connection() as conn:
        db_data.log_activity(conn, user_id=user['id'], action="logout")
        if db_data.get_borrowed_books(conn, user['id']):
            keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Вы не можете выйти, пока у вас есть книги на руках!", reply_markup=reply_markup)
            return USER_MENU
    context.user_data.clear()
    await query.edit_message_text("✅ Вы успешно вышли. Введите /start, чтобы снова войти.")
    return ConversationHandler.END

async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает стилизованный профиль пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    try:
        with get_db_connection() as conn:
            user_profile = db_data.get_user_profile(conn, user_id)
            borrowed_books = db_data.get_borrowed_books(conn, user_id)
        borrow_limit = get_user_borrow_limit(user_profile['status'])
        reg_date_str = user_profile['registration_date'].strftime('%d.%m.%Y')
        message_parts = [
            f"👤 **Личный кабинет** 👤", f"`-------------------------`",
            f"🔹 **Имя:** `{user_profile['full_name']}`",
            f"🔹 **Юзернейм:** `{user_profile['username']}`",
            f"🔹 **Статус:** `{user_profile['status'].capitalize()}`",
            f"🔹 **Контакт:** `{user_profile['contact_info']}`",
            f"🔹 **В библиотеке с:** `{reg_date_str}`", f"`-------------------------`",
            f"📚 **Взятые книги ({len(borrowed_books)}/{borrow_limit})**"
        ]
        if borrowed_books:
            for i, borrowed in enumerate(borrowed_books):
                message_parts.append(f"  {i+1}. `{borrowed['book_name']}` (автор: {borrowed['author_name']})")
        else:
            message_parts.append("  _У вас нет активных займов._")
        keyboard = [
            [InlineKeyboardButton("✏️ Редактировать профиль", callback_data="edit_profile")],
            [InlineKeyboardButton("📜 Перейти к истории", callback_data="user_history")],
            [InlineKeyboardButton("🗑️ Удалить аккаунт", callback_data="user_delete_account")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    except db_data.NotFoundError:
        await query.edit_message_text("❌ Не удалось найти ваш профиль. Пожалуйста, войдите снова.")
        context.user_data.clear()
        return await start(update, context)
    return USER_MENU

async def view_borrow_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает историю заимствований пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        history = db_data.get_user_borrow_history(conn, user_id)
    message_parts = ["**📜 Ваша история взятых книг**\n"]
    if history:
        for item in history:
            return_date_str = item['return_date'].strftime('%d.%m.%Y') if item['return_date'] else "На руках"
            borrow_date_str = item['borrow_date'].strftime('%d.%m.%Y')
            rating_str = ""
            if item['rating']:
                stars = "⭐" * item['rating']
                rating_str = f" (ваша оценка: {stars})"
            message_parts.append(f"📖 **{item['book_name']}**\n   - Взята: `{borrow_date_str}`\n   - Возвращена: `{return_date_str}`{rating_str}")
    else:
        message_parts.append("Вы еще не брали ни одной книги.")
    keyboard = [[InlineKeyboardButton("⬅️ Назад в профиль", callback_data="user_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    return USER_MENU

# --- ФУНКЦИИ РАБОТЫ С КНИГАМИ ---

@rate_limit(seconds=3, alert_admins=True)
async def process_borrow_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[2])
    user_id = context.user_data['current_user']['id']
    
    try:
        with get_db_connection() as conn:
            # Получаем детали книги для сообщений
            selected_book = db_data.get_book_by_id(conn, book_id)
            
            if selected_book['available_quantity'] > 0:
                borrowed_books = db_data.get_borrowed_books(conn, user_id)
                borrow_limit = get_user_borrow_limit(context.user_data['current_user']['status'])

                if len(borrowed_books) >= borrow_limit:
                    await query.edit_message_text(f"⚠️ Вы достигли лимита ({borrow_limit}) на заимствование.")
                    # Возвращаемся в меню через 3 секунды, чтобы пользователь успел прочитать
                    # (Это необязательное, но приятное UX улучшение)
                    # await asyncio.sleep(3) 
                    return await user_menu(update, context)

                # --- ИЗМЕНЕНИЯ ЗДЕСЬ ---

                # 1. Вызываем функцию, которая возвращает due_date
                due_date = db_data.borrow_book(conn, user_id, selected_book['id'])
                db_data.log_activity(conn, user_id=user_id, action="borrow_book", details=f"Book ID: {selected_book['id']}")

                # 2. Формируем и отправляем асинхронное уведомление
                due_date_str = due_date.strftime('%d.%m.%Y')
                notification_text = f"✅ Вы успешно взяли книгу «{selected_book['name']}».\n\nПожалуйста, верните ее до **{due_date_str}**."
                tasks.notify_user.delay(user_id=user_id, text=notification_text, category='confirmation')

                # 3. Даем пользователю быстрый ответ и возвращаем в меню
                await query.edit_message_text("👍 Отлично! Подтверждение отправлено вам в бот-уведомитель.")
                return await user_menu(update, context)
            
            else: # Логика резервации остается без изменений
                context.user_data['book_to_reserve'] = selected_book
                keyboard = [
                    [InlineKeyboardButton("✅ Да, уведомить", callback_data="reserve_yes")],
                    [InlineKeyboardButton("❌ Нет, спасибо", callback_data="reserve_no")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"⏳ Книга «{selected_book['name']}» временно отсутствует. Хотите зарезервировать и получить уведомление, когда она освободится?", reply_markup=reply_markup)
                return USER_RESERVE_BOOK_CONFIRM

    except (db_data.NotFoundError, IndexError):
        await query.edit_message_text("❌ Ошибка: книга не найдена.")
        return await user_menu(update, context)
    except Exception as e:
        error_text = f"❌ Непредвиденная ошибка. Мы уже работаем над этим."
        logger.error(f"Критическая ошибка в process_borrow_selection: {e}", exc_info=True)
        tasks.notify_admin.delay(
            text=f"❗️ **Критическая ошибка в `librarybot`**\n\n**Функция:** `process_borrow_selection`\n**Ошибка:** `{e}`",
            category='error'
        )
        await query.edit_message_text(error_text)
        return await user_menu(update, context)

async def process_reservation_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    book_to_reserve = context.user_data.get('book_to_reserve')
    if not book_to_reserve:
        await query.edit_message_text("❌ Ошибка. Попробуйте, пожалуйста, снова.")
        return await user_menu(update, context)
    user_id = context.user_data['current_user']['id']
    if query.data == 'reserve_yes':
        with get_db_connection() as conn:
            result = db_data.add_reservation(conn, user_id, book_to_reserve['id'])
            db_data.log_activity(conn, user_id=user_id, action="reserve_book", details=f"Book ID: {book_to_reserve['id']}")
        if "уже зарезервировали" in result:
             await query.edit_message_text(f"⚠️ {result}")
        else:
             await query.edit_message_text(f"👍 Вы будете уведомлены, когда книга «{book_to_reserve['name']}» станет доступна.")
    else:
        await query.edit_message_text("👌 Хорошо, действие отменено.")
    context.user_data.pop('book_to_reserve', None)
    return await user_menu(update, context)

async def start_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        borrowed_books = db_data.get_borrowed_books(conn, user_id)
    if not borrowed_books:
        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✅ У вас нет книг на руках.", reply_markup=reply_markup)
        return USER_MENU
    message_text = "📤 Выберите книгу для возврата:"
    keyboard = []
    context.user_data['borrowed_map'] = {}
    for i, borrowed in enumerate(borrowed_books):
        borrow_id_cb = f"return_{i}"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {borrowed['book_name']}", callback_data=borrow_id_cb)])
        context.user_data['borrowed_map'][borrow_id_cb] = {'borrow_id': borrowed['borrow_id'], 'book_id': borrowed['book_id'], 'book_name': borrowed['book_name']}
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return USER_RETURN_BOOK

@rate_limit(seconds=3, alert_admins=True)
async def process_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    borrowed_info = context.user_data.get('borrowed_map', {}).get(query.data)
    if not borrowed_info:
        await query.edit_message_text("❌ Ошибка выбора. Попробуйте снова.")
        return await user_menu(update, context)

    book_id = borrowed_info['book_id']
    book_name = borrowed_info['book_name']
    user_id = context.user_data['current_user']['id']

    try:
        with get_db_connection() as conn:
            result = db_data.return_book(conn, borrowed_info['borrow_id'], book_id)
            
            if result == "Успешно":
                db_data.log_activity(conn, user_id=user_id, action="return_book", details=f"Book ID: {book_id}")
                context.user_data.pop('borrowed_map', None)
                
                # --- НОВАЯ ЛОГИКА УВЕДОМЛЕНИЙ ---
                
                # 1. Отправляем пользователю, вернувшему книгу, уведомление с кнопкой "Оценить"
                notification_text = f"✅ Книга «{book_name}» успешно возвращена. Не хотите ли поставить ей оценку?"
                tasks.notify_user.delay(
                    user_id=user_id,
                    text=notification_text,
                    category='confirmation',
                    button_text="⭐ Поставить оценку",
                    button_callback=f"rate_book_{book_id}"
                )

                # 2. Проверяем резервации и уведомляем следующего в очереди
                reservations = db_data.get_reservations_for_book(conn, book_id)
                if reservations:
                    user_to_notify_id = reservations[0]
                    reservation_text = f"🎉 Отличные новости! Книга «{book_name}», которую вы резервировали, снова в наличии."
                    tasks.notify_user.delay(
                        user_id=user_to_notify_id, 
                        text=reservation_text, 
                        category='reservation',
                        button_text="📥 Взять книгу сейчас",
                        button_callback=f"borrow_book_{book_id}"
                    )
                    db_data.update_reservation_status(conn, user_to_notify_id, book_id, notified=True)

                # 3. Даем быстрый ответ в основном боте и возвращаемся в меню
                await query.edit_message_text(f"✅ Книга «{book_name}» возвращена. Подтверждение отправлено в бот-уведомитель.")
                return await user_menu(update, context)

            else: # Если db_data.return_book вернул строку с ошибкой
                await query.edit_message_text(f"❌ Не удалось вернуть: {result}")
                return await user_menu(update, context)
                
    except Exception as e:
        logger.error(f"Ошибка при возврате книги: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при возврате книги**\n\n**Функция:** `process_return_book`\n**Ошибка:** `{e}`")
        await query.edit_message_text("❌ Непредвиденная ошибка. Администратор уже уведомлен.")
        return await user_menu(update, context)


async def start_rate_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        history = db_data.get_user_borrow_history(conn, user_id)
    if not history:
        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📚 Вы можете оценить только те книги, которые брали.", reply_markup=reply_markup)
        return USER_MENU
    message_text = "⭐ Выберите книгу для оценки:"
    keyboard = []
    context.user_data['rating_map'] = {}
    unique_books = {item['book_name']: item for item in history if 'book_id' in item and item['book_id'] is not None}.values()
    for i, book in enumerate(unique_books):
        rate_id = f"rate_{i}"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {book['book_name']}", callback_data=rate_id)])
        context.user_data['rating_map'][rate_id] = {'book_id': book['book_id'], 'book_name': book['book_name']}
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return USER_RATE_BOOK_SELECT

async def select_rating(update: Update, context: ContextTypes.DEFAULT_TYPE, from_return: bool = False) -> int:
    query = update.callback_query
    await query.answer()
    if not from_return:
        book_info = context.user_data['rating_map'].get(query.data)
        if not book_info:
            await query.edit_message_text("❌ Ошибка выбора.")
            return await user_menu(update, context)
        context.user_data['book_to_rate'] = book_info
    else:
        book_info = context.user_data.get('book_to_rate')
    message_text = f"⭐ Ваша оценка для книги «{book_info['book_name']}» (от 1 до 5):"
    rating_buttons = [
        [InlineKeyboardButton("⭐"*i, callback_data=f"rating_{i}") for i in range(1, 6)],
        [InlineKeyboardButton("⬅️ Назад", callback_data="user_rate" if not from_return else "user_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(rating_buttons)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return USER_RATE_BOOK_RATING

async def process_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        rating = int(query.data.split('_')[1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка при выборе оценки.")
        return USER_RATE_BOOK_RATING
    user_id = context.user_data['current_user']['id']
    book_info = context.user_data['book_to_rate']

    try:
        with get_db_connection() as conn:
            db_data.add_rating(conn, user_id, book_info['book_id'], rating)
            db_data.log_activity(conn, user_id=user_id, action="rate_book", details=f"Book ID: {book_info['book_id']}, Rating: {rating}")

        notification_text = f"👍 Спасибо! Ваша оценка «{rating}» для книги «{book_info['book_name']}» сохранена."
        tasks.notify_user.delay(user_id=user_id, text=notification_text, category='confirmation')

        await query.edit_message_text("✅ Спасибо за вашу оценку!")

    except Exception as e:
        message_text = f"❌ Не удалось сохранить: {e}"
        await query.edit_message_text(message_text)
        tasks.notify_admin.delay(text=f"❗️ Ошибка при сохранении оценки для user_id {user_id}: {e}")

    context.user_data.pop('book_to_rate', None)
    context.user_data.pop('rating_map', None)

    return await user_menu(update, context)

async def start_rating_from_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс оценки из уведомления."""
    query = update.callback_query
    await query.answer()
    
    book_id = int(query.data.split('_')[2])
    
    # Получаем информацию о книге для заголовка
    with get_db_connection() as conn:
        book_info_raw = db_data.get_book_by_id(conn, book_id)
        
    book_info = {'id': book_id, 'name': book_info_raw['name']}
    context.user_data['book_to_rate'] = book_info

    # Переиспользуем существующую функцию для показа кнопок с оценками
    return await select_rating(update, context, from_return=True)

async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    try:
        with get_db_connection() as conn:
            notifications = db_data.get_notifications_for_user(conn, user_id)
        message_parts = ["📬 **Ваши последние уведомления:**\n"]
        for notif in notifications:
            date_str = notif['created_at'].strftime('%d.%m.%Y %H:%M')
            status = "⚪️" if notif['is_read'] else "🔵"
            category_map = {'broadcast': '📢 Рассылка', 'reservation': '📦 Резерв', 'system': '⚙️ Система'}
            category_str = category_map.get(notif['category'], notif['category'].capitalize())
            message_parts.append(f"`{date_str}`\n{status} **{category_str}:** {notif['text']}\n")
        message_text = "\n".join(message_parts)
    except db_data.NotFoundError:
        message_text = "📭 У вас пока нет уведомлений."
    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return USER_MENU

# --- ФУНКЦИИ УДАЛЕНИЯ АККАУНТА ---

async def ask_delete_self_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        borrowed_books = db_data.get_borrowed_books(conn, user_id)
    if borrowed_books:
        keyboard = [[InlineKeyboardButton("⬅️ Назад в профиль", callback_data="user_profile")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ Вы не можете удалить аккаунт, пока у вас есть книги на руках.", reply_markup=reply_markup)
        return USER_MENU
    keyboard = [
        [InlineKeyboardButton("✅ Да, я уверен", callback_data="user_confirm_self_delete")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data="user_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚠️ **Вы уверены?**\n\nЭто действие невозможно отменить. Все ваши данные будут анонимизированы.", reply_markup=reply_markup, parse_mode='Markdown')
    return USER_DELETE_CONFIRM

async def process_delete_self_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']

    # --- ИЗМЕНЕНИЯ ЗДЕСЬ ---
    
    # Сначала получаем username, пока данные еще доступны
    username = context.user_data['current_user'].get('username', f'ID: {user_id}')
    
    with get_db_connection() as conn:
        result = db_data.delete_user_by_self(conn, user_id)
        if result == "Успешно":
            # Теперь логируем действие С ДЕТАЛЯМИ (username)
            db_data.log_activity(conn, user_id=user_id, action="self_delete_account", details=f"Username: {username}")
            
            admin_text = f"🗑️ Пользователь @{username} (ID: {user_id}) самостоятельно удалил свой аккаунт."
            tasks.notify_admin.delay(text=admin_text, category='user_self_deleted')

            await query.edit_message_text("✅ Ваш аккаунт был удален. Прощайте!")
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await query.edit_message_text(f"❌ Не удалось удалить: {result}")
            return await user_menu(update, context)
        
# --- ФУНКЦИИ РЕДАКТИРОВАНИЯ ПРОФИЛЯ ---

async def start_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Входная точка для редактирования профиля. Показывает меню."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить ФИО", callback_data="edit_field_full_name")],
        [InlineKeyboardButton("📞 Изменить контакт", callback_data="edit_field_contact_info")],
        [InlineKeyboardButton("🔑 Сменить пароль", callback_data="edit_field_password")],
        [InlineKeyboardButton("⬅️ Назад в профиль", callback_data="user_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✏️ Выберите, что вы хотите изменить:", reply_markup=reply_markup)
    return EDIT_PROFILE_MENU

async def select_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор поля и запрашивает новые данные."""
    query = update.callback_query
    await query.answer()
    field = query.data.split('_')[2]

    if field == "full_name":
        await query.edit_message_text("✏️ Введите новое ФИО:")
        return EDITING_FULL_NAME
    elif field == "contact_info":
        await query.edit_message_text("📞 Введите **новый** контакт (email или телефон):", parse_mode='Markdown')
        # Меняем состояние на ожидание нового контакта
        return EDITING_CONTACT 
    elif field == "password":
        await query.edit_message_text("🔐 Для безопасности, введите ваш **текущий** пароль:", parse_mode='Markdown')
        return EDITING_PASSWORD_CURRENT

async def process_full_name_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет ФИО пользователя."""
    new_name = update.message.text
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        db_data.update_user_full_name(conn, user_id, new_name)
        context.user_data['current_user'] = db_data.get_user_by_id(conn, user_id)
    await update.message.reply_text("✅ ФИО успешно обновлено!")
    context.user_data['just_edited_profile'] = True
    return ConversationHandler.END

async def process_contact_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новый контакт, проверяет его на уникальность и отправляет код."""
    new_contact = normalize_phone_number(update.message.text)
    user_id = context.user_data['current_user']['id']
    
    try:
        # Проверим, не занят ли этот контакт кем-то другим
        with get_db_connection() as conn:
            if db_data.get_user_by_login(conn, new_contact):
                await update.message.reply_text("❌ Этот контакт уже занят другим пользователем. Попробуйте другой.")
                return EDITING_CONTACT # Остаемся в состоянии ввода нового контакта
    except db_data.NotFoundError:
        pass # Все хорошо, контакт свободен

    # Сохраняем новый контакт временно и генерируем код
    context.user_data['new_contact_temp'] = new_contact
    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code

    # Отправляем код на НОВЫЙ контакт
    sent = await send_verification_message(new_contact, code, context, update.effective_user.id)
    
    if sent:
        await update.message.reply_text(f"📲 На ваш новый контакт ({new_contact}) отправлен код. Введите его для подтверждения:")
        return AWAIT_CONTACT_VERIFICATION_CODE # Переходим в состояние ожидания кода
    else:
        await update.message.reply_text("⚠️ Не удалось отправить код. Проверьте правильность введенных данных и попробуйте снова.")
        return EDITING_CONTACT

async def check_current_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет текущий пароль пользователя."""
    current_password_input = update.message.text
    stored_hash = context.user_data['current_user']['password_hash']

    # ✅ НЕМЕДЛЕННО УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с текущим паролем: {e}")
    
    if hash_password(current_password_input) == stored_hash:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ Пароль верный. Теперь введите **новый** пароль:",
            parse_mode='Markdown'
        )
        return EDITING_PASSWORD_NEW
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Неверный пароль. Попробуйте еще раз или нажмите /cancel для отмены."
        )
        return EDITING_PASSWORD_CURRENT

async def get_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новый пароль."""
    new_password = update.message.text

    # ✅ НЕМЕДЛЕННО УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с новым паролем: {e}")

    if len(new_password) < 8:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароль должен быть не менее 8 символов. Попробуйте снова."
        )
        return EDITING_PASSWORD_NEW

    context.user_data['new_password_temp'] = new_password
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👍 Отлично. Повторите **новый** пароль для подтверждения:",
        parse_mode='Markdown'
    )
    return EDITING_PASSWORD_CONFIRM

async def confirm_and_set_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждает и устанавливает новый пароль."""
    confirm_password = update.message.text

    # ✅ НЕМЕДЛЕННО УДАЛЯЕМ СООБЩЕНИЕ С ПАРОЛЕМ
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с подтверждением нового пароля: {e}")

    if confirm_password != context.user_data.get('new_password_temp'):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароли не совпадают. Попробуйте ввести новый пароль еще раз."
        )
        return EDITING_PASSWORD_NEW
    
    user_id = context.user_data['current_user']['id']
    new_password = context.user_data.pop('new_password_temp')
    
    with get_db_connection() as conn:
        db_data.update_user_password_by_id(conn, user_id, new_password)
        context.user_data['current_user'] = db_data.get_user_by_id(conn, user_id)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🎉 Пароль успешно изменен!"
    )
    context.user_data['just_edited_profile'] = True
    return ConversationHandler.END

@rate_limit(seconds=1)
async def show_genres(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает пользователю список жанров и переходит в состояние выбора."""
    query = update.callback_query
    await query.answer()

    with get_db_connection() as conn:
        genres = db_data.get_unique_genres(conn)
    
    if not genres:
        await query.edit_message_text(
            "😔 К сожалению, в каталоге пока нет книг с указанием жанра.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]])
        )
        return USER_MENU

    keyboard = []
    for genre in genres:
        keyboard.append([InlineKeyboardButton(f"🎭 {genre}", callback_data=f"genre_{genre}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("📚 Выберите интересующий вас жанр:", reply_markup=reply_markup)
    return SHOWING_GENRES


async def show_books_in_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает постраничный список доступных книг в выбранном жанре."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    genre = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    books_per_page = 5
    offset = page * books_per_page

    with get_db_connection() as conn:
        books, total_books = db_data.get_available_books_by_genre(conn, genre, limit=books_per_page, offset=offset)

    if total_books == 0:
        message_text = f"😔 В жанре «{genre}» свободных книг не найдено."
    else:
        message_parts = [f"**📚 Книги в жанре «{genre}»** (Стр. {page + 1}):\n"]
        for book in books:
            message_parts.append(f"• *{book['name']}* ({book['author']})")
        message_text = "\n".join(message_parts)
    
    # --- Кнопки навигации ---
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"genre_{genre}_{page - 1}"))
    if (page + 1) * books_per_page < total_books:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"genre_{genre}_{page + 1}"))

    keyboard = [nav_buttons] if nav_buttons else []
    keyboard.append([InlineKeyboardButton("⬅️ К выбору жанра", callback_data="find_by_genre")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return SHOWING_GENRE_BOOKS

@rate_limit(seconds=1)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог поиска книги по ключевому слову."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="🔎 Введите название книги или фамилию автора для поиска:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]])
    )
    return GETTING_SEARCH_QUERY

@rate_limit(seconds=2)
async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ищет книги, показывает первую страницу результатов и сохраняет запрос."""
    search_term = update.message.text
    context.user_data['last_search_term'] = search_term # Сохраняем для пагинации
    
    # Вызываем новую функцию для навигации, чтобы не дублировать код
    # Имитируем callback_query для первой страницы
    query_data = "search_page_0"
    update.callback_query = type('CallbackQuery', (), {'data': query_data, 'message': update.message, 'answer': lambda: None})()
    
    # Удаляем сообщение пользователя с поисковым запросом для чистоты
    await update.message.delete()

    return await navigate_search_results(update, context)

async def navigate_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает навигацию по страницам результатов поиска по слову."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.split('_')[2])
    search_term = context.user_data.get('last_search_term')

    if not search_term:
        await query.edit_message_text("❌ Ошибка: поисковый запрос потерян. Попробуйте снова.")
        return await user_menu(update, context)

    books_per_page = 5
    offset = page * books_per_page

    with get_db_connection() as conn:
        books, total_books = db_data.search_available_books(conn, search_term, limit=books_per_page, offset=offset)

    if total_books == 0:
         await query.edit_message_text(
            text=f"😔 По запросу «{search_term}» ничего не найдено.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Попробовать еще раз", callback_data="search_book")],
                [InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")]
            ])
        )
         return USER_MENU

    message_text = f"🔎 Результаты по запросу «{search_term}» (Стр. {page + 1}):"
    keyboard = []
    for book in books:
        keyboard.append([InlineKeyboardButton(f"📖 {book['name']} ({book['author']})", callback_data=f"view_book_{book['id']}")])
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"search_page_{page - 1}"))
    if (page + 1) * books_per_page < total_books:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"search_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return SHOWING_SEARCH_RESULTS

async def show_book_card_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает детальную карточку книги для пользователя."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[2])
    
    with get_db_connection() as conn:
        book = db_data.get_book_card_details(conn, book_id)

    message_parts = [
        f"**📖 {book['name']}**",
        f"**Автор:** {book['author']}",
        f"**Жанр:** {book['genre']}",
        f"\n_{book['description']}_\n"
    ]
    
    keyboard = []
    if book['is_available']:
        message_parts.append("✅ **Статус:** Свободна")
        keyboard.append([InlineKeyboardButton("✅ Взять эту книгу", callback_data=f"borrow_book_{book['id']}")])
    else:
        message_parts.append("❌ **Статус:** На руках")

    # --- УЛУЧШЕННАЯ КЛАВИАТУРА ---
    keyboard.extend([
        [InlineKeyboardButton("🔎 Новый поиск", callback_data="search_book")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")]
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "\n".join(message_parts)

    # Удаляем старое сообщение со списком, чтобы не было путаницы
    if query.message:
        await query.message.delete()

    if book.get('cover_image_id'):
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=book['cover_image_id'],
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    return SHOWING_SEARCH_RESULTS

async def show_top_books(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает топ книг по среднему рейтингу."""
    query = update.callback_query
    await query.answer()

    with get_db_connection() as conn:
        top_books = db_data.get_top_rated_books(conn, limit=5)

    message_parts = ["**🏆 Топ-5 книг по оценкам читателей:**\n"]
    if top_books:
        for i, book in enumerate(top_books):
            # Округляем рейтинг и создаем звезды
            rating = round(float(book['avg_rating'])) 
            stars = "⭐" * rating
            # Форматируем средний балл до одного знака после запятой
            avg_rating_str = f"{float(book['avg_rating']):.1f}"
            message_parts.append(
                f"{i+1}. **{book['name']}** - {book['author']}\n"
                f"   Рейтинг: {stars} ({avg_rating_str}/5.0 на основе {book['votes']} оценок)\n"
            )
    else:
        message_parts.append("_Пока недостаточно данных для составления рейтинга._\n\n_Оценивайте прочитанные книги, чтобы помочь другим!_")

    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "\n".join(message_parts), 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )
    return VIEWING_TOP_BOOKS

async def verify_new_contact_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет код и, если он верен, обновляет контакт в БД."""
    user_code = update.message.text
    if user_code == context.user_data.get('verification_code'):
        user_id = context.user_data['current_user']['id']
        new_contact = context.user_data.get('new_contact_temp')
        
        with get_db_connection() as conn:
            db_data.update_user_contact(conn, user_id, new_contact)
            # Обновляем данные в сессии
            context.user_data['current_user'] = db_data.get_user_by_id(conn, user_id)

        await update.message.reply_text("✅ Контакт успешно обновлен!")
        
        # Очистка временных данных
        context.user_data.pop('verification_code', None)
        context.user_data.pop('new_contact_temp', None)
        
        context.user_data['just_edited_profile'] = True
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте еще раз.")
        return AWAIT_CONTACT_VERIFICATION_CODE # Остаемся в ожидании правильного кода

async def process_book_extension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатие на кнопку 'Продлить'."""
    query = update.callback_query
    await query.answer()
    
    borrow_id = int(query.data.split('_')[2])
    
    with get_db_connection() as conn:
        result = db_data.extend_due_date(conn, borrow_id)
    
    # result может быть либо новой датой, либо строкой с ошибкой
    if isinstance(result, datetime):
        new_due_date_str = result.strftime('%d.%m.%Y')
        await query.edit_message_text(f"✅ Срок возврата книги успешно продлен до **{new_due_date_str}**.", parse_mode='Markdown')
    else:
        await query.edit_message_text(f"⚠️ {result}")
        
    return USER_MENU # В любом случае возвращаемся в главное меню

@rate_limit(seconds=2)
async def show_authors_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает постраничный список всех авторов."""
    query = update.callback_query
    page = 0
    authors_per_page = 10

    if query:
        await query.answer()
        if '_' in query.data:
            page = int(query.data.split('_')[2])
    
    context.user_data['current_authors_page'] = page
    offset = page * authors_per_page

    try:
        with get_db_connection() as conn:
            authors, total_authors = db_data.get_all_authors_paginated(conn, limit=authors_per_page, offset=offset)

        if not authors:
            keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message_text = "📚 В библиотеке пока нет авторов."
            
            if query:
                await query.edit_message_text(message_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message_text, reply_markup=reply_markup)
            return USER_MENU

        message_text = f"👥 **Авторы в библиотеке** (Всего: {total_authors})\n\nСтраница {page + 1}:"
        keyboard = []
        
        for author in authors:
            books_count = author['books_count']
            available_count = author['available_books_count']
            button_text = f"✍️ {author['name']} ({books_count} книг, {available_count} доступно)"
            callback_data = f"view_author_{author['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"authors_page_{page - 1}"))
        if (page + 1) * authors_per_page < total_authors:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"authors_page_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

        return SHOWING_AUTHORS_LIST

    except Exception as e:
        error_message = f"❌ Ошибка при получении списка авторов: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `librarybot`**\n\n**Функция:** `show_authors_list`\n**Ошибка:** `{e}`")
        
        if query:
            await query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        return USER_MENU


async def show_author_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает детальную карточку автора с его книгами."""
    query = update.callback_query
    await query.answer()
    
    # Парсим данные из callback
    parts = query.data.split('_')
    author_id = int(parts[2])
    books_page = int(parts[3]) if len(parts) > 3 else 0
    
    current_authors_page = context.user_data.get('current_authors_page', 0)
    books_per_page = 5

    try:
        with get_db_connection() as conn:
            # Получаем информацию об авторе
            author = db_data.get_author_details(conn, author_id)
            
            # Получаем книги автора с пагинацией
            books, total_books = db_data.get_books_by_author(
                conn, 
                author_id, 
                limit=books_per_page, 
                offset=books_page * books_per_page
            )

        # Формируем текст карточки
        message_parts = [
            f"👤 **{author['name']}**\n",
            f"📚 **Всего книг в библиотеке:** {total_books}",
            f"✅ **Доступно:** {author['available_books_count']}",
            f"📖 **На руках:** {total_books - author['available_books_count']}\n"
        ]

        if total_books > 0:
            total_pages = (total_books + books_per_page - 1) // books_per_page
            message_parts.append(f"**📖 Книги автора (стр. {books_page + 1}/{total_pages}):**\n")
            
            for i, book in enumerate(books, start=1):
                status_icon = "✅" if book['is_available'] else "❌"
                message_parts.append(
                    f"{i}. {status_icon} **{book['name']}**\n"
                    f"   📅 {book.get('genre', 'Жанр не указан')}"
                )
                if book.get('avg_rating'):
                    stars = "⭐" * round(book['avg_rating'])
                    message_parts.append(f" | {stars} {book['avg_rating']:.1f}/5.0")
                message_parts.append("\n")
        else:
            message_parts.append("_У этого автора пока нет книг в библиотеке._")

        message_text = "\n".join(message_parts)

        # Формируем клавиатуру
        keyboard = []
        
        # Кнопки для просмотра книг
        if books:
            book_buttons = []
            for i, book in enumerate(books, start=1):
                book_buttons.append(
                    InlineKeyboardButton(f"📖 {i}", callback_data=f"view_book_{book['id']}")
                )
            # Разбиваем на строки по 5 кнопок
            for i in range(0, len(book_buttons), 5):
                keyboard.append(book_buttons[i:i+5])
        
        # Навигация по страницам книг
        if total_books > books_per_page:
            nav_buttons = []
            if books_page > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Книги", callback_data=f"view_author_{author_id}_{books_page - 1}")
                )
            nav_buttons.append(
                InlineKeyboardButton(f"{books_page + 1}/{(total_books + books_per_page - 1) // books_per_page}", callback_data="ignore")
            )
            if (books_page + 1) * books_per_page < total_books:
                nav_buttons.append(
                    InlineKeyboardButton("Книги ➡️", callback_data=f"view_author_{author_id}_{books_page + 1}")
                )
            keyboard.append(nav_buttons)

        # Кнопка возврата
        keyboard.append([
            InlineKeyboardButton("⬅️ К списку авторов", callback_data=f"authors_page_{current_authors_page}")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
        return VIEWING_AUTHOR_CARD

    except db_data.NotFoundError:
        await query.edit_message_text("❌ Автор не найден.")
        return await show_authors_list(update, context)
    except Exception as e:
        error_message = f"❌ Ошибка при получении карточки автора: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `librarybot`**\n\n**Функция:** `show_author_card`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)
        return USER_MENU

async def search_authors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Поиск авторов по имени."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔎 Введите имя автора для поиска:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Назад", callback_data="show_authors")
        ]])
    )
    return SEARCHING_AUTHORS

async def process_author_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает поиск автора."""
    search_term = update.message.text
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.id, a.name, COUNT(b.id) as books_count
            FROM authors a
            LEFT JOIN books b ON a.id = b.author_id
            WHERE a.name ILIKE %s
            GROUP BY a.id
            HAVING COUNT(b.id) > 0
            ORDER BY a.name
            LIMIT 10
            """,
            (f'%{search_term}%',)
        )
        results = cur.fetchall()
    
    if not results:
        await update.message.reply_text(
            f"😔 По запросу «{search_term}» ничего не найдено.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔎 Искать снова", callback_data="search_authors"),
                InlineKeyboardButton("⬅️ К списку", callback_data="show_authors")
            ]])
        )
        return SHOWING_AUTHORS_LIST
    
    keyboard = []
    for author_id, name, books_count in results:
        keyboard.append([
            InlineKeyboardButton(
                f"✍️ {name} ({books_count} книг)", 
                callback_data=f"view_author_{author_id}_0"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔎 Искать снова", callback_data="search_authors"),
        InlineKeyboardButton("⬅️ К списку", callback_data="show_authors")
    ])
    
    await update.message.reply_text(
        f"🔎 Результаты по запросу «{search_term}»:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SHOWING_AUTHORS_LIST

def get_book_recommendations(conn, user_id: int, limit: int = 5):
    """
    Рекомендует книги на основе:
    1. Жанров, которые пользователь читал
    2. Рейтингов, которые он ставил
    3. Популярности книг
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH user_genres AS (
                SELECT DISTINCT b.genre
                FROM borrowed_books bb
                JOIN books b ON bb.book_id = b.id
                WHERE bb.user_id = %s
            ),
            user_read_books AS (
                SELECT book_id FROM borrowed_books WHERE user_id = %s
            )
            SELECT 
                b.id, b.name, a.name as author,
                AVG(r.rating) as avg_rating,
                COUNT(bb.borrow_id) as popularity
            FROM books b
            JOIN authors a ON b.author_id = a.id
            LEFT JOIN ratings r ON b.id = r.book_id
            LEFT JOIN borrowed_books bb ON b.id = bb.book_id
            WHERE b.genre IN (SELECT genre FROM user_genres)
              AND b.id NOT IN (SELECT book_id FROM user_read_books)
              AND NOT EXISTS (
                  SELECT 1 FROM borrowed_books bb2 
                  WHERE bb2.book_id = b.id AND bb2.return_date IS NULL
              )
            GROUP BY b.id, a.name
            ORDER BY avg_rating DESC NULLS LAST, popularity DESC
            LIMIT %s
            """,
            (user_id, user_id, limit)
        )
        return cur.fetchall()

async def show_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает персональные рекомендации."""
    user_id = context.user_data['current_user']['id']
    
    with get_db_connection() as conn:
        recommendations = get_book_recommendations(conn, user_id)
    
    if not recommendations:
        await update.callback_query.edit_message_text(
            "🤷 К сожалению, пока нет рекомендаций. Попробуйте взять несколько книг!"
        )
        return
    
    message_parts = ["💡 **Рекомендуем вам:**\n"]
    keyboard = []
    
    for i, (book_id, title, author, rating, popularity) in enumerate(recommendations, 1):
        rating_str = f"⭐ {rating:.1f}" if rating else "Нет оценок"
        message_parts.append(f"{i}. **{title}** - {author} | {rating_str}")
        keyboard.append([
            InlineKeyboardButton(f"📖 {i}", callback_data=f"view_book_{book_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ В меню", callback_data="user_menu")])
    
    await update.callback_query.edit_message_text(
        "\n".join(message_parts),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def export_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспортирует данные пользователя в JSON (GDPR compliance)."""
    user_id = context.user_data['current_user']['id']
    
    with get_db_connection() as conn:
        user_profile = db_data.get_user_profile(conn, user_id)
        borrow_history = db_data.get_user_borrow_history(conn, user_id)
        ratings = db_data.get_user_ratings(conn, user_id)
        activity = db_data.get_user_activity(conn, user_id, limit=1000, offset=0)[0]
    
    export_data = {
        'profile': user_profile,
        'borrow_history': borrow_history,
        'ratings': ratings,
        'activity_log': activity
    }
    
    import json
    json_data = json.dumps(export_data, indent=2, default=str, ensure_ascii=False)
    
    # Отправляем как файл
    await update.message.reply_document(
        document=json_data.encode('utf-8'),
        filename=f"user_data_{user_id}.json",
        caption="📄 Ваши данные из системы библиотеки"
    )

async def show_rate_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику rate limiting (только для админов)."""
    user_id = update.effective_user.id
    
    # Проверка, что это админ
    if user_id != ADMIN_TELEGRAM_ID:
        return
    
    total_users = len(user_last_request)
    violators = len([v for v in user_violations.values() if v > 0])
    top_violators = sorted(
        user_violations.items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:5]
    
    message = (
        f"📊 **Статистика Rate Limiting**\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"⚠️ С нарушениями: {violators}\n\n"
        f"**Топ нарушителей:**\n"
    )
    
    for i, (uid, count) in enumerate(top_violators, 1):
        message += f"{i}. User ID {uid}: {count} нарушений\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# --------------------------
# --- ГЛАВНЫЙ HANDLER ---
# --------------------------

async def ignore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает callback'и, которые должны игнорироваться (например, счетчики страниц)."""
    query = update.callback_query
    await query.answer()

def main() -> None:

    """Запускает основного бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application = Application.builder().token(ADMIN_TELEGRAM_ID).build()
    application.add_handler(CommandHandler("rate_stats", show_rate_stats))
    # --- Вложенный обработчик для редактирования профиля ---
    edit_profile_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_profile_edit, pattern="^edit_profile$")],
        states={
            EDIT_PROFILE_MENU: [CallbackQueryHandler(select_field_to_edit, pattern="^edit_field_")],
            EDITING_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_full_name_edit)],
            EDITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_contact_edit)],
            AWAIT_CONTACT_VERIFICATION_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_new_contact_code)],
            EDITING_PASSWORD_CURRENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_current_password)],
            EDITING_PASSWORD_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_password)],
            EDITING_PASSWORD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_and_set_new_password)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(view_profile, pattern="^user_profile$")
        ],
        map_to_parent={ ConversationHandler.END: USER_MENU }
    )

    # --- Основной словарь состояний ---
    main_conv_states = {
        # -- Вход и Регистрация --
        START_ROUTES: [
            CallbackQueryHandler(start_registration, pattern="^register$"),
            CallbackQueryHandler(start_login, pattern="^login$"),
            # Обработчики для кнопок из уведомлений (должны работать всегда)
            CallbackQueryHandler(process_book_extension, pattern=r"^extend_borrow_"),
            CallbackQueryHandler(start_rating_from_notification, pattern=r"^rate_book_"),
            CallbackQueryHandler(process_borrow_selection, pattern=r"^borrow_book_"),
            CallbackQueryHandler(show_book_card_user, pattern="^view_book_"),
        ],
        AWAITING_NOTIFICATION_BOT: [
            CallbackQueryHandler(check_notification_subscription, pattern="^confirm_subscription$")
        ],
        **{state: [MessageHandler(filters.TEXT & ~filters.COMMAND, handler)] for state, handler in {
            REGISTER_NAME: get_name,
            REGISTER_DOB: get_dob,
            REGISTER_CONTACT: get_contact,
            REGISTER_VERIFY_CODE: verify_registration_code,
            REGISTER_USERNAME: get_username,
            REGISTER_PASSWORD: get_password,
            REGISTER_CONFIRM_PASSWORD: get_password_confirmation,
            LOGIN_PASSWORD: check_login_password,
            FORGOT_PASSWORD_CONTACT: get_forgot_password_contact,
            FORGOT_PASSWORD_VERIFY_CODE: verify_forgot_password_code,
            FORGOT_PASSWORD_SET_NEW: set_new_password,
            FORGOT_PASSWORD_CONFIRM_NEW: confirm_new_password,
        }.items()},
        REGISTER_STATUS: [CallbackQueryHandler(get_status, pattern=r"^(студент|учитель)$")],
        LOGIN_CONTACT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_login_contact),
            CallbackQueryHandler(start_forgot_password, pattern="^forgot_password$")
        ],

        # -- Главное Меню и его опции --
        USER_MENU: [
            # Основные действия
            CallbackQueryHandler(start_return_book, pattern="^user_return$"),
            CallbackQueryHandler(start_rate_book, pattern="^user_rate$"),
            CallbackQueryHandler(view_profile, pattern="^user_profile$"),
            CallbackQueryHandler(logout, pattern="^logout$"),
            # Навигация
            CallbackQueryHandler(view_borrow_history, pattern="^user_history$"),
            CallbackQueryHandler(show_notifications, pattern="^user_notifications$"),
            CallbackQueryHandler(show_top_books, pattern="^top_books$"),
            # Поиск
            CallbackQueryHandler(show_genres, pattern="^find_by_genre$"),
            CallbackQueryHandler(start_search, pattern="^search_book$"),
            # Вложенный обработчик
            edit_profile_handler,
            CallbackQueryHandler(show_authors_list, pattern="^show_authors$"),
            # Возврат в меню
            CallbackQueryHandler(user_menu, pattern="^user_menu$"),
        ],

        # -- Процесс взятия и резервирования книги --
        USER_BORROW_BOOK_SELECT: [
            CallbackQueryHandler(process_borrow_selection, pattern=r"^borrow_book_"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        USER_RESERVE_BOOK_CONFIRM: [CallbackQueryHandler(process_reservation_decision, pattern=r"^reserve_(yes|no)$")],

        # -- Процесс возврата книги --
        USER_RETURN_BOOK: [
            CallbackQueryHandler(process_return_book, pattern=r"^return_\d+$"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],

        # -- Процесс оценки книги --
        USER_RATE_BOOK_SELECT: [
            CallbackQueryHandler(select_rating, pattern=r"^rate_\d+$"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        USER_RATE_BOOK_RATING: [
            CallbackQueryHandler(process_rating, pattern=r"^rating_\d+$"),
            CallbackQueryHandler(start_rate_book, pattern="^user_rate$"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$"),
        ],

        # -- Процесс удаления аккаунта --
        USER_DELETE_CONFIRM: [
            CallbackQueryHandler(process_delete_self_confirmation, pattern="^user_confirm_self_delete$"),
            CallbackQueryHandler(view_profile, pattern="^user_profile$"),
        ],

        # -- Процессы поиска --
        SHOWING_GENRES: [
            CallbackQueryHandler(show_books_in_genre, pattern=r"^genre_"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        SHOWING_GENRE_BOOKS: [
            CallbackQueryHandler(show_genres, pattern="^find_by_genre$"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        GETTING_SEARCH_QUERY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        SHOWING_SEARCH_RESULTS: [
            CallbackQueryHandler(show_book_card_user, pattern="^view_book_"),
            CallbackQueryHandler(process_borrow_selection, pattern=r"^borrow_book_"), 
            CallbackQueryHandler(start_search, pattern="^search_book$"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$"),
            CallbackQueryHandler(navigate_search_results, pattern="^search_page_"),
            CallbackQueryHandler(ignore_callback, pattern="^ignore$"),
        ],
        VIEWING_TOP_BOOKS: [
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        SHOWING_AUTHORS_LIST: [
            CallbackQueryHandler(show_author_card, pattern=r"^view_author_"),
            CallbackQueryHandler(show_authors_list, pattern="^authors_page_"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$")
        ],
        VIEWING_AUTHOR_CARD: [
            CallbackQueryHandler(show_author_card, pattern=r"^view_author_"),
            CallbackQueryHandler(show_book_card_user, pattern="^view_book_"),
            CallbackQueryHandler(show_authors_list, pattern="^authors_page_"),
            CallbackQueryHandler(user_menu, pattern="^user_menu$"),
            CallbackQueryHandler(ignore_callback, pattern="^ignore$"),
        ],
        SEARCHING_AUTHORS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_author_search),
            CallbackQueryHandler(show_authors_list, pattern='^show_authors$'),
            CallbackQueryHandler(user_menu, pattern='^user_menu$'),
        ],
    }

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states=main_conv_states,
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)], # Добавили cancel
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()