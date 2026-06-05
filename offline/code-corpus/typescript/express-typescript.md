---
language: typescript
tags: [web, api, pattern]
title: Express with TypeScript
description: Typed Request/Response/NextFunction, typed middleware, and route handlers.
source: framework
---

```typescript
import express, { Request, Response, NextFunction } from 'express';
import { ErrorRequestHandler } from 'express-serve-static-core';

const app = express();
app.use(express.json());

// Typed request body
interface CreateUserBody {
  name: string;
  email: string;
}

interface UserResponse {
  id: number;
  name: string;
  email: string;
}

app.post('/api/users', (req: Request<{}, {}, CreateUserBody>, res: Response<UserResponse>) => {
  const { name, email } = req.body;
  const user: UserResponse = { id: Date.now(), name, email };
  res.status(201).json(user);
});

// Typed route params
app.get('/api/users/:id', (req: Request<{ id: string }>, res: Response<UserResponse | { error: string }>) => {
  const id = parseInt(req.params.id, 10);
  if (id !== 1) {
    res.status(404).json({ error: 'Not found' });
    return;
  }
  res.json({ id, name: 'Alice', email: 'alice@example.com' });
});

// Typed error-handling middleware
const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
};
app.use(errorHandler);

// Typed middleware
const logger: express.RequestHandler = (req, res, next) => {
  console.log(`${req.method} ${req.path}`);
  next();
};
app.use(logger);

app.listen(3000);

```
