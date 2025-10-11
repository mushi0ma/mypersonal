# src/core/db/utils.py
import hashlib
import asyncpg
import contextlib
import logging
import asyncio

from src.core import config

# --- Настройка логгера ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Глобальный пул соединений ---
db_pool = None

async def init_db_pool():
    """
    Инициализирует и возвращает пул соединений asyncpg (создает его только один раз).
    Должен вызываться при старте приложения.
    """
    global db_pool
    if db_pool is None:
        try:
            db_pool = await asyncpg.create_pool(
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                host=config.DB_HOST,
                port=config.DB_PORT
            )
            logger.info("Пул соединений с базой данных (asyncpg) успешно создан.")
        except Exception as e:
            logger.critical(f"Не удалось подключиться к базе данных для создания пула (asyncpg): {e}", exc_info=True)
            raise

@contextlib.asynccontextmanager
async def get_db_connection():
    """
    Асинхронный контекстный менеджер для безопасного получения соединения из пула.
    """
    if db_pool is None:
        await init_db_pool()

    if not db_pool:
        raise ConnectionError("Пул соединений (asyncpg) не был инициализирован или не удалось его создать.")

    conn = None
    try:
        async with db_pool.acquire() as conn:
            yield conn
    except Exception as e:
        logger.error(f"Ошибка при работе с соединением из пула asyncpg: {e}", exc_info=True)
        raise

def hash_password(password: str) -> str:
    """Хеширует пароль для безопасного хранения, используя SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

async def close_db_pool():
    """Асинхронно закрывает все соединения в пуле."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        logger.info("Пул соединений с базой данных (asyncpg) закрыт.")