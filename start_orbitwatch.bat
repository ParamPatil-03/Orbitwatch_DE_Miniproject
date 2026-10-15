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
if exist ".env" goto has_env
echo [Setup] Copying .env.example to .env
copy ".env.example" ".env" >nul
:has_env

:: 1. Verify / Auto-create Virtual Environment
if exist ".venv\Scripts\python.exe" goto has_venv
echo [Setup] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 goto python_error

echo [Setup] Installing dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto pip_error
:has_venv

set "PYTHON=.venv\Scripts\python.exe"
set "STREAMLIT=.venv\Scripts\streamlit.exe"

:: 2. Verify Docker Status
echo [1/4] Checking Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 goto docker_error

:: 3. Start Infrastructure
echo [2/4] Starting Docker services: Postgres, Mongo, Redpanda...
docker compose up -d
if errorlevel 1 goto docker_compose_error

:: 4. Verify Database Connectivity & Schema
echo [3/4] Checking database connection...
%PYTHON% scripts/healthcheck.py
if errorlevel 1 (
    echo Waiting for database readiness...
    ping 127.0.0.1 -n 6 >nul
)

:: Apply migrations
%PYTHON% scripts/apply_sql.py sql/migrations/001_initial_schema.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/002_audit_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/003_staging_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/004_clean_tables.sql >nul 2>&1
%PYTHON% scripts/apply_sql.py sql/migrations/005_star_schema.sql >nul 2>&1

:: Check if warehouse tables are populated
%PYTHON% -c "from orbitwatch.common.db import get_postgres_engine; from sqlalchemy import text; engine=get_postgres_engine('dashboard'); conn=engine.connect(); c=conn.execute(text('SELECT count(*) FROM dw.fact_gp_snapshot')).scalar(); exit(0 if c and c > 0 else 1)" >nul 2>&1
if errorlevel 1 goto load_data
goto start_dashboard

:load_data
echo Warehouse is empty. Running initial ETL load...
%PYTHON% flows/orbitwatch_flow.py
%PYTHON% scripts/export_lakehouse.py
goto start_dashboard

:start_dashboard
echo [4/4] Launching Services & Interactive UIs...
echo.
echo ======================================================================
echo   ORBITWATCH DEMONSTRATION ENVIRONMENT IS LIVE!
echo   1. Streamlit Dashboard:    http://localhost:8501
echo   2. Redpanda Kafka Console: http://localhost:8080
echo   3. FastAPI Ingestion Docs: http://localhost:8000/docs
echo   4. Data Quality Report:    docs\validation_report\index.html
echo ======================================================================
echo.

:: Launch FastAPI Ingestion Microservice in background
echo Starting FastAPI Ingestion Service (Port 8000)...
start "ORBITWATCH Ingestion API" /min "%PYTHON%" -m uvicorn orbitwatch.ingestion.api:app --host 127.0.0.1 --port 8000

:: Brief wait for services to initialize
ping 127.0.0.1 -n 3 >nul

:: Automatically open demonstration tabs in default web browser
echo Opening demonstration tabs in your web browser...
start "" "http://localhost:8080"
start "" "http://localhost:8000/docs"
if exist "%~dp0docs\validation_report\index.html" (
    start "" "%~dp0docs\validation_report\index.html"
)

echo.
echo Launching Streamlit Dashboard (will open automatically when ready)...
echo Keep this command window open while presenting ORBITWATCH to your teacher.
echo Press Ctrl+C in this window when you wish to stop the services.
echo.

%STREAMLIT% run app/dashboard.py --server.port 8501

:: Clean up background FastAPI process when Streamlit exits
taskkill /fi "WINDOWTITLE eq ORBITWATCH Ingestion API*" /f >nul 2>&1
pause
exit /b 0

:python_error
echo.
echo [ERROR] Python 3 was not found on your system PATH!
echo Please install Python 3.11+ from https://www.python.org/
echo Check the box 'Add python.exe to PATH' during installation.
echo.
pause
exit /b 1

:pip_error
echo.
echo [ERROR] Failed to install requirements.txt. Please check internet connection.
echo.
pause
exit /b 1

:docker_error
echo.
echo ======================================================================
echo [ERROR] Docker Desktop is not running!
echo Please start Docker Desktop and run this script again.
echo ======================================================================
echo.
pause
exit /b 1

:docker_compose_error
echo.
echo [ERROR] Could not start Docker services via docker compose up.
echo.
pause
exit /b 1
