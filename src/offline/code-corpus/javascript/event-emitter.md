---
language: javascript
tags: [pattern, util, async]
title: EventEmitter
description: Node.js EventEmitter: on, emit, once, removeListener, and custom events.
source: pattern
---

```javascript
const EventEmitter = require('events');

class Logger extends EventEmitter {
  log(level, message) {
    this.emit('message', { level, message, timestamp: Date.now() });
  }
}

const logger = new Logger();

// Single-use listener
logger.once('init', () => console.log('Logger initialized'));

function handleMessage({ level, message }) {
  console.log(`[${level}] ${message}`);
}

logger.on('message', handleMessage);

logger.emit('init');
logger.log('info', 'App started');
logger.log('warn', 'Low memory');

// Remove specific listener
logger.removeListener('message', handleMessage);
logger.log('error', 'This is not printed');

// Listener count
console.log('Listeners:', logger.listenerCount('message'));

```
