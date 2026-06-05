---
language: javascript
tags: [pattern, util]
title: ES Modules
description: Import/export syntax: named, default, re-exports, and dynamic imports.
source: textbook
---

```javascript
// ---- math.js ----
export const PI = 3.14159;

export function add(a, b) {
  return a + b;
}

export default function multiply(a, b) {
  return a * b;
}

// ---- utils.js ----
export { add, PI } from './math.js';
export { default as times } from './math.js';

// ---- app.js ----
import times, { add, PI } from './math.js';

const result = add(PI, times(2, 3));
console.log(result); // 9.14159

// Dynamic import
const modulePath = './math.js';
const mod = await import(modulePath);
console.log(mod.add(5, 7));

```
