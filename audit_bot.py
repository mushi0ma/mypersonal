# audit_bot.py
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
ADMIN_NOTIFICATION_BOT_TOKEN = os.getenv("ADMIN_NOTIFICATION_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start от админа."""
    user = update.effective_user
    if user.id == ADMIN_TELEGRAM_ID:
        await update.message.reply_text("✅ Бот-аудитор активирован. Сюда будут приходить системные оповещения.")
    else:
        await update.message.reply_text("Этот бот предназначен только для администратора системы.")

def main() -> None:
    application = Application.builder().token(ADMIN_NOTIFICATION_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    print("✅ Бот-аудитор запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()