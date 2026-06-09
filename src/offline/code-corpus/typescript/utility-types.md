---
language: typescript
tags: [pattern, util]
title: Utility Types
description: Partial, Required, Readonly, Record, Pick, Omit, Exclude, Extract, ReturnType, Parameters.
source: reference
---

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'user';
}

// Partial — all properties optional
const partial: Partial<User> = { name: 'Alice' };

// Required — all properties required (even optional ones)
type RequiredFields = Required<Partial<User>>;

// Readonly — no mutation allowed
const frozen: Readonly<User> = { id: 1, name: 'A', email: 'a@b.com', role: 'admin' };

// Record — dictionary with constrained keys
type Page = 'home' | 'about' | 'contact';
const routes: Record<Page, string> = {
  home: '/',
  about: '/about',
  contact: '/contact',
};

// Pick — select specific keys
const picked: Pick<User, 'id' | 'name'> = { id: 1, name: 'Alice' };

// Omit — exclude specific keys
const withoutRole: Omit<User, 'role'> = { id: 1, name: 'A', email: 'a@b.com' };

// Exclude — remove from union
type Roles = 'admin' | 'user' | 'guest';
type NonAdmin = Exclude<Roles, 'admin'>; // 'user' | 'guest'

// ReturnType — infer return type of a function
const createUser = (name: string): User => ({ id: 1, name, email: '', role: 'user' });
type NewUser = ReturnType<typeof createUser>;

// Parameters — infer parameter types
type CreateUserParams = Parameters<typeof createUser>; // [string]

```
