"""JavaScript snippets — 20 entries covering the full JS ecosystem."""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    # 1. ES6 CLASSES
    # ═══════════════════════════════════════════════════════════
    ("javascript/es6-classes.md", "javascript", ["pattern", "util"],
     "ES6 Classes", "Class syntax: constructor, methods, getters/setters, static, extends, super.", "textbook",
     """class Animal {
  constructor(name) {
    this.name = name;
  }

  speak() {
    return `${this.name} makes a sound.`;
  }

  static categorize() {
    return 'Living thing';
  }

  get info() {
    return `Name: ${this.name}`;
  }

  set alias(nick) {
    this.name = nick;
  }
}

class Dog extends Animal {
  constructor(name, breed) {
    super(name);
    this.breed = breed;
  }

  speak() {
    return `${this.name} barks!`;
  }

  static categorize() {
    return 'Mammal';
  }
}

const dog = new Dog('Rex', 'Husky');
console.log(dog.speak());
console.log(Dog.categorize());
"""),

    # ═══════════════════════════════════════════════════════════
    # 2. MODULES
    # ═══════════════════════════════════════════════════════════
    ("javascript/modules.md", "javascript", ["pattern", "util"],
     "ES Modules", "Import/export syntax: named, default, re-exports, and dynamic imports.", "textbook",
     """// ---- math.js ----
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 3. NODE.JS FILE SYSTEM
    # ═══════════════════════════════════════════════════════════
    ("javascript/node-fs.md", "javascript", ["io", "file", "util"],
     "Node.js File System", "fs.readFile/writeFile sync+async, fs.promises, and path operations.", "framework",
     """const fs = require('fs');
const fsPromises = require('fs').promises;
const path = require('path');

// Sync
const data = fs.readFileSync(path.join(__dirname, 'file.txt'), 'utf8');
fs.writeFileSync('out.txt', data.toUpperCase());

// Async callback
fs.readFile('file.txt', 'utf8', (err, content) => {
  if (err) throw err;
  fs.writeFile('copy.txt', content, () => {});
});

// Async promise
async function processFile(src, dest) {
  try {
    const content = await fsPromises.readFile(src, 'utf8');
    await fsPromises.writeFile(dest, content.replace(/foo/g, 'bar'));
    const stats = await fsPromises.stat(dest);
    console.log(`Written ${stats.size} bytes`);
  } catch (err) {
    console.error('File error:', err.message);
  }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 4. EXPRESS.JS REST API
    # ═══════════════════════════════════════════════════════════
    ("javascript/express-api.md", "javascript", ["web", "api", "server"],
     "Express REST API", "Express.js server with JSON routes, middleware, and error handling.", "framework",
     """const express = require('express');
const app = express();
app.use(express.json());

const items = [];

app.get('/api/items', (req, res) => {
  const { page = 1, limit = 10 } = req.query;
  res.json(items.slice(0, Number(limit)));
});

app.post('/api/items', (req, res) => {
  if (!req.body.name) {
    return res.status(400).json({ error: 'Name required' });
  }
  const item = { id: items.length + 1, ...req.body };
  items.push(item);
  res.status(201).json(item);
});

app.put('/api/items/:id', (req, res) => {
  const idx = items.findIndex(i => i.id === Number(req.params.id));
  if (idx === -1) return res.status(404).json({ error: 'Not found' });
  items[idx] = { ...items[idx], ...req.body, id: items[idx].id };
  res.json(items[idx]);
});

app.delete('/api/items/:id', (req, res) => {
  const idx = items.findIndex(i => i.id === Number(req.params.id));
  if (idx === -1) return res.status(404).json({ error: 'Not found' });
  items.splice(idx, 1);
  res.status(204).send();
});

app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal error' });
});

app.listen(3000, () => console.log('API on :3000'));
"""),

    # ═══════════════════════════════════════════════════════════
    # 5. EVENTEMITTER
    # ═══════════════════════════════════════════════════════════
    ("javascript/event-emitter.md", "javascript", ["pattern", "util", "async"],
     "EventEmitter", "Node.js EventEmitter: on, emit, once, removeListener, and custom events.", "pattern",
     """const EventEmitter = require('events');

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 6. PROMISES
    # ═══════════════════════════════════════════════════════════
    ("javascript/promises.md", "javascript", ["async", "pattern"],
     "Promises", "Promise creation, chaining, static methods: all, race, allSettled, resolve, reject.", "pattern",
     """const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 7. ARRAY METHODS
    # ═══════════════════════════════════════════════════════════
    ("javascript/array-methods.md", "javascript", ["algorithm", "util"],
     "Array Methods", "map, filter, reduce, find, some, every, sort, flat, flatMap in action.", "pattern",
     """const numbers = [3, 1, 4, 1, 5, 9, 2, 6];

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 8. CLOSURES & SCOPE
    # ═══════════════════════════════════════════════════════════
    ("javascript/closures-scope.md", "javascript", ["pattern", "util"],
     "Closures & Scope", "Lexical scope, IIFE, module pattern, and factory functions.", "pattern",
     """// Factory function with closure
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 9. PROTOTYPES & INHERITANCE
    # ═══════════════════════════════════════════════════════════
    ("javascript/prototypes.md", "javascript", ["pattern"],
     "Prototypes & Inheritance", "Prototype chain, Object.create, constructor functions vs class syntax.", "textbook",
     """// Constructor function
function Vehicle(type, speed) {
  this.type = type;
  this.speed = speed;
}

Vehicle.prototype.move = function() {
  return `${this.type} moves at ${this.speed} km/h`;
};

Vehicle.prototype.stop = function() {
  this.speed = 0;
  return `${this.type} stopped`;
};

// Prototypal inheritance
function Car(brand, speed) {
  Vehicle.call(this, 'car', speed);
  this.brand = brand;
}

Car.prototype = Object.create(Vehicle.prototype);
Car.prototype.constructor = Car;

Car.prototype.honk = function() {
  return `${this.brand} honks!`;
};

const tesla = new Car('Tesla', 120);
console.log(tesla.move());
console.log(tesla.honk());
console.log(tesla instanceof Vehicle);

// Object.create for direct inheritance
const proto = { greet() { return 'Hi!'; } };
const obj = Object.create(proto);
console.log(obj.greet()); // 'Hi!'
"""),

    # ═══════════════════════════════════════════════════════════
    # 10. ERROR HANDLING
    # ═══════════════════════════════════════════════════════════
    ("javascript/error-handling.md", "javascript", ["pattern", "util"],
     "Error Handling", "try/catch/finally, throw, custom Error classes, and error cause chaining.", "pattern",
     """// Custom error class
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 11. TIMERS & INTERVALS
    # ═══════════════════════════════════════════════════════════
    ("javascript/timers.md", "javascript", ["async", "util"],
     "Timers & Intervals", "setTimeout, setInterval, clearTimeout, debounce, and throttle patterns.", "pattern",
     """// Basic timers
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 12. ES6+ FEATURES
    # ═══════════════════════════════════════════════════════════
    ("javascript/es6-features.md", "javascript", ["util", "pattern"],
     "ES6+ Features", "Destructuring, spread/rest, optional chaining, nullish coalescing, template literals.", "pattern",
     """// Destructuring
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 13. STREAMS
    # ═══════════════════════════════════════════════════════════
    ("javascript/streams.md", "javascript", ["io", "file", "util", "async"],
     "Streams", "Readable/Writable/Transform, pipe, pipeline, and stream consumers in Node.js.", "framework",
     """const { Readable, Transform, pipeline } = require('stream');
const { createReadStream, createWriteStream } = require('fs');

// Transform stream: uppercase
const upper = new Transform({
  transform(chunk, encoding, callback) {
    this.push(chunk.toString().toUpperCase());
    callback();
  }
});

// Pipeline with error handling
pipeline(
  createReadStream('input.txt'),
  upper,
  createWriteStream('output.txt'),
  err => {
    if (err) {
      console.error('Pipeline failed:', err);
      process.exit(1);
    }
    console.log('Done');
  }
);

// Readable from iterable
const src = Readable.from(['hello\\n', 'world\\n']);
src.pipe(process.stdout);

// Stream consumers (Node 16+)
async function readStream(stream) {
  for await (const chunk of stream) {
    console.log('Chunk:', chunk.toString());
  }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 14. HTTP MODULE
    # ═══════════════════════════════════════════════════════════
    ("javascript/http-module.md", "javascript", ["web", "net", "api", "server"],
     "HTTP Module", "Node.js http.createServer: req/res, URL parsing, headers, JSON responses.", "framework",
     """const http = require('http');
const url = require('url');

const server = http.createServer((req, res) => {
  const parsed = new URL(req.url, `http://${req.headers.host}`);
  const path = parsed.pathname;
  const method = req.method;

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json');

  if (path === '/api/health' && method === 'GET') {
    res.writeHead(200);
    return res.end(JSON.stringify({ status: 'ok' }));
  }

  if (path === '/api/echo' && method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      res.writeHead(200);
      res.end(JSON.stringify({ received: body, parsed: JSON.parse(body) }));
    });
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(8080, () => console.log('HTTP on :8080'));
"""),

    # ═══════════════════════════════════════════════════════════
    # 15. WEBSOCKETS
    # ═══════════════════════════════════════════════════════════
    ("javascript/websockets.md", "javascript", ["net", "web"],
     "WebSockets", "WebSocket server and client using the ws library.", "framework",
     """const WebSocket = require('ws');

// Server
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws, req) => {
  console.log('Client connected from', req.socket.remoteAddress);

  ws.on('message', (data) => {
    const msg = data.toString();
    console.log('Received:', msg);

    // Echo back
    ws.send(`Server echo: ${msg}`);

    // Broadcast to all other clients
    wss.clients.forEach(client => {
      if (client !== ws && client.readyState === WebSocket.OPEN) {
        client.send(`Broadcast: ${msg}`);
      }
    });
  });

  ws.on('close', () => console.log('Client disconnected'));

  ws.send('Welcome to the WebSocket server!');
});

// Client
const ws = new WebSocket('ws://localhost:8080');

ws.on('open', () => {
  ws.send('Hello from client!');
});

ws.on('message', data => {
  console.log('Server says:', data.toString());
  ws.close();
});

ws.on('error', err => console.error('WS Error:', err.message));
"""),

    # ═══════════════════════════════════════════════════════════
    # 16. JSON & STRUCTURED DATA
    # ═══════════════════════════════════════════════════════════
    ("javascript/json-data.md", "javascript", ["io", "string", "util"],
     "JSON & Structured Data", "JSON.parse/stringify, reviver, structuredClone, serialization patterns.", "pattern",
     """// Parse with reviver — transform dates
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 17. LOCAL STORAGE / BROWSER APIS
    # ═══════════════════════════════════════════════════════════
    ("javascript/browser-apis.md", "javascript", ["web", "api", "dom"],
     "Browser APIs", "localStorage, sessionStorage, fetch, FormData, and file uploads.", "pattern",
     """// Local storage
localStorage.setItem('theme', 'dark');
localStorage.setItem('user', JSON.stringify({ id: 1, name: 'Alice' }));

const theme = localStorage.getItem('theme');
const user = JSON.parse(localStorage.getItem('user'));
localStorage.removeItem('theme');
// localStorage.clear();

// Session storage (cleared on tab close)
sessionStorage.setItem('sessionToken', 'abc123');

// FormData
async function submitForm(formEl) {
  const formData = new FormData(formEl);
  formData.append('_timestamp', Date.now());

  const response = await fetch('/api/submit', {
    method: 'POST',
    body: formData // multipart/form-data
  });
  return response.json();
}

// File upload via input
async function uploadAvatar(fileInput) {
  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('avatar', file);

  const res = await fetch('/api/upload', { method: 'POST', body: formData });
  return res.json();
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 18. ERROR-FIRST CALLBACK PATTERN
    # ═══════════════════════════════════════════════════════════
    ("javascript/error-first-callback.md", "javascript", ["async", "pattern"],
     "Error-First Callback", "Node.js callback(err, result) convention and promisification.", "pattern",
     """// Custom function with error-first callback
function readConfig(path, callback) {
  // Simulate async work
  setTimeout(() => {
    try {
      if (!path) {
        throw new Error('Path is required');
      }
      const config = { host: 'localhost', port: 3000 };
      callback(null, config);
    } catch (err) {
      callback(err);
    }
  }, 100);
}

// Usage
readConfig('/etc/app.json', (err, config) => {
  if (err) {
    console.error('Failed:', err.message);
    return;
  }
  console.log('Config:', config);
});

// Promisify manually
function promisify(fn) {
  return (...args) =>
    new Promise((resolve, reject) => {
      fn(...args, (err, result) => {
        if (err) reject(err);
        else resolve(result);
      });
    });
}

// Using util.promisify (Node.js built-in)
const { promisify: nodePromisify } = require('util');
const readFile = nodePromisify(require('fs').readFile);

async function main() {
  const content = await readFile('file.txt', 'utf8');
  console.log(content);
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 19. TEST PATTERNS
    # ═══════════════════════════════════════════════════════════
    ("javascript/test-patterns.md", "javascript", ["test", "pattern"],
     "Test Patterns", "Jest/Vitest: describe, it, expect matchers, mocks, and snapshots.", "framework",
     """// math.js
export const add = (a, b) => a + b;
export const fetchUser = async (id) => {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error('Not found');
  return res.json();
};

// math.test.js
import { describe, it, expect, vi } from 'vitest';
import { add, fetchUser } from './math.js';

describe('add()', () => {
  it('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  it('handles negatives', () => {
    expect(add(-1, -2)).toBe(-3);
  });

  it('is not NaN for strings', () => {
    expect(add('a', 1)).toBeNaN();
  });
});

describe('fetchUser()', () => {
  it('returns user data', async () => {
    const mock = vi.fn().mockResolvedValue({ id: 1, name: 'Alice' });
    global.fetch = mock;

    const user = await fetchUser(1);
    expect(user.name).toBe('Alice');
    expect(mock).toHaveBeenCalledWith('/api/users/1');
  });

  it('throws on error', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    await expect(fetchUser(2)).rejects.toThrow('Not found');
  });
});

// Snapshot test
it('matches snapshot', () => {
  const output = JSON.stringify({ a: 1, b: 2 });
  expect(output).toMatchSnapshot();
});
"""),

    # ═══════════════════════════════════════════════════════════
    # 20. BUFFER & TYPED ARRAYS
    # ═══════════════════════════════════════════════════════════
    ("javascript/buffer-typed.md", "javascript", ["util", "io"],
     "Buffer & Typed Arrays", "Node Buffer, Uint8Array, DataView, TextEncoder/TextDecoder.", "pattern",
     """// Node.js Buffer
const buf = Buffer.alloc(8);
buf.writeUInt32BE(0xDEADBEEF, 0);
buf.writeUInt32LE(0xCAFEBABE, 4);
console.log(buf.toString('hex')); // deadbeefbebafeca

const str = 'Hello 世界';
const encoded = Buffer.from(str, 'utf8');
console.log(encoded.length); // 11 bytes

// Uint8Array (browser + Node)
const uint8 = new Uint8Array([72, 101, 108, 108, 111]);
const decoded = new TextDecoder().decode(uint8);
console.log(decoded); // 'Hello'

// TextEncoder
const encoder = new TextEncoder();
const bytes = encoder.encode('Hello 世界');
console.log(bytes.length); // 11

// DataView — read/write at byte level
const buffer = new ArrayBuffer(8);
const view = new DataView(buffer);
view.setInt32(0, -42, true);        // little-endian
view.setFloat64(4, 3.14159, true);  // offset 4
console.log(view.getInt32(0, true));
console.log(view.getFloat64(4, true));

// Typed array from existing buffer
const shared = new Uint8Array(buffer);
console.log([...shared]);
"""),
]
