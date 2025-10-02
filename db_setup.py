# -*- coding: utf-8 -*-
import os
import hashlib
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import contextlib

# Загружаем переменные из .env файла
load_dotenv()

# --- Глобальный пул соединений ---
db_pool = None
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=20, # Увеличим для Celery worker'ов и двух ботов
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )
    print("✅ Пул соединений с базой данных успешно создан.")
except psycopg2.OperationalError as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к базе данных: {e}")

@contextlib.contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасного получения и возврата соединения в пул."""
    if not db_pool:
        raise ConnectionError("Пул соединений не был инициализирован.")
    
    conn = None
    try:
        conn = db_pool.getconn()
        yield conn
    finally:
        if conn:
            db_pool.putconn(conn)

def hash_password(password: str) -> str:
    """Хеширует пароль для безопасного хранения."""
    return hashlib.sha256(password.encode()).hexdigest()

# Пример функции для инициализации БД (нужно запустить один раз вручную)
def initialize_database():
    """Создает необходимые таблицы, если они не существуют."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            telegram_username VARCHAR(255) UNIQUE,
            full_name VARCHAR(255) NOT NULL,
            dob VARCHAR(10),
            contact_info VARCHAR(255) UNIQUE NOT NULL,
            status VARCHAR(50),
            password_hash VARCHAR(255) NOT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # ... другие таблицы (authors, books, borrowed_books, ratings, etc.)
    )
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for command in commands:
                    cur.execute(command)
                conn.commit()
        print("✅ База данных успешно инициализирована.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")

if __name__ == '__main__':
    # Этот блок можно запустить напрямую для создания таблиц в БД
    # python db_setup.py
    print("Инициализация схемы базы данных...")
    # initialize_database() # Раскомментируйте для первого запуска