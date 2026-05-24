# PowerShell script pro rychlý restart serveru a tunelu
# Použití: .\scripts\restart_server_tunnel.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  RESTART SERVERU A TUNELU" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Zastavit všechny procesy
Write-Host "[1/4] Zastavuji existující procesy..." -ForegroundColor Yellow

# Zastavit procesy na portu 8000
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($port8000) {
    foreach ($processId in $port8000) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Host "  Zastaven proces na portu 8000: PID $processId" -ForegroundColor Gray
    }
}

# Zastavit cloudflared
$cloudflared = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($cloudflared) {
    $cloudflared | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  Zastaven cloudflared" -ForegroundColor Gray
}

# Zastavit Python procesy (uvicorn)
$python = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    $cmdLine -like "*uvicorn*" -or $cmdLine -like "*main:app*"
}
if ($python) {
    $python | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  Zastaveny Python procesy (uvicorn)" -ForegroundColor Gray
}

Start-Sleep -Seconds 2

# Zkontrolovat, že port je volný
Write-Host "[2/4] Kontroluji port 8000..." -ForegroundColor Yellow
$portCheck = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($portCheck) {
    Write-Host "  VAROVÁNÍ: Port 8000 je stále obsazen!" -ForegroundColor Red
    Write-Host "  Zkusím znovu zastavit procesy..." -ForegroundColor Yellow
    Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "  Port 8000 je volný" -ForegroundColor Green
}

# Spustit server a tunnel
Write-Host "[3/4] Spouštím server a tunnel..." -ForegroundColor Yellow

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $projectRoot "start_server_with_tunnel.bat"
if (Test-Path $scriptPath) {
    Start-Process -FilePath $scriptPath -WorkingDirectory $projectRoot
    Write-Host "  Spuštěn start_server_with_tunnel.bat" -ForegroundColor Gray
} else {
    Write-Host "  CHYBA: start_server_with_tunnel.bat nenalezen!" -ForegroundColor Red
    exit 1
}

# Počkat na spuštění
Write-Host "[4/4] Čekám na spuštění služeb..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

# Ověřit, že server běží
Write-Host ""
Write-Host "Ověřuji funkčnost..." -ForegroundColor Cyan

$serverRunning = $false
$tunnelRunning = $false

# Zkontrolovat server
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $serverRunning = $true
        Write-Host "  ✅ Server běží (http://localhost:8000)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ❌ Server neběží nebo neodpovídá" -ForegroundColor Red
}

# Zkontrolovat tunnel
$cloudflared = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($cloudflared) {
    $tunnelRunning = $true
    Write-Host "  ✅ Cloudflare Tunnel běží" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Cloudflare Tunnel se nespustil (možná chybí config)" -ForegroundColor Yellow
}

# Zkontrolovat veřejnou URL
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/health" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ Veřejná URL funguje (https://hub.toozservis.cz)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ⚠️  Veřejná URL neodpovídá (tunnel možná ještě nestartoval)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($serverRunning) {
    Write-Host "  ✅ RESTART DOKONČEN" -ForegroundColor Green
} else {
    Write-Host "  ❌ RESTART SELHAL - zkontroluj logy" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

