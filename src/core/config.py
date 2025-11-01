"""
Configuration module for the application.

This module loads settings from environment variables, providing a single source of truth for configuration.
It uses `python-dotenv` to load a `.env` file in the root directory for local development.

Security Note:
⚠️ NEVER store secrets directly in this file.
All sensitive data (API keys, passwords, etc.) must be stored in the .env file,
which is included in .gitignore to prevent it from being committed to version control.
"""
import os
import warnings
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists.
# This is especially useful for local development.
load_dotenv()

# --- Telegram Bot Tokens (REQUIRED) ---
# These tokens are essential for the bots to connect to the Telegram API.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN')
NOTIFICATION_BOT_TOKEN = os.getenv('NOTIFICATION_BOT_TOKEN')
ADMIN_NOTIFICATION_BOT_TOKEN = os.getenv('ADMIN_NOTIFICATION_BOT_TOKEN')

# --- Bot Usernames ---
# The username of the notification bot is used to create deep links for user registration.
NOTIFICATION_BOT_USERNAME = os.getenv('NOTIFICATION_BOT_USERNAME', 'YourNotificationBot')

# --- Admin User ID (REQUIRED) ---
# The Telegram user ID of the administrator, used for access control and notifications.
try:
    ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', 0))
except (ValueError, TypeError):
    ADMIN_TELEGRAM_ID = None

# --- Database Configuration (REQUIRED) ---
# Connection details for the PostgreSQL database.
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'db')  # Defaults to 'db' for Docker Compose networking
DB_PORT = os.getenv('DB_PORT', '5432')

# --- Celery & Redis Configuration (REQUIRED) ---
# Connection URLs for the Celery message broker and result backend (Redis).
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
# Flag to run Celery tasks synchronously for testing purposes.
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() in ('true', '1', 't')

# --- Email Configuration - SendGrid (OPTIONAL) ---
# API key for SendGrid, used for sending verification emails.
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL')

# --- Twilio Configuration (OPTIONAL) ---
# Credentials for Twilio, used for sending SMS notifications (if implemented).
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')


# --- Feature Flags ---
# These flags are automatically set based on the presence of optional service credentials.
# They allow the application to gracefully disable features that are not configured.
EMAIL_ENABLED = bool(SENDGRID_API_KEY and FROM_EMAIL)
SMS_ENABLED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)

# Display warnings for disabled optional features at startup.
if not EMAIL_ENABLED:
    warnings.warn("⚠️ SendGrid API key or FROM_EMAIL not configured. Email features will be disabled.")
if not SMS_ENABLED:
    warnings.warn("⚠️ Twilio credentials not configured. SMS features will be disabled.")

# --- Validation Function ---
def validate_config():
    """
    Validates that all critical environment variables are set.

    Raises:
        ValueError: If any of the required environment variables are missing.
    """
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "ADMIN_BOT_TOKEN": ADMIN_BOT_TOKEN,
        "NOTIFICATION_BOT_TOKEN": NOTIFICATION_BOT_TOKEN,
        "ADMIN_NOTIFICATION_BOT_TOKEN": ADMIN_NOTIFICATION_BOT_TOKEN,
        "ADMIN_TELEGRAM_ID": ADMIN_TELEGRAM_ID,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
    }
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    
    if missing_vars:
        raise ValueError(
            f"❌ Missing required environment variables: {', '.join(missing_vars)}\n"
            f"Please check your .env file and ensure all required variables are set."
        )
    
    # Provide a summary of the configuration status at startup.
    print("✅ All required environment variables are set.")
    print(f"📊 Feature Status: Email Enabled = {EMAIL_ENABLED}, SMS Enabled = {SMS_ENABLED}")

# To enable automatic validation upon import, uncomment the following line:
# validate_config()
