.PHONY: help build up down restart logs ps clean prune shell exec test

# Цвета для вывода
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RED    := $(shell tput -Txterm setaf 1)
BLUE   := $(shell tput -Txterm setaf 4)
RESET  := $(shell tput -Txterm sgr0)

# Переменные проекта
DOCKER_COMPOSE = docker-compose
BOTS_SERVICE = bots
DB_SERVICE = db
REDIS_SERVICE = redis
CELERY_WORKER = celery_worker
CELERY_BEAT = celery_beat

help: ## Показать эту справку
	@echo "$(GREEN)Доступные команды:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'

# ============================================================================
# ОСНОВНЫЕ КОМАНДЫ ЗАПУСКА
# ============================================================================

init: ## Полная инициализация проекта (остановка, БД, миграции, запуск)
	@echo "$(BLUE)>>> Шаг 1: Остановка и очистка контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) down -v
	@echo "$(BLUE)>>> Шаг 2: Запуск базы данных...$(RESET)"
	$(DOCKER_COMPOSE) up -d $(DB_SERVICE)
	@echo "$(YELLOW)>>> Ожидание запуска БД (10 секунд)...$(RESET)"
	@sleep 10
	@echo "$(BLUE)>>> Шаг 3: Инициализация таблиц и данных...$(RESET)"
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/init_db.py
	@echo "$(BLUE)>>> Шаг 4: Запуск всех контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) up --build -d
	@echo "$(GREEN)✓ Проект успешно инициализирован!$(RESET)"

build: ## Собрать Docker образы
	@echo "$(BLUE)>>> Сборка образов...$(RESET)"
	$(DOCKER_COMPOSE) build

up: ## Запустить все контейнеры
	@echo "$(BLUE)>>> Запуск контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) up -d

up-build: ## Собрать и запустить все контейнеры
	@echo "$(BLUE)>>> Сборка и запуск контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) up --build -d

dev: ## Запустить в режиме разработки с выводом логов
	@echo "$(BLUE)>>> Запуск в режиме разработки...$(RESET)"
	$(DOCKER_COMPOSE) up --build

# ============================================================================
# УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ
# ============================================================================

db-start: ## Запустить только базу данных
	@echo "$(BLUE)>>> Запуск базы данных...$(RESET)"
	$(DOCKER_COMPOSE) up -d $(DB_SERVICE)

db-init: ## Создать таблицы и заполнить БД
	@echo "$(BLUE)>>> Инициализация базы данных...$(RESET)"
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/init_db.py

db-reset: ## Полный сброс БД: остановка, очистка, запуск, инициализация
	@echo "$(RED)>>> Внимание! Все данные будут удалены!$(RESET)"
	@echo "$(YELLOW)>>> Остановка и удаление volumes...$(RESET)"
	$(DOCKER_COMPOSE) down -v
	@echo "$(BLUE)>>> Запуск пустой БД...$(RESET)"
	$(DOCKER_COMPOSE) up -d $(DB_SERVICE)
	@echo "$(YELLOW)>>> Ожидание запуска БД (10 секунд)...$(RESET)"
	@sleep 10
	@echo "$(BLUE)>>> Создание таблиц и заполнение данных...$(RESET)"
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/init_db.py
	@echo "$(GREEN)✓ База данных сброшена и инициализирована!$(RESET)"

db-shell: ## Открыть psql shell базы данных PostgreSQL
	$(DOCKER_COMPOSE) exec $(DB_SERVICE) psql -U postgres -d $${DB_NAME:-library_db}

db-backup: ## Создать бэкап базы данных
	@echo "$(BLUE)>>> Создание бэкапа...$(RESET)"
	@mkdir -p backups
	docker exec $$(docker-compose ps -q $(DB_SERVICE)) pg_dump -U postgres $${DB_NAME:-library_db} > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✓ Бэкап создан в папке backups/$(RESET)"

db-restore: ## Восстановить БД из бэкапа (make db-restore FILE=backups/backup.sql)
	@echo "$(BLUE)>>> Восстановление из бэкапа: $(FILE)$(RESET)"
	docker exec -i $$(docker-compose ps -q $(DB_SERVICE)) psql -U postgres $${DB_NAME:-library_db} < $(FILE)

# ============================================================================
# УПРАВЛЕНИЕ КОНТЕЙНЕРАМИ
# ============================================================================

down: ## Остановить все контейнеры
	@echo "$(YELLOW)>>> Остановка контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) down

down-v: ## Остановить и удалить контейнеры с volumes (удаление данных БД)
	@echo "$(RED)>>> Остановка и удаление volumes...$(RESET)"
	$(DOCKER_COMPOSE) down -v

restart: ## Перезапустить все контейнеры
	@echo "$(BLUE)>>> Перезапуск контейнеров...$(RESET)"
	$(DOCKER_COMPOSE) restart

restart-bots: ## Перезапустить только боты
	@echo "$(BLUE)>>> Перезапуск ботов...$(RESET)"
	$(DOCKER_COMPOSE) restart $(BOTS_SERVICE)

restart-celery: ## Перезапустить Celery worker и beat
	@echo "$(BLUE)>>> Перезапуск Celery...$(RESET)"
	$(DOCKER_COMPOSE) restart $(CELERY_WORKER) $(CELERY_BEAT)

stop: ## Остановить все контейнеры (без удаления)
	$(DOCKER_COMPOSE) stop

start: ## Запустить остановленные контейнеры
	$(DOCKER_COMPOSE) start

rebuild: ## Пересобрать и перезапустить все контейнеры
	@echo "$(BLUE)>>> Пересборка проекта...$(RESET)"
	$(DOCKER_COMPOSE) down
	$(DOCKER_COMPOSE) build --no-cache
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Проект пересобран!$(RESET)"

# ============================================================================
# ЛОГИ И МОНИТОРИНГ
# ============================================================================

logs: ## Показать логи всех контейнеров
	$(DOCKER_COMPOSE) logs -f

logs-bots: ## Показать логи ботов
	$(DOCKER_COMPOSE) logs -f $(BOTS_SERVICE)

logs-db: ## Показать логи базы данных
	$(DOCKER_COMPOSE) logs -f $(DB_SERVICE)

logs-celery: ## Показать логи Celery worker
	$(DOCKER_COMPOSE) logs -f $(CELERY_WORKER)

logs-beat: ## Показать логи Celery beat
	$(DOCKER_COMPOSE) logs -f $(CELERY_BEAT)

logs-redis: ## Показать логи Redis
	$(DOCKER_COMPOSE) logs -f $(REDIS_SERVICE)

ps: ## Показать статус контейнеров
	$(DOCKER_COMPOSE) ps

status: ## Показать детальный статус проекта
	@echo "$(GREEN)=== Docker контейнеры ===$(RESET)"
	@$(DOCKER_COMPOSE) ps
	@echo "\n$(GREEN)=== Docker образы ===$(RESET)"
	@docker images | grep mypersonal || echo "Нет образов"
	@echo "\n$(GREEN)=== Docker volumes ===$(RESET)"
	@docker volume ls | grep mypersonal || echo "Нет volumes"

health: ## Проверить healthcheck всех сервисов
	@echo "$(GREEN)=== Health Check ===$(RESET)"
	@docker ps --format "table {{.Names}}\t{{.Status}}" | grep mypersonal

# ============================================================================
# РАБОТА С КОНТЕЙНЕРАМИ
# ============================================================================

shell: ## Открыть bash в контейнере ботов
	$(DOCKER_COMPOSE) exec $(BOTS_SERVICE) /bin/bash

sh: ## Открыть sh в контейнере ботов
	$(DOCKER_COMPOSE) exec $(BOTS_SERVICE) /bin/sh

shell-db: ## Открыть bash в контейнере БД
	$(DOCKER_COMPOSE) exec $(DB_SERVICE) /bin/bash

shell-celery: ## Открыть bash в контейнере Celery
	$(DOCKER_COMPOSE) exec $(CELERY_WORKER) /bin/bash

exec: ## Выполнить команду в контейнере ботов (make exec CMD="ls -la")
	$(DOCKER_COMPOSE) exec $(BOTS_SERVICE) $(CMD)

run: ## Выполнить разовую команду (make run CMD="python src/health_check.py")
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) $(CMD)

# ============================================================================
# РАБОТА С ОТДЕЛЬНЫМИ БОТАМИ
# ============================================================================

run-library: ## Запустить только library_bot
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/library_bot/main.py

run-admin: ## Запустить только admin_bot
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/admin_bot/main.py

run-notification: ## Запустить только notification_bot
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/notification_bot.py

run-audit: ## Запустить только audit_bot
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/audit_bot.py

health-check: ## Запустить проверку здоровья системы
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/health_check.py

# ============================================================================
# ОЧИСТКА
# ============================================================================

clean: ## Остановить и удалить контейнеры, сети, volumes
	@echo "$(YELLOW)>>> Очистка проекта...$(RESET)"
	$(DOCKER_COMPOSE) down -v

clean-all: ## Остановить и удалить контейнеры, сети, volumes, образы
	@echo "$(RED)>>> Полная очистка проекта...$(RESET)"
	$(DOCKER_COMPOSE) down -v --rmi all

prune: ## Удалить неиспользуемые Docker объекты (глобально)
	@echo "$(YELLOW)>>> Очистка неиспользуемых Docker объектов...$(RESET)"
	docker system prune -af

prune-volumes: ## Удалить неиспользуемые volumes
	@echo "$(YELLOW)>>> Очистка неиспользуемых volumes...$(RESET)"
	docker volume prune -f

# ============================================================================
# ТЕСТИРОВАНИЕ И РАЗРАБОТКА
# ============================================================================

test: ## Запустить тесты
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) pytest tests/

test-verbose: ## Запустить тесты с подробным выводом
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) pytest tests/ -v

test-coverage: ## Запустить тесты с покрытием кода
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) pytest tests/ --cov=src --cov-report=html

install: ## Установить зависимости Python
	$(DOCKER_COMPOSE) exec $(BOTS_SERVICE) pip install -r requirements.txt

requirements: ## Обновить requirements.txt
	$(DOCKER_COMPOSE) exec $(BOTS_SERVICE) pip freeze > requirements.txt

lint: ## Проверить код (flake8)
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) flake8 src/

format: ## Форматировать код (black)
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) black src/

format-check: ## Проверить форматирование без изменений
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) black --check src/

# ============================================================================
# CELERY УПРАВЛЕНИЕ
# ============================================================================

celery-status: ## Показать статус Celery worker
	$(DOCKER_COMPOSE) exec $(CELERY_WORKER) celery -A src.core.tasks.celery_app status

celery-purge: ## Очистить очередь задач Celery
	$(DOCKER_COMPOSE) exec $(CELERY_WORKER) celery -A src.core.tasks.celery_app purge

celery-inspect: ## Показать активные задачи Celery
	$(DOCKER_COMPOSE) exec $(CELERY_WORKER) celery -A src.core.tasks.celery_app inspect active

# ============================================================================
# БЫСТРЫЕ СЦЕНАРИИ
# ============================================================================

quick-restart: ## Быстрый перезапуск ботов (без пересборки)
	@echo "$(BLUE)>>> Быстрый перезапуск ботов...$(RESET)"
	$(DOCKER_COMPOSE) restart $(BOTS_SERVICE)
	@echo "$(GREEN)✓ Боты перезапущены!$(RESET)"

fresh-start: ## Свежий старт: очистка + полная инициализация
	@echo "$(BLUE)>>> Свежий старт проекта...$(RESET)"
	@$(MAKE) down-v
	@$(MAKE) init
	@echo "$(GREEN)✓ Проект готов к работе!$(RESET)"

deploy: ## Деплой: остановка, сборка, инициализация, запуск
	@echo "$(BLUE)>>> Деплой проекта...$(RESET)"
	$(DOCKER_COMPOSE) down
	$(DOCKER_COMPOSE) build
	$(DOCKER_COMPOSE) up -d $(DB_SERVICE)
	@sleep 10
	$(DOCKER_COMPOSE) run --rm $(BOTS_SERVICE) python src/init_db.py
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Деплой завершен!$(RESET)"

# ============================================================================
# ИНФОРМАЦИЯ
# ============================================================================

env-check: ## Проверить наличие .env файла
	@if [ -f .env ]; then \
		echo "$(GREEN)✓ Файл .env найден$(RESET)"; \
	else \
		echo "$(RED)✗ Файл .env не найден! Скопируйте .env.example в .env$(RESET)"; \
	fi