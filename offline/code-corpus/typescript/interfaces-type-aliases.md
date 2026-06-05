---
language: typescript
tags: [pattern, util]
title: Interfaces & Type Aliases
description: Interface vs type, extends, intersection types, Pick/Omit/Partial with interfaces.
source: reference
---

```typescript
// Interface — extends, mergeable
interface User {
  id: number;
  name: string;
  email: string;
}

interface Admin extends User {
  role: 'admin';
  permissions: string[];
}

// Type alias — intersection, computed properties
type Point = { x: number; y: number };
type NamedPoint = Point & { name: string };

const origin: NamedPoint = { x: 0, y: 0, name: 'origin' };

// Utility transformations on interfaces
type PartialUser = Partial<User>;
type UserNameAndEmail = Pick<User, 'name' | 'email'>;
type WithoutEmail = Omit<User, 'email'>;

// Readonly
const frozen: Readonly<User> = {
  id: 1, name: 'Alice', email: 'a@b.com',
};
// frozen.name = 'Bob'; // Error: readonly

// Interface vs type — use interface for public APIs, type for unions/computed
type Status = 'active' | 'inactive' | 'pending';

```
