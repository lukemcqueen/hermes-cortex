---
language: powershell
tags: [pattern, powershell]
title: Modules & Scripts
description: .psm1, .psd1, Import-Module, script scope, dot sourcing, and module manifests.
source: pattern
---

```powershell
# PowerShell modules and scripts

# --- Script file (.ps1) ---
# myscript.ps1
Write-Host "Running script"
$privateVar = "script-scoped"

function Get-Secret {
    param([string]$Name)
    return "secret-$Name"
}

# --- Module (.psm1) ---
# MyModule/MyModule.psm1
$script:ModuleVersion = "1.0.0"

function Get-MyModuleInfo {
    return "MyModule v$script:ModuleVersion"
}

function Set-MyConfiguration {
    param([string]$ConfigPath)
    $script:ConfigPath = $ConfigPath
}

# Export only specific functions
Export-ModuleMember -Function Get-MyModuleInfo, Set-MyConfiguration

# --- Module manifest (.psd1) ---
# MyModule/MyModule.psd1
@{
    RootModule           = 'MyModule.psm1'
    ModuleVersion        = '1.0.0'
    GUID                 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    Author               = 'Your Name'
    CompanyName          = 'Your Company'
    Copyright            = '(c) 2024 Your Name'
    Description          = 'Sample PowerShell module'
    PowerShellVersion    = '7.0'
    FunctionsToExport    = @('Get-MyModuleInfo', 'Set-MyConfiguration')
    CmdletsToExport      = @()
    VariablesToExport    = @()
    AliasesToExport      = @()
}

# --- Import module ---
Import-Module .\MyModule
Import-Module .\MyModule -Force        # re-import after changes
Import-Module ActiveDirectory          # from module path
Get-Module -ListAvailable               # see installed modules

# --- Dot sourcing (runs in current scope) ---
. .\utils.ps1                           # brings functions into global scope
# vs
.\utils.ps1                             # runs in child scope -- vars not persisted

# --- Module scope ---
# $script:     -- script/module scope
# $private:    -- private (not exported)
# $global:     -- visible everywhere
# $local:      -- current scope (default)

```
