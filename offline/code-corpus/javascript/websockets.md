---
language: javascript
tags: [net, web]
title: WebSockets
description: WebSocket server and client using the ws library.
source: framework
---

```javascript
const WebSocket = require('ws');

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

```
