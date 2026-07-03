---
name: react-best-practices
description: "70+ React & Next.js performance optimization rules from Vercel Engineering — covers waterfalls, bundle size, server/client perf, re-renders, and JS micro-optimizations. Use when writing new components, reviewing code for perf issues, or optimizing data fetching."
version: 1.0.0
author: Titus (incorporating vercel-labs/agent-skills)
metadata:
  tags: [react, nextjs, performance, optimization, vercel]
  source: https://github.com/vercel-labs/agent-skills
---

# React & Next.js Best Practices — Vercel Engineering

**Source:** Vercel Labs agent-skills (MIT). 70+ rules across 8 categories, prioritized by impact.

## When to Apply

- Writing new React components or Next.js pages
- Implementing data fetching (client or server-side)
- Code review for performance issues
- Refactoring existing React/Next.js code
- Optimizing bundle size or load times
- Debugging re-renders or slow interaction

## Rule Categories (by priority)

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Eliminating Waterfalls | CRITICAL | `async-` |
| 2 | Bundle Size Optimization | CRITICAL | `bundle-` |
| 3 | Server-Side Performance | HIGH | `server-` |
| 4 | Client-Side Data Fetching | MEDIUM-HIGH | `client-` |
| 5 | Re-render Optimization | MEDIUM | `rerender-` |
| 6 | Rendering Performance | MEDIUM | `rendering-` |
| 7 | JavaScript Micro-optimizations | LOW-MEDIUM | `js-` |
| 8 | Advanced Patterns | LOW | `advanced-` |

---

## 1. Eliminating Waterfalls (CRITICAL)

**Core principle:** Don't wait for data you don't need yet. Parallelize independent async operations.

### async-parallel — Promise.all() for Independent Operations
When async ops have no interdependencies, execute them concurrently:
```typescript
// INCORRECT — sequential, 3 round trips
const user = await fetchUser()
const posts = await fetchPosts()
const comments = await fetchComments()

// CORRECT — parallel, 1 round trip
const [user, posts, comments] = await Promise.all([
  fetchUser(), fetchPosts(), fetchComments()
])
```

### async-cheap-condition-before-await
Check cheap sync conditions BEFORE awaiting flags/remote values:
```typescript
// INCORRECT
const someFlag = await getFlag()
if (someFlag && someCondition) { ... }

// CORRECT
if (someCondition) {
  const someFlag = await getFlag()
  if (someFlag) { ... }
}
```

### async-defer-await
Move `await` into branches where actually used — don't block before you know you need it.

### async-dependencies
Use `Promise.all` with `Settled` for partial dependencies where some results may fail.

### async-api-routes
Start promises early, await late in API routes. Parallelize independent data lookups.

### async-suspense-boundaries
Use Suspense to stream content. Don't let the wrapper layout wait for data only needed by a subsection:
```typescript
// INCORRECT — entire page blocked
async function Page() {
  const data = await fetchData()
  return <Layout><Content data={data} /></Layout>
}

// CORRECT — layout renders immediately
function Page() {
  return (
    <Layout>
      <Suspense fallback={<Loading />}>
        <DataDisplay />
      </Suspense>
    </Layout>
  )
}
```

**Trade-off:** faster initial paint vs potential layout shift. Choose based on UX priorities.

---

## 2. Bundle Size Optimization (CRITICAL)

**Key insight:** Barrel files and dynamic paths prevent tree-shaking. Direct imports enable smaller bundles.

### bundle-barrel-imports
Import directly, avoid barrel files (`index.ts` that re-exports everything):
```typescript
// INCORRECT — barrel prevents tree-shaking
import { Button, Card } from '@/components'

// CORRECT — direct import enables tree-shaking
import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
```

### bundle-analyzable-paths
Prefer statically analyzable import paths. Dynamic paths (`${...}`) prevent bundlers from finding dependencies.

### bundle-dynamic-imports
Use `next/dynamic` for heavy components not needed on initial render:
```typescript
// INCORRECT — Monaco bundles with main chunk (~300KB)
import { MonacoEditor } from './monaco-editor'

// CORRECT — loads on demand
const MonacoEditor = dynamic(
  () => import('./monaco-editor').then(m => m.MonacoEditor),
  { ssr: false }
)
```

### bundle-defer-third-party
Load analytics, logging, and non-critical third-party scripts after hydration. Use `next/script` with `strategy="afterInteractive"` or `strategy="lazyOnload"`.

### bundle-conditional
Load modules only when the feature is activated. Use dynamic imports inside conditionals.

### bundle-preload
Preload on hover/focus for perceived speed. Listen for user intent signals.

---

## 3. Server-Side Performance (HIGH)

### server-cache-react — React.cache() for Per-Request Deduplication
```typescript
import { cache } from 'react'

export const getCurrentUser = cache(async () => {
  const session = await auth()
  if (!session?.user?.id) return null
  return await db.user.findUnique({ where: { id: session.user.id } })
})
```

**Critical:** `React.cache()` uses `Object.is` (shallow equality) for cache keys. Use primitive arguments, not inline objects:
```typescript
// INCORRECT — always cache miss (new object each call)
const getUser = cache(async (params: { uid: number }) => { ... })
getUser({ uid: 1 })  // Cache miss
getUser({ uid: 1 })  // Cache miss again

// CORRECT — primitive args use value equality
const getUser = cache(async (uid: number) => { ... })
getUser(1)  // Cache hit on second call

// If you must pass objects, use the same reference
const params = { uid: 1 }
getUser(params)
getUser(params)  // Cache hit (same reference)
```

**Next.js note:** `fetch` is auto-deduplicated. Use `React.cache()` for DB queries (Prisma, Drizzle), auth checks, filesystem ops, heavy computations.

### server-cache-lru — Cross-Request LRU Caching
`React.cache()` works within one request. For data shared across sequential requests, use an LRU cache:
```typescript
import { LRUCache } from 'lru-cache'

const cache = new LRUCache({ max: 1000, ttl: 5 * 60 * 1000 })

export async function getUser(id: string) {
  const cached = cache.get(id)
  if (cached) return cached
  const user = await db.user.findUnique({ where: { id } })
  cache.set(id, user)
  return user
}
```

### server-hoist-static-io
Hoist static I/O (fonts, logos, config reads) to module level — runs once, not per request.

### server-no-shared-module-state
Avoid module-level mutable request state in RSC/SSR — it leaks across requests. Use `React.cache()` instead.

### server-serialization — Minimize RSC Boundary Serialization
Only pass fields that the client actually uses. Every non-serializable prop (functions, Dates, Maps) breaks:
```typescript
// INCORRECT — serializes all 50 fields
<Profile user={user} />         // Client needs only name

// CORRECT — serializes 1 field
<Profile name={user.name} />    // Pass primitives only
```

### server-parallel-fetching
Restructure components to parallelize fetches — don't waterfall independent server requests.

### server-after-nonblocking
Use `after()` (Next.js) for non-blocking operations that don't need to block the response (logging, analytics, revalidation).

### server-auth-actions
Authenticate server actions the same way as API routes — don't assume they're automatically secure.

### server-dedup-props
Avoid duplicate serialization in RSC props. If the same data flows to multiple client components, share the prop.

---

## 4. Client-Side Data Fetching (MEDIUM-HIGH)

### client-swr-dedup
Use SWR for automatic request deduplication across components. Configure `dedupingInterval`:
```typescript
const { data } = useSWR('/api/user', fetcher, { dedupingInterval: 2000 })
```

### client-event-listeners
Deduplicate global event listeners — don't register the same listener twice. Clean up in `useEffect` return.

### client-passive-event-listeners
Use `{ passive: true }` for scroll/touch/wheel events to avoid blocking the main thread:
```typescript
element.addEventListener('scroll', handler, { passive: true })
```

### client-localstorage-schema
Version and minimize localStorage data. Add a schema version key for migration. Never store sensitive data.

---

## 5. Re-render Optimization (MEDIUM)

### rerender-memo — Extract Expensive Work into Memoized Components
```typescript
// INCORRECT — computes avatar even when loading
function Profile({ user, loading }: Props) {
  const avatar = useMemo(() => <Avatar user={user} />, [user])
  if (loading) return <Spinner />
  return <div>{avatar}</div>
}

// CORRECT — skips computation when loading
const UserAvatar = memo(function UserAvatar({ user }: { user: User }) {
  return <Avatar user={user} />
})
function Profile({ user, loading }: Props) {
  if (loading) return <Spinner />
  return <UserAvatar user={user} />
}
```

### rerender-defer-reads
Don't subscribe to state that's only used in callbacks — destructure outside the callback instead.

### rerender-derived-state
Subscribe to derived booleans, not raw values. Derive state during render, not in effects.

### rerender-derived-state-no-effect
Never use `useEffect` + `setState` for derived state — compute it during render directly.

### rerender-functional-setstate
Use functional `setState(prev => prev + 1)` for stable callbacks that don't need the state value in deps.

### rerender-lazy-state-init
Pass a function to `useState(() => expensiveComputation())` for expensive initial values.

### rerender-transitions
Use `startTransition` for non-urgent updates (tab switches, filter changes) to keep the UI responsive:
```typescript
import { startTransition } from 'react'
startTransition(() => {
  setQuery(input)
})
```

### rerender-use-deferred-value
Use `useDeferredValue` to defer expensive renders and keep input responsive:
```typescript
const deferredQuery = useDeferredValue(query)
// Show old results while new ones render
const isStale = query !== deferredQuery
```

### rerender-simple-expression-in-memo
Don't memoize simple primitives — `const fullName = `${first} ${last}`` is always fast enough.

### rerender-split-combined-hooks
Split `useEffect` hooks with independent dependencies — don't put unrelated concerns in one effect.

### rerender-move-effect-to-event
Put interaction logic in event handlers, not effects. Effects are for synchronization, not user actions.

### rerender-dependencies
Use primitive dependencies in effects. Objects/arrays change every render — memoize them or destructure.

### rerender-memo-with-default-value
Hoist default non-primitive props outside the component to avoid new references every render.

---

## 6. Rendering Performance (MEDIUM)

### rendering-svg-inline
Inline small SVGs instead of external image files — avoids HTTP requests, enables CSS styling.

### rendering-conditional-render
Prefer conditional rendering (`{show && <Component />}`) over CSS display toggling for components that mount/unmount.

### rendering-hydration-mismatch
Fix hydration mismatches by ensuring server + client render identical HTML. Use `suppressHydrationWarning` only as last resort.

### rendering-resource-hints
Add `<link rel="preload">` / `<link rel="preconnect">` for critical resources. Use Next.js `head` metadata API.

### rendering-script-loading
Use `next/script` with appropriate strategy. Don't block render with render-blocking scripts.

---

## 7. JavaScript Micro-optimizations (LOW-MEDIUM)

### js-early-exit
Use early returns to reduce nesting and avoid unnecessary computation:
```typescript
// INCORRECT
if (isValid) {
  if (isAllowed) {
    return process(data)
  }
}
// CORRECT
if (!isValid) return null
if (!isAllowed) return null
return process(data)
```

### js-hoist-regexp
Hoist regular expressions outside loops/functions — creating them repeatedly wastes GC:
```typescript
// INCORRECT
function clean(str: string) {
  return str.replace(/[^a-z0-9]/gi, '')
}

// CORRECT
const NON_ALPHANUMERIC = /[^a-z0-9]/gi
function clean(str: string) {
  return str.replace(NON_ALPHANUMERIC, '')
}
```

### js-batch-dom-css
Batch DOM reads before writes to avoid layout thrashing. Read all measurements first, then apply changes.

### js-cache-function-results
Use `useMemo` for expensive computations. For non-React code, use `Map`/`WeakMap` as simple caches.

### js-cache-property-access
Cache repeated property accesses in local variables: `const len = arr.length` in loops.

### js-combine-iterations
Combine multiple array iterations into one — `forEach` with multiple operations beats chained `map` + `filter`.

### js-flatmap-filter
Use `flatMap` instead of `.filter().map()`:
```typescript
// INCORRECT — double iteration
items.filter(x => x.active).map(x => x.name)

// CORRECT — single iteration
items.flatMap(x => x.active ? [x.name] : [])
```

### js-index-maps
Use `Map` for lookups instead of `Array.find()` in loops — O(1) vs O(n).

### js-loop-length-cache
Cache array length before loops: `for (let i = 0, len = arr.length; i < len; i++)`.

### js-object-pool
Reuse objects instead of allocating new ones in hot paths. Consider `Object.freeze` for immutable config objects.

### js-parse-int
Prefer `Number()` or `+` over `parseInt` when you don't need radix-based parsing. `parseInt` is slower and has edge cases with strings like `'0x'`.

### js-spread-alternative
Avoid spread in hot paths — `Object.assign(target, source)` is faster than `{ ...target, ...source }`.

### js-string-concat
Use template literals over concatenation. Modern engines optimize them better.

---

## 8. Advanced Patterns (LOW)

### advanced-effect-event-deps
Use `useEffectEvent` (React 19+) to extract non-reactive dependencies from effects — avoid stale closures without including everything in deps.

### advanced-event-handler-refs
Prefer `useRef` for event handlers to avoid re-adding listeners on handler changes:
```typescript
const handlerRef = useRef(handler)
handlerRef.current = handler  // Always latest
useEffect(() => {
  const cb = (e: Event) => handlerRef.current(e)
  window.addEventListener('resize', cb)
  return () => window.removeEventListener('resize', cb)
}, [])  // Stable mount/unmount
```

### advanced-init-once
Initialize expensive computations once with `useRef` or lazy state initialization:
```typescript
const workerRef = useRef<Worker>(null!)
if (!workerRef.current) {
  workerRef.current = new Worker('/worker.js')
}
```

### advanced-use-latest
Use `useLatest` pattern to always access the latest callback value without re-rendering:
```typescript
function useLatest<T>(value: T) {
  const ref = useRef(value)
  ref.current = value
  return ref
}
```

---

## React Compiler Note

If your project has [React Compiler](https://react.dev/learn/react-compiler) enabled, manual memoization with `memo()` and `useMemo()` is not necessary. The compiler automatically optimizes re-renders. Focus on the async/waterfall/bundle rules, which the compiler doesn't address.

---

## Related Skills

- `react-composition-patterns` — component architecture, compound components, state management
- `react-view-transitions` — View Transition API animations
- `web-design-guidelines` — accessibility, UX, performance compliance