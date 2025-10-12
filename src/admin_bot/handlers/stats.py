import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

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
        async with get_db_connection() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE telegram_id IS NOT NULL")
            total_books = await conn.fetchval("SELECT COUNT(*) FROM books")
            currently_borrowed = await conn.fetchval("SELECT COUNT(*) FROM borrowed_books WHERE return_date IS NULL")

        message = (
            f"📊 **Панель статистики**\n\n"
            f"👥 Активных пользователей: **{total_users or 0}**\n"
            f"📚 Книг в каталоге: **{total_books or 0}**\n"
            f"📖 Книг на руках: **{currently_borrowed or 0}**\n"
            f"✅ Книг доступно: **{(total_books or 0) - (currently_borrowed or 0)}**"
        )
        reply_markup = keyboards.get_stats_panel_keyboard()

        if query:
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        error_message = f"❌ Ошибка при получении статистики: {e}"
        if query:
            await query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный список пользователей."""
    query = update.callback_query
    page = int(query.data.split('_')[3])
    users_per_page = 5
    await query.answer()

    context.user_data['current_stats_page'] = page
    offset = page * users_per_page
    try:
        async with get_db_connection() as conn:
            users, total_users = await db_data.get_all_users(conn, limit=users_per_page, offset=offset)

        message_text = f"👥 **Список пользователей** (Всего: {total_users})\n\nСтраница {page + 1}:"
        reply_markup = keyboards.get_users_list_keyboard(users, total_users, page, users_per_page)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def view_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную карточку пользователя для админа."""
    query = update.callback_query
    await query.answer()
    current_page = context.user_data.get('current_stats_page', 0)
    user_id = int(query.data.split('_')[3])
    
    try:
        async with get_db_connection() as conn:
            user = await db_data.get_user_by_id(conn, user_id)
            borrow_history = await db_data.get_user_borrow_history(conn, user_id)
            borrowed_now = await db_data.get_borrowed_books(conn, user_id)

        reg_date = user['registration_date'].strftime("%d.%m.%Y %H:%M")
        age = calculate_age(user.get('dob'))
        
        message_parts = [
            "👤 **Карточка пользователя** 👤",
            "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`",
            f"🔹 **Имя:** `{user['full_name']}`",
            f"🔹 **Username:** `{user['username']}`",
            f"🔹 **Возраст:** `{age}`",
            f"🔹 **Статус:** `{user['status']}`",
            f"🔹 **Контакт:** `{user['contact_info']}`",
            f"🔹 **Telegram ID:** `{user.get('telegram_id', 'Не привязан')}`",
            f"🔹 **Telegram Username:** `@{user.get('telegram_username', 'Не указан')}`",
            f"🔹 **Регистрация:** `{reg_date}`",
            "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`",
            f"📚 **Книг на руках:** {len(borrowed_now)}",
        ]
        
        if borrowed_now:
            for book in borrowed_now:
                due_str = book['due_date'].strftime('%d.%m.%Y')
                message_parts.append(f"  • `{book['book_name']}` (до {due_str})")
        
        message_parts.append(f"\n📖 **Всего взято книг:** {len(borrow_history)}")
        
        if borrow_history:
            message_parts.append("\n**История (последние 5):**")
            for item in borrow_history[:5]:
                message_parts.append(f"  • `{item['book_name']}`")

        reply_markup = keyboards.get_user_profile_keyboard(user_id, current_page)
        await query.edit_message_text(
            "\n".join(message_parts),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
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
        async with get_db_connection() as conn:
            user_to_delete = await db_data.get_user_by_id(conn, user_id)
            username = user_to_delete.get('username', f'ID: {user_id}')
            await db_data.delete_user_by_admin(conn, user_id)

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
        async with get_db_connection() as conn:
            logs, total_logs = await db_data.get_user_activity(conn, user_id, limit=10, offset=page * 10)
            user = await db_data.get_user_by_id(conn, user_id)

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

async def show_ratings_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает общую статистику и историю оценок."""
    query = update.callback_query
    page = int(query.data.split('_')[2]) if query and "ratings_page_" in query.data else 0
    
    if query:
        await query.answer()
    
    ratings_per_page = 10
    
    try:
        async with get_db_connection() as conn:
            stats = await db_data.get_rating_statistics(conn)
            ratings, total = await db_data.get_all_ratings_paginated(
                conn, limit=ratings_per_page, offset=page * ratings_per_page
            )
        
        # Формируем статистику
        message_parts = [
            "⭐ **Статистика оценок**\n",
            f"📊 **Всего оценок:** {stats['total_ratings']}",
            f"📚 **Оценено книг:** {stats['books_rated']}",
            f"👥 **Пользователей оценило:** {stats['users_who_rated']}",
            f"📈 **Средняя оценка:** {'⭐' * round(stats['avg_rating'])} ({stats['avg_rating']:.2f}/5.0)\n",
        ]
        
        # Распределение оценок
        if stats['distribution']:
            message_parts.append("**Распределение:**")
            for rating in range(5, 0, -1):
                count = stats['distribution'].get(rating, 0)
                bar_length = int((count / stats['total_ratings']) * 10) if stats['total_ratings'] > 0 else 0
                bar = "█" * bar_length + "░" * (10 - bar_length)
                message_parts.append(f"{'⭐' * rating}: {bar} {count}")
            message_parts.append("")
        
        # История оценок
        if ratings:
            message_parts.append(f"**📜 История оценок** (стр. {page + 1}/{(total + ratings_per_page - 1) // ratings_per_page}):\n")
            
            for r in ratings:
                stars = "⭐" * r['rating']
                date_str = r['rated_at'].strftime('%d.%m %H:%M') if r['rated_at'] else 'Неизвестно'
                message_parts.append(
                    f"{stars} — `{r['book_name']}`\n"
                    f"   _@{r['username']} • {date_str}_"
                )
        else:
            message_parts.append("_Пока нет оценок._")
        
        # Навигация
        keyboard = []
        nav_buttons = []
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"ratings_page_{page - 1}"))
        if (page + 1) * ratings_per_page < total:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"ratings_page_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("📊 Назад к статистике", callback_data="back_to_stats_panel")])
        
        message_text = "\n".join(message_parts)
        
        if query:
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Ошибка при получении истории оценок: {e}", exc_info=True)
        error_msg = f"❌ Ошибка: {e}"
        if query:
            await query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)