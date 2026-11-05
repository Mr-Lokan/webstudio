@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Установка зависимостей...
python -m pip install -r requirements.txt --quiet
echo.
echo Сайт запускается: http://127.0.0.1:5000
echo Для остановки нажмите Ctrl+C
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python run.py
pause
