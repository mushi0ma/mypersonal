# -*- coding: utf-8 -*-
import os
from librarybot import rate_limit
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Загрузка переменных окружения ---
load_dotenv()
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# --- Импорт наших модулей ---
import db_data
from db_utils import get_db_connection # Импортируем функцию для получения соединения
import tasks

# --- Состояния для диалогов ---
BROADCAST_MESSAGE = range(1)
SELECTING_BOOK_FIELD, UPDATING_BOOK_FIELD = range(2, 4)
GET_NAME, GET_AUTHOR, GET_GENRE, GET_DESCRIPTION, GET_COVER, CONFIRM_ADD = range(4, 10)

# --- Ограничение доступа ---
admin_filter = filters.User(user_id=ADMIN_TELEGRAM_ID)

# --------------------------
# --- Вспомогательные функции ---
# --------------------------

def calculate_age(dob_string: str) -> str:
    """Вычисляет возраст на основе строки с датой рождения (ДД.ММ.ГГГГ)."""
    if not dob_string:
        return "?? лет"
    try:
        birth_date = datetime.strptime(dob_string, "%d.%m.%Y")
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return f"{age} лет"
    except (ValueError, TypeError):
        return "?? лет"

# --------------------------
# --- Основные обработчики ---
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение для админа."""
    await update.message.reply_text(
        "👋 **Добро пожаловать в панель администратора!**\n\n"
        "Здесь вы можете управлять ботом. Доступные команды:\n\n"
        "📊 /stats - Показать статистику и управлять пользователями\n"
        "📚 /books - Управление каталогом книг\n"
        "📢 /broadcast - Отправить сообщение всем пользователям"
    )

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог массовой рассылки."""
    await update.message.reply_text("📢 **Рассылка**\n\nВведите сообщение, которое получат все пользователи. Для отмены введите /cancel.")
    return BROADCAST_MESSAGE

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает и ставит в очередь задачи на рассылку."""
    message_text = update.message.text
    await update.message.reply_text("⏳ Начинаю рассылку...")
    try:
        with get_db_connection() as conn:
            user_db_ids = db_data.get_all_user_ids(conn)
        for user_id in user_db_ids:
            tasks.notify_user.delay(user_id=user_id, text=message_text, category='broadcast')
        await update.message.reply_text(f"✅ Рассылка успешно запущена для {len(user_db_ids)} пользователей.")

        admin_text = f"📢 Админ запустил рассылку для {len(user_db_ids)} пользователей."
        tasks.notify_admin.delay(text=admin_text, category='admin_action')

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запуске рассылки: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог."""
    message = "👌 Действие отменено."
    if update.callback_query:
        await update.callback_query.answer()
        # Проверяем, есть ли у сообщения caption (если это фото)
        if update.callback_query.message.caption:
            await update.callback_query.edit_message_caption(caption=message)
        else:
            await update.callback_query.edit_message_text(message)
    else:
        await update.message.reply_text(message)
        
    # Очищаем временные данные, если они есть
    context.user_data.pop('book_to_edit', None)
    context.user_data.pop('field_to_edit', None)
    context.user_data.pop('new_book', None)
    
    return ConversationHandler.END

async def show_stats_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает общую статистику системы и кнопки для управления."""
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
            cur.execute("SELECT COUNT(*) FROM borrowed_books WHERE return_date IS NOT NULL AND return_date <= due_date")
            on_time_returns = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM borrowed_books WHERE return_date IS NOT NULL")
            total_returns = cur.fetchone()[0]
            on_time_rate = (on_time_returns / total_returns * 100) if total_returns > 0 else 0
        
        message = (
            f"📊 **Панель статистики**\n\n"
            f"👥 Активных пользователей: **{total_users}**\n"
            f"📚 Книг в каталоге: **{total_books}**\n"
            f"📖 Книг на руках: **{currently_borrowed}**\n"
            f"✅ Книг доступно: **{total_books - currently_borrowed}**\n\n"
            f"📈 Возвращено вовремя: **{on_time_rate:.1f}%**"
        )
        
        keyboard = [
            [InlineKeyboardButton("👥 Посмотреть список пользователей", callback_data="users_list_page_0")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        error_message = f"❌ Ошибка при получении статистики: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `show_stats_panel`\n**Ошибка:** `{e}`")
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
        with get_db_connection() as conn:
            users, total_users = db_data.get_all_users(conn, limit=users_per_page, offset=offset)
        
        message_text = f"👥 **Список пользователей** (Всего: {total_users})\n\nСтраница {page + 1}:\nНажмите на пользователя для деталей."
        keyboard = []
        for user in users:
            button_text = f"👤 {user['username']} ({user['full_name']})"
            callback_data = f"admin_view_user_{user['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"users_list_page_{page - 1}"))
        if (page + 1) * users_per_page < total_users:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"users_list_page_{page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("📊 Назад к статистике", callback_data="back_to_stats_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        error_message = f"❌ Ошибка при получении списка пользователей: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `show_users_list`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)

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
            rating_history = db_data.get_user_ratings(conn, user_id)
        reg_date = user['registration_date'].strftime("%d.%m.%Y %H:%M")
        age = calculate_age(user['dob'])
        message_parts = [
            f"**👤 Карточка пользователя: `{user['username']}`**",
            f"**ФИО:** {user['full_name']}",
            f"**Возраст:** {age}",
            f"**Статус:** {user['status']}",
            f"**Контакт:** `{user['contact_info']}`",
            f"**Регистрация:** {reg_date}\n",
            "**📚 История взятых книг:**"
        ]
        if borrow_history:
            for item in borrow_history:
                return_date_str = item['return_date'].strftime('%d.%m.%Y') if item['return_date'] else "На руках"
                borrow_date_str = item['borrow_date'].strftime('%d.%m.%Y')
                message_parts.append(f" - `{item['book_name']}` (взята: {borrow_date_str}, возвращена: {return_date_str})")
        else:
            message_parts.append("  _Нет записей._")
        message_parts.append("\n**⭐ История оценок:**")
        if rating_history:
            for item in rating_history:
                stars = "⭐" * item['rating']
                message_parts.append(f" - `{item['book_name']}`: {stars}")
        else:
            message_parts.append("  _Нет оценок._")
        message_text = "\n".join(message_parts)
        keyboard = [
            [InlineKeyboardButton("📜 История действий", callback_data=f"admin_activity_{user_id}_0")],
            [InlineKeyboardButton("🗑️ Удалить пользователя", callback_data=f"admin_delete_user_{user_id}")],
            [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"users_list_page_{current_page}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        error_message = f"❌ Ошибка при получении карточки пользователя: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `view_user_profile`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)

async def ask_for_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Спрашивает у админа подтверждение на удаление."""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split('_')[3])
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_delete_{user_id}")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_view_user_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "**⚠️ Вы уверены, что хотите удалить этого пользователя?**\n\n"
        "Это действие вернет все его книги и обезличит аккаунт. История действий сохранится. Отменить это будет невозможно.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
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
        
        admin_text = f"🗑️ Админ удалил (анонимизировал) пользователя: @{username}"
        tasks.notify_admin.delay(text=admin_text, category='admin_action')

        await query.edit_message_text(f"✅ Пользователь успешно удален (анонимизирован).")
        # Имитируем нажатие кнопки "назад к списку"
        query.data = f"users_list_page_{current_page}"
        await show_users_list(update, context)

    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя admin'ом: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `process_delete_confirmation`\n**Ошибка:** `{e}`")
        keyboard = [[InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"users_list_page_{current_page}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"❌ Ошибка при удалении: {e}", reply_markup=reply_markup)

async def show_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный лог активности пользователя."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    logs_per_page = 10

    try:
        with get_db_connection() as conn:
            logs, total_logs = db_data.get_user_activity(conn, user_id, limit=logs_per_page, offset=page * logs_per_page)
            user = db_data.get_user_by_id(conn, user_id)
            
        message_parts = [f"**📜 Журнал действий для `{user['username']}`** (Всего: {total_logs}, Стр. {page + 1})\n"]

        if logs:
            for log in logs:
                timestamp_str = log['timestamp'].strftime('%d.%m.%Y %H:%M')
                details = f"({log['details']})" if log['details'] else ""
                message_parts.append(f"`{timestamp_str}`: **{log['action']}** {details}")
        else:
            message_parts.append("  _Нет записей об активности._")

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_activity_{user_id}_{page - 1}"))
        if (page + 1) * logs_per_page < total_logs:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"admin_activity_{user_id}_{page + 1}"))

        keyboard = []
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("👤 Назад к карточке", callback_data=f"admin_view_user_{user_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        error_message = f"❌ Произошла ошибка при получении логов: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `show_user_activity`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)

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

    try:
        with get_db_connection() as conn:
            books, total_books = db_data.get_all_books_paginated(conn, limit=books_per_page, offset=offset)

        message_text = f"📚 **Управление каталогом** (Всего: {total_books})\n\nСтраница {page + 1}:"
        keyboard = [
            [InlineKeyboardButton("➕ Добавить новую книгу", callback_data="admin_add_book_start")]
        ]
        for book in books:
            status_icon = "🔴" if book['is_borrowed'] else "🟢"
            button_text = f"{status_icon} {book['name']}"
            callback_data = f"admin_view_book_{book['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"books_page_{page - 1}"))
        if (page + 1) * books_per_page < total_books:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"books_page_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        error_message = f"❌ Ошибка при получении списка книг: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `show_books_list`\n**Ошибка:** `{e}`")
        if query:
            await query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)

def _build_book_details_content(conn, book_id, current_page=0):
    """Строит контент для карточки книги (текст и клавиатуру)."""
    book = db_data.get_book_details(conn, book_id)
    if not book:
        raise db_data.NotFoundError("Книга не найдена.")

    message_parts = [
        f"**📖 Карточка книги: «{book['name']}»**",
        f"**Автор:** {book['author']}",
        f"**Жанр:** {book['genre']}",
        f"**Описание:** {book['description']}\n"
    ]
    if book['username']:
        borrow_date_str = book['borrow_date'].strftime('%d.%m.%Y')
        message_parts.append(f"🔴 **Статус:** Занята (у @{book['username']} с {borrow_date_str})")
    else:
        message_parts.append("🟢 **Статус:** Свободна")

    message_text = "\n".join(message_parts)

    keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data=f"admin_edit_book_{book['id']}")]]
    if not book['username']:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_book_{book['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку книг", callback_data=f"books_page_{current_page}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    return {'text': message_text, 'reply_markup': reply_markup, 'cover_id': book.get('cover_image_id')}

async def show_book_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детальную карточку книги."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[3])
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            content = _build_book_details_content(conn, book_id, current_page)

        # Удаляем предыдущее сообщение, чтобы избежать дублей
        if query.message.photo and not content.get('cover_id'):
             await query.message.delete()
        elif query.message.text and content.get('cover_id'):
             await query.message.delete()

        if content.get('cover_id'):
            if query.message.photo:
                 await query.edit_message_caption(caption=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')
            else:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=content['cover_id'],
                    caption=content['text'],
                    reply_markup=content['reply_markup'],
                    parse_mode='Markdown'
                )
        else:
            await query.edit_message_text(text=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')

    except db_data.NotFoundError:
        await query.edit_message_text("❌ Книга не найдена.")
    except Exception as e:
        error_message = f"❌ Произошла ошибка при получении деталей книги: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `show_book_details`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)
    
    return ConversationHandler.END # Явный выход из диалога редактирования, если он был активен

async def start_book_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог редактирования книги, показывая поля для выбора."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[3])
    context.user_data['book_to_edit'] = book_id

    keyboard = [
        [InlineKeyboardButton("Название", callback_data=f"edit_field_name")],
        [InlineKeyboardButton("Автор", callback_data=f"edit_field_author")],
        [InlineKeyboardButton("Жанр", callback_data=f"edit_field_genre")],
        [InlineKeyboardButton("Описание", callback_data=f"edit_field_description")],
        [InlineKeyboardButton("⬅️ Отмена", callback_data=f"cancel_edit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "✏️ Какое поле вы хотите отредактировать?"
    if query.message.caption:
        await query.edit_message_caption(caption=message_text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    
    return SELECTING_BOOK_FIELD

async def prompt_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у администратора новое значение для выбранного поля."""
    query = update.callback_query
    await query.answer()
    
    field_to_edit = query.data.split('_')[2]
    context.user_data['field_to_edit'] = field_to_edit
    
    field_map = {'name': 'название', 'author': 'автора', 'genre': 'жанр', 'description': 'описание'}
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_edit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = f"Пришлите новое **{field_map[field_to_edit]}** для книги."
    if query.message.caption:
        await query.edit_message_caption(caption=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return UPDATING_BOOK_FIELD

async def process_book_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет информацию о книге в БД и показывает обновленную карточку."""
    new_value = update.message.text
    book_id = context.user_data.get('book_to_edit')
    field = context.user_data.get('field_to_edit')
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            book_before_update = db_data.get_book_details(conn, book_id)
            book_name = book_before_update.get('name', f'ID: {book_id}')

            db_data.update_book_field(conn, book_id, field, new_value)
            content = _build_book_details_content(conn, book_id, current_page)

        admin_text = f"✏️ Админ отредактировал поле `{field}` для книги «{book_name}»."
        tasks.notify_admin.delay(text=admin_text, category='admin_action')

        await update.message.delete() # Удаляем сообщение с новым текстом
        await update.message.reply_text("✅ Информация о книге успешно обновлена!")

        if content.get('cover_id'):
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=content['cover_id'],
                caption=content['text'],
                reply_markup=content['reply_markup'],
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=content['text'],
                reply_markup=content['reply_markup'],
                parse_mode='Markdown'
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Произошла ошибка при обновлении: {e}")
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `process_book_update`\n**Ошибка:** `{e}`")
        
    finally:
        context.user_data.pop('book_to_edit', None)
        context.user_data.pop('field_to_edit', None)

    return ConversationHandler.END

async def cancel_edit_and_show_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет редактирование и возвращает карточку книги."""
    query = update.callback_query
    await query.answer()
    book_id = context.user_data.get('book_to_edit')
    if book_id:
        query.data = f"admin_view_book_{book_id}"
        await show_book_details(update, context)
    else: # Если что-то пошло не так, просто отменяем
        await cancel(update, context)

    return ConversationHandler.END

async def ask_for_book_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает подтверждение на удаление книги."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[3])

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_book_delete_{book_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_view_book_{book_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "**⚠️ Вы уверены, что хотите удалить эту книгу?**\n\nЭто действие необратимо и удалит всю связанную с ней историю."
    if query.message.caption:
        await query.edit_message_caption(caption=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def process_book_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает удаление книги и возвращает к списку."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[4])
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            book_to_delete = db_data.get_book_details(conn, book_id)
            book_name = book_to_delete.get('name', f'ID: {book_id}')
            db_data.delete_book(conn, book_id)

        admin_text = f"🗑️ Админ удалил книгу «{book_name}» из каталога."
        tasks.notify_admin.delay(text=admin_text, category='admin_action')
        
        # Сначала редактируем сообщение, затем показываем список
        if query.message.caption:
             await query.edit_message_caption(caption="✅ Книга успешно удалена из каталога.", reply_markup=None)
        else:
             await query.edit_message_text(text="✅ Книга успешно удалена из каталога.", reply_markup=None)

    except Exception as e:
        error_message = f"❌ Ошибка при удалении книги: {e}"
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `process_book_delete`\n**Ошибка:** `{e}`")
        if query.message.caption:
            await query.edit_message_caption(caption=error_message)
        else:
            await query.edit_message_text(text=error_message)

    # Имитируем нажатие на кнопку "Назад", чтобы показать обновленный список книг
    query.data = f"books_page_{current_page}"
    await show_books_list(update, context)

# --- Функции для диалога добавления книги ---
async def add_book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['new_book'] = {}
    await query.edit_message_text(
        "**➕ Добавление новой книги**\n\n"
        "**Шаг 1/5: Введите название книги.**\n\n"
        "Для отмены введите /cancel."
    , parse_mode='Markdown')
    return GET_NAME

async def get_book_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['name'] = update.message.text
    await update.message.reply_text("**Шаг 2/5: Введите автора книги.**", parse_mode='Markdown')
    return GET_AUTHOR

async def get_book_author(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['author'] = update.message.text
    await update.message.reply_text("**Шаг 3/5: Введите жанр книги.**", parse_mode='Markdown')
    return GET_GENRE

async def get_book_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['genre'] = update.message.text
    await update.message.reply_text("**Шаг 4/5: Введите краткое описание книги.**", parse_mode='Markdown')
    return GET_DESCRIPTION

async def get_book_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['description'] = update.message.text
    await update.message.reply_text(
        "**Шаг 5/5: Отправьте фото обложки.**\n\n"
        "Если хотите пропустить этот шаг, отправьте любой текст (например, 'пропустить')."
    , parse_mode='Markdown')
    return GET_COVER

async def get_book_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['cover_image_id'] = update.message.photo[-1].file_id
    await show_add_confirmation(update, context)
    return CONFIRM_ADD

async def skip_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_book']['cover_image_id'] = None
    await update.message.reply_text("👌 Обложка пропущена.")
    await show_add_confirmation(update, context)
    return CONFIRM_ADD

async def show_add_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    book_data = context.user_data['new_book']
    message_parts = [
        "**🔍 Проверьте данные перед сохранением:**\n",
        f"**Название:** {book_data['name']}",
        f"**Автор:** {book_data['author']}",
        f"**Жанр:** {book_data['genre']}",
        f"**Описание:** {book_data['description']}"
    ]
    message_text = "\n".join(message_parts)
    keyboard = [
        [InlineKeyboardButton("✅ Сохранить", callback_data="add_book_save_simple")],
        [InlineKeyboardButton("🚀 Сохранить и уведомить всех", callback_data="add_book_save_notify")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_book_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if book_data.get('cover_image_id'):
        # Удаляем текстовые сообщения, чтобы не засорять чат
        await update.message.delete()
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=book_data['cover_image_id'],
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def add_book_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    should_notify = "_notify" in query.data
    book_data = context.user_data.pop('new_book', None)

    try:
        with get_db_connection() as conn:
            new_book_id = db_data.add_new_book(conn, book_data)
        
        message_end = " Запускаю рассылку о новинке..." if should_notify else ""
        caption_text = f"✅ Новая книга успешно добавлена в каталог!{message_end}"

        if query.message.caption:
            await query.edit_message_caption(caption=caption_text, reply_markup=None, parse_mode='Markdown')
        else:
            await query.edit_message_text(text=caption_text, reply_markup=None, parse_mode='Markdown')

        if should_notify:
            tasks.broadcast_new_book.delay(book_id=new_book_id)

    except Exception as e:
        error_message = f"❌ Ошибка при сохранении книги: {e}"
        logger.error(error_message, exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `add_book_save`\n**Ошибка:** `{e}`")
        await query.edit_message_text(error_message)
    
    return ConversationHandler.END

async def add_book_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс добавления книги."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('new_book', None)
    
    caption_text = "👌 Добавление книги отменено."
    if query.message.caption:
        await query.edit_message_caption(caption=caption_text, reply_markup=None)
    else:
        await query.edit_message_text(text=caption_text, reply_markup=None)
        
    # Показываем основной список книг
    await show_books_list(update, context)
    return ConversationHandler.END

# --------------------------
# --- ГЛАВНЫЙ HANDLER ---
# --------------------------

def main() -> None:
    application = Application.builder().token(ADMIN_BOT_TOKEN).build()

    add_book_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_book_start, pattern="^admin_add_book_start$")],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_name)],
            GET_AUTHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_author)],
            GET_GENRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_genre)],
            GET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_book_description)],
            GET_COVER: [
                MessageHandler(filters.PHOTO, get_book_cover),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_cover)
            ],
            CONFIRM_ADD: [
                CallbackQueryHandler(add_book_save, pattern="^add_book_save_"), 
                CallbackQueryHandler(add_book_cancel, pattern="^add_book_cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_book_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_book_edit, pattern="^admin_edit_book_")],
        states={
            SELECTING_BOOK_FIELD: [
                CallbackQueryHandler(prompt_for_update, pattern="^edit_field_"),
                CallbackQueryHandler(cancel_edit_and_show_card, pattern="^cancel_edit$"),
            ],
            UPDATING_BOOK_FIELD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_book_update),
                CallbackQueryHandler(cancel_edit_and_show_card, pattern="^cancel_edit$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast, filters=admin_filter)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Основные команды
    application.add_handler(CommandHandler("start", start, filters=admin_filter))
    application.add_handler(CommandHandler("stats", show_stats_panel, filters=admin_filter))
    application.add_handler(CommandHandler("books", show_books_list, filters=admin_filter))
    
    # Диалоги
    application.add_handler(broadcast_handler)
    application.add_handler(add_book_handler)
    application.add_handler(edit_book_handler)

    # Обработчики CallbackQuery
    # Статистика и пользователи
    application.add_handler(CallbackQueryHandler(show_stats_panel, pattern="^back_to_stats_panel$"))
    application.add_handler(CallbackQueryHandler(show_users_list, pattern="^users_list_page_"))
    application.add_handler(CallbackQueryHandler(view_user_profile, pattern="^admin_view_user_"))
    application.add_handler(CallbackQueryHandler(show_user_activity, pattern="^admin_activity_"))
    application.add_handler(CallbackQueryHandler(ask_for_delete_confirmation, pattern="^admin_delete_user_"))
    application.add_handler(CallbackQueryHandler(process_delete_confirmation, pattern="^admin_confirm_delete_"))
    
    # Книги
    application.add_handler(CallbackQueryHandler(show_books_list, pattern="^books_page_"))
    application.add_handler(CallbackQueryHandler(show_book_details, pattern="^admin_view_book_"))
    application.add_handler(CallbackQueryHandler(ask_for_book_delete_confirmation, pattern="^admin_delete_book_"))
    application.add_handler(CallbackQueryHandler(process_book_delete, pattern="^admin_confirm_book_delete_"))

    logger.info("Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()