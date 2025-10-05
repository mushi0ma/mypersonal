# -*- coding: utf-8 -*-
import os
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
SELECTING_BOOK_FIELD, UPDATING_BOOK_FIELD = range(2, 4) # Смещаем диапазон
# --- ДОБАВЬТЕ ЭТУ СТРОКУ ---
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
        "📢 /broadcast - Отправить сообщение всем пользователям\n"
        "📊 /stats - Показать статистику пользователей\n"
        "📚 /books - Управление каталогом книг"
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
            # Вызываем новую задачу для уведомления пользователей
            tasks.notify_user.delay(user_id=user_id, text=message_text, category='broadcast')
        await update.message.reply_text(f"✅ Рассылка успешно запущена для {len(user_db_ids)} пользователей.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запуске рассылки: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог рассылки."""
    await update.message.reply_text("👌 Действие отменено.")
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику с постраничным списком пользователей."""
    query = update.callback_query
    page = 0
    users_per_page = 5
    if query:
        await query.answer()
        page = int(query.data.split('_')[2])
    context.user_data['current_stats_page'] = page
    offset = page * users_per_page
    try:
        with get_db_connection() as conn:
            users, total_users = db_data.get_all_users(conn, limit=users_per_page, offset=offset)
        if not users and page == 0:
            await update.message.reply_text("👥 В базе данных пока нет пользователей.")
            return
        message_text = f"📊 **Статистика пользователей** (Всего: {total_users})\n\nСтраница {page + 1}:\nНажмите на пользователя для деталей."
        keyboard = []
        for user in users:
            button_text = f"👤 {user['username']} ({user['full_name']})"
            callback_data = f"admin_view_user_{user['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"stats_page_{page - 1}"))
        if (page + 1) * users_per_page < total_users:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"stats_page_{page + 1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        reply_markup = InlineKeyboardMarkup(keyboard)
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при получении статистики: {e}")

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
            [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"stats_page_{current_page}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка: {e}")

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
            result = db_data.delete_user_by_admin(conn, user_id)
        
        admin_text = f"🗑️ Админ удалил (анонимизировал) пользователя: @{username}"
        tasks.notify_admin.delay(text=admin_text, category='admin_action')

        await query.edit_message_text(f"✅ Пользователь успешно удален (анонимизирован).")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при удалении: {e}")
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `process_delete_confirmation`\n**Ошибка:** `{e}`")
    query.data = f"stats_page_{current_page}"
    await stats(update, context)

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

        # Кнопки навигации
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
        await query.edit_message_text(f"❌ Произошла ошибка при получении логов: {e}")

async def show_books_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный список всех книг."""
    query = update.callback_query
    page = 0
    books_per_page = 5

    if query:
        await query.answer()
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
    query_data = query.data.replace('_cancel', '')
    book_id = int(query_data.split('_')[3])
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            content = _build_book_details_content(conn, book_id, current_page)

        if content.get('cover_id'):
            if query.message.photo:
                 await query.edit_message_caption(caption=content['text'], reply_markup=content['reply_markup'], parse_mode='Markdown')
            else:
                await query.message.delete()
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
        await query.edit_message_text(f"❌ Произошла ошибка при получении деталей книги: {e}")

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
        [InlineKeyboardButton("⬅️ Отмена", callback_data=f"admin_view_book_{book_id}_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_caption(caption="✏️ Какое поле вы хотите отредактировать?", reply_markup=reply_markup)
    
    return SELECTING_BOOK_FIELD

async def prompt_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у администратора новое значение для выбранного поля."""
    query = update.callback_query
    await query.answer()
    
    field_to_edit = query.data.split('_')[2]
    context.user_data['field_to_edit'] = field_to_edit
    
    field_map = {
        'name': 'название',
        'author': 'автора',
        'genre': 'жанр',
        'description': 'описание'
    }
    
    book_id = context.user_data['book_to_edit']
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_book_{book_id}_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_caption(
        caption=f"Пришлите новое **{field_map[field_to_edit]}** для книги.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
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

    await query.edit_message_caption(
        caption="**⚠️ Вы уверены, что хотите удалить эту книгу?**\n\nЭто действие необратимо и удалит всю связанную с ней историю.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def process_book_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает удаление книги и возвращает к списку."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[4]) # `confirm` добавляет 1 часть, поэтому индекс 4
    current_page = context.user_data.get('current_books_page', 0)

    try:
        with get_db_connection() as conn:
            book_to_delete = db_data.get_book_details(conn, book_id)
            book_name = book_to_delete.get('name', f'ID: {book_id}')
            db_data.delete_book(conn, book_id)

        admin_text = f"🗑️ Админ удалил книгу «{book_name}» из каталога."
        tasks.notify_admin.delay(text=admin_text, category='admin_action')

        await query.edit_message_caption(caption="✅ Книга успешно удалена из каталога.")

    except Exception as e:
        await query.edit_message_caption(caption=f"❌ Ошибка при удалении книги: {e}")
        tasks.notify_admin.delay(text=f"❗️ **Ошибка в `admin_bot`**\n\n**Функция:** `process_book_delete`\n**Ошибка:** `{e}`")

    # Имитируем нажатие на кнопку "Назад", чтобы показать обновленный список книг
    query.data = f"books_page_{current_page}"
    await show_books_list(update, context)

# --- Функции для диалога добавления книги ---

async def add_book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог добавления новой книги."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "**➕ Добавление новой книги**\n\n"
        "**Шаг 1/5: Введите название книги.**\n\n"
        "Для отмены введите /cancel."
    , parse_mode='Markdown')
    return GET_NAME

async def get_book_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает название книги и запрашивает автора."""
    context.user_data['new_book'] = {'name': update.message.text}
    await update.message.reply_text(
        "**Шаг 2/5: Введите автора книги.**",
        parse_mode='Markdown'
    )
    return GET_AUTHOR

async def get_book_author(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает автора и запрашивает жанр."""
    context.user_data['new_book']['author'] = update.message.text
    await update.message.reply_text(
        "**Шаг 3/5: Введите жанр книги.**",
        parse_mode='Markdown'
    )
    return GET_GENRE

async def get_book_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает жанр и запрашивает описание."""
    context.user_data['new_book']['genre'] = update.message.text
    await update.message.reply_text(
        "**Шаг 4/5: Введите краткое описание книги.**",
        parse_mode='Markdown'
    )
    return GET_DESCRIPTION

async def get_book_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает описание и запрашивает обложку."""
    context.user_data['new_book']['description'] = update.message.text
    await update.message.reply_text(
        "**Шаг 5/5: Отправьте фото обложки.**\n\n"
        "Если хотите пропустить этот шаг, отправьте любой текст (например, 'пропустить')."
    , parse_mode='Markdown')
    return GET_COVER

async def get_book_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает фото обложки и переходит к подтверждению."""
    context.user_data['new_book']['cover_image_id'] = update.message.photo[-1].file_id
    await show_add_confirmation(update, context)
    return CONFIRM_ADD

async def skip_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пропускает шаг добавления обложки."""
    context.user_data['new_book']['cover_image_id'] = None
    await update.message.reply_text("👌 Обложка пропущена.")
    await show_add_confirmation(update, context)
    return CONFIRM_ADD

async def show_add_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает собранные данные для финального подтверждения."""
    book_data = context.user_data['new_book']
    
    message_parts = [
        "**🔍 Проверьте данные перед сохранением:**\n",
        f"**Название:** {book_data['name']}",
        f"**Автор:** {book_data['author']}",
        f"**Жанр:** {book_data['genre']}",
        f"**Описание:** {book_data['description']}"
    ]
    message_text = "\n".join(message_parts)

    # --- ИЗМЕНЕНИЯ ЗДЕСЬ ---
    keyboard = [
        [
            InlineKeyboardButton("✅ Сохранить", callback_data="add_book_save_simple"),
        ],
        [
            InlineKeyboardButton("🚀 Сохранить и уведомить всех", callback_data="add_book_save_notify"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="add_book_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ... остальная часть функции без изменений
    if book_data.get('cover_image_id'):
        await update.message.reply_photo(
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
    """Сохраняет новую книгу в БД и опционально запускает рассылку."""
    query = update.callback_query
    await query.answer()
    
    # Определяем, нужно ли отправлять уведомление
    should_notify = "_notify" in query.data
    
    book_data = context.user_data.pop('new_book', None)

    try:
        with get_db_connection() as conn:
            # add_new_book возвращает ID новой книги, это нам понадобится
            new_book_id = db_data.add_new_book(conn, book_data)
        
        if should_notify:
            await query.edit_message_caption(caption="✅ Книга сохранена. Запускаю рассылку о новинке...", reply_markup=None)
            # Вызываем новую задачу Celery
            tasks.broadcast_new_book.delay(book_id=new_book_id)
        else:
            await query.edit_message_caption(caption="✅ Новая книга успешно добавлена в каталог!", reply_markup=None)

    except Exception as e:
        await query.edit_message_caption(caption=f"❌ Ошибка при сохранении книги: {e}", reply_markup=None)
    
    return ConversationHandler.END

async def add_book_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс добавления книги."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('new_book', None)
    await query.edit_message_caption(caption="👌 Добавление книги отменено.", reply_markup=None)
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
            # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
                CallbackQueryHandler(add_book_save, pattern="^add_book_save_"), 
                CallbackQueryHandler(add_book_cancel, pattern="^add_book_cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_book_handler)

    edit_book_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_book_edit, pattern="^admin_edit_book_")],
        states={
            SELECTING_BOOK_FIELD: [
                CallbackQueryHandler(prompt_for_update, pattern="^edit_field_"),
            ],
            UPDATING_BOOK_FIELD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_book_update)
            ],
        },
        fallbacks=[
            # Обработчик для кнопки "Назад к карточке" и "Отмена"
            CallbackQueryHandler(show_book_details, pattern="^admin_view_book_.*_cancel$"),
            CommandHandler("cancel", cancel) # Общая команда отмены
        ],
        # Позволяет повторно входить в диалог по кнопке
        map_to_parent={
            ConversationHandler.END: -1 # Возвращаемся в "основное" состояние
        }
    )
    
    application.add_handler(edit_book_handler)

    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast, filters=admin_filter)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start, filters=admin_filter))
    application.add_handler(broadcast_handler)
    application.add_handler(CommandHandler("stats", stats, filters=admin_filter))
    application.add_handler(CallbackQueryHandler(stats, pattern="^stats_page_"))
    application.add_handler(CallbackQueryHandler(view_user_profile, pattern="^admin_view_user_"))
    application.add_handler(CallbackQueryHandler(show_user_activity, pattern="^admin_activity_"))
    application.add_handler(CallbackQueryHandler(ask_for_delete_confirmation, pattern="^admin_delete_user_"))
    application.add_handler(CallbackQueryHandler(process_delete_confirmation, pattern="^admin_confirm_delete_"))
    application.add_handler(CommandHandler("books", show_books_list, filters=admin_filter))
    application.add_handler(CallbackQueryHandler(show_books_list, pattern="^books_page_"))
    application.add_handler(CallbackQueryHandler(show_book_details, pattern="^admin_view_book_"))
    application.add_handler(CallbackQueryHandler(ask_for_book_delete_confirmation, pattern="^admin_delete_book_"))
    application.add_handler(CallbackQueryHandler(process_book_delete, pattern="^admin_confirm_book_delete_"))

    print("✅ Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()