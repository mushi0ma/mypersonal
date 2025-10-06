# tests/test_admin_bot_integration.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from contextlib import contextmanager

# Мокируем модуль tasks перед импортом admin_bot
with patch.dict('sys.modules', {'src.core.tasks': MagicMock()}):
    from src.admin_bot import main as admin_bot
    from src.core.db import data_access as db_data
    from src.admin_bot.states import AdminState

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler

pytestmark = pytest.mark.asyncio

def _create_mock_update(text=None, callback_data=None, photo=None, user_id=1, chat_id=1):
    """Создает мок-объект Update для симуляции действий админа."""
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
        # Сообщения с callback могут иметь текст или caption
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
    """Создает мок-объект Context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    context.user_data = {}
    return context

async def test_stats_command(db_session, monkeypatch, mock_context):
    """Тестирует, что команда /stats показывает сводную панель."""
    @contextmanager
    def mock_get_db_connection():
        yield db_session
    monkeypatch.setattr(admin_bot.stats, 'get_db_connection', mock_get_db_connection)
    
    update = _create_mock_update(text="/stats")
    
    await admin_bot.stats.show_stats_panel(update, mock_context)
    
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message_text = call_args[0][0]
    assert "📊 Панель статистики" in message_text
    assert "Активных пользователей" in message_text

async def test_add_book_flow(db_session, monkeypatch, mock_context):
    """Интеграционный тест для полного цикла добавления книги."""
    @contextmanager
    def mock_get_db_connection():
        yield db_session
    
    monkeypatch.setattr(admin_bot.books, 'get_db_connection', mock_get_db_connection)

    # --- Шаг 1: Начинаем диалог ---
    update = _create_mock_update(callback_data="admin_add_book_start")
    state = await admin_bot.books.add_book_start(update, mock_context)
    assert state == AdminState.GET_NAME
    mock_context.user_data['new_book'] = {}

    # --- Шаг 2-5: Вводим данные ---
    update = _create_mock_update(text="Война и мир")
    state = await admin_bot.books.get_book_name(update, mock_context)
    assert state == AdminState.GET_AUTHOR

    update = _create_mock_update(text="Лев Толстой")
    state = await admin_bot.books.get_book_author(update, mock_context)
    assert state == AdminState.GET_GENRE

    update = _create_mock_update(text="Роман-эпопея")
    state = await admin_bot.books.get_book_genre(update, mock_context)
    assert state == AdminState.GET_DESCRIPTION
    
    update = _create_mock_update(text="Великий роман о русском обществе.")
    state = await admin_bot.books.get_book_description(update, mock_context)
    assert state == AdminState.GET_COVER

    # --- Шаг 6: Пропускаем обложку ---
    update = _create_mock_update(text="пропустить")
    state = await admin_bot.books.skip_cover(update, mock_context)
    assert state == AdminState.CONFIRM_ADD
    
    # Проверяем, что бот показал подтверждение
    update.message.reply_text.assert_called_with(
        text=pytest.string_containing("🔍 Проверьте данные"),
        reply_markup=pytest.anything,
        parse_mode='Markdown'
    )

    # --- Шаг 7: Сохраняем книгу ---
    update = _create_mock_update(callback_data="add_book_save_simple")
    state = await admin_bot.add_book_save(update, mock_context)
    assert state == ConversationHandler.END

    # --- Финальная проверка в БД ---
    cursor = db_session.cursor()
    cursor.execute("SELECT name, author_id FROM books WHERE name = 'Война и мир'")
    book_from_db = cursor.fetchone()
    assert book_from_db is not None
    
    cursor.execute("SELECT name FROM authors WHERE id = %s", (book_from_db[1],))
    author_name = cursor.fetchone()[0]
    assert author_name == "Лев Толстой"
    cursor.close()