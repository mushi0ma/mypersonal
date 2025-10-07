# src/main.py
"""
Точка входа для запуска всех компонентов системы библиотеки.
"""
import logging
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from logging.handlers import RotatingFileHandler

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

handler = RotatingFileHandler('app.log', maxBytes=10485760, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def run_bot(bot_name: str, bot_module: str):
    """Запускает отдельного бота."""
    try:
        logger.info(f"🚀 Запуск {bot_name}...")
        module = __import__(f"src.{bot_module}", fromlist=['main'])
        await module.main()
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске {bot_name}: {e}", exc_info=True)

async def main():
    """Запускает все боты параллельно."""
    logger.info("🌟 Инициализация системы библиотеки...")
    
    # Запускаем всех ботов в отдельных задачах
    tasks = [
        asyncio.create_task(run_bot("Library Bot", "library_bot.main")),
        asyncio.create_task(run_bot("Admin Bot", "admin_bot.main")),
        asyncio.create_task(run_bot("Notification Bot", "notification_bot")),
        asyncio.create_task(run_bot("Audit Bot", "audit_bot")),
    ]
    
    await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Система остановлена")
        sys.exit(0)