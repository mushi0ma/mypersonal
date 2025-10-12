import pytest
from src.core.db import data_access as db_data

pytestmark = pytest.mark.asyncio

USER_DATA = {
    'username': 'rater',
    'telegram_id': 88888,
    'telegram_username': 'rater',
    'full_name': 'Book Rater',
    'dob': '01.01.1995',
    'contact_info': 'rater@test.com',
    'status': 'студент',
    'password': 'password123'
}

BOOK_DATA = {
    'name': 'Test Book for Rating',
    'author': 'Test Author',
    'genre': 'Test Genre',
    'description': 'Test Description',
    'total_quantity': 1
}


async def test_add_rating(db_session):
    """Тестирует добавление оценки книге."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Добавляем оценку
    await db_data.add_rating(db_session, user_id, book_id, 5)
    
    # Проверяем
    rating = await db_session.fetchval(
        "SELECT rating FROM ratings WHERE user_id = $1 AND book_id = $2",
        user_id, book_id
    )
    assert rating == 5


async def test_update_rating(db_session):
    """Тестирует изменение существующей оценки."""
    user_id = await db_data.add_user(db_session, USER_DATA)
    book_id = await db_data.add_new_book(db_session, BOOK_DATA)
    
    # Добавляем оценку
    await db_data.add_rating(db_session, user_id, book_id, 3)
    
    # Изменяем оценку
    await db_data.add_rating(db_session, user_id, book_id, 5)
    
    # Проверяем, что оценка изменилась
    rating = await db_session.fetchval(
        "SELECT rating FROM ratings WHERE user_id = $1 AND book_id = $2",
        user_id, book_id
    )
    assert rating == 5
    
    # Проверяем, что оценка одна (не дублировалась)
    count = await db_session.fetchval(
        "SELECT COUNT(*) FROM ratings WHERE user_id = $1 AND book_id = $2",
        user_id, book_id
    )
    assert count == 1


async def test_get_top_rated_books(db_session):
    """Тестирует получение топа книг по оценкам."""
    # Создаем пользователей и книги
    user1_id = await db_data.add_user(db_session, {**USER_DATA, 'username': 'user1', 'contact_info': 'user1@test.com', 'telegram_id': 11111})
    user2_id = await db_data.add_user(db_session, {**USER_DATA, 'username': 'user2', 'contact_info': 'user2@test.com', 'telegram_id': 22222})
    
    book1_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': 'Отличная книга'})
    book2_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': 'Хорошая книга'})
    book3_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': 'Средняя книга'})
    
    # Добавляем оценки
    await db_data.add_rating(db_session, user1_id, book1_id, 5)
    await db_data.add_rating(db_session, user2_id, book1_id, 5)
    
    await db_data.add_rating(db_session, user1_id, book2_id, 4)
    await db_data.add_rating(db_session, user2_id, book2_id, 4)
    
    await db_data.add_rating(db_session, user1_id, book3_id, 3)
    
    # Получаем топ
    top_books = await db_data.get_top_rated_books(db_session, limit=10)
    
    # Проверяем результаты
    assert len(top_books) == 3  # Все 3 книги должны быть в топе
    assert top_books[0]['name'] == 'Отличная книга'  # Средний рейтинг 5.0
    assert top_books[1]['name'] == 'Хорошая книга'   # Средний рейтинг 4.0
    assert top_books[2]['name'] == 'Средняя книга'   # Средний рейтинг 3.0
    assert float(top_books[0]['avg_rating']) == 5.0


async def test_rating_statistics(db_session):
    """Тестирует получение статистики по оценкам."""
    # Создаем данные
    user1_id = await db_data.add_user(db_session, {**USER_DATA, 'username': 'stat1', 'contact_info': 'stat1@test.com', 'telegram_id': 33333})
    user2_id = await db_data.add_user(db_session, {**USER_DATA, 'username': 'stat2', 'contact_info': 'stat2@test.com', 'telegram_id': 44444})
    
    book1_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': 'Book 1'})
    book2_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': 'Book 2'})
    
    # Добавляем оценки
    await db_data.add_rating(db_session, user1_id, book1_id, 5)
    await db_data.add_rating(db_session, user1_id, book2_id, 4)
    await db_data.add_rating(db_session, user2_id, book1_id, 3)
    
    # Получаем статистику
    stats = await db_data.get_rating_statistics(db_session)
    
    assert stats['total_ratings'] == 3
    assert stats['users_who_rated'] == 2
    assert stats['books_rated'] == 2
    assert 3.5 < stats['avg_rating'] < 4.5  # Средняя оценка около 4
    assert 5 in stats['distribution']
    assert 4 in stats['distribution']
    assert 3 in stats['distribution']


async def test_get_all_ratings_paginated(db_session):
    """Тестирует постраничное получение оценок."""
    # Создаем данные
    user_id = await db_data.add_user(db_session, USER_DATA)
    
    # Создаем 15 книг и оцениваем их
    book_ids = []
    for i in range(15):
        book_id = await db_data.add_new_book(db_session, {**BOOK_DATA, 'name': f'Book {i}'})
        book_ids.append(book_id)
        await db_data.add_rating(db_session, user_id, book_id, (i % 5) + 1)
    
    # Получаем первую страницу (10 элементов)
    ratings, total = await db_data.get_all_ratings_paginated(db_session, limit=10, offset=0)
    
    assert len(ratings) == 10
    assert total == 15
    
    # Получаем вторую страницу
    ratings2, total2 = await db_data.get_all_ratings_paginated(db_session, limit=10, offset=10)
    
    assert len(ratings2) == 5
    assert total2 == 15