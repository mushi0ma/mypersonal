# src/librarybot.py
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- Локальные импорты из новой структуры ---
from src.core import config # ✅ Импортируем конфиг
from src.library_bot.states import State
from src.library_bot.handlers import (
    start,
    auth,
    registration,
    user_menu,
    books,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler("librarybot.log", maxBytes=10485760, backupCount=5)
handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(handler)


async def main() -> None:
    """Запускает основного бота, собирая его из модулей."""
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # --- Основной ConversationHandler ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start.start)],
        states={
            # --- Стартовый маршрутизатор ---
            State.START_ROUTES: [
                CallbackQueryHandler(registration.start_registration, pattern="^register$"),
                CallbackQueryHandler(auth.start_login, pattern="^login$"),
                # Обработчики для кнопок из уведомлений, которые могут прийти в любом состоянии
                CallbackQueryHandler(books.process_book_extension, pattern=r"^extend_borrow_"),
                CallbackQueryHandler(books.select_rating, pattern=r"^rate_book_"),
                CallbackQueryHandler(books.process_borrow_selection, pattern=r"^borrow_book_"),
                CallbackQueryHandler(books.show_book_card_user, pattern="^view_book_"),
            ],

            # --- Регистрация ---
            State.REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_name)],
            State.REGISTER_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_dob)],
            State.REGISTER_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_contact)],
            State.REGISTER_VERIFY_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.verify_registration_code)],
            State.REGISTER_STATUS: [CallbackQueryHandler(registration.get_status, pattern=r"^(студент|учитель)$")],
            State.REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_username)],
            State.REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_password)],
            State.REGISTER_CONFIRM_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration.get_password_confirmation)],
            State.AWAITING_NOTIFICATION_BOT: [CallbackQueryHandler(registration.check_notification_subscription, pattern="^confirm_subscription$")],

            # --- Вход и восстановление пароля ---
            State.LOGIN_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, auth.get_login_contact),
                CallbackQueryHandler(auth.start_forgot_password, pattern="^forgot_password$"),
            ],
            State.LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth.check_login_password)],
            State.FORGOT_PASSWORD_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth.get_forgot_password_contact)],
            State.FORGOT_PASSWORD_VERIFY_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth.verify_forgot_password_code)],
            State.FORGOT_PASSWORD_SET_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth.set_new_password)],
            State.FORGOT_PASSWORD_CONFIRM_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth.confirm_new_password)],

            # --- Главное меню и его опции ---
            State.USER_MENU: [
                CallbackQueryHandler(user_menu.logout, pattern="^logout$"),
                CallbackQueryHandler(user_menu.view_profile, pattern="^user_profile$"),
                CallbackQueryHandler(user_menu.view_borrow_history, pattern="^user_history$"),
                CallbackQueryHandler(user_menu.show_notifications, pattern="^user_notifications$"),
                CallbackQueryHandler(books.start_return_book, pattern="^user_return$"),
                CallbackQueryHandler(books.start_rate_book, pattern="^user_rate$"),
                CallbackQueryHandler(books.show_top_books, pattern="^top_books$"),
                CallbackQueryHandler(books.start_search, pattern="^search_book$"),
                CallbackQueryHandler(books.show_genres, pattern="^find_by_genre$"),
                CallbackQueryHandler(books.show_authors_list, pattern="^show_authors$"),
                # Вложенный обработчик редактирования профиля
                user_menu.edit_profile_handler,
                # Возврат в меню (универсальная кнопка)
                CallbackQueryHandler(user_menu.user_menu, pattern="^user_menu$"),
            ],

            # --- Работа с книгами ---
            State.USER_RETURN_BOOK: [CallbackQueryHandler(books.process_return_book, pattern=r"^return_\d+$")],
            State.USER_RATE_BOOK_SELECT: [CallbackQueryHandler(books.select_rating, pattern=r"^rate_\d+$")],
            State.USER_RATE_BOOK_RATING: [CallbackQueryHandler(books.process_rating, pattern=r"^rating_\d+$")],
            State.USER_RESERVE_BOOK_CONFIRM: [CallbackQueryHandler(books.process_reservation_decision, pattern=r"^reserve_(yes|no)$")],
            State.SHOWING_SEARCH_RESULTS: [
                CallbackQueryHandler(books.show_book_card_user, pattern="^view_book_"),
                CallbackQueryHandler(books.process_borrow_selection, pattern=r"^borrow_book_"),
                CallbackQueryHandler(books.navigate_search_results, pattern="^search_page_"),
            ],
            State.GETTING_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, books.process_search_query)],
            State.SHOWING_GENRES: [
                CallbackQueryHandler(books.show_books_in_genre, pattern=r"^genre_"),
                CallbackQueryHandler(user_menu.user_menu, pattern="^user_menu$"),
            ],
            State.SHOWING_GENRE_BOOKS: [
                CallbackQueryHandler(books.show_books_in_genre, pattern=r"^genre_"),
                CallbackQueryHandler(books.show_book_card_user, pattern="^view_book_"),
                CallbackQueryHandler(books.show_genres, pattern="^find_by_genre$"),
                CallbackQueryHandler(user_menu.user_menu, pattern="^user_menu$"),
            ],
            State.SHOWING_AUTHORS_LIST: [
                CallbackQueryHandler(books.show_author_card, pattern=r"^view_author_"),
                CallbackQueryHandler(books.show_authors_list, pattern="^authors_page_"),
            ],
            State.VIEWING_AUTHOR_CARD: [
                CallbackQueryHandler(books.show_author_card, pattern=r"^view_author_"),
                CallbackQueryHandler(books.show_book_card_user, pattern="^view_book_"),
                CallbackQueryHandler(books.show_authors_list, pattern="^authors_page_"),
            ],

            # --- Удаление профиля ---
            State.USER_DELETE_CONFIRM: [
                CallbackQueryHandler(user_menu.process_delete_self_confirmation, pattern="^user_confirm_self_delete$"),
                CallbackQueryHandler(user_menu.view_profile, pattern="^user_profile$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start.start),
            CommandHandler("cancel", start.cancel),
            CallbackQueryHandler(start.cancel, pattern="^cancel$")
        ],
        per_message=False # Важно для согласованности состояний
    )

    application.add_handler(conv_handler)
    logger.info("Основной бот инициализирован и готов к запуску...")
    
    # Запускаем бота асинхронно
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())