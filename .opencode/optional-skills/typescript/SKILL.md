---
name: typescript
description: |
  Build, refactor, and verify TypeScript code using strict types,
  safe validation boundaries, and compiler-driven checks.

  Triggers when user mentions:
  - "typescript"
  - "type error"
  - "typecheck"
  - "ts refactor"
  - "strict typing"
  - "zod schema"
---

# TypeScript

## Purpose
Create and refactor TypeScript code that is:
- strongly typed
- safe at external boundaries
- easy to change
- verified by compiler/tests

---

## Output (STRICT ORDER)

1. **Code**
2. **Explanation** (≤3 sentences)
3. **Verification** (typecheck/test command)

---

## Workflow (STRICT)

1. Identify changed boundary: UI, API, DB, config, external input
2. Inspect existing types first
3. Prefer existing patterns
4. Make one coherent type-safe change
5. Validate untrusted data
6. Run narrow test/typecheck
7. Fix exact compiler/runtime error only
8. Re-run verification

---

## Core Rules

- Prefer explicit domain types over `any`
- Use `unknown` at untrusted boundaries
- Validate before narrowing
- Avoid unsafe type assertions
- Do not silence errors with `@ts-ignore`
- Keep types close to source of truth
- Use discriminated unions for variant states

---

## Boundary Safety

Treat these as untrusted:

- API responses
- request bodies
- form input
- localStorage/sessionStorage
- env vars
- third-party libraries
- JSON files
- RAG/tool outputs

Pattern:

```ts
function parseInput(input: unknown): DomainType {
  // validate before use
}
```

---

## Preferred Patterns

### Result Type

```ts
type Result<T, E = string> =
  | { ok: true; value: T }
  | { ok: false; error: E };
```

### Discriminated Union

```ts
type LoadState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: string };
```

### Exhaustive Check

```ts
function assertNever(value: never): never {
  throw new Error(`Unexpected value: ${value}`);
}
```

---

## Validation

Use project’s existing validation library when available.

Common choices:

* Zod
* Valibot
* Yup
* custom parser

Rules:

* validate at the edge
* use validated data internally
* never trust casted JSON

---

## Refactoring Rules

* Let compiler guide changes
* Update source-of-truth type first
* Fix one error class at a time
* Avoid broad rewrites
* Preserve runtime behavior unless required
* Add tests for changed behavior

---

## Enterprise Rules

* Model domain concepts explicitly
* Avoid primitive obsession for critical IDs/states
* Keep public API types stable
* Version external contracts when needed
* Avoid leaking internal types across boundaries
* Document intentional unsafe code

---

## Commands

```bash
npm run typecheck
npx tsc --noEmit
npm test
npm run lint
```

Use the repo’s package manager if different:
`pnpm`, `yarn`, or `bun`.

---

## Verification Order

```txt
targeted test
→ typecheck
→ lint
→ full test suite
→ build
```

Run typecheck after:

* type changes
* API boundary changes
* schema changes
* refactors

---

## Anti-Patterns

Avoid:

* `any`
* unsafe `as SomeType`
* `@ts-ignore`
* duplicating types far from schema/API
* over-generic abstractions
* runtime validation missing at boundaries
* fixing compiler errors by weakening types
* changing many unrelated types at once

---

## Final Report

```md
## Result
What changed.

## Files changed
- path: purpose

## Verification
- command: result

## Notes
Risks, blockers, follow-ups.
```

---

## Goal

Produce small, strict, compiler-verified TypeScript changes that are safe for enterprise systems and reliable with smaller models.