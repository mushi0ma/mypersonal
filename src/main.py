"""
The main entry point for the multi-bot application.

This script initializes and runs multiple bots in separate processes using the `multiprocessing` module.
It ensures that each bot operates independently and handles graceful shutdown on KeyboardInterrupt.
"""
import asyncio
import logging
import multiprocessing

# Import the main function from each bot's module
from src.library_bot.main import main as library_main
from src.admin_bot.main import main as admin_main
from src.notification_bot import main as notification_main
from src.audit_bot import main as audit_main

# Configure basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_bot(main_func):
    """
    A wrapper function to run a bot's main async function in a new process.

    Args:
        main_func (callable): The asynchronous main function of a bot to be executed.
    """
    asyncio.run(main_func())

if __name__ == "__main__":
    # Set the start method to "spawn" for clean and isolated process startup.
    # This is crucial for preventing issues with shared resources between processes.
    multiprocessing.set_start_method("spawn", force=True)

    logger.info("🌟 Initializing the library system...")

    # A dictionary mapping bot names to their main functions for easy management.
    bots = {
        "Library Bot": library_main,
        "Admin Bot": admin_main,
        "Notification Bot": notification_main,
        "Audit Bot": audit_main,
    }

    # Create a process for each bot defined in the bots dictionary.
    processes = [
        multiprocessing.Process(target=run_bot, args=(main_func,), name=bot_name)
        for bot_name, main_func in bots.items()
    ]

    # Start each bot process.
    for process in processes:
        logger.info(f"🚀 Starting {process.name}...")
        process.start()

    try:
        # Wait for all processes to complete. This keeps the main script alive.
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        # Handle graceful shutdown when the user presses Ctrl+C.
        logger.info("⛔ Stop signal received...")
        for process in processes:
            process.terminate()  # Terminate each process
            process.join()       # Wait for the process to finish terminating
        logger.info("✅ All bots have been stopped.")
