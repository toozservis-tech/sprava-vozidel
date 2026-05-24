@echo off
title TooZ Hub 2 - Cloudflare Tunnel
color 0B
cls
echo ========================================
echo   TOOZ HUB 2 - CLOUDFLARE TUNNEL
echo ========================================
echo.

cd /d "%~dp0"

REM Zkontrolovat, zda je cloudflared nainstalován
where cloudflared.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo CHYBA: cloudflared.exe nebyl nalezen v PATH!
    echo.
    echo Instalujte cloudflared:
    echo 1. Stahnete z: https://github.com/cloudflare/cloudflared/releases
    echo 2. Nebo pouzijte: winget install --id Cloudflare.cloudflared
    echo.
    pause
    exit /b 1
)

REM Zkontrolovat, zda existuje config soubor
set CONFIG_FILE=%USERPROFILE%\.cloudflared\config.yml
if not exist "%CONFIG_FILE%" (
    echo VAROVANI: Config soubor neexistuje: %CONFIG_FILE%
    echo.
    echo Vytvorte config soubor nebo spustte:
    echo cloudflared tunnel login
    echo cloudflared tunnel create nazev-tunelu
    echo.
    pause
    exit /b 1
)

echo Spoustim Cloudflare Tunnel...
echo Config soubor: %CONFIG_FILE%
echo.
echo Pro zastaveni tunelu stisknete: Ctrl+C
echo.
echo ========================================
echo.

cloudflared tunnel --config "%CONFIG_FILE%" run

echo.
echo.
echo Tunnel byl zastaven.
pause










