# Руководство по тестированию Library Bot

## Подготовка окружения

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка тестовой базы данных

#### Создание тестовой БД в PostgreSQL:

```sql
CREATE DATABASE library_test;
CREATE USER test_user WITH PASSWORD 'test_password';
GRANT ALL PRIVILEGES ON DATABASE library_test TO test_user;
```

#### Настройка .env.test:

Скопируйте файл `.env.test.example` в `.env.test`:

```bash
cp .env.test.example .env.test
```

Отредактируйте `.env.test` с реальными данными:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=library_test
DB_USER=test_user
DB_PASSWORD=test_password

# Для тестов можно использовать фейковые токены
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
NOTIFICATION_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_NOTIFICATION_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_TELEGRAM_ID=123456789

# Celery в режиме eager для тестов
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_TASK_ALWAYS_EAGER=True
```

## Запуск тестов

### Все тесты:

```bash
python -m pytest tests/ -v
```

### Конкретный тестовый файл:

```bash
python -m pytest tests/test_db_data.py -v
```

### Конкретный тест:

```bash
python -m pytest tests/test_db_data.py::test_add_user_success -v
```

### С покрытием кода:

```bash
python -m pytest tests/ --cov=src --cov-report=html
```

## Описание тестов

### test_db_data.py
Базовые операции с базой данных:
- ✅ Добавление пользователей
- ✅ Поиск пользователей
- ✅ Добавление книг
- ✅ Взятие и возврат книг

### test_authors.py
Работа с авторами:
- ✅ Постраничный список авторов
- ✅ Детальная информация об авторе
- ✅ Получение книг автора

### test_search.py
Функции поиска:
- ✅ Поиск книг по названию и автору
- ✅ Получение уникальных жанров
- ✅ Фильтрация по жанрам

### test_ratings.py
Система рейтингов:
- ✅ Добавление оценок
- ✅ Обновление оценок
- ✅ Топ книг по рейтингу
- ✅ Статистика оценок
- ✅ Постраничный список оценок

### test_book_requests.py
Запросы на книги:
- ✅ Создание запроса
- ✅ Получение ожидающих запросов
- ✅ Одобрение запроса
- ✅ Отклонение запроса

### test_extended_features.py
Расширенные функции:
- ✅ Продление срока возврата
- ✅ Ограничение продлений
- ✅ Система резервирования
- ✅ Определение просроченных книг
- ✅ Книги с близким сроком возврата

### test_admin_bot_integration.py
Интеграционные тесты админ-бота:
- ✅ Команда статистики
- ✅ Полный цикл добавления книги

## Health Check

Проверка состояния всех компонентов системы:

```bash
python -m src.health_check
```

Проверяет:
- 📊 PostgreSQL (подключение, метрики)
- 💾 Redis (подключение, очередь Celery)
- 📱 Telegram API (все боты)
- ⚙️ Celery Workers
- 💿 Дисковое пространство

## Устранение проблем

### Ошибка: "ModuleNotFoundError: No module named 'pytest_asyncio'"

```bash
pip install pytest-asyncio
```

### Ошибка подключения к БД

Проверьте:
1. PostgreSQL запущен
2. База данных `library_test` создана
3. Данные в `.env.test` корректны
4. Пользователь имеет права на БД

### Ошибка: "asyncio event loop is closed"

Убедитесь, что в `pytest.ini` установлено:
```ini
[pytest]
asyncio_mode = auto
```

## Continuous Integration

Для CI/CD можно использовать:

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: library_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest tests/ -v
```

## Полезные команды

```bash
# Запуск с подробным выводом
python -m pytest tests/ -vv

# Остановка на первой ошибке
python -m pytest tests/ -x

# Запуск только упавших тестов
python -m pytest tests/ --lf

# Параллельный запуск (требует pytest-xdist)
python -m pytest tests/ -n auto

# Генерация HTML отчета
python -m pytest tests/ --html=report.html
```
