# -*- coding: utf-8 -*-
# librarybot.py - REVISED FOR BUTTON-ONLY NAVIGATION
import logging
import os
import random
import re
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- ИМПОРТ ФУНКЦИЙ БАЗЫ ДАННЫХ И ХЕШИРОВАНИЯ ---
import db_data
from db_setup import hash_password
from tasks import send_telegram_message

# --- ИМПОРТ СЕРВИСОВ И PYWHATKIT ---
# import pywhatkit as kit
from twilio.rest import Client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Загрузка конфигурации из .env ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

# Учетные данные Twilio/SendGrid
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")
try:
    twilio_client = Client(account_sid, auth_token)
except Exception:
    logger.warning("Twilio client init failed. SMS verification might be disabled.")
    twilio_client = None

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")

# --- СОСТОЯНИЯ ДИАЛОГА ---
(
    START_ROUTES,
    REGISTER_NAME, REGISTER_DOB, REGISTER_CONTACT, REGISTER_VERIFY_CODE, REGISTER_STATUS, REGISTER_USERNAME, REGISTER_PASSWORD,
    LOGIN_CONTACT, LOGIN_PASSWORD,
    FORGOT_PASSWORD_CONTACT, FORGOT_PASSWORD_VERIFY_CODE, FORGOT_PASSWORD_SET_NEW,
    # Новые состояния для пользовательского меню
    USER_MENU, USER_BORROW_BOOK_NAME, USER_RETURN_BOOK, USER_RATE_BOOK_SELECT, USER_RATE_BOOK_RATING,
    # Новое состояние для резервации
    USER_RESERVE_BOOK_CONFIRM,
    # Новое состояние для истории
    USER_VIEW_HISTORY
) = range(20)


# --------------------------
# --- Вспомогательные функции верификации ---
# --------------------------

def normalize_phone_number(contact: str) -> str:
    """Нормализует российский/казахстанский номер в формат E.164 (+7XXXXXXXXXX)."""
    clean_digits = re.sub(r'\D', '', contact)

    if clean_digits.startswith('8') and len(clean_digits) == 11:
        return '+7' + clean_digits[1:]
    if clean_digits.startswith('7') and len(clean_digits) == 11:
        return '+' + clean_digits
    if re.match(r"^\+\d{1,14}$", contact):
        return contact

    return contact


def send_whatsapp_code(contact: str, code: str):
    """
    ОТПРАВЛЯЕТ код через pywhatkit (WhatsApp).
    ТРЕБУЕТ: Установленного WhatsApp Desktop и активной сессии.
    """
    # Эта функция временно отключена, так как pywhatkit не работает в Docker.
    logger.warning("Попытка отправки через WhatsApp/pywhatkit (отключено в Docker).")
    return False


async def send_local_code_telegram(code: str, context: ContextTypes.DEFAULT_TYPE, telegram_id: int) -> bool:
    """Отправляет локально сгенерированный код в Telegram."""
    try:
        message_body = f"Ваш код для библиотеки: {code}"
        await context.bot.send_message(chat_id=telegram_id, text=message_body)
        context.user_data['verification_method'] = 'telegram'
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке в Telegram пользователю {telegram_id}: {e}")
        return False


async def send_verification_message(contact_info: str, code: str, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    """
    Отправляет код верификации: Email (SendGrid), Телефон (Pywhatkit), Telegram (Fallback).
    """

    # 1. Проверка на email (SendGrid)
    if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", contact_info):
        if not SENDGRID_API_KEY:
            logger.error("API ключ для SendGrid не настроен. Email верификация невозможна.")
            return False
        try:
            message_body = f"Ваш код для библиотеки: {code}"
            message = Mail(
                from_email=FROM_EMAIL, to_emails=contact_info,
                subject='Код верификации для библиотеки',
                html_content=f'<strong>{message_body}</strong>'
            )
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            sg.send(message)
            context.user_data['verification_method'] = 'email'
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке email: {e}")
            return False

    # 2. Проверка на номер телефона (Pywhatkit)
    if re.match(r"^\+\d{1,14}$", contact_info):
        if send_whatsapp_code(contact_info, code):
            context.user_data['verification_method'] = 'pywhatkit'
            return True
        return False

    # 3. Fallback: Telegram (для username/ID)
    return await send_local_code_telegram(code, context, telegram_id)

# --------------------------
# --- Обработчики диалогов ---
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает приветственное сообщение и кнопки действий."""
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("Войти", callback_data="login")],
        [InlineKeyboardButton("Зарегистрироваться", callback_data="register")],
        [InlineKeyboardButton("Отмена", callback_data="cancel_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    chat_id = update.effective_chat.id

    if update.callback_query:
        await update.callback_query.edit_message_text("Добро пожаловать в библиотеку! 📚", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text="Добро пожаловать в библиотеку! 📚", reply_markup=reply_markup)

    return START_ROUTES

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог и возвращается в начальное меню."""
    text = "Действие отменено."
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(text)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text)

    return await start(update, context)

def get_back_button(current_state_const: int) -> list:
    """Генерирует кнопку 'Отмена', используя имя константы состояния."""
    state_name = [name for name, val in globals().items() if val == current_state_const and name.isupper() and '_' in name][0]
    # Используем 'Назад', чтобы явно показать, что это возврат
    return [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_{state_name}")]

# --- Функции Регистрации ---

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс регистрации / re-asks name."""
    # Если это первый вход, чистим данные
    if update.callback_query and update.callback_query.data == 'register':
        query = update.callback_query
        await query.answer()
        context.user_data.clear()
        context.user_data['registration'] = {}
        target_update = query
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        target_update = query
    else:
        target_update = update.message

    reply_markup = InlineKeyboardMarkup([get_back_button(START_ROUTES)])

    if isinstance(target_update, Update):
        await target_update.effective_message.edit_text("Введите ваше **ФИО** (полностью, например: Иванов Иван Иванович):", reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await target_update.edit_message_text("Введите ваше **ФИО** (полностью, например: Иванов Иван Иванович):", reply_markup=reply_markup, parse_mode='Markdown')

    return REGISTER_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает ФИО пользователя."""
    context.user_data['registration']['full_name'] = update.message.text
    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_NAME)])
    await update.message.reply_text("Введите **дату рождения** (ДД.ММ.ГГГГ):", reply_markup=reply_markup, parse_mode='Markdown')
    return REGISTER_DOB


async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и проверяет дату рождения."""
    dob = update.message.text
    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", dob):
        await update.message.reply_text("Неверный формат. Используйте формат **ДД.ММ.ГГГГ**.")
        return REGISTER_DOB

    context.user_data['registration']['dob'] = dob
    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_DOB)])
    await update.message.reply_text("Введите ваш **контакт** (email, телефон в формате +7... или username):", reply_markup=reply_markup, parse_mode='Markdown')
    return REGISTER_CONTACT


async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает контактную информацию, нормализует телефонный номер и отправляет код."""
    contact_input = update.message.text
    user_id = update.effective_user.id

    # Нормализация
    contact_processed = normalize_phone_number(contact_input)

    # Проверка на существование
    try:
        if db_data.get_user_by_login(contact_processed):
            await update.message.reply_text("Пользователь с такими данными уже существует. Попробуйте войти или введите другой контакт.")
            return REGISTER_CONTACT
    except db_data.NotFoundError:
        pass # Пользователь не найден, всё хорошо, продолжаем регистрацию

    context.user_data['registration']['contact_info'] = contact_processed

    code = str(random.randint(100000, 999999))
    context.user_data['verification_code'] = code

    sent = await send_verification_message(contact_processed, code, context, user_id)

    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_CONTACT)])
    if sent:
        await update.message.reply_text(f"На указанный вами контакт ({contact_processed}) отправлен **код верификации**. Пожалуйста, введите его:", reply_markup=reply_markup, parse_mode='Markdown')
        return REGISTER_VERIFY_CODE
    else:
        await update.message.reply_text(
            "Не удалось отправить код. Проверьте правильность введенных данных или попробуйте другой способ (email, username).",
            reply_markup=reply_markup
        )
        return REGISTER_CONTACT


async def verify_registration_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет код верификации."""
    input_code = update.message.text
    is_verified = False

    if input_code == context.user_data.get('verification_code'):
        is_verified = True

    if is_verified:
        keyboard = [
            [InlineKeyboardButton("Студент", callback_data="студент"), InlineKeyboardButton("Преподаватель", callback_data="учитель")],
            get_back_button(REGISTER_VERIFY_CODE)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Код верный! Теперь выберите ваш статус:", reply_markup=reply_markup)

        context.user_data.pop('verification_code', None)
        context.user_data.pop('verification_method', None)

        return REGISTER_STATUS
    else:
        await update.message.reply_text("Неверный код. Попробуйте еще раз.")
        return REGISTER_VERIFY_CODE


async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает статус и просит ввести юзернейм."""
    query = update.callback_query
    await query.answer()
    context.user_data['registration']['status'] = query.data

    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_STATUS)])
    await query.edit_message_text(
        "Придумайте **юзернейм** (на английском, без пробелов, например: `ivanov21`):",
        reply_markup=reply_markup, parse_mode='Markdown'
    )
    return REGISTER_USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает и валидирует юзернейм, затем запрашивает пароль."""
    username = update.message.text
    # Простая проверка на английские буквы, цифры и _
    if not re.match(r"^[a-zA-Z0-9_]{3,}$", username):
        await update.message.reply_text(
            "❌ Неверный формат. Юзернейм должен быть не короче 3 символов и состоять из английских букв, цифр и знака '_'. Попробуйте снова."
        )
        return REGISTER_USERNAME

    context.user_data['registration']['username'] = username
    reply_markup = InlineKeyboardMarkup([get_back_button(REGISTER_USERNAME)])
    await update.message.reply_text("Создайте **пароль** для входа (минимум 8 символов):", reply_markup=reply_markup, parse_mode='Markdown')
    return REGISTER_PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает пароль и завершает регистрацию."""
    new_password = update.message.text

    if not re.match(r"^(?=.*[A-Za-z])(?=.*\d|.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$", new_password):
        await update.message.reply_text("❌ Пароль должен содержать минимум 8 символов, включая буквы и хотя бы одну цифру или спецсимвол. Попробуйте снова.")
        return REGISTER_PASSWORD

    user_info = update.message.from_user
    context.user_data['registration']['password'] = new_password
    context.user_data['registration']['telegram_id'] = user_info.id
    context.user_data['registration']['telegram_username'] = user_info.username if user_info.username else None

    try:
        user_id = db_data.add_user(context.user_data['registration'])
        await update.message.reply_text("✅ Регистрация успешно завершена! Теперь вы можете войти, используя /start.")
    except db_data.UserExistsError:
         await update.message.reply_text("❌ Ошибка при регистрации. Возможно, имя пользователя/контакт уже заняты.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при регистрации: {e}")
        await update.message.reply_text("❌ Произошла системная ошибка при регистрации.")

    context.user_data.clear()
    return await start(update, context)


# --- Функции Входа ---

async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс входа / re-asks contact."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Забыли пароль?", callback_data="forgot_password")],
        get_back_button(START_ROUTES)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Введите ваш **контакт** (email, телефон, username) для входа:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return LOGIN_CONTACT

async def get_login_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает контакт для входа, нормализует его и проверяет пользователя."""
    contact_input = update.message.text
    contact_processed = normalize_phone_number(contact_input)

    try:
        user = db_data.get_user_by_login(contact_processed)
        context.user_data['login_user'] = user
        keyboard = [get_back_button(LOGIN_CONTACT)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Введите ваш **пароль**:", reply_markup=reply_markup, parse_mode='Markdown')
        return LOGIN_PASSWORD
    except db_data.NotFoundError:
        await update.message.reply_text("Пользователь не найден. Попробуйте еще раз или /start для регистрации.")
        return LOGIN_CONTACT


async def check_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет пароль пользователя."""
    user = context.user_data['login_user']
    stored_hash = user['password_hash']
    full_name = user['full_name']
    input_password = update.message.text

    if hash_password(input_password) == stored_hash:
        await update.message.reply_text(f"🎉 Добро пожаловать, {full_name}!")
        context.user_data['current_user'] = user
        context.user_data.pop('login_user')
        return await user_menu(update, context)
    else:
        await update.message.reply_text("Неверный пароль. Попробуйте снова.")
        return LOGIN_PASSWORD


# --- Функции Восстановления Пароля ---

async def start_forgot_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс восстановления пароля / re-asks contact."""
    query = update.callback_query
    await query.answer()

    keyboard = [get_back_button(LOGIN_CONTACT)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Введите ваш **контакт** (email, телефон, username) для сброса пароля:", reply_markup=reply_markup, parse_mode='Markdown')
    return FORGOT_PASSWORD_CONTACT


async def get_forgot_password_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Находит пользователя, нормализует контакт и отправляет КОД верификации (Шаг 1)."""
    contact_input = update.message.text
    user_id = update.effective_user.id
    contact_processed = normalize_phone_number(contact_input)

    try:
        user = db_data.get_user_by_login(contact_processed)
    except db_data.NotFoundError:
        await update.message.reply_text("Пользователь с такими данными не найден. Нажмите 'Назад' чтобы попробовать снова.")
        return FORGOT_PASSWORD_CONTACT

    contact_to_verify = user['contact_info']
    user_telegram_id = user['telegram_id'] if user['telegram_id'] else user_id

    code = str(random.randint(100000, 999999))
    context.user_data['forgot_password_code'] = code
    context.user_data['forgot_password_contact'] = contact_to_verify

    sent = await send_verification_message(contact_to_verify, code, context, user_telegram_id)

    keyboard = [get_back_button(FORGOT_PASSWORD_CONTACT)]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if sent:
        await update.message.reply_text(f"Код верификации для сброса пароля отправлен на ваш контакт ({contact_to_verify}). Введите его:", reply_markup=reply_markup)
        return FORGOT_PASSWORD_VERIFY_CODE
    else:
        await update.message.reply_text("Не удалось отправить код верификации. Нажмите 'Назад' и попробуйте другой контакт.")
        return FORGOT_PASSWORD_CONTACT


async def verify_forgot_password_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет код для сброса пароля (Шаг 2)."""
    input_code = update.message.text

    if input_code == context.user_data.get('forgot_password_code'):
        keyboard = [get_back_button(FORGOT_PASSWORD_VERIFY_CODE)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Код верный! Введите **новый пароль** (минимум 8 символов, буквы и цифры/спецсимволы):", reply_markup=reply_markup, parse_mode='Markdown')
        context.user_data.pop('forgot_password_code', None)
        return FORGOT_PASSWORD_SET_NEW
    else:
        await update.message.reply_text("Неверный код. Попробуйте еще раз.")
        return FORGOT_PASSWORD_VERIFY_CODE

async def set_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет пароль в БД (Шаг 3)."""
    new_password = update.message.text

    if not re.match(r"^(?=.*[A-Za-z])(?=.*\d|.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$", new_password):
        await update.message.reply_text("❌ Новый пароль должен содержать минимум 8 символов, включая буквы и хотя бы одну цифру или спецсимвол.")
        return FORGOT_PASSWORD_SET_NEW

    login_query = context.user_data['forgot_password_contact']

    try:
        db_data.update_user_password(login_query, new_password)
        await update.message.reply_text("🎉 Пароль успешно обновлен! Теперь вы можете войти, используя /start.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении пароля через db_data: {e}")
        await update.message.reply_text(f"❌ Ошибка при обновлении пароля. Нажмите 'Назад', чтобы попробовать ввести его снова.")
        return FORGOT_PASSWORD_SET_NEW

    context.user_data.clear()
    return await start(update, context)


# --- Функции Пользовательского Меню ---

def get_user_borrow_limit(status):
    """Возвращает лимит на заимствование."""
    return {'студент': 3, 'учитель': 5}.get(status.lower(), 0)

async def user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает главное меню пользователя."""
    user = context.user_data.get('current_user')

    if not user:
        return await start(update, context)

    borrowed_books = db_data.get_borrowed_books(user['id'])
    borrow_limit = get_user_borrow_limit(user['status'])

    message_text = (
        f"**Личный кабинет: {user['full_name']} ({user['status'].capitalize()})**\n"
        f"📚 Взято книг: {len(borrowed_books)}/{borrow_limit}"
    )

    keyboard = [
        [InlineKeyboardButton("Взять книгу", callback_data="user_borrow"), InlineKeyboardButton("Вернуть книгу", callback_data="user_return")],
        [InlineKeyboardButton("Оценить книгу", callback_data="user_rate"), InlineKeyboardButton("Профиль", callback_data="user_profile")],
        [InlineKeyboardButton("История", callback_data="user_history"), InlineKeyboardButton("Выйти", callback_data="logout")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

    return USER_MENU

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выход из аккаунта."""
    query = update.callback_query
    await query.answer()

    user = context.user_data.get('current_user')
    borrowed_books = db_data.get_borrowed_books(user['id'])

    if borrowed_books:
        keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Вы не можете выйти, пока не вернете все взятые книги!", reply_markup=reply_markup)
        return USER_MENU
    else:
        context.user_data.clear()
        await query.edit_message_text("Вы успешно вышли из аккаунта. Введите /start для входа.")
        return START_ROUTES

# --- Функции Взятия/Возврата/Оценки ---

async def start_borrow_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс взятия книги."""
    query = update.callback_query
    await query.answer()

    user = context.user_data.get('current_user')
    borrowed_books = db_data.get_borrowed_books(user['id'])
    borrow_limit = get_user_borrow_limit(user['status'])

    if len(borrowed_books) >= borrow_limit:
        keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Вы достигли лимита ({borrow_limit}) на количество заимствованных книг.", reply_markup=reply_markup)
        return USER_MENU

    keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Введите **название книги**, которую хотите взять:", reply_markup=reply_markup, parse_mode='Markdown')
    return USER_BORROW_BOOK_NAME

async def process_borrow_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает запрос на взятие книги и предлагает резервацию, если ее нет в наличии."""
    book_name = update.message.text
    user_id = context.user_data['current_user']['id']

    try:
        found_book = db_data.get_book_by_name(book_name)
    except db_data.NotFoundError:
        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Книга '{book_name}' не найдена. Попробуйте еще раз или вернитесь в меню.",
            reply_markup=reply_markup
        )
        return USER_BORROW_BOOK_NAME

    if found_book['available_quantity'] <= 0:
        context.user_data['book_to_reserve'] = found_book
        keyboard = [
            [InlineKeyboardButton("Да, уведомить меня", callback_data="reserve_yes")],
            [InlineKeyboardButton("Нет, спасибо", callback_data="reserve_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Книга '{found_book['name']}' временно отсутствует. Хотите зарезервировать ее и получить уведомление о поступлении?",
            reply_markup=reply_markup
        )
        return USER_RESERVE_BOOK_CONFIRM

    try:
        db_data.borrow_book(user_id, found_book['id'])
        await update.message.reply_text(f"✅ Книга '{found_book['name']}' успешно взята.")
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось взять книгу: {e}")

    return await user_menu(update, context)


async def process_reservation_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает решение пользователя о резервировании книги."""
    query = update.callback_query
    await query.answer()

    decision = query.data
    book_to_reserve = context.user_data.get('book_to_reserve')
    user_id = context.user_data['current_user']['id']

    if not book_to_reserve:
        await query.edit_message_text("Произошла ошибка. Пожалуйста, вернитесь в главное меню и попробуйте снова.")
        return await user_menu(update, context)

    if decision == 'reserve_yes':
        result = db_data.add_reservation(user_id, book_to_reserve['id'])
        await query.edit_message_text(f"✅ {result}")
    else:
        await query.edit_message_text("Действие отменено.")

    context.user_data.pop('book_to_reserve', None)
    return await user_menu(update, context)

async def start_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс возврата книги."""
    query = update.callback_query
    await query.answer()

    user_id = context.user_data['current_user']['id']
    borrowed_books = db_data.get_borrowed_books(user_id)

    if not borrowed_books:
        keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("У вас нет взятых книг.", reply_markup=reply_markup)
        return USER_MENU

    message_text = "Ваши взятые книги. Выберите ту, которую хотите вернуть:"
    keyboard = []
    context.user_data['borrowed_map'] = {}

    for i, borrowed in enumerate(borrowed_books):
        borrow_id = f"return_{i}"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {borrowed['book_name']} (взята: {borrowed['borrow_date'].strftime('%d.%m.%Y')})", callback_data=borrow_id)])
        context.user_data['borrowed_map'][borrow_id] = {'borrow_id': borrowed['borrow_id'], 'book_id': borrowed['book_id'], 'book_name': borrowed['book_name']}

    keyboard.append([InlineKeyboardButton("Назад в меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return USER_RETURN_BOOK

async def process_return_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает возврат книги и уведомляет зарезервировавших пользователей."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    borrowed_info = context.user_data['borrowed_map'].get(callback_data)
    book_id = borrowed_info['book_id']
    book_name = borrowed_info['book_name']

    if not borrowed_info:
        await query.edit_message_text("Ошибка: Неверный выбор книги.")
        return await user_menu(update, context)

    try:
        db_data.return_book(borrowed_info['borrow_id'], book_id)
        await query.edit_message_text(f"✅ Книга '{book_name}' успешно возвращена.")

        # Проверяем, есть ли резервации на эту книгу
        reservations = db_data.get_reservations_for_book(book_id)
        if reservations:
            user_to_notify_id = reservations[0] # Уведомляем первого в очереди
            notification_text = f"🎉 Хорошие новости! Книга '{book_name}', которую вы резервировали, снова в наличии. Вы можете взять ее сейчас."

            # Отправляем уведомление через Celery
            send_telegram_message.delay(user_to_notify_id, notification_text)

            # Обновляем статус бронирования, чтобы не уведомлять повторно
            db_data.update_reservation_status(user_to_notify_id, book_id, notified=True)
    except Exception as e:
        await query.edit_message_text(f"❌ Не удалось вернуть книгу: {e}")

    context.user_data.pop('borrowed_map', None)
    return await user_menu(update, context)


async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль и список взятых книг."""
    query = update.callback_query
    await query.answer()

    user_id = context.user_data['current_user']['id']
    user_profile = db_data.get_user_profile(user_id)
    borrowed_books = db_data.get_borrowed_books(user_id)
    borrow_limit = get_user_borrow_limit(user_profile['status'])

    message_parts = [
        "**📚 Ваш Личный Кабинет 📚**",
        f"ФИО: {user_profile['full_name']}",
        f"Имя пользователя: @{user_profile['telegram_username']}" if user_profile['telegram_username'] else "Имя пользователя: Н/Д",
        f"Статус: {user_profile['status'].capitalize()}",
        f"Контакт: {user_profile['contact_info']}",
        f"Лимит книг: {borrow_limit}",
        f"Дата регистрации: {user_profile['registration_date'].strftime('%Y-%m-%d')}\n",
        f"**Взятые книги ({len(borrowed_books)}):**"
    ]

    if borrowed_books:
        for borrowed in borrowed_books:
            message_parts.append(f"- {borrowed['book_name']} (автор: {borrowed['author_name']})")
    else:
        message_parts.append("У вас нет взятых книг.")

    keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    return USER_MENU


async def view_borrow_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает историю взятых книг."""
    query = update.callback_query
    await query.answer()

    user_id = context.user_data['current_user']['id']
    history = db_data.get_user_borrow_history(user_id)

    message_parts = ["**📜 Ваша история взятых книг 📜**\n"]

    if history:
        for item in history:
            return_date_str = item['return_date'].strftime('%d.%m.%Y') if item['return_date'] else "не возвращена"
            borrow_date_str = item['borrow_date'].strftime('%d.%m.%Y')
            message_parts.append(f"- **{item['book_name']}** (взята: {borrow_date_str}, возвращена: {return_date_str})")
    else:
        message_parts.append("Вы еще не брали ни одной книги.")

    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="user_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("\n".join(message_parts), reply_markup=reply_markup, parse_mode='Markdown')
    return USER_MENU


async def start_rate_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор книги для оценки."""
    query = update.callback_query
    await query.answer()

    user_id = context.user_data['current_user']['id']
    history = db_data.get_user_borrow_history(user_id) # Оценивать можно любую книгу из истории

    if not history:
        keyboard = [[InlineKeyboardButton("Назад в меню", callback_data="user_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Вы можете оценить только те книги, которые когда-либо брали.", reply_markup=reply_markup)
        return USER_MENU

    message_text = "Выберите книгу из вашей истории, которую хотите оценить:"
    keyboard = []
    context.user_data['rating_map'] = {}

    # Уникальные книги из истории
    unique_books = {item['book_name']: item for item in history}.values()

    for i, book in enumerate(unique_books):
        rate_id = f"rate_{i}"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {book['book_name']}", callback_data=rate_id)])
        context.user_data['rating_map'][rate_id] = {'book_id': book['book_id'], 'book_name': book['book_name']}

    keyboard.append([InlineKeyboardButton("Назад в меню", callback_data="user_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return USER_RATE_BOOK_SELECT

async def select_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает выбранную книгу и просит ввести оценку."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    book_info = context.user_data['rating_map'].get(callback_data)

    if not book_info:
        await query.edit_message_text("Ошибка: Неверный выбор книги.")
        return await user_menu(update, context)

    context.user_data['book_to_rate'] = book_info

    message_text = f"Введите вашу оценку для книги **'{book_info['book_name']}'** от 1 до 5:"

    # Кнопки для быстрого выбора оценки
    rating_buttons = [
        [InlineKeyboardButton("1", callback_data="rating_1"), InlineKeyboardButton("2", callback_data="rating_2"), InlineKeyboardButton("3", callback_data="rating_3"), InlineKeyboardButton("4", callback_data="rating_4"), InlineKeyboardButton("5", callback_data="rating_5")],
        [InlineKeyboardButton("Назад к выбору книги", callback_data="user_rate")] # Возврат к выбору книги
    ]
    reply_markup = InlineKeyboardMarkup(rating_buttons)

    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return USER_RATE_BOOK_RATING

async def process_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет оценку в БД."""

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            # Извлекаем оценку из callback_data (e.g., "rating_4")
            rating = int(query.data.split('_')[1])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Ошибка при выборе оценки. Попробуйте еще раз.")
            return USER_RATE_BOOK_RATING
        target_update = query
    elif update.message:
        # Если пользователь ввел текст (что мы стараемся избегать, но нужно обработать)
        try:
            rating = int(update.message.text)
            if not 1 <= rating <= 5:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Оценка должна быть числом от 1 до 5. Попробуйте еще раз.")
            return USER_RATE_BOOK_RATING
        target_update = update.message
    else:
        return USER_RATE_BOOK_RATING # Не должно случиться

    user_id = context.user_data['current_user']['id']
    book_info = context.user_data['book_to_rate']

    try:
        db_data.add_rating(user_id, book_info['book_id'], rating)
        message_text = f"✅ Ваша оценка '{rating}' для книги '{book_info['book_name']}' сохранена/обновлена."
    except Exception as e:
        message_text = f"❌ Не удалось сохранить оценку: {e}"

    context.user_data.pop('book_to_rate', None)
    context.user_data.pop('rating_map', None)

    # Отправляем сообщение и возвращаемся в меню
    if update.callback_query:
        await target_update.edit_message_text(message_text)
    else:
        await target_update.reply_text(message_text)

    return await user_menu(update, context)


def main() -> None:
    """Инициализирует БД и запускает бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START_ROUTES: [
                CallbackQueryHandler(start_registration, pattern="^register$"),
                CallbackQueryHandler(start_login, pattern="^login$"),
                # Отмена возвращает на start
                CallbackQueryHandler(cancel, pattern="^cancel_start$"),
            ],
            # --- Регистрация (Кнопочная навигация назад) ---
            REGISTER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name),
                # Назад: к START
                CallbackQueryHandler(start, pattern="^back_START_ROUTES$")
            ],
            REGISTER_DOB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob),
                # Назад: к вводу NAME (start_registration переспрашивает ФИО)
                CallbackQueryHandler(start_registration, pattern="^back_REGISTER_NAME$")
            ],
            REGISTER_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact),
                # Назад: к вводу DOB
                CallbackQueryHandler(get_name, pattern="^back_REGISTER_DOB$") # Это должно быть get_name, которое переспрашивает DOB
            ],
            REGISTER_VERIFY_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_registration_code),
                # Назад: к вводу CONTACT (переспросить контакт и переотправить код)
                CallbackQueryHandler(get_dob, pattern="^back_REGISTER_CONTACT$")
            ],
            REGISTER_STATUS: [
                CallbackQueryHandler(get_status, pattern="^(студент|учитель)$"),
                # Назад: к вводу VERIFY_CODE
                CallbackQueryHandler(get_contact, pattern="^back_REGISTER_VERIFY_CODE$")
            ],
            REGISTER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_password),
                # Назад: к выбору STATUS
                CallbackQueryHandler(verify_registration_code, pattern="^back_REGISTER_STATUS$") # Должно быть verify_code, которое переспрашивает статус
            ],

            # --- Вход ---
            LOGIN_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_login_contact),
                CallbackQueryHandler(start_forgot_password, pattern="^forgot_password$"),
                # Назад: к START
                CallbackQueryHandler(start, pattern="^back_START_ROUTES$")
            ],
            LOGIN_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_login_password),
                # Назад: к вводу LOGIN_CONTACT
                CallbackQueryHandler(start_login, pattern="^back_LOGIN_CONTACT$")
            ],

            # --- Меню пользователя ---
            USER_MENU: [
                CallbackQueryHandler(start_borrow_book, pattern="^user_borrow$"),
                CallbackQueryHandler(start_return_book, pattern="^user_return$"),
                CallbackQueryHandler(start_rate_book, pattern="^user_rate$"),
                CallbackQueryHandler(view_profile, pattern="^user_profile$"),
                CallbackQueryHandler(view_borrow_history, pattern="^user_history$"),
                CallbackQueryHandler(logout, pattern="^logout$"),
                CallbackQueryHandler(user_menu, pattern="^user_menu$")
            ],
            USER_BORROW_BOOK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_borrow_book),
                CallbackQueryHandler(user_menu, pattern="^user_menu$")
            ],
            USER_RESERVE_BOOK_CONFIRM: [
                CallbackQueryHandler(process_reservation_decision, pattern="^reserve_(yes|no)$")
            ],
            USER_RETURN_BOOK: [
                CallbackQueryHandler(process_return_book, pattern="^return_\d+$"),
                CallbackQueryHandler(user_menu, pattern="^user_menu$")
            ],
            USER_RATE_BOOK_SELECT: [
                CallbackQueryHandler(select_rating, pattern="^rate_\d+$"),
                CallbackQueryHandler(user_menu, pattern="^user_menu$")
            ],

            USER_RATE_BOOK_RATING: [
                # Обработка ввода (текст) или кнопок (callback)
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_rating),
                CallbackQueryHandler(process_rating, pattern="^rating_\d+$"),
                CallbackQueryHandler(start_rate_book, pattern="^user_rate$")
            ],

            # --- Восстановление пароля ---
            FORGOT_PASSWORD_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_forgot_password_contact),
                # Назад: к start_login
                CallbackQueryHandler(start_login, pattern="^back_LOGIN_CONTACT$")
            ],
            FORGOT_PASSWORD_VERIFY_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_forgot_password_code),
                # Назад: к вводу CONTACT
                CallbackQueryHandler(start_forgot_password, pattern="^back_FORGOT_PASSWORD_CONTACT$")
            ],
            FORGOT_PASSWORD_SET_NEW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_new_password),
                # Назад: к вводу VERIFY_CODE
                CallbackQueryHandler(get_forgot_password_contact, pattern="^back_FORGOT_PASSWORD_VERIFY_CODE$")
            ],
        },
        # Убрана команда /cancel из fallbacks для полной кнопочной навигации
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()