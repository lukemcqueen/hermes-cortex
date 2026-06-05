---
language: powershell
tags: [pattern, powershell]
title: Error Handling
description: try/catch/finally, $Error, $?, -ErrorAction, trap, and $LASTEXITCODE for native commands.
source: pattern
---

```powershell
# Error handling in PowerShell

# --- try / catch / finally ---
try {
    Get-Item "C:\nonexistent\file.txt" -ErrorAction Stop
    Write-Host "File found"
}
catch [System.Management.Automation.ItemNotFoundException] {
    Write-Warning "File not found: $_"
}
catch {
    Write-Error "Unexpected error: $_"
}
finally {
    Write-Debug "Cleanup runs regardless of success or failure"
}

# --- ErrorAction parameters ---
Get-Item "bad.txt" -ErrorAction SilentlyContinue   # suppress, no $?
Get-Item "bad.txt" -ErrorAction Stop                # make terminating
Get-Item "bad.txt" -ErrorAction Continue             # default -- print & continue
Get-Item "bad.txt" -ErrorAction Inquire              # prompt on error

# --- $Error automatic variable ---
# $Error is a stack -- most recent first
$Error[0]                    # most recent error
$Error.Count                 # number of errors in session
$Error.Clear()               # clear error list
$ErrorView = "CategoryView"  # compact error display

# --- $? (previous command success) ---
# Boolean: $true if last command succeeded, $false otherwise
if (-not $?) {
    Write-Warning "Last command failed"
}

# --- trap (legacy, scoped) ---
trap {
    Write-Warning "Trapped: $_"
    continue                  # continue execution
    # break                  # stop execution (like throw)
}

# --- $LASTEXITCODE (native commands) ---
git status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git command failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# --- Advanced error handling with -ErrorVariable ---
Get-ChildItem "*.log" -ErrorVariable errs -ErrorAction SilentlyContinue
if ($errs) {
    $errs | ForEach-Object { Write-Warning $_.Exception.Message }
}

```
