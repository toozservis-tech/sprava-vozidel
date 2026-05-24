# scripts/windows/run_server.ps1
# Spuštění FastAPI serveru pro TOOZHUB2

param(
    [int]$Port = 8000
)

# Nastavit working directory na root projektu
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

# Zkontrolovat, zda existuje venv
$pythonExe = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $pythonExe = "venv\Scripts\python.exe"
}

# Spusť uvicorn na pozadí bez viditelného okna
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $pythonExe
$processInfo.Arguments = "-m uvicorn src.server.main:app --host 127.0.0.1 --port $Port"
$processInfo.WorkingDirectory = $projectRoot
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true
$processInfo.RedirectStandardOutput = $false
$processInfo.RedirectStandardError = $false

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $processInfo
$process.Start() | Out-Null

# NEDISPOSOVAT proces - nechat ho běžet
# $process.Dispose() - NESMAZAT - proces musí běžet!

# Zkontrolovat, zda proces běží
Start-Sleep -Milliseconds 2000
try {
    $uvicornProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($uvicornProcess) {
        # Output pouze pokud je voláno z terminálu (ne z tray)
        if ($Host.UI.RawUI.WindowSize.Width -gt 0) {
            Write-Host "Server spuštěn na portu $Port (PID: $($process.Id))" -ForegroundColor Green
        }
    }
} catch {
    # Tichý běh - žádný output
}

