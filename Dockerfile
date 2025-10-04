# syntax=docker/dockerfile:1

# Используем конкретную версию Python
ARG PYTHON_VERSION=3.11.9
FROM python:${PYTHON_VERSION}-slim as base

# Отключаем создание .pyc файлов и буферизацию вывода
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Создаем пользователя с ограниченными правами для безопасности
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Устанавливаем зависимости, используя кэширование Docker
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Переключаемся на пользователя с ограниченными правами
USER appuser

# Копируем исходный код приложения
COPY . .

# Команда по умолчанию для запуска контейнера.
# Будет переопределена в docker-compose.yaml для каждого сервиса.
CMD ["python", "librarybot.py"]