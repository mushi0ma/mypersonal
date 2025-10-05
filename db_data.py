# -*- coding: utf-8 -*-
import logging
from db_utils import hash_password, get_db_connection
from datetime import datetime
import psycopg2
import uuid

# Настройка логирования
logger = logging.getLogger(__name__)

# --- Custom Exceptions ---
class DatabaseError(Exception):
    """Общая ошибка базы данных."""
    pass

class NotFoundError(DatabaseError):
    """Ошибка, когда запись не найдена."""
    pass

class UserExistsError(DatabaseError):
    """Ошибка, когда пользователь уже существует."""
    pass


def get_user_by_login(conn, login_query: str):
    """Ищет пользователя по УНИКАЛЬНОМУ полю: username, contact_info или telegram_username."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, contact_info, status, password_hash, telegram_id, telegram_username, username
            FROM users
            WHERE username = %s OR contact_info = %s OR telegram_username = %s
            """,
            (login_query, login_query, login_query)
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Пользователь с таким логином не найден.")
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

def add_user(conn, data: dict):
    """Добавляет нового пользователя."""
    hashed_pass = hash_password(data['password'])
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO users (username, telegram_id, telegram_username, full_name, dob, contact_info, status, password_hash, registration_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (data['username'], data.get('telegram_id'), data.get('telegram_username'), data['full_name'], data['dob'], data['contact_info'], data['status'], hashed_pass, datetime.now())
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            return user_id
        except psycopg2.IntegrityError:
            conn.rollback()
            raise UserExistsError("Пользователь с таким контактом или именем пользователя уже существует.")
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Не удалось добавить пользователя: {e}")

def get_all_user_ids(conn):
    """Возвращает список всех ID пользователей из нашей БД."""
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT id FROM users WHERE telegram_id IS NOT NULL")
            return [item[0] for item in cur.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Ошибка при получении всех ID пользователей: {e}")
            return []

def get_all_users(conn, limit: int, offset: int):
    """Возвращает порцию пользователей для постраничной навигации и общее количество."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute(
            """
            SELECT id, username, full_name, registration_date, dob
            FROM users
            ORDER BY registration_date DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        users_on_page = [dict(zip(columns, row)) for row in rows]
        return users_on_page, total_users

def get_user_by_id(conn, user_id: int):
    """Возвращает все данные одного пользователя по его ID."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Пользователь с таким ID не найден.")
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

def add_reservation(conn, user_id, book_id):
    """Добавляет запись о бронировании книги."""
    with conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO reservations (user_id, book_id) VALUES (%s, %s)", (user_id, book_id))
            conn.commit()
            return "Книга успешно зарезервирована."
        except psycopg2.IntegrityError:
            conn.rollback()
            return "Вы уже зарезервировали эту книгу."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при резервировании книги: {e}")

def get_reservations_for_book(conn, book_id):
    """Получает список пользователей, зарезервировавших книгу."""
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM reservations WHERE book_id = %s AND notified = FALSE ORDER BY reservation_date", (book_id,))
        return [item[0] for item in cur.fetchall()]

def update_user_password(conn, login_query: str, new_password: str):
    """Обновляет пароль пользователя."""
    hashed_pass = hash_password(new_password)
    with conn.cursor() as cur:
        try:
            cur.execute("UPDATE users SET password_hash = %s WHERE username = %s OR contact_info = %s", (hashed_pass, login_query, login_query))
            if cur.rowcount == 0:
                raise NotFoundError("Пользователь для обновления пароля не найден.")
            conn.commit()
            return "Пароль успешно обновлен."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при обновлении пароля: {e}")

def get_borrowed_books(conn, user_id: int):
    """Получает список книг, взятых пользователем."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT bb.borrow_id, b.id as book_id, b.name as book_name, a.name as author_name, bb.borrow_date
            FROM borrowed_books bb
            JOIN books b ON bb.book_id = b.id
            JOIN authors a ON b.author_id = a.id
            WHERE bb.user_id = %s AND bb.return_date IS NULL
            """, (user_id,)
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def get_book_by_name(conn, query: str):
    """Ищет книги по частичному совпадению в названии ИЛИ имени автора."""
    with conn.cursor() as cur:
        sql_query = """
            SELECT b.id, b.name, a.name as author_name, b.available_quantity
            FROM books b
            JOIN authors a ON b.author_id = a.id
            WHERE b.name ILIKE %s OR a.name ILIKE %s
            LIMIT 10
        """
        search_pattern = f"%{query}%"
        cur.execute(sql_query, (search_pattern, search_pattern))
        rows = cur.fetchall()
        if not rows:
            raise NotFoundError("По вашему запросу ничего не найдено.")
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]

def get_book_by_id(conn, book_id: int):
    """Ищет одну книгу по её уникальному ID."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.id, b.name, a.name as author_name, b.available_quantity
            FROM books b
            JOIN authors a ON b.author_id = a.id
            WHERE b.id = %s
            """, (book_id,)
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Книга с таким ID не найдена.")
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

def borrow_book(conn, user_id: int, book_id: int):
    """Обрабатывает взятие книги и возвращает дату, до которой нужно вернуть."""
    with conn.cursor() as cur:
        try:
            # Сначала уменьшаем количество доступных книг
            cur.execute("UPDATE books SET available_quantity = available_quantity - 1 WHERE id = %s AND available_quantity > 0", (book_id,))
            if cur.rowcount == 0:
                # Если rowcount == 0, значит, available_quantity была 0, и UPDATE не сработал
                return None # Возвращаем None, чтобы бот понял, что книга закончилась

            # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
            # Добавляем RETURNING due_date, чтобы получить рассчитанную дату
            cur.execute(
                """
                INSERT INTO borrowed_books (user_id, book_id, due_date) 
                VALUES (%s, %s, CURRENT_DATE + INTERVAL '14 day')
                RETURNING due_date
                """, 
                (user_id, book_id)
            )
            due_date = cur.fetchone()[0]
            conn.commit()
            return due_date # Теперь due_date содержит корректную дату

        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при взятии книги: {e}")

def return_book(conn, borrow_id: int, book_id: int):
    """Обрабатывает возврат книги."""
    with conn.cursor() as cur:
        try:
            cur.execute("UPDATE borrowed_books SET return_date = CURRENT_DATE WHERE borrow_id = %s", (borrow_id,))
            cur.execute("UPDATE books SET available_quantity = available_quantity + 1 WHERE id = %s", (book_id,))
            conn.commit()
            return "Книга успешно возвращена."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при возврате книги: {e}")

def get_user_profile(conn, user_id: int):
    """Получает полные данные профиля пользователя."""
    with conn.cursor() as cur:
        cur.execute("SELECT username, full_name, telegram_username, status, contact_info, registration_date, dob FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Профиль пользователя не найден.")
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))

def add_rating(conn, user_id: int, book_id: int, rating: int):
    """Добавляет или обновляет оценку книги."""
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO ratings (user_id, book_id, rating) VALUES (%s, %s, %s)
                ON CONFLICT (user_id, book_id) DO UPDATE SET rating = EXCLUDED.rating;
                """, (user_id, book_id, rating)
            )
            conn.commit()
            return "Оценка успешно сохранена."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при добавлении оценки: {e}")

def update_reservation_status(conn, user_id, book_id, notified: bool):
    """Обновляет статус уведомления для брони."""
    with conn.cursor() as cur:
        try:
            cur.execute("UPDATE reservations SET notified = %s WHERE user_id = %s AND book_id = %s AND notified = FALSE", (notified, user_id, book_id))
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при обновлении статуса брони: {e}")

def get_user_borrow_history(conn, user_id: int):
    """Получает всю историю заимствований пользователя, включая его оценки."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                b.id as book_id, b.name as book_name, a.name as author_name,
                bb.borrow_date, bb.return_date, r.rating
            FROM borrowed_books bb
            JOIN books b ON bb.book_id = b.id
            JOIN authors a ON b.author_id = a.id
            LEFT JOIN ratings r ON bb.user_id = r.user_id AND bb.book_id = r.book_id
            WHERE bb.user_id = %s
            ORDER BY bb.borrow_date DESC
            """, (user_id,)
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def delete_user_by_admin(conn, user_id: int):
    """Выполняет каскадное 'удаление' пользователя администратором."""
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT book_id FROM borrowed_books WHERE user_id = %s AND return_date IS NULL", (user_id,))
            book_ids_to_return = [item[0] for item in cur.fetchall()]
            if book_ids_to_return:
                for book_id in book_ids_to_return:
                    cur.execute("UPDATE books SET available_quantity = available_quantity + 1 WHERE id = %s", (book_id,))
            cur.execute("UPDATE borrowed_books SET return_date = CURRENT_DATE WHERE user_id = %s AND return_date IS NULL", (user_id,))
            anonymized_username = f"deleted_user_{user_id}"
            cur.execute(
                """
                UPDATE users
                SET username = %s, full_name = '(удален админом)', contact_info = %s,
                    password_hash = 'deleted', status = 'deleted', telegram_id = NULL, telegram_username = NULL
                WHERE id = %s
                """, (anonymized_username, anonymized_username, user_id)
            )
            conn.commit()
            return "Пользователь успешно удален (анонимизирован)."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при удалении пользователя: {e}")

def get_user_ratings(conn, user_id: int):
    """Возвращает историю оценок пользователя (книга и оценка)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.name as book_name, r.rating
            FROM ratings r
            JOIN books b ON r.book_id = b.id
            WHERE r.user_id = %s
            ORDER BY b.name
            """, (user_id,)
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]

def delete_user_by_self(conn, user_id: int):
    """Анонимизирует пользователя по его собственной просьбе."""
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT 1 FROM borrowed_books WHERE user_id = %s AND return_date IS NULL", (user_id,))
            if cur.fetchone():
                return "У вас есть невозвращенные книги. Удаление невозможно."
            anonymized_username = f"deleted_user_{user_id}"
            cur.execute(
                """
                UPDATE users
                SET username = %s, full_name = '(удален)', contact_info = %s,
                    password_hash = 'deleted', status = 'deleted', telegram_id = NULL, telegram_username = NULL
                WHERE id = %s
                """, (anonymized_username, anonymized_username, user_id)
            )
            conn.commit()
            return "Аккаунт успешно удален (анонимизирован)."
        except psycopg2.Error as e:
            conn.rollback()
            raise DatabaseError(f"Ошибка базы данных при удалении пользователя: {e}")

def create_notification(conn, user_id: int, text: str, category: str):
    """Сохраняет новое уведомление для пользователя в базу данных."""
    with conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO notifications (user_id, text, category) VALUES (%s, %s, %s)", (user_id, text, category))
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Не удалось создать уведомление для пользователя {user_id}: {e}")

def log_activity(conn, user_id: int, action: str, details: str = None):
    """Записывает действие пользователя в журнал активности."""
    with conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO activity_log (user_id, action, details) VALUES (%s, %s, %s)", (user_id, action, details))
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Не удалось записать действие '{action}' для пользователя {user_id}: {e}")

def get_telegram_id_by_user_id(conn, user_id: int):
    """Возвращает telegram_id пользователя по его внутреннему id."""
    with conn.cursor() as cur:
        cur.execute("SELECT telegram_id FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
        raise NotFoundError(f"Telegram ID для пользователя с ID {user_id} не найден.")

def get_notifications_for_user(conn, user_id: int, limit: int = 20):
    """Возвращает последние уведомления для пользователя."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT text, category, created_at, is_read
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """, (user_id, limit)
        )
        rows = cur.fetchall()
        if not rows:
            raise NotFoundError("Уведомлений для этого пользователя не найдено.")
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]
    
def get_user_activity(conn, user_id: int, limit: int, offset: int):
    """Возвращает порцию логов активности для пользователя и их общее количество."""
    # Контекстный менеджер 'with get_db_connection()' удален,
    # так как 'conn' теперь передается напрямую.
    with conn.cursor() as cur:
        # Получаем общее количество записей для этого пользователя
        cur.execute("SELECT COUNT(*) FROM activity_log WHERE user_id = %s", (user_id,))
        total_logs = cur.fetchone()[0]

        # Получаем срез логов
        cur.execute(
            """
            SELECT action, details, timestamp
            FROM activity_log
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset)
        )
        
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        activity_on_page = [dict(zip(columns, row)) for row in rows]
        
        return activity_on_page, total_logs
    
def get_all_books_paginated(conn, limit: int, offset: int):
    """Возвращает порцию книг для админ-панели и их общее количество."""
    with conn.cursor() as cur:
        # Считаем общее количество книг
        cur.execute("SELECT COUNT(*) FROM books")
        total_books = cur.fetchone()[0]

        # Получаем срез книг с информацией о том, взята ли книга
        cur.execute(
            """
            SELECT 
                b.id, 
                b.name,
                CASE WHEN bb.id IS NOT NULL AND bb.return_date IS NULL THEN TRUE ELSE FALSE END AS is_borrowed
            FROM books b
            LEFT JOIN borrowed_books bb ON b.id = bb.book_id AND bb.return_date IS NULL
            ORDER BY b.name
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        books_on_page = [dict(zip(columns, row)) for row in rows]
        
        return books_on_page, total_books

def get_book_details(conn, book_id: int):
    """Возвращает детальную информацию о книге, включая текущего владельца."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                b.id, b.name, b.author, b.genre, b.description, b.cover_image_id,
                u.id as user_id,
                u.username,
                bb.borrow_date
            FROM books b
            LEFT JOIN borrowed_books bb ON b.id = bb.book_id AND bb.return_date IS NULL
            LEFT JOIN users u ON bb.user_id = u.id
            WHERE b.id = %s
            """,
            (book_id,)
        )
        
        row = cur.fetchone()
        if not row:
            return None
            
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    
def update_book_field(conn, book_id: int, field: str, value: str):
    """Обновляет указанное поле для указанной книги."""
    # Белый список полей для безопасности, чтобы предотвратить SQL-инъекции
    allowed_fields = ["name", "author", "genre", "description"]
    if field not in allowed_fields:
        raise ValueError("Недопустимое поле для обновления")

    # Динамически, но безопасно формируем запрос
    sql = f"UPDATE books SET {field} = %s WHERE id = %s"
    
    with conn.cursor() as cur:
        cur.execute(sql, (value, book_id))
    return True

def delete_book(conn, book_id: int):
    """Удаляет книгу и все связанные с ней записи о взятии/возврате."""
    with conn.cursor() as cur:
        # Сначала удаляем связанные записи в borrowed_books, чтобы не нарушать целостность данных
        cur.execute("DELETE FROM borrowed_books WHERE book_id = %s", (book_id,))
        # Теперь удаляем саму книгу
        cur.execute("DELETE FROM books WHERE id = %s", (book_id,))
    return True

def add_new_book(conn, book_data: dict):
    """Добавляет новую книгу в базу данных."""
    sql = """
        INSERT INTO books (name, author, genre, description, cover_image_id)
        VALUES (%(name)s, %(author)s, %(genre)s, %(description)s, %(cover_image_id)s)
        RETURNING id;
    """
    with conn.cursor() as cur:
        cur.execute(sql, book_data)
        new_book_id = cur.fetchone()[0]
    return new_book_id

def get_unique_genres(conn):
    """Возвращает список всех уникальных жанров из таблицы книг."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT genre FROM books WHERE genre IS NOT NULL AND genre != '' ORDER BY genre")
        genres = [row[0] for row in cur.fetchall()]
    return genres

def get_available_books_by_genre(conn, genre: str, limit: int, offset: int):
    """Возвращает порцию свободных книг указанного жанра и их общее количество."""
    with conn.cursor() as cur:
        # 1. Находим ID книг, которые сейчас на руках
        cur.execute("SELECT book_id FROM borrowed_books WHERE return_date IS NULL")
        borrowed_ids = {row[0] for row in cur.fetchall()}
        borrowed_ids_tuple = tuple(borrowed_ids) if borrowed_ids else (None,)

        # 2. Считаем общее количество доступных книг в жанре
        cur.execute(
            "SELECT COUNT(*) FROM books WHERE genre = %s AND id NOT IN %s",
            (genre, borrowed_ids_tuple)
        )
        total_books = cur.fetchone()[0]

        # 3. Получаем порцию книг для текущей страницы
        cur.execute(
            """
            SELECT b.id, b.name, a.name as author
            FROM books b
            JOIN authors a ON b.author_id = a.id
            WHERE b.genre = %s AND b.id NOT IN %s
            ORDER BY b.name
            LIMIT %s OFFSET %s
            """,
            (genre, borrowed_ids_tuple, limit, offset)
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        books_on_page = [dict(zip(columns, row)) for row in rows]

    return books_on_page, total_books

def search_available_books(conn, search_term: str, limit: int, offset: int):
    """
    Ищет ДОСТУПНЫЕ книги по части названия или автора (с пагинацией).
    """
    with conn.cursor() as cur:
        # 1. Получаем ID всех книг, которые сейчас на руках
        cur.execute("SELECT book_id FROM borrowed_books WHERE return_date IS NULL")
        borrowed_ids = {row[0] for row in cur.fetchall()}
        borrowed_ids_tuple = tuple(borrowed_ids) if borrowed_ids else (None,)
        
        search_pattern = f"%{search_term}%"

        # 2. Считаем общее количество
        cur.execute(
            """
            SELECT COUNT(b.id) 
            FROM books b 
            JOIN authors a ON b.author_id = a.id 
            WHERE (b.name ILIKE %s OR a.name ILIKE %s) AND b.id NOT IN %s
            """,
            (search_pattern, search_pattern, borrowed_ids_tuple)
        )
        total_books = cur.fetchone()[0]

        # 3. Получаем порцию для страницы
        cur.execute(
            """
            SELECT b.id, b.name, a.name as author
            FROM books b
            JOIN authors a ON b.author_id = a.id
            WHERE (b.name ILIKE %s OR a.name ILIKE %s) AND b.id NOT IN %s
            ORDER BY b.name
            LIMIT %s OFFSET %s
            """,
            (search_pattern, search_pattern, borrowed_ids_tuple, limit, offset)
        )
        
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        books_on_page = [dict(zip(columns, row)) for row in rows]
                
    return books_on_page, total_books

def get_book_card_details(conn, book_id: int):
    """
    Возвращает все данные для карточки книги, включая статус доступности.
    """
    with conn.cursor() as cur:
        # 1. Проверяем, на руках ли книга
        cur.execute("SELECT 1 FROM borrowed_books WHERE book_id = %s AND return_date IS NULL", (book_id,))
        is_borrowed = cur.fetchone() is not None

        # 2. Получаем основные данные о книге
        cur.execute(
            """
            SELECT b.id, b.name, a.name as author, b.genre, b.description, b.cover_image_id
            FROM books b
            JOIN authors a ON b.author_id = a.id
            WHERE b.id = %s
            """,
            (book_id,)
        )
        row = cur.fetchone()
        if not row:
            raise NotFoundError("Книга с таким ID не найдена.")

        columns = [desc[0] for desc in cur.description]
        book_details = dict(zip(columns, row))
        
        # 3. Добавляем статус доступности
        book_details['is_available'] = not is_borrowed
        return book_details
    
def update_user_full_name(conn, user_id: int, new_name: str):
    """Обновляет ФИО пользователя."""
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET full_name = %s WHERE id = %s", (new_name, user_id))
        if cur.rowcount == 0:
            raise NotFoundError("Пользователь с таким ID не найден для обновления ФИО.")
    return True

def update_user_contact(conn, user_id: int, new_contact: str):
    """Обновляет контактную информацию пользователя."""
    with conn.cursor() as cur:
        try:
            cur.execute("UPDATE users SET contact_info = %s WHERE id = %s", (new_contact, user_id))
            if cur.rowcount == 0:
                raise NotFoundError("Пользователь с таким ID не найден для обновления контакта.")
        except psycopg2.IntegrityError:
            conn.rollback()
            raise UserExistsError("Этот контакт уже используется другим пользователем.")
    return True

def update_user_password_by_id(conn, user_id: int, new_password: str):
    """Обновляет пароль пользователя по его ID."""
    hashed_pass = hash_password(new_password)
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed_pass, user_id))
        if cur.rowcount == 0:
            raise NotFoundError("Пользователь с таким ID не найден для обновления пароля.")
    return True

def set_registration_code(conn, user_id: int) -> str:
    """Генерирует, сохраняет и возвращает уникальный код регистрации для пользователя."""
    code = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET registration_code = %s WHERE id = %s", (code, user_id))
    return code

def link_telegram_id_by_code(conn, code: str, telegram_id: int, telegram_username: str):
    """Находит пользователя по коду регистрации и обновляет его telegram_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users 
            SET telegram_id = %s, telegram_username = %s 
            WHERE registration_code = %s
            RETURNING id
            """,
            (telegram_id, telegram_username, code)
        )
        if cur.fetchone() is None:
            raise NotFoundError("Пользователь с таким кодом регистрации не найден.")
        
def get_users_with_overdue_books(conn):
    """
    Возвращает список пользователей, у которых есть книги с истекшим сроком возврата.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                u.id as user_id, 
                u.username,
                b.name as book_name,
                bb.due_date
            FROM borrowed_books bb
            JOIN users u ON bb.user_id = u.id
            JOIN books b ON bb.book_id = b.id
            WHERE bb.return_date IS NULL AND bb.due_date < CURRENT_DATE
            """
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    
def get_users_with_books_due_soon(conn, days_ahead: int = 2):
    """
    Возвращает список пользователей, у которых срок возврата книги
    истекает ровно через 'days_ahead' дней.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                u.id as user_id,
                b.name as book_name,
                bb.due_date,
                bb.borrow_id
            FROM borrowed_books bb
            JOIN users u ON bb.user_id = u.id
            JOIN books b ON bb.book_id = b.id
            WHERE bb.return_date IS NULL AND bb.due_date = CURRENT_DATE + INTERVAL '%s day'
            """,
            (days_ahead,)
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def extend_due_date(conn, borrow_id: int):
    """
    Продлевает срок возврата книги, если это возможно.
    Возвращает новую дату или строку с причиной отказа.
    """
    with conn.cursor() as cur:
        # 1. Получаем информацию о текущем займе
        cur.execute("SELECT book_id, extensions_count FROM borrowed_books WHERE borrow_id = %s", (borrow_id,))
        borrow_info = cur.fetchone()
        if not borrow_info:
            return "Запись о взятии книги не найдена."
        
        book_id, extensions_count = borrow_info

        # 2. Проверяем, не превышен ли лимит продлений
        if extensions_count >= 1:
            return "Вы уже продлевали эту книгу. Повторное продление невозможно."

        # 3. Проверяем, нет ли на книгу активных резерваций
        cur.execute("SELECT 1 FROM reservations WHERE book_id = %s AND notified = FALSE", (book_id,))
        if cur.fetchone():
            return "Невозможно продлить: эту книгу уже зарезервировал другой читатель."

        # 4. Если все проверки пройдены, обновляем запись
        cur.execute(
            """
            UPDATE borrowed_books
            SET due_date = due_date + INTERVAL '7 day',
                extensions_count = extensions_count + 1
            WHERE borrow_id = %s
            RETURNING due_date;
            """,
            (borrow_id,)
        )
        new_due_date = cur.fetchone()[0]
        return new_due_date

def get_top_rated_books(conn, limit: int = 5):
    """
    Возвращает список книг с самым высоким средним рейтингом.
    Учитывает только книги, имеющие 2 или более оценки.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                b.name,
                a.name as author,
                AVG(r.rating) as avg_rating,
                COUNT(r.rating) as votes
            FROM ratings r
            JOIN books b ON r.book_id = b.id
            JOIN authors a ON b.author_id = a.id
            GROUP BY b.id, a.name
            HAVING COUNT(r.rating) >= 2 -- Отсекаем книги с одной случайной оценкой
            ORDER BY avg_rating DESC, votes DESC -- Сортируем по рейтингу, затем по количеству голосов
            LIMIT %s;
            """,
            (limit,)
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]