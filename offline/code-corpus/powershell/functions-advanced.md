---
language: powershell
tags: [pattern, powershell]
title: Functions & Advanced Functions
description: function, param, [Parameter()], [CmdletBinding()], begin/process/end blocks.
source: pattern
---

```powershell
# PowerShell functions and advanced functions

# --- Simple function ---
function Get-Greeting {
    param($Name)
    "Hello, $Name!"
}
Get-Greeting "Alice"

# --- Advanced function (cmdlet-like) ---
function Get-ProcessReport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false, Position = 0)]
        [string[]]$Name,

        [Parameter(ValueFromPipeline = $true)]
        [System.Diagnostics.Process]$InputObject,

        [ValidateSet("CPU", "Memory", "Disk")]
        [string]$SortBy = "CPU",

        [switch]$IncludeIdle
    )

    begin {
        Write-Verbose "Starting process report..."
        $results = [System.Collections.ArrayList]::new()
    }

    process {
        if ($InputObject) {
            $procs = @($InputObject)
        } elseif ($Name) {
            $procs = Get-Process -Name $Name -ErrorAction SilentlyContinue
        } else {
            $procs = Get-Process
        }

        foreach ($p in $procs) {
            if (-not $IncludeIdle -and $p.Id -eq 0) { continue }
            $null = $results.Add([PSCustomObject]@{
                ProcessName = $p.ProcessName
                Id          = $p.Id
                CPU_s       = [math]::Round($p.TotalProcessorTime.TotalSeconds, 2)
                MemMB       = [math]::Round($p.WorkingSet64 / 1MB, 2)
                StartTime   = $p.StartTime
            })
        }
    }

    end {
        switch ($SortBy) {
            "CPU"    { $results = $results | Sort-Object CPU_s -Descending }
            "Memory" { $results = $results | Sort-Object MemMB -Descending }
        }
        Write-Output $results
    }
}

# --- Usage ---
# Get-ProcessReport -Name "powershell*" -SortBy Memory -Verbose
# Get-Process | Get-ProcessReport -SortBy CPU
# Get-ProcessReport -IncludeIdle

```
