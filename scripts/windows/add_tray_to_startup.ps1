# scripts/windows/add_tray_to_startup.ps1
# Přidání tray aplikace do Windows Autostartu pro TOOZHUB2

param()

# Název projektu (musí odpovídat PROJECT_NAME v tray_manager.py)
$PROJECT_NAME = "TOOZHUB2"

Write-Host "========================================"
Write-Host "  TooZ Hub 2 - Přidání do Autostartu"
Write-Host "========================================"
Write-Host ""

# Zjistit cestu ke složce Autostart
$startup = [Environment]::GetFolderPath("Startup")
Write-Host "[INFO] Složka Autostart: $startup"

# Zjistit cesty k projektovým souborům
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$vbsScript = Join-Path $scriptDir "run_tray_hidden.vbs"

Write-Host "[INFO] Root projektu: $projectRoot"
Write-Host "[INFO] VBS skript: $vbsScript"

# Název zástupce (unikátní pro tento projekt)
$shortcutName = "TooZ_Tray_${PROJECT_NAME}.lnk"
$shortcutPath = Join-Path $startup $shortcutName

Write-Host "[INFO] Název zástupce: $shortcutName"
Write-Host ""

# Zkontrolovat, zda existuje VBS skript
if (-not (Test-Path $vbsScript)) {
    Write-Host "[ERROR] VBS skript neexistuje: $vbsScript" -ForegroundColor Red
    Write-Host "[INFO] Zkontrolujte, zda je soubor scripts/windows/run_tray_hidden.vbs přítomen" -ForegroundColor Yellow
    exit 1
}

# Pokud existuje starý zástupce, smaž ho
if (Test-Path $shortcutPath) {
    Write-Host "[INFO] Odstraňuji existující zástupce..." -ForegroundColor Yellow
    Remove-Item $shortcutPath -Force
    Write-Host "[OK] Starý zástupce odstraněn"
}

# Vytvořit nový zástupce, který spouští VBS skript přes wscript.exe
Write-Host "[INFO] Vytvářím nový zástupce (skryté spuštění)..."
try {
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($shortcutPath)
    $sc.TargetPath = "wscript.exe"
    $sc.Arguments = "`"$vbsScript`""
    $sc.WorkingDirectory = $projectRoot
    $sc.WindowStyle = 0  # Hidden
    $sc.IconLocation = "wscript.exe,0"
    $sc.Description = "TooZ Hub 2 - Tray Manager (Hidden)"
    $sc.Save()
    
    Write-Host ""
    Write-Host "✅ Zástupce byl úspěšně vytvořen!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Zástupce: $shortcutPath"
    Write-Host ""
    Write-Host "Tray aplikace se nyní spustí automaticky při každém přihlášení do Windows."
    Write-Host ""
    Write-Host "Pro odebrání z Autostartu:"
    Write-Host "  1. Stiskněte Win + R"
    Write-Host "  2. Zadejte: shell:startup"
    Write-Host "  3. Odstraňte soubor: $shortcutName"
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "[ERROR] Chyba při vytváření zástupce: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Zkuste spustit PowerShell jako správce (Run as Administrator)."
    Write-Host ""
    exit 1
}

