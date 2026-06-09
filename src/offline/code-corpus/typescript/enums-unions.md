---
language: typescript
tags: [pattern, util]
title: Enums & Union Types
description: String enums, const enums, discriminated unions, and literal types.
source: reference
---

```typescript
// String enum
enum Direction {
  Up = 'UP',
  Down = 'DOWN',
  Left = 'LEFT',
  Right = 'RIGHT',
}

function move(direction: Direction): void {
  console.log(`Moving ${direction}`);
}

move(Direction.Up);

// Const enum — no runtime overhead, inlined at compile time
const enum Colors {
  Red = '#FF0000',
  Green = '#00FF00',
  Blue = '#0000FF',
}

const red = Colors.Red;

// Literal union type
type Status = 'idle' | 'loading' | 'success' | 'error';

function handleStatus(s: Status): string {
  switch (s) {
    case 'idle': return 'Waiting...';
    case 'loading': return 'Loading...';
    case 'success': return 'Done!';
    case 'error': return 'Failed!';
  }
}

// Discriminated union — tagged with a literal type property
interface Circle { kind: 'circle'; radius: number; }
interface Square { kind: 'square'; sideLength: number; }
type Shape = Circle | Square;

function area(shape: Shape): number {
  if (shape.kind === 'circle') {
    return Math.PI * shape.radius ** 2;
  }
  return shape.sideLength ** 2;
}

```
