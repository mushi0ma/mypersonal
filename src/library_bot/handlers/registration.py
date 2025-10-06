# src/library_bot/handlers/registration.py

import logging
import os
import random
import re
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import db_data
from db_utils import get_db_connection
import tasks
from src.library_bot.states import State
from src.library_bot.utils import normalize_phone_number
from src.library_bot import keyboards

# --- ИМПОРТ ДЛЯ ОТПРАВКИ EMAIL ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

logger = logging.getLogger(__name__)

# --- Вспомогательные функции, специфичные для регистрации/верификации ---

async def send_verification_message(contact_info: str, code: str, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    """
    Отправляет код верификации через наиболее подходящий канал.
    """
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

    try:
        user_telegram_id = None
        try:
            with get_db_connection() as conn:
                user = db_data.get_user_by_login(conn, contact_info)
                user_telegram_id = user.get('telegram_id')
        except db_data.NotFoundError:
            pass # Пользователь еще не существует

        if user_telegram_id:
            message_body = f"🔐 **Код верификации**\n\nВаш код для библиотеки: `{code}`"
            await context.bot.send_message(
                chat_id=user_telegram_id,
                text=message_body,
                parse_mode='Markdown'
            )
            context.user_data['verification_method'] = 'notification_bot'
            logger.info(f"Код отправлен через notification_bot пользователю {user_telegram_id}")
            return True
        else:
            message_body = f"📲 Ваш код для библиотеки: `{code}`"
            await context.bot.send_message(
                chat_id=telegram_id,
                text=message_body,
                parse_mode='Markdown'
            )
            context.user_data['verification_method'] = 'self_telegram'
            logger.info(f"Код отправлен через основного бота пользователю {telegram_id}")
            return True
    except Exception as e:
        logger.error(f"Ошибка при отправке кода через Telegram: {e}")
        return False

# --- Обработчики диалога регистрации ---

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает процесс регистрации."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['registration'] = {}
    await query.edit_message_text("📝 Начинаем регистрацию. Введите ваше **ФИО**:", parse_mode='Markdown')
    return State.REGISTER_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает ФИО и запрашивает дату рождения."""
    context.user_data['registration']['full_name'] = update.message.text
    await update.message.reply_text("🎂 Введите **дату рождения** (ДД.ММ.ГГГГ):", parse_mode='Markdown')
    return State.REGISTER_DOB

async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает дату рождения и запрашивает контакт."""
    dob = update.message.text
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", dob):
        await update.message.reply_text("❌ Неверный формат. Используйте **ДД.ММ.ГГГГ**.")
        return State.REGISTER_DOB
    context.user_data['registration']['dob'] = dob
    await update.message.reply_text("📞 Введите ваш **контакт** (email, телефон или @username):", parse_mode='Markdown')
    return State.REGISTER_CONTACT

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)
    try:
        with get_db_connection() as conn:
            if db_data.get_user_by_login(conn, contact_processed):
                await update.message.reply_text("🤔 Пользователь с такими данными уже существует. Попробуйте войти или введите другой контакт.")
                return State.REGISTER_CONTACT
    except db_data.NotFoundError:
        pass
    context.user_data['registration']['contact_info'] = contact_processed
    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code
    sent = await send_verification_message(contact_processed, code, context, update.effective_user.id)
    if sent:
        await update.message.reply_text(f"📲 На ваш контакт ({contact_processed}) отправлен **код верификации**. Введите его:", parse_mode='Markdown')
        return State.REGISTER_VERIFY_CODE
    else:
        await update.message.reply_text("⚠️ Не удалось отправить код. Проверьте правильность введенных данных.")
        return State.REGISTER_CONTACT

async def verify_registration_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Проверяет код верификации и запрашивает статус."""
    if update.message.text == context.user_data.get('verification_code'):
        reply_markup = keyboards.get_status_keyboard()
        await update.message.reply_text("✅ Код верный! Теперь выберите ваш статус:", reply_markup=reply_markup)
        context.user_data.pop('verification_code', None)
        return State.REGISTER_STATUS
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте еще раз.")
        return State.REGISTER_VERIFY_CODE

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает статус и запрашивает юзернейм."""
    query = update.callback_query
    await query.answer()
    context.user_data['registration']['status'] = query.data
    await query.edit_message_text("🧑‍💻 Придумайте **юзернейм** (на английском, без пробелов):", parse_mode='Markdown')
    return State.REGISTER_USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает юзернейм и запрашивает пароль."""
    username = update.message.text
    if not re.match(r"^[a-zA-Z0-9_]{3,}$", username):
        await update.message.reply_text("❌ Неверный формат. Юзернейм должен быть не короче 3 символов и состоять из английских букв, цифр и знака '_'.")
        return State.REGISTER_USERNAME
    context.user_data['registration']['username'] = username
    await update.message.reply_text("🔑 Создайте **пароль** (минимум 8 символов, буквы и цифры/спецсимволы):", parse_mode='Markdown')
    return State.REGISTER_PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает и валидирует пароль."""
    password = update.message.text
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с паролем: {e}")

    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() or not c.isalnum() for c in password):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароль должен содержать минимум 8 символов, буквы и цифры/спецсимволы.\nПопробуйте снова:",
            parse_mode='Markdown'
        )
        return State.REGISTER_PASSWORD

    context.user_data['registration']['password_temp'] = password
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👍 Отлично. Теперь **введите пароль еще раз** для подтверждения:",
        parse_mode='Markdown'
    )
    return State.REGISTER_CONFIRM_PASSWORD

async def get_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Завершает регистрацию, создает пользователя и переводит на этап подписки."""
    password_confirm = update.message.text
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с подтверждением пароля: {e}")

    if context.user_data['registration'].get('password_temp') != password_confirm:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Пароли не совпадают. Пожалуйста, придумайте пароль заново."
        )
        return State.REGISTER_PASSWORD

    context.user_data['registration']['password'] = context.user_data['registration'].pop('password_temp')

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✅ Пароль сохранен!\n\n⏳ Создаю ваш аккаунт...",
    )

    user_data = context.user_data['registration']
    try:
        with get_db_connection() as conn:
            user_id = db_data.add_user(conn, user_data)
            db_data.log_activity(conn, user_id=user_id, action="registration_start")
            reg_code = db_data.set_registration_code(conn, user_id)
            context.user_data['user_id_for_activation'] = user_id

        notifier_bot_username = os.getenv("NOTIFICATION_BOT_USERNAME", "ВашБотУведомитель")
        reply_markup = keyboards.get_notification_subscription_keyboard(notifier_bot_username, reg_code)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🎉 **Аккаунт создан.**\n\n"
                "**Последний шаг:** подпишитесь на нашего бота-уведомителя для получения кодов и оповещений.\n\n"
                "👉 Нажмите на кнопку ниже, запустите бота, "
                "а затем вернитесь сюда и нажмите **'Я подписался'**."
            ),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return State.AWAITING_NOTIFICATION_BOT

    except db_data.UserExistsError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Ошибка: этот юзернейм или контакт уже заняты.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при регистрации: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при регистрации**\n\n**Ошибка:** `{e}`")
        await context.bot.send_message(chat_id=update.effective.chat.id, text="❌ Произошла системная ошибка. Администратор уже уведомлен.")
        return ConversationHandler.END

async def check_notification_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Проверяет, привязал ли пользователь telegram_id через бота-уведомителя."""
    query = update.callback_query
    await query.answer()

    user_id = context.user_data.get('user_id_for_activation')
    if not user_id:
        await query.edit_message_text("❌ Произошла ошибка сессии. Пожалуйста, начните регистрацию заново с /start.")
        return ConversationHandler.END

    try:
        with get_db_connection() as conn:
            user = db_data.get_user_by_id(conn, user_id)

        if user.get('telegram_id'):
            with get_db_connection() as conn:
                db_data.log_activity(conn, user_id=user_id, action="registration_finish")

            tasks.notify_admin.delay(
                text=f"✅ **Новая регистрация**\n\n**Пользователь:** @{user.get('telegram_username', user.get('username'))}\n**ID:** {user_id}",
                category='new_user'
            )

            await query.edit_message_text("🎉 **Регистрация завершена!**\n\nТеперь вы можете войти в систему.")
            context.user_data.clear()
            # Вместо вызова start, который требует update.message, просто завершаем диалог
            # и пользователь сможет нажать /start сам
            return ConversationHandler.END
        else:
            await query.answer("⚠️ Вы еще не запустили бота-уведомителя. Пожалуйста, нажмите на кнопку выше.", show_alert=True)
            return State.AWAITING_NOTIFICATION_BOT

    except Exception as e:
        logger.error(f"Ошибка при проверке подписки для user_id {user_id}: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при проверке подписки**\n\n**UserID:** `{user_id}`\n**Ошибка:** `{e}`")
        await query.edit_message_text("❌ Произошла системная ошибка. Администратор уведомлен.")
        return ConversationHandler.END