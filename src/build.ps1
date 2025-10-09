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
# ОСНОВНЫЕ КОМАНДЫ
# ============================================================================

function Show-Help {
    Write-Success "`nДоступные команды:"
    Write-Host ""
    Write-Host "  init              " -ForegroundColor Yellow -NoNewline; Write-Host "Полная инициализация проекта"
    Write-Host "  build             " -ForegroundColor Yellow -NoNewline; Write-Host "Собрать Docker образы"
    Write-Host "  up                " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить все контейнеры"
    Write-Host "  up-build          " -ForegroundColor Yellow -NoNewline; Write-Host "Собрать и запустить"
    Write-Host "  dev               " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить с выводом логов"
    Write-Host "  down              " -ForegroundColor Yellow -NoNewline; Write-Host "Остановить контейнеры"
    Write-Host "  down-v            " -ForegroundColor Yellow -NoNewline; Write-Host "Остановить и удалить volumes"
    Write-Host "  restart           " -ForegroundColor Yellow -NoNewline; Write-Host "Перезапустить контейнеры"
    Write-Host "  restart-bots      " -ForegroundColor Yellow -NoNewline; Write-Host "Перезапустить только боты"
    Write-Host "  logs              " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи всех сервисов"
    Write-Host "  logs-bots         " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи ботов"
    Write-Host "  logs-db           " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи БД"
    Write-Host "   logs-celery       " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи Celery"
    Write-Host "   logs-redis        " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи Redis"
    Write-Host "   logs-celery-beat  " -ForegroundColor Yellow -NoNewline; Write-Host "Показать логи Celery Beat"
    Write-Host "  ps                " -ForegroundColor Yellow -NoNewline; Write-Host "Статус контейнеров"
    Write-Host "  status            " -ForegroundColor Yellow -NoNewline; Write-Host "Детальный статус"
    Write-Host "  shell             " -ForegroundColor Yellow -NoNewline; Write-Host "Открыть bash в контейнере ботов"
    Write-Host "  db-start          " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить только БД"
    Write-Host "  db-init           " -ForegroundColor Yellow -NoNewline; Write-Host "Инициализировать БД"
    Write-Host "  db-reset          " -ForegroundColor Yellow -NoNewline; Write-Host "Полный сброс БД"
    Write-Host "  db-shell          " -ForegroundColor Yellow -NoNewline; Write-Host "Открыть psql shell"
    Write-Host "  db-backup         " -ForegroundColor Yellow -NoNewline; Write-Host "Создать бэкап БД"
    Write-Host "  clean             " -ForegroundColor Yellow -NoNewline; Write-Host "Очистить проект"
    Write-Host "  clean-all         " -ForegroundColor Yellow -NoNewline; Write-Host "Полная очистка с образами"
    Write-Host "  test              " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить тесты"
    Write-Host "  run-library       " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить library_bot"
    Write-Host "  run-admin         " -ForegroundColor Yellow -NoNewline; Write-Host "Запустить admin_bot"
    Write-Host "  health-check      " -ForegroundColor Yellow -NoNewline; Write-Host "Проверка здоровья системы"
    Write-Host "  quick-restart     " -ForegroundColor Yellow -NoNewline; Write-Host "Быстрый перезапуск ботов"
    Write-Host "  fresh-start       " -ForegroundColor Yellow -NoNewline; Write-Host "Свежий старт проекта"
    Write-Host "  deploy            " -ForegroundColor Yellow -NoNewline; Write-Host "Деплой проекта"
    Write-Host ""
    Write-Info "Использование: .\build.ps1 <команда>"
    Write-Host ""
}

function Invoke-Init {
    Write-Info ">>> Шаг 1: Остановка и очистка контейнеров..."
    & $DOCKER_COMPOSE down -v
    
    Write-Info ">>> Шаг 2: Запуск базы данных..."
    & $DOCKER_COMPOSE up -d $DB_SERVICE
    
    Write-Warning ">>> Ожидание запуска БД (10 секунд)..."
    Start-Sleep -Seconds 10
    
    Write-Info ">>> Шаг 3: Инициализация таблиц и данных..."
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/init_db.py
    
    Write-Info ">>> Шаг 4: Запуск всех контейнеров..."
    & $DOCKER_COMPOSE up --build -d
    
    Write-Success "✓ Проект успешно инициализирован!"
}

function Invoke-Build {
    Write-Info ">>> Сборка образов..."
    & $DOCKER_COMPOSE build
}

function Invoke-Up {
    Write-Info ">>> Запуск контейнеров..."
    & $DOCKER_COMPOSE up -d
}

function Invoke-UpBuild {
    Write-Info ">>> Сборка и запуск контейнеров..."
    & $DOCKER_COMPOSE up --build -d
}

function Invoke-Dev {
    Write-Info ">>> Запуск в режиме разработки..."
    & $DOCKER_COMPOSE up --build
}

function Invoke-Down {
    Write-Warning ">>> Остановка контейнеров..."
    & $DOCKER_COMPOSE down
}

function Invoke-DownV {
    Write-Error ">>> Остановка и удаление volumes..."
    & $DOCKER_COMPOSE down -v
}

function Invoke-Restart {
    Write-Info ">>> Перезапуск контейнеров..."
    & $DOCKER_COMPOSE restart
}

function Invoke-RestartBots {
    Write-Info ">>> Перезапуск ботов..."
    & $DOCKER_COMPOSE restart $BOTS_SERVICE
}

function Invoke-Logs {
    & $DOCKER_COMPOSE logs -f
}

function Invoke-LogsBots {
    & $DOCKER_COMPOSE logs -f $BOTS_SERVICE
}

function Invoke-LogsDb {
    & $DOCKER_COMPOSE logs -f $DB_SERVICE
}

function Invoke-LogsCelery {
    & $DOCKER_COMPOSE logs -f $CELERY_WORKER
}

function Invoke-LogsRedis {
    & $DOCKER_COMPOSE logs -f $REDIS_SERVICE
}

function Invoke-LogsCeleryBeat {
    & $DOCKER_COMPOSE logs -f $CELERY_BEAT
}

function Invoke-Ps {
    & $DOCKER_COMPOSE ps
}

function Invoke-Status {
    Write-Success "=== Docker контейнеры ==="
    & $DOCKER_COMPOSE ps
    Write-Host ""
    Write-Success "=== Docker образы ==="
    docker images | Select-String "mypersonal"
    Write-Host ""
    Write-Success "=== Docker volumes ==="
    docker volume ls | Select-String "mypersonal"
}

function Invoke-Shell {
    & $DOCKER_COMPOSE exec $BOTS_SERVICE /bin/bash
}

function Invoke-DbStart {
    Write-Info ">>> Запуск базы данных..."
    & $DOCKER_COMPOSE up -d $DB_SERVICE
}

function Invoke-DbInit {
    Write-Info ">>> Инициализация базы данных..."
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/init_db.py
}

function Invoke-DbReset {
    Write-Error ">>> Внимание! Все данные будут удалены!"
    Write-Warning ">>> Остановка и удаление volumes..."
    & $DOCKER_COMPOSE down -v
    
    Write-Info ">>> Запуск пустой БД..."
    & $DOCKER_COMPOSE up -d $DB_SERVICE
    
    Write-Warning ">>> Ожидание запуска БД (10 секунд)..."
    Start-Sleep -Seconds 10
    
    Write-Info ">>> Создание таблиц и заполнение данных..."
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/init_db.py
    
    Write-Success "✓ База данных сброшена и инициализирована!"
}

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
    
    Write-Success "✓ Бэкап создан в папке backups/"
}

function Invoke-Clean {
    Write-Warning ">>> Очистка проекта..."
    & $DOCKER_COMPOSE down -v
}

function Invoke-CleanAll {
    Write-Error ">>> Полная очистка проекта..."
    & $DOCKER_COMPOSE down -v --rmi all
}

function Invoke-Test {
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE pytest tests/
}

function Invoke-RunLibrary {
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/library_bot/main.py
}

function Invoke-RunAdmin {
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/admin_bot/main.py
}

function Invoke-HealthCheck {
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/health_check.py
}

function Invoke-QuickRestart {
    Write-Info ">>> Быстрый перезапуск ботов..."
    & $DOCKER_COMPOSE restart $BOTS_SERVICE
    Write-Success "✓ Боты перезапущены!"
}

function Invoke-FreshStart {
    Write-Info ">>> Свежий старт проекта..."
    Invoke-DownV
    Invoke-Init
    Write-Success "✓ Проект готов к работе!"
}

function Invoke-Deploy {
    Write-Info ">>> Деплой проекта..."
    & $DOCKER_COMPOSE down
    & $DOCKER_COMPOSE build
    & $DOCKER_COMPOSE up -d $DB_SERVICE
    Start-Sleep -Seconds 10
    & $DOCKER_COMPOSE run --rm $BOTS_SERVICE python src/init_db.py
    & $DOCKER_COMPOSE up -d
    Write-Success "✓ Деплой завершен!"
}

# ============================================================================
# МАРШРУТИЗАЦИЯ КОМАНД
# ============================================================================

switch ($Command.ToLower()) {
    "help" { Show-Help }
    "init" { Invoke-Init }
    "build" { Invoke-Build }
    "up" { Invoke-Up }
    "up-build" { Invoke-UpBuild }
    "dev" { Invoke-Dev }
    "down" { Invoke-Down }
    "down-v" { Invoke-DownV }
    "restart" { Invoke-Restart }
    "restart-bots" { Invoke-RestartBots }
    "logs" { Invoke-Logs }
    "logs-bots" { Invoke-LogsBots }
    "logs-db" { Invoke-LogsDb }
    "logs-celery" { Invoke-LogsCelery }
    "logs-redis" { Invoke-LogsRedis }
    "logs-celery-beat" { Invoke-LogsCeleryBeat }
    "ps" { Invoke-Ps }
    "status" { Invoke-Status }
    "shell" { Invoke-Shell }
    "db-start" { Invoke-DbStart }
    "db-init" { Invoke-DbInit }
    "db-reset" { Invoke-DbReset }
    "db-shell" { Invoke-DbShell }
    "db-backup" { Invoke-DbBackup }
    "clean" { Invoke-Clean }
    "clean-all" { Invoke-CleanAll }
    "test" { Invoke-Test }
    "run-library" { Invoke-RunLibrary }
    "run-admin" { Invoke-RunAdmin }
    "health-check" { Invoke-HealthCheck }
    "quick-restart" { Invoke-QuickRestart }
    "fresh-start" { Invoke-FreshStart }
    "deploy" { Invoke-Deploy }
    default {
        Write-Error "Неизвестная команда: $Command"
        Show-Help
    }
}