
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.core import config
from telegram.request import HTTPXRequest

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start от админа."""
    user = update.effective_user
    if user.id == config.ADMIN_TELEGRAM_ID:
        await update.message.reply_text("✅ Бот-аудитор активирован. Сюда будут приходить системные оповещения.")
    else:
        await update.message.reply_text("Этот бот предназначен только для администратора системы.")

async def main() -> None:
    """Запускает бота-аудитора."""

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    application = (
        Application.builder()
        .token(config.ADMIN_NOTIFICATION_BOT_TOKEN)
        .request(request)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Бот-аудитор инициализирован и готов к запуску.")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())