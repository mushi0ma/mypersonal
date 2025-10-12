from telegram import Update
from telegram.ext import ContextTypes

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение с разъяснениями главных команд."""
    help_text = (
        "**📚 Помощь по командам бота:**\n\n"
        "/start - Перезапустить бота и вернуться в главное меню.\n"
        "/help - Показать это сообщение.\n"
        "/cancel - Отменить текущее действие и вернуться в меню."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
