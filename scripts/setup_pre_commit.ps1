# Setup script pro pre-commit hooks (Windows PowerShell)

Write-Host "Installing pre-commit hooks..." -ForegroundColor Green

# Instalace pre-commit
pip install pre-commit detect-secrets

# Vytvoření baseline pro detect-secrets
if (-not (Test-Path .secrets.baseline)) {
    Write-Host "Creating .secrets.baseline..." -ForegroundColor Yellow
    detect-secrets scan | Out-File -FilePath .secrets.baseline -Encoding utf8
}

# Instalace hooků
pre-commit install

Write-Host "✅ Pre-commit hooks installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Hooks will now check for:" -ForegroundColor Cyan
Write-Host "  - Sensitive files (.env, *.log, *.db)"
Write-Host "  - Hardcoded secrets"
Write-Host "  - Code formatting (black, flake8, isort)"
Write-Host ""
Write-Host "To test: pre-commit run --all-files" -ForegroundColor Yellow

