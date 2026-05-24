# PowerShell script pro instalaci automatického startu serveru TooZ Hub 2
# Používá Startup složku (nevyžaduje admin práva)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INSTALACE AUTOSTARTU - TOOZ HUB 2" -ForegroundColor Cyan
Write-Host "  (Metoda: Startup složka)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Získat cestu ke skriptu
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ScriptDir "start_server_background.bat"

if (-not (Test-Path $StartScript)) {
    Write-Host "[CHYBA] Soubor start_server_background.bat nebyl nalezen!" -ForegroundColor Red
    Write-Host "       Cesta: $StartScript" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[OK] Start script nalezen: $StartScript" -ForegroundColor Green
Write-Host ""

# Získat cestu k Startup složce
$StartupFolder = [System.Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "TooZHub2-Server-Autostart.lnk"

Write-Host "[INFO] Startup složka: $StartupFolder" -ForegroundColor Yellow
Write-Host ""

# Zkontrolovat, zda zástupce už existuje
if (Test-Path $ShortcutPath) {
    Write-Host "[INFO] Zástupce už existuje: $ShortcutPath" -ForegroundColor Yellow
    $Response = Read-Host "Chcete ho přepsat? (A/N)"
    if ($Response -ne "A" -and $Response -ne "a") {
        Write-Host "[INFO] Instalace zrušena." -ForegroundColor Yellow
        pause
        exit 0
    }
    Remove-Item $ShortcutPath -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Existující zástupce odebrán." -ForegroundColor Green
    Write-Host ""
}

# Vytvořit zástupce
try {
    Write-Host "[INFO] Vytvářím zástupce v Startup složce..." -ForegroundColor Yellow
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $StartScript
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "Automatické spuštění TooZ Hub 2 serveru a Cloudflare Tunnel"
    $Shortcut.WindowStyle = 7  # Minimalizované okno
    $Shortcut.Save()
    
    Write-Host "[OK] Zástupce úspěšně vytvořen!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[CHYBA] Nepodařilo se vytvořit zástupce: $_" -ForegroundColor Red
    pause
    exit 1
}

# Zobrazit informace
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INSTALACE DOKONČENA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Zástupce: $ShortcutPath" -ForegroundColor Green
Write-Host "Spouští se: Při každém přihlášení do Windows" -ForegroundColor Green
Write-Host "Spouští: $StartScript" -ForegroundColor Green
Write-Host ""
Write-Host "Pro ověření otevřete Startup složku:" -ForegroundColor Yellow
Write-Host "  Win + R -> shell:startup" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pro odebrání autostartu:" -ForegroundColor Yellow
Write-Host "  .\uninstall_server_autostart_startup.ps1" -ForegroundColor Cyan
Write-Host "  Nebo smažte zástupce z Startup složky" -ForegroundColor Cyan
Write-Host ""

pause








