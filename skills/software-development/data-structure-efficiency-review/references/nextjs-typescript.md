# Next.js / TypeScript / JavaScript structural review

Load only when reviewing TypeScript/JavaScript/Next.js code. Pattern numbers (P1–P16) refer to SKILL.md section 3.

## If you take nothing else

- `.find`/`.some`/`.includes`/`.indexOf`/`.filter(...)[0]` **inside** a `.map`/loop = P1/P2 → build one `Map`/`Set` before the loop.
- Repeated `[...arr]`/`{...obj}` spread, `concat`, or `slice` in loops/reducers = P7.
- A `new Map()` rebuilt on every render/request over unchanged data = P3 — build it once.
- Rebuilding data client-side that the server could shape once = P9/P15.
- Unbounded process-global `Map`/`Set` caches = P10 (Node processes live long).
- JSON round-trip as deep clone in a hot path = P7/P11.
- Next.js already memoizes identical `fetch` requests within a server render pass — do not add an app cache on top.

## Recipes

### P1/P2 — membership and key lookup

```ts
// Before: for every user, scan every role
const rows = users.map((u) => {
  const role = roles.find((r) => r.id === u.roleId);
  return { name: u.name, role: role?.title };
});

// After: Map built once, O(1) lookups
const rolesById = new Map(roles.map((r) => [r.id, r]));
const rows = users.map((u) => {
  const role = rolesById.get(u.roleId);
  return { name: u.name, role: role?.title };
});
```

### P3 — index rebuilt per render / per request

Build at the point where data is fetched. `useMemo` only helps when deps are stable — if parent recreates array every render, `useMemo` recomputes every render too.

### P7 — quadratic spread/concat accumulation

```ts
// Before: each iteration copies the whole array
let acc: Item[] = [];
for (const group of groups) acc = [...acc, ...group.items];

// After: accumulate with push, spread once at the end
const acc: Item[] = [];
for (const group of groups) acc.push(...group.items);
```

### P10 — unbounded caches and retention

Fix: bound + TTL + invalidation; scope to data's true lifetime. `WeakMap` only for object-keyed metadata, not string keys.

### P11 — clone/serialization as copy

`JSON.parse(JSON.stringify(x))` loses types. `structuredClone` is the correct primitive but still O(n). The real fix is not copying at all.

### P15 — client/server data boundary (Next.js)

- Whole records passed to Client Component using two fields → project server-side.
- Server fetches in sequence that are independent → `Promise.all`.
- Large server arrays without pagination → bound them server-side.
- Client re-indexing data the server could deliver shaped → shape once server-side.

### Next.js caching scopes (do not double-cache)

Next.js distinguishes request memoization (auto, request-lifetime) from persistent data caching (cross-request, `revalidate`-controlled). Before recommending a cache: which layer already covers this?

## JavaScript gotchas

- `Map`/`Set` iterate in insertion order; **plain objects do not** (integer-like keys iterate first in numeric order). Replacing one with the other changes iteration order.
- Object keys compare by identity — two structurally equal objects are different keys.
- `.sort()` mutates in place and is stable since ES2019.
- `undefined`-keyed maps conflate absent and present-but-`undefined`.

## Verification commands

- Compare before/after with identical input; assert identical output (order included).
- Node: `--cpu-prof`/`--heap-prof`; Next.js: framework/server timings, DB query metrics, RSC payload bytes.