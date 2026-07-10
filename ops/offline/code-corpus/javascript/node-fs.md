---
language: javascript
tags: [io, file, util]
title: Node.js File System
description: fs.readFile/writeFile sync+async, fs.promises, and path operations.
source: framework
---

```javascript
const fs = require('fs');
const fsPromises = require('fs').promises;
const path = require('path');

// Sync
const data = fs.readFileSync(path.join(__dirname, 'file.txt'), 'utf8');
fs.writeFileSync('out.txt', data.toUpperCase());

// Async callback
fs.readFile('file.txt', 'utf8', (err, content) => {
  if (err) throw err;
  fs.writeFile('copy.txt', content, () => {});
});

// Async promise
async function processFile(src, dest) {
  try {
    const content = await fsPromises.readFile(src, 'utf8');
    await fsPromises.writeFile(dest, content.replace(/foo/g, 'bar'));
    const stats = await fsPromises.stat(dest);
    console.log(`Written ${stats.size} bytes`);
  } catch (err) {
    console.error('File error:', err.message);
  }
}

```
