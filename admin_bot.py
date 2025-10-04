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
from tasks import create_and_send_notification

# --- Состояния для диалогов ---
BROADCAST_MESSAGE = range(1)

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
        "Добро пожаловать в панель администратора!\n"
        "Доступные команды:\n"
        "/broadcast - Отправить сообщение всем пользователям\n"
        "/stats - Показать статистику"
    )

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог массовой рассылки."""
    await update.message.reply_text("Введите сообщение для рассылки. Для отмены введите /cancel.")
    return BROADCAST_MESSAGE

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает и ставит в очередь задачи на рассылку."""
    message_text = update.message.text
    await update.message.reply_text("Начинаю рассылку...")
    try:
        with get_db_connection() as conn:
            user_db_ids = db_data.get_all_user_ids(conn)
        for user_id in user_db_ids:
            # Вызываем новую "умную" задачу
            create_and_send_notification.delay(user_id=user_id, text=message_text, category='broadcast')
        await update.message.reply_text(f"Рассылка запущена для {len(user_db_ids)} пользователей.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при запуске рассылки: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог рассылки."""
    await update.message.reply_text("Действие отменено.")
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
            await update.message.reply_text("В базе данных пока нет пользователей.")
            return
        message_text = f"👤 **Всего пользователей: {total_users}**\n\nСтраница {page + 1}:\nНажмите на пользователя для деталей."
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
        await update.message.reply_text(f"Ошибка при получении статистики: {e}")

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
        reg_date = user['registration_date'].strftime("%Y-%m-%d %H:%M")
        age = calculate_age(user['dob'])
        message_parts = [
            f"**Карточка: `{user['username']}`**",
            f"**ФИО:** {user['full_name']}",
            f"**Возраст:** {age}",
            f"**Статус:** {user['status']}",
            f"**Контакт:** {user['contact_info']}",
            f"**Регистрация:** {reg_date}\n",
            "**История взятых книг:**"
        ]
        if borrow_history:
            for item in borrow_history:
                return_date_str = item['return_date'].strftime('%d.%m.%Y') if item['return_date'] else "не возвращена"
                borrow_date_str = item['borrow_date'].strftime('%d.%m.%Y')
                message_parts.append(f" - `{item['book_name']}` (взята: {borrow_date_str}, возвращена: {return_date_str})")
        else:
            message_parts.append("Нет записей.")
        message_parts.append("\n**История оценок:**")
        if rating_history:
            for item in rating_history:
                stars = "⭐" * item['rating']
                message_parts.append(f" - `{item['book_name']}`: {stars}")
        else:
            message_parts.append("Нет оценок.")
        message_text = "\n".join(message_parts)
        keyboard = [
            [InlineKeyboardButton("📜 История действий", callback_data=f"admin_activity_{user_id}_0")],
            [InlineKeyboardButton("🗑️ Удалить пользователя", callback_data=f"admin_delete_user_{user_id}")],
            [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"stats_page_{current_page}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"Произошла ошибка: {e}")

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
        "Вы уверены, что хотите удалить этого пользователя?\n\n"
        "Это действие вернет все его книги и обезличит аккаунт. История действий сохранится.",
        reply_markup=reply_markup
    )

async def process_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает подтверждение и удаляет пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split('_')[3])
    current_page = context.user_data.get('current_stats_page', 0)
    try:
        with get_db_connection() as conn:
            result = db_data.delete_user_by_admin(conn, user_id)
        await query.edit_message_text(f"Пользователь успешно удален.")
    except Exception as e:
        await query.edit_message_text(f"Ошибка при удалении: {e}")
    query.data = f"stats_page_{current_page}"
    await stats(update, context)

async def show_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает постраничный лог активности пользователя."""
    query = update.callback_query
    await query.answer()

    # Извлекаем ID пользователя и номер страницы
    # e.g., "admin_activity_12_1" -> user_id=12, page=1
    parts = query.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    
    logs_per_page = 10

    try:
        logs, total_logs = db_data.get_user_activity(user_id, limit=logs_per_page, offset=page * logs_per_page)

        user = db_data.get_user_by_id(user_id) # Получаем имя для заголовка
        
        message_parts = [f"**📜 Журнал действий для `{user['username']}`**\n(Всего записей: {total_logs}, страница {page + 1})\n"]

        if logs:
            for log in logs:
                timestamp_str = log['timestamp'].strftime('%d.%m.%Y %H:%M')
                details = f"({log['details']})" if log['details'] else ""
                message_parts.append(f"`{timestamp_str}` - **{log['action']}** {details}")
        else:
            message_parts.append("Нет записей об активности.")

        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_activity_{user_id}_{page - 1}"))
        if (page + 1) * logs_per_page < total_logs:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"admin_activity_{user_id}_{page + 1}"))

        keyboard = []
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопка возврата к карточке пользователя
        keyboard.append([InlineKeyboardButton("👤 Назад к карточке", callback_data=f"admin_view_user_{user_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        await query.edit_message_text(f"Произошла ошибка при получении логов: {e}")

# --------------------------
# --- ГЛАВНЫЙ HANDLER ---
# --------------------------

def main() -> None:
    application = Application.builder().token(ADMIN_BOT_TOKEN).build()
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

    print("✅ Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()