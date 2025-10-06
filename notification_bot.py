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
            
            await update.message.reply_text(
                "✅ **Отлично!**\n\n"
                "Вы успешно подписались на уведомления библиотеки. "
                "Теперь можете вернуться к основному боту и завершить регистрацию.\n\n"
                "💡 Через этого бота вы будете получать:\n"
                "• Коды верификации\n"
                "• Напоминания о сроках возврата\n"
                "• Уведомления о новых книгах\n"
                "• И другие важные сообщения",
                parse_mode='Markdown'
            )
            logger.info(f"Пользователь {user.username} (ID: {user.id}) успешно привязал аккаунт.")
            
        except db_data.NotFoundError:
            await update.message.reply_text(
                "⚠️ **Код активации не найден.**\n\n"
                "Возможные причины:\n"
                "• Код уже был использован\n"
                "• Код устарел\n"
                "• Ошибка при копировании\n\n"
                "Пожалуйста, попробуйте начать регистрацию заново из основного бота.",
                parse_mode='Markdown'
            )
            logger.warning(f"Пользователь {user.id} попытался активировать неверный код: {registration_code}")
            
        except Exception as e:
            await update.message.reply_text(
                "❌ Произошла ошибка при привязке вашего аккаунта. "
                "Администратор уже уведомлен. Попробуйте позже."
            )
            logger.error(f"Ошибка при привязке аккаунта для кода {registration_code}: {e}", exc_info=True)
            tasks.notify_admin.delay(
                text=f"❗️ **Критическая ошибка в `notification_bot`**\n\n"
                     f"**Функция:** `start` (привязка по коду)\n"
                     f"**Код:** `{registration_code}`\n"
                     f"**User ID:** `{user.id}`\n"
                     f"**Ошибка:** `{e}`"
            )
    else:
        await update.message.reply_text(
            "👋 **Добро пожаловать!**\n\n"
            "Это бот для отправки уведомлений библиотеки.\n\n"
            "Чтобы привязать его к вашему аккаунту, пожалуйста, "
            "завершите регистрацию в основном боте библиотеки.",
            parse_mode='Markdown'
        )

def main() -> None:
    """Запускает бота-уведомителя."""
    application = Application.builder().token(NOTIFICATION_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Бот-уведомитель запущен.") # <-- Заменили print()
    
    application.run_polling()

if __name__ == "__main__":
    main()