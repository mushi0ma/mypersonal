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
# Этот файл теперь отвечает только за настройку пула соединений и утилиты.
# Для инициализации базы данных используйте `python init_db.py`.