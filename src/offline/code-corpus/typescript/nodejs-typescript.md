---
language: typescript
tags: [io, file, sys, net, config]
title: Node.js with TypeScript
description: Typed fs/path/http, @types packages, ESM vs CJS module configuration.
source: pattern
---

```typescript
import fs from 'node:fs/promises';
import path from 'node:path';
import http, { IncomingMessage, ServerResponse } from 'node:http';

// Typed file read/write
interface Config {
  port: number;
  host: string;
  debug: boolean;
}

async function readConfig(filePath: string): Promise<Config> {
  const raw = await fs.readFile(filePath, 'utf-8');
  const config: Config = JSON.parse(raw);
  return config;
}

// Typed HTTP server
const server = http.createServer(
  async (req: IncomingMessage, res: ServerResponse) => {
    res.setHeader('Content-Type', 'application/json');

    if (req.url === '/api/health') {
      res.writeHead(200);
      res.end(JSON.stringify({ status: 'ok' }));
      return;
    }

    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Not found' }));
  },
);

// ESM — package.json: "type": "module"
// import fs from 'node:fs/promises';  ✓
// CJS — package.json: no "type" or "type": "commonjs"
// import fs = require('node:fs');      ✓

// @types packages — always install dev dependencies
// npm install -D @types/node @types/express @types/react

// Path operations — typed and cross-platform
const dataDir = path.join(process.cwd(), 'data');
const logFile = path.resolve(dataDir, 'app.log');

server.listen(3000, () => {
  console.log(`Server running on port 3000`);
});

```
