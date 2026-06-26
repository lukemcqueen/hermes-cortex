# Echo Korean — E2E Testing Patterns

## Overview

E2E tests use Playwright and run against the Docker stack (`./run up`). Tests live in `apps/web/e2e/`.

## When to Create E2E Tests

Add Playwright tests alongside any feature that:
- Introduces new user-facing pages or routes
- Modifies critical flows (auth, reading, review, missions, settings)
- Changes navigation or page structure

## Test Structure

Each test file covers one flow and is self-contained:

```typescript
import { test, expect } from '@playwright/test';

test.describe('Flow Name', () => {
  test('specific behavior', async ({ page }) => {
    // Arrange — navigate, fill forms
    // Act — click, submit
    // Assert — verify URL, content, toast
  });
});
```

Keep each test independent — no shared state between tests in different describe blocks.
Do NOT import helper modules from `./helpers` — keep tests self-contained with `page.goto()`, `page.fill()`, `page.click()`, and `expect()`.

## Patterns

**Auth:**
- Create test users via direct API calls in `test.beforeAll`
- Clean up in `test.afterAll` (delete test user)
- Use unique emails via `Date.now()` to avoid conflicts

**Reading/Review:**
- Sign in first in `test.beforeEach`
- Navigate to the page with `page.goto()`
- Wait for content with `page.waitForSelector()` or `page.getByText()`
- Check navigation with `expect(page).toHaveURL()`

**Optional elements:**
- Use try/catch via `.catch(() => false)` for elements that may not appear
- Use `{ timeout: 10000 }` on slow-loading assertions

## Config

- Base URL: `http://localhost:15501` (from playwright.config.ts)
- The built-in webServer in playwright.config.ts is disabled — Docker stack must be running
- Only chromium is configured as the browser target

## Verification

```bash
cd apps/web
npx playwright test --list                    # verify all tests parse (no Docker needed)
npx playwright test --reporter=line           # run all (requires Docker stack: ./run up)
npx playwright test --config=playwright.config.ts --list  # also works
```

Always run `--list` after creating new spec files to verify they parse correctly.

## Existing Tests (June 2026)

| File | Tests | Coverage |
|------|-------|----------|
| `smoke.spec.ts` | 2 | home page loads, login page loads |
| `login.spec.ts` | 6 | form elements, empty validation, wrong credentials, valid login, auth guard, rate limit |
| `signup.spec.ts` | 2+ | form elements, validation |
| `content.spec.ts` | 3 | content API responses |
| `auth-flow.spec.ts` | 5 | login valid/invalid, signup valid/mismatch, forgot password |
| `reading-flow.spec.ts` | 4 | study listing, content click, token popover, timed modes |
| `review-flow.spec.ts` | 2 | empty state, grade buttons |
| `dashboard-flow.spec.ts` | 2 | guest view, authenticated stats |
| `missions-chain.spec.ts` | 3 | page load, daily phrase, chain missions |
| `settings-page.spec.ts` | 3 | profile, preferences, sessions |
| `content-flow.spec.ts` | 3 | study, my content, new content |
| `admin-flow.spec.ts` | 4 | dashboard, approvals, users, content |
| `ai-features.spec.ts` | 2 | collapsible sections, AI unavailable message |

**Total: 42+ tests across 13 spec files**
