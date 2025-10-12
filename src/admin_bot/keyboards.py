from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- Клавиатуры для управления пользователями ---

def get_stats_panel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для панели статистики с кнопкой истории оценок."""
    keyboard = [
        [InlineKeyboardButton("👥 Список пользователей", callback_data="users_list_page_0")],
        [InlineKeyboardButton("⭐ История оценок", callback_data="ratings_page_0")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_users_list_keyboard(users: list, total_users: int, page: int, users_per_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для постраничного списка пользователей."""
    keyboard = [[InlineKeyboardButton(f"👤 {user['username']} ({user['full_name']})", callback_data=f"admin_view_user_{user['id']}")] for user in users]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"users_list_page_{page - 1}"))
    if (page + 1) * users_per_page < total_users:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"users_list_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("📊 Назад к статистике", callback_data="back_to_stats_panel")])
    return InlineKeyboardMarkup(keyboard)

def get_user_profile_keyboard(user_id: int, current_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для карточки профиля пользователя."""
    keyboard = [
        [InlineKeyboardButton("📜 История действий", callback_data=f"admin_activity_{user_id}_0")],
        [InlineKeyboardButton("🗑️ Удалить пользователя", callback_data=f"admin_delete_user_{user_id}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"users_list_page_{current_page}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_delete_confirmation_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления пользователя."""
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_delete_{user_id}")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_view_user_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатуры для управления книгами ---

def get_books_list_keyboard(books: list, total_books: int, page: int, books_per_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для постраничного списка книг."""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить одну книгу", callback_data="admin_add_book_start")],
        [InlineKeyboardButton("📥 Массовый импорт (CSV)", callback_data="admin_bulk_add_books")]
    ]
    
    for book in books:
        status_icon = "🔴" if book.get('is_borrowed', False) else "🟢"
        button_text = f"{status_icon} {book['name']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"admin_view_book_{book['id']}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"books_page_{page - 1}"))
    if (page + 1) * books_per_page < total_books:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"books_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    return InlineKeyboardMarkup(keyboard)

def get_book_details_keyboard(book_id: int, is_borrowed: bool, current_page: int) -> InlineKeyboardMarkup:
    """Клавиатура для карточки книги."""
    keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data=f"admin_edit_book_{book_id}")]]
    if not is_borrowed:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_book_{book_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку книг", callback_data=f"books_page_{current_page}")])
    return InlineKeyboardMarkup(keyboard)

def get_book_edit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора поля для редактирования книги."""
    keyboard = [
        [InlineKeyboardButton("Название", callback_data="edit_field_name")],
        [InlineKeyboardButton("Автор", callback_data="edit_field_author")],
        [InlineKeyboardButton("Жанр", callback_data="edit_field_genre")],
        [InlineKeyboardButton("Описание", callback_data="edit_field_description")],
        [InlineKeyboardButton("⬅️ Отмена", callback_data="cancel_edit")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_book_delete_confirmation_keyboard(book_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления книги."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_confirm_book_delete_{book_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data=f"admin_view_book_{book_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_add_book_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения добавления новой книги."""
    keyboard = [
        [InlineKeyboardButton("✅ Сохранить", callback_data="add_book_save_simple")],
        [InlineKeyboardButton("🚀 Сохранить и уведомить всех", callback_data="add_book_save_notify")],
        [InlineKeyboardButton("❌ Отмена", callback_data="add_book_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)