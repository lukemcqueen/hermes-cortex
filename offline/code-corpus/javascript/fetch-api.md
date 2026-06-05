---
language: javascript
tags: [web, net, api]
title: Fetch API
description: HTTP requests with the Fetch API: GET, POST, headers, error handling, uploads.
source: pattern
---

```javascript
// GET with error handling
async function getJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// POST with JSON body
async function postJSON(url, data) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error(`POST failed: ${response.status}`);
    return response.json();
}

// Upload file
async function uploadFile(url, file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(url, { method: 'POST', body: formData });
    return response.json();
}

// Download file as blob
async function downloadFile(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Download failed');
    return response.blob();
}

```
