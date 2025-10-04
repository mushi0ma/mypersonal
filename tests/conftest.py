import pytest
import os
import psycopg2
from dotenv import load_dotenv

# Add the root directory to the Python path to ensure imports work correctly
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from init_db import initialize_database, seed_data
from db_utils import get_db_connection, close_db_pool

@pytest.fixture(scope="function")
def test_db():
    """
    Fixture to set up and tear down the test database.

    This fixture runs for each test function. It loads the test environment,
    initializes a clean database schema, yields to the test, and then
    drops all tables to ensure test isolation.
    """
    # Close any existing pool, load test env, then initialize
    close_db_pool()
    load_dotenv(dotenv_path='.env.test', override=True)

    # Initialize the database schema
    initialize_database()

    # Yield to the test function
    yield

    # Teardown: Drop all tables to clean up
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get all table names in the public schema
                cur.execute("""
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public';
                """)
                tables = cur.fetchall()

                # Drop all tables
                for table in tables:
                    cur.execute(f"DROP TABLE IF EXISTS {table[0]} CASCADE;")

                conn.commit()
    except (psycopg2.Error, ConnectionError) as e:
        print(f"Error during test database cleanup: {e}")
    finally:
        # Ensure the pool is closed after tests
        close_db_pool()

@pytest.fixture(scope="function")
def seeded_test_db(test_db):
    """
    Fixture that depends on test_db and also seeds initial data.

    Use this fixture for tests that require the initial set of authors
    and books to be present in the database.
    """
    seed_data()
    yield