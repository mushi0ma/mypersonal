# src/main.py
import logging
import asyncio
import os
from logging.handlers import RotatingFileHandler

from src.core import config
from src.library_bot.main import main as library_main
from src.admin_bot.main import main as admin_main
from src.notification_bot import main as notification_main
from src.audit_bot import main as audit_main

# Создаем директорию для логов, если ее нет
os.makedirs('logs', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def run_bot(name: str, bot_main_func):
    """Запускает бота в отдельной задаче"""
    try:
        logger.info(f"Запуск бота: {name}")
        # Запускаем синхронную функцию main бота в отдельном потоке,
        # чтобы не блокировать основной асинхронный цикл.
        await asyncio.to_thread(bot_main_func)
    except Exception as e:
        logger.error(f"Ошибка в боте {name}: {e}", exc_info=True)

async def main():
    """Запускает все боты параллельно"""
    logger.info("=" * 60)
    logger.info("Запуск системы управления библиотекой")
    logger.info("=" * 60)

    # Валидация конфигурации
    try:
        config.validate_config()
        logger.info("✓ Конфигурация валидна")
    except ValueError as e:
        logger.critical(f"✗ Ошибка конфигурации: {e}")
        return

    # Запускаем всех ботов параллельно
    tasks = [
        asyncio.create_task(run_bot("Library Bot", library_main)),
        asyncio.create_task(run_bot("Admin Bot", admin_main)),
        asyncio.create_task(run_bot("Notification Bot", notification_main)),
        asyncio.create_task(run_bot("Audit Bot", audit_main)),
    ]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("\nПолучен сигнал остановки...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass