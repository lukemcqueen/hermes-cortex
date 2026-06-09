---
language: javascript
tags: [web, net, api, server]
title: HTTP Module
description: Node.js http.createServer: req/res, URL parsing, headers, JSON responses.
source: framework
---

```javascript
const http = require('http');
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

```
