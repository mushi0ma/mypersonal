# init_db.py
import os
import psycopg2
from db_utils import get_db_connection

def initialize_database():
    """Создает все необходимые таблицы с корректной схемой."""
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
            author_id INTEGER REFERENCES authors(id) ON DELETE SET NULL,
            genre VARCHAR(100),
            description TEXT,
            cover_image_id VARCHAR(255),
            total_quantity INTEGER NOT NULL,
            available_quantity INTEGER NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            telegram_id BIGINT UNIQUE,
            telegram_username VARCHAR(255), -- Ограничение UNIQUE убрано
            full_name VARCHAR(255) NOT NULL,
            dob VARCHAR(10),
            contact_info VARCHAR(255) UNIQUE NOT NULL,
            status VARCHAR(50),
            password_hash VARCHAR(255) NOT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            registration_code VARCHAR(36) UNIQUE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS borrowed_books (
            borrow_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
            borrow_date DATE NOT NULL DEFAULT CURRENT_DATE,
            due_date DATE NOT NULL,
            return_date DATE,
            extensions_count INTEGER DEFAULT 0 NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
            reservation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified BOOLEAN DEFAULT FALSE,
            UNIQUE(user_id, book_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ratings (
            rating_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            UNIQUE(user_id, book_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for command in commands:
                    cur.execute(command)
        print("✅ Схема базы данных успешно инициализирована.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при инициализации схемы базы данных: {e}")

def seed_data():
    """Заполняет таблицы авторов и книг полными начальными данными."""
    authors_to_add = [
        "Михаил Булгаков", "Федор Достоевский", "Лев Толстой",
        "Антон Чехов", "Александр Пушкин", "Фрэнк Герберт", "Айзек Азимов"
    ]
    books_to_add = [
        ("Мастер и Маргарита", "Михаил Булгаков", "Роман", "Мистический роман о визите дьявола в Москву.", 5),
        ("Собачье сердце", "Михаил Булгаков", "Повесть", "Сатирическая повесть об опасных социальных экспериментах.", 3),
        ("Преступление и наказание", "Федор Достоевский", "Роман", "История бедного студента Раскольникова.", 4),
        ("Война и мир", "Лев Толстой", "Роман-эпопея", "Масштабное произведение об эпохе наполеоновских войн.", 3),
        ("Капитанская дочка", "Александр Пушкин", "Исторический роман", "История любви на фоне пугачёвского восстания.", 5),
        ("Дюна", "Фрэнк Герберт", "Фантастика", "Эпическая сага о планете Арракис и борьбе за власть.", 2),
        ("Основание", "Айзек Азимов", "Фантастика", "История о падении Галактической Империи и плане ученых.", 1)
    ]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # --- Логика заполнения ---
                author_ids = {name: i + 1 for i, name in enumerate(authors_to_add)}
                cur.execute("INSERT INTO authors (name) VALUES " + ", ".join(["(%s)"] * len(authors_to_add)) + " ON CONFLICT (name) DO NOTHING", authors_to_add)

                for book_title, author_name, genre, description, quantity in books_to_add:
                    author_id = author_ids.get(author_name)
                    if author_id:
                        cur.execute(
                            """
                            INSERT INTO books (name, author_id, genre, description, total_quantity, available_quantity)
                            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING
                            """, (book_title, author_id, genre, description, quantity, quantity)
                        )
        print("✅ Таблицы авторов и книг успешно заполнены.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"❌ Ошибка при заполнении таблиц: {e}")

if __name__ == '__main__':
    print("--- Шаг 1: Инициализация схемы базы данных ---")
    initialize_database()
    print("\n--- Шаг 2: Заполнение начальными данными ---")
    seed_data()