import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CommandHandler,
)

from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks
from src.admin_bot.states import AdminState

logger = logging.getLogger(__name__)

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Начинает диалог массовой рассылки."""
    await update.message.reply_text("📢 **Рассылка**\n\nВведите сообщение, которое получат все пользователи. Для отмены введите /cancel.")
    return AdminState.BROADCAST_MESSAGE

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает и ставит в очередь задачи на рассылку."""
    message_text = update.message.text
    await update.message.reply_text("⏳ Начинаю рассылку...")
    try:
        async with get_db_connection() as conn:
            user_db_ids = await db_data.get_all_user_ids(conn)

        for user_id in user_db_ids:
            tasks.notify_user.delay(user_id=user_id, text=message_text, category='broadcast')

        await update.message.reply_text(f"✅ Рассылка успешно запущена для {len(user_db_ids)} пользователей.")
        tasks.notify_admin.delay(text=f"📢 Админ запустил рассылку для {len(user_db_ids)} пользователей.", category='admin_action')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запуске рассылки: {e}")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог рассылки."""
    await update.message.reply_text("👌 Рассылка отменена.")
    return ConversationHandler.END

broadcast_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", start_broadcast)],
    states={
        AdminState.BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast)],
    },
    fallbacks=[CommandHandler("cancel", cancel_broadcast)],
)