@echo off
setlocal
set "DATA_DIR=%LOCALAPPDATA%\PC-Builder"
set "DB_FILE=%DATA_DIR%\pc_builder.db"

if not exist "%DB_FILE%" (
    echo База PC-Builder пока не найдена:
    echo %DB_FILE%
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq PC-Builder.exe" | find /I "PC-Builder.exe" >nul
if not errorlevel 1 (
    echo Сначала закройте PC-Builder, затем повторите резервное копирование.
    pause
    exit /b 1
)

if exist "%DB_FILE%-wal" (
    echo Найден активный журнал SQLite. Закройте PC-Builder и повторите попытку.
    pause
    exit /b 1
)

if not exist "%DATA_DIR%\backups" mkdir "%DATA_DIR%\backups"
for /f %%i in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%i"
if not defined STAMP (
    echo Не удалось получить время для имени резервной копии.
    pause
    exit /b 1
)

set "BACKUP_FILE=%DATA_DIR%\backups\pc_builder_%STAMP%.db"
copy "%DB_FILE%" "%BACKUP_FILE%" >nul
if errorlevel 1 (
    echo Не удалось создать резервную копию.
    pause
    exit /b 1
)

echo Резервная копия создана:
echo %BACKUP_FILE%
pause
