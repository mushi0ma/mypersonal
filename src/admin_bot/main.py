import logging
import asyncio
import traceback
import html
import json
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# --- Локальные импорты из новой структуры ---
from src.core import config
from src.admin_bot.handlers import stats, books, broadcast, start, requests, help as help_handler
from telegram.request import HTTPXRequest

# --- Настройка логгера ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Ограничение доступа ---
admin_filter = filters.User(user_id=config.ADMIN_TELEGRAM_ID)

# --- Глобальный обработчик ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Логирует ошибки и отправляет сообщение администратору.
    """
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Формируем отчет об ошибке
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Отправляем трассировку администратору
    await context.bot.send_message(
        chat_id=config.ADMIN_TELEGRAM_ID, text=message, parse_mode='HTML'
    )

async def main() -> None:
    """Запускает админ-бота с всеми новыми функциями."""

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    
    application = (
        Application.builder()
        .token(config.ADMIN_BOT_TOKEN)
        .request(request)
        .build()
    )

    # --- Регистрация обработчика ошибок ---
    application.add_error_handler(error_handler)

    # --- Основные команды ---
    application.add_handler(CommandHandler("start", start.start, filters=admin_filter))
    application.add_handler(CommandHandler("stats", stats.show_stats_panel, filters=admin_filter))
    application.add_handler(CommandHandler("books", books.show_books_list, filters=admin_filter))
    application.add_handler(CommandHandler("requests", requests.show_book_requests, filters=admin_filter))
    application.add_handler(CommandHandler("help", help_handler.show_help, filters=admin_filter))

    # --- Диалоги (ConversationHandlers) ---
    application.add_handler(broadcast.broadcast_handler)
    application.add_handler(books.add_book_handler)
    application.add_handler(books.edit_book_handler)
    application.add_handler(books.bulk_add_books_handler)

    # --- Статистика и пользователи ---
    application.add_handler(CallbackQueryHandler(stats.show_stats_panel, pattern="^back_to_stats_panel$"))
    application.add_handler(CallbackQueryHandler(stats.show_users_list, pattern="^users_list_page_"))
    application.add_handler(CallbackQueryHandler(stats.view_user_profile, pattern="^admin_view_user_"))
    application.add_handler(CallbackQueryHandler(stats.show_user_activity, pattern="^admin_activity_"))
    application.add_handler(CallbackQueryHandler(stats.kick_user, pattern="^admin_kick_user_"))
    application.add_handler(CallbackQueryHandler(stats.ban_unban_user, pattern="^admin_ban_user_"))
    application.add_handler(CallbackQueryHandler(stats.ask_for_delete_confirmation, pattern="^admin_delete_user_"))
    application.add_handler(CallbackQueryHandler(stats.process_delete_confirmation, pattern="^admin_confirm_delete_"))
    application.add_handler(CallbackQueryHandler(stats.show_ratings_history, pattern="^ratings_page_"))

    # --- Книги ---
    application.add_handler(CallbackQueryHandler(books.show_books_list, pattern="^books_page_"))
    application.add_handler(CallbackQueryHandler(books.show_book_details, pattern="^admin_view_book_"))
    application.add_handler(CallbackQueryHandler(books.ask_for_book_delete_confirmation, pattern="^admin_delete_book_"))
    application.add_handler(CallbackQueryHandler(books.process_book_delete, pattern="^admin_confirm_book_delete_"))

    # --- Запросы на книги ---
    application.add_handler(CallbackQueryHandler(requests.show_book_requests, pattern="^view_requests$"))
    application.add_handler(CallbackQueryHandler(requests.view_book_request, pattern="^view_request_"))
    application.add_handler(CallbackQueryHandler(requests.approve_request_and_add_book, pattern="^approve_request_"))
    application.add_handler(CallbackQueryHandler(requests.reject_book_request, pattern="^reject_request_"))

    logger.info("Админ-бот инициализирован и готов к запуску.")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
