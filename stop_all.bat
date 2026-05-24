@echo off
title TooZ Hub 2 - Zastavit Server + Tunnel
color 0C
cls
echo ========================================
echo   TOOZ HUB 2 - ZASTAVENI VSECH SLUZEB
echo ========================================
echo.

echo Zastavuji server na portu 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Zastavuji proces PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo Zastavuji Cloudflare Tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1

timeout /t 2 >nul

echo.
echo Kontroluji, zda jsou procesy zastaveny...
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% == 0 (
    echo VAROVANI: Server stale bezi!
) else (
    echo Server byl zastaven.
)

tasklist | findstr cloudflared.exe >nul
if %errorlevel% == 0 (
    echo VAROVANI: Tunnel stale bezi!
) else (
    echo Tunnel byl zastaven.
)

echo.
echo ========================================
echo Hotovo!
echo ========================================
echo.
pause

