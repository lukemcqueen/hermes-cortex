---
language: javascript
tags: [async, pattern]
title: Error-First Callback
description: Node.js callback(err, result) convention and promisification.
source: pattern
---

```javascript
// Custom function with error-first callback
function readConfig(path, callback) {
  // Simulate async work
  setTimeout(() => {
    try {
      if (!path) {
        throw new Error('Path is required');
      }
      const config = { host: 'localhost', port: 3000 };
      callback(null, config);
    } catch (err) {
      callback(err);
    }
  }, 100);
}

// Usage
readConfig('/etc/app.json', (err, config) => {
  if (err) {
    console.error('Failed:', err.message);
    return;
  }
  console.log('Config:', config);
});

// Promisify manually
function promisify(fn) {
  return (...args) =>
    new Promise((resolve, reject) => {
      fn(...args, (err, result) => {
        if (err) reject(err);
        else resolve(result);
      });
    });
}

// Using util.promisify (Node.js built-in)
const { promisify: nodePromisify } = require('util');
const readFile = nodePromisify(require('fs').readFile);

async function main() {
  const content = await readFile('file.txt', 'utf8');
  console.log(content);
}

```
