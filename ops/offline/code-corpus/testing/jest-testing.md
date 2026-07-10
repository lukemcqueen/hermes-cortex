---
language: typescript
tags: [jest, testing, typescript, unit-test]
title: Jest Testing Framework
description: Comprehensive guide to Jest testing including describe/it/expect, mocking (jest.fn, jest.spyOn), snapshot testing, async tests, setup/teardown, coverage, and CI integration
source: pattern
---

# Jest Testing Framework

## Setup and Configuration

```typescript
// jest.config.ts
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: [
    '**/__tests__/**/*.+(ts|tsx|js)',
    '**/?(*.)+(spec|test).+(ts|tsx|js)',
  ],
  transform: {
    '^.+\\.(ts|tsx)$': 'ts-jest',
  },
  
  // Coverage
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/index.ts',
    '!src/types/**',
  ],
  coverageDirectory: 'coverage',
  coverageReporters: ['text', 'lcov', 'clover', 'json'],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
  
  // Module resolution
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@utils/(.*)$': '<rootDir>/src/utils/$1',
    '\\.(css|less|scss)$': '<rootDir>/src/__mocks__/styleMock.js',
  },
  
  // Setup files
  setupFilesAfterSetup: ['<rootDir>/src/setupTests.ts'],
  
  // Performance
  maxWorkers: '50%',
  testTimeout: 30000,
  verbose: true,
};

export default config;
```

## Basic Testing: describe, it, expect

```typescript
import { describe, it, expect, test } from '@jest/globals';

// ─── describe and it blocks ──────────────────────────────────────────────────

describe('Math utilities', () => {
  describe('addition', () => {
    it('should add two positive numbers correctly', () => {
      const result = 2 + 3;
      expect(result).toBe(5);
    });
    
    it('should handle negative numbers', () => {
      expect(-1 + -1).toBe(-2);
      expect(5 + -3).toBe(2);
    });
  });
  
  describe('subtraction', () => {
    test('subtracts correctly', () => {
      expect(10 - 5).toBe(5);
    });
  });
});

// ─── Common Matchers ─────────────────────────────────────────────────────────

describe('Common Jest Matchers', () => {
  // Exact equality
  it('toBe uses Object.is for exact equality', () => {
    expect(1 + 1).toBe(2);
    expect('hello').toBe('hello');
    expect(true).toBe(true);
    expect(null).toBeNull();
    expect(undefined).toBeUndefined();
    expect(null).toBeDefined();
    expect(1).toBeTruthy();
    expect(0).toBeFalsy();
  });
  
  // Object and array equality (deep equality)
  it('toEqual checks deep equality', () => {
    expect({ a: 1, b: 2 }).toEqual({ a: 1, b: 2 });
    expect([1, 2, 3]).toEqual([1, 2, 3]);
    expect({ nested: { value: 'deep' } }).toEqual({ nested: { value: 'deep' } });
  });
  
  // Strict object equality
  it('toStrictEqual is stricter than toEqual', () => {
    expect({ a: 1 }).not.toStrictEqual({ a: '1' });
    expect({ a: undefined }).not.toStrictEqual({});
  });
  
  // Numbers
  it('number matchers', () => {
    expect(0.1 + 0.2).toBeCloseTo(0.3);
    expect(10).toBeGreaterThan(5);
    expect(5).toBeGreaterThanOrEqual(5);
    expect(3).toBeLessThan(5);
    expect(5).toBeLessThanOrEqual(5);
  });
  
  // Strings
  it('string matchers', () => {
    expect('hello world').toMatch(/world/);
    expect('hello world').toMatch('world');
    expect('hello world').toContain('world');
    expect('hello').toHaveLength(5);
  });
  
  // Arrays and iterables
  it('array matchers', () => {
    expect([1, 2, 3]).toContain(2);
    expect([1, 2, 3]).toHaveLength(3);
    expect([1, 2, 3]).toEqual(expect.arrayContaining([1, 3]));
    expect([{ id: 1 }, { id: 2 }]).toContainEqual({ id: 1 });
    expect([1, 2, 3]).not.toContain(4);
  });
  
  // Objects
  it('object matchers', () => {
    const obj = { name: 'Alice', age: 30, role: 'admin' };
    
    expect(obj).toHaveProperty('name');
    expect(obj).toHaveProperty('age', 30);
    expect(obj).toMatchObject({ name: 'Alice' });
    expect(obj).toMatchObject({ name: expect.any(String), age: expect.any(Number) });
    expect(obj).toEqual(
      expect.objectContaining({ name: 'Alice', role: 'admin' })
    );
  });
  
  // Exceptions
  it('exception matchers', () => {
    const throwError = () => { throw new Error('Something went wrong'); };
    
    expect(throwError).toThrow();
    expect(throwError).toThrow(Error);
    expect(throwError).toThrow('Something went wrong');
    expect(throwError).toThrow(/went wrong/);
  });
});
```

## Mocking

```typescript
import { jest, describe, it, expect, beforeEach, afterEach } from '@jest/globals';

// ─── jest.fn() ───────────────────────────────────────────────────────────────

describe('jest.fn()', () => {
  it('creates a mock function', () => {
    const mockFn = jest.fn();
    expect(mockFn).not.toHaveBeenCalled();
    
    mockFn();
    expect(mockFn).toHaveBeenCalled();
    expect(mockFn).toHaveBeenCalledTimes(1);
  });
  
  it('returns a default value', () => {
    const mockFn = jest.fn();
    expect(mockFn()).toBeUndefined();
    
    const mockReturn = jest.fn(() => 'mocked value');
    expect(mockReturn()).toBe('mocked value');
    
    const mockReturn2 = jest.fn().mockReturnValue(42);
    expect(mockReturn2()).toBe(42);
  });
  
  it('mocks implementation', () => {
    const mockAdd = jest.fn((a: number, b: number) => a + b);
    expect(mockAdd(2, 3)).toBe(5);
    expect(mockAdd).toHaveBeenCalledWith(2, 3);
  });
  
  it('tracks calls and arguments', () => {
    const mockFn = jest.fn();
    mockFn('arg1', 'arg2');
    mockFn('arg3');
    
    expect(mockFn).toHaveBeenCalledTimes(2);
    expect(mockFn).toHaveBeenCalledWith('arg1', 'arg2');
    expect(mockFn).toHaveBeenLastCalledWith('arg3');
    expect(mockFn.mock.calls).toEqual([
      ['arg1', 'arg2'],
      ['arg3'],
    ]);
    expect(mockFn.mock.results[0].value).toBeUndefined();
  });
  
  it('mocks return values with chaining', () => {
    const mockFn = jest.fn()
      .mockReturnValueOnce('first')
      .mockReturnValueOnce('second')
      .mockReturnValue('default');
    
    expect(mockFn()).toBe('first');
    expect(mockFn()).toBe('second');
    expect(mockFn()).toBe('default');
    expect(mockFn()).toBe('default');
  });
  
  it('mocks async functions', async () => {
    const mockAsync = jest.fn().mockResolvedValue('async result');
    const result = await mockAsync();
    expect(result).toBe('async result');
    
    const mockReject = jest.fn().mockRejectedValue(new Error('failed'));
    await expect(mockReject()).rejects.toThrow('failed');
  });
  
  it('provides mock implementations with context', () => {
    const mockFn = jest.fn(function(this: any, x: number) {
      return this.value + x;
    });
    
    const context = { value: 10 };
    const result = mockFn.call(context, 5);
    expect(result).toBe(15);
  });
});

// ─── jest.spyOn() ────────────────────────────────────────────────────────────

const database = {
  users: [
    { id: 1, name: 'Alice' },
    { id: 2, name: 'Bob' },
  ],
  
  findUser(id: number) {
    return this.users.find(u => u.id === id);
  },
  
  saveUser(user: { name: string }) {
    const id = this.users.length + 1;
    this.users.push({ id, ...user });
    return id;
  },
  
  async query(sql: string): Promise<any[]> {
    return this.users;
  },
};

describe('jest.spyOn()', () => {
  it('spies on a method without changing implementation', () => {
    const spy = jest.spyOn(database, 'findUser');
    
    const result = database.findUser(1);
    
    expect(result).toEqual({ id: 1, name: 'Alice' });
    expect(spy).toHaveBeenCalledWith(1);
    expect(spy).toHaveReturnedWith({ id: 1, name: 'Alice' });
    
    spy.mockRestore();
  });
  
  it('spies and mocks implementation', () => {
    const spy = jest.spyOn(database, 'findUser')
      .mockImplementation((id: number) => ({ id, name: 'Mocked' }));
    
    const result = database.findUser(99);
    
    expect(result).toEqual({ id: 99, name: 'Mocked' });
    expect(spy).toHaveBeenCalledWith(99);
    
    spy.mockRestore();
  });
  
  it('spies and returns a different value', () => {
    const spy = jest.spyOn(database, 'saveUser')
      .mockReturnValue(999);
    
    const id = database.saveUser({ name: 'Charlie' });
    
    expect(id).toBe(999);
    expect(spy).toHaveBeenCalledWith({ name: 'Charlie' });
    
    spy.mockRestore();
  });
  
  it('spies on getters and setters', () => {
    const obj = {
      _value: 0,
      get value() { return this._value; },
      set value(v: number) { this._value = v; },
    };
    
    const getterSpy = jest.spyOn(obj, 'value', 'get');
    const setterSpy = jest.spyOn(obj, 'value', 'set');
    
    obj.value = 42;
    const val = obj.value;
    
    expect(val).toBe(42);
    expect(getterSpy).toHaveBeenCalled();
    expect(setterSpy).toHaveBeenCalledWith(42);
    
    getterSpy.mockRestore();
    setterSpy.mockRestore();
  });
  
  it('mocks async methods', async () => {
    const spy = jest.spyOn(database, 'query')
      .mockResolvedValue([{ id: 1, name: 'Mocked' }]);
    
    const result = await database.query('SELECT * FROM users');
    
    expect(result).toHaveLength(1);
    expect(spy).toHaveBeenCalledWith('SELECT * FROM users');
    
    spy.mockRestore();
  });
});

// ─── Mocking Modules ─────────────────────────────────────────────────────────

// Mock the entire 'axios' module
jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
  create: jest.fn(),
}));

import axios from 'axios';

describe('Module mocking', () => {
  const mockedAxios = jest.mocked(axios);
  
  it('mocks axios.get', async () => {
    mockedAxios.get.mockResolvedValue({
      data: { id: 1, name: 'Test' },
      status: 200,
    });
    
    const response = await axios.get('/api/users');
    expect(response.data).toEqual({ id: 1, name: 'Test' });
    expect(mockedAxios.get).toHaveBeenCalledWith('/api/users');
  });
});
```

## Snapshot Testing

```typescript
import { describe, it, expect } from '@jest/globals';

// ─── Basic Snapshot ──────────────────────────────────────────────────────────

function generateUserCard(user: { name: string; age: number; role: string }) {
  return {
    displayName: `${user.name} (${user.age})`,
    badge: user.role === 'admin' ? '🔴 Admin' : '🟢 User',
    isActive: true,
    createdAt: new Date('2024-01-01').toISOString(),
  };
}

describe('Snapshot Testing', () => {
  it('should generate user card matching snapshot', () => {
    const user = { name: 'Alice', age: 30, role: 'admin' };
    
    // First run: creates snapshot, subsequent runs compare
    expect(generateUserCard(user)).toMatchSnapshot();
  });
  
  it('should generate multiple user cards', () => {
    const users = [
      { name: 'Alice', age: 30, role: 'admin' },
      { name: 'Bob', age: 25, role: 'user' },
    ];
    
    const cards = users.map(generateUserCard);
    expect(cards).toMatchSnapshot('user-cards-list');
  });
  
  // Inline snapshot (stores directly in the test file)
  it('should work with inline snapshots', () => {
    const result = { status: 'ok', code: 200, message: 'Success' };
    expect(result).toMatchInlineSnapshot(`
      {
        "code": 200,
        "message": "Success",
        "status": "ok",
      }
    `);
  });
});

// ─── Property Matchers for Dynamic Values ────────────────────────────────────

describe('Snapshot Property Matchers', () => {
  it('should handle dynamic values', () => {
    const result = {
      id: Math.random(),
      createdAt: new Date().toISOString(),
      timestamp: Date.now(),
      name: 'Static name',
    };
    
    expect(result).toMatchSnapshot({
      id: expect.any(Number),
      createdAt: expect.any(String),
      timestamp: expect.any(Number),
    });
  });
  
  it('should handle dynamic arrays', () => {
    const results = [
      { id: 1, name: 'First', createdAt: new Date().toISOString() },
      { id: 2, name: 'Second', createdAt: new Date().toISOString() },
    ];
    
    expect(results).toMatchSnapshot([
      { id: expect.any(Number), name: 'First', createdAt: expect.any(String) },
      { id: expect.any(Number), name: 'Second', createdAt: expect.any(String) },
    ]);
  });
});

// NOTE: Update snapshots with:
//   npx jest --updateSnapshot
//   npx jest -u
```

## Async Tests

```typescript
import { describe, it, expect } from '@jest/globals';

// ─── Async/Await ─────────────────────────────────────────────────────────────

async function fetchData(id: number): Promise<{ id: number; name: string }> {
  return { id, name: `User ${id}` };
}

async function fetchWithError(): Promise<never> {
  throw new Error('Network error');
}

describe('Async Tests', () => {
  // Using async/await
  it('should fetch data with async/await', async () => {
    const data = await fetchData(1);
    expect(data.name).toBe('User 1');
  });
  
  // Using resolves
  it('should resolve with correct data', async () => {
    await expect(fetchData(1)).resolves.toEqual({ id: 1, name: 'User 1' });
  });
  
  // Using rejects
  it('should reject with error', async () => {
    await expect(fetchWithError()).rejects.toThrow('Network error');
  });
  
  // Multiple async calls
  it('should handle parallel async calls', async () => {
    const [user1, user2, user3] = await Promise.all([
      fetchData(1),
      fetchData(2),
      fetchData(3),
    ]);
    
    expect(user1.name).toBe('User 1');
    expect(user2.name).toBe('User 2');
    expect(user3.name).toBe('User 3');
  });
  
  // Callback style (avoid when possible)
  it('should work with done callback', (done) => {
    fetchData(1).then(data => {
      expect(data.name).toBe('User 1');
      done();
    }).catch(done);
  });
});
```

## Setup and Teardown

```typescript
import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from '@jest/globals';

// ─── Lifecycle Hooks ─────────────────────────────────────────────────────────

describe('Lifecycle Hooks', () => {
  let counter: number;
  const items: number[] = [];
  
  beforeAll(() => {
    // Runs once before all tests in this describe block
    console.log('💡 beforeAll: setup test suite');
    items.push(0);
  });
  
  afterAll(() => {
    // Runs once after all tests in this describe block
    console.log('💡 afterAll: teardown test suite');
    items.length = 0;
  });
  
  beforeEach(() => {
    // Runs before each test
    counter = 0;
    console.log('• beforeEach: reset counter');
  });
  
  afterEach(() => {
    // Runs after each test
    console.log('• afterEach: cleanup');
  });
  
  it('test 1 - counter starts at 0', () => {
    expect(counter).toBe(0);
    counter += 1;
    expect(items).toEqual([0]);
  });
  
  it('test 2 - counter is reset', () => {
    // Counter was reset by beforeEach
    expect(counter).toBe(0);
  });
});

// ─── Scoped Setup ────────────────────────────────────────────────────────────

describe('Scoped Setup', () => {
  // The toplevel describe scope
  beforeAll(() => {
    console.log('OUTER beforeAll');
  });
  
  beforeEach(() => {
    console.log('OUTER beforeEach');
  });
  
  it('outer test', () => {
    expect(true).toBe(true);
  });
  
  describe('inner describe scope', () => {
    beforeAll(() => {
      console.log('  INNER beforeAll');
    });
    
    beforeEach(() => {
      console.log('  INNER beforeEach');
    });
    
    it('inner test', () => {
      expect(true).toBe(true);
    });
  });
});

// ─── Test Isolation ──────────────────────────────────────────────────────────

describe('Test Isolation', () => {
  // Shared state that gets reset
  let db: Map<number, string>;
  
  beforeEach(() => {
    db = new Map([
      [1, 'Alice'],
      [2, 'Bob'],
    ]);
  });
  
  it('should find Alice', () => {
    expect(db.get(1)).toBe('Alice');
    db.set(3, 'Charlie');
  });
  
  it('should not have Charlie from previous test', () => {
    expect(db.has(3)).toBe(false);
    expect(db.get(1)).toBe('Alice');
  });
  
  it('should have exactly 2 items', () => {
    expect(db.size).toBe(2);
  });
});
```

## Coverage Configuration

```typescript
// package.json (jest config section)
//
// {
//   "jest": {
//     "collectCoverage": true,
//     "coverageThreshold": {
//       "global": {
//         "branches": 80,
//         "functions": 80,
//         "lines": 80,
//         "statements": 80
//       },
//       "./src/components/": {
//         "branches": 90,
//         "functions": 90,
//         "lines": 90,
//         "statements": 90
//       }
//     }
//   }
// }

// Running coverage:
//   npx jest --coverage
//   npx jest --coverage --coverageReporters=text --coverageReporters=lcov
//   npx jest --coverage --collectCoverageFrom='src/**/*.ts' --coverageDirectory=coverage

// CI integration — fail if coverage drops below threshold:
//   npx jest --coverage --ci --coverageThreshold='{"global":{"lines":80}}'
```

## CI Integration

```yaml
# .github/workflows/jest.yml
name: Jest Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        node-version: ['18', '20', '22']
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run Jest tests with coverage
        run: npx jest --ci --coverage --maxWorkers=2
        env:
          CI: true
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          directory: ./coverage/
          flags: jest-${{ matrix.node-version }}
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: jest-results-${{ matrix.node-version }}
          path: |
            coverage/
            junit.xml
          retention-days: 7
```

## Advanced Patterns

```typescript
import { jest, describe, it, expect, beforeEach } from '@jest/globals';

// ─── Timers ──────────────────────────────────────────────────────────────────

describe('Timer Mocks', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });
  
  afterEach(() => {
    jest.useRealTimers();
  });
  
  it('should advance time', () => {
    const callback = jest.fn();
    
    setTimeout(callback, 1000);
    expect(callback).not.toHaveBeenCalled();
    
    jest.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);
  });
  
  it('should run all timers', () => {
    const callback = jest.fn();
    
    setTimeout(callback, 1000);
    setTimeout(callback, 2000);
    setTimeout(callback, 3000);
    
    jest.runAllTimers();
    expect(callback).toHaveBeenCalledTimes(3);
  });
  
  it('should handle interval timers', () => {
    const callback = jest.fn();
    
    setInterval(callback, 100);
    jest.advanceTimersByTime(500);
    
    expect(callback).toHaveBeenCalledTimes(5);
  });
});

// ─── Custom Matchers ─────────────────────────────────────────────────────────

// Extend expect with custom matchers
expect.extend({
  toBeWithinRange(received: number, floor: number, ceiling: number) {
    const pass = received >= floor && received <= ceiling;
    return {
      message: () =>
        `expected ${received} to be within range ${floor} - ${ceiling}`,
      pass,
    };
  },
});

declare module 'expect' {
  interface Matchers<R> {
    toBeWithinRange(floor: number, ceiling: number): R;
  }
}

describe('Custom Matchers', () => {
  it('should use custom matcher', () => {
    expect(5).toBeWithinRange(1, 10);
    expect(15).not.toBeWithinRange(1, 10);
  });
});

// ─── Testing Classes ─────────────────────────────────────────────────────────

class Calculator {
  protected history: number[] = [];
  
  add(a: number, b: number): number {
    const result = a + b;
    this.history.push(result);
    return result;
  }
  
  getHistory(): number[] {
    return [...this.history];
  }
  
  clear(): void {
    this.history = [];
  }
}

describe('Calculator class', () => {
  let calc: Calculator;
  
  beforeEach(() => {
    calc = new Calculator();
  });
  
  it('should add numbers', () => {
    expect(calc.add(2, 3)).toBe(5);
  });
  
  it('should track history', () => {
    calc.add(1, 1);
    calc.add(2, 2);
    expect(calc.getHistory()).toEqual([2, 4]);
  });
  
  it('should clear history', () => {
    calc.add(1, 1);
    calc.clear();
    expect(calc.getHistory()).toEqual([]);
  });
});
```