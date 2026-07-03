# Frontend i18n `t` function pattern (acme-works)

The `t` function from `useI18n()` has a specific signature that differs from `next-intl`/`react-i18next` conventions.

## Signature

```tsx
// Defined in src/lib/i18n.tsx
t: (path: string, params?: Record<string, string | number>) => string
```

- **path**: dot-separated key (e.g. `'contracts.title'`)
- **params** (optional): interpolation values using `{key}` placeholders in the message string

## When passing `t` as a prop

Child components that receive `t` as a prop MUST type it with the full optional `params` param:

```tsx
// WRONG — will cause TS error if the caller passes interpolation params
function EmptyState({ t }: { t: (key: string) => string }) { ... }
// t('documents.no_results_filtered', { query }) → Expected 1 arguments, but got 2

// RIGHT
function EmptyState({ t }: { t: (key: string, params?: Record<string, string | number>) => string }) { ... }
```

## Interpolation mechanism

Messages use `{key}` placeholders. The `t` function does simple string replacement:

```json
{
  "documents": {
    "no_results_filtered": "No results for \"{query}\" in {category}"
  }
}
```

```tsx
t('documents.no_results_filtered', { query: 'test', category: 'contracts' })
// → "No results for \"test\" in contracts"
```

## Vitest mock patterns

When mocking `useI18n()` in tests for components that pass `t` as a prop:

### Basic mock (no interpolation assertions)

```tsx
vi.mock('@/lib/i18n', () => ({
  useI18n: () => ({
    t: vi.fn((key: string) => {
      const map: Record<string, string> = {
        'nav.contracts': 'Contracts',
        'contracts.title': 'Contracts',
      };
      return map[key] ?? key;
    }),
  }),
}));
```

The mock above ignores the 2nd `params` argument (it's a no-op) — the return value just uses the key from the map. This works when tests don't assert on interpolated text.

### Full mock (interpolation assertions)

When tests check for rendered output from `t()` calls with params (e.g., `t('documents.results_count', { count: 17 })` producing `"17 document(s)"`), the mock MUST handle params:

```tsx
vi.mock('@/lib/i18n', () => ({
  useI18n: () => ({
    t: vi.fn((key: string, params?: Record<string, string | number>) => {
      const map: Record<string, string> = {
        'documents.results_count': '{count} document(s)',
        'audit.field_changed_multi': '{count} fields',
        'audit.total_entries': '{count} total entries',
      };
      const val: string = map[key] ?? key;
      if (!params) return val;
      return Object.entries(params).reduce(
        (s, [k, v]) => s.replace(`{${k}}`, String(v)),
        val,
      );
    }),
  }),
}));
```

Common pattern for finding all needed keys: grep the page source file for `t('` calls and add each key to the mock's map.

### Test assertion pitfalls

- `getByText('17')` does EXACT text matching, not substring. To find `"17 document(s)"`, use `getByText(/17/)` (regex) or `getByText('17 document(s)')` (exact).
- `getByText` with string fails when the same text appears in multiple elements (e.g., sidebar link + page title both say "Documents"). Use `getAllByText` with `.length` assertions instead.  
- The `useCurrentLocale()` hook reads from `usePathname()`. Tests that mock `usePathname` must return locale-prefixed paths: `'/ko/works'` not `'/works'`.

## Vitest + next/navigation mock

Component pages that render through `AppLayout` → `Sidebar` need `usePathname` mocked:

```tsx
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => '/current-path',  // always needed with Sidebar
}));
```

Without `usePathname`, Vitest 4.x throws:
`No "usePathname" export is defined on the "next/navigation" mock`

Affects any test rendering a page that uses `AppLayout` (documents, audit, reports, contracts, etc.).
