@echo off
title TooZ Hub 2 - Server Only
color 0A
cls
echo ========================================
echo   TOOZ HUB 2 - SERVER ONLY
echo ========================================
echo.

cd /d "%~dp0"

REM Zkontrolovat, zda je port 8000 volný
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% == 0 (
    echo VAROVANI: Port 8000 je obsazen!
    echo Zastavuji procesy na portu 8000...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 >nul
)

REM Zkontrolovat Python
where python.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo CHYBA: Python nebyl nalezen v PATH!
    echo Zkontrolujte instalaci Pythonu.
    pause
    exit /b 1
)

echo Server bude spusten na: http://0.0.0.0:8000
echo.
echo Pro zastaveni serveru stisknete: Ctrl+C
echo.
echo ========================================
echo.
echo Startuji server...
echo.

python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000

echo.
echo.
echo Server byl zastaven.
pause








