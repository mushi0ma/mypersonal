import asyncio
import logging
import multiprocessing

# Импортируем main-функции каждого бота один раз
from src.library_bot.main import main as library_main
from src.admin_bot.main import main as admin_main
from src.notification_bot import main as notification_main
from src.audit_bot import main as audit_main

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_bot(main_func):
    """Универсальная функция-обертка для запуска бота в новом процессе."""
    asyncio.run(main_func())

if __name__ == "__main__":
    # Устанавливаем метод старта "spawn" для чистого и изолированного запуска процессов
    multiprocessing.set_start_method("spawn", force=True)

    logger.info("🌟 Инициализация системы библиотеки...")

    bots = {
        "Library Bot": library_main,
        "Admin Bot": admin_main,
        "Notification Bot": notification_main,
        "Audit Bot": audit_main,
    }

    processes = [
        multiprocessing.Process(target=run_bot, args=(main_func,), name=bot_name)
        for bot_name, main_func in bots.items()
    ]

    for process in processes:
        logger.info(f"🚀 Запуск {process.name}...")
        process.start()

    try:
        # Ожидаем завершения всех процессов
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        logger.info("⛔ Получен сигнал остановки...")
        for process in processes:
            process.terminate()
            process.join()
        logger.info("✅ Все боты остановлены")