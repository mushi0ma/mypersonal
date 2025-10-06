# src/library_bot/handlers/start.py

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.library_bot.states import State
from src.library_bot import keyboards

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """
    Начальная точка диалога. Показывает кнопки входа/регистрации
    или перенаправляет в главное меню, если пользователь уже авторизован.
    """
    # Если пользователь уже залогинен, сразу отправляем его в меню
    if context.user_data.get('current_user'):
        from src.library_bot.handlers.user_menu import user_menu
        return await user_menu(update, context)

    # В противном случае, начинаем с чистого листа
    context.user_data.clear()
    reply_markup = keyboards.get_start_keyboard()

    start_message = "Добро пожаловать в библиотеку! 📚"

    if update.callback_query:
        # Если мы пришли сюда по кнопке "назад", редактируем сообщение
        await update.callback_query.edit_message_text(start_message, reply_markup=reply_markup)
    else:
        # Если это первый запуск команды /start, удаляем команду и отправляем новое сообщение
        if update.message:
            await update.message.delete()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=start_message,
            reply_markup=reply_markup
        )

    return State.START_ROUTES

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет любой диалог и возвращает пользователя в главное меню или к стартовому сообщению.
    """
    message_text = "❌ Действие отменено."

    # Определяем, куда возвращать пользователя
    if context.user_data.get('current_user'):
        from src.library_bot.handlers.user_menu import user_menu
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(f"{message_text} Возвращаемся в меню.")
        else:
            await update.message.reply_text(f"{message_text} Возвращаемся в меню.")
        return await user_menu(update, context)
    else:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(f"{message_text} Возвращаемся в начало.")
        else:
            await update.message.reply_text(f"{message_text} Возвращаемся в начало.")
        return await start(update, context)