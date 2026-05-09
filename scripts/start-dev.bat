@echo off
chcp 65001 >nul
echo ========================================
echo  WebBot Dev Starter (Windows)
echo ========================================
echo.
echo  This script will start both backend and frontend.
echo  Close each window to stop the respective service.
echo.
echo  Prerequisites:
echo   - Python 3.11+ with uv
echo   - Node.js 18+ with pnpm
echo   - Google Chrome (recommended) or Chromium
echo.
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"

echo Starting backend in new window...
start "WebBot Backend" cmd /k "\"%SCRIPT_DIR%start-backend.bat\""

timeout /t 2 /nobreak >nul

echo Starting frontend in new window...
start "WebBot Frontend" cmd /k "\"%SCRIPT_DIR%start-frontend.bat\""

echo.
echo ========================================
echo  Both services are starting...
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo ========================================
echo.
pause
