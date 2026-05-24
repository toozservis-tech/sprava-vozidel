# Skript pro spuštění všech GitHub Actions workflows
# Vytvoří prázdný commit, který spustí všechny workflows nastavené na push

Write-Host "Spouštění všech GitHub Actions workflows..." -ForegroundColor Green
Write-Host ""

# Zkontrolovat, zda jsme v git repozitáři
if (-not (Test-Path .git)) {
    Write-Host "ERROR: Nejsme v git repozitáři!" -ForegroundColor Red
    exit 1
}

# Zkontrolovat, zda jsou změny commitnuté
$status = git status --porcelain
if ($status) {
    Write-Host "VAROVÁNÍ: Máte necommitnuté změny:" -ForegroundColor Yellow
    Write-Host $status
    Write-Host ""
    Write-Host "Commituji změny před spuštěním testů..." -ForegroundColor Cyan
    git add .
    git commit -m "ci: Prepare for comprehensive testing"
}

# Vytvořit prázdný commit pro spuštění workflows
Write-Host "Vytváření prázdného commitu pro spuštění workflows..." -ForegroundColor Cyan
git commit --allow-empty -m "ci: Trigger all workflows for comprehensive testing

- QA Tests
- Security Checks
- Production Smoke Tests (if on main/master)
- Full Test Suite (if exists)"

# Push na GitHub
Write-Host ""
Write-Host "Pushnutí na GitHub..." -ForegroundColor Cyan
git push origin master

Write-Host ""
Write-Host "✅ Workflows byly spuštěny!" -ForegroundColor Green
Write-Host ""
Write-Host "Sledujte průběh na:" -ForegroundColor Yellow
Write-Host "https://github.com/toozservis-tech/TOOZHUB2/actions" -ForegroundColor Cyan
Write-Host ""
Write-Host "Spuštěné workflows:" -ForegroundColor Yellow
Write-Host "  - QA Tests" -ForegroundColor White
Write-Host "  - Security Checks" -ForegroundColor White
Write-Host "  - Production Smoke Tests (pokud na main/master)" -ForegroundColor White
Write-Host "  - Full Test Suite (pokud existuje)" -ForegroundColor White

