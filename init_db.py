# -*- coding: utf-8 -*-
import psycopg2
from db_setup import get_db_connection

def initialize_database():
    """Создает необходимые таблицы, если они не существуют."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            telegram_username VARCHAR(255) UNIQUE,
            full_name VARCHAR(255) NOT NULL,
            dob VARCHAR(10),
            contact_info VARCHAR(255) UNIQUE NOT NULL,
            status VARCHAR(50),
            password_hash VARCHAR(255) NOT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS authors (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS books (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            author_id INTEGER REFERENCES authors(id),
            year_published INTEGER,
            genre VARCHAR(100),
            total_quantity INTEGER NOT NULL,
            available_quantity INTEGER NOT NULL,
            average_rating NUMERIC(3, 2) DEFAULT 0.00
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS borrowed_books (
            borrow_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            book_id INTEGER NOT NULL REFERENCES books(id),
            borrow_date DATE NOT NULL DEFAULT CURRENT_DATE,
            return_date DATE,
            due_date DATE NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ratings (
            rating_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            book_id INTEGER NOT NULL REFERENCES books(id),
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            UNIQUE(user_id, book_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            book_id INTEGER NOT NULL REFERENCES books(id),
            reservation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            UNIQUE(user_id, book_id)
        );
        """
    )
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for command in commands:
                    cur.execute(command)
                conn.commit()
        print("✅ База данных успешно инициализирована.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")

if __name__ == '__main__':
    print("Инициализация схемы базы данных...")
    initialize_database()
    print("✅ Схема базы данных создана.")