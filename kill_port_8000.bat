@echo off
title Uvolnuji port 8000
color 0C
cls
echo ========================================
echo   UVOLNOVANI PORTU 8000
echo ========================================
echo.

echo Hledam procesy na portu 8000...
echo.

:: Najít všechny procesy na portu 8000
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    set FOUND=1
    echo Nasel jsem proces s PID: %%a
    echo Zastavuji proces...
    taskkill /PID %%a /F >nul 2>&1
    if errorlevel 1 (
        echo Chyba: Nepodarilo se zastavit proces %%a
    ) else (
        echo OK: Proces %%a byl zastaven
    )
    echo.
)

if %FOUND% == 0 (
    echo Port 8000 neni obsazen.
    echo.
) else (
    echo Kontroluji, zda je port 8000 volny...
    timeout /t 2 >nul
    
    netstat -ano | findstr :8000 | findstr LISTENING >nul
    if errorlevel 1 (
        echo ========================================
        echo Port 8000 je nyni volny!
        echo ========================================
    ) else (
        echo ========================================
        echo Varovani: Port 8000 je stale obsazen!
        echo ========================================
        echo.
        echo Zkuste restartovat pocitac nebo zkontrolujte,
        echo ktery proces port 8000 pouziva.
    )
)

echo.
pause
