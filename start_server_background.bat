@echo off
REM Spuštění serveru TooZ Hub 2 na pozadí (pro autostart)
REM Tento script je určen pro spuštění přes Task Scheduler

cd /d "%~dp0"

REM Zkontrolovat, zda je port 8000 volný
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% == 0 (
    REM Port je obsazen, zkusit zastavit procesy
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 >nul
)

REM Zkontrolovat Python
where python.exe >nul 2>&1
if %errorlevel% neq 0 (
    REM Python nebyl nalezen - zapsat do logu
    echo [%date% %time%] CHYBA: Python nebyl nalezen v PATH! >> "%TEMP%\toozhub2_autostart.log"
    exit /b 1
)

REM Zkontrolovat cloudflared
where cloudflared.exe >nul 2>&1
set CLOUDFLARED_AVAILABLE=%errorlevel%

REM Zkontrolovat config soubor
set CONFIG_FILE=%USERPROFILE%\.cloudflared\config.yml

REM Spustit server na pozadí (minimalizované okno)
start "TooZ Hub 2 - Server" /MIN cmd /c "python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000 >> \"%TEMP%\toozhub2_server.log\" 2>&1"

REM Počkat, až se server spustí
timeout /t 5 >nul

REM Zkontrolovat, zda server běží
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% == 0 (
    echo [%date% %time%] Server spusten na portu 8000 >> "%TEMP%\toozhub2_autostart.log"
) else (
    echo [%date% %time%] CHYBA: Server se nepodarilo spustit! >> "%TEMP%\toozhub2_autostart.log"
    exit /b 1
)

REM Spustit Cloudflare Tunnel (pokud je k dispozici)
if %CLOUDFLARED_AVAILABLE% == 0 (
    if exist "%CONFIG_FILE%" (
        start "TooZ Hub 2 - Tunnel" /MIN cmd /c "cloudflared tunnel --config \"%CONFIG_FILE%\" run >> \"%TEMP%\toozhub2_tunnel.log\" 2>&1"
        echo [%date% %time%] Cloudflare Tunnel spusten >> "%TEMP%\toozhub2_autostart.log"
    ) else (
        echo [%date% %time%] VAROVANI: Config soubor neexistuje: %CONFIG_FILE% >> "%TEMP%\toozhub2_autostart.log"
    )
) else (
    echo [%date% %time%] VAROVANI: cloudflared.exe nebyl nalezen v PATH >> "%TEMP%\toozhub2_autostart.log"
)

REM Script končí, ale procesy běží na pozadí
exit /b 0








