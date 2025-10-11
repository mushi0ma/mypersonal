import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks

logger = logging.getLogger(__name__)


async def show_book_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех запросов на книги."""
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()
    
    try:
        async with get_db_connection() as conn:
            requests = await db_data.get_pending_book_requests(conn)
        
        if not requests:
            message_text = (
                "📚 **Запросы на книги**\n\n"
                "Нет ожидающих запросов."
            )
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_stats_panel")]]
        else:
            message_text = f"📚 **Запросы на книги** (Всего: {len(requests)})\n"
            keyboard = []
            
            for req in requests:
                created = req['created_at'].strftime('%d.%m %H:%M')
                button_text = f"📖 {req['book_name'][:30]} — {req['username']} ({created})"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"view_request_{req['id']}")
                ])
            
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_stats_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Ошибка при получении запросов: {e}", exc_info=True)
        error_msg = f"❌ Ошибка: {e}"
        if query:
            await query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)


async def view_book_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную информацию о запросе."""
    query = update.callback_query
    await query.answer()
    
    request_id = int(query.data.split('_')[2])
    
    try:
        async with get_db_connection() as conn:
            request_data = await conn.fetchrow(
                """
                SELECT br.*, u.username, u.full_name, u.telegram_id
                FROM book_requests br
                JOIN users u ON br.user_id = u.id
                WHERE br.id = $1
                """,
                request_id
            )
        
        if not request_data:
            await query.edit_message_text("❌ Запрос не найден.")
            return
        
        created = request_data['created_at'].strftime('%d.%m.%Y %H:%M')
        
        message_parts = [
            f"📚 **Запрос #{request_id}**",
            "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`",
            f"📖 **Книга:** `{request_data['book_name']}`",
            f"✍️ **Автор:** `{request_data['author_name']}`",
            f"🎭 **Жанр:** `{request_data['genre'] or 'Не указан'}`",
            f"📝 **Описание:**\n_{request_data['description'] or 'Нет'}_\n",
            f"👤 **Запросил:** @{request_data['username']} ({request_data['full_name']})",
            f"📅 **Дата:** `{created}`",
            "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
        ]
        
        keyboard = [
            [InlineKeyboardButton("✅ Одобрить и добавить книгу", callback_data=f"approve_request_{request_id}")],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_request_{request_id}")],
            [InlineKeyboardButton("⬅️ К списку запросов", callback_data="view_requests")]
        ]
        
        await query.edit_message_text(
            "\n".join(message_parts),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре запроса: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")


async def approve_request_and_add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобряет запрос и автоматически добавляет книгу."""
    query = update.callback_query
    await query.answer()
    
    request_id = int(query.data.split('_')[2])
    
    try:
        async with get_db_connection() as conn:
            # Получаем данные запроса
            request_data = await db_data.approve_book_request(conn, request_id)
            
            # Добавляем книгу
            book_data = {
                'name': request_data['book_name'],
                'author': request_data['author_name'],
                'genre': request_data['genre'] or 'Разное',
                'description': request_data['description'] or 'Добавлено по запросу пользователя',
                'total_quantity': 1
            }
            
            book_id = await db_data.add_new_book(conn, book_data)
        
        # Уведомляем пользователя
        tasks.notify_user.delay(
            user_id=request_data['user_id'],
            text=(
                f"🎉 **Отличные новости!**\n\n"
                f"Ваш запрос на книгу «{request_data['book_name']}» одобрен!\n"
                f"Книга добавлена в библиотеку и доступна для взятия."
            ),
            category='book_request_approved',
            button_text="📖 Посмотреть книгу",
            button_callback=f"view_book_{book_id}"
        )
        
        tasks.notify_admin.delay(
            text=f"✅ Запрос #{request_id} одобрен. Книга «{request_data['book_name']}» добавлена в каталог.",
            category='admin_action'
        )
        
        await query.edit_message_text(
            f"✅ **Запрос одобрен!**\n\n"
            f"Книга «{request_data['book_name']}» добавлена в библиотеку.\n"
            f"Пользователь получил уведомление.",
            parse_mode='Markdown'
        )
        
        await show_book_requests(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка при одобрении запроса: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")


async def reject_book_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклоняет запрос на книгу."""
    query = update.callback_query
    await query.answer()
    
    request_id = int(query.data.split('_')[2])
    
    try:
        async with get_db_connection() as conn:
            request_data = await conn.fetchrow(
                "SELECT user_id, book_name FROM book_requests WHERE id = $1",
                request_id
            )
            
            await db_data.reject_book_request(
                conn, request_id,
                reason="Книга не соответствует профилю библиотеки"
            )
        
        # Уведомляем пользователя
        tasks.notify_user.delay(
            user_id=request_data['user_id'],
            text=(
                f"😔 К сожалению, ваш запрос на книгу «{request_data['book_name']}» был отклонен.\n\n"
                f"Причина: Книга не соответствует профилю нашей библиотеки."
            ),
            category='book_request_rejected'
        )
        
        await query.edit_message_text(
            f"✅ Запрос #{request_id} отклонен.\nПользователь получил уведомление.",
            parse_mode='Markdown'
        )
        
        await show_book_requests(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка при отклонении запроса: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")