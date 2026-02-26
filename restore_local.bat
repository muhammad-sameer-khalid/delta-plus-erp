@echo off
REM ============================================================
REM  Delta Plus ERP - Local Database Restore Script
REM  Run this after downloading a backup from the Admin panel.
REM ============================================================

setlocal

REM ---- CONFIGURE THESE if your local setup is different ----
set DB_USER=root
set DB_NAME=delta_plus_erp
set MYSQL_PATH=C:\Program Files\MySQL\MySQL Server 8.0\bin

REM ----------------------------------------------------------

set PATH=%MYSQL_PATH%;%PATH%

echo ============================================
echo  Delta Plus ERP - Database Restore
echo ============================================
echo.

REM Find the most recent .sql backup in the same folder as this script
for /f "delims=" %%f in ('dir /b /o-d /a-d "%~dp0*.sql" 2^>nul') do (
    set BACKUP_FILE=%~dp0%%f
    goto :found
)

echo ERROR: No .sql backup file found in this folder.
echo Please place the downloaded .sql file in the same folder as this script.
pause
exit /b 1

:found
echo Found backup file: %BACKUP_FILE%
echo.
echo This will REPLACE all data in the local '%DB_NAME%' database.
echo.
set /p CONFIRM=Type YES to continue, or press Enter to cancel: 
if /i not "%CONFIRM%"=="YES" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Enter your local MySQL root password when prompted.
echo (If your local MySQL has no password, just press Enter.)
echo.

REM Create database if it doesn't exist, then restore
mysql -u %DB_USER% -p -e "CREATE DATABASE IF NOT EXISTS %DB_NAME% CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
if errorlevel 1 (
    echo ERROR: Could not connect to MySQL. Check that MySQL is running and the password is correct.
    pause
    exit /b 1
)

mysql -u %DB_USER% -p %DB_NAME% < "%BACKUP_FILE%"
if errorlevel 1 (
    echo ERROR: Restore failed. Check the error message above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  SUCCESS! Database restored from:
echo  %BACKUP_FILE%
echo ============================================
echo  You can now start the local ERP server by
echo  running start_server.bat
echo ============================================
pause
