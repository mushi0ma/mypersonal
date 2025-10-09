import asyncio
import logging
from multiprocessing import Process

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_library_bot():
    """Запуск Library Bot в отдельном процессе"""
    from src.library_bot.main import main
    import asyncio
    asyncio.run(main())

def run_admin_bot():
    """Запуск Admin Bot в отдельном процессе"""
    from src.admin_bot.main import main
    import asyncio
    asyncio.run(main())

def run_notification_bot():
    """Запуск Notification Bot в отдельном процессе"""
    from src.notification_bot import main
    import asyncio
    asyncio.run(main())

def run_audit_bot():
    """Запуск Audit Bot в отдельном процессе"""
    from src.audit_bot import main
    import asyncio
    asyncio.run(main())

if __name__ == "__main__":
    logger.info("🌟 Инициализация системы библиотеки...")
    
    # Создаём процессы для каждого бота
    processes = [
        Process(target=run_library_bot, name="Library Bot"),
        Process(target=run_admin_bot, name="Admin Bot"),
        Process(target=run_notification_bot, name="Notification Bot"),
        Process(target=run_audit_bot, name="Audit Bot"),
    ]
    
    # Запускаем все процессы
    for process in processes:
        logger.info(f"🚀 Запуск {process.name}...")
        process.start()
    
    # Ждём завершения всех процессов
    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        logger.info("⛔ Получен сигнал остановки...")
        for process in processes:
            process.terminate()
            process.join()
        logger.info("✅ Все боты остановлены")