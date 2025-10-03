import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Перед импортом db_data, убедимся что db_utils доступен
# (на случай если вы уже переименовали db_setup.py)
if os.path.exists('db_utils.py'):
    import db_utils
    
import db_data
from db_data import UserExistsError, NotFoundError

class TestDbData(unittest.TestCase):

    @patch('db_data.get_db_connection')
    def test_add_user_success(self, mock_get_db_connection):
        """Test that a user is added successfully with a username."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [1]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_db_connection.return_value.__enter__.return_value = mock_conn

        user_data = {
            'username': 'testuser123', # <-- ДОБАВЛЕНО
            'telegram_id': 12345,
            'telegram_username': 'testuser',
            'full_name': 'Test User',
            'dob': '01.01.2000',
            'contact_info': 'test@example.com',
            'status': 'студент',
            'password': 'password123'
        }

        user_id = db_data.add_user(user_data)

        self.assertEqual(user_id, 1)
        mock_cur.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('db_data.get_db_connection')
    def test_add_user_already_exists(self, mock_get_db_connection):
        """Test that adding a user who already exists raises an error."""
        import psycopg2
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = psycopg2.IntegrityError("User already exists")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_db_connection.return_value.__enter__.return_value = mock_conn

        user_data = {
            'username': 'testuser123', # <-- ДОБАВЛЕНО
            'telegram_id': 12345,
            'telegram_username': 'testuser',
            'full_name': 'Test User',
            'dob': '01.01.2000',
            'contact_info': 'test@example.com',
            'status': 'студент',
            'password': 'password123'
        }

        with self.assertRaises(UserExistsError):
            db_data.add_user(user_data)

        mock_conn.rollback.assert_called_once()

    @patch('db_data.get_db_connection')
    def test_get_user_by_login_found(self, mock_get_db_connection):
        """Test retrieving a user by login when the user is found."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        # Обновляем мок ответа, добавляя username
        mock_cur.description = [('id',), ('full_name',), ('contact_info',), ('username',)]
        mock_cur.fetchone.return_value = (1, 'Test User', 'test@example.com', 'testuser123')

        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_db_connection.return_value.__enter__.return_value = mock_conn

        user = db_data.get_user_by_login('testuser123')

        self.assertIsNotNone(user)
        self.assertEqual(user['full_name'], 'Test User')
        # Обновляем SQL-запрос, чтобы он соответствовал новой логике
        mock_cur.execute.assert_called_once_with(
            """
                SELECT id, full_name, contact_info, status, password_hash, telegram_id, telegram_username, username
                FROM users
                WHERE username = %s OR contact_info = %s OR telegram_username = %s
                """,
            ('testuser123', 'testuser123', 'testuser123')
        )

    @patch('db_data.get_db_connection')
    def test_get_user_by_login_not_found(self, mock_get_db_connection):
        """Test retrieving a user by login when the user is not found."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_get_db_connection.return_value.__enter__.return_value = mock_conn

        with self.assertRaises(NotFoundError):
            db_data.get_user_by_login('nonexistent_user')

if __name__ == '__main__':
    unittest.main()