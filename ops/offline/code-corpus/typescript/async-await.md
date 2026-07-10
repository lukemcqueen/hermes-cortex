---
language: typescript
tags: [async, pattern, util]
title: Async/Await with Types
description: Typed Promise return values, async error handling, Promise.all typing.
source: pattern
---

```typescript
interface ApiResponse<T> {
  data: T;
  status: number;
  message: string;
}

// Typed async function
async function fetchUser(id: number): Promise<ApiResponse<{ name: string; email: string }>> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

// Typed error handling with async
async function getUser(id: number): Promise<string | null> {
  try {
    const response = await fetchUser(id);
    return response.data.name;
  } catch (err: unknown) {
    if (err instanceof Error) {
      console.error(`Failed to fetch user: ${err.message}`);
    }
    return null;
  }
}

// Promise.all with typed results
async function fetchMultiple(): Promise<[string, number]> {
  const [name, count] = await Promise.all([
    fetchUser(1).then(r => r.data.name),
    Promise.resolve(42),
  ]);
  return [name, count];
}

// Typed async generator
async function* generatePages(max: number): AsyncGenerator<number[], void, unknown> {
  for (let page = 1; page <= max; page++) {
    yield [page]; // simulated page data
  }
}

// Awaited helper — unwrap Promise type
type UserResponse = Awaited<ReturnType<typeof fetchUser>>;

```
