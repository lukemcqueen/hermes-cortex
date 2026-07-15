# fake-indexeddb Polyfill for Dexie/IndexedDB Tests (jsdom)

## Problem

Vitest runs in a Node.js jsdom environment. jsdom does NOT implement IndexedDB. Any code that uses `import Dexie from 'dexie'` will crash with `ReferenceError: indexedDB is not defined`.

## Solution: fake-indexeddb

`fake-indexeddb` is a pure-JS implementation of the IndexedDB API that works in any Node.js environment. It's a drop-in replacement — Dexie doesn't know the difference.

### Setup

```bash
pnpm add -D fake-indexeddb
```

### Vitest Setup File

Create `apps/web/src/test-setup.ts` (or add to existing one):

```typescript
import "fake-indexeddb/auto";

// This polyfills:
//   window.indexedDB
//   window.IDBIndex
//   window.IDBCursor
//   window.IDBObjectStore
//   window.IDBRequest
//   window.IDBTransaction
//   window.IDBKeyRange
//   window.IDBDatabase
//   window.IDBVersionChangeEvent
```

Configure in `vitest.config.ts`:

```typescript
export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

### Test Pattern

```typescript
import Dexie from "dexie";
import "fake-indexeddb/auto";

describe("Offline Database", () => {
  let db: Dexie;

  beforeEach(() => {
    // Create a fresh in-memory DB for each test
    db = new Dexie("TestDB");
    db.version(1).stores({
      items: "++id, name, category",
    });
  });

  afterEach(() => {
    db.close();
  });

  it("should store and retrieve items", async () => {
    await db.table("items").add({ name: "test", category: "A" });
    const items = await db.table("items").toArray();
    expect(items.length).toBe(1);
    expect(items[0].name).toBe("test");
  });
});
```

### Clearing DB Between Tests

Each `new Dexie("TestDB")` with the same name shares data (same storage key). To isolate tests:

```typescript
// Option 1: Use different DB names per test
beforeEach(() => {
  db = new Dexie(`TestDB_${Math.random().toString(36).slice(2)}`);
});

// Option 2: Delete all data before each test
beforeEach(async () => {
  await db.delete();
  db = new Dexie("TestDB");
  db.version(1).stores({ items: "++id, name" });
});
```

### When to Use

- Tests for Dexie-based offline DB schemas
- Tests for IndexedDB-dependent sync modules
- Tests for PWA components that read/write to IndexedDB
- Any Vitest test importing a module that does `import Dexie from 'dexie'`

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `ReferenceError: indexedDB is not defined` | fake-indexeddb not imported | Add `import "fake-indexeddb/auto"` in setup file or test file before any Dexie import |
| `Dexie is not a constructor` | Wrong import | Use `import Dexie from "dexie"` not `import { Dexie } from "dexie"` |
| `Cannot find module 'fake-indexeddb/auto'` | Package not installed | `pnpm add -D fake-indexeddb` |
