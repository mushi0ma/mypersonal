# src/health_check.py
import os
import logging
import asyncpg
from redis import Redis
from src.core import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_database():
    """Асинхронно проверяет соединение с базой данных."""
    try:
        conn = await asyncpg.connect(
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            host=config.DB_HOST,
            port=config.DB_PORT,
            timeout=5  # 5-секундный таймаут
        )
        await conn.close()
        return True, "Database connection successful."
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False, str(e)

def check_redis():
    """Проверяет соединение с Redis."""
    try:
        redis_host = config.CELERY_BROKER_URL.split('//')[1].split(':')[0]
        r = Redis(host=redis_host, port=6379, socket_connect_timeout=5)
        r.ping()
        return True, "Redis connection successful."
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False, str(e)

async def run_health_check():
    """Запускает все проверки и возвращает общий статус."""
    db_ok, db_msg = await check_database()
    redis_ok, redis_msg = check_redis()

    all_ok = db_ok and redis_ok
    message = f"DB: {db_msg} | Redis: {redis_msg}"
    
    if all_ok:
        logger.info("Health check passed.")
    else:
        logger.warning(f"Health check failed: {message}")

    return all_ok, message

if __name__ == '__main__':
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()

    all_ok, message = asyncio.run(run_health_check())
    print(f"Health Check Status: {'OK' if all_ok else 'FAILED'}")
    print(f"Details: {message}")