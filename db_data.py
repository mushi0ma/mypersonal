# -*- coding: utf-8 -*-
# db_data.py - REVISED FOR CONNECTION POOLING AND EXCEPTION HANDLING
from db_utils import get_db_connection, hash_password
from datetime import datetime
import psycopg2

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


def get_user_by_login(login_query: str):
    """Ищет пользователя по УНИКАЛЬНОМУ полю: username, contact_info или telegram_username."""
    with get_db_connection() as conn:
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
                raise NotFoundError("Пользователь не найден.")

            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))

def add_user(data: dict):
    """Добавляет нового пользователя."""
    hashed_pass = hash_password(data['password'])
    with get_db_connection() as conn:
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

def get_all_user_ids():
    """Возвращает список всех telegram_id пользователей."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL")
                return [item[0] for item in cur.fetchall()]
            except psycopg2.Error as e:
                print(f"Ошибка при получении всех ID пользователей: {e}")
                return []

def add_reservation(user_id, book_id):
    """Добавляет запись о бронировании книги."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO reservations (user_id, book_id) VALUES (%s, %s)",
                    (user_id, book_id)
                )
                conn.commit()
                return "Успешно"
            except psycopg2.IntegrityError:
                conn.rollback()
                return "Вы уже зарезервировали эту книгу."
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось зарезервировать книгу: {e}")

def get_reservations_for_book(book_id):
    """Получает список пользователей, зарезервировавших книгу."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM reservations WHERE book_id = %s AND notified = FALSE ORDER BY reservation_date",
                (book_id,)
            )
            return [item[0] for item in cur.fetchall()]

def update_user_password(login_query: str, new_password: str):
    """Обновляет пароль пользователя."""
    hashed_pass = hash_password(new_password)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE contact_info = %s OR telegram_username = %s",
                    (hashed_pass, login_query, login_query)
                )
                if cur.rowcount == 0:
                    raise NotFoundError("Пользователь для обновления пароля не найден.")
                conn.commit()
                return "Успешно"
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось обновить пароль: {e}")

def get_borrowed_books(user_id: int):
    """Получает список книг, взятых пользователем."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT bb.borrow_id, b.id as book_id, b.name as book_name, a.name as author_name, bb.borrow_date
                FROM borrowed_books bb
                JOIN books b ON bb.book_id = b.id
                JOIN authors a ON b.author_id = a.id
                WHERE bb.user_id = %s AND bb.return_date IS NULL
                """,
                (user_id,)
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

def get_book_by_name(query: str):
    """Ищет книги по частичному совпадению в названии ИЛИ имени автора."""
    with get_db_connection() as conn:
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

def get_book_by_id(book_id: int):
    """Ищет одну книгу по её уникальному ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.name, a.name as author_name, b.available_quantity
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
            return dict(zip(columns, row))

def borrow_book(user_id: int, book_id: int):
    """Обрабатывает взятие книги: создает запись о займе и уменьшает количество доступных книг."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE books SET available_quantity = available_quantity - 1 WHERE id = %s AND available_quantity > 0",
                    (book_id,)
                )
                if cur.rowcount == 0:
                    return "Книга закончилась."
                cur.execute(
                    "INSERT INTO borrowed_books (user_id, book_id, due_date) VALUES (%s, %s, CURRENT_DATE + INTERVAL '14 day')",
                    (user_id, book_id)
                )
                conn.commit()
                return "Успешно"
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось взять книгу: {e}")

def return_book(borrow_id: int, book_id: int):
    """Обрабатывает возврат книги: обновляет запись о займе и увеличивает количество доступных книг."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE borrowed_books SET return_date = CURRENT_DATE WHERE borrow_id = %s",
                    (borrow_id,)
                )
                cur.execute(
                    "UPDATE books SET available_quantity = available_quantity + 1 WHERE id = %s",
                    (book_id,)
                )
                conn.commit()
                return "Успешно"
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось вернуть книгу: {e}")

def get_user_profile(user_id: int):
    """Получает полные данные профиля пользователя."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_name, telegram_username, status, contact_info, registration_date FROM users WHERE id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                raise NotFoundError("Профиль пользователя не найден.")
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))

def add_rating(user_id: int, book_id: int, rating: int):
    """Добавляет или обновляет оценку книги."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO ratings (user_id, book_id, rating) VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, book_id) DO UPDATE SET rating = EXCLUDED.rating;
                    """,
                    (user_id, book_id, rating)
                )
                conn.commit()
                return "Успешно"
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось добавить оценку: {e}")

def update_reservation_status(user_id, book_id, notified: bool):
    """Обновляет статус уведомления для брони."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE reservations SET notified = %s WHERE user_id = %s AND book_id = %s AND notified = FALSE",
                    (notified, user_id, book_id)
                )
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                raise DatabaseError(f"Не удалось обновить статус брони: {e}")

def get_user_borrow_history(user_id: int):
    """Получает всю историю заимствований пользователя."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.name as book_name, a.name as author_name, bb.borrow_date, bb.return_date
                FROM borrowed_books bb
                JOIN books b ON bb.book_id = b.id
                JOIN authors a ON b.author_id = a.id
                WHERE bb.user_id = %s
                ORDER BY bb.borrow_date DESC
                """,
                (user_id,)
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

def get_all_users(limit: int, offset: int):
    """Возвращает порцию пользователей для постраничной навигации и общее количество."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Получаем общее количество пользователей
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            # Получаем срез пользователей с использованием LIMIT и OFFSET
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