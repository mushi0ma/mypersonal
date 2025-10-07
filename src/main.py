# src/main.py
"""
Точка входа для запуска всех компонентов системы библиотеки.
Централизованное управление жизненным циклом приложения.
"""
import logging
import asyncio
from logging.handlers import RotatingFileHandler
import signal
import sys

from telegram.ext import Application

# Убедитесь, что этот файл существует и настроен
from src.core import config

# !!! ВНИМАНИЕ: Эти импорты пока будут вызывать ошибку, мы это исправим на следующем шаге
from src.library_bot.main import setup_library_bot
from src.admin_bot.main import setup_admin_bot
from src.notification_bot import setup_notification_bot
from src.audit_bot import setup_audit_bot
# from src.core.db.utils import close_db_pool # Закомментируем пока нет пула соединений

# --- Настройка логирования ---
def setup_logging():
    """Централизованная настройка логирования для всего приложения."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        format=log_format,
        level=logging.INFO,
        handlers=[
            RotatingFileHandler(
                config.LOG_DIR / 'app.log', # Используем путь из конфига
                maxBytes=10485760,  # 10MB
                backupCount=5
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Устанавливаем более высокий уровень логирования для шумных библиотек
    for component in ['telegram', 'httpx']:
        logging.getLogger(component).setLevel(logging.WARNING)
        
    return logging.getLogger(__name__)

logger = setup_logging()

# --- Класс Оркестратора ---
class BotOrchestrator:
    """Оркестратор для управления жизненным циклом всех ботов."""
    def __init__(self):
        self.applications: dict[str, Application] = {}
        self.running_tasks = []
        self._shutdown_event = asyncio.Event()

    def register_bot(self, name: str, app: Application):
        """Регистрирует бота для управления."""
        self.applications[name] = app
        logger.info(f"✅ Бот '{name}' зарегистрирован")

    async def start_all(self):
        """Запускает все зарегистрированные боты."""
        if not self.applications:
            logger.error("❌ Нет зарегистрированных ботов!")
            return
            
        logger.info(f"🚀 Запуск {len(self.applications)} ботов...")
        
        for name, app in self.applications.items():
            task = asyncio.create_task(self._run_bot(name, app))
            self.running_tasks.append(task)
            
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks)

    async def _run_bot(self, name: str, app: Application):
        """Внутренний метод для запуска и управления одним ботом."""
        try:
            await app.initialize()
            await app.start()
            logger.info(f"✅ {name} запущен успешно")
            
            if app.updater:
                await app.updater.start_polling(drop_pending_updates=True)
            
            await self._shutdown_event.wait() # Ожидаем сигнала на остановку
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в {name}: {e}", exc_info=True)
            await self.stop_all() # Остановить всех при падении одного
        finally:
            await self._cleanup_bot(name, app)

    async def _cleanup_bot(self, name: str, app: Application):
        """Корректно останавливает бота."""
        try:
            logger.info(f"🛑 Остановка {name}...")
            if app.updater and app.updater.running:
                await app.updater.stop()
            if app.running:
                await app.stop()
            await app.shutdown()
            logger.info(f"✅ {name} остановлен")
        except Exception as e:
            logger.error(f"⚠️  Ошибка при остановке {name}: {e}")

    async def stop_all(self):
        """Инициирует остановку всех ботов."""
        if not self._shutdown_event.is_set():
            logger.info("🛑 Инициирована остановка всех ботов...")
            self._shutdown_event.set()

# --- Главная функция ---
async def main():
    """Главная асинхронная функция запуска приложения."""
    logger.info("=" * 50)
    logger.info("📚 ЗАПУСК СИСТЕМЫ УПРАВЛЕНИЯ БИБЛИОТЕКОЙ")
    logger.info("=" * 50)
    
    try:
        config.validate_config()
    except config.ConfigError as e:
        logger.critical(str(e))
        sys.exit(1)

    orchestrator = BotOrchestrator()
    
    # Настройка graceful shutdown
    loop = asyncio.get_running_loop()
    stop_task = lambda: asyncio.create_task(orchestrator.stop_all())
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_task)

    try:
        # Регистрируем всех ботов
        orchestrator.register_bot("library", setup_library_bot())
        orchestrator.register_bot("admin", setup_admin_bot())
        orchestrator.register_bot("notifier", setup_notification_bot())
        orchestrator.register_bot("auditor", setup_audit_bot())
        
        await orchestrator.start_all()
        
    except Exception as e:
        logger.critical(f"❌ Необработанная ошибка в main: {e}", exc_info=True)
    finally:
        # await close_db_pool() # Раскомментируем, когда будет пул
        logger.info("👋 Система остановлена.")

# --- Точка входа в скрипт ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершение работы по команде пользователя.")