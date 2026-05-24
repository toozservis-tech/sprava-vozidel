@echo off
if not "%1"=="min" start /min cmd /c "%~0" min & exit
title Správa vozidel - Tray Manager
color 0A
cls
echo ========================================
echo   TOOZ HUB 2 - TRAY MANAGER
echo ========================================
echo.

cd /d "%~dp0\.."

REM Zkontrolovat Python
where python.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo CHYBA: Python nebyl nalezen v PATH!
    echo Zkontrolujte instalaci Pythonu.
    pause
    exit /b 1
)

REM Zkontrolovat, zda jsou nainstalované balíčky
python -c "import pystray, PIL, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo Instaluji požadované balíčky...
    pip install pystray pillow requests
    if %errorlevel% neq 0 (
        echo CHYBA: Nepodařilo se nainstalovat balíčky!
        pause
        exit /b 1
    )
)

echo Spouštím tray aplikaci...
echo.

python tray\tray_app.py

if %errorlevel% neq 0 (
    echo.
    echo CHYBA: Tray aplikace se nepodařila spustit!
    pause
)

