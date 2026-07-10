---
language: powershell
tags: [pattern, powershell]
title: Remoting & CIM
description: Invoke-Command, Enter-PSSession, New-PSSession, Get-CimInstance, and WinRM configuration.
source: pattern
---

```powershell
# PowerShell remoting and CIM/WMI

# --- One-off remote command ---
Invoke-Command -ComputerName SRV-APP01 -ScriptBlock {
    Get-Service | Where-Object Status -eq 'Running'
}

# --- Persistent session (PSSession) ---
$session = New-PSSession -ComputerName SRV-DB01, SRV-DB02 -Credential (Get-Credential)

# Run commands in both sessions
Invoke-Command -Session $session -ScriptBlock {
    Get-ChildItem D:\Databases
}

# Copy files to/from remote sessions
Copy-Item .\deploy.ps1 -Destination C:\Scripts\ -ToSession $session[0]
Copy-Item C:\Logs\app.log -Destination .\logs\ -FromSession $session[0]

# Remove session
Remove-PSSession $session

# --- Enter interactive session ---
# Enter-PSSession SRV-WEB01
# [SRV-WEB01]: PS C:\> Get-Service
# Exit-PSSession

# --- CIM (modern WMI) ---
Get-CimInstance -ClassName Win32_OperatingSystem
Get-CimInstance -ClassName Win32_ComputerSystem
Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3"

# CIM session (reusable)
$cim = New-CimSession -ComputerName SRV-APP01
Get-CimInstance -CimSession $cim -ClassName Win32_Process |
    Where-Object { $_.WorkingSetSize -gt 100MB }
Remove-CimSession $cim

# --- WinRM configuration ---
# Enable PSRemoting (admin prompt)
# Enable-PSRemoting -Force

# Trusted hosts (for workgroup)
# Set-Item WSMan:\localhost\Client\TrustedHosts -Value "*.contoso.com" -Force

# Test connectivity
Test-WSMan SRV-APP01
Test-Connection SRV-APP01

# --- Fan-out pattern ---
$computers = Get-Content .\servers.txt
$jobs = $computers | ForEach-Object {
    Invoke-Command -ComputerName $_ -ScriptBlock {
        Get-WinEvent -LogName System -MaxEvents 100
    } -AsJob
}
$jobs | Receive-Job -Wait | Select-Object -First 50

```
