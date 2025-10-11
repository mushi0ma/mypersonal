import logging
import asyncio
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

# --- Локальные импорты из новой структуры ---
from src.core import config
from src.admin_bot.handlers import stats, books, broadcast, start

# --- Настройка логгера ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Ограничение доступа ---
admin_filter = filters.User(user_id=config.ADMIN_TELEGRAM_ID)

async def main() -> None:
    """Запускает админ-бота, собирая его из модулей."""
    application = (
        Application.builder()
        .token(config.ADMIN_BOT_TOKEN)
        .connect_timeout(10)
        .read_timeout(20)
        .build()
    )

    # --- Основные команды ---
    application.add_handler(CommandHandler("start", start.start, filters=admin_filter))
    application.add_handler(CommandHandler("stats", stats.show_stats_panel, filters=admin_filter))
    application.add_handler(CommandHandler("books", books.show_books_list, filters=admin_filter))

    # --- Диалоги (ConversationHandlers) ---
    application.add_handler(broadcast.broadcast_handler)
    application.add_handler(books.add_book_handler)
    application.add_handler(books.edit_book_handler)

    # --- Обработчики CallbackQuery для навигации ---
    # Статистика и пользователи
    application.add_handler(CallbackQueryHandler(stats.show_stats_panel, pattern="^back_to_stats_panel$"))
    application.add_handler(CallbackQueryHandler(stats.show_users_list, pattern="^users_list_page_"))
    application.add_handler(CallbackQueryHandler(stats.view_user_profile, pattern="^admin_view_user_"))
    application.add_handler(CallbackQueryHandler(stats.show_user_activity, pattern="^admin_activity_"))
    application.add_handler(CallbackQueryHandler(stats.ask_for_delete_confirmation, pattern="^admin_delete_user_"))
    application.add_handler(CallbackQueryHandler(stats.process_delete_confirmation, pattern="^admin_confirm_delete_"))

    # Книги
    application.add_handler(CallbackQueryHandler(books.show_books_list, pattern="^books_page_"))
    application.add_handler(CallbackQueryHandler(books.show_book_details, pattern="^admin_view_book_"))
    application.add_handler(CallbackQueryHandler(books.ask_for_book_delete_confirmation, pattern="^admin_delete_book_"))
    application.add_handler(CallbackQueryHandler(books.process_book_delete, pattern="^admin_confirm_book_delete_"))

    logger.info("Админ-бот инициализирован и готов к запуску.")
    
    # Запускаем бота асинхронно
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())