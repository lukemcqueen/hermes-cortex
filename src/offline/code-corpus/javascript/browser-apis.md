---
language: javascript
tags: [web, api, dom]
title: Browser APIs
description: localStorage, sessionStorage, fetch, FormData, and file uploads.
source: pattern
---

```javascript
// Local storage
localStorage.setItem('theme', 'dark');
localStorage.setItem('user', JSON.stringify({ id: 1, name: 'Alice' }));

const theme = localStorage.getItem('theme');
const user = JSON.parse(localStorage.getItem('user'));
localStorage.removeItem('theme');
// localStorage.clear();

// Session storage (cleared on tab close)
sessionStorage.setItem('sessionToken', 'abc123');

// FormData
async function submitForm(formEl) {
  const formData = new FormData(formEl);
  formData.append('_timestamp', Date.now());

  const response = await fetch('/api/submit', {
    method: 'POST',
    body: formData // multipart/form-data
  });
  return response.json();
}

// File upload via input
async function uploadAvatar(fileInput) {
  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('avatar', file);

  const res = await fetch('/api/upload', { method: 'POST', body: formData });
  return res.json();
}

```
