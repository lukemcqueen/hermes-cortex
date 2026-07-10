---
language: powershell
tags: [pattern, powershell]
title: Active Directory & Users
description: Get-ADUser, New-ADUser, Set-ADUser, group management, computer objects, and AD module basics.
source: pattern
---

```powershell
# Active Directory management with PowerShell

# --- Prerequisites ---
# Import-Module ActiveDirectory
# Or install RSAT: Add-WindowsCapability -Name Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0

# --- Query users ---
Get-ADUser -Identity jdoe
Get-ADUser -Filter {Enabled -eq $true} -Properties LastLogonDate, Department
Get-ADUser -Filter "Title -like '*Engineer*'" -SearchBase "OU=Engineering,DC=contoso,DC=com"

# --- Create a new user ---
New-ADUser -Name "John Doe" `
    -GivenName John `
    -Surname Doe `
    -SamAccountName jdoe `
    -UserPrincipalName jdoe@contoso.com `
    -Title "Software Engineer" `
    -Department Engineering `
    -Company Contoso `
    -Office "Building 4" `
    -StreetAddress "123 Main St" `
    -City "Seattle" `
    -State "WA" `
    -PostalCode "98101" `
    -Country US `
    -PhoneNumber "555-0100" `
    -MobilePhone "555-0199" `
    -AccountPassword (ConvertTo-SecureString "P@ssw0rd!" -AsPlainText -Force) `
    -Enabled $true `
    -PassThru

# --- Modify users ---
Set-ADUser jdoe -OfficePhone "555-0200" -Title "Senior Engineer"
Set-ADUser jdoe -Replace @{extensionAttribute1 = "Onboarding"}

# Disable / Enable
Disable-ADAccount -Identity jdoe
Enable-ADAccount -Identity jdoe

# --- Group management ---
# Create group
New-ADGroup -Name "Engineering-Admins" `
    -GroupScope Global `
    -GroupCategory Security `
    -Path "OU=Groups,DC=contoso,DC=com"

# Add/remove members
Add-ADGroupMember -Identity "Engineering-Admins" -Members jdoe, asmith
Remove-ADGroupMember -Identity "Engineering-Admins" -Members asmith -Confirm:$false

# Get group membership
Get-ADGroupMember -Identity "Domain Admins" | Select-Object Name, SamAccountName

# --- Computer objects ---
Get-ADComputer -Filter {OperatingSystem -like "*Server*"} -Properties OperatingSystem
Get-ADComputer -Identity SRV-APP01
Move-ADObject -Identity "CN=SRV-APP01,CN=Computers,DC=contoso,DC=com" `
    -TargetPath "OU=Servers,DC=contoso,DC=com"

```
