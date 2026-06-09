---
language: powershell
tags: [pattern, powershell]
title: WMI & System Management
description: Get-WmiObject, Win32_* classes, Get-Process, Get-Service, Stop-Service, Get-EventLog, and system inventory.
source: pattern
---

```powershell
# WMI and system management

# --- WMI basics (Get-WmiObject) ---
# Note: Get-WmiObject is legacy; prefer Get-CimInstance where possible

# System information
Get-WmiObject Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber, OSArchitecture, TotalVisibleMemorySize

Get-WmiObject Win32_ComputerSystem |
    Select-Object Manufacturer, Model, TotalPhysicalMemory, NumberOfProcessors

Get-WmiObject Win32_Processor |
    Select-Object Name, NumberOfCores, MaxClockSpeed, L2CacheSize, L3CacheSize

# Disk and storage
Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" |
    Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}},
        @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,2)}},
        @{N='PctFree';E={[math]::Round(($_.FreeSpace/$_.Size)*100,1)}}

# Network adapters
Get-WmiObject Win32_NetworkAdapterConfiguration |
    Where-Object { $_.IPEnabled -eq $true } |
    Select-Object Description, IPAddress, MACAddress, DefaultIPGateway, DNSServerSearchOrder

# --- Process management ---
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
Get-Process -Name "notepad" | Stop-Process -Force
Get-Process -Id $pid   # current PowerShell process

# --- Service management ---
Get-Service | Where-Object Status -eq 'Running'
Get-Service -Name "Spooler", "W3SVC"
Stop-Service -Name "Spooler" -Force
Set-Service -Name "W3SVC" -StartupType Automatic
Start-Service -Name "W3SVC"

# --- Event Log ---
Get-EventLog -LogName System -Newest 50 |
    Where-Object { $_.EntryType -eq 'Error' } |
    Select-Object TimeGenerated, Source, Message

# With WinRM:
# Get-WmiObject Win32_NTLogEvent -Filter "LogFile='System' AND Type='Error'" |
#     Select-Object -First 10 TimeGenerated, SourceName, Message

# --- Hardware inventory function ---
function Get-SystemInventory {
    [CmdletBinding()]
    param([string[]]$ComputerName = @($env:COMPUTERNAME))

    foreach ($comp in $ComputerName) {
        try {
            $os = Get-WmiObject Win32_OperatingSystem -ComputerName $comp
            $cs = Get-WmiObject Win32_ComputerSystem -ComputerName $comp
            $disk = Get-WmiObject Win32_LogicalDisk -ComputerName $comp -Filter "DriveType=3"

            [PSCustomObject]@{
                Computer     = $comp
                OS           = $os.Caption
                OSVersion    = $os.Version
                Manufacturer = $cs.Manufacturer
                Model        = $cs.Model
                RAM_GB       = [math]::Round($cs.TotalPhysicalMemory/1GB, 2)
                CPU          = $cs.NumberOfProcessors
                Disks        = ($disk | ForEach-Object {
                    "$($_.DeviceID) $([math]::Round($_.Size/1GB,0))GB"
                }) -join '; '
                LastBoot     = $os.LastBootUpTime
            }
        } catch {
            Write-Warning "Failed to query $comp : $_"
        }
    }
}

```
