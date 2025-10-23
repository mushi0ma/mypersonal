# src/health_check.py
"""
Модуль health check для мониторинга состояния всех компонентов системы.
Проверяет: PostgreSQL, Redis, Telegram API, Celery workers.
"""
import os
import logging
import asyncio
from typing import Tuple, Dict, Any
from datetime import datetime

import asyncpg
from redis import Redis
import telegram
from celery import Celery

from src.core import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_database() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверяет соединение с PostgreSQL и основные метрики.
    
    Returns:
        Tuple[bool, str, Dict]: (успех, сообщение, метрики)
    """
    metrics = {}
    try:
        conn = await asyncpg.connect(
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            host=config.DB_HOST,
            port=config.DB_PORT,
            timeout=5
        )
        
        # Проверка базовой функциональности
        await conn.fetchval("SELECT 1")
        
        # Сбор метрик
        metrics['total_users'] = await conn.fetchval("SELECT COUNT(*) FROM users")
        metrics['total_books'] = await conn.fetchval("SELECT COUNT(*) FROM books")
        metrics['active_borrows'] = await conn.fetchval(
            "SELECT COUNT(*) FROM borrowed_books WHERE return_date IS NULL"
        )
        metrics['pending_requests'] = await conn.fetchval(
            "SELECT COUNT(*) FROM book_requests WHERE status = 'pending'"
        )
        
        # Проверка индексов
        index_count = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public'"
        )
        metrics['indexes'] = index_count
        
        await conn.close()
        
        return True, "PostgreSQL: OK", metrics
        
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"PostgreSQL error: {e}")
        return False, f"PostgreSQL: {str(e)[:100]}", {}
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return False, f"Database: {str(e)[:100]}", {}


def check_redis() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверяет соединение с Redis и метрики.
    
    Returns:
        Tuple[bool, str, Dict]: (успех, сообщение, метрики)
    """
    metrics = {}
    try:
        r = Redis.from_url(config.CELERY_BROKER_URL, socket_connect_timeout=5)
        
        # Проверка доступности
        r.ping()
        
        # Сбор метрик
        info = r.info()
        metrics['connected_clients'] = info.get('connected_clients', 0)
        metrics['used_memory_human'] = info.get('used_memory_human', 'N/A')
        metrics['uptime_days'] = info.get('uptime_in_days', 0)
        
        # Проверка очереди Celery
        queue_length = r.llen('celery')
        metrics['celery_queue_length'] = queue_length
        
        return True, "Redis: OK", metrics
        
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False, f"Redis: {str(e)[:100]}", {}


async def check_telegram_api() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверяет доступность Telegram API для всех ботов.
    
    Returns:
        Tuple[bool, str, Dict]: (успех, сообщение, статусы ботов)
    """
    bots_status = {}
    all_ok = True
    
    bot_tokens = {
        'library_bot': config.TELEGRAM_BOT_TOKEN,
        'admin_bot': config.ADMIN_BOT_TOKEN,
        'notification_bot': config.NOTIFICATION_BOT_TOKEN,
        'audit_bot': config.ADMIN_NOTIFICATION_BOT_TOKEN,
    }
    
    for bot_name, token in bot_tokens.items():
        try:
            bot = telegram.Bot(token=token)
            bot_info = await bot.get_me()
            bots_status[bot_name] = {
                'status': 'OK',
                'username': bot_info.username,
                'can_read_all_group_messages': bot_info.can_read_all_group_messages
            }
        except telegram.error.TimedOut:
            all_ok = False
            bots_status[bot_name] = {'status': 'TIMEOUT'}
            logger.warning(f"Telegram API timeout for {bot_name}")
        except telegram.error.NetworkError as e:
            all_ok = False
            bots_status[bot_name] = {'status': 'NETWORK_ERROR', 'error': str(e)[:50]}
            logger.error(f"Telegram network error for {bot_name}: {e}")
        except Exception as e:
            all_ok = False
            bots_status[bot_name] = {'status': 'ERROR', 'error': str(e)[:50]}
            logger.error(f"Telegram API check failed for {bot_name}: {e}")
    
    message = "Telegram API: OK" if all_ok else "Telegram API: PARTIAL"
    return all_ok, message, bots_status


def check_celery_workers() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверяет состояние Celery workers.
    
    Returns:
        Tuple[bool, str, Dict]: (успех, сообщение, статус workers)
    """
    metrics = {}
    try:
        celery_app = Celery(
            broker=config.CELERY_BROKER_URL,
            backend=config.CELERY_RESULT_BACKEND
        )
        
        # Получаем статистику воркеров
        inspect = celery_app.control.inspect(timeout=3)
        
        # Проверяем активные воркеры
        active_workers = inspect.active()
        if active_workers:
            metrics['active_workers'] = list(active_workers.keys())
            metrics['worker_count'] = len(active_workers)
            
            # Считаем активные задачи
            total_tasks = sum(len(tasks) for tasks in active_workers.values())
            metrics['active_tasks'] = total_tasks
        else:
            metrics['active_workers'] = []
            metrics['worker_count'] = 0
            metrics['active_tasks'] = 0
        
        # Проверяем зарегистрированные задачи
        registered = inspect.registered()
        if registered:
            all_tasks = set()
            for worker_tasks in registered.values():
                all_tasks.update(worker_tasks)
            metrics['registered_tasks'] = list(all_tasks)
        
        if metrics.get('worker_count', 0) == 0:
            return False, "Celery: NO WORKERS", metrics
        
        return True, "Celery: OK", metrics
        
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return False, f"Celery: {str(e)[:100]}", {}


async def check_disk_space() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Проверяет доступное место на диске.
    
    Returns:
        Tuple[bool, str, Dict]: (успех, сообщение, метрики диска)
    """
    import shutil
    
    metrics = {}
    try:
        # Проверяем корневой раздел
        total, used, free = shutil.disk_usage("/")
        
        metrics['total_gb'] = round(total / (1024**3), 2)
        metrics['used_gb'] = round(used / (1024**3), 2)
        metrics['free_gb'] = round(free / (1024**3), 2)
        metrics['used_percent'] = round((used / total) * 100, 1)
        
        # Предупреждение если свободного места < 10%
        if metrics['used_percent'] > 90:
            return False, f"Disk: LOW SPACE ({metrics['free_gb']}GB free)", metrics
        
        return True, "Disk: OK", metrics
        
    except Exception as e:
        logger.error(f"Disk space check failed: {e}")
        return False, f"Disk: {str(e)[:100]}", {}


async def run_health_check() -> Tuple[bool, str]:
    """
    Запускает все проверки здоровья системы.
    
    Returns:
        Tuple[bool, str]: (все_ок, детальный_отчет)
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    report_lines = [
        "=" * 60,
        f"🏥 HEALTH CHECK REPORT - {timestamp}",
        "=" * 60,
        ""
    ]
    
    all_checks_passed = True
    
    # 1. PostgreSQL
    db_ok, db_msg, db_metrics = await check_database()
    report_lines.append(f"📊 {db_msg}")
    if db_metrics:
        report_lines.append(f"   Users: {db_metrics.get('total_users', 0)}")
        report_lines.append(f"   Books: {db_metrics.get('total_books', 0)}")
        report_lines.append(f"   Active borrows: {db_metrics.get('active_borrows', 0)}")
        report_lines.append(f"   Pending requests: {db_metrics.get('pending_requests', 0)}")
    report_lines.append("")
    all_checks_passed &= db_ok
    
    # 2. Redis
    redis_ok, redis_msg, redis_metrics = check_redis()
    report_lines.append(f"💾 {redis_msg}")
    if redis_metrics:
        report_lines.append(f"   Connected clients: {redis_metrics.get('connected_clients', 0)}")
        report_lines.append(f"   Memory: {redis_metrics.get('used_memory_human', 'N/A')}")
        report_lines.append(f"   Queue length: {redis_metrics.get('celery_queue_length', 0)}")
    report_lines.append("")
    all_checks_passed &= redis_ok
    
    # 3. Telegram API
    tg_ok, tg_msg, tg_status = await check_telegram_api()
    report_lines.append(f"📱 {tg_msg}")
    for bot_name, status in tg_status.items():
        status_symbol = "✅" if status.get('status') == 'OK' else "❌"
        username = status.get('username', 'N/A')
        report_lines.append(f"   {status_symbol} {bot_name}: @{username}")
    report_lines.append("")
    all_checks_passed &= tg_ok
    
    # 4. Celery Workers
    celery_ok, celery_msg, celery_metrics = check_celery_workers()
    report_lines.append(f"⚙️  {celery_msg}")
    if celery_metrics:
        report_lines.append(f"   Active workers: {celery_metrics.get('worker_count', 0)}")
        report_lines.append(f"   Active tasks: {celery_metrics.get('active_tasks', 0)}")
    report_lines.append("")
    all_checks_passed &= celery_ok
    
    # 5. Disk Space
    disk_ok, disk_msg, disk_metrics = await check_disk_space()
    report_lines.append(f"💿 {disk_msg}")
    if disk_metrics:
        report_lines.append(f"   Used: {disk_metrics.get('used_gb', 0)} GB / {disk_metrics.get('total_gb', 0)} GB")
        report_lines.append(f"   Free: {disk_metrics.get('free_gb', 0)} GB ({100 - disk_metrics.get('used_percent', 0):.1f}%)")
    report_lines.append("")
    all_checks_passed &= disk_ok
    
    # Итог
    report_lines.append("=" * 60)
    status_emoji = "✅" if all_checks_passed else "❌"
    status_text = "ALL SYSTEMS OPERATIONAL" if all_checks_passed else "ISSUES DETECTED"
    report_lines.append(f"{status_emoji} STATUS: {status_text}")
    report_lines.append("=" * 60)
    
    full_report = "\n".join(report_lines)
    
    if all_checks_passed:
        logger.info("✅ Health check passed")
    else:
        logger.warning(f"⚠️ Health check failed:\n{full_report}")
    
    return all_checks_passed, full_report


if __name__ == '__main__':
    """
    Запуск health check из командной строки.
    """
    from dotenv import load_dotenv
    load_dotenv()

    all_ok, report = asyncio.run(run_health_check())
    print(report)
    
    # Exit code для CI/CD
    exit(0 if all_ok else 1)