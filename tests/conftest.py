# tests/conftest.py
import pytest
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import re

# --- ВРЕМЕННОЕ РЕШЕНИЕ: Жестко задаем данные для подключения ---
TEST_DB_CONFIG = {
    "dbname": "test_db",
    "user": "test_user",
    "password": "test_password",
    "host": "localhost",
    "port": "5434" # Убедитесь, что порт верный
}
# -----------------------------------------------------------

# Загружаем остальные переменные (не для БД)
load_dotenv(dotenv_path='.env.test', encoding='utf-8')

@pytest.fixture(scope="session")
def test_db_connection():
    """Создает соединение с тестовой базой данных."""
    conn_pool = None
    conn = None
    try:
        # Используем наши жестко заданные данные вместо os.getenv()
        conn_pool = psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=1, **TEST_DB_CONFIG)
        conn = conn_pool.getconn()
        print("\n--- Connected to TEST database ---")
        yield conn
    finally:
        if conn and conn_pool:
            conn_pool.putconn(conn)
        if conn_pool:
            conn_pool.closeall()
        print("\n--- Disconnected from TEST database ---")

@pytest.fixture(scope="function")
def db_session(test_db_connection):
    """Для каждого теста: создает и очищает таблицы."""
    cursor = test_db_connection.cursor()
    
    with open('init_db.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    create_table_commands = re.findall(r'"""\s*(CREATE TABLE.*?);', content, re.DOTALL)
    
    for command in create_table_commands:
        cursor.execute(command)
    
    test_db_connection.commit()
    print("\n--- Tables created ---")

    yield test_db_connection

    cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    test_db_connection.commit()
    cursor.close()
    print("\n--- Tables dropped ---")