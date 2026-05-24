@echo off
title TooZ Hub 2 - Spustit Server + Tunnel
color 0A
cls
echo ========================================
echo   TOOZ HUB 2 - SPUSTENI VSECH SLUZEB
echo ========================================
echo.

cd /d "%~dp0"

REM Zkontrolovat, zda uz neco bezi
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% == 0 (
    echo Server uz bezi na portu 8000.
    echo.
    echo Chcete ho zastavit a spustit znovu? (A/N)
    set /p RESTART="> "
    if /i "%RESTART%"=="A" (
        echo Zastavuji existujici procesy...
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
            taskkill /PID %%a /F >nul 2>&1
        )
        taskkill /F /IM cloudflared.exe >nul 2>&1
        timeout /t 2 >nul
    ) else (
        echo Zustavam bezi existujici procesy.
        pause
        exit /b 0
    )
)

REM Zkontrolovat Python
where python.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo CHYBA: Python nebyl nalezen v PATH!
    pause
    exit /b 1
)

REM Zkontrolovat cloudflared
where cloudflared.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo VAROVANI: cloudflared.exe nebyl nalezen!
    echo Spustim pouze server.
    set TUNNEL_AVAILABLE=0
) else (
    set TUNNEL_AVAILABLE=1
)

REM Zkontrolovat config
set CONFIG_FILE=%USERPROFILE%\.cloudflared\config.yml
if not exist "%CONFIG_FILE%" (
    echo VAROVANI: Config soubor neexistuje: %CONFIG_FILE%
    set TUNNEL_AVAILABLE=0
)

echo.
echo Spoustim server...
start "TooZ Hub 2 - Server" /MIN cmd /c "cd /d %~dp0 && python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000"

echo Cekam na spusteni serveru...
timeout /t 5 >nul

netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% neq 0 (
    echo CHYBA: Server se nepodarilo spustit!
    pause
    exit /b 1
)

echo Server je spusten na http://localhost:8000
echo.

if %TUNNEL_AVAILABLE%==1 (
    echo Spoustim Cloudflare Tunnel...
    start "TooZ Hub 2 - Tunnel" /MIN cmd /c "cloudflared tunnel --config \"%CONFIG_FILE%\" run"
    timeout /t 2 >nul
    echo Tunnel je spusten.
) else (
    echo Tunnel nebyl spusten (chybi cloudflared nebo config).
)

echo.
echo ========================================
echo Oba procesy jsou spusteny!
echo Server: http://localhost:8000
echo Tunnel: hub.toozservis.cz
echo.
echo Pro zastaveni zavrete okna "TooZ Hub 2 - Server" a "TooZ Hub 2 - Tunnel"
echo nebo pouzijte: stop_all.bat
echo ========================================
echo.
pause

