@echo off
title Delta Plus ERP
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run setup first - see SETUP_GUIDE.md
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo Starting Delta Plus ERP...
echo.
python app.py

pause
