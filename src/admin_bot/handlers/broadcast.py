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
from src.admin_bot import keyboards

logger = logging.getLogger(__name__)


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Начинает диалог рассылки, спрашивая тип."""
    context.user_data['broadcast'] = {'selected_users': set()}
    reply_markup = keyboards.get_broadcast_type_keyboard()
    await update.message.reply_text("📢 **Рассылка**\n\nВыберите, кому отправить сообщение:", reply_markup=reply_markup)
    return AdminState.BROADCAST_TYPE


async def ask_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Спрашивает сообщение для рассылки."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Теперь введите сообщение для рассылки. Для отмены введите /cancel.")
    else:
        await update.message.reply_text("Теперь введите сообщение для рассылки. Для отмены введите /cancel.")
    return AdminState.BROADCAST_MESSAGE


async def show_user_selection_for_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Показывает постраничный список пользователей для выбора."""
    query = update.callback_query
    page = int(query.data.split('_')[-1]) if query and "broadcast_users_page" in query.data else 0
    await query.answer()

    users_per_page = 5
    context.user_data['broadcast']['current_page'] = page
    offset = page * users_per_page

    try:
        async with get_db_connection() as conn:
            users, total_users = await db_data.get_all_users(conn, limit=users_per_page, offset=offset)

        selected_users = context.user_data['broadcast']['selected_users']
        reply_markup = keyboards.get_user_selection_keyboard_for_broadcast(
            users, selected_users, total_users, page, users_per_page
        )
        await query.edit_message_text(f"👥 **Выберите получателей** (Страница {page + 1})", reply_markup=reply_markup)
        return AdminState.BROADCAST_SELECT_USERS
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей для рассылки: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")
        return AdminState.BROADCAST_TYPE


async def toggle_user_for_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Добавляет или удаляет пользователя из списка рассылки."""
    query = update.callback_query
    user_id = int(query.data.split('_')[-1])
    selected_users = context.user_data['broadcast']['selected_users']

    if user_id in selected_users:
        selected_users.remove(user_id)
    else:
        selected_users.add(user_id)

    await query.answer(f"Пользователь {'удален' if user_id not in selected_users else 'добавлен'}")

    # Обновляем клавиатуру, не меняя страницу
    current_page = context.user_data['broadcast']['current_page']
    query.data = f"broadcast_users_page_{current_page}"
    return await show_user_selection_for_broadcast(update, context)


async def confirm_broadcast_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Подтверждает выбор пользователей и запрашивает сообщение."""
    query = update.callback_query
    await query.answer()
    selected_count = len(context.user_data['broadcast']['selected_users'])
    if selected_count == 0:
        await query.answer("⚠️ Вы не выбрали ни одного пользователя!", show_alert=True)
        return AdminState.BROADCAST_SELECT_USERS

    await query.edit_message_text(f"Выбрано **{selected_count}** пользователей. Теперь введите сообщение для рассылки.")
    return AdminState.BROADCAST_MESSAGE


async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает и ставит в очередь задачи на рассылку."""
    message_text = update.message.text
    broadcast_data = context.user_data.get('broadcast', {})
    selected_users = broadcast_data.get('selected_users')

    await update.message.reply_text("⏳ Начинаю рассылку...")
    try:
        if selected_users is None:  # Рассылка всем
            async with get_db_connection() as conn:
                user_db_ids = await db_data.get_all_user_ids(conn)
        else:  # Рассылка выбранным
            user_db_ids = list(selected_users)

        for user_id in user_db_ids:
            tasks.notify_user.delay(user_id=user_id, text=message_text, category='broadcast')

        await update.message.reply_text(f"✅ Рассылка успешно запущена для {len(user_db_ids)} пользователей.")
        tasks.notify_admin.delay(text=f"📢 Админ запустил рассылку для {len(user_db_ids)} пользователей.", category='admin_action')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при запуске рассылки: {e}")

    context.user_data.pop('broadcast', None)
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог рассылки."""
    context.user_data.pop('broadcast', None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("👌 Рассылка отменена.")
    else:
        await update.message.reply_text("👌 Рассылка отменена.")
    return ConversationHandler.END


broadcast_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", start_broadcast)],
    states={
        AdminState.BROADCAST_TYPE: [
            CallbackQueryHandler(ask_broadcast_message, pattern="^broadcast_all$"),
            CallbackQueryHandler(show_user_selection_for_broadcast, pattern="^broadcast_select$")
        ],
        AdminState.BROADCAST_SELECT_USERS: [
            CallbackQueryHandler(toggle_user_for_broadcast, pattern="^broadcast_toggle_user_"),
            CallbackQueryHandler(show_user_selection_for_broadcast, pattern="^broadcast_users_page_"),
            CallbackQueryHandler(confirm_broadcast_selection, pattern="^broadcast_confirm_selection$"),
        ],
        AdminState.BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_broadcast),
        CallbackQueryHandler(cancel_broadcast, pattern="^broadcast_cancel$")
    ],
    per_user=True,
    per_chat=True
)
