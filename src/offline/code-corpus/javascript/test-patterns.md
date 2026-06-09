---
language: javascript
tags: [test, pattern]
title: Test Patterns
description: Jest/Vitest: describe, it, expect matchers, mocks, and snapshots.
source: framework
---

```javascript
// math.js
export const add = (a, b) => a + b;
export const fetchUser = async (id) => {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error('Not found');
  return res.json();
};

// math.test.js
import { describe, it, expect, vi } from 'vitest';
import { add, fetchUser } from './math.js';

describe('add()', () => {
  it('adds two numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  it('handles negatives', () => {
    expect(add(-1, -2)).toBe(-3);
  });

  it('is not NaN for strings', () => {
    expect(add('a', 1)).toBeNaN();
  });
});

describe('fetchUser()', () => {
  it('returns user data', async () => {
    const mock = vi.fn().mockResolvedValue({ id: 1, name: 'Alice' });
    global.fetch = mock;

    const user = await fetchUser(1);
    expect(user.name).toBe('Alice');
    expect(mock).toHaveBeenCalledWith('/api/users/1');
  });

  it('throws on error', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false });
    await expect(fetchUser(2)).rejects.toThrow('Not found');
  });
});

// Snapshot test
it('matches snapshot', () => {
  const output = JSON.stringify({ a: 1, b: 2 });
  expect(output).toMatchSnapshot();
});

```
