# tests/conftest.py
import pytest_asyncio
import os
from dotenv import load_dotenv
import asyncpg

# Загружаем переменные из .env.test ПЕРЕД импортом других модулей
load_dotenv(dotenv_path='.env.test')

# Импортируем схему из ее нового местоположения в src
from src.init_db import SCHEMA_COMMANDS

@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    Для каждого теста:
    1. Создает соединение с БД.
    2. Создает чистую схему.
    3. Предоставляет соединение тесту.
    4. Закрывает соединение.
    Это обеспечивает максимальную изоляцию, решая проблемы с event loop.
    """
    conn = None
    try:
        conn = await asyncpg.connect(
            database="library_db",
            user="postgres",
            password="12345",
            host="test_db",
            port="5432"
        )
        # Полная очистка и создание схемы для каждого теста
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for command in SCHEMA_COMMANDS:
            await conn.execute(command)

        yield conn

    finally:
        if conn:
            await conn.close()