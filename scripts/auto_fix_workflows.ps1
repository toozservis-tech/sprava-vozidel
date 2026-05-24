# PowerShell script to automatically monitor and fix GitHub Actions workflow failures
# This script uses GitHub API to check for failed runs and attempts to fix them

param(
    [string]$GitHubToken = $env:GITHUB_TOKEN,
    [string]$Repository = "toozservis-tech/TOOZHUB2",
    [int]$CheckInterval = 300,  # 5 minutes
    [switch]$RunOnce = $false
)

if (-not $GitHubToken) {
    Write-Host "ERROR: GITHUB_TOKEN not set!" -ForegroundColor Red
    Write-Host "Set it with: `$env:GITHUB_TOKEN = 'your-token'" -ForegroundColor Yellow
    Write-Host "Or pass it as parameter: -GitHubToken 'your-token'" -ForegroundColor Yellow
    exit 1
}

function Get-FailedWorkflowRuns {
    param([string]$Token, [string]$Repo)
    
    $headers = @{
        "Authorization" = "token $Token"
        "Accept" = "application/vnd.github.v3+json"
    }
    
    $url = "https://api.github.com/repos/$Repo/actions/runs?status=failure&per_page=5"
    
    try {
        $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Get
        return $response.workflow_runs
    } catch {
        Write-Host "ERROR: Failed to get workflow runs: $_" -ForegroundColor Red
        return @()
    }
}

function Get-WorkflowRunLogs {
    param([string]$Token, [string]$Repo, [int]$RunId)
    
    $headers = @{
        "Authorization" = "token $Token"
        "Accept" = "application/vnd.github.v3+json"
    }
    
    $url = "https://api.github.com/repos/$Repo/actions/runs/$RunId/logs"
    
    try {
        $response = Invoke-WebRequest -Uri $url -Headers $headers -Method Get
        return $response.Content
    } catch {
        Write-Host "WARNING: Could not get logs for run $RunId" -ForegroundColor Yellow
        return ""
    }
}

function Analyze-Error {
    param([string]$Logs, [string]$JobName)
    
    $logsLower = $Logs.ToLower()
    $analysis = @{
        HasErrors = $false
        CanAutoFix = $false
        ErrorType = $null
        ErrorMessage = $null
        SuggestedFix = $null
        FilesToFix = @()
    }
    
    # Common error patterns
    $errorPatterns = @{
        "login_failed" = @{
            Patterns = @("login failed", "authentication failed", "401", "unauthorized")
            CanFix = $false
            Fix = "Check GitHub Secrets (PROD_E2E_EMAIL, PROD_E2E_PASSWORD)"
        }
        "connection_refused" = @{
            Patterns = @("connection refused", "err_connection_refused", "econnrefused")
            CanFix = $false
            Fix = "Server is down - requires manual intervention"
        }
        "selector_not_found" = @{
            Patterns = @("locator", "data-testid", "not found", "timeout")
            CanFix = $true
            Fix = "Update test selectors or add missing data-testid attributes"
        }
        "import_error" = @{
            Patterns = @("import error", "module not found", "cannot import")
            CanFix = $true
            Fix = "Fix import statements or add missing dependencies"
        }
        "syntax_error" = @{
            Patterns = @("syntax error", "unexpected token", "parse error")
            CanFix = $true
            Fix = "Fix syntax errors in code"
        }
        "test_failure" = @{
            Patterns = @("test failed", "assertion error", "expect", "to be")
            CanFix = $true
            Fix = "Update test expectations or fix application code"
        }
    }
    
    foreach ($errorType in $errorPatterns.Keys) {
        $errorInfo = $errorPatterns[$errorType]
        foreach ($pattern in $errorInfo.Patterns) {
            if ($logsLower -match $pattern) {
                $analysis.HasErrors = $true
                $analysis.ErrorType = $errorType
                $analysis.CanAutoFix = $errorInfo.CanFix
                $analysis.SuggestedFix = $errorInfo.Fix
                
                # Extract error message
                $matchIndex = $logsLower.IndexOf($pattern)
                if ($matchIndex -ge 0) {
                    $errorSection = $Logs.Substring($matchIndex, [Math]::Min(500, $Logs.Length - $matchIndex))
                    $analysis.ErrorMessage = $errorSection
                }
                break
            }
        }
        if ($analysis.HasErrors) { break }
    }
    
    return $analysis
}

function Apply-Fix {
    param([hashtable]$Analysis)
    
    Write-Host "Attempting to apply fix for: $($Analysis.ErrorType)" -ForegroundColor Yellow
    
    switch ($Analysis.ErrorType) {
        "selector_not_found" {
            Write-Host "Fix: $($Analysis.SuggestedFix)" -ForegroundColor Cyan
            # TODO: Implement actual fix logic
            # This would involve:
            # 1. Finding the missing selector in test files
            # 2. Adding it to HTML files
            # 3. Or updating test files to use correct selector
            return $false
        }
        "import_error" {
            Write-Host "Fix: $($Analysis.SuggestedFix)" -ForegroundColor Cyan
            # TODO: Implement actual fix logic
            return $false
        }
        "syntax_error" {
            Write-Host "Fix: $($Analysis.SuggestedFix)" -ForegroundColor Cyan
            # TODO: Implement actual fix logic
            return $false
        }
        default {
            Write-Host "Cannot auto-fix this error type" -ForegroundColor Red
            return $false
        }
    }
}

function Main {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  AUTO-FIX WORKFLOW MONITOR" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Repository: $Repository" -ForegroundColor Gray
    Write-Host "Check interval: $CheckInterval seconds" -ForegroundColor Gray
    Write-Host ""
    
    $processedRuns = @()
    
    do {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Checking for failed workflow runs..." -ForegroundColor Yellow
        
        $failedRuns = Get-FailedWorkflowRuns -Token $GitHubToken -Repo $Repository
        
        if ($failedRuns.Count -eq 0) {
            Write-Host "  No failed runs found" -ForegroundColor Green
        } else {
            foreach ($run in $failedRuns) {
                $runId = $run.id
                
                # Skip if already processed
                if ($processedRuns -contains $runId) {
                    continue
                }
                
                Write-Host "  Found failed run: $runId ($($run.name))" -ForegroundColor Red
                
                # Get logs
                $logs = Get-WorkflowRunLogs -Token $GitHubToken -Repo $Repository -RunId $runId
                
                if ($logs) {
                    # Analyze error
                    $analysis = Analyze-Error -Logs $logs -JobName $run.name
                    
                    if ($analysis.HasErrors) {
                        Write-Host "    Error Type: $($analysis.ErrorType)" -ForegroundColor Yellow
                        Write-Host "    Can Auto-Fix: $($analysis.CanAutoFix)" -ForegroundColor $(if ($analysis.CanAutoFix) { "Green" } else { "Red" })
                        Write-Host "    Suggested Fix: $($analysis.SuggestedFix)" -ForegroundColor Cyan
                        
                        if ($analysis.CanAutoFix) {
                            Write-Host "    Attempting to apply fix..." -ForegroundColor Yellow
                            $fixApplied = Apply-Fix -Analysis $analysis
                            
                            if ($fixApplied) {
                                Write-Host "    Fix applied! Committing changes..." -ForegroundColor Green
                                # TODO: Commit and push fixes
                                # git add .
                                # git commit -m "Auto-fix: $($analysis.SuggestedFix)"
                                # git push origin master
                            } else {
                                Write-Host "    Could not automatically apply fix" -ForegroundColor Red
                            }
                        } else {
                            Write-Host "    Manual intervention required" -ForegroundColor Red
                        }
                    }
                }
                
                $processedRuns += $runId
            }
        }
        
        if (-not $RunOnce) {
            Write-Host ""
            Write-Host "Waiting $CheckInterval seconds until next check..." -ForegroundColor Gray
            Start-Sleep -Seconds $CheckInterval
        }
        
    } while (-not $RunOnce)
    
    Write-Host ""
    Write-Host "Monitoring stopped" -ForegroundColor Cyan
}

Main

