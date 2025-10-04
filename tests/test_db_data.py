import pytest
import psycopg2
from db_data import add_user, get_user_by_login, UserExistsError, NotFoundError
from db_utils import get_db_connection

# A sample user for testing
SAMPLE_USER_DATA = {
    'username': 'testuser_pytest',
    'telegram_id': 123456789,
    'telegram_username': 'pytest_user',
    'full_name': 'Pytest Test User',
    'dob': '01.01.2001',
    'contact_info': 'pytest@example.com',
    'status': 'студент',
    'password': 'a_strong_password'
}

def test_add_user_success(test_db):
    """
    Test that a user is added successfully to the database.
    This is an integration test that interacts with the test_db.
    """
    # Call the function to add the user
    user_id = add_user(SAMPLE_USER_DATA)
    
    # Assert that a user ID was returned
    assert isinstance(user_id, int)

    # Verify the user was actually added by querying the database directly
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, full_name, contact_info, status FROM users WHERE id = %s",
                (user_id,)
            )
            user_record = cur.fetchone()

            assert user_record is not None
            assert user_record[0] == SAMPLE_USER_DATA['username']
            assert user_record[1] == SAMPLE_USER_DATA['full_name']
            assert user_record[2] == SAMPLE_USER_DATA['contact_info']
            assert user_record[3] == SAMPLE_USER_DATA['status']

def test_add_user_already_exists(test_db):
    """
    Test that adding a user with a duplicate username raises UserExistsError.
    """
    # Add the user for the first time (should succeed)
    add_user(SAMPLE_USER_DATA)

    # Try to add the same user again and expect an error
    with pytest.raises(UserExistsError):
        add_user(SAMPLE_USER_DATA)

def test_get_user_by_login_found(test_db):
    """
    Test retrieving a user by their login (username) when the user exists.
    """
    # First, add a user to the database
    add_user(SAMPLE_USER_DATA)

    # Now, try to retrieve the user
    user = get_user_by_login(SAMPLE_USER_DATA['username'])

    # Assert that the user was found and the data is correct
    assert user is not None
    assert user['username'] == SAMPLE_USER_DATA['username']
    assert user['full_name'] == SAMPLE_USER_DATA['full_name']

def test_get_user_by_login_not_found(test_db):
    """
    Test that trying to retrieve a non-existent user raises NotFoundError.
    """
    # In a clean database, no user should exist
    with pytest.raises(NotFoundError):
        get_user_by_login('non_existent_user')