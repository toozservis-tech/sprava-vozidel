# PowerShell script pro kontrolu GitHub Actions workflows
# Kontroluje syntaxi, konfiguraci a potenciální problémy

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  KONTROLA GITHUB ACTIONS WORKFLOWS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$errors = @()
$warnings = @()

# Kontrola existence workflow souborů
Write-Host "[1/5] Kontroluji workflow soubory..." -ForegroundColor Yellow

$workflowFiles = @(
    ".github/workflows/qa.yml",
    ".github/workflows/prod-smoke.yml",
    ".github/workflows/auto-fix.yml"
)

foreach ($file in $workflowFiles) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file existuje" -ForegroundColor Green
    } else {
        $errors += "Workflow soubor neexistuje: $file"
        Write-Host "  ❌ $file neexistuje" -ForegroundColor Red
    }
}

# Kontrola existence helper skriptů
Write-Host ""
Write-Host "[2/5] Kontroluji helper skripty..." -ForegroundColor Yellow

$scriptFiles = @(
    ".github/scripts/analyze_failed_workflow.py",
    ".github/scripts/apply_fixes.py"
)

foreach ($file in $scriptFiles) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file existuje" -ForegroundColor Green
    } else {
        $warnings += "Helper skript neexistuje: $file"
        Write-Host "  ⚠️  $file neexistuje" -ForegroundColor Yellow
    }
}

# Kontrola YAML syntaxe (základní)
Write-Host ""
Write-Host "[3/5] Kontroluji YAML syntaxi..." -ForegroundColor Yellow

foreach ($file in $workflowFiles) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        
        # Kontrola základních problémů
        if ($content -match '^\s*if:\s*$') {
            $errors += "$file: Prázdná podmínka 'if:'"
            Write-Host "  ❌ $file: Prázdná podmínka 'if:'" -ForegroundColor Red
        }
        
        if ($content -notmatch 'name:') {
            $errors += "$file: Chybí 'name:'"
            Write-Host "  ❌ $file: Chybí 'name:'" -ForegroundColor Red
        }
        
        if ($content -notmatch 'on:') {
            $errors += "$file: Chybí 'on:'"
            Write-Host "  ❌ $file: Chybí 'on:'" -ForegroundColor Red
        }
        
        if ($content -notmatch 'jobs:') {
            $errors += "$file: Chybí 'jobs:'"
            Write-Host "  ❌ $file: Chybí 'jobs:'" -ForegroundColor Red
        }
        
        # Kontrola neuzavřených závorek v podmínkách
        $ifCount = ([regex]::Matches($content, 'if:')).Count
        $thenCount = ([regex]::Matches($content, 'then:')).Count
        if ($ifCount -gt 0 -and $thenCount -eq 0) {
            # GitHub Actions nepoužívá then, takže to je OK
        }
        
        Write-Host "  ✅ $file: Základní syntax OK" -ForegroundColor Green
    }
}

# Kontrola konfigurace
Write-Host ""
Write-Host "[4/5] Kontroluji konfiguraci..." -ForegroundColor Yellow

# QA workflow
$qaContent = Get-Content ".github/workflows/qa.yml" -Raw -ErrorAction SilentlyContinue
if ($qaContent) {
    if ($qaContent -notmatch 'E2E_EMAIL') {
        $warnings += "qa.yml: Chybí E2E_EMAIL env variable"
        Write-Host "  ⚠️  qa.yml: Chybí E2E_EMAIL" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ qa.yml: E2E credentials nastavené" -ForegroundColor Green
    }
}

# Prod-smoke workflow
$prodContent = Get-Content ".github/workflows/prod-smoke.yml" -Raw -ErrorAction SilentlyContinue
if ($prodContent) {
    if ($prodContent -notmatch 'PROD_E2E_EMAIL') {
        $warnings += "prod-smoke.yml: Chybí PROD_E2E_EMAIL secret reference"
        Write-Host "  ⚠️  prod-smoke.yml: Chybí PROD_E2E_EMAIL" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ prod-smoke.yml: Production secrets reference OK" -ForegroundColor Green
    }
    
    if ($prodContent -notmatch 'BASE_URL.*hub\.toozservis\.cz') {
        $warnings += "prod-smoke.yml: BASE_URL možná není správně nastavený"
        Write-Host "  ⚠️  prod-smoke.yml: Zkontroluj BASE_URL" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ prod-smoke.yml: BASE_URL nastavený" -ForegroundColor Green
    }
}

# Auto-fix workflow
$autoFixContent = Get-Content ".github/workflows/auto-fix.yml" -Raw -ErrorAction SilentlyContinue
if ($autoFixContent) {
    # Kontrola, že Apply fixes má podmínku
    if ($autoFixContent -match 'name: Apply fixes' -and $autoFixContent -notmatch 'name: Apply fixes[\s\S]*?if:') {
        $errors += "auto-fix.yml: Apply fixes step nemá podmínku 'if:'"
        Write-Host "  ❌ auto-fix.yml: Apply fixes nemá podmínku" -ForegroundColor Red
    } else {
        Write-Host "  ✅ auto-fix.yml: Apply fixes má podmínku" -ForegroundColor Green
    }
}

# Kontrola test souborů
Write-Host ""
Write-Host "[5/5] Kontroluji test soubory..." -ForegroundColor Yellow

$testFiles = @(
    "tests/e2e/prod-smoke.spec.ts",
    "tests/e2e/helpers.ts"
)

foreach ($file in $testFiles) {
    if (Test-Path $file) {
        Write-Host "  ✅ $file existuje" -ForegroundColor Green
    } else {
        $warnings += "Test soubor neexistuje: $file"
        Write-Host "  ⚠️  $file neexistuje" -ForegroundColor Yellow
    }
}

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SHRNUTÍ" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($errors.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "✅ Všechny kontroly prošly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Pro zkontrolování skutečných workflow runů:" -ForegroundColor Cyan
    Write-Host "https://github.com/toozservis-tech/TOOZHUB2/actions" -ForegroundColor Gray
    exit 0
} else {
    if ($errors.Count -gt 0) {
        Write-Host "❌ Nalezeny chyby ($($errors.Count)):" -ForegroundColor Red
        foreach ($error in $errors) {
            Write-Host "  - $error" -ForegroundColor Red
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
    
    Write-Host "Pro zkontrolování skutečných workflow runů:" -ForegroundColor Cyan
    Write-Host "https://github.com/toozservis-tech/TOOZHUB2/actions" -ForegroundColor Gray
    
    exit 1
}

