@echo off
setlocal
cd /d "%~dp0"

:: Set PYTHONPATH so config and orbitwatch packages are found
set "PYTHONPATH=%~dp0;%~dp0src;%PYTHONPATH%"

title ORBITWATCH Launcher

echo ======================================================================
echo   ORBITWATCH: Space Domain Awareness Data Platform
echo ======================================================================
echo.

:: 0. Check or create .env file
if not exist ".env" (
    echo [Setup] Initializing environment: copying .env.example to .env ...
    copy ".env.example" ".env" >nul
)

:: 1. Verify / Auto-create Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [Setup] First-time setup detected. Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Python was not found on your system PATH!
        echo Please install Python 3.11+ from https://www.python.org/
        echo (Make sure to check "Add python.exe to PATH" during installation)
        echo.
        pause
        exit /b 1
    )
    echo [Setup] Installing required dependencies (this takes ~1-2 minutes on first run)...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements.txt. Please check your internet connection.
        pause
        exit /b 1
    )
)
set "PYTHON=.venv\Scripts\python.exe"
set "STREAMLIT=.venv\Scripts\streamlit.exe"

:: 2. Verify Docker Status
echo [1/4] Checking Docker Desktop...
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Docker is not running!
    echo.
    echo Please make sure Docker Desktop is installed and running:
    echo   1. Open Docker Desktop from your Start menu.
    echo   2. Wait until the whale icon in the system tray shows "running".
    echo   3. Run this batch file again.
    echo ======================================================================
    echo.
    pause
    exit /b 1
)

:: 3. Start Infrastructure
echo [2/4] Starting Docker services: Postgres, Mongo, Redpanda...
docker compose up -d
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Could not start Docker services.
    pause
    exit /b 1
)

:: 4. Verify Database Connectivity & Schema
echo [3/4] Checking database connection...
%PYTHON% scripts/healthcheck.py
if %ERRORLEVEL% neq 0 (
    echo Waiting 5 seconds for database readiness...
    ping 127.0.0.1 -n 6 >nul
)

:: Apply all migrations in order
%PYTHON% scripts/apply_sql.py sql/migrations/001_initial_schema.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/002_audit_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/003_staging_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/004_clean_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/005_star_schema.sql >nul 2>&1

:: Check if warehouse tables are populated
%PYTHON% -c "from orbitwatch.common.db import get_postgres_engine; from sqlalchemy import text; engine=get_postgres_engine('dashboard'); conn=engine.connect(); c=conn.execute(text('SELECT count(*) FROM dw.fact_gp_snapshot')).scalar(); exit(0 if c and c > 0 else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Warehouse is empty. Running initial ingestion, validation, and ETL load...
    %PYTHON% flows/orbitwatch_flow.py
    %PYTHON% scripts/export_lakehouse.py
)

:: 5. Launch Dashboard
echo [4/4] Launching Streamlit Dashboard...
echo.
echo ======================================================================
echo   ORBITWATCH SYSTEM IS LIVE!
echo   - Dashboard URL:    http://localhost:8501
echo   - Redpanda Console: http://localhost:8080
echo ======================================================================
echo.
echo Opening browser to http://localhost:8501 ...
echo Keep this command window open while using ORBITWATCH.
echo Press Ctrl+C in this window to stop the server.
echo.

:: Open browser
start http://localhost:8501

:: Start Streamlit server
%STREAMLIT% run app/dashboard.py --server.port 8501

pause
