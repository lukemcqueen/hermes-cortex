---
language: javascript
tags: [web, api, server]
title: Express REST API
description: Express.js server with JSON routes, middleware, and error handling.
source: framework
---

```javascript
const express = require('express');
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

```
