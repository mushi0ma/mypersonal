import subprocess
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# В backup_db.py, модифицировать:

def backup_database():
    """Создает резервную копию базы данных PostgreSQL."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.getenv('BACKUP_DIR', '/backups')
        
        os.makedirs(backup_dir, exist_ok=True)
        
        filename = f"{backup_dir}/backup_{timestamp}.sql"
        
        command = [
            'pg_dump',
            '-h', os.getenv('DB_HOST', 'localhost'),
            '-U', os.getenv('DB_USER', 'postgres'),
            '-d', os.getenv('DB_NAME', 'library_db'),
            '-f', filename,
            '--no-password'
        ]
        
        env = os.environ.copy()
        env['PGPASSWORD'] = os.getenv('DB_PASSWORD', '')
        
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            # ✅ ДОБАВИТЬ УВЕДОМЛЕНИЕ АДМИНУ
            file_size = os.path.getsize(filename) / (1024 * 1024)  # MB
            
            # Импортируем tasks здесь, чтобы избежать circular import
            from tasks import notify_admin
            notify_admin.delay(
                text=f"✅ **Backup успешно создан**\n\n"
                     f"📁 Файл: `{filename}`\n"
                     f"📊 Размер: {file_size:.2f} MB\n"
                     f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                category='backup'
            )
            
            logger.info(f"✅ Backup успешно создан: {filename}")
            cleanup_old_backups(backup_dir, days=30)
            return filename
        else:
            error_msg = f"❌ Ошибка создания backup: {result.stderr}"
            logger.error(error_msg)
            
            from tasks import notify_admin
            notify_admin.delay(
                text=f"❌ **Ошибка создания backup**\n\n{result.stderr}",
                category='backup_error'
            )
            return None
            
    except Exception as e:
        error_msg = f"❌ Исключение при создании backup: {e}"
        logger.error(error_msg)
        
        from tasks import notify_admin
        notify_admin.delay(
            text=f"❌ **Критическая ошибка backup**\n\n`{e}`",
            category='backup_error'
        )
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