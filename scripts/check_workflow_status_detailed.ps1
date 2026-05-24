# Detailní kontrola stavu GitHub Actions workflows
# Používá GitHub API (veřejný přístup)

param(
    [string]$Repository = "toozservis-tech/TOOZHUB2",
    [int]$PerPage = 20
)

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "KONTROLA STAVU GITHUB ACTIONS WORKFLOWS" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Repository: $Repository" -ForegroundColor Yellow
Write-Host ""

$baseUrl = "https://api.github.com/repos/$Repository"

# Získat seznam workflows
Write-Host "Získávání seznamu workflows..." -ForegroundColor Cyan
try {
    $workflowsUrl = "$baseUrl/actions/workflows"
    $workflowsResponse = Invoke-WebRequest -Uri $workflowsUrl -Headers @{"Accept"="application/vnd.github.v3+json"} -UseBasicParsing -ErrorAction SilentlyContinue
    
    if ($workflowsResponse.StatusCode -eq 200) {
        $workflows = ($workflowsResponse.Content | ConvertFrom-Json).workflows
        Write-Host "✅ Nalezeno $($workflows.Count) workflows" -ForegroundColor Green
        Write-Host ""
        
        foreach ($workflow in $workflows) {
            Write-Host "Workflow: $($workflow.name)" -ForegroundColor Yellow
            Write-Host "  ID: $($workflow.id)"
            Write-Host "  State: $($workflow.state)"
            Write-Host ""
        }
    }
} catch {
    Write-Host "⚠️ Nelze získat seznam workflows (možná privátní repo)" -ForegroundColor Yellow
}

# Získat poslední workflow runs
Write-Host "Získávání posledních workflow runs..." -ForegroundColor Cyan
try {
    $runsUrl = "$baseUrl/actions/runs?per_page=$PerPage"
    $runsResponse = Invoke-WebRequest -Uri $runsUrl -Headers @{"Accept"="application/vnd.github.v3+json"} -UseBasicParsing -ErrorAction SilentlyContinue
    
    if ($runsResponse.StatusCode -eq 200) {
        $data = $runsResponse.Content | ConvertFrom-Json
        $runs = $data.workflow_runs
        
        Write-Host "✅ Nalezeno $($runs.Count) workflow runs" -ForegroundColor Green
        Write-Host ""
        
        # Seskupit podle workflow
        $grouped = $runs | Group-Object -Property name
        
        foreach ($group in $grouped) {
            Write-Host ("=" * 70) -ForegroundColor Cyan
            Write-Host "WORKFLOW: $($group.Name)" -ForegroundColor Yellow
            Write-Host ("=" * 70) -ForegroundColor Cyan
            
            $latest = $group.Group | Sort-Object -Property created_at -Descending | Select-Object -First 1
            
            $statusColor = switch ($latest.status) {
                "completed" { if ($latest.conclusion -eq "success") { "Green" } else { "Red" } }
                "in_progress" { "Yellow" }
                "queued" { "Cyan" }
                default { "White" }
            }
            
            $conclusionIcon = switch ($latest.conclusion) {
                "success" { "✅" }
                "failure" { "❌" }
                "cancelled" { "⚠️" }
                "skipped" { "⏭️" }
                default { "⏳" }
            }
            
            Write-Host "Status: $conclusionIcon $($latest.status)" -ForegroundColor $statusColor
            if ($latest.conclusion) {
                Write-Host "Conclusion: $($latest.conclusion)" -ForegroundColor $statusColor
            }
            Write-Host "Created: $($latest.created_at)" -ForegroundColor Gray
            Write-Host "Updated: $($latest.updated_at)" -ForegroundColor Gray
            Write-Host "URL: $($latest.html_url)" -ForegroundColor Cyan
            Write-Host ""
            
            # Zobrazit poslední 3 runs
            Write-Host "Poslední 3 runs:" -ForegroundColor Yellow
            $recent = $group.Group | Sort-Object -Property created_at -Descending | Select-Object -First 3
            foreach ($run in $recent) {
                $icon = switch ($run.conclusion) {
                    "success" { "✅" }
                    "failure" { "❌" }
                    "cancelled" { "⚠️" }
                    default { "⏳" }
                }
                Write-Host "  $icon $($run.status) - $($run.created_at)" -ForegroundColor White
            }
            Write-Host ""
        }
        
        # Shrnutí
        Write-Host ("=" * 70) -ForegroundColor Cyan
        Write-Host "SHRNUTÍ" -ForegroundColor Green
        Write-Host ("=" * 70) -ForegroundColor Cyan
        
        $successCount = ($runs | Where-Object { $_.conclusion -eq "success" }).Count
        $failureCount = ($runs | Where-Object { $_.conclusion -eq "failure" }).Count
        $inProgressCount = ($runs | Where-Object { $_.status -eq "in_progress" }).Count
        $queuedCount = ($runs | Where-Object { $_.status -eq "queued" }).Count
        
        Write-Host "✅ Úspěšné: $successCount" -ForegroundColor Green
        Write-Host "❌ Selhané: $failureCount" -ForegroundColor Red
        Write-Host "⏳ Běží: $inProgressCount" -ForegroundColor Yellow
        Write-Host "📋 Ve frontě: $queuedCount" -ForegroundColor Cyan
        Write-Host ""
        
        if ($failureCount -gt 0) {
            Write-Host "⚠️ POZOR: Nalezeny selhané workflow runs!" -ForegroundColor Red
            Write-Host "Zkontrolujte logy na: https://github.com/$Repository/actions" -ForegroundColor Cyan
        } elseif ($inProgressCount -gt 0) {
            Write-Host "⏳ Některé testy stále běží..." -ForegroundColor Yellow
        } else {
            Write-Host "✅ Všechny testy jsou dokončené!" -ForegroundColor Green
        }
        
    } else {
        Write-Host "❌ Nelze získat workflow runs (Status: $($runsResponse.StatusCode))" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Chyba při získávání dat z GitHub API:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Možné důvody:" -ForegroundColor Yellow
    Write-Host "  - Repository je privátní a vyžaduje autentizaci" -ForegroundColor White
    Write-Host "  - GitHub API má rate limit" -ForegroundColor White
    Write-Host "  - Problém s připojením" -ForegroundColor White
    Write-Host ""
    Write-Host "Zkontrolujte manuálně na: https://github.com/$Repository/actions" -ForegroundColor Cyan
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan

