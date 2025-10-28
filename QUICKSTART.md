# 🚀 Быстрый старт Library Bot

## Исправленные проблемы (28.10.2025)

✅ Добавлены версии пакетов в `requirements.txt`  
✅ Исправлена проверка диска для Windows в `health_check.py`  
✅ Добавлены колонки `is_banned` и `force_logout` в схему БД  
✅ Создан `.env.test.example` для тестов  
✅ Обновлен `.gitignore`  

## Установка и запуск

### 1. Клонирование и установка зависимостей

```bash
git clone <your-repo>
cd mypersonal
pip install -r requirements.txt
```

### 2. Настройка окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
```

Обязательные параметры:
- `TELEGRAM_BOT_TOKEN` - токен основного бота
- `ADMIN_BOT_TOKEN` - токен админ-бота  
- `NOTIFICATION_BOT_TOKEN` - токен бота уведомлений
- `ADMIN_NOTIFICATION_BOT_TOKEN` - токен аудит-бота
- `ADMIN_TELEGRAM_ID` - ваш Telegram ID
- `DB_*` - параметры PostgreSQL
- `CELERY_*` - параметры Redis

### 3. Инициализация базы данных

```bash
python -m src.init_db
```

Это создаст все таблицы и заполнит начальными данными (30 книг).

### 4. Запуск сервисов

#### Вариант 1: Docker (рекомендуется)

```bash
docker-compose up -d
```

#### Вариант 2: Локально

**Терминал 1 - Redis:**
```bash
redis-server
```

**Терминал 2 - Celery Worker:**
```bash
celery -A src.core.tasks worker -l info
```

**Терминал 3 - Celery Beat (периодические задачи):**
```bash
celery -A src.core.tasks beat -l info
```

**Терминал 4 - Боты:**
```bash
python -m src.main
```

### 5. Проверка работоспособности

```bash
python -m src.health_check
```

Должен показать статус всех компонентов:
- ✅ PostgreSQL
- ✅ Redis
- ✅ Telegram API
- ✅ Celery Workers
- ✅ Disk Space

## Тестирование

### Настройка тестов

```bash
cp .env.test.example .env.test
# Отредактируйте .env.test с данными тестовой БД
```

### Запуск тестов

```bash
# Все тесты
python -m pytest tests/ -v

# Конкретный файл
python -m pytest tests/test_db_data.py -v

# С покрытием
python -m pytest tests/ --cov=src --cov-report=html
```

## Структура проекта

```
mypersonal/
├── src/
│   ├── main.py                 # Главный файл запуска
│   ├── health_check.py         # Мониторинг системы
│   ├── init_db.py              # Инициализация БД
│   ├── core/
│   │   ├── config.py           # Конфигурация
│   │   ├── tasks.py            # Celery задачи
│   │   └── db/
│   │       ├── utils.py        # Утилиты БД
│   │       └── data_access.py  # Доступ к данным
│   ├── library_bot/            # Основной бот
│   ├── admin_bot/              # Админ-бот
│   ├── notification_bot.py     # Бот уведомлений
│   └── audit_bot.py            # Аудит-бот
├── tests/                      # Тесты
├── requirements.txt            # Зависимости
├── .env.example                # Пример конфигурации
├── DEBUG_REPORT.md             # Отчет о дебаге
├── TESTING.md                  # Руководство по тестированию
└── QUICKSTART.md               # Этот файл
```

## Основные команды

### Управление ботами

```bash
# Запуск всех ботов
python -m src.main

# Запуск отдельного бота
python -m src.library_bot.main
python -m src.admin_bot.main
```

### Celery

```bash
# Worker
celery -A src.core.tasks worker -l info

# Beat (планировщик)
celery -A src.core.tasks beat -l info

# Flower (мониторинг)
celery -A src.core.tasks flower
```

### База данных

```bash
# Инициализация
python -m src.init_db

# Backup (вручную)
pg_dump -U user -d mydatabase > backup.sql

# Restore
psql -U user -d mydatabase < backup.sql
```

## Периодические задачи

Автоматически выполняются через Celery Beat:

- **10:00 ежедневно** - Проверка просроченных книг
- **03:00 ежедневно** - Backup базы данных
- **Каждый час** - Health check системы

## Troubleshooting

### Ошибка подключения к БД

```bash
# Проверьте статус PostgreSQL
sudo systemctl status postgresql

# Проверьте параметры в .env
cat .env | grep DB_
```

### Ошибка подключения к Redis

```bash
# Проверьте статус Redis
redis-cli ping
# Должен вернуть: PONG
```

### Боты не отвечают

1. Проверьте токены в `.env`
2. Убедитесь, что боты не запущены в другом месте
3. Проверьте логи: `tail -f app.log`

### Тесты падают

1. Убедитесь, что тестовая БД создана
2. Проверьте `.env.test`
3. Убедитесь, что PostgreSQL запущен

## Полезные ссылки

- [DEBUG_REPORT.md](DEBUG_REPORT.md) - Подробный отчет о найденных проблемах
- [TESTING.md](TESTING.md) - Руководство по тестированию
- [README.Docker.md](README.Docker.md) - Запуск через Docker

## Поддержка

При возникновении проблем:
1. Проверьте логи: `tail -f app.log librarybot.log`
2. Запустите health check: `python -m src.health_check`
3. Проверьте DEBUG_REPORT.md на наличие известных проблем
