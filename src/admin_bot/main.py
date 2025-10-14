import logging
import asyncio
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    MessageHandler
)

# --- Локальные импорты из новой структуры ---
from src.core import config
from src.admin_bot.handlers import stats, books, broadcast, start
from src.admin_bot.states import AdminState
from telegram.request import HTTPXRequest

# --- Настройка логгера ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Ограничение доступа ---
admin_filter = filters.User(user_id=config.ADMIN_TELEGRAM_ID)

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

    # Импорты
    from src.admin_bot.handlers import stats, books, broadcast, start, requests, help as help_handler

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