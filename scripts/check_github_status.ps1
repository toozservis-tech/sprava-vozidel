# Skript pro kontrolu stavu GitHub Actions workflows
# Používá GitHub API pro získání informací o běžících workflow runs

param(
    [string]$Repository = "toozservis-tech/TOOZHUB2",
    [int]$PerPage = 10
)

Write-Host "Kontrola stavu GitHub Actions workflows..." -ForegroundColor Green
Write-Host "Repository: $Repository" -ForegroundColor Cyan
Write-Host ""

try {
    $url = "https://api.github.com/repos/$Repository/actions/runs?per_page=$PerPage"
    $headers = @{
        "Accept" = "application/vnd.github.v3+json"
    }
    
    $response = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing
    $data = $response.Content | ConvertFrom-Json
    
    $runs = $data.workflow_runs
    
    Write-Host "Poslední workflow runs:" -ForegroundColor Yellow
    Write-Host ""
    
    foreach ($run in $runs) {
        $statusColor = switch ($run.status) {
            "completed" { if ($run.conclusion -eq "success") { "Green" } else { "Red" } }
            "in_progress" { "Yellow" }
            "queued" { "Cyan" }
            default { "White" }
        }
        
        $conclusionIcon = switch ($run.conclusion) {
            "success" { "✅" }
            "failure" { "❌" }
            "cancelled" { "⚠️" }
            default { "⏳" }
        }
        
        Write-Host "$conclusionIcon $($run.name)" -ForegroundColor $statusColor -NoNewline
        Write-Host " - Status: $($run.status)" -ForegroundColor White -NoNewline
        if ($run.conclusion) {
            Write-Host " - Conclusion: $($run.conclusion)" -ForegroundColor White
        } else {
            Write-Host ""
        }
        Write-Host "   Created: $($run.created_at)" -ForegroundColor Gray
        Write-Host "   URL: $($run.html_url)" -ForegroundColor Gray
        Write-Host ""
    }
    
    # Shrnutí
    $successCount = ($runs | Where-Object { $_.conclusion -eq "success" }).Count
    $failureCount = ($runs | Where-Object { $_.conclusion -eq "failure" }).Count
    $inProgressCount = ($runs | Where-Object { $_.status -eq "in_progress" }).Count
    
    Write-Host "Shrnutí:" -ForegroundColor Yellow
    Write-Host "  ✅ Úspěšné: $successCount" -ForegroundColor Green
    Write-Host "  ❌ Selhané: $failureCount" -ForegroundColor Red
    Write-Host "  ⏳ Běží: $inProgressCount" -ForegroundColor Yellow
    Write-Host ""
    
    if ($failureCount -gt 0) {
        Write-Host "⚠️ Nalezeny selhané workflow runs!" -ForegroundColor Red
        Write-Host "Zkontrolujte logy na: https://github.com/$Repository/actions" -ForegroundColor Cyan
    } else {
        Write-Host "✅ Všechny workflow runs jsou úspěšné nebo stále běží!" -ForegroundColor Green
    }
    
} catch {
    Write-Host "❌ Chyba při získávání dat z GitHub API:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Zkontrolujte manuálně na: https://github.com/$Repository/actions" -ForegroundColor Cyan
}

