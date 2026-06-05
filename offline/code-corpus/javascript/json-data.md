---
language: javascript
tags: [io, string, util]
title: JSON & Structured Data
description: JSON.parse/stringify, reviver, structuredClone, serialization patterns.
source: pattern
---

```javascript
// Parse with reviver — transform dates
const data = '{"name":"Event","date":"2025-01-15T10:00:00Z"}';
const parsed = JSON.parse(data, (key, value) => {
  if (key === 'date') return new Date(value);
  return value;
});
console.log(parsed.date instanceof Date); // true

// Stringify with replacer and formatting
const obj = {
  name: 'Alice',
  password: 'secret',
  scores: [95, 87, 92],
  meta: { version: 2 }
};

const json = JSON.stringify(obj, (key, value) => {
  if (key === 'password') return undefined;
  if (key === 'scores') return value.join(', ');
  return value;
}, 2);
console.log(json);

// Deep clone
const clone = structuredClone(obj);
console.log(clone.meta === obj.meta); // false

// Safe parse
function safeParse(text) {
  try {
    return { ok: true, data: JSON.parse(text) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

```
