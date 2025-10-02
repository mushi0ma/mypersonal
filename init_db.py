# init_db.py
import os
import psycopg2
from db_setup import get_db_connection

def initialize_database():
    """Создает все необходимые таблицы, если они не существуют."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS authors (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS books (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            author_id INTEGER REFERENCES authors(id),
            total_quantity INTEGER NOT NULL,
            available_quantity INTEGER NOT NULL
        );
        """,
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
        CREATE TABLE IF NOT EXISTS borrowed_books (
            borrow_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            book_id INTEGER REFERENCES books(id),
            borrow_date DATE NOT NULL DEFAULT CURRENT_DATE,
            due_date DATE NOT NULL,
            return_date DATE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            book_id INTEGER REFERENCES books(id),
            reservation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            UNIQUE(user_id, book_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ratings (
            rating_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            book_id INTEGER REFERENCES books(id),
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
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
        print("✅ Схема базы данных успешно инициализирована.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при инициализации схемы базы данных: {e}")

def seed_data():
    """Заполняет таблицы авторов и книг начальными данными."""
    authors_to_add = [
        "Михаил Булгаков",
        "Федор Достоевский",
        "Лев Толстой",
        "Антон Чехов",
        "Александр Пушкин"
    ]
    
    # Структура: (Название, Имя автора, Общее количество)
    books_to_add = [
        ("Мастер и Маргарита", "Михаил Булгаков", 5),
        ("Собачье сердце", "Михаил Булгаков", 3),
        ("Преступление и наказание", "Федор Достоевский", 4),
        ("Идиот", "Федор Достоевский", 2),
        ("Война и мир", "Лев Толстой", 3),
        ("Анна Каренина", "Лев Толстой", 4),
        ("Вишневый сад", "Антон Чехов", 6),
        ("Капитанская дочка", "Александр Пушкин", 5)
    ]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                author_ids = {}
                # Добавляем авторов и получаем их ID
                for author_name in authors_to_add:
                    # ON CONFLICT DO NOTHING - чтобы не было ошибки при повторном запуске
                    cur.execute(
                        "INSERT INTO authors (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING id, name",
                        (author_name,)
                    )
                    row = cur.fetchone()
                    if row:
                        author_ids[row[1]] = row[0]

                # Если ID не были добавлены, получаем существующие
                if not author_ids:
                    cur.execute("SELECT id, name FROM authors")
                    for row in cur.fetchall():
                        author_ids[row[1]] = row[0]

                # Добавляем книги
                for book_title, author_name, quantity in books_to_add:
                    author_id = author_ids.get(author_name)
                    if author_id:
                        cur.execute(
                            """
                            INSERT INTO books (name, author_id, total_quantity, available_quantity)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (name) DO NOTHING
                            """,
                            (book_title, author_id, quantity, quantity)
                        )
            conn.commit()
        print("✅ Таблицы авторов и книг успешно заполнены начальными данными.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при заполнении таблиц: {e}")


if __name__ == '__main__':
    print("--- Шаг 1: Инициализация схемы базы данных ---")
    initialize_database()
    print("\n--- Шаг 2: Заполнение начальными данными ---")
    seed_data()