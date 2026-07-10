---
language: powershell
tags: [pattern, powershell]
title: REST API & JSON
description: Invoke-RestMethod, Invoke-WebRequest, ConvertFrom-Json, handling headers, auth tokens, and pagination.
source: pattern
---

```powershell
# REST API consumption and JSON handling

# --- Basic GET request ---
$response = Invoke-RestMethod -Uri "https://api.github.com/repos/PowerShell/PowerShell/releases" -Method Get
$response[0].tag_name
$response[0].assets | Select-Object name, size, browser_download_url

# --- POST with JSON body ---
$body = @{
    title       = "Bug report"
    body        = "Something broke"
    labels      = @("bug", "urgent")
} | ConvertTo-Json

$headers = @{
    "Content-Type" = "application/json"
}

$result = Invoke-RestMethod -Uri "https://api.github.com/repos/owner/repo/issues" `
    -Method Post `
    -Headers $headers `
    -Body $body

# --- Authentication (Bearer token) ---
$token = "ghp_your_token_here"
$authHeaders = @{
    Authorization = "Bearer $token"
    Accept        = "application/vnd.github.v3+json"
}

$user = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $authHeaders
Write-Host "Authenticated as $($user.login)"

# --- Invoke-WebRequest (raw response) ---
$webResponse = Invoke-WebRequest -Uri "https://api.github.com/repos/PowerShell/PowerShell"
$webResponse.StatusCode          # 200
$webResponse.Headers             # response headers
$webResponse.Content             # raw JSON string
$webResponse.Content | ConvertFrom-Json | Select-Object full_name, description

# --- Pagination (GitHub-style Link header) ---
function Get-GitHubIssues {
    param(
        [string]$Repo = "PowerShell/PowerShell",
        [string]$State = "open",
        [int]$PerPage = 100
    )

    $uri = "https://api.github.com/repos/$Repo/issues?state=$State&per_page=$PerPage&page=1"
    $allIssues = @()

    do {
        $response = Invoke-WebRequest -Uri $uri -Headers @{
            Accept = "application/vnd.github.v3+json"
        }
        $issues = $response.Content | ConvertFrom-Json
        $allIssues += $issues

        # Parse Link header for next page
        if ($response.Headers.Link) {
            $nextLink = $response.Headers.Link -match '<([^>]+)>;\s*rel="next"'
            $uri = if ($nextLink) { $matches[1] } else { $null }
        } else {
            $uri = $null
        }
    } while ($uri)

    return $allIssues
}

# --- POST with form data ---
$formData = @{
    grant_type    = "client_credentials"
    client_id     = "my-id"
    client_secret = "my-secret"
}

$tokenResponse = Invoke-RestMethod -Uri "https://auth.example.com/token" `
    -Method Post `
    -Body $formData

$accessToken = $tokenResponse.access_token

# --- Error handling with REST ---
try {
    $result = Invoke-RestMethod -Uri "https://api.example.com/data" `
        -ErrorAction Stop
}
catch [System.Net.WebException] {
    $statusCode = $_.Exception.Response.StatusCode.value__
    $errorBody  = $_.ErrorDetails.Message
    Write-Error "API error $statusCode : $errorBody"
}
catch {
    Write-Error "Request failed: $_"
}

```
