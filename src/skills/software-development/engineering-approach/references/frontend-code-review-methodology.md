# Frontend Code Review Methodology (hc-party adapted)

Adapts the hc-party architecture review pattern (`references/architecture-review-methodology.md`) for **existing frontend codebases** — not new builds but audits of live UI code. Same risk tiers (🔴→🔴→🟡→🟢), same trade-off + ADR style, but the review dimensions are frontend-specific.

## When to Use

- User says "code review the UI" or "audit the frontend"
- Before a major frontend refactor
- When test coverage gaps or brittleness issues are suspected
- After a new page set was built, for quality verification

## Review Dimensions (Frontend)

### Phase 1: Discover & Contextualise

1. Load `engineering-approach` skill
2. Read `references/fullstack-feature-workflow.md` for feature conventions
3. Read `references/frontend-i18n-t-pattern.md` for i18n conventions
4. List `src/__tests__/` to identify test coverage gaps
5. Run the full test suite: `npx vitest run --reporter=verbose`
6. Build-check: `npx tsc --noEmit --pretty`

### Phase 2: Architecture Risk Identification

**🔴 Critical — Must Fix Before Build**

Common frontend 🔴 risks:

| Risk | Signal | Fix |
|------|--------|-----|
| Dual `Providers` | Same component exported from two files with different trees | Remove duplicate; single source in `app/providers.tsx` |
| No ErrorBoundary | No class component with `getDerivedStateFromError` in the tree | Create `lib/error-boundary.tsx`; wrap in root provider |
| Memory leak | `setTimeout`/`setInterval` in hook with no cleanup on unmount | Add `useEffect(() => () => clearTimeout(timer), [])` |
| Duplicate QueryClient | Two places creating QueryClient with different configs | One `QueryClientProvider` in root; share via `useRef` or `useState` |
| API error bleed-through | `fetchJSON` throws raw error text to the user | Create `ApiError` class with user-friendly fallback |

**🟡 Medium — Address Before Phase 1**

| Issue | Signal | Fix |
|-------|--------|-----|
| Client sort on paginated data | `.sort()` on data from server-paginated endpoint | Move sort to API query param |
| Inconsistent debounce | 200ms in one hook, 300ms in another | Extract shared `useDebounce` hook; consolidate |
| Scattered date formatting | `new Date(...).toLocaleDateString('ko-KR', ...)` repeated | Extract `formatDate`/`formatDateTime` utility |
| Missing aria attributes | No `aria-current`, `aria-sort`, `role` on interactive elements | Add `aria-current="page"` to nav links, `aria-sort` to sortable columns |
| Placeholder auth | `login()` creates fake user | Add JSDoc TODO; wire to real endpoint or document clearly |
| `as any` in test mocks | `mockReturnValueOnce({ ... } as any)` | Type mocks properly with `vi.mocked()` and `Partial<>` |
| No loading state | Page renders nothing until data arrives | Add `Skeleton` component loading state |

**🟢 Observations**

- No loading skeleton on certain pages
- Inline styles vs Tailwind utility consistency
- Missing integration tests for user flows (search → filter → paginate)
- Test files with stale/unused mocks

### Phase 3: Coverage Gap Analysis

1. **List all pages in `src/app/`** — ensure each has a test file
2. **List all hooks in `src/hooks/`** — ensure each has a test file
3. **List all lib utilities** — ensure `formatDate`, `cn`, `formatDateTime` have tests
4. **Check for edge cases**:
   - Empty state (no data)
   - Error state (API failure)
   - Loading state (skeleton/spinner)
   - Null fields / missing data
   - Unmount cleanup (timers, subscriptions, EventSource)
   - Fake timers with debounce (use `fireEvent.change` not `userEvent.type` with fake timers)

### Phase 4: Test Patterns (Vitest + RTL)

**Hook tests with debounce (fake timers):**
```tsx
vi.useFakeTimers();
const { result } = renderHook(() => useDebounce(fn, 300));
act(() => { result.current('hello'); });
expect(fn).not.toHaveBeenCalled();
await act(async () => { vi.advanceTimersByTime(300); });
expect(fn).toHaveBeenCalledWith('hello');
vi.useRealTimers();
```

**Component tests with debounce (fake timers + `fireEvent.change`):**
```tsx
vi.useFakeTimers();
render(<SearchInput onChange={fn} />);
fireEvent.change(screen.getByPlaceholderText('Search…'), { target: { value: 'test' } });
vi.advanceTimersByTime(350);
expect(fn).toHaveBeenCalledWith('test');
vi.useRealTimers();
```
> Avoid `userEvent.type` with fake timers — it times out. Use `fireEvent.change` for debounce tests.

**EventSource / SSE tests (mock the global constructor):**
```tsx
let latestInstance: any = null;
class MockEventSource {
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  readyState = MockEventSource.CONNECTING;
  static CONNECTING = 0, OPEN = 1, CLOSED = 2;
  constructor(url: string) { latestInstance = this; }
  close() { this.readyState = MockEventSource.CLOSED; }
  addEventListener() {}
  _open() { this.onopen?.(new Event('open')); }
  _message(data: string) { this.onmessage?.(new MessageEvent('message', { data })); }
  _error() { this.readyState = MockEventSource.CLOSED; this.onerror?.(new Event('error')); }
}
vi.stubGlobal('EventSource', MockEventSource);
```

**ErrorBoundary tests (suppress console.error):**
```tsx
const BadChild = () => { throw new Error('boom'); };
const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
render(<ErrorBoundary><BadChild /></ErrorBoundary>);
expect(screen.getByText('Something went wrong')).toBeInTheDocument();
spy.mockRestore();
```

**`formatDate`/`formatDateTime` tests (null-safe check):**
```tsx
export function formatDate(date: string | null | undefined, ...): string {
  if (!date) return '\u2014';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '\u2014';  // must check, toLocaleDateString doesn't throw
  return d.toLocaleDateString('ko-KR', options);
}
```

### Phase 5: Consistency Verification

Cross-reference these for gaps:

| Dimension | Check |
|-----------|-------|
| Pages vs routes | Every sidebar nav link has a matching route file |
| Hooks vs API types | TypeScript types match actual API response shape |
| i18n keys vs usage | Every `t('...')` call maps to a message key (test with `messages-parity.test.ts`) |
| Loading states | Every page has skeleton/spinner, error state, and empty state |
| Auth requirements | Pages requiring auth have proper `useAuth()` guard |
| Test coverage gaps | List untested files and prioritize by user-facing impact |
| Build errors | `npx tsc --noEmit` passes for production code (test file errors are secondary) |

### Phase 6: Sequential Fix Order

Fix 🔴 risks first (blockers), then 🟡 issues (brittleness), then add tests. Within each tier, fix the dependency chain:

```
🔴 ErrorBoundary → wrap root providers first
🔴 Dual Providers → remove duplicate, then other fixes can depend on the result
🟡 Accessibility → add aria attributes (non-breaking)
🟡 Shared utilities → extract hooks/utils, then migrate consumers
Tests → write after stability fixes land
```

## Verification

Run the full suite after every batch of fixes:
```bash
npx vitest run --reporter=verbose 2>&1 | grep -E 'Test Files|Tests'
# Confirm count hasn't regressed
```
