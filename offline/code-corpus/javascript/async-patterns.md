---
language: javascript
tags: [async, pattern, net]
title: Async/Await Patterns
description: Modern async/await with error handling, parallel execution, and timeouts.
source: pattern
---

```javascript
// Parallel execution with Promise.all
async function fetchAll(urls) {
    try {
        const results = await Promise.all(
            urls.map(url => fetch(url).then(r => r.json()))
        );
        return results;
    } catch (error) {
        console.error('One or more requests failed:', error);
        throw error;
    }
}

// Sequential with error handling
async function processSequential(items) {
    const results = [];
    for (const item of items) {
        try {
            const result = await processItem(item);
            results.push(result);
        } catch (err) {
            results.push({ error: err.message, item });
        }
    }
    return results;
}

// Timeout wrapper
function withTimeout(promise, ms = 5000) {
    const timeout = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timeout')), ms)
    );
    return Promise.race([promise, timeout]);
}

// Retry with backoff
async function retry(fn, maxRetries = 3, delay = 1000) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            return await fn();
        } catch (err) {
            if (i === maxRetries - 1) throw err;
            await new Promise(r => setTimeout(r, delay * Math.pow(2, i)));
        }
    }
}

```
