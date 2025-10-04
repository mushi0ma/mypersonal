import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import contextmanager
import sys
import os

# Добавляем корневую директорию в путь, чтобы можно было импортировать модули
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Мокируем (симулируем) внешние зависимости, которые не должны работать во время тестов
sys.modules['tasks'] = MagicMock()
sys.modules['sendgrid'] = MagicMock()
sys.modules['sendgrid.helpers.mail'] = MagicMock()
sys.modules['twilio'] = MagicMock()

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ConversationHandler, ContextTypes
import librarybot
import db_data
from db_utils import get_db_connection

# Помечаем все тесты в этом файле как асинхронные для pytest
pytestmark = pytest.mark.asyncio

# --- Вспомогательная функция для создания мок-объектов ---
def _create_mock_update(text=None, callback_data=None, user_id=12345, chat_id=12345):
    """Создает мок-объект Update для симуляции действий пользователя."""
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock(spec=Chat, id=chat_id)
    update.effective_user = MagicMock(spec=User, id=user_id, username='test_tg_user')

    if text:
        update.message = AsyncMock(spec=Message)
        update.message.text = text
        update.message.from_user = update.effective_user
        update.message.chat_id = chat_id
        update.callback_query = None
    
    if callback_data:
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = callback_data
        update.callback_query.from_user = update.effective_user
        update.message = None

    return update

# --- Основной интеграционный тест ---

async def test_full_registration_flow(db_session, monkeypatch):
    """
    Интеграционный тест для полного цикла регистрации пользователя.
    Использует фикстуру `db_session` для работы с чистой тестовой БД.
    """
    # --- Подготовка ---
    # Создаем мок-контекст менеджера, который будет возвращать нашу тестовую сессию
    @contextmanager
    def mock_get_db_connection():
        yield db_session

    # Патчим функцию get_db_connection в модуле librarybot, чтобы она использовала нашу тестовую БД
    monkeypatch.setattr(librarybot, 'get_db_connection', mock_get_db_connection)

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    context.user_data = {}

    # Мокируем функцию отправки сообщений, так как мы не хотим реально их слать
    librarybot.send_verification_message = AsyncMock(return_value=True)

    # --- Шаг 1: /start ---
    update = _create_mock_update(text="/start")
    next_state = await librarybot.start(update, context)
    assert next_state == librarybot.START_ROUTES

    # --- Шаг 2: Нажатие "Зарегистрироваться" ---
    update = _create_mock_update(callback_data="register")
    next_state = await librarybot.start_registration(update, context)
    assert next_state == librarybot.REGISTER_NAME

    # --- Шаг 3: Ввод ФИО ---
    update = _create_mock_update(text="Тестов Тест Тестович")
    next_state = await librarybot.get_name(update, context)
    assert next_state == librarybot.REGISTER_DOB
    assert context.user_data['registration']['full_name'] == "Тестов Тест Тестович"

    # --- Шаг 4: Ввод Даты рождения ---
    update = _create_mock_update(text="01.01.1990")
    next_state = await librarybot.get_dob(update, context)
    assert next_state == librarybot.REGISTER_CONTACT

    # --- Шаг 5: Ввод контакта ---
    update = _create_mock_update(text="test@example.com")
    next_state = await librarybot.get_contact(update, context)
    assert next_state == librarybot.REGISTER_VERIFY_CODE
    librarybot.send_verification_message.assert_called_once()

    # --- Шаг 6: Ввод кода верификации ---
    code = context.user_data['verification_code']
    update = _create_mock_update(text=code)
    next_state = await librarybot.verify_registration_code(update, context)
    assert next_state == librarybot.REGISTER_STATUS

    # --- Шаг 7: Выбор статуса ---
    update = _create_mock_update(callback_data="студент")
    next_state = await librarybot.get_status(update, context)
    assert next_state == librarybot.REGISTER_USERNAME

    # --- Шаг 8: Ввод юзернейма ---
    update = _create_mock_update(text="test_user_123")
    next_state = await librarybot.get_username(update, context)
    assert next_state == librarybot.REGISTER_PASSWORD
    assert context.user_data['registration']['username'] == "test_user_123"

    # --- Шаг 9: Ввод первого пароля ---
    update = _create_mock_update(text="ValidPassword123")
    next_state = await librarybot.get_password(update, context)
    assert next_state == librarybot.REGISTER_CONFIRM_PASSWORD
    # Сообщение должно редактироваться, чтобы скрыть пароль
    update.message.edit_text.assert_called_once() 

    # --- Шаг 10: Ввод второго пароля (подтверждение) ---
    update = _create_mock_update(text="ValidPassword123")
    next_state = await librarybot.get_password_confirmation(update, context)
    
    # Финальное состояние - возврат в главное меню
    assert next_state == librarybot.START_ROUTES
    
    # --- Финальная проверка в РЕАЛЬНОЙ БАЗЕ ДАННЫХ ---
    cursor = db_session.cursor()
    cursor.execute("SELECT username, full_name, status FROM users WHERE username = 'test_user_123'")
    user_from_db = cursor.fetchone()
    cursor.close()

    assert user_from_db is not None
    assert user_from_db[0] == "test_user_123"
    assert user_from_db[1] == "Тестов Тест Тестович"
    assert user_from_db[2] == "студент"