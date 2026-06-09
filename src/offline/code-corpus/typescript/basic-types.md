---
language: typescript
tags: [pattern, util]
title: Basic Types & Type Inference
description: TypeScript primitives: string, number, boolean, array, tuple, any, unknown, never, void with inference.
source: reference
---

```typescript
// Basic primitive types
let name: string = 'Alice';
let age: number = 30;
let isActive: boolean = true;

// Arrays and tuples
let scores: number[] = [85, 92, 78];
let pair: [string, number] = ['age', 30];

// any — opt out of type checking
let loose: any = 'could be anything';
loose = 42; // no error

// unknown — type-safe version of any
let input: unknown = JSON.parse('{"id":1}');
if (typeof input === 'object' && input !== null) {
  const obj = input as Record<string, unknown>;
  console.log(obj['id']);
}

// never — function never returns
function fail(msg: string): never {
  throw new Error(msg);
}

// void — function returns nothing
function log(msg: string): void {
  console.log(msg);
}

// Type inference — type is inferred automatically
let inferred = 'hello'; // inferred as string
// inferred = 42; // Error: Type 'number' not assignable to 'string'

```
