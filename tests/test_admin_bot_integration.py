# tests/test_admin_bot_integration.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import types
from contextlib import asynccontextmanager

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def patched_admin_bot_handlers():
    """
    Mocks src.core.tasks and imports admin bot handlers inside a fixture.
    This prevents pytest from hanging during test collection by removing top-level side effects.
    """
    with patch.dict('sys.modules', {'src.core.tasks': MagicMock()}):
        from src.admin_bot.handlers import stats, books
        from src.core.db import data_access as db_data
        from src.admin_bot.states import AdminState

        handlers = types.SimpleNamespace()
        handlers.stats = stats
        handlers.books = books
        handlers.db_data = db_data
        handlers.AdminState = AdminState
        yield handlers

def _create_mock_update(text=None, callback_data=None, photo=None, user_id=1, chat_id=1):
    """Creates a mock Update object to simulate admin actions."""
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock(spec=Chat, id=chat_id)
    update.effective_user = MagicMock(spec=User, id=user_id, username='test_admin')

    if text is not None:
        update.message = AsyncMock(spec=Message)
        update.message.text = text
        update.message.from_user = update.effective_user
        update.message.chat_id = chat_id
        update.callback_query = None
    
    if callback_data is not None:
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = callback_data
        update.callback_query.from_user = update.effective_user
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.message.text = "Some previous message"
        update.callback_query.message.caption = None
        update.callback_query.message.photo = None
        update.message = None

    if photo:
        update.message = update.message or AsyncMock(spec=Message)
        update.message.photo = [MagicMock(file_id="test_photo_file_id")]
        update.message.text = None

    return update

@pytest.fixture
def mock_context():
    """Creates a mock Context object."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    context.user_data = {}
    return context

async def test_stats_command(db_session, monkeypatch, mock_context, patched_admin_bot_handlers):
    """Tests that the /stats command shows the summary panel."""
    stats = patched_admin_bot_handlers.stats

    @asynccontextmanager
    async def mock_manager():
        yield db_session

    monkeypatch.setattr(stats, 'get_db_connection', mock_manager)
    
    update = _create_mock_update(text="/stats")
    
    await stats.show_stats_panel(update, mock_context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message_text = call_args[0][0]
    assert "📊 Панель статистики" in message_text
    assert "Активных пользователей" in message_text

async def test_add_book_flow(db_session, monkeypatch, mock_context, patched_admin_bot_handlers):
    """Integration test for the complete book addition cycle."""
    books = patched_admin_bot_handlers.books
    AdminState = patched_admin_bot_handlers.AdminState
    
    @asynccontextmanager
    async def mock_manager():
        yield db_session

    monkeypatch.setattr(books, 'get_db_connection', mock_manager)

    # Step 1: Start the conversation
    update = _create_mock_update(callback_data="admin_add_book_start")
    state = await books.add_book_start(update, mock_context)
    assert state == AdminState.GET_NAME
    mock_context.user_data['new_book'] = {}

    # Steps 2-5: Enter data
    update = _create_mock_update(text="Война и мир")
    state = await books.get_book_name(update, mock_context)
    assert state == AdminState.GET_AUTHOR

    update = _create_mock_update(text="Лев Толстой")
    state = await books.get_book_author(update, mock_context)
    assert state == AdminState.GET_GENRE

    update = _create_mock_update(text="Роман-эпопея")
    state = await books.get_book_genre(update, mock_context)
    assert state == AdminState.GET_DESCRIPTION
    
    update = _create_mock_update(text="Великий роман о русском обществе.")
    state = await books.get_book_description(update, mock_context)
    assert state == AdminState.GET_COVER

    # Step 6: Skip cover
    update = _create_mock_update(text="пропустить")
    state = await books.skip_cover(update, mock_context)
    assert state == AdminState.CONFIRM_ADD
    
    # Check that the confirmation was shown
    update.message.reply_text.assert_called_with(
        text=pytest.string_containing("🔍 Проверьте данные"),
        reply_markup=pytest.anything,
        parse_mode='Markdown'
    )

    # Step 7: Save the book
    update = _create_mock_update(callback_data="add_book_save_simple")
    state = await books.add_book_save(update, mock_context)
    assert state == ConversationHandler.END

    # Final check in the DB
    book_from_db = await db_session.fetchrow("SELECT name, author_id FROM books WHERE name = $1", 'Война и мир')
    assert book_from_db is not None
    
    author_name = await db_session.fetchval("SELECT name FROM authors WHERE id = $1", book_from_db['author_id'])
    assert author_name == "Лев Толстой"