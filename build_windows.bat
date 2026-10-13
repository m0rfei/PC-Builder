@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Не найдено виртуальное окружение .venv.
    echo Сначала установите Python, создайте .venv и установите зависимости проекта.
    pause
    exit /b 1
)

echo Установка зависимостей сборки в .venv...
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 (
    echo Не удалось установить зависимости. Проверьте подключение к интернету.
    pause
    exit /b 1
)

echo Сборка автономного приложения PC-Builder...
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "PC-Builder.spec"
if errorlevel 1 (
    echo Сборка завершилась с ошибкой.
    pause
    exit /b 1
)

echo.
echo Готовое приложение: %~dp0dist\PC-Builder\PC-Builder.exe
echo Папку dist\PC-Builder можно запустить или упаковать целиком.
pause
