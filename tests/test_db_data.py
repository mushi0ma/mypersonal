# tests/test_db_data.py
import pytest
import sys
import os
import datetime

# Добавляем корневую директорию в путь, чтобы можно было импортировать db_data
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db_data
from db_data import UserExistsError, NotFoundError

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

def test_add_user_success(db_session):
    """Тестирует успешное добавление пользователя в реальную тестовую БД."""
    # Действие: вызываем нашу функцию, передавая соединение
    user_id = db_data.add_user(db_session, USER_DATA)

    # Проверка: подключаемся к БД и проверяем, что пользователь действительно там
    assert isinstance(user_id, int)
    
    cursor = db_session.cursor()
    cursor.execute("SELECT username, full_name FROM users WHERE id = %s", (user_id,))
    user_from_db = cursor.fetchone()
    cursor.close()

    assert user_from_db is not None
    assert user_from_db[0] == USER_DATA['username']
    assert user_from_db[1] == USER_DATA['full_name']

def test_add_user_already_exists(db_session):
    """Тестирует выброс исключения при попытке добавить дубликат."""
    # Подготовка: сначала успешно добавляем пользователя
    db_data.add_user(db_session, USER_DATA)

    # Действие и Проверка: ожидаем, что вторая попытка вызовет UserExistsError
    with pytest.raises(UserExistsError):
        db_data.add_user(db_session, USER_DATA)

def test_get_user_by_login_found(db_session):
    """Тестирует поиск существующего пользователя."""
    # Подготовка: добавляем пользователя, чтобы было что искать
    user_id = db_data.add_user(db_session, USER_DATA)

    # Действие: ищем этого пользователя по его юзернейму
    found_user = db_data.get_user_by_login(db_session, USER_DATA['username'])

    # Проверка: убеждаемся, что нашелся правильный пользователь
    assert found_user is not None
    assert found_user['id'] == user_id
    assert found_user['full_name'] == USER_DATA['full_name']

def test_get_user_by_login_not_found(db_session):
    """Тестирует выброс исключения, если пользователь не найден."""
    # Действие и Проверка: ожидаем NotFoundError при поиске несуществующего пользователя
    with pytest.raises(NotFoundError):
        db_data.get_user_by_login(db_session, 'non_existent_user')

# Новые тестовые данные
AUTHOR_DATA = {'name': 'Test Author'}
BOOK_DATA = {
    'name': 'Test Book',
    'author': 'Test Author',
    'genre': 'Fantasy',
    'description': 'A book for testing.',
    'cover_image_id': 'file123',
    'total_quantity': 1,
    'available_quantity': 1
}

def test_get_or_create_author(db_session):
    """Тестирует поиск и создание автора."""
    # 1. Создаем нового автора
    author_id_1 = db_data.get_or_create_author(db_session, "New Author")
    assert isinstance(author_id_1, int)

    # 2. Пытаемся получить его снова, должны получить тот же ID
    author_id_2 = db_data.get_or_create_author(db_session, "New Author")
    assert author_id_1 == author_id_2

    # 3. Проверяем в БД
    cursor = db_session.cursor()
    cursor.execute("SELECT name FROM authors WHERE id = %s", (author_id_1,))
    assert cursor.fetchone()[0] == "New Author"
    cursor.close()

def test_add_new_book(db_session):
    """Тестирует добавление новой книги."""
    book_id = db_data.add_new_book(db_session, BOOK_DATA)
    assert isinstance(book_id, int)

    # Проверяем, что книга и автор были созданы
    cursor = db_session.cursor()
    cursor.execute("""
        SELECT b.name, a.name FROM books b
        JOIN authors a ON b.author_id = a.id
        WHERE b.id = %s
    """, (book_id,))
    book_name, author_name = cursor.fetchone()
    cursor.close()

    assert book_name == BOOK_DATA['name']
    assert author_name == BOOK_DATA['author']

def test_borrow_return_book_flow(db_session):
    """Тестирует полный цикл взятия и возврата книги."""
    # Подготовка
    user_id = db_data.add_user(db_session, USER_DATA)
    book_id = db_data.add_new_book(db_session, BOOK_DATA)

    # 1. Берем книгу
    due_date = db_data.borrow_book(db_session, user_id, book_id)
    assert isinstance(due_date, datetime.date)

    # Проверяем, что книга теперь числится как взятая
    borrowed_books = db_data.get_borrowed_books(db_session, user_id)
    assert len(borrowed_books) == 1
    assert borrowed_books[0]['book_id'] == book_id
    
    borrow_id = borrowed_books[0]['borrow_id']

    # 2. Возвращаем книгу
    result = db_data.return_book(db_session, borrow_id, book_id)
    assert result == "Успешно"

    # Проверяем, что у пользователя больше нет книг на руках
    assert len(db_data.get_borrowed_books(db_session, user_id)) == 0