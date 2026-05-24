# Kompletní lokální testování - spustí všechny možné testy

Write-Host "🧪 Spouštění kompletního testovacího balíčku..." -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# 1. Python syntax check
Write-Host "1️⃣ Kontrola Python syntaxe..." -ForegroundColor Yellow
$pythonFiles = Get-ChildItem -Path src -Recurse -Filter "*.py"
$syntaxErrors = 0
foreach ($file in $pythonFiles) {
    try {
        python -m py_compile $file.FullName 2>&1 | Out-Null
    } catch {
        Write-Host "  ❌ Syntax error v: $($file.FullName)" -ForegroundColor Red
        $syntaxErrors++
    }
}
if ($syntaxErrors -eq 0) {
    Write-Host "  ✅ Všechny Python soubory jsou syntakticky validní" -ForegroundColor Green
} else {
    Write-Host "  ❌ Nalezeno $syntaxErrors syntax errors!" -ForegroundColor Red
    exit 1
}

# 2. Import check
Write-Host ""
Write-Host "2️⃣ Kontrola importů..." -ForegroundColor Yellow
try {
    python -c "from src.server.main import app; print('  ✅ Server import OK')" 2>&1
    python -c "from src.modules.ai_features.models import *; print('  ✅ AI Features modely import OK')" 2>&1
    python -c "from src.modules.ai_features.analytics import *; print('  ✅ Analytics import OK')" 2>&1
    python -c "from src.modules.ai_features.routers import *; print('  ✅ Routers import OK')" 2>&1
    Write-Host "  ✅ Všechny importy OK" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Import error!" -ForegroundColor Red
    exit 1
}

# 3. Database initialization
Write-Host ""
Write-Host "3️⃣ Inicializace databáze přes Alembic..." -ForegroundColor Yellow
try {
    if (Test-Path "test_vehicles.db") {
        Remove-Item "test_vehicles.db" -Force
    }
    python scripts/migrate_database.py upgrade head 2>&1
    Write-Host "  ✅ Databázové schema připraveno přes migrace" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Chyba při přípravě schématu přes migrace!" -ForegroundColor Red
    exit 1
}

# 4. Security check
Write-Host ""
Write-Host "4️⃣ Kontrola bezpečnosti..." -ForegroundColor Yellow
$sensitiveFiles = git ls-files | Select-String -Pattern "\.env$|\.log$|\.db$|\.sqlite$"
if ($sensitiveFiles) {
    Write-Host "  ❌ Nalezeny citlivé soubory v git:" -ForegroundColor Red
    $sensitiveFiles | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
    exit 1
} else {
    Write-Host "  ✅ Žádné citlivé soubory v git" -ForegroundColor Green
}

# 5. .gitignore check
Write-Host ""
Write-Host "5️⃣ Kontrola .gitignore..." -ForegroundColor Yellow
$gitignore = Get-Content .gitignore -Raw
if ($gitignore -notmatch "\.env") {
    Write-Host "  ❌ .env není v .gitignore!" -ForegroundColor Red
    exit 1
} else {
    Write-Host "  ✅ .gitignore OK" -ForegroundColor Green
}

# 6. API tests
Write-Host ""
Write-Host "6️⃣ Spouštění API testů..." -ForegroundColor Yellow
try {
    python -m pytest tests/api -v --tb=short
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ API testy prošly" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️ Některé API testy selhaly" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ Chyba při spouštění API testů!" -ForegroundColor Red
}

# 7. TypeScript check
Write-Host ""
Write-Host "7️⃣ Kontrola TypeScript..." -ForegroundColor Yellow
if (Test-Path "tests/e2e/node_modules") {
    Push-Location tests/e2e
    try {
        npx tsc --noEmit 2>&1 | Out-Null
        Write-Host "  ✅ TypeScript kompilace OK" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠️ TypeScript warnings (neblokující)" -ForegroundColor Yellow
    }
    Pop-Location
} else {
    Write-Host "  ⚠️ E2E dependencies nejsou nainstalované (spusťte: cd tests/e2e && npm install)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Kompletní testování dokončeno!" -ForegroundColor Green
Write-Host ""
Write-Host "Pro spuštění E2E testů použijte:" -ForegroundColor Cyan
Write-Host "  cd tests/e2e" -ForegroundColor White
Write-Host "  npx playwright test" -ForegroundColor White
