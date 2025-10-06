import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.core import config
from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks
from src.admin_bot import keyboards

logger = logging.getLogger(__name__)

def calculate_age(dob_string: str) -> str:
    """Вычисляет возраст на основе строки с датой рождения (ДД.ММ.ГГГГ)."""
    if not dob_string:
        return "?? лет"
    try:
        from datetime import datetime
        birth_date = datetime.strptime(dob_string, "%d.%m.%Y")
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return f"{age} лет"
    except (ValueError, TypeError):
        return "?? лет"

async def show_stats_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает общую статистику системы."""
    query = update.callback_query
    if query:
        await query.answer()

    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users WHERE telegram_id IS NOT NULL")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM books")
            total_books = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM borrowed_books WHERE return_date IS NULL")
            currently_borrowed = cur.fetchone()[0]

        message = (
            f"📊 **Панель статистики**\n\n"
            f"👥 Активных пользователей: **{total_users}**\n"
            f"📚 Книг в каталоге: **{total_books}**\n"
            f"📖 Книг на руках: **{currently_borrowed}**\n"
            f"✅ Книг доступно: **{total_books - currently_borrowed}**"
        )
        reply_markup = keyboards.get_stats_panel_keyboard()

        if query:
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        await update.effective_message.reply_text(f"❌ Ошибка при получении статистики: {e}")

async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный список пользователей."""
    query = update.callback_query
    page = int(query.data.split('_')[3])
    users_per_page = 5
    await query.answer()

    context.user_data['current_stats_page'] = page
    offset = page * users_per_page
    try:
        with get_db_connection() as conn:
            users, total_users = db_data.get_all_users(conn, limit=users_per_page, offset=offset)

        message_text = f"👥 **Список пользователей** (Всего: {total_users})\n\nСтраница {page + 1}:"
        reply_markup = keyboards.get_users_list_keyboard(users, total_users, page, users_per_page)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def view_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную карточку пользователя."""
    query = update.callback_query
    await query.answer()
    current_page = context.user_data.get('current_stats_page', 0)
    user_id = int(query.data.split('_')[3])
    try:
        with get_db_connection() as conn:
            user = db_data.get_user_by_id(conn, user_id)
            borrow_history = db_data.get_user_borrow_history(conn, user_id)

        reg_date = user['registration_date'].strftime("%d.%m.%Y %H:%M")
        age = calculate_age(user.get('dob'))
        message_parts = [
            f"**👤 Карточка: `{user['username']}`**",
            f"**ФИО:** {user['full_name']}",
            f"**Возраст:** {age}",
            f"**Статус:** {user['status']}",
            f"**Регистрация:** {reg_date}\n",
            "**📚 История взятых книг:**"
        ]
        if borrow_history:
            for item in borrow_history:
                message_parts.append(f" - `{item['book_name']}`")
        else:
            message_parts.append("  _Нет записей._")

        reply_markup = keyboards.get_user_profile_keyboard(user_id, current_page)
        await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при получении карточки пользователя: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def ask_for_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Спрашивает у админа подтверждение на удаление."""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split('_')[3])
    reply_markup = keyboards.get_user_delete_confirmation_keyboard(user_id)
    await query.edit_message_text(
        "**⚠️ Вы уверены?**\n\nЭто действие вернет все книги пользователя и обезличит аккаунт. Отменить будет невозможно.",
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def process_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает подтверждение и удаляет пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split('_')[3])
    current_page = context.user_data.get('current_stats_page', 0)
    try:
        with get_db_connection() as conn:
            user_to_delete = db_data.get_user_by_id(conn, user_id)
            username = user_to_delete.get('username', f'ID: {user_id}')
            db_data.delete_user_by_admin(conn, user_id)

        tasks.notify_admin.delay(text=f"🗑️ Админ удалил (анонимизировал) пользователя: @{username}", category='admin_action')
        await query.edit_message_text("✅ Пользователь успешно удален (анонимизирован).")

        query.data = f"users_list_page_{current_page}"
        await show_users_list(update, context)
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя admin'ом: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка при удалении: {e}")

async def show_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный лог активности пользователя."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    user_id, page = int(parts[2]), int(parts[3])

    try:
        with get_db_connection() as conn:
            logs, total_logs = db_data.get_user_activity(conn, user_id, limit=10, offset=page * 10)
            user = db_data.get_user_by_id(conn, user_id)

        message_parts = [f"**📜 Журнал действий для `{user['username']}`** (Стр. {page + 1})\n"]
        if logs:
            for log in logs:
                ts = log['timestamp'].strftime('%d.%m.%Y %H:%M')
                details = f"({log['details']})" if log['details'] else ""
                message_parts.append(f"`{ts}`: **{log['action']}** {details}")
        else:
            message_parts.append("  _Нет записей._")

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_activity_{user_id}_{page - 1}"))
        if (page + 1) * 10 < total_logs:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_activity_{user_id}_{page + 1}"))

        keyboard = [nav_buttons] if nav_buttons else []
        keyboard.append([InlineKeyboardButton("👤 Назад к карточке", callback_data=f"admin_view_user_{user_id}")])

        await query.edit_message_text("\n".join(message_parts), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при получении логов: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")