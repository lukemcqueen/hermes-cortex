# UI Code Review using the hc-party Pattern

The hc-party methodology (risk tiers 🔴/🟡/🟢, trade-off analysis, consistency verification) applies to UI codebases as well as infrastructure/PRDs. This reference documents the adaptation for frontend code.

## When to Use

- After a UI codebase audit or before a major refactor
- When identifying brittleness patterns in React/Next.js components
- Before writing or expanding test coverage
- When the app has drifted from test expectations (tests failing because components changed but tests didn't)

## UI-Specific Risk Categories

### 🔴 Critical — Fix Before Building

| Pattern | Example | Fix |
|---------|---------|-----|
| Dual/duplicate provider definitions | `Providers` exported from both `lib/auth.tsx` and `app/providers.tsx` with different QueryClient creation | Remove duplicate, keep single source in `app/providers.tsx` |
| No ErrorBoundary | Entire app crashes on any render error | Add root `<ErrorBoundary>` in `app/providers.tsx` |
| Effect/Timeout memory leak | `setTimeout` in `useCallback` with no cleanup on unmount | Add `useEffect` return to clear pending timeout via `useRef` |

### 🟡 Medium — Address Before Phase 1

| Pattern | Example | Fix |
|---------|---------|-----|
| Client-side sort on server-paginated data | Sorting `data.items` client-side when data is already paginated (50/page) | Remove client-side sort; move to API query param or add comment documenting limitation |
| Inconsistent debounce timing | 300ms in one component, 200ms in another | Extract shared `useDebounce` hook, consolidate timing |
| Manual date formatting repeated | `toLocaleDateString('ko-KR', ...)` in 5+ components | Extract `formatDate`/`formatDateTime` utility with null/invalid guards |
| Missing `aria-*` attributes | Sidebar active link is purely visual (CSS class only) | Add `aria-current="page"` to active nav links |

### 🟢 Observations

- No loading skeleton for certain pages
- `as any` casts in tests weaken type safety
- Inconsistent data-state patterns (some pages have loading/empty/error, others don't)
- Placeholder auth that needs real API wiring

## Test Failure Diagnosis (Pre-existing)

When a test suite has pre-existing failures (25+ failures in 4 test files, all with "Unable to find element" errors), the root cause pattern is almost always:

1. Page components were refactored to use `t()` from `useI18n()` for strings
2. Test mocks were not updated — they return the raw key or have a small subset of keys
3. Tests look for English text but `t()` returns `'audit.operation_labels.I'` instead of `'Insert'`

**Fix pattern:** Read the actual page source, extract ALL `t()` keys, read `messages/en.json` for actual values, expand the mock. Then adjust test assertions to match actual rendered text (use `getAllByText` for text appearing in both filters and data rows, use regex for substring matching).
