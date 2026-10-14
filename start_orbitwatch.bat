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

:: 1. Verify Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv!
    echo Please create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
set "PYTHON=.venv\Scripts\python.exe"
set "STREAMLIT=.venv\Scripts\streamlit.exe"

:: 2. Verify Docker Status
echo [1/4] Checking Docker Desktop...
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker is not running!
    echo Please open Docker Desktop, wait for it to start, and try again.
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
    echo Waiting for database readiness...
    ping 127.0.0.1 -n 4 >nul
)

:: Ensure star schema is applied
%PYTHON% scripts/apply_sql.py sql/migrations/005_star_schema.sql >nul 2>&1

:: Check if warehouse tables are populated
%PYTHON% -c "from orbitwatch.common.db import get_postgres_engine; from sqlalchemy import text; engine=get_postgres_engine('dashboard'); conn=engine.connect(); c=conn.execute(text('SELECT count(*) FROM dw.fact_gp_snapshot')).scalar(); exit(0 if c and c > 0 else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Warehouse is empty. Loading dimensional tables, please wait...
    %PYTHON% scripts/load_warehouse.py
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
