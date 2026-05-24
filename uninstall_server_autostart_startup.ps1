# PowerShell script pro odebrání automatického startu serveru TooZ Hub 2
# Odebere zástupce z Startup složky

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ODEBRÁNÍ AUTOSTARTU - TOOZ HUB 2" -ForegroundColor Cyan
Write-Host "  (Metoda: Startup složka)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Získat cestu k Startup složce
$StartupFolder = [System.Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "TooZHub2-Server-Autostart.lnk"

# Zkontrolovat, zda zástupce existuje
if (-not (Test-Path $ShortcutPath)) {
    Write-Host "[INFO] Zástupce neexistuje: $ShortcutPath" -ForegroundColor Yellow
    Write-Host "       Autostart není nainstalován." -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 0
}

# Odebrat zástupce
try {
    Write-Host "[INFO] Odebírám zástupce..." -ForegroundColor Yellow
    Remove-Item $ShortcutPath -Force
    Write-Host "[OK] Zástupce úspěšně odebrán!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[CHYBA] Nepodařilo se odebrat zástupce: $_" -ForegroundColor Red
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








