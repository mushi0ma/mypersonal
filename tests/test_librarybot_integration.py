import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import sys
import os

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock pywhatkit before it's imported by librarybot
sys.modules['pywhatkit'] = MagicMock()

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes

import librarybot
from db_data import get_user_by_login

# --- Helper functions to create mock Telegram objects ---

def _create_mock_user(user_id=123, username='test_telegram_user'):
    """Creates a mock Telegram User."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = username
    return user

def _create_mock_chat(chat_id=123):
    """Creates a mock Telegram Chat."""
    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    return chat

def _create_mock_message(text, user, chat):
    """Creates a mock Telegram Message."""
    message = MagicMock(spec=Message)
    message.text = text
    message.from_user = user
    message.chat = chat
    # Mock the edit_text method that is sometimes called on messages
    message.edit_text = AsyncMock()
    message.reply_text = AsyncMock()
    return message

def _create_mock_callback_query(data, user, message):
    """Creates a mock Telegram CallbackQuery."""
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.data = data
    callback_query.from_user = user
    callback_query.message = message
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    return callback_query

def _create_mock_update(text=None, callback_data=None, user_id=123, chat_id=123):
    """
    Creates a mock Update object, which can simulate either a text message
    or a callback query from an inline keyboard.
    """
    update = MagicMock(spec=Update)
    user = _create_mock_user(user_id)
    chat = _create_mock_chat(chat_id)
    message = _create_mock_message(text or "", user, chat)

    update.effective_user = user
    update.effective_chat = chat

    if text is not None:
        update.message = message
        update.callback_query = None
    elif callback_data is not None:
        update.message = None
        update.callback_query = _create_mock_callback_query(callback_data, user, message)

    return update

def _create_mock_context():
    """Creates a mock bot context, including user_data storage."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    context.bot = AsyncMock()
    # Add a dummy application object
    context.application = MagicMock()
    return context

# --- The Main Integration Test ---

@pytest.mark.asyncio
@patch('librarybot.send_verification_message', new_callable=AsyncMock)
async def test_full_registration_flow(mock_send_verification, test_db):
    """
    An integration test that simulates the entire user registration flow,
    from /start to final database insertion.
    """
    # --- Test Data ---
    USER_ID = 98765
    CHAT_ID = 98765
    FULL_NAME = "Интеграционный Тест"
    DOB = "15.05.1995"
    CONTACT_INFO = "integration@test.com"
    USERNAME = "integration_tester"
    PASSWORD = "ValidPassword123"

    # --- Mocks & Context ---
    # We use the real db_data functions, but mock the external verification
    mock_send_verification.return_value = True
    context = _create_mock_context()

    # === 1. User starts the bot ===
    update = _create_mock_update(text="/start", user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.start(update, context)
    assert state == librarybot.START_ROUTES
    update.message.reply_text.assert_called_once() # Initial welcome message

    # === 2. User clicks "Register" ===
    update = _create_mock_update(callback_data="register", user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.start_registration(update, context)
    assert state == librarybot.REGISTER_NAME
    update.callback_query.edit_message_text.assert_called_with(
        "Введите ваше **ФИО** (полностью, например: Иванов Иван Иванович):",
        reply_markup=ANY,
        parse_mode='Markdown'
    )
    assert 'registration' in context.user_data

    # === 3. User enters Full Name ===
    update = _create_mock_update(text=FULL_NAME, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_name(update, context)
    assert state == librarybot.REGISTER_DOB
    assert context.user_data['registration']['full_name'] == FULL_NAME

    # === 4. User enters Date of Birth ===
    update = _create_mock_update(text=DOB, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_dob(update, context)
    assert state == librarybot.REGISTER_CONTACT
    assert context.user_data['registration']['dob'] == DOB

    # === 5. User enters Contact Info ===
    update = _create_mock_update(text=CONTACT_INFO, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_contact(update, context)
    assert state == librarybot.REGISTER_VERIFY_CODE
    # Verification code should have been "sent" and stored
    mock_send_verification.assert_called_once()
    assert 'verification_code' in context.user_data
    verification_code = context.user_data['verification_code']

    # === 6. User enters correct Verification Code ===
    update = _create_mock_update(text=verification_code, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.verify_registration_code(update, context)
    assert state == librarybot.REGISTER_STATUS

    # === 7. User selects Status ===
    update = _create_mock_update(callback_data="студент", user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_status(update, context)
    assert state == librarybot.REGISTER_USERNAME
    assert context.user_data['registration']['status'] == "студент"

    # === 8. User enters Username ===
    update = _create_mock_update(text=USERNAME, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_username(update, context)
    assert state == librarybot.REGISTER_PASSWORD
    assert context.user_data['registration']['username'] == USERNAME

    # === 9. User enters Password ===
    update = _create_mock_update(text=PASSWORD, user_id=USER_ID, chat_id=CHAT_ID)
    state = await librarybot.get_password(update, context)
    assert state == librarybot.REGISTER_CONFIRM_PASSWORD
    assert 'password_temp' in context.user_data['registration']

    # === 10. User confirms Password ===
    update = _create_mock_update(text=PASSWORD, user_id=USER_ID, chat_id=CHAT_ID)
    # The final registration step calls start() again, so we catch the state
    final_state = await librarybot.get_password_confirmation(update, context)
    assert final_state == librarybot.START_ROUTES

    # === 11. Final Verification in Database ===
    # This is the most important part: check that the user was actually created.
    # We are NOT mocking db_data.add_user, so this should be a real check.
    newly_created_user = get_user_by_login(USERNAME)
    assert newly_created_user is not None
    assert newly_created_user['full_name'] == FULL_NAME
    assert newly_created_user['contact_info'] == CONTACT_INFO
    assert newly_created_user['status'] == 'студент'
    assert newly_created_user['telegram_id'] == USER_ID

    # Check that user_data is cleared after registration
    assert context.user_data == {}