# src/library_bot/handlers/auth.py

import logging
import random
from time import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection, hash_password
from src.core import tasks
from src.library_bot.states import State
from src.library_bot.utils import normalize_phone_number
from src.library_bot.handlers.registration import send_verification_message

logger = logging.getLogger(__name__)

# --- Переменная для отслеживания блокировок входа ---
login_lockouts = {}  # {user_id: (lockout_until_timestamp, attempts)}

# --- Обработчики диалога входа ---

async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает процесс входа."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
    await query.edit_message_text(
        "👤 Введите ваш **юзернейм** или **контакт** для входа:", 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return State.LOGIN_CONTACT

async def get_login_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает контакт/логин и ищет пользователя в БД."""
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    try:
        async with get_db_connection() as conn:
            user = await db_data.get_user_by_login(conn, contact_processed)
        context.user_data['login_user'] = user
        context.user_data['login_attempts'] = 0

        keyboard = [
            [InlineKeyboardButton("🤔 Забыли пароль?", callback_data="forgot_password")],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔑 Введите ваш **пароль**:", 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
        return State.LOGIN_PASSWORD
    except db_data.NotFoundError:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await update.message.reply_text(
            "❌ Пользователь не найден. Попробуйте еще раз или зарегистрируйтесь.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.LOGIN_CONTACT

async def check_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State | int:
    """Проверяет пароль, обрабатывает блокировку и входит в систему."""
    user = context.user_data['login_user']
    user_id = user['id']
    input_password = update.message.text

    # Проверка блокировки
    if user_id in login_lockouts:
        lockout_until, _ = login_lockouts[user_id]
        if time() < lockout_until:
            remaining = int(lockout_until - time())
            await update.message.reply_text(f"🔒 Вход заблокирован на {remaining} секунд из-за множественных неудачных попыток.")
            return State.LOGIN_PASSWORD
        else:
            login_lockouts.pop(user_id, None)

    try:
        await update.message.delete()
    except Exception:
        pass

    if hash_password(input_password) == user['password_hash']:
        async with get_db_connection() as conn:
            await db_data.log_activity(conn, user_id=user['id'], action="login")

        context.user_data.pop('login_attempts', None)
        login_lockouts.pop(user_id, None)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎉 Добро пожаловать, {user['full_name']}!"
        )
        context.user_data['current_user'] = user
        context.user_data.pop('login_user')

        # Динамический импорт, чтобы избежать циклической зависимости
        from src.library_bot.handlers.user_menu import user_menu
        await user_menu(update, context)
        return State.USER_MENU
    else:
        attempts = context.user_data.get('login_attempts', 0) + 1
        context.user_data['login_attempts'] = attempts

        if attempts >= 3:
            lockout_duration = 300  # 5 минут
            login_lockouts[user_id] = (time() + lockout_duration, attempts)

            tasks.notify_admin.delay(
                text=f"🔒 **[АУДИТ БЕЗОПАСНОСТИ]**\n\nЗамечено {attempts} неудачных попытки входа для пользователя @{user.get('username', user.get('contact_info'))}. Вход заблокирован на 5 минут.",
                category='security_alert',
                user_id=user_id
            )

            context.user_data.pop('login_attempts', None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Неверный пароль. Вы исчерпали количество попыток.\n\n🔒 Вход заблокирован на 5 минут."
            )
            return ConversationHandler.END
        else:
            keyboard = [
                [InlineKeyboardButton("🤔 Забыли пароль?", callback_data="forgot_password")],
                [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
            ]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Неверный пароль. Осталось попыток: {3 - attempts}.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return State.LOGIN_PASSWORD

# --- Обработчики диалога восстановления пароля ---

async def start_forgot_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает процесс восстановления пароля."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
    await query.edit_message_text(
        "🔑 Введите ваш **юзернейм** или **контакт** для сброса пароля:", 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return State.FORGOT_PASSWORD_CONTACT

async def get_forgot_password_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает контакт, отправляет код верификации."""
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    
    try:
        async with get_db_connection() as conn:
            user = await db_data.get_user_by_login(conn, contact_processed)
    except db_data.NotFoundError:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await update.message.reply_text(
            "❌ Пользователь с такими данными не найден.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_CONTACT

    user_telegram_id = user.get('telegram_id') or update.effective_user.id
    code = str(random.randint(100000, 999999))
    context.user_data['forgot_password_code'] = code
    context.user_data['forgot_password_contact'] = user['contact_info']

    sent = await send_verification_message(user['contact_info'], code, context, user_telegram_id)
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
    if sent:
        await update.message.reply_text(
            f"📲 Код верификации отправлен на {user['contact_info']}. Введите его:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_VERIFY_CODE
    else:
        await update.message.reply_text(
            "⚠️ Не удалось отправить код верификации. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_CONTACT

async def verify_forgot_password_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Проверяет код и запрашивает новый пароль."""
    if update.message.text == context.user_data.get('forgot_password_code'):
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await update.message.reply_text(
            "✅ Код верный! Введите **новый пароль** (минимум 8 символов, буквы и цифры/спецсимволы):", 
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.pop('forgot_password_code', None)
        return State.FORGOT_PASSWORD_SET_NEW
    else:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await update.message.reply_text(
            "❌ Неверный код. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_VERIFY_CODE

async def set_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает и валидирует новый пароль СРАЗУ."""
    new_password = update.message.text
    try:
        await update.message.delete()
    except Exception: 
        pass

    # ПРОВЕРКА ПАРОЛЯ НА МЕСТЕ
    if len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() or not c.isalnum() for c in new_password):
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ Пароль должен содержать:\n• Минимум 8 символов\n• Буквы\n• Цифры или спецсимволы\n\nПопробуйте снова:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_SET_NEW

    context.user_data['forgot_password_temp'] = new_password
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="👍 Пожалуйста, **введите новый пароль еще раз**:", 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return State.FORGOT_PASSWORD_CONFIRM_NEW

async def confirm_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждает и сохраняет новый пароль."""
    password_confirm = update.message.text
    try:
        await update.message.delete()
    except Exception: 
        pass

    if context.user_data.get('forgot_password_temp') != password_confirm:
        keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]]
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ Пароли не совпадают. Пожалуйста, введите новый пароль заново.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return State.FORGOT_PASSWORD_SET_NEW

    login_query = context.user_data['forgot_password_contact']
    final_password = context.user_data.pop('forgot_password_temp')
    try:
        async with get_db_connection() as conn:
            await db_data.update_user_password(conn, login_query, final_password)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="🎉 Пароль успешно обновлен! Теперь вы можете войти с новым паролем."
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении пароля: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при обновлении пароля**: `{e}`")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ Произошла ошибка. Администратор уведомлен."
        )

    context.user_data.clear()
    return ConversationHandler.END