import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock pywhatkit before it's imported by librarybot
sys.modules['pywhatkit'] = MagicMock()

from telegram import Update, User, Message, Chat
from telegram.ext import ConversationHandler, Application, ContextTypes

# Import the functions and states from librarybot
import librarybot

class TestLibraryBotIntegration(unittest.TestCase):

    def setUp(self):
        # Create a mock application and context
        self.application = MagicMock(spec=Application)
        self.context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        self.context.bot = AsyncMock()
        self.context.user_data = {}

    def _create_mock_update(self, text=None, callback_data=None, user_id=123, chat_id=123):
        """Helper to create a mock Update object."""
        update = MagicMock(spec=Update)
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = chat_id
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = user_id

        if text:
            update.message = MagicMock(spec=Message)
            update.message.text = text
            update.message.from_user = update.effective_user
            update.callback_query = None

        if callback_data:
            update.callback_query = MagicMock()
            update.callback_query.data = callback_data
            update.callback_query.message = MagicMock(spec=Message)
            update.callback_query.message.chat_id = chat_id
            update.callback_query.answer = AsyncMock() # Make the answer method awaitable
            update.callback_query.edit_message_text = AsyncMock()
            update.message = None

        return update

    @patch('librarybot.db_data')
    @patch('librarybot.send_verification_message', new_callable=AsyncMock)
    def test_registration_flow(self, mock_send_verification, mock_db_data):
        """Test the full registration flow in an integrated way."""

        async def run_test():
            # Mock database calls
            mock_db_data.get_user_by_login.return_value = None
            mock_db_data.add_user.return_value = 1 # Mock successful user creation
            mock_send_verification.return_value = True

            # 1. User starts the bot
            update = self._create_mock_update(text="/start")
            state = await librarybot.start(update, self.context)
            self.assertEqual(state, librarybot.START_ROUTES)
            self.context.bot.send_message.assert_called_once()

            # 2. User clicks "Register"
            update = self._create_mock_update(callback_data="register")
            state = await librarybot.start_registration(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_NAME)
            update.callback_query.edit_message_text.assert_called_with(
                "Введите ваше **ФИО** (полностью, например: Иванов Иван Иванович):",
                reply_markup=unittest.mock.ANY,
                parse_mode='Markdown'
            )

            # 3. User enters name
            update = self._create_mock_update(text="Тестов Тест Тестович")
            state = await librarybot.get_name(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_DOB)
            self.assertEqual(self.context.user_data['registration']['full_name'], "Тестов Тест Тестович")

            # 4. User enters date of birth
            update = self._create_mock_update(text="01.01.1990")
            state = await librarybot.get_dob(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_CONTACT)
            self.assertEqual(self.context.user_data['registration']['dob'], "01.01.1990")

            # 5. User enters contact info
            update = self._create_mock_update(text="test@example.com")
            state = await librarybot.get_contact(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_VERIFY_CODE)
            mock_send_verification.assert_called_once()
            self.assertIn('verification_code', self.context.user_data)

            # 6. User enters verification code
            verification_code = self.context.user_data['verification_code']
            update = self._create_mock_update(text=verification_code)
            state = await librarybot.verify_registration_code(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_STATUS)

            # 7. User selects status
            update = self._create_mock_update(callback_data="студент")
            state = await librarybot.get_status(update, self.context)
            self.assertEqual(state, librarybot.REGISTER_PASSWORD)
            self.assertEqual(self.context.user_data['registration']['status'], "студент")

            # 8. User enters password and completes registration
            update = self._create_mock_update(text="ValidPassword123")
            state = await librarybot.get_password(update, self.context)
            self.assertEqual(state, librarybot.START_ROUTES)
            mock_db_data.add_user.assert_called_once()

            # Check that user_data is cleared after registration
            self.assertEqual(self.context.user_data, {})

        # Run the async test
        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()