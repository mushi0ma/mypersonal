# -*- coding: utf-8 -*-
# db_data.py - REVISED FOR CONNECTION POOLING AND EXCEPTION HANDLING
from db_setup import get_db_connection, hash_password
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
    """Ищет пользователя по УНИКАЛЬНОМУ полю: contact_info или telegram_username."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, full_name, contact_info, status, password_hash, telegram_id, telegram_username
                FROM users 
                WHERE contact_info = %s OR telegram_username = %s
                """,
                (login_query, login_query)
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
                    INSERT INTO users (telegram_id, telegram_username, full_name, dob, contact_info, status, password_hash, registration_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (data.get('telegram_id'), data.get('telegram_username'), data['full_name'], data['dob'], data['contact_info'], data['status'], hashed_pass, datetime.now())
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

# ... (Остальные функции `db_data.py` переписываются по тому же принципу)
# Для краткости я опущу их здесь, но полный файл будет содержать
# обновленные `get_user_profile`, `update_user_password`, `get_book_by_name`, `borrow_book`, `return_book`, `add_rating`
# и новые функции для поиска, истории, бронирования и администрирования.
# Полная версия этого файла будет очень большой, но логика везде одинакова:
# 1. Использовать `with get_db_connection() as conn:`.
# 2. Оборачивать логику в `try...except`.
# 3. Пробрасывать кастомные исключения (`raise NotFoundError`, `raise DatabaseError`).