---
language: typescript
tags: [pattern, util, api]
title: Zod Validation
description: Schema definition with z.object, parse/safeParse, inferred types from schemas.
source: library
---

```typescript
import { z } from 'zod';

// Define schema
const UserSchema = z.object({
  id: z.number().int().positive(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().int().min(0).optional(),
  role: z.enum(['admin', 'user', 'guest']).default('user'),
});

// Infer TypeScript type from schema
type User = z.infer<typeof UserSchema>;

// Parse with validation — throws on failure
const rawData = { id: 1, name: 'Alice', email: 'alice@example.com', age: 30 };
const user: User = UserSchema.parse(rawData);

// Safe parse — returns result object, no throw
const result = UserSchema.safeParse({ id: -1, name: '', email: 'bad' });
if (!result.success) {
  console.error(result.error.format());
  // {
  //   id: { _errors: ['Number must be positive'] },
  //   name: { _errors: ['String must contain at least 1 character(s)'] },
  //   email: { _errors: ['Invalid email'] },
  // }
}

// Partial and pick from schemas
const PartialUserSchema = UserSchema.partial();
const UserNameSchema = UserSchema.pick({ name: true, email: true });

```
