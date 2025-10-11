from enum import Enum, auto


class State(Enum):
    """
    Перечисление для всех состояний ConversationHandler.
    Использование Enum вместо range() повышает читаемость и безопасность кода.
    """
    # --- Начальные состояния ---
    START_ROUTES = auto()

    # --- Регистрация ---
    REGISTER_NAME = auto()
    REGISTER_DOB = auto()
    REGISTER_CONTACT = auto()
    REGISTER_VERIFY_CODE = auto()
    REGISTER_STATUS = auto()
    REGISTER_USERNAME = auto()
    REGISTER_PASSWORD = auto()
    REGISTER_CONFIRM_PASSWORD = auto()
    AWAITING_NOTIFICATION_BOT = auto()

    # --- Вход ---
    LOGIN_CONTACT = auto()
    LOGIN_PASSWORD = auto()

    # --- Восстановление пароля ---
    FORGOT_PASSWORD_CONTACT = auto()
    FORGOT_PASSWORD_VERIFY_CODE = auto()
    FORGOT_PASSWORD_SET_NEW = auto()
    FORGOT_PASSWORD_CONFIRM_NEW = auto()

    # --- Главное меню и его разделы ---
    USER_MENU = auto()
    USER_VIEW_HISTORY = auto()
    USER_NOTIFICATIONS = auto()
    VIEWING_TOP_BOOKS = auto()
    SHOWING_AUTHORS_LIST = auto()
    VIEWING_AUTHOR_CARD = auto()
    SEARCHING_AUTHORS = auto()

    # --- Работа с книгами ---
    USER_BORROW_BOOK_SELECT = auto()
    USER_RETURN_BOOK = auto()
    USER_RATE_BOOK_SELECT = auto()
    USER_RATE_BOOK_RATING = auto()
    USER_RESERVE_BOOK_CONFIRM = auto()
    BOOK_REQUEST_NAME = auto()
    BOOK_REQUEST_AUTHOR = auto()
    BOOK_REQUEST_GENRE = auto()
    BOOK_REQUEST_DESCRIPTION = auto()

    # --- Поиск ---
    SHOWING_GENRES = auto()
    SHOWING_GENRE_BOOKS = auto()
    GETTING_SEARCH_QUERY = auto()
    SHOWING_SEARCH_RESULTS = auto()

    # --- Редактирование профиля ---
    EDIT_PROFILE_MENU = auto()
    EDITING_FULL_NAME = auto()
    EDITING_CONTACT = auto()
    AWAIT_CONTACT_VERIFICATION_CODE = auto()
    EDITING_PASSWORD_CURRENT = auto()
    EDITING_PASSWORD_NEW = auto()
    EDITING_PASSWORD_CONFIRM = auto()

    # --- Удаление профиля ---
    USER_DELETE_CONFIRM = auto()