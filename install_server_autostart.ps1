# PowerShell script pro instalaci automatického startu serveru TooZ Hub 2
# Spouští server + Cloudflare Tunnel při každém přihlášení do Windows

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INSTALACE AUTOSTARTU - TOOZ HUB 2" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Kontrola, zda běží jako správce
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[VAROVANI] Script neběží jako správce (Administrator)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Pro vytvoření úkolu v Task Scheduleru jsou potřeba admin práva." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Možnosti:" -ForegroundColor Cyan
    Write-Host "1. Spustit PowerShell jako správce a znovu spustit tento script" -ForegroundColor White
    Write-Host "2. Použít alternativní metodu (Startup složka) - nevyžaduje admin práva" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "Chcete použít alternativní metodu (Startup složka)? (A/N)"
    
    if ($choice -eq "A" -or $choice -eq "a") {
        # Použít Startup složku místo Task Scheduleru
        Write-Host ""
        Write-Host "[INFO] Používám alternativní metodu (Startup složka)..." -ForegroundColor Yellow
        
        $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $StartScript = Join-Path $ScriptDir "start_server_background.bat"
        $StartupFolder = [System.Environment]::GetFolderPath("Startup")
        $ShortcutPath = Join-Path $StartupFolder "TooZHub2-Server-Autostart.lnk"
        
        # Vytvořit zástupce
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $StartScript
        $Shortcut.WorkingDirectory = $ScriptDir
        $Shortcut.Description = "Automatické spuštění TooZ Hub 2 serveru"
        $Shortcut.Save()
        
        Write-Host "[OK] Zástupce vytvořen v Startup složce!" -ForegroundColor Green
        Write-Host "     Cesta: $ShortcutPath" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Server se nyní spustí automaticky při každém přihlášení do Windows." -ForegroundColor Green
        Write-Host ""
        pause
        exit 0
    } else {
        Write-Host ""
        Write-Host "[INFO] Pro pokračování spusťte PowerShell jako správce:" -ForegroundColor Yellow
        Write-Host "1. Klikněte pravým tlačítkem na PowerShell" -ForegroundColor White
        Write-Host "2. Vyberte 'Spustit jako správce'" -ForegroundColor White
        Write-Host "3. Spusťte znovu: .\install_server_autostart.ps1" -ForegroundColor White
        Write-Host ""
        pause
        exit 1
    }
}

# Získat cestu ke skriptu
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir

Write-Host "[INFO] Projekt složka: $ProjectRoot" -ForegroundColor Yellow
Write-Host ""

# Zkontrolovat, zda existuje start_server_background.bat (pro autostart)
$StartScript = Join-Path $ProjectRoot "start_server_background.bat"
if (-not (Test-Path $StartScript)) {
    # Fallback na start_server_with_tunnel.bat
    $StartScript = Join-Path $ProjectRoot "start_server_with_tunnel.bat"
    if (-not (Test-Path $StartScript)) {
        Write-Host "[CHYBA] Start script nebyl nalezen!" -ForegroundColor Red
        Write-Host "       Hledal jsem: start_server_background.bat a start_server_with_tunnel.bat" -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host "[OK] Start script nalezen: $StartScript" -ForegroundColor Green
Write-Host ""

# Název úkolu v Task Scheduleru
$TaskName = "TooZHub2-Server-Autostart"

# Zkontrolovat, zda úkol už existuje
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Write-Host "[INFO] Úkol '$TaskName' už existuje." -ForegroundColor Yellow
    $Response = Read-Host "Chcete ho přepsat? (A/N)"
    if ($Response -ne "A" -and $Response -ne "a") {
        Write-Host "[INFO] Instalace zrušena." -ForegroundColor Yellow
        pause
        exit 0
    }
    Write-Host "[INFO] Odebírám existující úkol..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Existující úkol odebrán." -ForegroundColor Green
    Write-Host ""
}

# Vytvořit akci - spustit batch soubor
$Action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$StartScript`"" `
    -WorkingDirectory $ProjectRoot

# Vytvořit trigger - při přihlášení
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Nastavení úkolu
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Vytvořit principál (spustit jako aktuální uživatel)
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Vytvořit úkol
try {
    Write-Host "[INFO] Vytvářím úkol v Task Scheduleru..." -ForegroundColor Yellow
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Automatické spuštění TooZ Hub 2 serveru a Cloudflare Tunnel při přihlášení do Windows" `
        -ErrorAction Stop | Out-Null
    
    Write-Host "[OK] Úkol úspěšně vytvořen!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[CHYBA] Nepodařilo se vytvořit úkol: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Zkuste:" -ForegroundColor Yellow
    Write-Host "1. Spustit PowerShell jako správce (pravý klik -> Spustit jako správce)" -ForegroundColor White
    Write-Host "2. Nebo použít alternativní metodu (Startup složka)" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

# Zobrazit informace o úkolu
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  INSTALACE DOKONČENA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Úkol: $TaskName" -ForegroundColor Green
Write-Host "Spouští se: Při každém přihlášení do Windows" -ForegroundColor Green
Write-Host "Spouští: $StartScript" -ForegroundColor Green
Write-Host ""
Write-Host "Pro ověření otevřete Task Scheduler (taskschd.msc)" -ForegroundColor Yellow
Write-Host "a najděte úkol '$TaskName'." -ForegroundColor Yellow
Write-Host ""
Write-Host "Pro odebrání autostartu spusťte:" -ForegroundColor Yellow
Write-Host "  .\uninstall_server_autostart.ps1" -ForegroundColor Cyan
Write-Host ""

pause








