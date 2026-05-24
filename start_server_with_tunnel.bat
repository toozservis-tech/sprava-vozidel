@echo off
title TooZ Hub 2 - Server + Cloudflare Tunnel
color 0E
cls
echo ========================================
echo   TOOZ HUB 2 - SERVER + TUNNEL
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

REM Zkontrolovat cloudflared
where cloudflared.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo VAROVANI: cloudflared.exe nebyl nalezen v PATH!
    echo.
    echo Instalujte cloudflared:
    echo 1. Stahnete z: https://github.com/cloudflare/cloudflared/releases
    echo 2. Nebo pouzijte: winget install --id Cloudflare.cloudflared
    echo.
    echo Spustim pouze server bez tunelu...
    echo.
    timeout /t 3 >nul
    goto :start_server_only
)

REM Zkontrolovat config soubor
set CONFIG_FILE=%USERPROFILE%\.cloudflared\config.yml
if not exist "%CONFIG_FILE%" (
    echo VAROVANI: Config soubor neexistuje: %CONFIG_FILE%
    echo.
    echo Vytvorte config soubor nebo spustte:
    echo cloudflared tunnel login
    echo cloudflared tunnel create nazev-tunelu
    echo.
    echo Spustim pouze server bez tunelu...
    echo.
    timeout /t 3 >nul
    goto :start_server_only
)

echo Server bude spusten na: http://0.0.0.0:8000
echo Cloudflare Tunnel bude spusten s config: %CONFIG_FILE%
echo.
echo Pro zastaveni obou sluzeb stisknete: Ctrl+C
echo.
echo ========================================
echo.
echo Startuji server...
echo.

REM Spustit server v novem okne
start "TooZ Hub 2 - Server" cmd /k "python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000"

REM Pockat, az se server spusti
echo Cekam na spusteni serveru...
timeout /t 5 >nul

REM Zkontrolovat, zda server bezi
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% neq 0 (
    echo CHYBA: Server se nepodarilo spustit!
    pause
    exit /b 1
)

echo Server je spusten!
echo.
echo Startuji Cloudflare Tunnel...
echo.

REM Spustit tunel v novem okne
start "TooZ Hub 2 - Tunnel" cmd /k "cloudflared tunnel --config \"%CONFIG_FILE%\" run"

echo.
echo ========================================
echo Oba procesy jsou spusteny v samostatnych oknech.
echo Zavrenim tohoto okna se procesy NEZASTAVI.
echo Pro zastaveni zavrete okna "TooZ Hub 2 - Server" a "TooZ Hub 2 - Tunnel".
echo ========================================
echo.
pause
exit /b 0

:start_server_only
echo Startuji pouze server...
echo.
start "TooZ Hub 2 - Server" cmd /k "python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000"
echo.
echo Server je spusten v samostatnem okne.
echo Pro zastaveni zavrete okno "TooZ Hub 2 - Server".
echo.
pause
exit /b 0

