import pytest
from src.core.db import data_access as db_data

pytestmark = pytest.mark.asyncio


async def test_search_available_books(db_session):
    """Тестирует поиск доступных книг по названию и автору."""
    # Создаем книги
    books_data = [
        {'name': 'Гарри Поттер и философский камень', 'author': 'Дж.К. Роулинг', 'genre': 'Фэнтези'},
        {'name': 'Гарри Поттер и тайная комната', 'author': 'Дж.К. Роулинг', 'genre': 'Фэнтези'},
        {'name': 'Властелин колец', 'author': 'Дж.Р.Р. Толкин', 'genre': 'Фэнтези'},
        {'name': '1984', 'author': 'Джордж Оруэлл', 'genre': 'Антиутопия'},
    ]
    
    for book_data in books_data:
        book_data.update({'description': 'Test', 'total_quantity': 1})
        await db_data.add_new_book(db_session, book_data)
    
    # Поиск по названию
    results1, total1 = await db_data.search_available_books(db_session, 'Гарри', limit=10, offset=0)
    assert len(results1) == 2
    assert total1 == 2
    
    # Поиск по автору
    results2, total2 = await db_data.search_available_books(db_session, 'Роулинг', limit=10, offset=0)
    assert len(results2) == 2
    assert total2 == 2
    
    # Поиск по частичному совпадению
    results3, total3 = await db_data.search_available_books(db_session, 'кольц', limit=10, offset=0)
    assert len(results3) == 1
    assert 'Властелин' in results3[0]['name']


async def test_get_unique_genres(db_session):
    """Тестирует получение списка уникальных жанров."""
    # Создаем книги с разными жанрами
    genres = ['Фэнтези', 'Фантастика', 'Детектив', 'Фэнтези', 'Триллер', 'Фантастика']
    
    for i, genre in enumerate(genres):
        book_data = {
            'name': f'Book {i}',
            'author': f'Author {i}',
            'genre': genre,
            'description': 'Test',
            'total_quantity': 1
        }
        await db_data.add_new_book(db_session, book_data)
    
    # Получаем уникальные жанры
    unique_genres = await db_data.get_unique_genres(db_session)
    
    assert len(unique_genres) == 4
    assert set(unique_genres) == {'Фэнтези', 'Фантастика', 'Детектив', 'Триллер'}


async def test_get_available_books_by_genre(db_session):
    """Тестирует получение доступных книг по жанру."""
    # Создаем книги
    for i in range(3):
        await db_data.add_new_book(db_session, {
            'name': f'Fantasy Book {i}',
            'author': f'Author {i}',
            'genre': 'Фэнтези',
            'description': 'Test',
            'total_quantity': 1
        })
    
    for i in range(2):
        await db_data.add_new_book(db_session, {
            'name': f'Detective Book {i}',
            'author': f'Author {i}',
            'genre': 'Детектив',
            'description': 'Test',
            'total_quantity': 1
        })
    
    # Получаем книги по жанру
    fantasy_books, total_fantasy = await db_data.get_available_books_by_genre(
        db_session, 'Фэнтези', limit=10, offset=0
    )
    
    assert len(fantasy_books) == 3
    assert total_fantasy == 3
    assert all('Fantasy' in book['name'] for book in fantasy_books)