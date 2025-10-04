# tests/test_db_data.py
import pytest
import sys
import os

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