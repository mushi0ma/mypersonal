# src/init_db.py
import asyncio
import asyncpg
from src.core.db.utils import get_db_connection, init_db_pool, close_db_pool

SCHEMA_COMMANDS = (
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
        author_id INTEGER REFERENCES authors(id) ON DELETE CASCADE,
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
        telegram_username VARCHAR(255),
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
    CREATE TABLE IF NOT EXISTS book_requests (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        book_name VARCHAR(255) NOT NULL,
        author_name VARCHAR(255) NOT NULL,
        genre VARCHAR(100),
        description TEXT,
        status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
        rejection_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """,
    """
    CREATE TABLE IF NOT EXISTS book_copies (
        id SERIAL PRIMARY KEY,
        book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        serial_number VARCHAR(50) UNIQUE NOT NULL,
        condition VARCHAR(50) DEFAULT 'good',
        is_available BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

)

async def initialize_database():
    """Асинхронно создает все необходимые таблицы с корректной схемой."""
    try:
        async with get_db_connection() as conn:
            for command in SCHEMA_COMMANDS:
                await conn.execute(command)
        print("✅ Схема базы данных успешно инициализирована.")
    except (asyncpg.PostgresError, ConnectionError) as e:
        print(f"❌ Ошибка при инициализации схемы базы данных: {e}")

async def seed_data():
    """Асинхронно заполняет таблицы авторов и книг начальными данными."""
    authors_to_add = list(set([
        "Михаил Булгаков", "Федор Достоевский", "Лев Толстой", "Антон Чехов", "Александр Пушкин",
        "Фрэнк Герберт", "Айзек Азимов", "Джордж Оруэлл", "Олдос Хаксли", "Дж. Р. Р. Толкин",
        "Рэй Брэдбери", "Артур Конан Дойл", "Агата Кристи", "Стивен Кинг", "Дэн Симмонс",
        "братья Стругацкие", "Виктор Пелевин", "Габриэль Гарсиа Маркес", "Эрнест Хемингуэй",
        "Джером Сэлинджер", "Кен Кизи", "Харпер Ли", "Дэниел Киз", "Дуглас Адамс", "Станислав Лем",
        "Филип К. Дик", "Уильям Гибсон", "Нил Стивенсон", "Харуки Мураками", "Анджей Сапковский"
    ]))

    books_to_add = [
        ("Мастер и Маргарита", "Михаил Булгаков", "Роман", "Мистический роман о визите дьявола в Москву.", 5),
        ("Собачье сердце", "Михаил Булгаков", "Повесть", "Сатирическая повесть об опасных социальных экспериментах.", 3),
        ("Преступление и наказание", "Федор Достоевский", "Роман", "История бедного студента Раскольникова.", 4),
        ("Война и мир", "Лев Толстой", "Роман-эпопея", "Масштабное произведение об эпохе наполеоновских войн.", 3),
        ("Капитанская дочка", "Александр Пушкин", "Исторический роман", "История любви на фоне пугачёвского восстания.", 5),
        ("Дюна", "Фрэнк Герберт", "Фантастика", "Эпическая сага о планете Арракис и борьбе за власть.", 2),
        ("Основание", "Айзек Азимов", "Фантастика", "История о падении Галактической Империи и плане ученых.", 1),
        ("1984", "Джордж Оруэлл", "Антиутопия", "Роман о тоталитарном обществе и Большом Брате.", 4),
        ("О дивный новый мир", "Олдос Хаксли", "Антиутопия", "Изображение общества потребления, доведенного до абсурда.", 3),
        ("Властелин колец", "Дж. Р. Р. Толкин", "Фэнтези", "Эпическое путешествие хоббита Фродо для уничтожения Кольца Всевластия.", 2),
        ("451 градус по Фаренгейту", "Рэй Брэдбери", "Фантастика", "Мир будущего, в котором все книги подлежат сожжению.", 4),
        ("Приключения Шерлока Холмса", "Артур Конан Дойл", "Детектив", "Сборник рассказов о знаменитом лондонском сыщике.", 6),
        ("Убийство в Восточном экспрессе", "Агата Кристи", "Детектив", "Эркюль Пуаро расследует загадочное убийство в поезде.", 5),
        ("Сияние", "Стивен Кинг", "Ужасы", "История семьи, изолированной в отеле с темным прошлым.", 3),
        ("Гиперион", "Дэн Симмонс", "Фантастика", "Паломничество к таинственным Гробницам Времени на планете Гиперион.", 2),
        ("Пикник на обочине", "братья Стругацкие", "Фантастика", "Повесть о сталкерах, рискующих жизнью в аномальной Зоне.", 4),
        ("Чапаев и Пустота", "Виктор Пелевин", "Постмодернизм", "Роман, действие которого происходит в двух реальностях.", 3),
        ("Сто лет одиночества", "Габриэль Гарсиа Маркес", "Магический реализм", "История семьи Буэндиа в вымышленном городе Макондо.", 2),
        ("Старик и море", "Эрнест Хемингуэй", "Повесть", "Повесть-притча о героической и трагической борьбе старого рыбака с гигантской рыбой.", 5),
        ("Над пропастью во ржи", "Джером Сэлинджер", "Роман", "История о нескольких днях из жизни 17-летнего Холдена Колфилда.", 4),
        ("Пролетая над гнездом кукушки", "Кен Кизи", "Роман", "Противостояние бунтаря Макмёрфи и деспотичной сестры Рэтчед в психбольнице.", 3),
        ("Убить пересмешника", "Харпер Ли", "Роман", "История о судебном процессе в южном американском городке глазами ребенка.", 4),
        ("Цветы для Элджернона", "Дэниел Киз", "Фантастика", "Трогательная история о научном эксперименте по повышению интеллекта.", 5),
        ("Автостопом по галактике", "Дуглас Адамс", "Юмористическая фантастика", "Космические приключения последнего выжившего землянина Артура Дента.", 3),
        ("Солярис", "Станислав Лем", "Фантастика", "Роман о столкновении человеческого разума с непостижимым внеземным интеллектом.", 2),
        ("Мечтают ли андроиды об электроовцах?", "Филип К. Дик", "Киберпанк", "История охотника за головами, выслеживающего беглых андроидов.", 3),
        ("Нейромант", "Уильям Гибсон", "Киберпанк", "Роман, определивший каноны жанра киберпанк.", 2),
        ("Лавина", "Нил Стивенсон", "Киберпанк", "Роман о Метавселенной, вирусах и древней шумерской культуре.", 1),
        ("Охота на овец", "Харуки Мураками", "Магический реализм", "Сюрреалистический детектив о поисках мистической овцы.", 3),
        ("Ведьмак: Последнее желание", "Анджей Сапковский", "Фэнтези", "Сборник рассказов о ведьмаке Геральте из Ривии.", 4)
    ]
    try:
        async with get_db_connection() as conn:
            # 1. Сначала вставляем всех авторов
            # asyncpg не поддерживает `VALUES %s, %s`, используем `executemany`
            await conn.executemany("INSERT INTO authors (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                                   [(author,) for author in authors_to_add])

            # 2. Теперь получаем актуальный словарь 'имя' -> 'id' из базы данных
            author_records = await conn.fetch("SELECT id, name FROM authors")
            author_ids = {record['name']: record['id'] for record in author_records}

            # 3. Вставляем книги, используя актуальные ID авторов
            books_data_to_insert = []
            for book_title, author_name, genre, description, quantity in books_to_add:
                author_id = author_ids.get(author_name)
                if author_id:
                    books_data_to_insert.append(
                        (book_title, author_id, genre, description, quantity, quantity)
                    )

            if books_data_to_insert:
                await conn.executemany(
                    """
                    INSERT INTO books (name, author_id, genre, description, total_quantity, available_quantity)
                    VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (name) DO NOTHING
                    """, books_data_to_insert
                )
        print("✅ Таблицы авторов и книг успешно заполнены.")
    except (asyncpg.PostgresError, ConnectionError) as e:
        print(f"❌ Ошибка при заполнении таблиц: {e}")

async def main():
    """Основная функция для запуска инициализации."""
    # Инициализируем пул соединений
    await init_db_pool()

    print("--- Шаг 1: Инициализация схемы базы данных ---")
    await initialize_database()

    print("\n--- Шаг 2: Заполнение начальными данными ---")
    await seed_data()

    # Закрываем пул соединений
    await close_db_pool()

if __name__ == '__main__':
    # Загружаем переменные окружения из основного .env файла
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(main())