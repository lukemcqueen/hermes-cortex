---
language: javascript
tags: [pattern, util]
title: Closures & Scope
description: Lexical scope, IIFE, module pattern, and factory functions.
source: pattern
---

```javascript
// Factory function with closure
function createCounter(start = 0) {
  let count = start;
  return {
    increment: () => ++count,
    decrement: () => --count,
    value: () => count,
    reset: () => { count = start; }
  };
}

const counter = createCounter(10);
counter.increment();
counter.increment();
console.log(counter.value()); // 12

// IIFE — module pattern
const bankAccount = (function() {
  let balance = 0;
  return {
    deposit(amount) {
      if (amount > 0) balance += amount;
    },
    withdraw(amount) {
      if (amount <= balance) balance -= amount;
    },
    getBalance() { return balance; }
  };
})();

bankAccount.deposit(100);
console.log(bankAccount.getBalance()); // 100
// balance is not accessible from outside

// Private variable via closure
function createMultiplier(factor) {
  return x => x * factor;
}

```
