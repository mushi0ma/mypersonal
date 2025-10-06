import psycopg2
from redis import Redis
from db_utils import get_db_connection
import os
from tasks import celery_app, notify_admin

def check_database():
    """Проверка подключения к БД."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True, "OK"
    except Exception as e:
        return False, str(e)

def check_redis():
    """Проверка подключения к Redis."""
    try:
        redis_client = Redis.from_url(os.getenv("CELERY_BROKER_URL"))
        redis_client.ping()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def check_celery_workers():
    """Проверка работы Celery workers."""
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        if stats:
            active_workers = len(stats)
            return True, f"{active_workers} workers активны"
        else:
            return False, "Нет активных workers"
    except Exception as e:
        return False, str(e)

def run_health_check():
    """Запуск полной проверки здоровья системы."""
    checks = {
        "Database": check_database(),
        "Redis": check_redis(),
        "Celery Workers": check_celery_workers(),
    }
    
    all_ok = all(status for status, _ in checks.values())
    
    message_parts = ["🏥 **Health Check**\n"]
    for component, (status, msg) in checks.items():
        icon = "✅" if status else "❌"
        message_parts.append(f"{icon} **{component}**: {msg}")
    
    message = "\n".join(message_parts)
    
    if not all_ok:
        notify_admin.delay(text=message, category='health_check')
    
    return all_ok, message
