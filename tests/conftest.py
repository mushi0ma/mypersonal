# tests/conftest.py
import pytest
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Загружаем переменные из .env.test
load_dotenv(dotenv_path='.env.test')

# --- Фикстура для управления тестовой базой данных ---
@pytest.fixture(scope="session")
def test_db_connection():
    """Создает соединение с тестовой базой данных перед запуском всех тестов."""
    conn_pool = None
    try:
        conn_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=1,
            dbname=os.getenv("TEST_DB_NAME"),
            user=os.getenv("TEST_DB_USER"),
            password=os.getenv("TEST_DB_PASSWORD"),
            host=os.getenv("TEST_DB_HOST"),
            port=os.getenv("TEST_DB_PORT")
        )
        conn = conn_pool.getconn()
        print("\n--- Connected to TEST database ---")
        yield conn  # Передаем соединение в тесты
    finally:
        if conn:
            conn_pool.putconn(conn)
        if conn_pool:
            conn_pool.closeall()
        print("\n--- Disconnected from TEST database ---")


@pytest.fixture(scope="function")
def db_session(test_db_connection):
    """
    Для каждого теста:
    1. Создает все таблицы.
    2. Выполняет тест.
    3. Удаляет все таблицы (очистка).
    """
    cursor = test_db_connection.cursor()
    
    # 1. Читаем и выполняем init_db.py для создания схемы
    # Мы не можем просто импортировать, так как он выполняет seed_data,
    # поэтому читаем SQL-команды из него.
    with open('init_db.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Очень упрощенный парсер, чтобы взять только CREATE TABLE команды
    import re
    create_table_commands = re.findall(r'"""\s*(CREATE TABLE.*?);', content, re.DOTALL)
    
    for command in create_table_commands:
        cursor.execute(command)
    
    test_db_connection.commit()
    print("\n--- Tables created ---")

    yield test_db_connection # Тест выполняется здесь

    # 3. Очистка после теста
    cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    test_db_connection.commit()
    cursor.close()
    print("\n--- Tables dropped ---")