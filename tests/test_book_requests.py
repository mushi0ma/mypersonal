import pytest
from src.core.db import data_access as db_data

pytestmark = pytest.mark.asyncio

USER_DATA = {
    'username': 'requester',
    'telegram_id': 99999,
    'telegram_username': 'requester',
    'full_name': 'Book Requester',
    'dob': '01.01.2000',
    'contact_info': 'requester@test.com',
    'status': 'студент',
    'password': 'password123'
}


async def test_create_book_request(db_session):
    """Тестирует создание запроса на книгу."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    
    request_data = {
        'name': 'Гарри Поттер',
        'author': 'Дж.К. Роулинг',
        'genre': 'Фэнтези',
        'description': 'Хочу прочитать эту книгу'
    }
    
    request_id = await db_data.create_book_request(db_session, user_id, request_data)
    assert isinstance(request_id, int)
    
    # Проверяем, что запрос создался в БД
    request_from_db = await db_session.fetchrow(
        "SELECT * FROM book_requests WHERE id = $1",
        request_id
    )
    assert request_from_db is not None
    assert request_from_db['book_name'] == 'Гарри Поттер'
    assert request_from_db['status'] == 'pending'


async def test_get_pending_requests(db_session):
    """Тестирует получение списка ожидающих запросов."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    
    # Создаем несколько запросов
    requests_data = [
        {'name': 'Книга 1', 'author': 'Автор 1'},
        {'name': 'Книга 2', 'author': 'Автор 2'},
        {'name': 'Книга 3', 'author': 'Автор 3'},
    ]
    
    for req_data in requests_data:
        await db_data.create_book_request(db_session, user_id, req_data)
    
    # Получаем ожидающие запросы
    pending = await db_data.get_pending_book_requests(db_session)
    assert len(pending) == 3
    assert all(req['book_name'] in ['Книга 1', 'Книга 2', 'Книга 3'] for req in pending)


async def test_approve_book_request(db_session):
    """Тестирует одобрение запроса на книгу."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    
    request_data = {
        'name': 'Новая книга',
        'author': 'Новый автор',
        'genre': 'Триллер',
        'description': 'Интересная книга'
    }
    
    request_id = await db_data.create_book_request(db_session, user_id, request_data)
    
    # Одобряем запрос
    approved_data = await db_data.approve_book_request(db_session, request_id)
    assert approved_data['book_name'] == 'Новая книга'
    
    # Проверяем статус
    status = await db_session.fetchval(
        "SELECT status FROM book_requests WHERE id = $1",
        request_id
    )
    assert status == 'approved'


async def test_reject_book_request(db_session):
    """Тестирует отклонение запроса на книгу."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    
    request_data = {'name': 'Плохая книга', 'author': 'Плохой автор'}
    request_id = await db_data.create_book_request(db_session, user_id, request_data)
    
    # Отклоняем запрос
    await db_data.reject_book_request(db_session, request_id, "Не соответствует профилю")
    
    # Проверяем статус и причину
    result = await db_session.fetchrow(
        "SELECT status, rejection_reason FROM book_requests WHERE id = $1",
        request_id
    )
    assert result['status'] == 'rejected'
    assert result['rejection_reason'] == "Не соответствует профилю"