# scripts/windows/start_tray.ps1
# Spuštění tray aplikace pro TOOZHUB2

param()

# Zjistit root projektu (dva adresáře nahoru od tohoto skriptu)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Set-Location $projectRoot

Write-Host "========================================"
Write-Host "  TooZ Hub 2 - Spuštění Tray Aplikace"
Write-Host "========================================"
Write-Host ""

# Zkontrolovat, zda existuje venv
$pythonExe = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $pythonExe = "venv\Scripts\python.exe"
    Write-Host "[INFO] Používám Python z virtuálního prostředí"
} else {
    Write-Host "[INFO] Používám systémový Python"
}

# Zkontrolovat, zda existuje tray skript
$trayScript = "$projectRoot\tray\tray_app.py"
if (-not (Test-Path $trayScript)) {
    Write-Host "[ERROR] Tray skript neexistuje: $trayScript" -ForegroundColor Red
    Write-Host "[INFO] Zkontrolujte, zda je soubor tray\tray_app.py přítomen" -ForegroundColor Yellow
    pause
    exit 1
}

# Spustit tray aplikaci na pozadí bez viditelného okna
Write-Host "[INFO] Spouštím tray aplikaci na pozadí..."
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $pythonExe
$processInfo.Arguments = "`"$trayScript`""
$processInfo.WorkingDirectory = $projectRoot
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $processInfo
$process.Start() | Out-Null

# Uvolnit proces z terminálu (detach) - proces běží nezávisle
$process.Dispose()

Write-Host ""
Write-Host "✅ Tray aplikace byla spuštěna!"
Write-Host ""
Write-Host "Ikona by se měla objevit v systémové liště (u hodin)."
Write-Host "Pro ukončení klikněte pravým tlačítkem na ikonu a vyberte 'Ukončit'."
Write-Host ""

