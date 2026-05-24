#!/usr/bin/env python3
"""
Analyze failed GitHub Actions workflow runs and determine if they can be auto-fixed.
"""
import os
import sys
import json
import requests
from typing import Dict, List, Optional

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Výchozí hodnota odpovídá aktuálnímu GitHub repozitáři (slug může být přejmenován – viz TECHNICAL_RENAME_BACKLOG.md).
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "toozservis-tech/sprava-vozidel")
WORKFLOW_RUN_ID = os.getenv("WORKFLOW_RUN_ID")

def get_failed_workflow_runs() -> List[Dict]:
    """Get recent failed workflow runs."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    params = {
        "status": "failure",
        "per_page": 5
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json().get("workflow_runs", [])

def get_workflow_run_logs(run_id: int) -> str:
    """Download workflow run logs."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}/logs"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    return ""

def get_workflow_run_jobs(run_id: int) -> List[Dict]:
    """Get jobs for a workflow run."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}/jobs"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("jobs", [])

def analyze_error(logs: str, job_name: str) -> Dict:
    """Analyze error logs and determine if it can be auto-fixed."""
    error_analysis = {
        "has_errors": False,
        "can_auto_fix": False,
        "error_type": None,
        "error_message": None,
        "suggested_fix": None,
        "files_to_fix": []
    }
    
    if not logs:
        return error_analysis
    
    logs_lower = logs.lower()
    
    # Common error patterns
    error_patterns = {
        "login_failed": {
            "patterns": ["login failed", "authentication failed", "401", "unauthorized"],
            "can_fix": False,
            "fix": "Check GitHub Secrets (PROD_E2E_EMAIL, PROD_E2E_PASSWORD)"
        },
        "connection_refused": {
            "patterns": ["connection refused", "err_connection_refused", "econnrefused"],
            "can_fix": False,
            "fix": "Server is down - requires manual intervention"
        },
        "selector_not_found": {
            "patterns": ["locator", "data-testid", "not found", "timeout"],
            "can_fix": True,
            "fix": "Update test selectors or add missing data-testid attributes"
        },
        "import_error": {
            "patterns": ["import error", "module not found", "cannot import"],
            "can_fix": True,
            "fix": "Fix import statements or add missing dependencies"
        },
        "syntax_error": {
            "patterns": ["syntax error", "unexpected token", "parse error"],
            "can_fix": True,
            "fix": "Fix syntax errors in code"
        },
        "test_failure": {
            "patterns": ["test failed", "assertion error", "expect", "to be"],
            "can_fix": True,
            "fix": "Update test expectations or fix application code"
        }
    }
    
    for error_type, error_info in error_patterns.items():
        for pattern in error_info["patterns"]:
            if pattern in logs_lower:
                error_analysis["has_errors"] = True
                error_analysis["error_type"] = error_type
                error_analysis["can_auto_fix"] = error_info["can_fix"]
                error_analysis["suggested_fix"] = error_info["fix"]
                
                # Extract error message (last 500 chars of relevant section)
                error_section = logs[logs_lower.find(pattern):logs_lower.find(pattern)+500]
                error_analysis["error_message"] = error_section[:500]
                break
        
        if error_analysis["has_errors"]:
            break
    
    return error_analysis

def main():
    """Main analysis function."""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)
    
    # Get workflow run ID from environment or find latest failed run
    run_id = None
    if WORKFLOW_RUN_ID:
        try:
            run_id = int(WORKFLOW_RUN_ID)
        except ValueError:
            print(f"WARNING: Invalid WORKFLOW_RUN_ID: {WORKFLOW_RUN_ID}")
            run_id = None
    
    # If no run_id from env, find latest failed run
    if not run_id:
        failed_runs = get_failed_workflow_runs()
        if not failed_runs:
            print("No failed workflow runs found")
            sys.exit(0)
        run_id = failed_runs[0]["id"]
    
    print(f"Analyzing workflow run {run_id}...")
    
    # Get jobs and logs
    jobs = get_workflow_run_jobs(run_id)
    all_errors = []
    
    for job in jobs:
        if job["conclusion"] == "failure":
            job_name = job["name"]
            print(f"Analyzing failed job: {job_name}")
            
            # Get logs for this job
            logs = get_workflow_run_logs(run_id)
            
            # Analyze errors
            analysis = analyze_error(logs, job_name)
            if analysis["has_errors"]:
                all_errors.append({
                    "job": job_name,
                    "analysis": analysis
                })
    
    # Output results
    if all_errors:
        error_summary = []
        can_auto_fix = any(e["analysis"]["can_auto_fix"] for e in all_errors)
        
        for error in all_errors:
            summary = f"{error['job']}: {error['analysis']['error_type']} - {error['analysis']['suggested_fix']}"
            error_summary.append(summary)
        
        # Output to GITHUB_OUTPUT (GitHub Actions v2)
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a") as f:
                f.write(f"has_errors=true\n")
                f.write(f"can_auto_fix={str(can_auto_fix).lower()}\n")
                f.write(f"error_analysis={json.dumps(all_errors)}\n")
                f.write(f"fix_summary={error_summary[0] if error_summary else 'Unknown error'}\n")
        else:
            # Fallback for older GitHub Actions
            print(f"::set-output name=has_errors::true")
            print(f"::set-output name=can_auto_fix::{str(can_auto_fix).lower()}")
            print(f"::set-output name=error_analysis::{json.dumps(all_errors)}")
            print(f"::set-output name=fix_summary::{error_summary[0] if error_summary else 'Unknown error'}")
    else:
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a") as f:
                f.write("has_errors=false\n")
                f.write("can_auto_fix=false\n")
        else:
            print("::set-output name=has_errors::false")
            print("::set-output name=can_auto_fix::false")

if __name__ == "__main__":
    main()

