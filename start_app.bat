@echo off
setlocal
cd /d "%~dp0"

set "BACKEND_DIR=%CD%\backend"
set "FRONTEND_DIR=%CD%\frontend"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Backend virtual environment not found at %VENV_PY%
    echo Please create it from the project root with: python -m venv .venv
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules\@vercel\analytics" (
    echo Syncing frontend dependencies...
    cd /d "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        echo Frontend dependency installation failed.
        exit /b 1
    )
)

start "Legal Metrology Backend" /D "%BACKEND_DIR%" "%VENV_PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
start "Legal Metrology Frontend" /D "%FRONTEND_DIR%" "%ProgramFiles%\nodejs\npm.cmd" run dev -- --host 0.0.0.0 --port 5173
start "" "http://localhost:5173"

echo.
echo Open this in your browser: http://localhost:5173
echo Backend health/API: http://localhost:8000
echo 0.0.0.0 is only the server bind address; do not enter it in the browser.

echo.
echo If the backend is not ready yet, wait a few seconds then open the frontend URL.
endlocal
