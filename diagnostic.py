#!/usr/bin/env python3
"""
Диагностический скрипт для выявления проблем с health_check.py
"""
import os
import sys
import asyncio
import traceback
from datetime import datetime

def print_section(title):
    print(f"\n{'='*50}")
    print(f"🔍 {title}")
    print(f"{'='*50}")

def print_check(name, status, details=""):
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name}")
    if details:
        print(f"   {details}")

async def main():
    print(f"🚀 Диагностика проекта - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Проверка импортов
    print_section("ПРОВЕРКА ИМПОРТОВ")
    
    try:
        from src.core import config
        print_check("Импорт config", True)
    except Exception as e:
        print_check("Импорт config", False, str(e))
        return
    
    try:
        import asyncpg
        print_check("Импорт asyncpg", True)
    except Exception as e:
        print_check("Импорт asyncpg", False, str(e))
    
    try:
        import redis
        print_check("Импорт redis", True)
    except Exception as e:
        print_check("Импорт redis", False, str(e))
    
    try:
        import telegram
        print_check("Импорт telegram", True)
    except Exception as e:
        print_check("Импорт telegram", False, str(e))
    
    try:
        from celery import Celery
        print_check("Импорт Celery", True)
    except Exception as e:
        print_check("Импорт Celery", False, str(e))
    
    # 2. Проверка конфигурации
    print_section("ПРОВЕРКА КОНФИГУРАЦИИ")
    
    print_check("DB_HOST", bool(config.DB_HOST), config.DB_HOST)
    print_check("DB_NAME", bool(config.DB_NAME), config.DB_NAME)
    print_check("DB_USER", bool(config.DB_USER), config.DB_USER)
    print_check("DB_PASSWORD", bool(config.DB_PASSWORD), "[СКРЫТО]" if config.DB_PASSWORD else "НЕ УСТАНОВЛЕН")
    print_check("CELERY_BROKER_URL", bool(config.CELERY_BROKER_URL), config.CELERY_BROKER_URL)
    print_check("TELEGRAM_BOT_TOKEN", bool(config.TELEGRAM_BOT_TOKEN), "[УСТАНОВЛЕН]" if config.TELEGRAM_BOT_TOKEN else "НЕ УСТАНОВЛЕН")
    
    # 3. Проверка PostgreSQL
    print_section("ПРОВЕРКА POSTGRESQL")
    
    try:
        conn = await asyncpg.connect(
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            host=config.DB_HOST,
            port=config.DB_PORT,
            timeout=5
        )
        print_check("Подключение к PostgreSQL", True)
        
        # Проверка базовой команды
        result = await conn.fetchval("SELECT 1")
        print_check("Выполнение SELECT 1", result == 1)
        
        # Проверка таблиц
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        table_names = [row['table_name'] for row in tables]
        print_check("Найдено таблиц", len(table_names) > 0, f"Таблицы: {', '.join(table_names)}")
        
        # Проверка конкретных таблиц
        required_tables = ['users', 'books', 'borrowed_books', 'book_requests']
        for table in required_tables:
            exists = table in table_names
            print_check(f"Таблица {table}", exists)
        
        await conn.close()
        
    except Exception as e:
        print_check("PostgreSQL", False, str(e))
    
    # 4. Проверка Redis
    print_section("ПРОВЕРКА REDIS")
    
    try:
        from redis import Redis
        r = Redis.from_url(config.CELERY_BROKER_URL, socket_connect_timeout=5)
        r.ping()
        print_check("Подключение к Redis", True)
        
        info = r.info()
        print_check("Redis версия", True, info.get('redis_version', 'неизвестно'))
        print_check("Подключенные клиенты", True, str(info.get('connected_clients', 0)))
        
    except Exception as e:
        print_check("Redis", False, str(e))
    
    # 5. Проверка Telegram API
    print_section("ПРОВЕРКА TELEGRAM API")
    
    bot_tokens = {
        'TELEGRAM_BOT_TOKEN': config.TELEGRAM_BOT_TOKEN,
        'ADMIN_BOT_TOKEN': config.ADMIN_BOT_TOKEN,
        'NOTIFICATION_BOT_TOKEN': config.NOTIFICATION_BOT_TOKEN,
        'ADMIN_NOTIFICATION_BOT_TOKEN': config.ADMIN_NOTIFICATION_BOT_TOKEN,
    }
    
    for token_name, token in bot_tokens.items():
        if not token:
            print_check(f"{token_name}", False, "Токен не установлен")
            continue
            
        try:
            bot = telegram.Bot(token=token)
            bot_info = await bot.get_me()
            print_check(f"{token_name}", True, f"@{bot_info.username}")
        except Exception as e:
            print_check(f"{token_name}", False, str(e)[:100])
    
    # 6. Проверка Celery
    print_section("ПРОВЕРКА CELERY")
    
    try:
        celery_app = Celery(
            broker=config.CELERY_BROKER_URL,
            backend=config.CELERY_RESULT_BACKEND
        )
        
        inspect = celery_app.control.inspect(timeout=3)
        active_workers = inspect.active()
        
        if active_workers:
            worker_count = len(active_workers)
            print_check("Celery workers", True, f"Найдено {worker_count} активных воркеров")
            for worker_name in active_workers.keys():
                print(f"   - {worker_name}")
        else:
            print_check("Celery workers", False, "Активные воркеры не найдены")
        
    except Exception as e:
        print_check("Celery", False, str(e))
    
    # 7. Запуск health_check
    print_section("ЗАПУСК HEALTH CHECK")
    
    try:
        from src.health_check import run_health_check
        all_ok, report = await run_health_check()
        print_check("Health Check", all_ok)
        print("\n📋 ПОЛНЫЙ ОТЧЕТ:")
        print(report)
        
    except Exception as e:
        print_check("Health Check", False, str(e))
        print("\n🐛 ДЕТАЛИ ОШИБКИ:")
        traceback.print_exc()
    
    print(f"\n✅ Диагностика завершена")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Диагностика прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        traceback.print_exc()