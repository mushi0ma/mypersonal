# db_utils.py
import os
import hashlib
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import contextlib

# --- Глобальный пул соединений (теперь он пустой при старте) ---
db_pool = None

def get_db_pool():
    """
    Инициализирует и возвращает пул соединений (создает его только один раз).
    Это "ленивая" инициализация.
    """
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                dbname=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                host=os.getenv("DB_HOST"),
                port=os.getenv("DB_PORT")
            )
            print("✅ Пул соединений с базой данных успешно создан.")
        except psycopg2.OperationalError as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к базе данных: {e}")
            # В случае ошибки пул останется None
    return db_pool

@contextlib.contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасного получения и возврата соединения в пул."""
    # Теперь мы получаем пул через функцию, а не напрямую
    pool = get_db_pool()
    if not pool:
        raise ConnectionError("Пул соединений не был инициализирован или не удалось его создать.")

    conn = None
    try:
        conn = pool.getconn()
        yield conn
    finally:
        if conn:
            pool.putconn(conn)

def hash_password(password: str) -> str:
    """Хеширует пароль для безопасного хранения."""
    return hashlib.sha256(password.encode()).hexdigest()

def close_db_pool():
    """Closes all connections in the pool and sets the pool to None."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        db_pool = None
        print("ℹ️ Пул соединений с базой данных закрыт.")