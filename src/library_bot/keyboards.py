from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- Клавиатуры для начального меню ---

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для стартового сообщения."""
    keyboard = [
        [InlineKeyboardButton("Войти", callback_data="login")],
        [InlineKeyboardButton("Зарегистрироваться", callback_data="register")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатуры для регистрации ---

def get_status_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для выбора статуса (студент/преподаватель)."""
    keyboard = [
        [
            InlineKeyboardButton("Студент", callback_data="студент"),
            InlineKeyboardButton("Преподаватель", callback_data="учитель")
        ],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_notification_subscription_keyboard(bot_username: str, reg_code: str) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для подписки на бота-уведомителя."""
    keyboard = [
        [InlineKeyboardButton("🤖 Подписаться на уведомления", url=f"https://t.me/{bot_username}?start={reg_code}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="confirm_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатуры для главного меню ---

def get_user_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню с кнопкой запроса книги."""
    keyboard = [
        [
            InlineKeyboardButton("🔎 Поиск книг", callback_data="search_book"),
            InlineKeyboardButton("📚 По жанру", callback_data="find_by_genre")
        ],
        [
            InlineKeyboardButton("👥 Все авторы", callback_data="show_authors"),
            InlineKeyboardButton("🏆 Топ книг", callback_data="top_books")
        ],
        [
            InlineKeyboardButton("📥 Взять книгу", callback_data="search_book"),
            InlineKeyboardButton("📤 Вернуть книгу", callback_data="user_return")
        ],
        [
            InlineKeyboardButton("⭐ Оценить книгу", callback_data="user_rate"),
            InlineKeyboardButton("📝 Запросить книгу", callback_data="request_book")
        ],
        [
            InlineKeyboardButton("📜 История", callback_data="user_history"),
            InlineKeyboardButton("👤 Профиль", callback_data="user_profile")
        ],
        [
            InlineKeyboardButton("📬 Уведомления", callback_data="user_notifications")
        ],
        [
            InlineKeyboardButton("🚪 Выйти", callback_data="logout")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатуры для профиля ---

def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для меню профиля."""
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать профиль", callback_data="edit_profile")],
        [InlineKeyboardButton("📜 Перейти к истории", callback_data="user_history")],
        [InlineKeyboardButton("🗑️ Удалить аккаунт", callback_data="user_delete_account")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_edit_profile_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для редактирования профиля."""
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить ФИО", callback_data="edit_field_full_name")],
        [InlineKeyboardButton("📞 Изменить контакт", callback_data="edit_field_contact_info")],
        [InlineKeyboardButton("🔑 Сменить пароль", callback_data="edit_field_password")],
        [InlineKeyboardButton("⬅️ Назад в профиль", callback_data="user_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_delete_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для подтверждения удаления аккаунта."""
    keyboard = [
        [InlineKeyboardButton("✅ Да, я уверен", callback_data="user_confirm_self_delete")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data="user_profile")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Клавиатуры для работы с книгами ---

def get_return_book_keyboard(borrowed_books: list) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора книги к возврату."""
    keyboard = []
    for i, borrowed in enumerate(borrowed_books):
        borrow_id_cb = f"return_{i}"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {borrowed['book_name']}", callback_data=borrow_id_cb)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_rating_keyboard(from_return: bool = False) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора оценки (1-5 звезд)."""
    back_callback = "user_menu" if from_return else "user_rate"
    rating_buttons = [
        [InlineKeyboardButton("⭐"*i, callback_data=f"rating_{i}") for i in range(1, 6)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(rating_buttons)

def get_book_card_keyboard(book_id: int, is_available: bool) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для карточки книги с кнопкой нового поиска."""
    keyboard = []
    
    if is_available:
        keyboard.append([
            InlineKeyboardButton("✅ Взять эту книгу", callback_data=f"borrow_book_{book_id}")
        ])
    
    keyboard.extend([
        [InlineKeyboardButton("🔍 Новый поиск", callback_data="search_book")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="user_menu")]
    ])
    
    return InlineKeyboardMarkup(keyboard)