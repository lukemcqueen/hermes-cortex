---
language: javascript
tags: [pattern, util]
title: Error Handling
description: try/catch/finally, throw, custom Error classes, and error cause chaining.
source: pattern
---

```javascript
// Custom error class
class ValidationError extends Error {
  constructor(message, field) {
    super(message);
    this.name = 'ValidationError';
    this.field = field;
  }
}

// Throwing
function parseAge(input) {
  const age = Number(input);
  if (Number.isNaN(age)) {
    throw new ValidationError('Must be a number', 'age');
  }
  if (age < 0 || age > 150) {
    throw new ValidationError('Out of range', 'age');
  }
  return age;
}

// Handling with finally
function processInput(raw) {
  try {
    const age = parseAge(raw);
    console.log(`Age: ${age}`);
  } catch (err) {
    if (err instanceof ValidationError) {
      console.error(`Field "${err.field}": ${err.message}`);
    } else {
      // Re-throw unexpected errors with cause
      throw new Error('Unexpected input error', { cause: err });
    }
  } finally {
    console.log('Cleanup: always runs');
  }
}

processInput('25');   // OK
processInput('abc');  // ValidationError caught

```
