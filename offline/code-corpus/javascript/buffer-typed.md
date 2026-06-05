---
language: javascript
tags: [util, io]
title: Buffer & Typed Arrays
description: Node Buffer, Uint8Array, DataView, TextEncoder/TextDecoder.
source: pattern
---

```javascript
// Node.js Buffer
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

```
