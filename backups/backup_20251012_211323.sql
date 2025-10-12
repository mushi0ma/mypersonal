--
-- PostgreSQL database dump
--

\restrict ZuAk0QEzpRSO3zrORgseu19peYczJaWMaRKVfhmua3qNcVOGcY7bIYCwoMBbekg

-- Dumped from database version 14.19
-- Dumped by pg_dump version 15.14 (Debian 15.14-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activity_log (
    id integer NOT NULL,
    user_id integer,
    action character varying(100) NOT NULL,
    details text,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.activity_log OWNER TO postgres;

--
-- Name: activity_log_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.activity_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.activity_log_id_seq OWNER TO postgres;

--
-- Name: activity_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.activity_log_id_seq OWNED BY public.activity_log.id;


--
-- Name: authors; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.authors (
    id integer NOT NULL,
    name character varying(255) NOT NULL
);


ALTER TABLE public.authors OWNER TO postgres;

--
-- Name: authors_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.authors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.authors_id_seq OWNER TO postgres;

--
-- Name: authors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.authors_id_seq OWNED BY public.authors.id;


--
-- Name: book_copies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.book_copies (
    id integer NOT NULL,
    book_id integer,
    serial_number character varying(50) NOT NULL,
    condition character varying(50) DEFAULT 'good'::character varying,
    is_available boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.book_copies OWNER TO postgres;

--
-- Name: book_copies_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.book_copies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.book_copies_id_seq OWNER TO postgres;

--
-- Name: book_copies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.book_copies_id_seq OWNED BY public.book_copies.id;


--
-- Name: book_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.book_requests (
    id integer NOT NULL,
    user_id integer,
    book_name character varying(255) NOT NULL,
    author_name character varying(255) NOT NULL,
    genre character varying(100),
    description text,
    status character varying(20) DEFAULT 'pending'::character varying,
    rejection_reason text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT book_requests_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
);


ALTER TABLE public.book_requests OWNER TO postgres;

--
-- Name: book_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.book_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.book_requests_id_seq OWNER TO postgres;

--
-- Name: book_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.book_requests_id_seq OWNED BY public.book_requests.id;


--
-- Name: books; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.books (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    author_id integer,
    genre character varying(100),
    description text,
    cover_image_id character varying(255),
    total_quantity integer NOT NULL,
    available_quantity integer NOT NULL,
    CONSTRAINT books_available_quantity_check CHECK ((available_quantity >= 0)),
    CONSTRAINT books_total_quantity_check CHECK ((total_quantity >= 0))
);


ALTER TABLE public.books OWNER TO postgres;

--
-- Name: books_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.books_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.books_id_seq OWNER TO postgres;

--
-- Name: books_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.books_id_seq OWNED BY public.books.id;


--
-- Name: borrowed_books; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.borrowed_books (
    borrow_id integer NOT NULL,
    user_id integer,
    book_id integer,
    borrow_date date DEFAULT CURRENT_DATE NOT NULL,
    due_date date NOT NULL,
    return_date date,
    extensions_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT borrowed_books_extensions_count_check CHECK ((extensions_count >= 0))
);


ALTER TABLE public.borrowed_books OWNER TO postgres;

--
-- Name: borrowed_books_borrow_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.borrowed_books_borrow_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.borrowed_books_borrow_id_seq OWNER TO postgres;

--
-- Name: borrowed_books_borrow_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.borrowed_books_borrow_id_seq OWNED BY public.borrowed_books.borrow_id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer,
    text text NOT NULL,
    category character varying(50) NOT NULL,
    is_read boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.notifications OWNER TO postgres;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.notifications_id_seq OWNER TO postgres;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: ratings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ratings (
    rating_id integer NOT NULL,
    user_id integer,
    book_id integer,
    rating integer,
    CONSTRAINT ratings_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


ALTER TABLE public.ratings OWNER TO postgres;

--
-- Name: ratings_rating_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ratings_rating_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ratings_rating_id_seq OWNER TO postgres;

--
-- Name: ratings_rating_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ratings_rating_id_seq OWNED BY public.ratings.rating_id;


--
-- Name: reservations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reservations (
    reservation_id integer NOT NULL,
    user_id integer,
    book_id integer,
    reservation_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    notified boolean DEFAULT false
);


ALTER TABLE public.reservations OWNER TO postgres;

--
-- Name: reservations_reservation_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reservations_reservation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reservations_reservation_id_seq OWNER TO postgres;

--
-- Name: reservations_reservation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reservations_reservation_id_seq OWNED BY public.reservations.reservation_id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    telegram_id bigint,
    telegram_username character varying(255),
    full_name character varying(255) NOT NULL,
    dob character varying(10),
    contact_info character varying(255) NOT NULL,
    status character varying(50),
    password_hash character varying(255) NOT NULL,
    registration_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    registration_code character varying(36)
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: activity_log id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_log ALTER COLUMN id SET DEFAULT nextval('public.activity_log_id_seq'::regclass);


--
-- Name: authors id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.authors ALTER COLUMN id SET DEFAULT nextval('public.authors_id_seq'::regclass);


--
-- Name: book_copies id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_copies ALTER COLUMN id SET DEFAULT nextval('public.book_copies_id_seq'::regclass);


--
-- Name: book_requests id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_requests ALTER COLUMN id SET DEFAULT nextval('public.book_requests_id_seq'::regclass);


--
-- Name: books id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.books ALTER COLUMN id SET DEFAULT nextval('public.books_id_seq'::regclass);


--
-- Name: borrowed_books borrow_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.borrowed_books ALTER COLUMN borrow_id SET DEFAULT nextval('public.borrowed_books_borrow_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: ratings rating_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ratings ALTER COLUMN rating_id SET DEFAULT nextval('public.ratings_rating_id_seq'::regclass);


--
-- Name: reservations reservation_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reservations ALTER COLUMN reservation_id SET DEFAULT nextval('public.reservations_reservation_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: activity_log; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.activity_log (id, user_id, action, details, "timestamp") FROM stdin;
\.


--
-- Data for Name: authors; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.authors (id, name) FROM stdin;
1	Михаил Булгаков
2	Федор Достоевский
3	Лев Толстой
4	Антон Чехов
5	Александр Пушкин
6	Фрэнк Герберт
7	Айзек Азимов
8	Джордж Оруэлл
9	Олдос Хаксли
10	Дж. Р. Р. Толкин
11	Рэй Брэдбери
12	Артур Конан Дойл
13	Агата Кристи
14	Стивен Кинг
15	Дэн Симмонс
16	братья Стругацкие
17	Виктор Пелевин
18	Габриэль Гарсиа Маркес
19	Эрнест Хемингуэй
20	Джером Сэлинджер
21	Кен Кизи
22	Харпер Ли
23	Дэниел Киз
24	Дуглас Адамс
25	Станислав Лем
26	Филип К. Дик
27	Уильям Гибсон
28	Нил Стивенсон
29	Харуки Мураками
30	Анджей Сапковский
\.


--
-- Data for Name: book_copies; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.book_copies (id, book_id, serial_number, condition, is_available, created_at) FROM stdin;
\.


--
-- Data for Name: book_requests; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.book_requests (id, user_id, book_name, author_name, genre, description, status, rejection_reason, created_at) FROM stdin;
\.


--
-- Data for Name: books; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.books (id, name, author_id, genre, description, cover_image_id, total_quantity, available_quantity) FROM stdin;
1	Мастер и Маргарита	1	Роман	Мистический роман о визите дьявола в Москву.	\N	5	5
2	Собачье сердце	1	Повесть	Сатирическая повесть об опасных социальных экспериментах.	\N	3	3
3	Преступление и наказание	2	Роман	История бедного студента Раскольникова.	\N	4	4
4	Война и мир	3	Роман-эпопея	Масштабное произведение об эпохе наполеоновских войн.	\N	3	3
5	Капитанская дочка	5	Исторический роман	История любви на фоне пугачёвского восстания.	\N	5	5
6	Дюна	6	Фантастика	Эпическая сага о планете Арракис и борьбе за власть.	\N	2	2
7	Основание	7	Фантастика	История о падении Галактической Империи и плане ученых.	\N	1	1
8	1984	8	Антиутопия	Роман о тоталитарном обществе и Большом Брате.	\N	4	4
9	О дивный новый мир	9	Антиутопия	Изображение общества потребления, доведенного до абсурда.	\N	3	3
10	Властелин колец	10	Фэнтези	Эпическое путешествие хоббита Фродо для уничтожения Кольца Всевластия.	\N	2	2
11	451 градус по Фаренгейту	11	Фантастика	Мир будущего, в котором все книги подлежат сожжению.	\N	4	4
12	Приключения Шерлока Холмса	12	Детектив	Сборник рассказов о знаменитом лондонском сыщике.	\N	6	6
13	Убийство в Восточном экспрессе	13	Детектив	Эркюль Пуаро расследует загадочное убийство в поезде.	\N	5	5
14	Сияние	14	Ужасы	История семьи, изолированной в отеле с темным прошлым.	\N	3	3
15	Гиперион	15	Фантастика	Паломничество к таинственным Гробницам Времени на планете Гиперион.	\N	2	2
16	Пикник на обочине	16	Фантастика	Повесть о сталкерах, рискующих жизнью в аномальной Зоне.	\N	4	4
17	Чапаев и Пустота	17	Постмодернизм	Роман, действие которого происходит в двух реальностях.	\N	3	3
18	Сто лет одиночества	18	Магический реализм	История семьи Буэндиа в вымышленном городе Макондо.	\N	2	2
19	Старик и море	19	Повесть	Повесть-притча о героической и трагической борьбе старого рыбака с гигантской рыбой.	\N	5	5
20	Над пропастью во ржи	20	Роман	История о нескольких днях из жизни 17-летнего Холдена Колфилда.	\N	4	4
21	Пролетая над гнездом кукушки	21	Роман	Противостояние бунтаря Макмёрфи и деспотичной сестры Рэтчед в психбольнице.	\N	3	3
22	Убить пересмешника	22	Роман	История о судебном процессе в южном американском городке глазами ребенка.	\N	4	4
23	Цветы для Элджернона	23	Фантастика	Трогательная история о научном эксперименте по повышению интеллекта.	\N	5	5
24	Автостопом по галактике	24	Юмористическая фантастика	Космические приключения последнего выжившего землянина Артура Дента.	\N	3	3
25	Солярис	25	Фантастика	Роман о столкновении человеческого разума с непостижимым внеземным интеллектом.	\N	2	2
26	Мечтают ли андроиды об электроовцах?	26	Киберпанк	История охотника за головами, выслеживающего беглых андроидов.	\N	3	3
27	Нейромант	27	Киберпанк	Роман, определивший каноны жанра киберпанк.	\N	2	2
28	Лавина	28	Киберпанк	Роман о Метавселенной, вирусах и древней шумерской культуре.	\N	1	1
29	Охота на овец	29	Магический реализм	Сюрреалистический детектив о поисках мистической овцы.	\N	3	3
30	Ведьмак: Последнее желание	30	Фэнтези	Сборник рассказов о ведьмаке Геральте из Ривии.	\N	4	4
\.


--
-- Data for Name: borrowed_books; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.borrowed_books (borrow_id, user_id, book_id, borrow_date, due_date, return_date, extensions_count) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.notifications (id, user_id, text, category, is_read, created_at) FROM stdin;
\.


--
-- Data for Name: ratings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ratings (rating_id, user_id, book_id, rating) FROM stdin;
\.


--
-- Data for Name: reservations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reservations (reservation_id, user_id, book_id, reservation_date, notified) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, username, telegram_id, telegram_username, full_name, dob, contact_info, status, password_hash, registration_date, registration_code) FROM stdin;
\.


--
-- Name: activity_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.activity_log_id_seq', 1, false);


--
-- Name: authors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.authors_id_seq', 30, true);


--
-- Name: book_copies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.book_copies_id_seq', 1, false);


--
-- Name: book_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.book_requests_id_seq', 1, false);


--
-- Name: books_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.books_id_seq', 30, true);


--
-- Name: borrowed_books_borrow_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.borrowed_books_borrow_id_seq', 1, false);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: ratings_rating_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ratings_rating_id_seq', 1, false);


--
-- Name: reservations_reservation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reservations_reservation_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 1, false);


--
-- Name: activity_log activity_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_pkey PRIMARY KEY (id);


--
-- Name: authors authors_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.authors
    ADD CONSTRAINT authors_name_key UNIQUE (name);


--
-- Name: authors authors_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.authors
    ADD CONSTRAINT authors_pkey PRIMARY KEY (id);


--
-- Name: book_copies book_copies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_copies
    ADD CONSTRAINT book_copies_pkey PRIMARY KEY (id);


--
-- Name: book_copies book_copies_serial_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_copies
    ADD CONSTRAINT book_copies_serial_number_key UNIQUE (serial_number);


--
-- Name: book_requests book_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_requests
    ADD CONSTRAINT book_requests_pkey PRIMARY KEY (id);


--
-- Name: books books_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_name_key UNIQUE (name);


--
-- Name: books books_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_pkey PRIMARY KEY (id);


--
-- Name: borrowed_books borrowed_books_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.borrowed_books
    ADD CONSTRAINT borrowed_books_pkey PRIMARY KEY (borrow_id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: ratings ratings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_pkey PRIMARY KEY (rating_id);


--
-- Name: ratings ratings_user_id_book_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_user_id_book_id_key UNIQUE (user_id, book_id);


--
-- Name: reservations reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_pkey PRIMARY KEY (reservation_id);


--
-- Name: reservations reservations_user_id_book_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_user_id_book_id_key UNIQUE (user_id, book_id);


--
-- Name: users users_contact_info_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_contact_info_key UNIQUE (contact_info);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_registration_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_registration_code_key UNIQUE (registration_code);


--
-- Name: users users_telegram_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_telegram_id_key UNIQUE (telegram_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_activity_log_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_activity_log_user ON public.activity_log USING btree (user_id);


--
-- Name: idx_books_author; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_books_author ON public.books USING btree (author_id);


--
-- Name: idx_borrowed_books_book; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_borrowed_books_book ON public.borrowed_books USING btree (book_id);


--
-- Name: idx_borrowed_books_return; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_borrowed_books_return ON public.borrowed_books USING btree (return_date);


--
-- Name: idx_borrowed_books_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_borrowed_books_user ON public.borrowed_books USING btree (user_id);


--
-- Name: idx_notifications_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_notifications_user ON public.notifications USING btree (user_id);


--
-- Name: idx_ratings_book; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ratings_book ON public.ratings USING btree (book_id);


--
-- Name: idx_ratings_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ratings_user ON public.ratings USING btree (user_id);


--
-- Name: idx_users_telegram; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_telegram ON public.users USING btree (telegram_id);


--
-- Name: activity_log activity_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: book_copies book_copies_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_copies
    ADD CONSTRAINT book_copies_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: book_requests book_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.book_requests
    ADD CONSTRAINT book_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: books books_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.authors(id) ON DELETE CASCADE;


--
-- Name: borrowed_books borrowed_books_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.borrowed_books
    ADD CONSTRAINT borrowed_books_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: borrowed_books borrowed_books_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.borrowed_books
    ADD CONSTRAINT borrowed_books_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: ratings ratings_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: ratings ratings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reservations reservations_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.books(id) ON DELETE CASCADE;


--
-- Name: reservations reservations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict ZuAk0QEzpRSO3zrORgseu19peYczJaWMaRKVfhmua3qNcVOGcY7bIYCwoMBbekg

