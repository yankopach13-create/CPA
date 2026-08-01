@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  Анализ клиентов в продукте (Streamlit)
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ и добавьте его в PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Создание виртуального окружения...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
)

echo Установка зависимостей...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
set PYTHONDONTWRITEBYTECODE=1

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Запуск приложения: http://localhost:8501
echo Для остановки нажмите Ctrl+C
echo.

".venv\Scripts\python.exe" -m streamlit run app.py

pause
