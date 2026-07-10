---
language: powershell
tags: [pattern, powershell]
title: Filesystem & Registry
description: Get-ChildItem, Set-Location, Get-Content, Set-Content, Copy/Move/Remove-Item, and registry as a PSDrive.
source: pattern
---

```powershell
# Filesystem and Registry operations

# --- Navigation ---
Set-Location C:\Projects
Get-Location
Push-Location C:\Windows\System32
Pop-Location

# --- List contents ---
Get-ChildItem                     # ls equivalent
Get-ChildItem -Recurse -Filter *.ps1
Get-ChildItem -Directory          # directories only
Get-ChildItem -File               # files only
Get-ChildItem -Hidden             # hidden items

# --- File content ---
Get-Content .\log.txt             # read file
Get-Content .\log.txt -Tail 50    # last 50 lines (tail -f with -Wait)
Set-Content .\output.txt -Value "Hello, World!"
Add-Content .\log.txt -Value "New log entry"

# --- Copy / Move / Remove ---
Copy-Item .\source.txt .\dest.txt -Force
Move-Item .\old.txt .\new.txt
Remove-Item .\temp.txt -Confirm

# New-Item (creates files and directories)
New-Item -ItemType Directory -Path .\scripts -Force
New-Item -ItemType File -Path .\scripts\deploy.ps1 -Force

# --- Registry as a PSDrive ---
# Registry drives: HKLM:, HKCU:
Set-Location HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion

Get-ChildItem                        # list registry keys
Get-ItemProperty .                    # get values of current key
Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -Name ProductName

# Create/modify registry key
New-Item -Path HKCU:\Software\MyApp
Set-ItemProperty -Path HKCU:\Software\MyApp -Name Setting -Value "enabled"

# Remove registry key
Remove-Item -Path HKCU:\Software\MyApp -Recurse

```
