---
language: javascript
tags: [async, pattern]
title: Promises
description: Promise creation, chaining, static methods: all, race, allSettled, resolve, reject.
source: pattern
---

```javascript
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

// Chaining
delay(100)
  .then(() => 'Step 1')
  .then(msg => { console.log(msg); return 'Step 2'; })
  .then(console.log)
  .catch(err => console.error('Failed:', err));

// Promise.all — fail fast
const all = Promise.all([
  fetch('/api/a').then(r => r.json()),
  fetch('/api/b').then(r => r.json())
]);
all.then(([a, b]) => console.log(a, b));

// Promise.allSettled — wait for all
async function fetchAllSettled(urls) {
  const results = await Promise.allSettled(
    urls.map(url => fetch(url).then(r => r.json()))
  );
  return results.map(r =>
    r.status === 'fulfilled' ? r.value : { error: r.reason.message }
  );
}

// Promise.race — first wins
const withTimeout = (promise, ms) =>
  Promise.race([
    promise,
    delay(ms).then(() => { throw new Error('Timeout'); })
  ]);

// Promise.resolve / reject
const cached = Promise.resolve('cached data');
const failed = Promise.reject(new Error('Bail out'));
failed.catch(() => {}); // suppress unhandled rejection

```
