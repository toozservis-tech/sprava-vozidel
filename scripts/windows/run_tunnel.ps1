# scripts/windows/run_tunnel.ps1
# Spuštění Cloudflare Tunnel pro TOOZHUB2

# UPRAV tyto hodnoty podle projektu:
$tunnelName = "tooz-hub2"      # Název tunelu v Cloudflare
$hostname = "hub.toozservis.cz"      # Veřejná doména

# Nastavit working directory na root projektu
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

# Zkontrolovat, zda je cloudflared nainstalován
$cloudflaredExe = "cloudflared"
if (-not (Get-Command $cloudflaredExe -ErrorAction SilentlyContinue)) {
    Write-Host "CHYBA: cloudflared.exe nebyl nalezen v PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Instalujte cloudflared:"
    Write-Host "1. Stáhněte z: https://github.com/cloudflare/cloudflared/releases"
    Write-Host "2. Nebo použijte: winget install --id Cloudflare.cloudflared"
    Write-Host ""
    Write-Host "Ujistěte se, že máte vytvořený tunel:"
    Write-Host "  cloudflared tunnel create $tunnelName"
    Write-Host "  cloudflared tunnel route dns $tunnelName $hostname"
    exit 1
}

# Zkontrolovat, zda existuje config soubor
$configFile = Join-Path $projectRoot "cloudflared\config.yml"
if (-not (Test-Path $configFile)) {
    $configFile = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    if (-not (Test-Path $configFile)) {
        Write-Host "CHYBA: Config soubor neexistuje!" -ForegroundColor Red
        Write-Host "Očekávané umístění:"
        Write-Host "  - $projectRoot\cloudflared\config.yml"
        Write-Host "  - $configFile"
        exit 1
    }
}

# Spuštění cloudflared tunnel na pozadí bez viditelného okna
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $cloudflaredExe
$processInfo.Arguments = "tunnel --config `"$configFile`" run $tunnelName"
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
    $tunnelProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($tunnelProcess) {
        # Output pouze pokud je voláno z terminálu (ne z tray)
        if ($Host.UI.RawUI.WindowSize.Width -gt 0) {
            Write-Host "Cloudflare Tunnel spuštěn: $tunnelName -> $hostname (PID: $($process.Id))" -ForegroundColor Green
            Write-Host "Config soubor: $configFile"
        }
    }
} catch {
    # Tichý běh - žádný output
}

