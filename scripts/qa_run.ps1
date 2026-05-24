# QA Run Script - Spustí všechny testy
# Použití: .\scripts\qa_run.ps1

param(
    [switch]$SkipBackend,
    [switch]$SkipAPI,
    [switch]$SkipE2E,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# Vytvořit artifacts složku
$artifactsDir = Join-Path $projectRoot "artifacts\qa"
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TOOZHUB2 QA RUN" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendProcess = $null
$backendStarted = $false

# Funkce pro kontrolu, zda server běží
function Test-ServerRunning {
    param([string]$Url, [int]$TimeoutSeconds = 30)
    
    $endTime = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $endTime) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

# Funkce pro zastavení backendu
function Stop-Backend {
    if ($backendProcess -and !$backendProcess.HasExited) {
        Write-Host "Zastavuji backend..." -ForegroundColor Yellow
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        $backendProcess = $null
    }
    
    # Zastavit všechny procesy uvicorn na portu
    $processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processes) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

# Spuštění backendu
if (-not $SkipBackend) {
    Write-Host "[1/4] Spouštím backend server..." -ForegroundColor Green
    
    # Zastavit existující procesy na portu
    $existingProcesses = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $existingProcesses) {
        Write-Host "Zastavuji existující proces na portu $Port (PID: $processId)..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    
    # Spustit backend
    $pythonExe = "python"
    if (Test-Path "venv\Scripts\python.exe") {
        $pythonExe = "venv\Scripts\python.exe"
    }
    
    $backendProcess = Start-Process -FilePath $pythonExe -ArgumentList @(
        "-m", "uvicorn",
        "src.server.main:app",
        "--host", "127.0.0.1",
        "--port", "$Port"
    ) -PassThru -WindowStyle Hidden
    
    Write-Host "Backend spuštěn (PID: $($backendProcess.Id))" -ForegroundColor Green
    
    # Počkat na readiness
    $healthUrl = "http://127.0.0.1:$Port/health"
    Write-Host "Čekám na připravenost serveru..." -ForegroundColor Yellow
    
    if (Test-ServerRunning -Url $healthUrl -TimeoutSeconds 30) {
        Write-Host "✓ Server je připraven" -ForegroundColor Green
        $backendStarted = $true
    } else {
        Write-Host "✗ Server se nespustil včas" -ForegroundColor Red
        Stop-Backend
        exit 1
    }
    Write-Host ""
}

# Spuštění API testů
if (-not $SkipAPI) {
    Write-Host "[2/4] Spouštím API testy (pytest)..." -ForegroundColor Green
    
    # Zkontrolovat Python exe
    $pythonExe = "python"
    if (Test-Path "venv\Scripts\python.exe") {
        $pythonExe = "venv\Scripts\python.exe"
    }
    
    # Zkontrolovat, zda je pytest nainstalován
    $pytestCheck = & $pythonExe -m pytest --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠ pytest není nainstalován. Instaluji..." -ForegroundColor Yellow
        & $pythonExe -m pip install pytest pytest-asyncio
    }
    
    $pytestOutput = Join-Path $artifactsDir "pytest-report.txt"
    $pytestXml = Join-Path $artifactsDir "pytest-report.xml"
    
    $pytestArgs = @(
        "-m", "pytest",
        "tests/api",
        "-v",
        "--tb=short",
        "--junit-xml=$pytestXml"
    )
    
    Push-Location $projectRoot
    try {
        # Použít Invoke-Expression místo Start-Process pro lepší přesměrování
        $pytestCmd = "$pythonExe -m pytest tests/api -v --tb=short --junit-xml=`"$pytestXml`""
        $pytestResult = Invoke-Expression $pytestCmd 2>&1 | Tee-Object -FilePath $pytestOutput
        $pytestExitCode = $LASTEXITCODE
        
        if ($pytestExitCode -eq 0) {
            Write-Host "✓ API testy prošly" -ForegroundColor Green
        } else {
            Write-Host "✗ API testy selhaly (Exit code: $pytestExitCode)" -ForegroundColor Red
            if (Test-Path $pytestOutput) {
                Write-Host "Poslední řádky výstupu:" -ForegroundColor Yellow
                Get-Content $pytestOutput -Tail 20 | Write-Host
            }
        }
    } finally {
        Pop-Location
    }
    Write-Host ""
}

# Instalace Playwright závislostí (pokud nejsou)
if (-not $SkipE2E) {
    Write-Host "[3/4] Kontroluji Playwright závislosti..." -ForegroundColor Green
    
    $e2eDir = Join-Path $projectRoot "tests\e2e"
    if (Test-Path $e2eDir) {
        Push-Location $e2eDir
        
        if (-not (Test-Path "node_modules")) {
            Write-Host "Instaluji npm závislosti..." -ForegroundColor Yellow
            npm install
        }
        
        if (-not (Get-Command "npx" -ErrorAction SilentlyContinue)) {
            Write-Host "✗ npx není dostupný. Nainstalujte Node.js." -ForegroundColor Red
            Pop-Location
            Stop-Backend
            exit 1
        }
        
        Write-Host "Instaluji Playwright prohlížeče (pokud chybí)..." -ForegroundColor Yellow
        npx playwright install --with-deps chromium 2>&1 | Out-Null
        
        Pop-Location
    }
    Write-Host ""
}

# Spuštění E2E testů
if (-not $SkipE2E) {
    Write-Host "[4/4] Spouštím E2E testy (Playwright)..." -ForegroundColor Green
    
    $e2eDir = Join-Path $projectRoot "tests\e2e"
    
    if (-not (Test-Path $e2eDir)) {
        Write-Host "✗ E2E testy nebyly nalezeny v: $e2eDir" -ForegroundColor Red
    } else {
        Push-Location $e2eDir
        
        # Zkontrolovat, zda jsou nainstalovány závislosti
        if (-not (Test-Path "node_modules")) {
            Write-Host "Instaluji npm závislosti..." -ForegroundColor Yellow
            npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Host "✗ Selhala instalace npm závislostí" -ForegroundColor Red
                Pop-Location
                Stop-Backend
                exit 1
            }
        }
        
        $playwrightOutput = Join-Path $artifactsDir "playwright-output.txt"
        
        # Spustit Playwright testy
        $env:CI = "true"
        npx playwright test --reporter=list,html 2>&1 | Tee-Object -FilePath $playwrightOutput
        
        $playwrightExitCode = $LASTEXITCODE
        
        Pop-Location
        
        if ($playwrightExitCode -eq 0) {
            Write-Host "✓ E2E testy prošly" -ForegroundColor Green
        } else {
            Write-Host "✗ E2E testy selhaly (Exit code: $playwrightExitCode)" -ForegroundColor Red
            if (Test-Path $playwrightOutput) {
                Write-Host "Poslední řádky výstupu:" -ForegroundColor Yellow
                Get-Content $playwrightOutput -Tail 20 | Write-Host
            }
        }
    }
    Write-Host ""
}

# Zastavení backendu
if ($backendStarted) {
    Stop-Backend
}

# Shrnutí
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  QA RUN DOKONČEN" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Výstupy jsou v: $artifactsDir" -ForegroundColor Yellow
Write-Host ""

if ($backendStarted) {
    Write-Host "Backend byl zastaven." -ForegroundColor Green
}
