import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks
from src.admin_bot import keyboards
from src.admin_bot.states import AdminState
from src.core.utils import rate_limit

logger = logging.getLogger(__name__)

# --- Вспомогательная функция для построения карточки книги ---
async def _build_book_details_content(conn, book_id, current_page=0):
    """Строит контент для карточки книги (текст и клавиатуру)."""
    book = await db_data.get_book_details(conn, book_id)
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

    async with get_db_connection() as conn:
        books, total_books = await db_data.get_all_books_paginated(conn, limit=books_per_page, offset=offset)

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
        async with get_db_connection() as conn:
            content = await _build_book_details_content(conn, book_id, current_page)

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

    async with get_db_connection() as conn:
        new_book_id = await db_data.add_new_book(conn, book_data)

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


async def start_bulk_add_books(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Начинает процесс массового добавления книг."""
    query = update.callback_query
    await query.answer()
    
    instruction_text = (
        "📚 **Массовое добавление книг**\n\n"
        "Отправьте CSV файл со следующими колонками:\n"
        "`name,author,genre,description,quantity`\n\n"
        "**Пример файла:**\n"
        "```\n"
        "Война и мир,Лев Толстой,Роман,Описание книги,3\n"
        "1984,Джордж Оруэлл,Антиутопия,Описание,2\n"
        "```\n\n"
        "📝 **Важно:**\n"
        "• Первая строка должна быть заголовком\n"
        "• Разделитель: запятая (,)\n"
        "• Кодировка: UTF-8\n"
        "• Если автор новый, он будет создан автоматически"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="books_page_0")]]
    
    await query.edit_message_text(
        instruction_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return AdminState.BULK_ADD_WAITING_FILE


async def process_bulk_add_csv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает CSV файл с книгами."""
    if not update.message.document:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте CSV файл."
        )
        return AdminState.BULK_ADD_WAITING_FILE
    
    document = update.message.document
    
    if not document.file_name.endswith('.csv'):
        await update.message.reply_text(
            "❌ Неверный формат файла. Ожидается .csv"
        )
        return AdminState.BULK_ADD_WAITING_FILE
    
    await update.message.reply_text("⏳ Обрабатываю файл...")
    
    try:
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        csv_text = file_content.decode('utf-8')
        
        # Парсим CSV
        import csv
        import io
        
        reader = csv.DictReader(io.StringIO(csv_text))
        books_to_add = []
        
        for row in reader:
            books_to_add.append({
                'name': row['name'].strip(),
                'author': row['author'].strip(),
                'genre': row['genre'].strip(),
                'description': row['description'].strip(),
                'total_quantity': int(row['quantity'])
            })
        
        # Добавляем книги в БД
        added_count = 0
        skipped_count = 0
        errors = []
        
        async with get_db_connection() as conn:
            for book_data in books_to_add:
                try:
                    await db_data.add_new_book(conn, book_data)
                    added_count += 1
                except Exception as e:
                    skipped_count += 1
                    errors.append(f"'{book_data['name']}': {str(e)[:50]}")
        
        # Формируем отчет
        report_parts = [
            "✅ **Импорт завершен**\n",
            f"📥 **Добавлено книг:** {added_count}",
            f"⚠️ **Пропущено:** {skipped_count}"
        ]
        
        if errors:
            report_parts.append("\n**Ошибки:**")
            for error in errors[:5]:
                report_parts.append(f"• {error}")
            if len(errors) > 5:
                report_parts.append(f"_...и еще {len(errors) - 5}_")
        
        tasks.notify_admin.delay(
            text=f"📚 Массовый импорт: добавлено {added_count} книг, пропущено {skipped_count}.",
            category='admin_action'
        )
        
        await update.message.reply_text(
            "\n".join(report_parts),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при массовом добавлении книг: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка обработки файла:\n`{str(e)}`",
            parse_mode='Markdown'
        )
    
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
    async with get_db_connection() as conn:
        await db_data.update_book_field(conn, book_id, field, update.message.text)

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

    async with get_db_connection() as conn:
        book_to_delete = await db_data.get_book_details(conn, book_id)
        await db_data.delete_book(conn, book_id)

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
    fallbacks=[CallbackQueryHandler(show_books_list, pattern="^books_page_0$")],
    per_user=True,
    per_chat=True
)

edit_book_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_book_edit, pattern="^admin_edit_book_")],
    states={
        AdminState.SELECTING_BOOK_FIELD: [CallbackQueryHandler(prompt_for_update, pattern="^edit_field_")],
        AdminState.UPDATING_BOOK_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_book_update)],
    },
    fallbacks=[CallbackQueryHandler(cancel_edit, pattern="^cancel_edit$")],
    per_chat=True,
    per_user=True
)

bulk_add_books_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_bulk_add_books, pattern="^bulk_add_start$")
    ],
    states={
        AdminState.BULK_ADD_WAITING_FILE: [
            MessageHandler(filters.Document.FileExtension('csv'), process_bulk_add_csv)
        ]
    },
    fallbacks=[
        CallbackQueryHandler(show_books_list, pattern="^books_page_0$")
    ],
    per_user=True,
    per_chat=True
)