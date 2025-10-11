# tests/test_db_data.py
import pytest
import datetime

from src.core.db import data_access as db_data
from src.core.db.data_access import UserExistsError, NotFoundError

pytestmark = pytest.mark.asyncio

# Данные для тестового пользователя
USER_DATA = {
    'username': 'testuser123',
    'telegram_id': 12345,
    'telegram_username': 'testuser',
    'full_name': 'Test User',
    'dob': '01.01.2000',
    'contact_info': 'test@example.com',
    'status': 'студент',
    'password': 'password123'
}

AUTHOR_DATA = {'name': 'Test Author'}
BOOK_DATA = {
    'name': 'Test Book',
    'author': 'Test Author',
    'genre': 'Fantasy',
    'description': 'A book for testing.',
    'cover_image_id': 'file123',
    'total_quantity': 1
}

async def test_add_user_success(db_session):
    """Тестирует успешное добавление пользователя в реальную тестовую БД."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    assert isinstance(user_id, int)
    
    user_from_db = await db_session.fetchrow("SELECT username, full_name FROM users WHERE id = $1", user_id)
    assert user_from_db is not None
    assert user_from_db['username'] == USER_DATA['username']
    assert user_from_db['full_name'] == USER_DATA['full_name']

async def test_add_user_already_exists(db_session):
    """Тестирует выброс исключения при попытке добавить дубликат."""
    await db_data.add_user(db_session, USER_DATA)
    with pytest.raises(UserExistsError):
        await db_data.add_user(db_session, USER_DATA)

async def test_get_user_by_login_found(db_session):
    """Тестирует поиск существующего пользователя."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    found_user = await db_data.get_user_by_login(db_session, USER_DATA['username'])
    assert found_user is not None
    assert found_user['id'] == user_id
    assert found_user['full_name'] == USER_DATA['full_name']

async def test_get_user_by_login_not_found(db_session):
    """Тестирует выброс исключения, если пользователь не найден."""
    with pytest.raises(NotFoundError):
        await db_data.get_user_by_login(db_session, 'non_existent_user')

async def test_get_or_create_author(db_session):
    """Тестирует поиск и создание автора."""
    author_id_1 = await db_data.get_or_create_author(db_session, "New Author")
    assert isinstance(author_id_1, int)

    author_id_2 = await db_data.get_or_create_author(db_session, "New Author")
    assert author_id_1 == author_id_2

    author_name = await db_session.fetchval("SELECT name FROM authors WHERE id = $1", author_id_1)
    assert author_name == "New Author"

async def test_add_new_book(db_session):
    """Тестирует добавление новой книги."""
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    assert isinstance(book_id, int)

    record = await db_session.fetchrow(
        "SELECT b.name, a.name as author_name FROM books b JOIN authors a ON b.author_id = a.id WHERE b.id = $1",
        book_id
    )
    assert record['name'] == BOOK_DATA['name']
    assert record['author_name'] == BOOK_DATA['author']

async def test_borrow_return_book_flow(db_session):
    """Тестирует полный цикл взятия и возврата книги."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)

    # 1. Берем книгу
    due_date = await db_data.borrow_book(db_session, user_id, book_id)
    assert isinstance(due_date, datetime.date)

    # Проверяем, что книга теперь числится как взятая
    borrowed_books = await db_data.get_borrowed_books(db_session, user_id)
    assert len(borrowed_books) == 1
    assert borrowed_books[0]['book_id'] == book_id
    
    borrow_id = borrowed_books[0]['borrow_id']

    # 2. Возвращаем книгу
    result = await db_data.return_book(db_session, borrow_id, book_id)
    assert result == "Успешно"

    # Проверяем, что у пользователя больше нет книг на руках
    borrowed_after_return = await db_data.get_borrowed_books(db_session, user_id)
    assert len(borrowed_after_return) == 0