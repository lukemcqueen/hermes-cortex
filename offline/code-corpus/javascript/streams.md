---
language: javascript
tags: [io, file, util, async]
title: Streams
description: Readable/Writable/Transform, pipe, pipeline, and stream consumers in Node.js.
source: framework
---

```javascript
const { Readable, Transform, pipeline } = require('stream');
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
const src = Readable.from(['hello\n', 'world\n']);
src.pipe(process.stdout);

// Stream consumers (Node 16+)
async function readStream(stream) {
  for await (const chunk of stream) {
    console.log('Chunk:', chunk.toString());
  }
}

```
