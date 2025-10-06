# db_utils.py
import hashlib
import psycopg2
from psycopg2 import pool
import contextlib
import logging

from src.core import config

# --- Настройка логгера ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Глобальный пул соединений ---
db_pool = None

def get_db_pool():
    """
    Инициализирует и возвращает пул соединений (создает его только один раз).
    Использует "ленивую" инициализацию.
    """
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                dbname=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                host=config.DB_HOST,
                port=config.DB_PORT
            )
            logger.info("Пул соединений с базой данных успешно создан.")
        except psycopg2.OperationalError as e:
            # Используем CRITICAL, так как без БД приложение бесполезно
            logger.critical(f"Не удалось подключиться к базе данных для создания пула: {e}")
            
    return db_pool

@contextlib.contextmanager
def get_db_connection():
    """
    Контекстный менеджер для безопасного получения соединения из пула и его возврата.
    """
    pool = get_db_pool()
    if not pool:
        raise ConnectionError("Пул соединений не был инициализирован или не удалось его создать.")

    conn = None
    try:
        conn = pool.getconn()
        yield conn
        # Если блок 'with' завершился без ошибок, коммит произойдет здесь
        conn.commit() 
    except Exception:
        # В случае любой ошибки откатываем транзакцию
        if conn:
            conn.rollback()
        # Пробрасываем ошибку дальше, чтобы ее можно было обработать выше
        raise 
    finally:
        # В любом случае возвращаем соединение в пул
        if conn:
            pool.putconn(conn)

def hash_password(password: str) -> str:
    """Хеширует пароль для безопасного хранения, используя SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def close_db_pool():
    """Закрывает все соединения в пуле. Полезно для корректного завершения работы приложения."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        db_pool = None
        logger.info("Пул соединений с базой данных закрыт.")