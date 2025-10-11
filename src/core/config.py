"""
Configuration module - loads settings from environment variables.
⚠️ NEVER store secrets directly in this file!
All sensitive data must be in .env file (which is in .gitignore)
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==========================================
# Telegram Bot Tokens
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN')
NOTIFICATION_BOT_TOKEN = os.getenv('NOTIFICATION_BOT_TOKEN')
ADMIN_NOTIFICATION_BOT_TOKEN = os.getenv('ADMIN_NOTIFICATION_BOT_TOKEN')

# Usernames
NOTIFICATION_BOT_USERNAME = os.getenv('NOTIFICATION_BOT_USERNAME', 'YourNotificationBot')

# Admin ID
try:
    ADMIN_TELEGRAM_ID = int(os.getenv('ADMIN_TELEGRAM_ID', 0))
except (ValueError, TypeError):
    ADMIN_TELEGRAM_ID = None

# ==========================================
# Database Configuration
# ==========================================
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')

# ==========================================
# Celery & Redis Configuration
# ==========================================
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() in ('true', '1', 't')

# ==========================================
# Email Configuration (SendGrid)
# ==========================================
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL')

# ==========================================
# Twilio Configuration (if needed)
# ==========================================
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

# ==========================================
# Validation Function
# ==========================================
def validate_config():
    """Validates that all critical environment variables are set."""
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
            f"Please check your .env file!"
        )
    
    print("✅ All required environment variables are set!")

# Call validation when this module is imported
# Comment out if you want to validate manually
# validate_config()