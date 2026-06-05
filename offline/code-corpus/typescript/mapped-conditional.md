---
language: typescript
tags: [pattern, util]
title: Mapped & Conditional Types
description: keyof, in keyof, mapped type modifiers, conditional extends, infer keyword.
source: reference
---

```typescript
// Mapped type — transform all properties
type Readonly<T> = {
  readonly [K in keyof T]: T[K];
};

type Optional<T> = {
  [K in keyof T]?: T[K];
};

// Mapped type with property filtering
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

interface Person {
  name: string;
  age: number;
}

// { getName: () => string; getAge: () => number }
type PersonGetters = Getters<Person>;

// Conditional type
type IsString<T> = T extends string ? true : false;
type A = IsString<'hello'>; // true
type B = IsString<42>;      // false

// Conditional with infer — extract unwrapped type
type UnwrapPromise<T> = T extends Promise<infer U> ? U : T;
type C = UnwrapPromise<Promise<string>>; // string
type D = UnwrapPromise<number>;          // number

// Recursive conditional — flatten array of arrays
type Flatten<T> = T extends Array<infer U> ? Flatten<U> : T;
type E = Flatten<number[][][]>; // number

// Conditional type with function arguments
type FirstArg<T> = T extends (arg: infer A, ...rest: unknown[]) => unknown ? A : never;
type F = FirstArg<(name: string, age: number) => void>; // string

```
