---
name: playwright-browser
description: |
  Write, refactor, and debug Playwright E2E tests using stable selectors,
  real user flows, and reliable async handling.

  Triggers when user mentions:
  - "playwright test"
  - "e2e test"
  - "browser automation"
  - "fix flaky test"
  - "ui test"
---

# Playwright Browser

## Purpose
Create, refactor, and debug reliable E2E tests that:
- simulate real user behavior
- avoid flakiness
- validate full application flows

---

## Output (STRICT ORDER)

1. **Code** (test or fix)
2. **Explanation** (≤3 sentences)
3. **Verification** (commands + expected result)

---

## Workflow (STRICT)

1. Identify intent: new test, refactor, or debug
2. Inspect existing tests/selectors first
3. Use stable selectors (role/text/test-id)
4. Model real user flow (navigation → action → assertion)
5. Avoid sleeps; rely on Playwright waiting
6. Make one focused change
7. Run narrow test first
8. Fix failures iteratively

---

## Core Rules

- Tests must reflect real user behavior
- Prefer readability over cleverness
- Keep tests deterministic and isolated
- Never rely on timing hacks (`waitForTimeout`)

---

## Selectors (MANDATORY)

Priority order:

```txt
getByRole → getByText → getByLabel → getByTestId → CSS (last resort)
```

Examples:

```ts
await page.getByRole("button", { name: "Submit" }).click();
await expect(page.getByText("Success")).toBeVisible();
```

### Rules

* Avoid brittle CSS selectors
* Use `data-testid` for complex UI
* Keep selectors stable across UI changes

---

## Test Structure

Standard pattern:

```ts
test("user creates order", async ({ page }) => {
  await page.goto("/orders");

  await page.getByRole("button", { name: "New Order" }).click();
  await page.getByLabel("Item").fill("Book");

  await page.getByRole("button", { name: "Submit" }).click();

  await expect(page.getByText("Order created")).toBeVisible();
});
```

---

## Async + Waiting

Use Playwright’s built-in waiting:

* `expect(...).toBeVisible()`
* `page.waitForURL()`
* `page.waitForResponse()`

Avoid:

```ts
await page.waitForTimeout(1000); // ❌
```

---

## Auth Handling

Use stored auth state when possible:

```ts
test.use({ storageState: "storageState.json" });
```

Rules:

* Avoid logging in every test
* Reuse authenticated sessions
* Keep auth setup separate

---

## Test Isolation

* Tests must not depend on each other
* Reset state where needed
* Use fixtures for setup/teardown

---

## Debugging (MANDATORY FLOW)

When test fails:

1. Read exact error
2. Check selector validity
3. Check visibility/state timing
4. Use debug tools:

   ```bash
   npx playwright test --headed
   npx playwright test --debug
   ```
5. Fix smallest issue
6. Re-run same test

---

## Refactoring Rules

* Extract repeated flows into helpers
* Keep tests ≤50–70 lines
* Group related steps logically
* Avoid over-abstraction

---

## Performance (ENTERPRISE)

* Run tests in parallel where safe
* Avoid unnecessary navigation
* Mock external APIs if needed
* Use retries ONLY for known flake cases

---

## Commands

```bash
npx playwright install
npx playwright test
npx playwright test tests/example.spec.ts
npx playwright test --headed
npx playwright test --debug
```

---

## Verification Order

```txt
single test
→ test file
→ full suite
```

---

## Anti-Patterns

Avoid:

* `waitForTimeout`
* brittle CSS selectors
* testing implementation details
* overly long tests
* repeated login flows
* ignoring failures
* guessing fixes without rerun

---

## Examples

User: "fix this flaky playwright test"

→ identify selector/timing issue, fix minimal cause, rerun test

---

User: "write e2e test for checkout"

→ create user-flow test with stable selectors + assertions

---

## Goal

Produce stable, readable, user-focused E2E tests that:

* pass consistently
* are easy to debug
* work reliably with smaller models