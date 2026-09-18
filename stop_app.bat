@echo off
setlocal

taskkill /F /FI "WINDOWTITLE eq Legal Metrology Backend*" /T >nul 2>&1

taskkill /F /FI "WINDOWTITLE eq Legal Metrology Frontend*" /T >nul 2>&1

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000"') do taskkill /F /PID %%P >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173"') do taskkill /F /PID %%P >nul 2>&1

echo Stopped backend/frontend processes if they were running.
endlocal
