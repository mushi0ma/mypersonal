import pytest
from src.core.db import data_access as db_data

pytestmark = pytest.mark.asyncio


async def test_get_all_authors_paginated(db_session):
    """Тестирует получение списка авторов с пагинацией."""
    # Создаем авторов через добавление книг
    for i in range(15):
        book_data = {
            'name': f'Book by Author {i}',
            'author': f'Author {i}',
            'genre': 'Test',
            'description': 'Test book',
            'total_quantity': 1
        }
        await db_data.add_new_book(db_session, book_data)
    
    # Получаем первую страницу
    authors, total = await db_data.get_all_authors_paginated(db_session, limit=10, offset=0)
    
    assert len(authors) == 10
    assert total == 15
    
    # Проверяем, что у каждого автора есть books_count
    for author in authors:
        assert 'books_count' in author
        assert author['books_count'] >= 1


async def test_get_author_details(db_session):
    """Тестирует получение детальной информации об авторе."""
    # Создаем автора с несколькими книгами
    book1 = {
        'name': 'Book 1 by Tolkien',
        'author': 'J.R.R. Tolkien',
        'genre': 'Fantasy',
        'description': 'Fantasy book',
        'total_quantity': 2
    }
    book2 = {
        'name': 'Book 2 by Tolkien',
        'author': 'J.R.R. Tolkien',
        'genre': 'Fantasy',
        'description': 'Another fantasy book',
        'total_quantity': 1
    }
    
    await db_data.add_new_book(db_session, book1)
    await db_data.add_new_book(db_session, book2)
    
    # Получаем ID автора
    author_id = await db_session.fetchval("SELECT id FROM authors WHERE name = $1", 'J.R.R. Tolkien')
    
    # Получаем детали
    details = await db_data.get_author_details(db_session, author_id)
    
    assert details['name'] == 'J.R.R. Tolkien'
    assert details['total_books'] == 2
    assert details['available_books_count'] == 2


async def test_get_books_by_author(db_session):
    """Тестирует получение книг конкретного автора."""
    # Создаем книги
    for i in range(5):
        book_data = {
            'name': f'Asimov Book {i}',
            'author': 'Isaac Asimov',
            'genre': 'Sci-Fi',
            'description': f'Book {i}',
            'total_quantity': 1
        }
        await db_data.add_new_book(db_session, book_data)
    
    # Получаем ID автора
    author_id = await db_session.fetchval("SELECT id FROM authors WHERE name = $1", 'Isaac Asimov')
    
    # Получаем книги
    books, total = await db_data.get_books_by_author(db_session, author_id, limit=10, offset=0)
    
    assert len(books) == 5
    assert total == 5
    assert all('Asimov' in book['name'] for book in books)