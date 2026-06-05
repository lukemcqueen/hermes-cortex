---
language: javascript
tags: [async, util]
title: Timers & Intervals
description: setTimeout, setInterval, clearTimeout, debounce, and throttle patterns.
source: pattern
---

```javascript
// Basic timers
const timeout = setTimeout(() => {
  console.log('Fired after 1s');
}, 1000);

const interval = setInterval(() => {
  console.log('Every 500ms');
}, 500);

// Clear them
clearTimeout(timeout);
clearInterval(interval);

// Debounce — fires after pause
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

const save = debounce(text => console.log('Saving:', text), 300);

// Throttle — fires at most once per interval
function throttle(fn, ms) {
  let last = 0;
  return (...args) => {
    const now = Date.now();
    if (now - last >= ms) {
      last = now;
      fn(...args);
    }
  };
}

const logScroll = throttle(() => console.log('Scrolled'), 200);

```
