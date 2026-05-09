@echo off
chcp 65001 >nul
echo ========================================
echo  WebBot Backend Starter (Windows)
echo ========================================

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%..\backend"
set "PYTHONPATH=%BACKEND_DIR%"

cd /d "%BACKEND_DIR%"

REM Check if uv is available
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] uv not found. Please install uv first:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
uv sync
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/3] Installing Playwright browsers...
uv run playwright install chromium
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Playwright browser install failed. Will try fallback mode.
)

echo [3/3] Running database migrations...
uv run alembic upgrade head
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Migration failed. Tables will be auto-created on startup.
)

echo.
echo ========================================
echo  Starting backend server...
echo  API: http://localhost:8000
echo  Docs: http://localhost:8000/docs
echo ========================================
echo.

REM Use --host 0.0.0.0 to allow local network access (optional, remove if not needed)
uv run uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

pause
