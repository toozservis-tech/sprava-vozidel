# PowerShell skript pro pomoc s nastavením GitHub Secrets
# POZNÁMKA: Tento skript pouze zobrazí instrukce - secrets musíš nastavit ručně v GitHub UI

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GITHUB SECRETS SETUP GUIDE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Pro nastavení GitHub Secrets pro Production Smoke Tests:" -ForegroundColor Yellow
Write-Host ""

Write-Host "1. Otevři GitHub repozitář v prohlížeči" -ForegroundColor Green
Write-Host "   https://github.com/[TVAJE-ORGANIZACE]/TOOZHUB2" -ForegroundColor Gray
Write-Host ""

Write-Host "2. Jdi do Settings → Secrets and variables → Actions" -ForegroundColor Green
Write-Host ""

Write-Host "3. Přidej následující secrets:" -ForegroundColor Green
Write-Host ""
Write-Host "   Secret 1:" -ForegroundColor Yellow
Write-Host "   - Name: PROD_E2E_EMAIL" -ForegroundColor White
Write-Host "   - Value: [tvůj-produkční-email]" -ForegroundColor Gray
Write-Host ""
Write-Host "   Secret 2:" -ForegroundColor Yellow
Write-Host "   - Name: PROD_E2E_PASSWORD" -ForegroundColor White
Write-Host "   - Value: [tvůj-produkční-heslo]" -ForegroundColor Gray
Write-Host ""

Write-Host "4. Po nastavení secrets:" -ForegroundColor Green
Write-Host "   - Workflow se spustí automaticky při push na main" -ForegroundColor Gray
Write-Host "   - Nebo spusť ručně: Actions → Production Smoke Tests → Run workflow" -ForegroundColor Gray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Zkusit zjistit GitHub URL z git remote
$gitRemote = git remote get-url origin 2>$null
if ($gitRemote) {
    # Konverze SSH na HTTPS nebo extrakce URL
    if ($gitRemote -match 'git@github\.com:(.+?)(?:\.git)?$') {
        $repoPath = $matches[1]
        $repoUrl = "https://github.com/$repoPath"
    } elseif ($gitRemote -match 'https://github\.com/(.+?)(?:\.git)?$') {
        $repoPath = $matches[1]
        $repoUrl = "https://github.com/$repoPath"
    } else {
        $repoUrl = $null
    }
    
    if ($repoUrl) {
        Write-Host "Nalezen GitHub repozitář: $repoUrl" -ForegroundColor Green
        Write-Host ""
        $open = Read-Host "Otevřít stránku pro nastavení secrets? (Y/N)"
        if ($open -eq 'Y' -or $open -eq 'y') {
            Write-Host "Otevírám GitHub Secrets v prohlížeči..." -ForegroundColor Yellow
            Start-Process "$repoUrl/settings/secrets/actions"
        }
    } else {
        Write-Host "Nepodařilo se zjistit GitHub URL z git remote" -ForegroundColor Yellow
    }
} else {
    Write-Host "Git remote není nastavený" -ForegroundColor Yellow
    Write-Host ""
    $repoUrl = Read-Host "Zadej URL GitHub repozitáře (nebo Enter pro přeskočení)"
    if ($repoUrl) {
        Write-Host "Otevírám GitHub repozitář v prohlížeči..." -ForegroundColor Yellow
        Start-Process "$repoUrl/settings/secrets/actions"
    }
}

if (-not $repoUrl) {
    Write-Host "Pro nastavení secrets jdi na:" -ForegroundColor Yellow
    Write-Host "https://github.com/[TVAJE-ORGANIZACE]/TOOZHUB2/settings/secrets/actions" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Více informací: docs/GITHUB_SECRETS_SETUP.md" -ForegroundColor Gray

