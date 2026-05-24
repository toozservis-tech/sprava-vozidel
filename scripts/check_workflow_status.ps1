# PowerShell script pro kontrolu stavu GitHub Actions workflows
# Zkontroluje workflow soubory a identifikuje potenciální problémy

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  KONTROLA GITHUB ACTIONS WORKFLOWS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$issues = @()
$warnings = @()

# 1. Kontrola workflow souborů
Write-Host "[1/6] Kontroluji workflow soubory..." -ForegroundColor Yellow

$workflows = @(
    @{File=".github/workflows/qa.yml"; Name="QA Tests"},
    @{File=".github/workflows/prod-smoke.yml"; Name="Production Smoke Tests"},
    @{File=".github/workflows/auto-fix.yml"; Name="Auto-Fix"}
)

foreach ($wf in $workflows) {
    if (Test-Path $wf.File) {
        $content = Get-Content $wf.File -Raw
        
        # Kontrola základní struktury
        if ($content -notmatch 'name:') {
            $issues += "$($wf.Name): Chybí 'name:'"
        }
        if ($content -notmatch 'on:') {
            $issues += "$($wf.Name): Chybí 'on:'"
        }
        if ($content -notmatch 'jobs:') {
            $issues += "$($wf.Name): Chybí 'jobs:'"
        }
        
        # Kontrola prázdných podmínek
        if ($content -match '^\s*if:\s*$' -or $content -match 'if:\s*$') {
            $issues += "$($wf.Name): Prázdná podmínka 'if:'"
        }
        
        Write-Host "  ✅ $($wf.Name)" -ForegroundColor Green
    } else {
        $issues += "$($wf.Name): Soubor neexistuje"
        Write-Host "  ❌ $($wf.Name): Soubor neexistuje" -ForegroundColor Red
    }
}

# 2. Kontrola helper skriptů
Write-Host ""
Write-Host "[2/6] Kontroluji helper skripty..." -ForegroundColor Yellow

$scripts = @(
    ".github/scripts/analyze_failed_workflow.py",
    ".github/scripts/apply_fixes.py"
)

foreach ($script in $scripts) {
    if (Test-Path $script) {
        $result = python -m py_compile $script 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ $(Split-Path $script -Leaf): Syntax OK" -ForegroundColor Green
        } else {
            $issues += "$script: Syntax error"
            Write-Host "  ❌ $(Split-Path $script -Leaf): Syntax error" -ForegroundColor Red
        }
    } else {
        $warnings += "$script: Neexistuje"
        Write-Host "  ⚠️  $(Split-Path $script -Leaf): Neexistuje" -ForegroundColor Yellow
    }
}

# 3. Kontrola test souborů
Write-Host ""
Write-Host "[3/6] Kontroluji test soubory..." -ForegroundColor Yellow

$testFiles = @(
    "tests/e2e/prod-smoke.spec.ts",
    "tests/e2e/helpers.ts",
    "tests/e2e/playwright.config.ts",
    "tests/e2e/package.json"
)

foreach ($file in $testFiles) {
    if (Test-Path $file) {
        Write-Host "  ✅ $(Split-Path $file -Leaf)" -ForegroundColor Green
    } else {
        $warnings += "$file: Neexistuje"
        Write-Host "  ⚠️  $(Split-Path $file -Leaf): Neexistuje" -ForegroundColor Yellow
    }
}

# 4. Kontrola konfigurace
Write-Host ""
Write-Host "[4/6] Kontroluji konfiguraci..." -ForegroundColor Yellow

# QA workflow
$qaContent = Get-Content ".github/workflows/qa.yml" -Raw -ErrorAction SilentlyContinue
if ($qaContent) {
    if ($qaContent -match 'E2E_EMAIL.*toozservis@gmail.com') {
        Write-Host "  ✅ QA: E2E credentials nastavené" -ForegroundColor Green
    } else {
        $warnings += "QA workflow: E2E credentials možná chybí"
    }
}

# Prod-smoke workflow
$prodContent = Get-Content ".github/workflows/prod-smoke.yml" -Raw -ErrorAction SilentlyContinue
if ($prodContent) {
    if ($prodContent -match 'PROD_E2E_EMAIL') {
        Write-Host "  ✅ Prod-smoke: Secrets reference OK" -ForegroundColor Green
    } else {
        $issues += "Prod-smoke workflow: Chybí PROD_E2E_EMAIL secret reference"
    }
    
    if ($prodContent -match 'BASE_URL.*hub\.toozservis\.cz') {
        Write-Host "  ✅ Prod-smoke: BASE_URL nastavený" -ForegroundColor Green
    }
}

# Auto-fix workflow
$autoFixContent = Get-Content ".github/workflows/auto-fix.yml" -Raw -ErrorAction SilentlyContinue
if ($autoFixContent) {
    # Kontrola podmínky if
    if ($autoFixContent -match 'if:\s*\|\s*$' -or $autoFixContent -match 'if:\s*github\.event_name') {
        Write-Host "  ✅ Auto-fix: Podmínka if správně nastavená" -ForegroundColor Green
    } else {
        $warnings += "Auto-fix workflow: Zkontroluj podmínku if"
    }
}

# 5. Kontrola dependencies
Write-Host ""
Write-Host "[5/6] Kontroluji dependencies..." -ForegroundColor Yellow

if (Test-Path "requirements.txt") {
    Write-Host "  ✅ requirements.txt existuje" -ForegroundColor Green
} else {
    $warnings += "requirements.txt: Neexistuje"
}

if (Test-Path "tests/e2e/package.json") {
    Write-Host "  ✅ tests/e2e/package.json existuje" -ForegroundColor Green
} else {
    $issues += "tests/e2e/package.json: Neexistuje"
}

# 6. Kontrola secrets (pouze varování)
Write-Host ""
Write-Host "[6/6] Kontroluji secrets reference..." -ForegroundColor Yellow
Write-Host "  ⚠️  Secrets musíš zkontrolovat manuálně v GitHub Settings" -ForegroundColor Yellow
Write-Host "     Potřebné secrets:" -ForegroundColor Gray
Write-Host "     - PROD_E2E_EMAIL" -ForegroundColor Gray
Write-Host "     - PROD_E2E_PASSWORD" -ForegroundColor Gray

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SHRNUTÍ" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($issues.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "✅ Všechny kontroly prošly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Workflow soubory jsou připravené." -ForegroundColor Gray
    Write-Host "Pro kontrolu skutečných workflow runů:" -ForegroundColor Cyan
    Write-Host "https://github.com/toozservis-tech/TOOZHUB2/actions" -ForegroundColor Gray
    exit 0
} else {
    if ($issues.Count -gt 0) {
        Write-Host "❌ Nalezeny problémy ($($issues.Count)):" -ForegroundColor Red
        foreach ($issue in $issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
        Write-Host ""
    }
    
    if ($warnings.Count -gt 0) {
        Write-Host "⚠️  Nalezena varování ($($warnings.Count)):" -ForegroundColor Yellow
        foreach ($warning in $warnings) {
            Write-Host "  - $warning" -ForegroundColor Yellow
        }
        Write-Host ""
    }
    
    Write-Host "Pro kontrolu skutečných workflow runů:" -ForegroundColor Cyan
    Write-Host "https://github.com/toozservis-tech/TOOZHUB2/actions" -ForegroundColor Gray
    
    exit 1
}

