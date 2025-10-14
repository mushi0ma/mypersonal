# src/notification_bot.py
"""
Бот-уведомитель для отправки сообщений пользователям.
Обрабатывает подписки через deep links.
"""
import asyncio
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
from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)

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
            async with get_db_connection() as conn:
                # НОВОЕ: Сначала проверяем, не привязан ли уже этот telegram_id
                existing_user = await conn.fetchrow(
                    "SELECT id, username FROM users WHERE telegram_id = $1",
                    user.id
                )
                
                if existing_user:
                    # Telegram ID уже используется
                    await update.message.reply_text(
                        "⚠️ **Этот Telegram-аккаунт уже зарегистрирован**\n\n"
                        f"Ваш аккаунт привязан к пользователю: `{existing_user['username']}`\n\n"
                        "**Что делать:**\n"
                        "• Если это ваш аккаунт — всё в порядке, используйте его\n"
                        "• Если вы хотите создать новый профиль — используйте другой Telegram\n"
                        "• Если считаете, что произошла ошибка — обратитесь к администратору\n\n"
                        "_Код регистрации не был использован._",
                        parse_mode='Markdown'
                    )
                    logger.warning(
                        f"⚠️ Попытка повторной привязки: telegram_id={user.id} "
                        f"уже принадлежит user_id={existing_user['id']} "
                        f"(username={existing_user['username']}), код={registration_code}"
                    )
                    
                    # Уведомляем админа о подозрительной активности
                    tasks.notify_admin.delay(
                        text=(
                            f"⚠️ **Попытка повторной привязки Telegram**\n\n"
                            f"**Telegram ID:** `{user.id}`\n"
                            f"**Username:** @{user.username or 'N/A'}\n"
                            f"**Уже привязан к:** `{existing_user['username']}` (ID: {existing_user['id']})\n"
                            f"**Попытка использовать код:** `{registration_code}`"
                        ),
                        category='security'
                    )
                    return
                
                # Привязываем telegram_id к аккаунту по коду
                await db_data.link_telegram_id_by_code(
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
                f"⚠️ Попытка использования неверного кода: "
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
            
            # Безопасное форматирование ошибки для Telegram
            error_msg = str(e).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[')
            tasks.notify_admin.delay(
                text=(
                    f"❗️ **Критическая ошибка в notification\\_bot**\n\n"
                    f"**User ID:** `{user.id}`\n"
                    f"**Username:** @{user.username or 'N/A'}\n"
                    f"**Код:** `{registration_code}`\n"
                    f"**Ошибка:**\n```\n{error_msg[:200]}\n```"
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

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    application = (
        Application.builder()
        .token(config.NOTIFICATION_BOT_TOKEN)
        .request(request)
        .build()
    )

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    logger.info("🔧 Notification bot сконфигурирован")
    return application

async def main() -> None:
    """
    Основная асинхронная функция для запуска бота-уведомителя.
    Используется в `src/main.py` для параллельного запуска.
    """
    logger.info("🚀 Запуск Notification Bot...")
    application = setup_notification_bot()
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await asyncio.Future()

if __name__ == "__main__":
    logger.warning(
        "⚠️ Запуск этого файла напрямую предназначен только для тестирования."
    )
    asyncio.run(main())