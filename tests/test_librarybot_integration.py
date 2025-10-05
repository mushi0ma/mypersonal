# test_librarybot_integration.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from contextlib import contextmanager
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Мокируем внешние зависимости
sys.modules['tasks'] = MagicMock()
sys.modules['sendgrid'] = MagicMock()
sys.modules['sendgrid.helpers.mail'] = MagicMock()
sys.modules['twilio'] = MagicMock()

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes
import librarybot
import db_data

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
    Интеграционный тест для полного цикла регистрации, включая подписку на уведомителя.
    """
    # --- Подготовка ---
    @contextmanager
    def mock_get_db_connection():
        yield db_session
    monkeypatch.setattr(librarybot, 'get_db_connection', mock_get_db_connection)

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    context.user_data = {}

    librarybot.send_verification_message = AsyncMock(return_value=True)

    # --- Шаги с 1 по 9 (остаются без изменений) ---
    await librarybot.start(_create_mock_update(text="/start"), context)
    await librarybot.start_registration(_create_mock_update(callback_data="register"), context)
    await librarybot.get_name(_create_mock_update(text="Тестов Тест Тестович"), context)
    await librarybot.get_dob(_create_mock_update(text="01.01.1990"), context)
    await librarybot.get_contact(_create_mock_update(text="test@example.com"), context)
    code = context.user_data['verification_code']
    await librarybot.verify_registration_code(_create_mock_update(text=code), context)
    await librarybot.get_status(_create_mock_update(callback_data="студент"), context)
    await librarybot.get_username(_create_mock_update(text="test_user_123"), context)
    await librarybot.get_password(_create_mock_update(text="ValidPassword123"), context)
    
    # --- Шаг 10: Ввод второго пароля (подтверждение) ---
    update = _create_mock_update(text="ValidPassword123")
    next_state = await librarybot.get_password_confirmation(update, context)
    # --- ИЗМЕНЕНИЕ: Теперь бот ждет подписки на уведомителя ---
    assert next_state == librarybot.AWAITING_NOTIFICATION_BOT

    # --- Шаг 11: Симулируем, что бот-уведомитель сделал свою работу ---
    # В реальном тесте мы вручную обновляем запись в БД, как это сделал бы notification_bot
    user_id_for_activation = context.user_data['user_id_for_activation']
    cursor = db_session.cursor()
    cursor.execute(
        "UPDATE users SET telegram_id = %s, telegram_username = %s WHERE id = %s",
        (12345, 'test_tg_user', user_id_for_activation)
    )
    db_session.commit()
    cursor.close()

    # --- Шаг 12: Нажатие "Я подписался" ---
    update = _create_mock_update(callback_data="confirm_subscription")
    next_state = await librarybot.check_notification_subscription(update, context)
    # --- ИЗМЕНЕНИЕ: Теперь регистрация завершена, и мы возвращаемся на стартовый экран ---
    assert next_state == librarybot.START_ROUTES
    
    # --- Финальная проверка в РЕАЛЬНОЙ БАЗЕ ДАННЫХ ---
    cursor = db_session.cursor()
    cursor.execute("SELECT username, full_name, status, telegram_id FROM users WHERE username = 'test_user_123'")
    user_from_db = cursor.fetchone()
    cursor.close()

    assert user_from_db is not None
    assert user_from_db[0] == "test_user_123"
    assert user_from_db[1] == "Тестов Тест Тестович"
    assert user_from_db[2] == "студент"
    assert user_from_db[3] == 12345 # Проверяем, что telegram_id сохранился