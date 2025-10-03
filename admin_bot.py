# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from datetime import datetime
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
from tasks import send_telegram_message

# --- Состояния для диалогов ---
BROADCAST_MESSAGE = range(1)

# --- Ограничение доступа ---
admin_filter = filters.User(user_id=ADMIN_TELEGRAM_ID)

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
    await update.message.reply_text("Введите сообщение, которое хотите отправить всем пользователям. Для отмены введите /cancel.")
    return BROADCAST_MESSAGE

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает и рассылает сообщение."""
    message_text = update.message.text
    await update.message.reply_text("Начинаю рассылку...")

    try:
        user_ids = db_data.get_all_user_ids()
        for user_id in user_ids:
            send_telegram_message.delay(user_id, message_text)
        await update.message.reply_text(f"Рассылка запущена для {len(user_ids)} пользователей.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при рассылке: {e}")

    return ConversationHandler.END

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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику с постраничным списком пользователей."""
    query = update.callback_query
    page = 0
    users_per_page = 5 # Сколько пользователей показывать на одной странице

    if query:
        await query.answer()
        # Извлекаем номер страницы из callback_data (e.g., "stats_page_1")
        page = int(query.data.split('_')[2])
    
    # Считаем смещение для SQL-запроса
    offset = page * users_per_page
    
    try:
        users, total_users = db_data.get_all_users(limit=users_per_page, offset=offset)
        
        if not users:
            message_text = "В базе данных пока нет зарегистрированных пользователей."
            await update.message.reply_text(message_text)
            return

        # Формируем сообщение
        message_text = f"👤 **Всего пользователей: {total_users}**\n\nСтраница {page + 1}:\n"
        for user in users:
            reg_date = user['registration_date'].strftime("%Y-%m-%d %H:%M")
            age = calculate_age(user['dob'])
            message_text += f"• `{user['username']}` ({user['full_name']}, {age}) - рег: {reg_date}\n"

        # Создаем кнопки навигации
        keyboard = []
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"stats_page_{page - 1}"))
        
        # Проверяем, есть ли еще пользователи для следующей страницы
        if (page + 1) * users_per_page < total_users:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"stats_page_{page + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем или редактируем сообщение
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        error_text = f"Произошла ошибка при получении статистики: {e}"
        if query:
            await query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)

    await update.message.reply_text("Раздел статистики в разработке.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог."""
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


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
    
    # --- ДОБАВЬТЕ ЭТУ СТРОКУ ---
    application.add_handler(CallbackQueryHandler(stats, pattern="^stats_page_"))

    print("✅ Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()