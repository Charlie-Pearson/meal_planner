@echo off
REM Batch file to generate and apply Flask-Migrate database migrations.
REM Uses --app flag for explicit application discovery.
REM Assumes 'migrations' folder already initialized via 'flask db init'.
REM Assumes this script is in the same directory as your app.py file.

title Flask DB Migration Helper

echo ========================================
echo  Flask Database Migration Script
echo ========================================
echo.

REM Change directory to the location of this script
cd /d "%~dp0"
echo Changed directory to: %cd%
echo.

REM Check if migrations directory exists
if not exist migrations (
    echo ERROR: 'migrations' directory not found!
    echo You might need to run 'python -m flask --app app.py db init' once first.
    echo.
    pause
    exit /b 1
)

REM Prompt for the migration message
set "MIGRATE_MSG="
set /p MIGRATE_MSG="Enter a short description for this migration (e.g., 'Add user email column'): "

REM Validate input
if "%MIGRATE_MSG%"=="" (
    echo ERROR: Migration message cannot be empty. Aborting.
    echo.
    pause
    exit /b 1
)

echo.
echo --- Running Migration Generation ---
python -m flask --app app.py db migrate -m "%MIGRATE_MSG%"

REM Check if migrate command was successful
if errorlevel 1 (
    echo.
    echo ERROR: 'flask db migrate' command failed. See output above.
    echo Check your model changes and database connection.
    echo Migration script was NOT generated or applied.
    echo.
    pause
    exit /b 1
)

echo.
echo --- Migration Script Generated Successfully ---
echo Review the script in the migrations/versions folder if desired.
echo.
echo --- Running Database Upgrade ---
python -m flask --app app.py db upgrade

REM Check if upgrade command was successful
if errorlevel 1 (
    echo.
    echo ERROR: 'flask db upgrade' command failed. See output above.
    echo The database may not have been updated correctly. Check logs/database.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Database Migration Successful!
echo ========================================
echo.
pause
exit /b 0