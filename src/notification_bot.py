# src/notification_bot.py
"""
Бот-уведомитель для отправки сообщений пользователям.
Обрабатывает подписки через deep links.
"""

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from src.core import config
from src.core.db import data_access as db_data
from src.core.db.utils import get_db_connection
from src.core import tasks

logger = logging.getLogger(name)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    """
    Обрабатывает команду /start с deep link для привязки аккаунта.
    Deep link формат: /start <registration_code>
    """

    user = update.effective_user

    # Проверяем наличие кода регистрации в аргументах
    if context.args:
        registration_code = context.args[0]
        
        try:
            with get_db_connection() as conn:
                # Привязываем telegram_id к аккаунту по коду
                db_data.link_telegram_id_by_code(
                    conn,
                    code=registration_code,
                    telegram_id=user.id,
                    telegram_username=user.username
                )
            
            await update.message.reply_text(
                "✅ **Отлично!**\n\n"
                "Вы успешно подписались на уведомления библиотеки.\n\n"
                "💡 **Что вы будете получать:**\n"
                "• 🔐 Коды верификации\n"
                "• ⏰ Напоминания о сроках возврата\n"
                "• 📚 Уведомления о новых книгах\n"
                "• 🎯 Персональные рекомендации\n\n"
                "_Теперь можете вернуться к основному боту._",
                parse_mode='Markdown'
            )
            
            logger.info(
                f"✅ Успешная привязка: user_id={user.id}, "
                f"username=@{user.username}, code={registration_code}"
            )
            
        except db_data.NotFoundError:
            await update.message.reply_text(
                "⚠️ **Код активации не найден.**\n\n"
                "**Возможные причины:**\n"
                "• Код уже был использован\n"
                "• Код устарел\n"
                "• Ошибка при копировании\n\n"
                "Попробуйте начать регистрацию заново из основного бота.",
                parse_mode='Markdown'
            )
            logger.warning(
                f"⚠️  Попытка использования неверного кода: "
                f"user_id={user.id}, code={registration_code}"
            )
            
        except Exception as e:
            await update.message.reply_text(
                "❌ Произошла ошибка при привязке аккаунта. "
                "Администратор уже уведомлён. Попробуйте позже."
            )
            logger.error(
                f"❌ Ошибка привязки: user_id={user.id}, code={registration_code}",
                exc_info=True
            )
            tasks.notify_admin.delay(
                text=(
                    f"❗️ **Критическая ошибка в notification_bot**\n\n"
                    f"**User ID:** `{user.id}`\n"
                    f"**Username:** @{user.username or 'N/A'}\n"
                    f"**Код:** `{registration_code}`\n"
                    f"**Ошибка:** `{e}`"
                ),
                category='error'
            )
    else:
        # Приветственное сообщение без кода
        await update.message.reply_text(
            "👋 **Добро пожаловать!**\n\n"
            "Это бот для отправки уведомлений библиотеки.\n\n"
            "Чтобы привязать его к вашему аккаунту, "
            "завершите регистрацию в основном боте библиотеки.",
            parse_mode='Markdown'
        )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку по боту."""
    await update.message.reply_text(
        "ℹ️ Справка\n\n"
        "Этот бот используется для отправки уведомлений.\n\n"
        "Как подписаться:\n"
        "1. Зарегистрируйтесь в основном боте\n"
        "2. Нажмите на ссылку активации\n"
        "3. Всё готово!\n\n"
        "Для управления уведомлениями используйте основного бота.", parse_mode='Markdown')

def setup_notification_bot() -> Application:
    """
    Настраивает и возвращает приложение бота-уведомителя.
    Returns:
        Application: Сконфигурированное приложение Telegram бота
    """
    application = Application.builder().token(config.NOTIFICATION_BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    logger.info("🔧 Notification bot сконфигурирован")
    return application

def main() -> None:
    """Legacy точка входа для прямого запуска."""
    logger.warning(
    "⚠️  Прямой запуск notification_bot.py устарел. "
    "Используйте src/main.py для запуска всех ботов."
    )
    application = setup_notification_bot()
    application.run_polling()

if __name__ == "main":
    main()
