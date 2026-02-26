@echo off
REM ============================================================
REM  Delta Plus ERP - Local Database Restore Script
REM  Run this after downloading a backup from the Admin panel.
REM ============================================================

setlocal

REM ---- CONFIGURE THESE if your local setup is different ----
set DB_USER=root
set DB_NAME=delta_plus_erp

REM ----------------------------------------------------------
REM Auto-detect MySQL bin folder
REM ----------------------------------------------------------
set MYSQL_BIN=

REM Try common MySQL 8.x paths
for %%P in (
    "C:\Program Files\MySQL\MySQL Server 8.4\bin"
    "C:\Program Files\MySQL\MySQL Server 8.3\bin"
    "C:\Program Files\MySQL\MySQL Server 8.2\bin"
    "C:\Program Files\MySQL\MySQL Server 8.1\bin"
    "C:\Program Files\MySQL\MySQL Server 8.0\bin"
    "C:\Program Files\MySQL\MySQL Server 5.7\bin"
    "C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin"
    "C:\mysql\bin"
    "C:\xampp\mysql\bin"
    "C:\wamp64\bin\mysql\mysql8.0\bin"
) do (
    if exist "%%~P\mysql.exe" (
        set MYSQL_BIN=%%~P
        goto :found_mysql
    )
)

REM Last resort: try mysql from PATH directly
where mysql >nul 2>&1
if %errorlevel%==0 (
    goto :skip_path
)

echo ERROR: Could not find MySQL. Please set the MYSQL_BIN variable
echo at the top of this script to your MySQL bin folder path.
echo Example: C:\Program Files\MySQL\MySQL Server 8.0\bin
pause
exit /b 1

:found_mysql
echo Found MySQL at: %MYSQL_BIN%
set PATH=%MYSQL_BIN%;%PATH%

:skip_path

echo ============================================
echo  Delta Plus ERP - Database Restore
echo ============================================
echo.

REM Find the most recent .sql backup in the same folder as this script
for /f "delims=" %%f in ('dir /b /o-d /a-d "%~dp0*.sql" 2^>nul') do (
    set BACKUP_FILE=%~dp0%%f
    goto :found_backup
)

echo ERROR: No .sql backup file found in this folder.
echo Please place the downloaded .sql file in the same folder as this script.
pause
exit /b 1

:found_backup
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
echo  running start_erp.bat
echo ============================================
pause
