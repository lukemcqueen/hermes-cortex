---
language: javascript
tags: [algorithm, util]
title: Array Methods
description: map, filter, reduce, find, some, every, sort, flat, flatMap in action.
source: pattern
---

```javascript
const numbers = [3, 1, 4, 1, 5, 9, 2, 6];

// Transform
const doubled = numbers.map(n => n * 2);
const evens = numbers.filter(n => n % 2 === 0);
const sum = numbers.reduce((acc, n) => acc + n, 0);

// Search
const firstBig = numbers.find(n => n > 5);
const hasNegative = numbers.some(n => n < 0);
const allPositive = numbers.every(n => n > 0);

// Sort (copy)
const sorted = [...numbers].sort((a, b) => a - b);

// Flatten
const nested = [[1, 2], [3, [4, 5]]];
const flat1 = nested.flat();
const flat2 = nested.flat(2);

// flatMap
const words = ['hello world', 'foo bar'];
const tokens = words.flatMap(w => w.split(' '));

// Chaining
const result = numbers
  .filter(n => n > 3)
  .map(n => n * 10)
  .reduce((a, b) => a + b, 0);

console.log({ doubled, evens, sum, firstBig, hasNegative, allPositive });

```
