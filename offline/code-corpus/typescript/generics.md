---
language: typescript
tags: [pattern, util]
title: Generics
description: Generic functions, constraints, generic interfaces, and default type parameters.
source: reference
---

```typescript
// Generic function
function identity<T>(arg: T): T {
  return arg;
}

const num = identity<number>(42);
const str = identity('hello'); // inferred

// Generic interface
interface Repository<T> {
  getById(id: string): T | undefined;
  getAll(): T[];
  create(item: T): void;
}

// Generic constraint with extends
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const user = { id: 1, name: 'Alice' };
const userName = getProperty(user, 'name'); // string

// Default type parameter
function createArray<T = string>(length: number, value: T): T[] {
  return Array(length).fill(value);
}

const strings = createArray(3, 'x'); // string[]
const numbers = createArray<number>(3, 0); // number[]

// Generic class
class Stack<T> {
  private items: T[] = [];
  push(item: T): void { this.items.push(item); }
  pop(): T | undefined { return this.items.pop(); }
}

const numStack = new Stack<number>();
numStack.push(1);

```
