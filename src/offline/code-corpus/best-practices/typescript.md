---
language: typescript
tags: [typescript, best-practices, type-safety]
title: TypeScript Best Practices
description: Strict mode, noImplicitAny, discriminated unions, satisfies operator, branded types, never type exhaustiveness, and interfaces over types for objects
source: pattern
---

# TypeScript Best Practices

## Strict Mode
Always enable strict mode in `tsconfig.json` — this implies `noImplicitAny`, `strictNullChecks`, `strictFunctionTypes`, and more:

```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

## Discriminated Unions
Model state machines and API responses with tagged unions:

```typescript
type ApiResult<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string; code: number };

function handleResult<T>(result: ApiResult<T>): string {
  switch (result.status) {
    case "loading":
      return "Loading…";
    case "success":
      return `Got ${result.data}`;
    case "error":
      return `Error ${result.code}: ${result.message}`;
  }
}
```

## `satisfies` Operator
Use `satisfies` to infer narrow types without widening:

```typescript
const palette = {
  red: [255, 0, 0],
  green: "#00ff00",
  blue: [0, 0, 255],
} satisfies Record<string, string | number[]>;

// palette.red is inferred as number[], not string | number[]
palette.red.map(Math.round); // OK
```

## Branded Types
Use branded types to prevent mixing semantically different primitives:

```typescript
type Brand<T, B extends string> = T & { __brand: B };

type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;

function createUser(id: UserId): void {
  /* … */
}

const uid = "abc123" as UserId;
createUser(uid); // OK
// createUser("abc123");      // ❌ Type error
// createUser(uid as OrderId); // ❌ Type error
```

## Never Type Exhaustiveness
Use `never` in the default branch to catch unhandled union members at compile time:

```typescript
type Shape =
  | { kind: "circle"; radius: number }
  | { kind: "square"; side: number }
  | { kind: "triangle"; base: number; height: number };

function area(shape: Shape): number {
  switch (shape.kind) {
    case "circle":
      return Math.PI * shape.radius ** 2;
    case "square":
      return shape.side ** 2;
    case "triangle":
      return (shape.base * shape.height) / 2;
    default:
      // If a new Shape variant is added, this line forces a compile error
      return shape satisfies never;
  }
}
```

## Prefer Interfaces for Objects
Use `interface` for public API object shapes (better error messages, declaration merging, extends):

```typescript
interface User {
  readonly id: string;
  name: string;
  email?: string;
}

interface AdminUser extends User {
  role: "admin";
  permissions: readonly string[];
}
```

Use `type` for unions, intersections, mapped types, and utility aliases.

## Additional Patterns
- Use `as const` for literal inference on enums and config objects
- Prefer `Record<K, V>` over index signatures `{ [key: string]: V }`
- Use `unknown` instead of `any` for values of uncertain type
- Use `zod` or `io-ts` for runtime validation of external data