import pytest
from datetime import datetime, timedelta
from src.core.db import data_access as db_data

pytestmark = pytest.mark.asyncio

USER_DATA = {
    'username': 'extended_user',
    'telegram_id': 77777,
    'telegram_username': 'extended_user',
    'full_name': 'Extended Features User',
    'dob': '15.05.1998',
    'contact_info': 'extended@test.com',
    'status': 'студент',
    'password': 'password123'
}

BOOK_DATA = {
    'name': 'Extended Test Book',
    'author': 'Extended Author',
    'genre': 'Test',
    'description': 'For testing extended features',
    'total_quantity': 1
}


async def test_extend_due_date(db_session):
    """Тестирует продление срока возврата книги."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Берем книгу
    original_due_date = await db_data.borrow_book(db_session, user_id, book_id)
    
    # Получаем borrow_id
    borrow_id = await db_session.fetchval(
        "SELECT borrow_id FROM borrowed_books WHERE user_id = $1 AND book_id = $2 AND return_date IS NULL",
        user_id, book_id
    )
    
    # Продлеваем
    new_due_date = await db_data.extend_due_date(db_session, borrow_id)
    
    assert isinstance(new_due_date, datetime)
    assert new_due_date > original_due_date


async def test_extend_due_date_limit(db_session):
    """Тестирует ограничение на количество продлений."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Берем книгу
    await db_data.borrow_book(db_session, user_id, book_id)
    
    borrow_id = await db_session.fetchval(
        "SELECT borrow_id FROM borrowed_books WHERE user_id = $1 AND book_id = $2 AND return_date IS NULL",
        user_id, book_id
    )
    
    # Первое продление - должно работать
    result1 = await db_data.extend_due_date(db_session, borrow_id)
    assert isinstance(result1, datetime)
    
    # Второе продление - должно отказать
    result2 = await db_data.extend_due_date(db_session, borrow_id)
    assert isinstance(result2, str)
    assert "продлевали" in result2.lower()


async def test_reservation_system(db_session):
    """Тестирует систему резервирования книг."""
    user1_id = await db_data.add_user(db_session, USER_DATA)
    user2_id = await db_data.add_user(db_session, {**USER_DATA, 'username': 'user2', 'contact_info': 'user2@test.com', 'telegram_id': 66666})
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # User1 берет книгу
    await db_data.borrow_book(db_session, user1_id, book_id)
    
    # User2 резервирует книгу
    result = await db_data.add_reservation(db_session, user2_id, book_id)
    assert "успешно" in result.lower()
    
    # Проверяем, что резервация создана
    reservations = await db_data.get_reservations_for_book(db_session, book_id)
    assert user2_id in reservations
    
    # Пытаемся зарезервировать повторно - должно отказать
    result2 = await db_data.add_reservation(db_session, user2_id, book_id)
    assert "уже" in result2.lower()


async def test_overdue_books_detection(db_session):
    """Тестирует определение просроченных книг."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Берем книгу
    await db_data.borrow_book(db_session, user_id, book_id)
    
    # Меняем due_date на вчера
    yesterday = datetime.now().date() - timedelta(days=1)
    await db_session.execute(
        "UPDATE borrowed_books SET due_date = $1 WHERE user_id = $2",
        yesterday, user_id
    )
    
    # Получаем просроченные книги
    overdue = await db_data.get_users_with_overdue_books(db_session)
    
    assert len(overdue) == 1
    assert overdue[0]['user_id'] == user_id
    assert overdue[0]['book_name'] == BOOK_DATA['name']


async def test_books_due_soon(db_session):
    """Тестирует определение книг с близким сроком возврата."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Берем книгу
    await db_data.borrow_book(db_session, user_id, book_id)
    
    # Меняем due_date на послезавтра
    day_after_tomorrow = datetime.now().date() + timedelta(days=2)
    await db_session.execute(
        "UPDATE borrowed_books SET due_date = $1 WHERE user_id = $2",
        day_after_tomorrow, user_id
    )
    
    # Получаем книги с близким сроком
    due_soon = await db_data.get_users_with_books_due_soon(db_session, days_ahead=2)
    
    assert len(due_soon) == 1
    assert due_soon[0]['user_id'] == user_id