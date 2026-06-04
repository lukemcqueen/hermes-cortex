---
name: nextjs-app-router
description: |
  Build, refactor, and test Next.js App Router code using Server Components,
  route handlers, typed validation, and minimal client-side JavaScript.

  Triggers when user mentions:
  - "nextjs app router"
  - "server component"
  - "client component"
  - "route handler"
  - "server action"
  - "nextjs refactor"
---

# Next.js App Router

## Purpose
Create, refactor, and test production-ready Next.js App Router code.

Use:
- Server Components by default
- Client Components only for interactivity
- typed validation at boundaries
- small, verifiable changes

---

## Output (STRICT ORDER)

1. **Code**
2. **Explanation** (≤3 sentences)
3. **Tests / Verification**

---

## Workflow (STRICT)

1. Identify intent: feature, bug, refactor, test, or performance
2. Inspect relevant routes/components first
3. Prefer Server Components
4. Add `"use client"` only when required
5. Validate all external input
6. Make one coherent change
7. Run narrow verification first
8. Then run broader checks

---

## Architecture Rules

### Server Components
- Default choice
- Fetch data here when possible
- Do not use browser-only APIs
- Keep rendering logic simple

### Client Components
Use only for:
- state
- effects
- event handlers
- browser APIs
- interactive UI

Keep client components small.

### Route Handlers
Use for API boundaries.

Rules:
- validate input
- return explicit status codes
- avoid business logic inside handler
- move complex logic to `lib/` or `services/`

### Server Actions
Use for form mutations when appropriate.

Rules:
- validate inputs
- check auth/permissions
- handle errors safely
- revalidate paths/tags when needed

---

## Data + State

- Keep data fetching close to route/page
- Avoid duplicate fetches
- Use caching intentionally
- Use `revalidatePath`, `revalidateTag`, or `no-store` deliberately
- Do not expose secrets to client code

---

## File Patterns

```txt
app/
  route/
    page.tsx
    loading.tsx
    error.tsx
    not-found.tsx
    actions.ts
    route.ts
components/
lib/
services/
types/
tests/
```

---

## Testing Rules

Use project’s existing test stack.

Prefer:

* unit tests for pure logic
* integration tests for route handlers/actions
* E2E tests for critical user flows

Cover:

* success case
* failure case
* edge case

---

## Refactoring Rules

* Preserve behavior first
* Remove duplication before adding abstraction
* Keep components small
* Extract pure logic to `lib/`
* Extract business logic to `services/`
* Avoid unrelated rewrites

---

## Security Rules

* Validate all input at server boundaries
* Never trust client data
* Never expose env secrets to client
* Check auth before mutations
* Avoid leaking stack traces/errors

---

## Performance Rules

* Prefer Server Components
* Minimize client JavaScript
* Use dynamic imports for heavy client code
* Add `loading.tsx` for slow routes
* Add `error.tsx` for recoverable route errors
* Avoid unnecessary waterfalls

---

## Commands

```bash
npm run dev
npm run build
npm run lint
npm run typecheck
npm test
```

Use the repo’s package manager if different:
`pnpm`, `yarn`, or `bun`.

---

## Verification Order

```txt
narrow test
→ related test file
→ typecheck
→ lint
→ build
→ full test suite
```

---

## Anti-Patterns

Avoid:

* unnecessary `"use client"`
* data fetching in client components without need
* business logic in route handlers
* unvalidated request bodies
* exposing server secrets
* large component rewrites
* skipping build/typecheck

---

## Examples

User: "refactor this Next.js page"

→ preserve behavior, move logic to server/lib/service, verify.

User: "add a route handler"

→ validate request, use service, return typed response, test success/failure.

---

## Goal

Produce small, typed, secure, test-verified Next.js App Router changes that work well with OpenCode and smaller models.