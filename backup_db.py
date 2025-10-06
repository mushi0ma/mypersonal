import subprocess
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backup_database():
    """Создает резервную копию базы данных PostgreSQL."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.getenv('BACKUP_DIR', '/backups')
        
        # Создаем директорию для бэкапов, если её нет
        os.makedirs(backup_dir, exist_ok=True)
        
        filename = f"{backup_dir}/backup_{timestamp}.sql"
        
        # Формируем команду pg_dump
        command = [
            'pg_dump',
            '-h', os.getenv('DB_HOST', 'localhost'),
            '-U', os.getenv('DB_USER', 'postgres'),
            '-d', os.getenv('DB_NAME', 'library_db'),
            '-f', filename,
            '--no-password'  # Используйте PGPASSWORD в переменных окружения
        ]
        
        # Устанавливаем пароль через переменную окружения
        env = os.environ.copy()
        env['PGPASSWORD'] = os.getenv('DB_PASSWORD', '')
        
        # Выполняем backup
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Backup успешно создан: {filename}")
            # Опционально: удаляем старые бэкапы (старше 30 дней)
            cleanup_old_backups(backup_dir, days=30)
            return filename
        else:
            logger.error(f"❌ Ошибка создания backup: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Исключение при создании backup: {e}")
        return None

def cleanup_old_backups(backup_dir, days=30):
    """Удаляет бэкапы старше заданного количества дней."""
    import time
    
    now = time.time()
    cutoff = now - (days * 86400)
    
    for filename in os.listdir(backup_dir):
        if filename.startswith('backup_') and filename.endswith('.sql'):
            filepath = os.path.join(backup_dir, filename)
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                logger.info(f"🗑️ Удален старый backup: {filename}")

if __name__ == "__main__":
    backup_database()