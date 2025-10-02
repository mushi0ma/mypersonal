# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- Загрузка переменных окружения ---
load_dotenv()
ADMIN_BOT_TOKEN = os.getenv("8284942434:AAH1DG3KpV3Y0JKvg80PRGvIm74GoVtS0r8")
ADMIN_TELEGRAM_ID = int(os.getenv("1101597449")) # Загружаем ID админа

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
        # user_ids = db_data.get_all_user_ids() # Нужна эта функция в db_data.py
        # for user_id in user_ids:
        #     send_telegram_message.delay(user_id, message_text)
        await update.message.reply_text(f"Рассылка завершена. Сообщение отправлено N пользователям.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при рассылке: {e}")
        
    return ConversationHandler.END

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
    
    print("✅ Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()