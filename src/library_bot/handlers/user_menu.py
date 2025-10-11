# src/library_bot/handlers/user_menu.py

import logging
import random
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection, hash_password
from src.core import tasks
from src.library_bot.states import State
from src.library_bot.utils import get_user_borrow_limit, normalize_phone_number
from src.library_bot import keyboards
from src.library_bot.handlers.registration import send_verification_message # Переиспользуем

logger = logging.getLogger(__name__)

# --- Основные обработчики меню и профиля ---

async def user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Отображает главное меню пользователя."""
    user = context.user_data.get('current_user')
    if not user:
        from src.library_bot.handlers.start import start
        return await start(update, context)

    try:
        async with get_db_connection() as conn:
            context.user_data['current_user'] = await db_data.get_user_by_id(conn, user['id'])
            user = context.user_data['current_user']
            borrowed_books = await db_data.get_borrowed_books(conn, user['id'])
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных для меню пользователя {user['id']}: {e}")
        borrowed_books = []

    borrow_limit = get_user_borrow_limit(user['status'])
    message_text = (
        f"**🏠 Главное меню**\n"
        f"Добро пожаловать, {user['full_name']}!\n\n"
        f"📖 У вас на руках: **{len(borrowed_books)}/{borrow_limit}** книг."
    )
    reply_markup = keyboards.get_user_menu_keyboard()

    if update.callback_query:
        await update.callback_query.edit_message_text(
            message_text, reply_markup=reply_markup, parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text, reply_markup=reply_markup, parse_mode='Markdown'
        )
    return State.USER_MENU

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выход пользователя из системы."""
    query = update.callback_query
    await query.answer()
    user = context.user_data.get('current_user')
    if user:
        async with get_db_connection() as conn:
            await db_data.log_activity(conn, user_id=user['id'], action="logout")
            borrowed_books = await db_data.get_borrowed_books(conn, user['id'])
            if borrowed_books:
                await query.answer("❌ Вы не можете выйти, пока у вас есть книги на руках!", show_alert=True)
                return State.USER_MENU

    context.user_data.clear()
    await query.edit_message_text("✅ Вы успешно вышли. Введите /start, чтобы снова войти.")
    return ConversationHandler.END

async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает стилизованный профиль пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    try:
        async with get_db_connection() as conn:
            user_profile = await db_data.get_user_profile(conn, user_id)
            borrowed_books = await db_data.get_borrowed_books(conn, user_id)

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

        reply_markup = keyboards.get_profile_keyboard()
        await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    except db_data.NotFoundError:
        await query.edit_message_text("❌ Не удалось найти ваш профиль. Пожалуйста, войдите снова с помощью /start.")
        context.user_data.clear()
        return ConversationHandler.END

    return State.USER_MENU

async def view_borrow_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает историю заимствований пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    async with get_db_connection() as conn:
        history = await db_data.get_user_borrow_history(conn, user_id)

    message_parts = ["**📜 Ваша история взятых книг**\n"]
    if history:
        for item in history:
            return_date_str = item['return_date'].strftime('%d.%m.%Y') if item['return_date'] else "На руках"
            borrow_date_str = item['borrow_date'].strftime('%d.%m.%Y')
            rating_str = f" (ваша оценка: {'⭐' * item['rating']})" if item['rating'] else ""
            message_parts.append(f"📖 **{item['book_name']}**\n   - Взята: `{borrow_date_str}`\n   - Возвращена: `{return_date_str}`{rating_str}")
    else:
        message_parts.append("Вы еще не брали ни одной книги.")

    keyboard = [[keyboards.InlineKeyboardButton("⬅️ Назад в профиль", callback_data="user_profile")]]
    await query.edit_message_text("\n".join(message_parts), reply_markup=keyboards.InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return State.USER_MENU

async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает последние уведомления пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    try:
        async with get_db_connection() as conn:
            notifications = await db_data.get_notifications_for_user(conn, user_id)
        message_parts = ["📬 **Ваши последние уведомления:**\n"]
        for notif in notifications:
            date_str = notif['created_at'].strftime('%d.%m.%Y %H:%M')
            status = "⚪️" if notif['is_read'] else "🔵"
            message_parts.append(f"`{date_str}`\n{status} **{notif['category'].capitalize()}:** {notif['text']}\n")
    except db_data.NotFoundError:
        message_parts = ["📭 У вас пока нет уведомлений."]

    keyboard = [[keyboards.InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
    await query.edit_message_text("\n".join(message_parts), reply_markup=keyboards.InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return State.USER_MENU

# --- Обработчики удаления аккаунта ---

async def ask_delete_self_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Запрашивает подтверждение на удаление аккаунта."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    async with get_db_connection() as conn:
        borrowed_books = await db_data.get_borrowed_books(conn, user_id)
        if borrowed_books:
            await query.answer("❌ Вы не можете удалить аккаунт, пока у вас есть книги на руках.", show_alert=True)
            return State.USER_MENU

    reply_markup = keyboards.get_delete_confirmation_keyboard()
    await query.edit_message_text("⚠️ **Вы уверены?**\n\nЭто действие невозможно отменить. Все ваши данные будут анонимизированы.", reply_markup=reply_markup, parse_mode='Markdown')
    return State.USER_DELETE_CONFIRM

async def process_delete_self_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает удаление аккаунта."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    username = context.user_data['current_user'].get('username', f'ID: {user_id}')

    async with get_db_connection() as conn:
        await db_data.delete_user_by_self(conn, user_id)
        await db_data.log_activity(conn, user_id=user_id, action="self_delete_account", details=f"Username: {username}")

    tasks.notify_admin.delay(text=f"🗑️ Пользователь @{username} самостоятельно удалил свой аккаунт.", category='user_self_deleted')

    await query.edit_message_text("✅ Ваш аккаунт был удален. Прощайте!")
    context.user_data.clear()
    return ConversationHandler.END

# --- Обработчики редактирования профиля ---

async def start_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает меню редактирования профиля."""
    query = update.callback_query
    await query.answer()
    reply_markup = keyboards.get_edit_profile_keyboard()
    await query.edit_message_text("✏️ Выберите, что вы хотите изменить:", reply_markup=reply_markup)
    return State.EDIT_PROFILE_MENU

async def select_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает выбор поля для редактирования."""
    query = update.callback_query
    await query.answer()
    field = query.data.split('_')[2]

    if field == "full_name":
        await query.edit_message_text("✏️ Введите новое ФИО:")
        return State.EDITING_FULL_NAME
    elif field == "contact_info":
        await query.edit_message_text("📞 Введите **новый** контакт (email или телефон):", parse_mode='Markdown')
        return State.EDITING_CONTACT
    elif field == "password":
        await query.edit_message_text("🔐 Для безопасности, введите ваш **текущий** пароль:", parse_mode='Markdown')
        return State.EDITING_PASSWORD_CURRENT

async def process_full_name_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет ФИО пользователя."""
    new_name = update.message.text
    user_id = context.user_data['current_user']['id']
    async with get_db_connection() as conn:
        await db_data.update_user_full_name(conn, user_id, new_name)
    await update.message.reply_text("✅ ФИО успешно обновлено!")
    await user_menu(update, context)
    return ConversationHandler.END

async def process_contact_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает новый контакт и отправляет на него код."""
    new_contact = normalize_phone_number(update.message.text)
    try:
        async with get_db_connection() as conn:
            await db_data.get_user_by_login(conn, new_contact)
        await update.message.reply_text("❌ Этот контакт уже занят. Попробуйте другой.")
        return State.EDITING_CONTACT
    except db_data.NotFoundError:
        pass

    context.user_data['new_contact_temp'] = new_contact
    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code

    sent = await send_verification_message(new_contact, code, context, update.effective_user.id)
    if sent:
        await update.message.reply_text(f"📲 На ваш новый контакт ({new_contact}) отправлен код. Введите его:")
        return State.AWAIT_CONTACT_VERIFICATION_CODE
    else:
        await update.message.reply_text("⚠️ Не удалось отправить код. Попробуйте снова.")
        return State.EDITING_CONTACT

async def verify_new_contact_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет код и обновляет контакт в БД."""
    if update.message.text == context.user_data.get('verification_code'):
        user_id = context.user_data['current_user']['id']
        new_contact = context.user_data.pop('new_contact_temp')
        async with get_db_connection() as conn:
            await db_data.update_user_contact(conn, user_id, new_contact)
        await update.message.reply_text("✅ Контакт успешно обновлен!")
        context.user_data.pop('verification_code', None)
        await user_menu(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте еще раз.")
        return State.AWAIT_CONTACT_VERIFICATION_CODE

# --- Обработчики смены пароля ---

async def check_current_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Проверяет текущий пароль пользователя."""
    current_password_input = update.message.text
    try:
        await update.message.delete()
    except Exception: pass

    if hash_password(current_password_input) == context.user_data['current_user']['password_hash']:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Пароль верный. Теперь введите **новый** пароль:", parse_mode='Markdown')
        return State.EDITING_PASSWORD_NEW
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Неверный пароль. Попробуйте еще раз или нажмите /cancel для отмены.")
        return State.EDITING_PASSWORD_CURRENT

async def get_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Получает новый пароль."""
    new_password = update.message.text
    try:
        await update.message.delete()
    except Exception: pass

    if len(new_password) < 8:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Пароль должен быть не менее 8 символов. Попробуйте снова.")
        return State.EDITING_PASSWORD_NEW

    context.user_data['new_password_temp'] = new_password
    await context.bot.send_message(chat_id=update.effective_chat.id, text="👍 Отлично. Повторите **новый** пароль для подтверждения:", parse_mode='Markdown')
    return State.EDITING_PASSWORD_CONFIRM

async def confirm_and_set_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждает и устанавливает новый пароль."""
    confirm_password = update.message.text
    try:
        await update.message.delete()
    except Exception: pass

    if confirm_password != context.user_data.get('new_password_temp'):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Пароли не совпадают. Попробуйте ввести новый пароль еще раз.")
        return State.EDITING_PASSWORD_NEW

    user_id = context.user_data['current_user']['id']
    new_password = context.user_data.pop('new_password_temp')

    async with get_db_connection() as conn:
        await db_data.update_user_password_by_id(conn, user_id, new_password)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="🎉 Пароль успешно изменен!")
    await user_menu(update, context)
    return ConversationHandler.END

# --- ConversationHandler для редактирования профиля ---
edit_profile_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_profile_edit, pattern="^edit_profile$")],
    states={
        State.EDIT_PROFILE_MENU: [CallbackQueryHandler(select_field_to_edit, pattern="^edit_field_")],
        State.EDITING_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_full_name_edit)],
        State.EDITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_contact_edit)],
        State.AWAIT_CONTACT_VERIFICATION_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, verify_new_contact_code)],
        State.EDITING_PASSWORD_CURRENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_current_password)],
        State.EDITING_PASSWORD_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_password)],
        State.EDITING_PASSWORD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_and_set_new_password)],
    },
    fallbacks=[CallbackQueryHandler(view_profile, pattern="^user_profile$")],
    map_to_parent={ ConversationHandler.END: State.USER_MENU },
    per_user=True,
    per_chat=True,
)
