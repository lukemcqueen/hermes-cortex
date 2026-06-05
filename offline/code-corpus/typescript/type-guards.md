---
language: typescript
tags: [pattern, util]
title: Type Guards & Narrowing
description: typeof, instanceof, in, discriminated union narrowing, and type predicates.
source: reference
---

```typescript
// typeof guard
function format(value: string | number): string {
  if (typeof value === 'string') {
    return value.toUpperCase();
  }
  return value.toFixed(2);
}

// instanceof guard
class APIError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message);
  }
}

function handleError(err: Error | APIError): void {
  if (err instanceof APIError) {
    console.error(`API ${err.statusCode}: ${err.message}`);
  } else {
    console.error(err.message);
  }
}

// 'in' operator guard
interface Fish { swim(): void; }
interface Bird { fly(): void; }

function move(animal: Fish | Bird): void {
  if ('swim' in animal) {
    animal.swim();
  } else {
    animal.fly();
  }
}

// Type predicate — custom type guard function
function isFish(pet: Fish | Bird): pet is Fish {
  return (pet as Fish).swim !== undefined;
}

function feed(pet: Fish | Bird): void {
  if (isFish(pet)) {
    pet.swim(); // narrowed to Fish
  }
}

```
