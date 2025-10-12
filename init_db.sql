-- Таблица авторов
CREATE TABLE IF NOT EXISTS authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

-- Таблица книг
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    author_id INTEGER REFERENCES authors(id) ON DELETE CASCADE,
    genre VARCHAR(100),
    description TEXT,
    cover_image_id VARCHAR(255),
    total_quantity INTEGER NOT NULL CHECK (total_quantity >= 0),
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0)
);

-- Таблица пользователей
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

-- Таблица заимствованных книг
CREATE TABLE IF NOT EXISTS borrowed_books (
    borrow_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    borrow_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    return_date DATE,
    extensions_count INTEGER DEFAULT 0 NOT NULL CHECK (extensions_count >= 0)
);

-- Таблица бронирований
CREATE TABLE IF NOT EXISTS reservations (
    reservation_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    reservation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, book_id)
);

-- Таблица запросов на книги
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

-- Таблица оценок
CREATE TABLE IF NOT EXISTS ratings (
    rating_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    UNIQUE(user_id, book_id)
);

-- Таблица уведомлений
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица логов активности
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица копий книг
CREATE TABLE IF NOT EXISTS book_copies (
    id SERIAL PRIMARY KEY,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    serial_number VARCHAR(50) UNIQUE NOT NULL,
    condition VARCHAR(50) DEFAULT 'good',
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==============================================================================
-- СОЗДАНИЕ ИНДЕКСОВ
-- ==============================================================================

CREATE INDEX IF NOT EXISTS idx_books_author ON books(author_id);
CREATE INDEX IF NOT EXISTS idx_borrowed_books_user ON borrowed_books(user_id);
CREATE INDEX IF NOT EXISTS idx_borrowed_books_book ON borrowed_books(book_id);
CREATE INDEX IF NOT EXISTS idx_borrowed_books_return ON borrowed_books(return_date);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_book ON ratings(book_id);
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_user ON activity_log(user_id);

-- ==============================================================================
-- НАЧАЛЬНЫЕ ДАННЫЕ (seed data)
-- ==============================================================================

-- Вставка авторов
INSERT INTO authors (name) VALUES 
    ('Михаил Булгаков'),
    ('Федор Достоевский'),
    ('Лев Толстой'),
    ('Антон Чехов'),
    ('Александр Пушкин'),
    ('Фрэнк Герберт'),
    ('Айзек Азимов'),
    ('Джордж Оруэлл'),
    ('Олдос Хаксли'),
    ('Дж. Р. Р. Толкин'),
    ('Рэй Брэдбери'),
    ('Артур Конан Дойл'),
    ('Агата Кристи'),
    ('Стивен Кинг'),
    ('Дэн Симмонс'),
    ('братья Стругацкие'),
    ('Виктор Пелевин'),
    ('Габриэль Гарсиа Маркес'),
    ('Эрнест Хемингуэй'),
    ('Джером Сэлинджер'),
    ('Кен Кизи'),
    ('Харпер Ли'),
    ('Дэниел Киз'),
    ('Дуглас Адамс'),
    ('Станислав Лем'),
    ('Филип К. Дик'),
    ('Уильям Гибсон'),
    ('Нил Стивенсон'),
    ('Харуки Мураками'),
    ('Анджей Сапковский')
ON CONFLICT (name) DO NOTHING;

-- Вставка книг (используем подзапросы для получения author_id)
INSERT INTO books (name, author_id, genre, description, total_quantity, available_quantity) VALUES 
    ('Мастер и Маргарита', (SELECT id FROM authors WHERE name='Михаил Булгаков'), 'Роман', 'Мистический роман о визите дьявола в Москву.', 5, 5),
    ('Собачье сердце', (SELECT id FROM authors WHERE name='Михаил Булгаков'), 'Повесть', 'Сатирическая повесть об опасных социальных экспериментах.', 3, 3),
    ('Преступление и наказание', (SELECT id FROM authors WHERE name='Федор Достоевский'), 'Роман', 'История бедного студента Раскольникова.', 4, 4),
    ('Война и мир', (SELECT id FROM authors WHERE name='Лев Толстой'), 'Роман-эпопея', 'Масштабное произведение об эпохе наполеоновских войн.', 3, 3),
    ('Капитанская дочка', (SELECT id FROM authors WHERE name='Александр Пушкин'), 'Исторический роман', 'История любви на фоне пугачёвского восстания.', 5, 5),
    ('Дюна', (SELECT id FROM authors WHERE name='Фрэнк Герберт'), 'Фантастика', 'Эпическая сага о планете Арракис и борьбе за власть.', 2, 2),
    ('Основание', (SELECT id FROM authors WHERE name='Айзек Азимов'), 'Фантастика', 'История о падении Галактической Империи и плане ученых.', 1, 1),
    ('1984', (SELECT id FROM authors WHERE name='Джордж Оруэлл'), 'Антиутопия', 'Роман о тоталитарном обществе и Большом Брате.', 4, 4),
    ('О дивный новый мир', (SELECT id FROM authors WHERE name='Олдос Хаксли'), 'Антиутопия', 'Изображение общества потребления, доведенного до абсурда.', 3, 3),
    ('Властелин колец', (SELECT id FROM authors WHERE name='Дж. Р. Р. Толкин'), 'Фэнтези', 'Эпическое путешествие хоббита Фродо для уничтожения Кольца Всевластия.', 2, 2),
    ('451 градус по Фаренгейту', (SELECT id FROM authors WHERE name='Рэй Брэдбери'), 'Фантастика', 'Мир будущего, в котором все книги подлежат сожжению.', 4, 4),
    ('Приключения Шерлока Холмса', (SELECT id FROM authors WHERE name='Артур Конан Дойл'), 'Детектив', 'Сборник рассказов о знаменитом лондонском сыщике.', 6, 6),
    ('Убийство в Восточном экспрессе', (SELECT id FROM authors WHERE name='Агата Кристи'), 'Детектив', 'Эркюль Пуаро расследует загадочное убийство в поезде.', 5, 5),
    ('Сияние', (SELECT id FROM authors WHERE name='Стивен Кинг'), 'Ужасы', 'История семьи, изолированной в отеле с темным прошлым.', 3, 3),
    ('Гиперион', (SELECT id FROM authors WHERE name='Дэн Симмонс'), 'Фантастика', 'Паломничество к таинственным Гробницам Времени на планете Гиперион.', 2, 2),
    ('Пикник на обочине', (SELECT id FROM authors WHERE name='братья Стругацкие'), 'Фантастика', 'Повесть о сталкерах, рискующих жизнью в аномальной Зоне.', 4, 4),
    ('Чапаев и Пустота', (SELECT id FROM authors WHERE name='Виктор Пелевин'), 'Постмодернизм', 'Роман, действие которого происходит в двух реальностях.', 3, 3),
    ('Сто лет одиночества', (SELECT id FROM authors WHERE name='Габриэль Гарсиа Маркес'), 'Магический реализм', 'История семьи Буэндиа в вымышленном городе Макондо.', 2, 2),
    ('Старик и море', (SELECT id FROM authors WHERE name='Эрнест Хемингуэй'), 'Повесть', 'Повесть-притча о героической и трагической борьбе старого рыбака с гигантской рыбой.', 5, 5),
    ('Над пропастью во ржи', (SELECT id FROM authors WHERE name='Джером Сэлинджер'), 'Роман', 'История о нескольких днях из жизни 17-летнего Холдена Колфилда.', 4, 4),
    ('Пролетая над гнездом кукушки', (SELECT id FROM authors WHERE name='Кен Кизи'), 'Роман', 'Противостояние бунтаря Макмёрфи и деспотичной сестры Рэтчед в психбольнице.', 3, 3),
    ('Убить пересмешника', (SELECT id FROM authors WHERE name='Харпер Ли'), 'Роман', 'История о судебном процессе в южном американском городке глазами ребенка.', 4, 4),
    ('Цветы для Элджернона', (SELECT id FROM authors WHERE name='Дэниел Киз'), 'Фантастика', 'Трогательная история о научном эксперименте по повышению интеллекта.', 5, 5),
    ('Автостопом по галактике', (SELECT id FROM authors WHERE name='Дуглас Адамс'), 'Юмористическая фантастика', 'Космические приключения последнего выжившего землянина Артура Дента.', 3, 3),
    ('Солярис', (SELECT id FROM authors WHERE name='Станислав Лем'), 'Фантастика', 'Роман о столкновении человеческого разума с непостижимым внеземным интеллектом.', 2, 2),
    ('Мечтают ли андроиды об электроовцах?', (SELECT id FROM authors WHERE name='Филип К. Дик'), 'Киберпанк', 'История охотника за головами, выслеживающего беглых андроидов.', 3, 3),
    ('Нейромант', (SELECT id FROM authors WHERE name='Уильям Гибсон'), 'Киберпанк', 'Роман, определивший каноны жанра киберпанк.', 2, 2),
    ('Лавина', (SELECT id FROM authors WHERE name='Нил Стивенсон'), 'Киберпанк', 'Роман о Метавселенной, вирусах и древней шумерской культуре.', 1, 1),
    ('Охота на овец', (SELECT id FROM authors WHERE name='Харуки Мураками'), 'Магический реализм', 'Сюрреалистический детектив о поисках мистической овцы.', 3, 3),
    ('Ведьмак: Последнее желание', (SELECT id FROM authors WHERE name='Анджей Сапковский'), 'Фэнтези', 'Сборник рассказов о ведьмаке Геральте из Ривии.', 4, 4)
ON CONFLICT (name) DO NOTHING;

-- Вывод информации
DO $$
BEGIN
    RAISE NOTICE '✅ База данных успешно инициализирована';
    RAISE NOTICE '📚 Авторов: %', (SELECT COUNT(*) FROM authors);
    RAISE NOTICE '📖 Книг: %', (SELECT COUNT(*) FROM books);
END $$;