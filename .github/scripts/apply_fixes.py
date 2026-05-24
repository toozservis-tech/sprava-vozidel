#!/usr/bin/env python3
"""
Apply automatic fixes based on error analysis.
"""
import os
import sys
import json
import re
from pathlib import Path

ERROR_ANALYSIS = os.getenv("ERROR_ANALYSIS", "[]")

def fix_selector_errors(analysis: dict) -> bool:
    """Fix selector/UI test errors by updating test files."""
    error_msg = analysis.get("error_message", "")
    files_fixed = []
    
    # Find test files that might need fixing
    test_files = list(Path("tests/e2e").glob("*.spec.ts"))
    
    # Look for missing data-testid references
    if "data-testid" in error_msg.lower():
        # Extract the missing selector from error
        match = re.search(r"data-testid=['\"]([^'\"]+)['\"]", error_msg)
        if match:
            missing_id = match.group(1)
            print(f"Found missing data-testid: {missing_id}")
            
            # Try to find and fix in HTML files
            html_files = list(Path("web").glob("*.html"))
            for html_file in html_files:
                content = html_file.read_text(encoding="utf-8")
                # This is a placeholder - actual fix would need more context
                # For now, we'll just log it
                print(f"Would check {html_file} for missing {missing_id}")
    
    return len(files_fixed) > 0

def fix_import_errors(analysis: dict) -> bool:
    """Fix import errors in Python files."""
    error_msg = analysis.get("error_message", "")
    files_fixed = []
    
    # Extract module name from error
    match = re.search(r"cannot import name ['\"]([^'\"]+)['\"]", error_msg, re.IGNORECASE)
    if match:
        missing_import = match.group(1)
        print(f"Found missing import: {missing_import}")
        
        # Try to find files that might need this import
        # This is a simplified version - real fix would need more analysis
        print(f"Would add import for {missing_import}")
    
    return len(files_fixed) > 0

def fix_syntax_errors(analysis: dict) -> bool:
    """Fix syntax errors in code files."""
    error_msg = analysis.get("error_message", "")
    
    # Extract file and line from error
    match = re.search(r"File ['\"]([^'\"]+)['\"], line (\d+)", error_msg)
    if match:
        file_path = match.group(1)
        line_num = int(match.group(2))
        
        print(f"Found syntax error in {file_path} at line {line_num}")
        
        # Try to read and fix the file
        if Path(file_path).exists():
            content = Path(file_path).read_text(encoding="utf-8")
            lines = content.split("\n")
            
            if line_num <= len(lines):
                problem_line = lines[line_num - 1]
                print(f"Problem line: {problem_line}")
                
                # Common syntax fixes
                # Missing closing bracket
                if problem_line.count("(") > problem_line.count(")"):
                    lines[line_num - 1] = problem_line + ")"
                    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
                    print(f"Fixed: Added missing closing parenthesis")
                    return True
                
                # Missing closing brace
                if problem_line.count("{") > problem_line.count("}"):
                    lines[line_num - 1] = problem_line + "}"
                    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
                    print(f"Fixed: Added missing closing brace")
                    return True
    
    return False

def main():
    """Main fix application function."""
    try:
        errors = json.loads(ERROR_ANALYSIS)
    except json.JSONDecodeError:
        print("ERROR: Invalid ERROR_ANALYSIS JSON")
        sys.exit(1)
    
    if not errors:
        print("No errors to fix")
        return
    
    fixes_applied = False
    
    for error in errors:
        analysis = error.get("analysis", {})
        error_type = analysis.get("error_type")
        
        if not analysis.get("can_auto_fix"):
            print(f"Skipping {error_type} - cannot auto-fix")
            continue
        
        print(f"Attempting to fix {error_type}...")
        
        if error_type == "selector_not_found":
            fixes_applied = fix_selector_errors(analysis) or fixes_applied
        elif error_type == "import_error":
            fixes_applied = fix_import_errors(analysis) or fixes_applied
        elif error_type == "syntax_error":
            fixes_applied = fix_syntax_errors(analysis) or fixes_applied
        elif error_type == "test_failure":
            # Test failures might need code fixes - skip for now
            print(f"Test failure detected - requires manual review")
    
    if fixes_applied:
        print("Fixes applied successfully")
        sys.exit(0)
    else:
        print("No automatic fixes could be applied")
        sys.exit(1)

if __name__ == "__main__":
    main()

