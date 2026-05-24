# PowerShell script for GitHub repository setup
# This script helps set up GitHub repository and push the project

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GITHUB REPOSITORY SETUP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if project is a git repository
if (-not (Test-Path .git)) {
    Write-Host "ERROR: This directory is not a git repository!" -ForegroundColor Red
    Write-Host "Run first: git init" -ForegroundColor Yellow
    exit 1
}

# Check git remote
$remote = git remote get-url origin 2>$null
if ($remote) {
    Write-Host "OK: Git remote is already set:" -ForegroundColor Green
    Write-Host "   $remote" -ForegroundColor Gray
    Write-Host ""
    $continue = Read-Host "Continue with push? (Y/N)"
    if ($continue -ne 'Y' -and $continue -ne 'y') {
        exit 0
    }
} else {
    Write-Host "INFO: Git remote is not set" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Steps:" -ForegroundColor Cyan
    Write-Host "1. Create new repository on GitHub:" -ForegroundColor White
    Write-Host "   - Go to: https://github.com/new" -ForegroundColor Gray
    Write-Host "   - Name: TOOZHUB2" -ForegroundColor Gray
    Write-Host "   - Choose: Private or Public" -ForegroundColor Gray
    Write-Host "   - DO NOT create README, .gitignore or license (you already have them)" -ForegroundColor Yellow
    Write-Host "   - Click 'Create repository'" -ForegroundColor Gray
    Write-Host ""
    
    $repoUrl = Read-Host "2. Enter URL of new repository (e.g. https://github.com/username/TOOZHUB2.git)"
    
    if ($repoUrl) {
        Write-Host ""
        Write-Host "Setting git remote..." -ForegroundColor Yellow
        git remote add origin $repoUrl
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: Git remote set!" -ForegroundColor Green
        } else {
            Write-Host "ERROR: Failed to set remote" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "ERROR: URL not provided. Exiting." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PREPARING TO PUSH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check for changes
$status = git status --short
if ($status) {
    Write-Host "Found changes:" -ForegroundColor Yellow
    Write-Host $status -ForegroundColor Gray
    Write-Host ""
    
    $commit = Read-Host "Commit all changes? (Y/N)"
    if ($commit -eq 'Y' -or $commit -eq 'y') {
        Write-Host ""
        Write-Host "Adding all files..." -ForegroundColor Yellow
        git add .
        
        $commitMsg = Read-Host "Enter commit message (or Enter for default)"
        if (-not $commitMsg) {
            $commitMsg = "Initial commit: Add TooZHub2 project with CI/CD workflows"
        }
        
        Write-Host "Committing changes..." -ForegroundColor Yellow
        git commit -m $commitMsg
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to commit" -ForegroundColor Red
            exit 1
        }
        Write-Host "OK: Changes committed!" -ForegroundColor Green
    }
} else {
    Write-Host "OK: No changes to commit" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PUSHING TO GITHUB" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get current branch
$branch = git branch --show-current
Write-Host "Current branch: $branch" -ForegroundColor Gray
Write-Host ""

$push = Read-Host "Push to GitHub? (Y/N)"
if ($push -eq 'Y' -or $push -eq 'y') {
    Write-Host ""
    Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
    
    # First push - set upstream
    git push -u origin $branch
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "OK: Project successfully pushed to GitHub!" -ForegroundColor Green
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  NEXT STEPS" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "1. Set GitHub Secrets for Production Smoke Tests:" -ForegroundColor Yellow
        Write-Host "   - Go to: https://github.com/[YOUR-ORG]/TOOZHUB2/settings/secrets/actions" -ForegroundColor Gray
        Write-Host "   - Add: PROD_E2E_EMAIL and PROD_E2E_PASSWORD" -ForegroundColor Gray
        Write-Host ""
        Write-Host "2. Workflow will run automatically on push to main" -ForegroundColor Gray
        Write-Host "   Or manually: Actions -> Production Smoke Tests -> Run workflow" -ForegroundColor Gray
        Write-Host ""
        Write-Host "More info: docs/GITHUB_SECRETS_SETUP.md" -ForegroundColor Gray
    } else {
        Write-Host ""
        Write-Host "ERROR: Failed to push" -ForegroundColor Red
        Write-Host "Possible causes:" -ForegroundColor Yellow
        Write-Host "- Not logged in to git (git config --global user.name/email)" -ForegroundColor Gray
        Write-Host "- No permission to repository" -ForegroundColor Gray
        Write-Host "- Repository already has commits (try: git pull --rebase origin $branch)" -ForegroundColor Gray
    }
} else {
    Write-Host "Push skipped. You can run it later:" -ForegroundColor Yellow
    Write-Host "  git push -u origin $branch" -ForegroundColor Gray
}
