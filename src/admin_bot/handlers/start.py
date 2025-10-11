from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и список доступных команд."""
    await update.message.reply_text(
        "👋 **Панель администратора**\n\n"
        "Доступные команды:\n"
        "📊 /stats - Статистика и управление пользователями\n"
        "📚 /books - Управление каталогом книг\n"
        "📝 /requests - Запросы пользователей на книги\n"
        "📢 /broadcast - Массовая рассылка\n"
        "❓ /help - Справка по командам",
        parse_mode='Markdown'
    )