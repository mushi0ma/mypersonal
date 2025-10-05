# notification_bot.py
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Импорты для работы с БД и задачами ---
import db_data
from db_utils import get_db_connection
import tasks # <-- ДОБАВЛЕН ИМПОРТ

# Загрузка переменных окружения и настройка
load_dotenv()
NOTIFICATION_BOT_TOKEN = os.getenv("NOTIFICATION_BOT_TOKEN")
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start, особенно 'глубокие ссылки'."""
    user = update.effective_user
    
    if context.args:
        registration_code = context.args[0]
        try:
            with get_db_connection() as conn:
                db_data.link_telegram_id_by_code(
                    conn, 
                    code=registration_code, 
                    telegram_id=user.id,
                    telegram_username=user.username
                )
            await update.message.reply_text("✅ Вы успешно подписались на уведомления! Теперь можете вернуться к основному боту.")
            logger.info(f"Пользователь {user.username} (ID: {user.id}) успешно привязал аккаунт.")
        except db_data.NotFoundError:
            await update.message.reply_text("⚠️ Код активации не найден. Пожалуйста, попробуйте снова из основного бота.")
            logger.warning(f"Пользователь {user.id} попытался активировать неверный код: {registration_code}")
        except Exception as e:
            await update.message.reply_text("❌ Произошла ошибка при привязке вашего аккаунта.")
            logger.error(f"Ошибка при привязке аккаунта для кода {registration_code}: {e}", exc_info=True)
            # --- ДОБАВЛЕНО УВЕДОМЛЕНИЕ АДМИНУ ---
            tasks.notify_admin.delay(
                text=f"❗️ **Критическая ошибка в `notification_bot`**\n\n**Функция:** `start` (привязка по коду)\n**Ошибка:** `{e}`"
            )
    else:
        await update.message.reply_text("👋 Это бот для отправки уведомлений. Чтобы привязать его к вашему аккаунту, пожалуйста, завершите регистрацию в основном боте библиотеки.")

def main() -> None:
    """Запускает бота-уведомителя."""
    application = Application.builder().token(NOTIFICATION_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Бот-уведомитель запущен.") # <-- Заменили print()
    
    application.run_polling()

if __name__ == "__main__":
    main()