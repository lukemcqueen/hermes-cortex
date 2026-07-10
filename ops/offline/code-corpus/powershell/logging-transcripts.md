---
language: powershell
tags: [pattern, powershell]
title: Logging & Transcripts
description: Start-Transcript, Write-Verbose/Debug/Information/Progress, structured logging, and transcript management.
source: pattern
---

```powershell
# Logging and transcripts in PowerShell

# --- Transcript (full session log) ---
$transcriptPath = "C:\Logs\session-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
Start-Transcript -Path $transcriptPath -Append
Write-Host "Session started at $(Get-Date)"
# ... run commands ...
Stop-Transcript

# --- Write-* stream output ---
Write-Verbose "Detailed verbose message" -Verbose         # -Verbose forces display
Write-Debug "Debug info for troubleshooting" -Debug       # -Debug forces display
Write-Information "Info message" -InformationAction Continue
Write-Warning "This is a warning"
Write-Error "This is a terminating error"

# --- Structured logging function ---
function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Message,

        [ValidateSet('INFO', 'WARN', 'ERROR', 'DEBUG')]
        [string]$Level = 'INFO',

        [string]$Component = 'General',

        [string]$LogFile = "C:\Logs\app.log"
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
    $logEntry = "[$timestamp] [$Level] [$Component] $Message"

    # Console output
    switch ($Level) {
        'ERROR' { Write-Host $logEntry -ForegroundColor Red }
        'WARN'  { Write-Host $logEntry -ForegroundColor Yellow }
        'DEBUG' { Write-Host $logEntry -ForegroundColor Gray }
        default { Write-Host $logEntry -ForegroundColor Green }
    }

    # File output
    Add-Content -Path $LogFile -Value $logEntry
}

# Usage
Write-Log -Message "Deployment started" -Level INFO -Component Deploy
Write-Log -Message "Connection timeout" -Level WARN -Component Network
Write-Log -Message "Fatal exception" -Level ERROR -Component Core -LogFile "C:\Logs\errors.log"

# --- Write-Progress (long operations) ---
1..100 | ForEach-Object {
    Write-Progress -Activity "Processing files" `
        -Status "File $_ of 100" `
        -PercentComplete $_
    Start-Sleep -Milliseconds 50
}

# --- Advanced structured logging (JSON) ---
$logObject = [PSCustomObject]@{
    Timestamp   = (Get-Date -Format 'o')
    Level       = 'INFO'
    Component   = 'API'
    Message     = 'Request received'
    RequestId   = 'req-12345'
    Duration_ms = 42
}
$logObject | ConvertTo-Json -Compress | Add-Content -Path "C:\Logs\structured.log"

```
