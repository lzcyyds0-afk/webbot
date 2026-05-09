@echo off
chcp 65001 >nul
echo ========================================
echo  WebBot Frontend Starter (Windows)
echo ========================================

set "SCRIPT_DIR=%~dp0"
set "FRONTEND_DIR=%SCRIPT_DIR%..\frontend"

cd /d "%FRONTEND_DIR%"

REM Check if pnpm is available
where pnpm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pnpm not found. Please install pnpm first:
    echo   npm install -g pnpm
    pause
    exit /b 1
)

echo [1/2] Installing dependencies...
pnpm install
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Starting frontend dev server...
echo  URL: http://localhost:5173
echo ========================================
echo.

pnpm dev

pause
