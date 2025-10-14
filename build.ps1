# build.ps1 - PowerShell скрипт для управления Docker проектом
param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

# Переменные
$DOCKER_COMPOSE = "docker-compose"
$BOTS_SERVICE = "bots"
$DB_SERVICE = "db"
$REDIS_SERVICE = "redis"
$CELERY_WORKER = "celery_worker"
$CELERY_BEAT = "celery_beat"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Blue }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

# ============================================================================
# ВНУТРЕННИЕ HELPER-ФУНКЦИИ (для переиспользования кода)
# ============================================================================

function Initialize-Database {
    Write-Info ">>> Запуск базы данных..."
    & $DOCKER_COMPOSE up -d $DB_SERVICE
    
    Write-Warning ">>> Ожидание запуска БД (10 секунд)..."
    Start-Sleep -Seconds 10
    
    Write-Info ">>> Инициализация таблиц и данных через init_db.py..."
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/init_db.py
}

# ============================================================================
# ОСНОВНЫЕ КОМАНДЫ
# ============================================================================

function Show-Help {
    Write-Success "`nДоступные команды:"
    Write-Host ""
    Write-Host "--- Жизненный цикл ---"
    Write-Host "  up               " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить все контейнеры в фоне"
    Write-Host "  up-build         " -ForegroundColor Yellow -NoNewline; Write-Host "Собрать образы и запустить контейнеры"
    Write-Host "  down             " -ForegroundColor Yellow -NoNewline; Write-Host "Остановить контейнеры"
    Write-Host "  down-v           " -ForegroundColor Yellow -NoNewline; Write-Host "Остановить контейнеры и удалить volumes"
    Write-Host "  build            " -ForegroundColor Yellow -NoNewline; Write-Host "Собрать или пересобрать образы"
    Write-Host "  restart [svc..]  " -ForegroundColor Yellow -NoNewline; Write-Host "Перезапустить все или указанные сервисы (напр. 'dk restart bots')"
    Write-Host "  dev              " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить в режиме разработки с выводом логов"
    Write-Host ""
    Write-Host "--- Отладка и мониторинг ---"
    Write-Host "  logs [svc..]     " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи всех или указанных сервисов (напр. 'dk logs bots db')"
    Write-Host "  ps               " -ForegroundColor Yellow -NoNewline; Write-Host "Показать статус запущенных контейнеров"
    Write-Host "  status           " -ForegroundColor Yellow -NoNewline; Write-Host "Показать детальный статус проекта (контейнеры, образы, volumes)"
    Write-Host ""
    Write-Host "--- Управление Celery ---"
    Write-Host "  celery-restart   " -ForegroundColor Yellow -NoNewline; Write-Host "Перезапустить Celery worker и beat"
    Write-Host "  celery-logs      " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи Celery (worker + beat)"
    Write-Host "  celery-status    " -ForegroundColor Yellow -NoNewline; Write-Host "Проверить статус задач Celery"
    Write-Host ""
    Write-Host "--- Управление Redis ---"
    Write-Host "  redis-cli        " -ForegroundColor Yellow -NoNewline; Write-Host "Открыть Redis CLI для отладки"
    Write-Host "  redis-flush      " -ForegroundColor Yellow -NoNewline; Write-Host "Очистить все данные Redis (кэш, очереди)"
    Write-Host "  redis-info       " -ForegroundColor Yellow -NoNewline; Write-Host "Показать информацию о Redis (память, ключи)"
    Write-Host ""
    Write-Host "--- Взаимодействие и утилиты ---"
    Write-Host "  shell            " -ForegroundColor Yellow -NoNewline; Write-Host "Открыть интерактивную shell-сессию в контейнере ботов"
    Write-Host "  run <cmd>        " -ForegroundColor Yellow -NoNewline; Write-Host "Выполнить любую команду в контейнере ботов (напр. 'dk run pip freeze')"
    Write-Host "  test             " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить тесты (pytest)"
    Write-Host ""
    Write-Host "--- Управление Базой Данных ---"
    Write-Host "  db-shell         " -ForegroundColor Yellow -NoNewline; Write-Host "Открыть psql shell для подключения к БД"
    Write-Host "  db-backup        " -ForegroundColor Yellow -NoNewline; Write-Host "Создать бэкап базы данных"
    Write-Host "  db-restore       " -ForegroundColor Yellow -NoNewline; Write-Host "Восстановить БД из последнего бэкапа"
    Write-Host ""
    Write-Host "--- Полная перезагрузка проекта ---"
    Write-Host "  recreate         " -ForegroundColor Yellow -NoNewline; Write-Host "✨ Полностью пересоздать проект (down -v, build, up, init_db)"
    Write-Host "  deploy           " -ForegroundColor Yellow -NoNewline; Write-Host "Выкатить обновления кода без потери данных в БД"
    Write-Host ""
    Write-Host "--- Очистка ---"
    Write-Host "  prune            " -ForegroundColor Yellow -NoNewline; Write-Host "🗑️ Очистить Docker от всего мусора (контейнеры, сети, образы)"
    Write-Host ""
    Write-Info "Использование: dk <команда> [аргументы]"
    Write-Host ""
}

# --- Жизненный цикл ---
function Invoke-Up { & $DOCKER_COMPOSE up -d }
function Invoke-UpBuild { & $DOCKER_COMPOSE up --build -d }
function Invoke-Down { & $DOCKER_COMPOSE down }
function Invoke-DownV { & $DOCKER_COMPOSE down -v }
function Invoke-Build { & $DOCKER_COMPOSE build $Args }
function Invoke-Dev { & $DOCKER_COMPOSE up --build }

function Invoke-Restart {
    Write-Info ">>> Перезапуск сервисов: $($Args -join ', ' | ForEach-Object { if ($_ -eq '') { 'все' } else { $_ } })"
    & $DOCKER_COMPOSE restart $Args
}

# --- Отладка и мониторинг ---
function Invoke-Ps { & $DOCKER_COMPOSE ps }

function Invoke-Logs {
    Write-Info ">>> Показ логов для сервисов: $($Args -join ', ' | ForEach-Object { if ($_ -eq '') { 'все' } else { $_ } })"
    & $DOCKER_COMPOSE logs -f $Args
}

function Invoke-Status {
    Write-Success "=== Docker контейнеры ==="; & $DOCKER_COMPOSE ps
    Write-Host ""; Write-Success "=== Docker образы проекта ==="; docker images | Select-String "mypersonal"
    Write-Host ""; Write-Success "=== Docker volumes проекта ==="; docker volume ls | Select-String "mypersonal"
}

# --- Управление Celery ---
function Invoke-CeleryRestart {
    Write-Info ">>> Перезапуск Celery (worker + beat)..."
    & $DOCKER_COMPOSE restart $CELERY_WORKER $CELERY_BEAT
    Write-Success "✓ Celery перезапущен!"
}

function Invoke-CeleryLogs {
    Write-Info ">>> Логи Celery (worker + beat)..."
    & $DOCKER_COMPOSE logs -f $CELERY_WORKER $CELERY_BEAT
}

function Invoke-CeleryStatus {
    Write-Info ">>> Проверка статуса Celery..."
    & $DOCKER_COMPOSE exec $CELERY_WORKER celery -A src.core.tasks.celery_app inspect active
    Write-Host ""
    Write-Info ">>> Зарегистрированные задачи:"
    & $DOCKER_COMPOSE exec $CELERY_WORKER celery -A src.core.tasks.celery_app inspect registered
}

# --- Взаимодействие и утилиты ---
function Invoke-Shell { & $DOCKER_COMPOSE exec $BOTS_SERVICE /bin/bash }
function Invoke-Test { & $DOCKER_COMPOSE run --rm $BOTS_SERVICE pytest tests/ }

function Invoke-Run {
    if ($Args.Length -eq 0) {
        Write-Error "Необходимо указать команду для выполнения. Пример: dk run python src/health_check.py"
        return
    }
    Write-Info ">>> Выполнение команды в контейнере '$BOTS_SERVICE': $($Args -join ' ')"
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE $Args
}

# --- Управление Базой Данных ---
function Invoke-DbShell {
    $dbName = $env:DB_NAME
    if (-not $dbName) { $dbName = "library_db" }
    & $DOCKER_COMPOSE exec $DB_SERVICE psql -U postgres -d $dbName
}

function Invoke-DbBackup {
    Write-Info ">>> Создание бэкапа..."
    New-Item -ItemType Directory -Force -Path "backups" | Out-Null
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $dbName = $env:DB_NAME
    if (-not $dbName) { $dbName = "library_db" }
    
    $containerId = (& $DOCKER_COMPOSE ps -q $DB_SERVICE)
    docker exec $containerId pg_dump -U postgres $dbName > "backups/backup_$timestamp.sql"
    Write-Success "✓ Бэкап создан: backups/backup_$timestamp.sql"
}

function Invoke-DbRestore {
    Write-Info ">>> Восстановление базы данных из последнего бэкапа..."
    $latestBackup = Get-ChildItem -Path "backups" -Filter "*.sql" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    
    if (-not $latestBackup) {
        Write-Error "Бэкапы не найдены в папке /backups"
        return
    }

    Write-Warning "Найден последний бэкап: $($latestBackup.Name)"
    Write-Error "Текущая база данных будет полностью УДАЛЕНА и заменена данными из бэкапа!"
    Read-Host -Prompt "Нажмите Enter для продолжения или Ctrl+C для отмены"

    Write-Info ">>> Пересоздание сервиса БД..."
    & $DOCKER_COMPOSE rm -sfv $DB_SERVICE
    docker volume rm $(docker volume ls -q | Where-Object { $_ -like "*_db_data" }) 2>$null
    
    Write-Info ">>> Запуск нового контейнера БД..."
    & $DOCKER_COMPOSE up -d $DB_SERVICE
    
    Write-Warning ">>> Ожидание запуска БД (15 секунд)..."
    Start-Sleep -Seconds 15

    $dbName = $env:DB_NAME
    if (-not $dbName) { $dbName = "library_db" }
    
    Write-Info ">>> Загрузка данных из бэкапа..."
    Get-Content $latestBackup.FullName | docker exec -i $(& $DOCKER_COMPOSE ps -q $DB_SERVICE) psql -U postgres -d $dbName
    
    Write-Success "✓ База данных успешно восстановлена из файла $($latestBackup.Name)!"
}

# --- Полная перезагрузка и деплой ---
function Invoke-Recreate {
    Write-Info ">>> ✨ Полное пересоздание проекта с нуля..."
    
    Write-Warning "Шаг 1: Остановка и удаление всех контейнеров и volumes..."
    & $DOCKER_COMPOSE down -v
    
    Write-Info "Шаг 2: Сборка свежих образов..."
    & $DOCKER_COMPOSE build
    
    Write-Info "Шаг 3: Инициализация базы данных..."
    Initialize-Database
    
    Write-Info "Шаг 4: Запуск всех остальных сервисов..."
    & $DOCKER_COMPOSE up -d
    
    Write-Success "✓ Проект успешно пересоздан и запущен!"
    & $DOCKER_COMPOSE ps
}

function Invoke-Deploy {
    Write-Info ">>> Деплой обновлений кода (БД не затрагивается)..."
    
    Write-Warning "Остановка текущих сервисов..."
    & $DOCKER_COMPOSE down
    
    Write-Info "Сборка новых образов..."
    & $DOCKER_COMPOSE build
    
    Write-Info "Запуск обновленных сервисов..."
    & $DOCKER_COMPOSE up -d
    
    Write-Success "✓ Деплой завершен!"
    & $DOCKER_COMPOSE ps
}

# --- Очистка ---
function Invoke-Prune {
    Write-Warning ">>> 🗑️  Полная очистка Docker от неиспользуемых данных..."
    Write-Error "Будут удалены все остановленные контейнеры, неиспользуемые сети, dangling-образы и кэш сборки."
    Read-Host -Prompt "Нажмите Enter для продолжения или Ctrl+C для отмены"
    
    docker system prune -af
    Write-Success "✓ Система Docker очищена!"
}

# ============================================================================
# МАРШРУТИЗАЦИЯ КОМАНД
# ============================================================================

switch ($Command.ToLower()) {
    # Жизненный цикл
    "up" { Invoke-Up }
    "up-build" { Invoke-UpBuild }
    "down" { Invoke-Down }
    "down-v" { Invoke-DownV }
    "build" { Invoke-Build }
    "restart" { Invoke-Restart }
    "dev" { Invoke-Dev }

    # Отладка
    "logs" { Invoke-Logs }
    "ps" { Invoke-Ps }
    "status" { Invoke-Status }

    # Celery
    "celery-restart" { Invoke-CeleryRestart }
    "celery-logs" { Invoke-CeleryLogs }
    "celery-status" { Invoke-CeleryStatus }

    # Взаимодействие
    "shell" { Invoke-Shell }
    "run" { Invoke-Run }
    "test" { Invoke-Test }

    # Управление БД
    "db-shell" { Invoke-DbShell }
    "db-backup" { Invoke-DbBackup }
    "db-restore" { Invoke-DbRestore }

    # Перезагрузка
    "recreate" { Invoke-Recreate }
    "deploy" { Invoke-Deploy }

    # Очистка
    "prune" { Invoke-Prune }
    
    "help" { Show-Help }
    default {
        Write-Error "Неизвестная команда: $Command"
        Show-Help
    }
}