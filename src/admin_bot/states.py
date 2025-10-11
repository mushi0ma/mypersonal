from enum import Enum, auto

class AdminState(Enum):
    """
    Перечисление для состояний ConversationHandler в админ-боте.
    """
    # --- Рассылка ---
    BROADCAST_MESSAGE = auto()

    # --- Редактирование книги ---
    SELECTING_BOOK_FIELD = auto()
    UPDATING_BOOK_FIELD = auto()

    # --- Добавление книги ---
    GET_NAME = auto()
    GET_AUTHOR = auto()
    GET_GENRE = auto()
    GET_DESCRIPTION = auto()
    GET_COVER = auto()
    CONFIRM_ADD = auto()
    BULK_ADD_WAITING_FILE = auto()