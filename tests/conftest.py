# tests/conftest.py
import pytest
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import sys

# Добавляем корневую директорию в путь, чтобы можно было импортировать init_db
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from init_db import SCHEMA_COMMANDS # <-- ИМПОРТИРУЕМ НАШУ СХЕМУ НАПРЯМУЮ

# Загружаем переменные из .env.test
load_dotenv(dotenv_path='.env.test')

@pytest.fixture(scope="session")
def test_db_connection():
    """Создает и предоставляет соединение с тестовой базой данных на всю сессию."""
    conn_pool = None
    conn = None
    try:
        conn_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=1,
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        conn = conn_pool.getconn()
        yield conn
    finally:
        if conn and conn_pool:
            conn_pool.putconn(conn)
        if conn_pool:
            conn_pool.closeall()

@pytest.fixture(scope="function")
def db_session(test_db_connection):
    """
    Для каждого теста: создает чистую схему БД, предоставляет сессию,
    а после теста все удаляет.
    """
    cursor = test_db_connection.cursor()
    
    # --- УПРОЩЕННАЯ ЛОГИКА ---
    # Просто итерируемся по импортированным командам
    for command in SCHEMA_COMMANDS:
        cursor.execute(command)

    test_db_connection.commit()
    
    yield test_db_connection # Предоставляем настроенную сессию тесту

    # --- Очистка после теста ---
    cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    test_db_connection.commit()
    cursor.close()