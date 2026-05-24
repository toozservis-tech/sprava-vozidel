# scripts/windows/start_all.ps1
# Spuštění serveru + Cloudflare Tunnel pro TOOZHUB2

param(
    [int]$Port = 8000
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host "========================================"
Write-Host "  TOOZ HUB 2 - Spuštění serveru + tunelu"
Write-Host "========================================"
Write-Host ""

# Spusť server
Write-Host "[1/2] Spouštím FastAPI server na portu $Port..."
Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-File", (Join-Path $scriptDir "run_server.ps1"),
    "-Port", "$Port"
) -WindowStyle Minimized

# Počkat 2 sekundy, než se server spustí
Start-Sleep -Seconds 2

# Spusť Cloudflare Tunnel
Write-Host "[2/2] Spouštím Cloudflare Tunnel..."
Start-Process powershell -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-NoExit",
    "-File", (Join-Path $scriptDir "run_tunnel.ps1")
) -WindowStyle Minimized

Write-Host ""
Write-Host "✅ Server a tunnel byly spuštěny!"
Write-Host ""
Write-Host "Server: http://127.0.0.1:$Port"
Write-Host "Veřejná URL: https://hub.toozservis.cz"
Write-Host ""
Write-Host "Pro zastavení použijte Task Manager."


