# PowerShell script pro odebrání automatického startu serveru TooZ Hub 2

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ODEBRÁNÍ AUTOSTARTU - TOOZ HUB 2" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Název úkolu v Task Scheduleru
$TaskName = "TooZHub2-Server-Autostart"

# Zkontrolovat, zda úkol existuje
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $ExistingTask) {
    Write-Host "[INFO] Úkol '$TaskName' neexistuje." -ForegroundColor Yellow
    Write-Host "       Autostart není nainstalován." -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 0
}

# Odebrat úkol
try {
    Write-Host "[INFO] Odebírám úkol '$TaskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[OK] Úkol úspěšně odebrán!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[CHYBA] Nepodařilo se odebrat úkol: $_" -ForegroundColor Red
    Write-Host ""
    pause
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ODEBRÁNÍ DOKONČENO" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Autostart byl úspěšně odebrán." -ForegroundColor Green
Write-Host "Server se již nebude spouštět automaticky při startu PC." -ForegroundColor Yellow
Write-Host ""

pause








