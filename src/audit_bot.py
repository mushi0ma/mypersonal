# audit_bot.py
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.core import config

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start от админа."""
    user = update.effective_user
    if user.id == config.ADMIN_TELEGRAM_ID:
        await update.message.reply_text("✅ Бот-аудитор активирован. Сюда будут приходить системные оповещения.")
    else:
        await update.message.reply_text("Этот бот предназначен только для администратора системы.")

def main() -> None:
    """Запускает бота-аудитора."""
    application = Application.builder().token(config.ADMIN_NOTIFICATION_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Бот-аудитор запущен.") # <-- Заменили print() на logger.info()
    
    application.run_polling()

if __name__ == "__main__":
    main()