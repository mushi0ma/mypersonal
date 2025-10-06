# src/library_bot/handlers/books.py

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db_data
from db_utils import get_db_connection
import tasks
from src.library_bot.states import State
from src.library_bot.utils import rate_limit
from src.library_bot import keyboards

logger = logging.getLogger(__name__)

# --- Обработчики взятия, возврата и резервирования ---

@rate_limit(seconds=3, alert_admins=True)
async def process_borrow_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает выбор книги для взятия или резервирования."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[2])
    user = context.user_data['current_user']

    try:
        with get_db_connection() as conn:
            selected_book = db_data.get_book_by_id(conn, book_id)

            if selected_book['available_quantity'] > 0:
                borrowed_books = db_data.get_borrowed_books(conn, user['id'])
                from src.library_bot.utils import get_user_borrow_limit
                borrow_limit = get_user_borrow_limit(user['status'])

                if len(borrowed_books) >= borrow_limit:
                    await query.answer(f"⚠️ Вы достигли лимита ({borrow_limit}) на заимствование.", show_alert=True)
                    return State.USER_MENU

                due_date = db_data.borrow_book(conn, user['id'], selected_book['id'])
                db_data.log_activity(conn, user_id=user['id'], action="borrow_book", details=f"Book ID: {selected_book['id']}")

                due_date_str = due_date.strftime('%d.%m.%Y')
                notification_text = f"✅ Вы успешно взяли книгу «{selected_book['name']}».\n\nПожалуйста, верните ее до **{due_date_str}**."
                tasks.notify_user.delay(user_id=user['id'], text=notification_text, category='confirmation')

                await query.edit_message_text("👍 Отлично! Подтверждение отправлено вам в бот-уведомитель.")
                from src.library_bot.handlers.user_menu import user_menu
                return await user_menu(update, context)

            else:
                context.user_data['book_to_reserve'] = selected_book
                keyboard = [
                    [InlineKeyboardButton("✅ Да, уведомить", callback_data="reserve_yes")],
                    [InlineKeyboardButton("❌ Нет, спасибо", callback_data="reserve_no")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"⏳ Книга «{selected_book['name']}» временно отсутствует. Хотите зарезервировать?", reply_markup=reply_markup)
                return State.USER_RESERVE_BOOK_CONFIRM

    except Exception as e:
        logger.error(f"Критическая ошибка в process_borrow_selection: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка в `librarybot`**: `{e}`", category='error')
        await query.edit_message_text("❌ Непредвиденная ошибка. Мы уже работаем над этим.")
        from src.library_bot.handlers.user_menu import user_menu
        return await user_menu(update, context)

async def process_reservation_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает решение о резервации."""
    query = update.callback_query
    await query.answer()
    book_to_reserve = context.user_data.pop('book_to_reserve', None)
    if not book_to_reserve:
        await query.edit_message_text("❌ Ошибка сессии. Попробуйте снова.")
        from src.library_bot.handlers.user_menu import user_menu
        return await user_menu(update, context)

    if query.data == 'reserve_yes':
        user_id = context.user_data['current_user']['id']
        with get_db_connection() as conn:
            result = db_data.add_reservation(conn, user_id, book_to_reserve['id'])
            db_data.log_activity(conn, user_id=user_id, action="reserve_book", details=f"Book ID: {book_to_reserve['id']}")
        await query.edit_message_text(f"👍 {result}")
    else:
        await query.edit_message_text("👌 Действие отменено.")

    from src.library_bot.handlers.user_menu import user_menu
    return await user_menu(update, context)

async def start_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает процесс возврата книги."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        borrowed_books = db_data.get_borrowed_books(conn, user_id)

    if not borrowed_books:
        await query.answer("✅ У вас нет книг на руках.", show_alert=True)
        return State.USER_MENU

    context.user_data['borrowed_map'] = {f"return_{i}": {'borrow_id': b['borrow_id'], 'book_id': b['book_id'], 'book_name': b['book_name']} for i, b in enumerate(borrowed_books)}
    reply_markup = keyboards.get_return_book_keyboard(borrowed_books)
    await query.edit_message_text("📤 Выберите книгу для возврата:", reply_markup=reply_markup)
    return State.USER_RETURN_BOOK

@rate_limit(seconds=3, alert_admins=True)
async def process_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает возврат книги и инициирует уведомления."""
    query = update.callback_query
    await query.answer()
    borrowed_info = context.user_data.get('borrowed_map', {}).get(query.data)
    if not borrowed_info:
        await query.edit_message_text("❌ Ошибка выбора. Попробуйте снова.")
        from src.library_bot.handlers.user_menu import user_menu
        return await user_menu(update, context)

    user_id = context.user_data['current_user']['id']
    try:
        with get_db_connection() as conn:
            db_data.return_book(conn, borrowed_info['borrow_id'], borrowed_info['book_id'])
            db_data.log_activity(conn, user_id=user_id, action="return_book", details=f"Book ID: {borrowed_info['book_id']}")

            # Уведомляем пользователя и предлагаем оценить
            tasks.notify_user.delay(
                user_id=user_id,
                text=f"✅ Книга «{borrowed_info['book_name']}» успешно возвращена. Не хотите ли поставить ей оценку?",
                category='confirmation',
                button_text="⭐ Поставить оценку",
                button_callback=f"rate_book_{borrowed_info['book_id']}"
            )

            # Проверяем резервации
            reservations = db_data.get_reservations_for_book(conn, borrowed_info['book_id'])
            if reservations:
                next_user_id = reservations[0]
                tasks.notify_user.delay(
                    user_id=next_user_id,
                    text=f"🎉 Книга «{borrowed_info['book_name']}», которую вы ждали, снова в наличии!",
                    category='reservation',
                    button_text="📥 Взять книгу",
                    button_callback=f"borrow_book_{borrowed_info['book_id']}"
                )
                db_data.update_reservation_status(conn, next_user_id, borrowed_info['book_id'], notified=True)

        await query.edit_message_text(f"✅ Книга «{borrowed_info['book_name']}» возвращена. Подтверждение отправлено в бот-уведомитель.")
    except Exception as e:
        logger.error(f"Ошибка при возврате книги: {e}", exc_info=True)
        tasks.notify_admin.delay(text=f"❗️ **Критическая ошибка при возврате книги**: `{e}`")
        await query.edit_message_text("❌ Непредвиденная ошибка. Администратор уже уведомлен.")

    context.user_data.pop('borrowed_map', None)
    from src.library_bot.handlers.user_menu import user_menu
    return await user_menu(update, context)

# --- Обработчики оценки книг ---

async def start_rate_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает процесс оценки книги."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['current_user']['id']
    with get_db_connection() as conn:
        history = db_data.get_user_borrow_history(conn, user_id)

    unique_books = {item['book_id']: item for item in history if item.get('book_id')}.values()
    if not unique_books:
        await query.answer("📚 Вы можете оценить только те книги, которые брали.", show_alert=True)
        return State.USER_MENU

    message_text = "⭐ Выберите книгу для оценки:"
    keyboard = []
    context.user_data['rating_map'] = {}
    for i, book in enumerate(unique_books):
        rate_id = f"rate_{i}"
        keyboard.append([InlineKeyboardButton(f"{book['book_name']}", callback_data=rate_id)])
        context.user_data['rating_map'][rate_id] = {'book_id': book['book_id'], 'book_name': book['book_name']}

    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return State.USER_RATE_BOOK_SELECT

async def select_rating(update: Update, context: ContextTypes.DEFAULT_TYPE, from_notification: bool = False) -> State:
    """Показывает клавиатуру для выбора оценки (звездочек)."""
    query = update.callback_query
    await query.answer()

    if from_notification:
        book_id = int(query.data.split('_')[2])
        with get_db_connection() as conn:
            book_info_raw = db_data.get_book_by_id(conn, book_id)
        context.user_data['book_to_rate'] = {'book_id': book_id, 'book_name': book_info_raw['name']}
    else:
        book_info = context.user_data.get('rating_map', {}).get(query.data)
        if not book_info:
            await query.edit_message_text("❌ Ошибка выбора.")
            from src.library_bot.handlers.user_menu import user_menu
            return await user_menu(update, context)
        context.user_data['book_to_rate'] = book_info

    book_name = context.user_data['book_to_rate']['book_name']
    message_text = f"⭐ Ваша оценка для книги «{book_name}»:"
    reply_markup = keyboards.get_rating_keyboard(from_return=from_notification)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return State.USER_RATE_BOOK_RATING

async def process_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Сохраняет оценку в БД."""
    query = update.callback_query
    await query.answer()
    rating = int(query.data.split('_')[1])
    user_id = context.user_data['current_user']['id']
    book_info = context.user_data.pop('book_to_rate')

    with get_db_connection() as conn:
        db_data.add_rating(conn, user_id, book_info['book_id'], rating)
        db_data.log_activity(conn, user_id=user_id, action="rate_book", details=f"Book ID: {book_info['book_id']}, Rating: {rating}")

    tasks.notify_user.delay(user_id=user_id, text=f"👍 Спасибо! Ваша оценка «{rating}» для книги «{book_info['book_name']}» сохранена.", category='confirmation')
    await query.edit_message_text("✅ Спасибо за вашу оценку!")

    context.user_data.pop('rating_map', None)
    from src.library_bot.handlers.user_menu import user_menu
    return await user_menu(update, context)

async def process_book_extension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает продление срока возврата книги."""
    query = update.callback_query
    await query.answer()
    borrow_id = int(query.data.split('_')[2])

    with get_db_connection() as conn:
        result = db_data.extend_due_date(conn, borrow_id)

    if isinstance(result, datetime):
        await query.edit_message_text(f"✅ Срок возврата продлен до **{result.strftime('%d.%m.%Y')}**.", parse_mode='Markdown')
    else:
        await query.edit_message_text(f"⚠️ {result}")

    from src.library_bot.handlers.user_menu import user_menu
    return await user_menu(update, context)

# --- Обработчики поиска и просмотра ---

@rate_limit(seconds=1)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Начинает диалог поиска книги."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text="🔎 Введите название книги или фамилию автора для поиска:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]])
    )
    return State.GETTING_SEARCH_QUERY

@rate_limit(seconds=2)
async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Ищет книги и показывает первую страницу результатов."""
    search_term = update.message.text
    context.user_data['last_search_term'] = search_term

    # Имитируем callback_query для навигации
    from telegram import CallbackQuery
    update.callback_query = CallbackQuery(id="dummy", from_user=update.effective_user, chat_instance="dummy", data="search_page_0")
    await update.message.delete()
    return await navigate_search_results(update, context)

async def navigate_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Обрабатывает навигацию по страницам результатов поиска."""
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[2])
    search_term = context.user_data.get('last_search_term')

    if not search_term:
        await query.edit_message_text("❌ Ошибка: поисковый запрос потерян. Попробуйте снова.")
        from src.library_bot.handlers.user_menu import user_menu
        return await user_menu(update, context)

    with get_db_connection() as conn:
        books, total = db_data.search_available_books(conn, search_term, limit=5, offset=page * 5)

    if total == 0:
         await query.edit_message_text(f"😔 По запросу «{search_term}» ничего не найдено.")
         return State.USER_MENU

    message_text = f"🔎 Результаты по запросу «{search_term}» (Стр. {page + 1}):"
    keyboard = [[InlineKeyboardButton(f"📖 {b['name']} ({b['author']})", callback_data=f"view_book_{b['id']}")] for b in books]

    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"search_page_{page - 1}"))
    if (page + 1) * 5 < total: nav.append(InlineKeyboardButton("➡️", callback_data=f"search_page_{page + 1}"))
    if nav: keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")])
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SHOWING_SEARCH_RESULTS

async def show_book_card_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает детальную карточку книги."""
    query = update.callback_query
    await query.answer()
    book_id = int(query.data.split('_')[2])

    with get_db_connection() as conn:
        book = db_data.get_book_card_details(conn, book_id)

    message_parts = [
        f"**📖 {book['name']}**", f"**Автор:** {book['author']}", f"**Жанр:** {book['genre']}",
        f"\n_{book['description']}_\n",
        f"✅ **Статус:** {'Свободна' if book['is_available'] else 'На руках'}"
    ]

    reply_markup = keyboards.get_book_card_keyboard(book['id'], book['is_available'])

    await query.message.delete()
    if book.get('cover_image_id'):
        await context.bot.send_photo(
            chat_id=query.message.chat_id, photo=book['cover_image_id'],
            caption="\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="\n".join(message_parts),
            reply_markup=reply_markup, parse_mode='Markdown'
        )
    return State.SHOWING_SEARCH_RESULTS

async def show_top_books(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает топ книг по рейтингу."""
    query = update.callback_query
    await query.answer()
    with get_db_connection() as conn:
        top_books = db_data.get_top_rated_books(conn, limit=5)

    message_parts = ["**🏆 Топ-5 книг по оценкам читателей:**\n"]
    if top_books:
        for i, book in enumerate(top_books):
            stars = "⭐" * round(float(book['avg_rating']))
            message_parts.append(
                f"{i+1}. **{book['name']}** - {book['author']}\n"
                f"   Рейтинг: {stars} ({float(book['avg_rating']):.1f}/5.0 на основе {book['votes']} оценок)\n"
            )
    else:
        message_parts.append("_Пока недостаточно данных для рейтинга._")

    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
    await query.edit_message_text("\n".join(message_parts), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return State.VIEWING_TOP_BOOKS

@rate_limit(seconds=1)
async def show_genres(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает пользователю список жанров."""
    query = update.callback_query
    await query.answer()
    with get_db_connection() as conn:
        genres = db_data.get_unique_genres(conn)

    if not genres:
        await query.edit_message_text("😔 В каталоге пока нет книг с указанием жанра.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]))
        return State.USER_MENU

    keyboard = [[InlineKeyboardButton(f"🎭 {genre}", callback_data=f"genre_{genre}")] for genre in genres]
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    await query.edit_message_text("📚 Выберите интересующий вас жанр:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SHOWING_GENRES

async def show_books_in_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает постраничный список доступных книг в выбранном жанре."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    genre = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    books_per_page = 5
    offset = page * books_per_page

    with get_db_connection() as conn:
        books, total_books = db_data.get_available_books_by_genre(conn, genre, limit=books_per_page, offset=offset)

    # ✅ Инициализируем keyboard сразу
    keyboard = []

    if total_books == 0:
        message_text = f"😔 В жанре «{genre}» свободных книг не найдено."
    else:
        message_parts = [f"**📚 Книги в жанре «{genre}»** (Стр. {page + 1}):\n"]
        for book in books:
            message_parts.append(f"• *{book['name']}* ({book['author']})")
        message_text = "\n".join(message_parts)

        # Добавляем кнопки для книг
        for i, book in enumerate(books, start=1):
            status_icon = "✅" # В этой функции мы ищем только доступные книги
            button_text = f"{status_icon} {book['name']} ({book['author']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_book_{book['id']}")])

    # --- Кнопки навигации ---
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"genre_{genre}_{page - 1}"))
    if (page + 1) * books_per_page < total_books:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"genre_{genre}_{page + 1}"))

    if nav_buttons:  # ✅ Добавляем только если есть кнопки навигации
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⬅️ К выбору жанра", callback_data="find_by_genre")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return State.SHOWING_GENRE_BOOKS

@rate_limit(seconds=2)
async def show_authors_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает постраничный список всех авторов."""
    query = update.callback_query
    page = int(query.data.split('_')[2]) if query and "authors_page_" in query.data else 0
    if query: await query.answer()

    context.user_data['current_authors_page'] = page

    with get_db_connection() as conn:
        authors, total = db_data.get_all_authors_paginated(conn, limit=10, offset=page * 10)

    if not authors:
        await query.edit_message_text("📚 В библиотеке пока нет авторов.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]))
        return State.USER_MENU

    message_text = f"👥 **Авторы в библиотеке** (Всего: {total})\nСтраница {page + 1}:"
    keyboard = [[InlineKeyboardButton(f"✍️ {a['name']} ({a['books_count']} книг)", callback_data=f"view_author_{a['id']}")] for a in authors]

    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"authors_page_{page - 1}"))
    if (page + 1) * 10 < total: nav.append(InlineKeyboardButton("➡️", callback_data=f"authors_page_{page + 1}"))
    if nav: keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")])

    if query:
        await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return State.SHOWING_AUTHORS_LIST

async def show_author_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    """Показывает детальную карточку автора с его книгами."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    author_id = int(parts[2])
    books_page = int(parts[3]) if len(parts) > 3 else 0

    with get_db_connection() as conn:
        author = db_data.get_author_details(conn, author_id)
        books, total_books = db_data.get_books_by_author(conn, author_id, limit=5, offset=books_page * 5)

    message_parts = [
        f"👤 **{author['name']}**",
        f"📚 Всего книг: {total_books} | ✅ Доступно: {author['available_books_count']}\n"
    ]
    if books:
        message_parts.append(f"**📖 Книги автора (стр. {books_page + 1}/{(total_books + 4) // 5}):**")
        for i, book in enumerate(books, 1):
            status = "✅" if book['is_available'] else "❌"
            message_parts.append(f"{i}. {status} *{book['name']}*")

    keyboard = [[InlineKeyboardButton(f"📖 {i+1}", callback_data=f"view_book_{b['id']}")] for i, b in enumerate(books)]

    nav = []
    if books_page > 0: nav.append(InlineKeyboardButton("⬅️ Книги", callback_data=f"view_author_{author_id}_{books_page - 1}"))
    if (books_page + 1) * 5 < total_books: nav.append(InlineKeyboardButton("Книги ➡️", callback_data=f"view_author_{author_id}_{books_page + 1}"))
    if nav: keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("⬅️ К списку авторов", callback_data=f"authors_page_{context.user_data.get('current_authors_page', 0)}")])

    await query.edit_message_text("\n".join(message_parts), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return State.VIEWING_AUTHOR_CARD