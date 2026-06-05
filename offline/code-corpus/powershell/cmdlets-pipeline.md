---
language: powershell
tags: [pattern, powershell]
title: Cmdlets & Pipeline
description: Get-Command, Get-Help, Where-Object, Select-Object, ForEach-Object, and pipeline object binding.
source: pattern
---

```powershell
# Cmdlets and the PowerShell pipeline

# --- Discover cmdlets ---
Get-Command -Verb Get          # all cmdlets that 'Get' something
Get-Command -Noun Process      # all *-Process cmdlets
Get-Command -Module ActiveDirectory

# --- Get help ---
Get-Help Get-Process
Get-Help Get-Process -Examples
Get-Help about_Pipelines       # conceptual help

# --- Pipeline basics ---
# Objects flow through the pipeline, not text
Get-Process |
    Where-Object { $_.WorkingSet64 -gt 100MB } |
    Select-Object Name, Id, @{Name='MemMB';Expression={[math]::Round($_.WorkingSet64/1MB,2)}} |
    Sort-Object MemMB -Descending |
    Format-Table -AutoSize

# --- ForEach-Object ---
Get-Service |
    ForEach-Object {
        [PSCustomObject]@{
            ServiceName = $_.Name
            Status      = $_.Status
            StartType   = $_.StartType
        }
    }

# --- Pipeline bound parameters ---
# Cmdlets that accept pipeline input by value or by property name
Get-Process | Stop-Process -WhatIf   # pipe process objects directly
Get-Content servers.txt | Test-Connection -Count 1

# --- Custom pipeline function ---
function Add-Numbers {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromPipeline)]
        [int[]]$Number
    )
    begin { $sum = 0 }
    process { $sum += $_ }
    end { $sum }
}
1..10 | Add-Numbers  # returns 55

```
