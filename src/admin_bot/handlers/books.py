import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks
from src.admin_bot import keyboards
from src.admin_bot.states import AdminState
from src.core.utils import rate_limit

logger = logging.getLogger(__name__)

# --- Вспомогательная функция для построения карточки книги ---
def _build_book_details_content(conn, book_id, current_page=0):
    """Строит контент для карточки книги (текст и клавиатуру)."""
    book = db_data.get_book_details(conn, book_id)
    if not book:
        raise db_data.NotFoundError("Книга не найдена.")

    message_parts = [
        f"**📖 Карточка книги: «{book['name']}»**",
        f"**Автор:** {book['author']}",
        f"**Жанр:** {book['genre']}",
        f"**Описание:** {book.get('description', '_Нет описания_')}\n"
    ]
    if book.get('username'):
        borrow_date_str = book['borrow_date'].strftime('%d.%m.%Y')
        message_parts.append(f"🔴 **Статус:** Занята (у @{book['username']} с {borrow_date_str})")
    else:
        message_parts.append("🟢 **Статус:** Свободна")

    message_text = "\n".join(message_parts)
    reply_markup = keyboards.get_book_details_keyboard(book_id, bool(book.get('username')), current_page)
    return {'text': message_text, 'reply_markup': reply_markup, 'cover_id': book.get('cover_image_id')}

# --- Обработчики просмотра списка и карточки книги ---

@rate_limit(seconds=2)
async def show_books_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный список всех книг."""
    query = update.callback_query
    page = 0
    books_per_page = 5

    if query:
        await query.answer()
        if "books_page_" in query.data:
            page = int(query.data.split('_')[2])

    context.user_data['current_books_page'] = page
    offset = page * books_per_page

    with get_db_connection() as conn:
        books, total_books = db_data.get_all_books_paginated(conn, limit=books_per_page, offset=offset)

    message_text = f"📚 **Управление каталогом** (Всего: {total_books})\n\nСтраница {page + 1}:"
    reply_markup = keyboards.get_books_list_keyboard(books, total_books, page, books_per_page)

    if query:
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_book_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную карточку книги."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[3])
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            content = _build_book_details_content(conn, book_id, current_page)

        if query.message.photo and not content.get('cover_id'):
            await query.message.delete()
        elif query.message.text and content.get('cover_id'):
            await query.message.delete()

        if content.get('cover_id'):
            if query.message.photo:
                await query.edit_message_caption(caption=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')
            else:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=content['cover_id'], caption=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')
        else:
            await query.edit_message_text(text=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')
    except db_data.NotFoundError:
        await query.edit_message_text("❌ Книга не найдена.")
    except Exception as e:
        logger.error(f"Ошибка в show_book_details: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Ошибка: {e}")

    return ConversationHandler.END

# --- Обработчики диалога добавления книги ---

async def add_book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    query = update.callback_query
    await query.answer()
    context.user_data['new_book'] = {}
    await query.edit_message_text("**➕ Добавление книги**\n\n**Шаг 1/5: Введите название.**", parse_mode='Markdown')
    return AdminState.GET_NAME

async def get_book_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['name'] = update.message.text
    await update.message.reply_text("**Шаг 2/5: Введите автора.**", parse_mode='Markdown')
    return AdminState.GET_AUTHOR

async def get_book_author(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['author'] = update.message.text
    await update.message.reply_text("**Шаг 3/5: Введите жанр.**", parse_mode='Markdown')
    return AdminState.GET_GENRE

async def get_book_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['genre'] = update.message.text
    await update.message.reply_text("**Шаг 4/5: Введите описание.**", parse_mode='Markdown')
    return AdminState.GET_DESCRIPTION

async def get_book_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['description'] = update.message.text
    await update.message.reply_text("**Шаг 5/5: Отправьте фото обложки** или 'пропустить'.", parse_mode='Markdown')
    return AdminState.GET_COVER

async def show_add_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    book_data = context.user_data['new_book']
    text = "\n".join([f"**{k.capitalize()}:** {v}" for k, v in book_data.items() if k != 'cover_image_id'])
    reply_markup = keyboards.get_add_book_confirmation_keyboard()

    if book_data.get('cover_image_id'):
        await update.message.delete()
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=book_data['cover_image_id'], caption=f"**🔍 Проверьте данные:**\n{text}", reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"**🔍 Проверьте данные:**\n{text}", reply_markup=reply_markup, parse_mode='Markdown')

async def get_book_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['cover_image_id'] = update.message.photo[-1].file_id
    await show_add_confirmation(update, context)
    return AdminState.CONFIRM_ADD

async def skip_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    context.user_data['new_book']['cover_image_id'] = None
    await update.message.reply_text("👌 Обложка пропущена.")
    await show_add_confirmation(update, context)
    return AdminState.CONFIRM_ADD

async def add_book_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    should_notify = "_notify" in query.data
    book_data = context.user_data.pop('new_book')

    with get_db_connection() as conn:
        new_book_id = db_data.add_new_book(conn, book_data)

    tasks.notify_admin.delay(text=f"➕ Админ добавил книгу «{book_data['name']}».")
    if should_notify:
        tasks.broadcast_new_book.delay(book_id=new_book_id)

    await query.edit_message_text("✅ Книга успешно добавлена!", reply_markup=None)
    await show_books_list(update, context)
    return ConversationHandler.END

async def add_book_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('new_book', None)
    await query.edit_message_text("👌 Добавление книги отменено.", reply_markup=None)
    await show_books_list(update, context)
    return ConversationHandler.END

# --- Обработчики диалога редактирования книги ---

async def start_book_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    query = update.callback_query
    await query.answer()
    context.user_data['book_to_edit'] = int(query.data.split('_')[3])
    reply_markup = keyboards.get_book_edit_keyboard()
    await query.edit_message_text("✏️ Какое поле вы хотите отредактировать?", reply_markup=reply_markup)
    return AdminState.SELECTING_BOOK_FIELD

async def prompt_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    query = update.callback_query
    await query.answer()
    context.user_data['field_to_edit'] = query.data.split('_')[2]
    field_map = {'name': 'название', 'author': 'автора', 'genre': 'жанр', 'description': 'описание'}
    await query.edit_message_text(f"Пришлите новое **{field_map[context.user_data['field_to_edit']]}**.", parse_mode='Markdown')
    return AdminState.UPDATING_BOOK_FIELD

async def process_book_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    book_id = context.user_data['book_to_edit']
    field = context.user_data['field_to_edit']
    with get_db_connection() as conn:
        db_data.update_book_field(conn, book_id, field, update.message.text)

    tasks.notify_admin.delay(text=f"✏️ Админ отредактировал поле `{field}` для книги ID {book_id}.")
    await update.message.reply_text("✅ Информация о книге успешно обновлена!")

    from telegram import CallbackQuery
    update.callback_query = CallbackQuery(id="dummy", from_user=update.effective_user, chat_instance="dummy", data=f"admin_view_book_{book_id}")
    await show_book_details(update, context)
    return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    book_id = context.user_data['book_to_edit']
    from telegram import CallbackQuery
    update.callback_query = CallbackQuery(id="dummy", from_user=update.effective_user, chat_instance="dummy", data=f"admin_view_book_{book_id}")
    await show_book_details(update, context)
    return ConversationHandler.END

# --- Обработчики удаления книги ---

async def ask_for_book_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[3])
    reply_markup = keyboards.get_book_delete_confirmation_keyboard(book_id)
    await query.edit_message_text("**⚠️ Вы уверены, что хотите удалить эту книгу?**", reply_markup=reply_markup, parse_mode='Markdown')

async def process_book_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[4])

    with get_db_connection() as conn:
        book_to_delete = db_data.get_book_details(conn, book_id)
        db_data.delete_book(conn, book_id)

    tasks.notify_admin.delay(text=f"🗑️ Админ удалил книгу «{book_to_delete.get('name', 'ID: ' + str(book_id))}».")
    await query.edit_message_text("✅ Книга успешно удалена.")
    await show_books_list(update, context)

# --- ConversationHandlers ---

add_book_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_book_start, pattern="^admin_add_book_start$")],
    states={
        AdminState.GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_name)],
        AdminState.GET_AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_author)],
        AdminState.GET_GENRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_genre)],
        AdminState.GET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_description)],
        AdminState.GET_COVER: [MessageHandler(filters.PHOTO, get_book_cover), MessageHandler(filters.TEXT & ~filters.COMMAND, skip_cover)],
        AdminState.CONFIRM_ADD: [CallbackQueryHandler(add_book_save, pattern="^add_book_save_"), CallbackQueryHandler(add_book_cancel, pattern="^add_book_cancel$")]
    },
    fallbacks=[CallbackQueryHandler(show_books_list, pattern="^books_page_0$")], # Fallback to the book list
)

edit_book_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_book_edit, pattern="^admin_edit_book_")],
    states={
        AdminState.SELECTING_BOOK_FIELD: [CallbackQueryHandler(prompt_for_update, pattern="^edit_field_")],
        AdminState.UPDATING_BOOK_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_book_update)],
    },
    fallbacks=[CallbackQueryHandler(cancel_edit, pattern="^cancel_edit$")],
)