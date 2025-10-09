# -*- coding: utf-8 -*-
import logging
from .utils import hash_password
from datetime import datetime, timedelta
import asyncpg
import uuid

# Настройка логирования
logger = logging.getLogger(__name__)

# --- Пользовательские исключения ---
class DatabaseError(Exception):
    """Общая ошибка базы данных."""
    pass

class NotFoundError(DatabaseError):
    """Ошибка, когда запись не найдена."""
    pass

class UserExistsError(DatabaseError):
    """Ошибка, когда пользователь уже существует."""
    pass

# --- Вспомогательные функции для преобразования ---
def _record_to_dict(record: asyncpg.Record | None) -> dict | None:
    return dict(record) if record else None

def _records_to_list_of_dicts(records: list[asyncpg.Record]) -> list[dict]:
    return [dict(r) for r in records]

# ==============================================================================
# --- Функции для работы с ПОЛЬЗОВАТЕЛЯМИ (Users) ---
# ==============================================================================

async def add_user(conn: asyncpg.Connection, data: dict) -> int:
    """Добавляет нового пользователя."""
    hashed_pass = hash_password(data['password'])
    try:
        user_id = await conn.fetchval(
            """
            INSERT INTO users (username, telegram_id, telegram_username, full_name, dob, contact_info, status, password_hash, registration_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id;
            """,
            data['username'], data.get('telegram_id'), data.get('telegram_username'),
            data['full_name'], data['dob'], data['contact_info'], data['status'],
            hashed_pass, datetime.now()
        )
        return user_id
    except asyncpg.IntegrityConstraintViolationError:
        raise UserExistsError("Пользователь с таким контактом или именем пользователя уже существует.")
    except asyncpg.PostgresError as e:
        raise DatabaseError(f"Не удалось добавить пользователя: {e}")

async def get_user_by_login(conn: asyncpg.Connection, login_query: str) -> dict:
    """Ищет пользователя по username, contact_info или telegram_username."""
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE username = $1 OR contact_info = $1 OR telegram_username = $1",
        login_query
    )
    if not row:
        raise NotFoundError("Пользователь с таким логином не найден.")
    return _record_to_dict(row)

async def get_user_by_id(conn: asyncpg.Connection, user_id: int) -> dict:
    """Возвращает все данные одного пользователя по его ID."""
    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        raise NotFoundError("Пользователь с таким ID не найден.")
    return _record_to_dict(row)

async def get_all_users(conn: asyncpg.Connection, limit: int, offset: int) -> tuple[list, int]:
    """Возвращает порцию пользователей для постраничной навигации и общее количество."""
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    rows = await conn.fetch(
        "SELECT id, username, full_name, registration_date, dob FROM users ORDER BY registration_date DESC LIMIT $1 OFFSET $2",
        limit, offset
    )
    return _records_to_list_of_dicts(rows), total_users or 0

async def get_all_user_ids(conn: asyncpg.Connection) -> list[int]:
    """Возвращает список всех ID пользователей, привязавших Telegram."""
    records = await conn.fetch("SELECT id FROM users WHERE telegram_id IS NOT NULL")
    return [item['id'] for item in records]

async def get_user_profile(conn: asyncpg.Connection, user_id: int) -> dict:
    """Получает данные для карточки профиля пользователя."""
    row = await conn.fetchrow("SELECT username, full_name, telegram_username, status, contact_info, registration_date, dob FROM users WHERE id = $1", user_id)
    if not row:
        raise NotFoundError("Профиль пользователя не найден.")
    return _record_to_dict(row)

async def update_user_password(conn: asyncpg.Connection, login_query: str, new_password: str):
    """Обновляет пароль пользователя по логину."""
    hashed_pass = hash_password(new_password)
    result = await conn.execute("UPDATE users SET password_hash = $1 WHERE username = $2 OR contact_info = $2", hashed_pass, login_query)
    if int(result.split()[-1]) == 0:
        raise NotFoundError("Пользователь для обновления пароля не найден.")

async def update_user_password_by_id(conn: asyncpg.Connection, user_id: int, new_password: str):
    """Обновляет пароль пользователя по его ID."""
    hashed_pass = hash_password(new_password)
    result = await conn.execute("UPDATE users SET password_hash = $1 WHERE id = $2", hashed_pass, user_id)
    if int(result.split()[-1]) == 0:
        raise NotFoundError("Пользователь не найден для обновления пароля.")

async def update_user_full_name(conn: asyncpg.Connection, user_id: int, new_name: str):
    """Обновляет ФИО пользователя."""
    result = await conn.execute("UPDATE users SET full_name = $1 WHERE id = $2", new_name, user_id)
    if int(result.split()[-1]) == 0:
        raise NotFoundError("Пользователь не найден для обновления ФИО.")

async def update_user_contact(conn: asyncpg.Connection, user_id: int, new_contact: str):
    """Обновляет контактную информацию пользователя."""
    try:
        result = await conn.execute("UPDATE users SET contact_info = $1 WHERE id = $2", new_contact, user_id)
        if int(result.split()[-1]) == 0:
            raise NotFoundError("Пользователь не найден для обновления контакта.")
    except asyncpg.IntegrityConstraintViolationError:
        raise UserExistsError("Этот контакт уже используется другим пользователем.")

async def delete_user_by_admin(conn: asyncpg.Connection, user_id: int):
    """Анонимизирует пользователя (выполняется администратором)."""
    async with conn.transaction():
        book_ids_records = await conn.fetch("SELECT book_id FROM borrowed_books WHERE user_id = $1 AND return_date IS NULL", user_id)
        if book_ids_records:
            book_ids = [(r['book_id'],) for r in book_ids_records]
            await conn.executemany("UPDATE books SET available_quantity = available_quantity + 1 WHERE id = $1", book_ids)
        await conn.execute("UPDATE borrowed_books SET return_date = CURRENT_DATE WHERE user_id = $1 AND return_date IS NULL", user_id)
        anonymized_username = f"deleted_user_{user_id}"
        await conn.execute(
            "UPDATE users SET username = $1, full_name = '(удален админом)', contact_info = $2, password_hash = 'deleted', status = 'deleted', telegram_id = NULL, telegram_username = NULL WHERE id = $3",
            anonymized_username, anonymized_username, user_id
        )

async def delete_user_by_self(conn: asyncpg.Connection, user_id: int) -> str:
    """Анонимизирует пользователя по его собственной просьбе."""
    async with conn.transaction():
        has_books = await conn.fetchval("SELECT 1 FROM borrowed_books WHERE user_id = $1 AND return_date IS NULL", user_id)
        if has_books:
            return "У вас есть невозвращенные книги. Удаление невозможно."
        anonymized_username = f"deleted_user_{user_id}"
        await conn.execute(
            "UPDATE users SET username = $1, full_name = '(удален)', contact_info = $2, password_hash = 'deleted', status = 'deleted', telegram_id = NULL, telegram_username = NULL WHERE id = $3",
            anonymized_username, anonymized_username, user_id
        )
        return "Аккаунт успешно удален (анонимизирован)."

# ==============================================================================
# --- Функции для привязки Telegram (Регистрация) ---
# ==============================================================================

async def set_registration_code(conn: asyncpg.Connection, user_id: int) -> str:
    """Генерирует, сохраняет и возвращает уникальный код регистрации для пользователя."""
    code = str(uuid.uuid4())
    await conn.execute("UPDATE users SET registration_code = $1 WHERE id = $2", code, user_id)
    return code

async def link_telegram_id_by_code(conn: asyncpg.Connection, code: str, telegram_id: int, telegram_username: str):
    """Находит пользователя по коду регистрации и обновляет его telegram_id."""
    res = await conn.fetchval("UPDATE users SET telegram_id = $1, telegram_username = $2 WHERE registration_code = $3 RETURNING id", telegram_id, telegram_username, code)
    if res is None:
        raise NotFoundError("Пользователь с таким кодом регистрации не найден.")

async def get_telegram_id_by_user_id(conn: asyncpg.Connection, user_id: int) -> int:
    """Возвращает telegram_id пользователя по его внутреннему id."""
    tid = await conn.fetchval("SELECT telegram_id FROM users WHERE id = $1", user_id)
    if not tid:
        raise NotFoundError(f"Telegram ID для пользователя с ID {user_id} не найден.")
    return tid

# ==============================================================================
# --- Функции для работы с КНИГАМИ (Books & Authors) ---
# ==============================================================================

async def get_or_create_author(conn: asyncpg.Connection, author_name: str) -> int:
    """Находит автора по имени или создает нового. Возвращает ID автора."""
    async with conn.transaction():
        author_id = await conn.fetchval("SELECT id FROM authors WHERE name = $1", author_name)
        if author_id:
            return author_id
        return await conn.fetchval("INSERT INTO authors (name) VALUES ($1) RETURNING id", author_name)

async def add_new_book(conn: asyncpg.Connection, book_data: dict) -> int:
    """Добавляет новую книгу, находя или создавая автора."""
    author_id = await get_or_create_author(conn, book_data['author'])
    return await conn.fetchval(
        "INSERT INTO books (name, author_id, genre, description, cover_image_id, total_quantity, available_quantity) VALUES ($1, $2, $3, $4, $5, $6, $6) RETURNING id",
        book_data['name'], author_id, book_data['genre'], book_data['description'],
        book_data.get('cover_image_id'), book_data.get('total_quantity', 1)
    )

async def get_book_by_id(conn: asyncpg.Connection, book_id: int) -> dict:
    """Ищет одну книгу по её ID для базовых операций."""
    row = await conn.fetchrow("SELECT b.id, b.name, a.name as author_name, b.available_quantity FROM books b JOIN authors a ON b.author_id = a.id WHERE b.id = $1", book_id)
    if not row:
        raise NotFoundError("Книга с таким ID не найдена.")
    return _record_to_dict(row)

async def get_all_books_paginated(conn: asyncpg.Connection, limit: int, offset: int) -> tuple[list, int]:
    """Возвращает порцию книг для админ-панели и их общее количество."""
    total_books = await conn.fetchval("SELECT COUNT(*) FROM books")
    rows = await conn.fetch(
        """
        SELECT b.id, b.name, a.name as author, b.available_quantity > 0 as is_available
        FROM books b JOIN authors a ON b.author_id = a.id
        ORDER BY b.name LIMIT $1 OFFSET $2
        """, limit, offset
    )
    return _records_to_list_of_dicts(rows), total_books or 0

async def get_book_details(conn: asyncpg.Connection, book_id: int) -> dict | None:
    """Возвращает детальную информацию о книге для админа (включая текущего владельца)."""
    row = await conn.fetchrow(
        """
        SELECT b.id, b.name, a.name as author, b.genre, b.description, b.cover_image_id, u.id as user_id, u.username, bb.borrow_date
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.id
        LEFT JOIN borrowed_books bb ON b.id = bb.book_id AND bb.return_date IS NULL
        LEFT JOIN users u ON bb.user_id = u.id
        WHERE b.id = $1
        """, book_id
    )
    return _record_to_dict(row)

async def get_book_card_details(conn: asyncpg.Connection, book_id: int) -> dict:
    """Возвращает все данные для карточки книги (для пользователя), включая статус доступности."""
    book_details = await conn.fetchrow(
        """
        SELECT b.id, b.name, a.name as author, b.genre, b.description, b.cover_image_id, (b.available_quantity > 0) as is_available
        FROM books b JOIN authors a ON b.author_id = a.id WHERE b.id = $1
        """, book_id
    )
    if not book_details:
        raise NotFoundError("Книга с таким ID не найдена.")
    return _record_to_dict(book_details)

async def update_book_field(conn: asyncpg.Connection, book_id: int, field: str, value: str):
    """Обновляет указанное поле для указанной книги (безопасно)."""
    ALLOWED_FIELDS = ["name", "genre", "description"]
    if field == 'author':
        author_id = await get_or_create_author(conn, value)
        await conn.execute("UPDATE books SET author_id = $1 WHERE id = $2", author_id, book_id)
    elif field in ALLOWED_FIELDS:
        # Использование f-string здесь безопасно, так как `field` проверяется по белому списку
        query = f"UPDATE books SET {field} = $1 WHERE id = $2"
        await conn.execute(query, value, book_id)
    else:
        raise ValueError(f"Недопустимое поле для обновления: {field}")

async def delete_book(conn: asyncpg.Connection, book_id: int):
    """Удаляет книгу и все связанные с ней записи (благодаря ON DELETE CASCADE)."""
    await conn.execute("DELETE FROM books WHERE id = $1", book_id)

# ==============================================================================
# --- Функции для ПОИСКА КНИГ (Search) ---
# ==============================================================================

async def get_unique_genres(conn: asyncpg.Connection) -> list[str]:
    """Возвращает список всех уникальных жанров из таблицы книг."""
    records = await conn.fetch("SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL AND genre != '' ORDER BY genre")
    return [row['genre'] for row in records]

async def get_available_books_by_genre(conn: asyncpg.Connection, genre: str, limit: int, offset: int) -> tuple[list, int]:
    """Возвращает порцию свободных книг по жанру."""
    total = await conn.fetchval("SELECT COUNT(*) FROM books WHERE genre = $1 AND available_quantity > 0", genre)
    rows = await conn.fetch(
        "SELECT b.id, b.name, a.name as author, (b.available_quantity > 0) as is_available FROM books b JOIN authors a ON b.author_id = a.id WHERE b.genre = $1 AND b.available_quantity > 0 ORDER BY b.name LIMIT $2 OFFSET $3",
        genre, limit, offset
    )
    return _records_to_list_of_dicts(rows), total or 0

async def search_available_books(conn: asyncpg.Connection, search_term: str, limit: int, offset: int) -> tuple[list, int]:
    """Ищет доступные книги по названию или автору."""
    search_pattern = f"%{search_term}%"
    total = await conn.fetchval(
        "SELECT COUNT(b.id) FROM books b JOIN authors a ON b.author_id = a.id WHERE (b.name ILIKE $1 OR a.name ILIKE $1) AND b.available_quantity > 0",
        search_pattern
    )
    rows = await conn.fetch(
        "SELECT b.id, b.name, a.name as author FROM books b JOIN authors a ON b.author_id = a.id WHERE (b.name ILIKE $1 OR a.name ILIKE $1) AND b.available_quantity > 0 ORDER BY b.name LIMIT $2 OFFSET $3",
        search_pattern, limit, offset
    )
    return _records_to_list_of_dicts(rows), total or 0

# ==============================================================================
# --- Функции для ВЗАИМОДЕЙСТВИЙ с книгами (Borrow, Return, Rate, etc.) ---
# ==============================================================================

async def get_borrowed_books(conn: asyncpg.Connection, user_id: int) -> list[dict]:
    """Получает список книг, взятых пользователем."""
    rows = await conn.fetch(
        """
        SELECT bb.borrow_id, b.id as book_id, b.name as book_name, a.name as author_name, bb.borrow_date, bb.due_date
        FROM borrowed_books bb JOIN books b ON bb.book_id = b.id JOIN authors a ON b.author_id = a.id
        WHERE bb.user_id = $1 AND bb.return_date IS NULL
        """, user_id
    )
    return _records_to_list_of_dicts(rows)

async def get_user_borrow_history(conn: asyncpg.Connection, user_id: int) -> list[dict]:
    """Получает всю историю заимствований пользователя, включая его оценки."""
    rows = await conn.fetch(
        """
        SELECT b.id as book_id, b.name as book_name, a.name as author_name, bb.borrow_date, bb.return_date, r.rating
        FROM borrowed_books bb JOIN books b ON bb.book_id = b.id JOIN authors a ON b.author_id = a.id
        LEFT JOIN ratings r ON bb.user_id = r.user_id AND bb.book_id = r.book_id
        WHERE bb.user_id = $1 ORDER BY bb.borrow_date DESC
        """, user_id
    )
    return _records_to_list_of_dicts(rows)

async def borrow_book(conn: asyncpg.Connection, user_id: int, book_id: int) -> datetime:
    """Обрабатывает взятие книги. Возвращает due_date."""
    async with conn.transaction():
        available = await conn.fetchval("SELECT available_quantity FROM books WHERE id = $1 FOR UPDATE", book_id)
        if not available or available <= 0:
            raise ValueError("Книга недоступна для взятия")
        await conn.execute("UPDATE books SET available_quantity = available_quantity - 1 WHERE id = $1", book_id)
        due_date = datetime.now().date() + timedelta(days=14)
        return await conn.fetchval(
            "INSERT INTO borrowed_books (user_id, book_id, borrow_date, due_date) VALUES ($1, $2, CURRENT_DATE, $3) RETURNING due_date",
            user_id, book_id, due_date
        )

async def return_book(conn: asyncpg.Connection, borrow_id: int, book_id: int) -> str:
    """Обрабатывает возврат книги."""
    async with conn.transaction():
        await conn.execute("UPDATE borrowed_books SET return_date = CURRENT_DATE WHERE borrow_id = $1", borrow_id)
        await conn.execute("UPDATE books SET available_quantity = available_quantity + 1 WHERE id = $1", book_id)
    return "Успешно"

async def add_rating(conn: asyncpg.Connection, user_id: int, book_id: int, rating: int):
    """Добавляет или обновляет оценку книги."""
    await conn.execute(
        "INSERT INTO ratings (user_id, book_id, rating) VALUES ($1, $2, $3) ON CONFLICT (user_id, book_id) DO UPDATE SET rating = EXCLUDED.rating",
        user_id, book_id, rating
    )

async def get_user_ratings(conn: asyncpg.Connection, user_id: int) -> list[dict]:
    """Возвращает историю оценок пользователя (книга и оценка)."""
    rows = await conn.fetch(
        "SELECT b.name as book_name, r.rating FROM ratings r JOIN books b ON r.book_id = b.id WHERE r.user_id = $1 ORDER BY b.name",
        user_id
    )
    return _records_to_list_of_dicts(rows)

async def get_top_rated_books(conn: asyncpg.Connection, limit: int = 5) -> list[dict]:
    """Возвращает список книг с самым высоким средним рейтингом (2+ оценки)."""
    rows = await conn.fetch(
        """
        SELECT b.name, a.name as author, AVG(r.rating) as avg_rating, COUNT(r.rating) as votes
        FROM ratings r JOIN books b ON r.book_id = b.id JOIN authors a ON b.author_id = a.id
        GROUP BY b.id, a.name HAVING COUNT(r.rating) >= 2
        ORDER BY avg_rating DESC, votes DESC LIMIT $1
        """, limit
    )
    return _records_to_list_of_dicts(rows)

async def extend_due_date(conn: asyncpg.Connection, borrow_id: int) -> datetime | str:
    """Продлевает срок возврата книги, если это возможно."""
    async with conn.transaction():
        borrow_info = await conn.fetchrow("SELECT book_id, extensions_count FROM borrowed_books WHERE borrow_id = $1 FOR UPDATE", borrow_id)
        if not borrow_info:
            return "Запись о взятии книги не найдена."
        if borrow_info['extensions_count'] >= 1:
            return "Вы уже продлевали эту книгу. Повторное продление невозможно."
        has_reservation = await conn.fetchval("SELECT 1 FROM reservations WHERE book_id = $1 AND notified = FALSE", borrow_info['book_id'])
        if has_reservation:
            return "Невозможно продлить: эту книгу уже зарезервировал другой читатель."
        return await conn.fetchval(
            "UPDATE borrowed_books SET due_date = due_date + INTERVAL '7 day', extensions_count = extensions_count + 1 WHERE borrow_id = $1 RETURNING due_date",
            borrow_id
        )

# ==============================================================================
# --- Функции для УВЕДОМЛЕНИЙ и ЛОГОВ (Notifications & Logs) ---
# ==============================================================================

async def add_reservation(conn: asyncpg.Connection, user_id: int, book_id: int) -> str:
    """Добавляет запись о бронировании книги."""
    try:
        await conn.execute("INSERT INTO reservations (user_id, book_id) VALUES ($1, $2)", user_id, book_id)
        return "Книга успешно зарезервирована."
    except asyncpg.IntegrityConstraintViolationError:
        return "Вы уже зарезервировали эту книгу."

async def get_reservations_for_book(conn: asyncpg.Connection, book_id: int) -> list[int]:
    """Получает ID пользователей, зарезервировавших книгу."""
    records = await conn.fetch("SELECT user_id FROM reservations WHERE book_id = $1 AND notified = FALSE ORDER BY reservation_date", book_id)
    return [r['user_id'] for r in records]

async def update_reservation_status(conn: asyncpg.Connection, user_id: int, book_id: int, notified: bool):
    """Обновляет статус уведомления для брони."""
    await conn.execute("UPDATE reservations SET notified = $1 WHERE user_id = $2 AND book_id = $3 AND notified = FALSE", notified, user_id, book_id)

async def create_notification(conn: asyncpg.Connection, user_id: int, text: str, category: str):
    """Сохраняет новое уведомление для пользователя в базу данных."""
    await conn.execute("INSERT INTO notifications (user_id, text, category) VALUES ($1, $2, $3)", user_id, text, category)

async def get_notifications_for_user(conn: asyncpg.Connection, user_id: int, limit: int = 20) -> list[dict]:
    """Возвращает последние уведомления для пользователя."""
    rows = await conn.fetch("SELECT text, category, created_at, is_read FROM notifications WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2", user_id, limit)
    if not rows:
        raise NotFoundError("Уведомлений для этого пользователя не найдено.")
    return _records_to_list_of_dicts(rows)

async def log_activity(conn: asyncpg.Connection, user_id: int, action: str, details: str = None):
    """Записывает действие пользователя в журнал активности."""
    await conn.execute("INSERT INTO activity_log (user_id, action, details) VALUES ($1, $2, $3)", user_id, action, details)

async def get_user_activity(conn: asyncpg.Connection, user_id: int, limit: int, offset: int) -> tuple[list, int]:
    """Возвращает порцию логов активности для пользователя и их общее количество."""
    total = await conn.fetchval("SELECT COUNT(*) FROM activity_log WHERE user_id = $1", user_id)
    rows = await conn.fetch("SELECT action, details, timestamp FROM activity_log WHERE user_id = $1 ORDER BY timestamp DESC LIMIT $2 OFFSET $3", user_id, limit, offset)
    return _records_to_list_of_dicts(rows), total or 0

async def get_users_with_overdue_books(conn: asyncpg.Connection) -> list[dict]:
    """Возвращает пользователей с просроченными книгами."""
    rows = await conn.fetch("""
        SELECT u.id as user_id, u.username, b.name as book_name, bb.due_date
        FROM borrowed_books bb JOIN users u ON bb.user_id = u.id JOIN books b ON bb.book_id = b.id
        WHERE bb.return_date IS NULL AND bb.due_date < CURRENT_DATE
    """)
    return _records_to_list_of_dicts(rows)

async def get_users_with_books_due_soon(conn: asyncpg.Connection, days_ahead: int = 2) -> list[dict]:
    """Возвращает пользователей, у которых срок возврата истекает через 'days_ahead' дней."""
    rows = await conn.fetch("""
        SELECT u.id as user_id, b.name as book_name, bb.due_date, bb.borrow_id
        FROM borrowed_books bb JOIN users u ON bb.user_id = u.id JOIN books b ON bb.book_id = b.id
        WHERE bb.return_date IS NULL AND bb.due_date = CURRENT_DATE + make_interval(days => $1)
    """, days_ahead)
    return _records_to_list_of_dicts(rows)

async def get_all_authors_paginated(conn: asyncpg.Connection, limit: int, offset: int) -> tuple[list, int]:
    """Возвращает постраничный список авторов с количеством их книг."""
    total = await conn.fetchval("SELECT COUNT(*) FROM authors a JOIN books b ON a.id = b.author_id")
    rows = await conn.fetch("""
        SELECT a.id, a.name, COUNT(b.id) as books_count,
               SUM(CASE WHEN b.available_quantity > 0 THEN 1 ELSE 0 END) as available_books_count
        FROM authors a LEFT JOIN books b ON a.id = b.author_id
        GROUP BY a.id, a.name HAVING COUNT(b.id) > 0
        ORDER BY a.name LIMIT $1 OFFSET $2
    """, limit, offset)
    return _records_to_list_of_dicts(rows), total or 0

async def get_author_details(conn: asyncpg.Connection, author_id: int) -> dict:
    """Возвращает детальную информацию об авторе."""
    row = await conn.fetchrow("""
        SELECT a.id, a.name, COUNT(b.id) as total_books,
               SUM(CASE WHEN b.available_quantity > 0 THEN 1 ELSE 0 END) as available_books_count
        FROM authors a LEFT JOIN books b ON a.id = b.author_id
        WHERE a.id = $1 GROUP BY a.id, a.name
    """, author_id)
    if not row:
        raise NotFoundError("Автор не найден.")
    return _record_to_dict(row)

async def get_books_by_author(conn: asyncpg.Connection, author_id: int, limit: int = 10, offset: int = 0) -> tuple[list, int]:
    """Возвращает книги конкретного автора с пагинацией."""
    total = await conn.fetchval("SELECT COUNT(*) FROM books WHERE author_id = $1", author_id)
    rows = await conn.fetch("""
        SELECT b.id, b.name, b.genre, b.description, (b.available_quantity > 0) as is_available,
               AVG(r.rating) as avg_rating, COUNT(r.rating) as ratings_count
        FROM books b LEFT JOIN ratings r ON b.id = r.book_id
        WHERE b.author_id = $1
        GROUP BY b.id, b.name, b.genre, b.description
        ORDER BY b.name LIMIT $2 OFFSET $3
    """, author_id, limit, offset)
    return _records_to_list_of_dicts(rows), total or 0