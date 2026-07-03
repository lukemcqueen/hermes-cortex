---
language: javascript
tags: [util, pattern]
title: ES6+ Features
description: Destructuring, spread/rest, optional chaining, nullish coalescing, template literals.
source: pattern
---

```javascript
// Destructuring
const user = { name: 'Alice', age: 30, city: 'NYC' };
const { name, ...rest } = user;
const colors = ['red', 'green', 'blue'];
const [first, , third] = colors;

// Spread
const merged = { ...user, role: 'admin' };
const combined = [...colors, 'yellow'];

// Rest parameters
function sum(...nums) {
  return nums.reduce((a, b) => a + b, 0);
}
console.log(sum(1, 2, 3, 4)); // 10

// Optional chaining
const data = { users: [{ profile: { email: 'a@b.com' } }] };
const email = data?.users?.[0]?.profile?.email;
console.log(email); // 'a@b.com'

// Nullish coalescing
const input = null;
const value = input ?? 'default';
const falsy = input || 'default'; // same here but 0/''
console.log(value); // 'default'

// Template literals
const greeting = `Hello, ${name}! You are ${rest.age}.`;

```
