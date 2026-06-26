# Full-Stack Feature Workflow (acme-royalty)

> **NOTE:** This reference covers the **acme-royalty** project. For **acme-works** (this project), see [`acme-works-page-build-workflow.md`](./acme-works-page-build-workflow.md) — different i18n system (React Context vs next-intl), API path conventions, admin router registration, and sidebar architecture.

Workflow for adding a complete feature across both backend (FastAPI) and frontend (Next.js) layers in the acme-royalty pnpm monorepo.

## Phase 0: PRD Gap Analysis (before any new work)

Before building new features, run the PRD gap analysis to identify what already exists and what needs to change:

1. **Enumerate** all PRD requirements (FRs and NFRs)
2. **Scan** the actual codebase for existing implementations, naming, and architecture fit
3. **Map** existing code to PRD requirements — identify architecture, infrastructure, content, and naming gaps
4. **Categorize** gaps into dependency-ordered epics (Foundation → Port → Refactor → Auth → Infra → New Features)
5. **Consolidate** the gap matrix into a story set

See `references/prd-gap-analysis-methodology.md` for the full methodology.

Skip this phase when adding a small feature to an already-aligned architecture; use it when migrating stacks, updating architecture, or after a major PRD revision.

## Execution Mode

**Default mode (sequential):** Backend first, then frontend. Follow the golden sequence below.

### Parallel: 2-agent split (backend + frontend)

For standalone features with clear API contracts (admin CRUD, settings pages, independent views), dispatch 2 subagents simultaneously — one for backend, one for frontend. See subagent-driven-development skills Parallel Workstreams section. Verify integration after both complete.

### Multi-feature parallel (3+ independent features)

For a batch of independent features where each has its own backend + frontend, delegate all at once via delegate_task(tasks=[...]):

"""
delegate_task(tasks=[
    {"goal": "Feature A: Admin approval queue", ...},
    {"goal": "Feature B: CSV import", ...},
    {"goal": "Feature C: Dashboard", ...},
])
"""

Requirements for safe parallel dispatch:
1. Each subagent writes to disjoint files — own router file, own test file, own page file(s)
2. Identify shared conflict files before delegating — pyproject.toml, locales/*.json, routes/index.tsx, main.py. These need one owner or a post-merge fix.
3. Mark pyproject.toml as shared — if two subagents add different dependencies, verify both made it in after completion. Run uv lock or reinstall after merging.
4. i18n keys — specify the exact key list to all subagents upfront. Diff locale files after completion for orphans.
5. Route registration — each subagent adds its own include_router(...) to main.py (different lines, no conflict). Verify all routes exist after merge.

## Golden Sequence

```
Backend: Model → Migration → Router + Tests → Register in main.py
Frontend: Types → API Functions → Page → i18n → NavBar → Tests
Verify: Full test suites (API + Web), zero regressions
```

## Backend Layer (`apps/api/`)

Follow the existing `references/backend-api-feature-workflow.md` for:
- DB model in `db/models.py` (SQLAlchemy 2.x MappedAsDataclass style)
- Alembic migration in `alembic/versions/`
- Router in `routers/<name>.py`
- Test in `tests/test_<name>.py`
- Register in `main.py` with `app.include_router(...)`

### Running API tests

```bash
cd apps/api
.venv/bin/python -m pytest tests/test_<name>.py -xvs        # single file
.venv/bin/python -m pytest tests/ -v --tb=no                 # full suite (regression check)
```

If no `.venv` exists:
```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### Key patterns

- **SQLAlchemy test seeding**: Create a session from `conftest.test_engine`, use `try/finally { session.close() }`
- **Variance breakdown columns**: Add fine-grained variance fields to the report model (`bank_fees`, `failed_payments`, `timing_differences`, `unexplained_variance`)
- **CSV/JSON export**: Use `Response(content=csv_str, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=..."})` — note FastAPI appends `; charset=utf-8` to media_type
- **One-shot certify**: Check `report.status == "certified"` and return 422 if already certified — prevents double-certify
- **Deprecation**: Use `Query(pattern="...")` not `Query(regex="...")` for FastAPI 0.136+
- **UploadFile requires python-multipart**: If a router endpoint uses `fastapi.UploadFile` or `fastapi.Form`, add `python-multipart` to pyproject.toml dependencies. FastAPI does not include it by default. Symptom: `RuntimeError: Form data requires "python-multipart"` at the first POST with file upload. Subagents often miss this — verify after delegation.

## Cross-Cutting: Frontend Auth

### Next.js (acme-royalty)

All API calls go through `fetchJSON()` which auto-attaches JWT Bearer tokens. See the `nextjs-frontend-auth` skill for:
- AuthProvider — React context for login/logout/session restore
- AuthGuard — page-level auth redirect guard
- Login page — email/password form with redirect param support
- Token refresh on 401 — transparent retry
- **Post-login redirect pattern** — auto-expire redirects to `/login?redirect=<path>`; after login, returns to the referring page. See `references/frontend-auth-redirect-pattern.md` for the four-touchpoint implementation guide.
- Test mock patterns for auth

Create the login page and wire up AuthProvider before building feature pages that need auth.

### React SPA — Vite + React Router (acme-live, acme-license)

Projects using Vite + React Router + i18next (not Next.js) use this pattern:

- **AuthProvider** in `lib/auth.tsx` — React context with `useAuth()` hook exposing `{ user, login, register, logout, loading }`
- **API client** in `lib/api.ts` — plain `fetch` wrapper that reads JWT from `localStorage` and sets `Authorization: Bearer {token}` header
- **React Router** — routes defined in `routes/index.tsx` with `<AuthProvider>` wrapping the router in `App.tsx`
- **i18next** — `react-i18next` + `i18next-browser-languagedetector`, locale stored in `localStorage`, default `'ko'`
- **Layout** — `layout.tsx` wraps `<Outlet>` with auth-aware nav: shows user name + sign out when authenticated, login link when not

```typescript
// lib/auth.tsx — AuthProvider + useAuth hook
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (token) fetchUser(token).then(setUser).finally(() => setLoading(false));
    else setLoading(false);
  }, []);

  return <AuthContext value={{ user, loading, login, register, logout }}>{children}</AuthContext>;
}

// lib/api.ts — auto-injects JWT on every request
export async function api(path: string, options?: RequestInit): Promise<Response> {
  const token = localStorage.getItem('kc-live-token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...options?.headers as any };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(import.meta.env.VITE_API_BASE + path, { ...options, headers });
}
```

Key differences from Next.js:
- No `next/navigation`, no App Router, no `next-intl`
- API base URL from `VITE_API_BASE` env var or Vite proxy (`/api` → `http://localhost:13601`)
- Route components imported in `routes/index.tsx` and rendered via `createBrowserRouter`
- i18next files in `lib/locales/{ko,en}.json` with flat key structure per domain

## Frontend Layer (`apps/web/`)

Follow this exact order:

### 1. TypeScript Types (`apps/web/src/lib/api-types.ts`)

Add interfaces at the bottom of the file under a section comment:
```typescript
// ── <Feature Title> ─────────────────────────────────────

export interface FeatureItem {
  // fields matching the API response (snake_case)
}
```

- All snake_case field names matching the Python API response
- nullable fields: `field: string | null`
- Monetary amounts as `number` (the API returns the raw int; `Intl.NumberFormat` handles display)

### 2. API Functions (`apps/web/src/lib/api.ts`)

Add functions at the bottom under a section comment:
```typescript
// ── <Feature Title> ─────────────────────────────────────

export function listFeatureItems(): Promise<{ items: FeatureItem[] }> {
  return fetchJSON('/feature/items');
}
```

- Import the new types at the top of the file
- Use `fetchJSON(...)` with query params via `URLSearchParams`
- For POST with body: `fetchJSON(path, { method: 'POST', body: JSON.stringify({...}) })`
- For download links: create a URL builder function that returns the full URL with `NEXT_PUBLIC_API_URL`
- Export download links as `export*Url(...)` functions returning strings (for `<a href>`)

### 3. Page Component (`apps/web/src/app/[locale]/<feature>/page.tsx`)

Use this template:
```typescript
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { ...api functions } from '../../../lib/api';
import type { ...types } from '../../../lib/api-types';

const KRW = (n: number) =>
  new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }).format(n);

export default function FeaturePage() {
  const t = useTranslations('FeatureName');
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.split('/')[1];

  // State, effects, handlers...

  return (
    <div className="max-w-[1120px] mx-auto px-4 py-6">
      ...
    </div>
  );
}
```

Key patterns:
- **Period/entity selector**: Use `<select>` driven by searchParams — changing selection calls `router.push()` to update the URL
- **Data loading**: `useCallback` + `useEffect` pattern, keyed on searchParams values
- **Summary cards**: Grid layout, conditional color variant (ok/warn/err)
- **Variance breakdown**: Grid of cards, conditionally rendered when variance > 0
- **Detail table**: Overflow-x-auto wrapper, column header patterns matching other pages, status badges with color classes
- **Pagination**: Previous/Next buttons with searchParams updates
- **Modals**: Fixed overlay with centered card, two action buttons
- **Export links**: Plain `<a href>` pointing to the export URL builder, styled as buttons

### 4. i18n Messages

**Two i18n architectures exist across ACME projects. Know which one the project uses before writing code.**

#### Pattern A: next-intl (acme-royalty, acme-platform)

Uses `next-intl` library with URL-based locale routing (`/[locale]/` prefix), `messages/en.json` and `messages/ko.json` files, and `useTranslations()` hook. See `references/nextjs-standalone-docker-patterns.md` for details.

Edit both files:

**`apps/web/messages/en.json`**:
```json
{
  "FeatureName": {
    "title": "...",
    "subtitle": "...",
    ...
  }
}
```

**`apps/web/messages/ko.json`** — add Korean translations matching the same structure.

Also add the Nav link:
```json
"Nav": {
  "reconciliation": "Reconciliation",
  ...
}
```

#### Pattern B: React Context (acme-license)

Uses `LanguageProvider` React Context with `useTranslation()` hook — no URL prefix, no next-intl. Locale stored in `localStorage('acme-locale')`, default `'ko'`. Translation files in `src/lib/i18n/translations/{ko,en}.json`. Type-safe key constants in `translations.ts`.

```typescript
'use client';
import { useTranslation } from '@/lib/i18n';
const { t } = useTranslation();
return <h1>{t('home.hero.title')}</h1>;
```

Edit both translation files to add new keys (must match exactly between ko.json and en.json):

```
apps/web/src/lib/i18n/translations/ko.json
apps/web/src/lib/i18n/translations/en.json
```

**LanguageSwitcher** component is available at `@/components/LanguageSwitcher`. It's already placed in the root layout.

**Key rule:** Every user-visible string must use `t('key')` — no hardcoded text. All translations must have matching keys in both ko.json and en.json (i18n tests enforce this).

### 5. NavBar (Sidebar)

The app uses a vertical sidebar, not a horizontal nav bar. See `references/sidebar-navigation.md` for the full architecture.

Adding a new link:
1. Add the link to the appropriate section array in `app/[locale]/NavBar.tsx`
2. Add i18n key in `messages/en.json` and `messages/ko.json` under `Nav` namespace
3. Active detection is automatic via `isActive()`

### 6. Page Tests (`apps/web/src/app/[locale]/<feature>/__tests__/page.test.tsx`)

Use this test pattern:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import FeaturePage from '../page';

const mockRouter = { push: vi.fn() };
const mockSearchParams = { get: vi.fn(), entries: vi.fn() };

vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
  usePathname: () => '/en/<feature>',
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => {
    const m: Record<string, string> = { /* full translation key map */ };
    return m[key] || key;
  },
}));

vi.mock('../../../../lib/api', () => ({
  listFeatureItems: vi.fn(),
  // ...
}));

import { listFeatureItems } from '../../../../lib/api';

beforeEach(() => { vi.clearAllMocks(); mockSearchParams.get.mockReturnValue(null); });

it('renders title', async () => {
  (listFeatureItems as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockData);
  render(<FeaturePage />);
  await waitFor(() => expect(screen.getByText('Feature Title')).toBeDefined());
});
```

Key points:
- Mock `next/navigation` for `useRouter`, `useSearchParams`, `usePathname`
- Mock `next-intl` with a complete key→value map (every key the page calls)
- Mock the API module — provide both resolved and rejected paths
- For amounts rendered via `Intl.NumberFormat`, expect the formatted string like `₩20,000,000`
- Test: title rendering, empty/no-data state, data-loaded state, error state\n- If text appears in multiple elements (e.g. same label in summary card and table heading), use `getAllByText('...').length` instead of `getByText('...')` to avoid "Found multiple elements" errors
- If text appears in multiple elements (e.g. same amount in summary card and table), use `getAllByText().length`

### Running frontend tests

```bash
cd apps/web
pnpm vitest run --reporter=verbose src/app/\\[locale\\]/<feature>/   # single page
pnpm vitest run                                                      # full suite
```

## Next.js Pitfalls in Parallel Subagent Work

When dispatching a parallel frontend subagent (alongside the backend subagent), watch for these:

### Import path depth in nested admin pages

Deeply nested admin pages like `admin/faq/categories/[id]/items/[itemId]/edit/page.tsx` need extra `../../` in relative imports compared to shallow pages:

```
../../../..               # admin/faq/categories/new/page.tsx
../../../../../../..      # admin/faq/categories/[id]/items/[itemId]/edit/page.tsx
```

This is easy to miscount. **Mitigation:** use path aliases (`@/lib/db/queries/...`) in server components. For client components in admin pages that import from `actions.ts`, `lib/api.ts`, or `lib/api-types.ts`, verify the import depth by counting directory levels against a known‑good file.

### Next.js strict typed routes block template literal hrefs

After adding new route pages (e.g. `admin/faq/...`), `.next/types/routes.d.ts` is stale — Next.js hasn't regenerated it yet. Template literal hrefs like `` `/en/admin/faq/categories/${cat.id}/items` `` fail TypeScript with:

```
Type '`/en/admin/faq/categories/${number}/items`' is not assignable to type ... Route
```

**Fix:** run `next build` or `pnpm typecheck` to regenerate route types. The first build after adding routes will take longer but will succeed. After that, the types are correct.

**Prevention:** pre-generate route types before the frontend subagent starts work by running `pnpm typecheck` in the parent session (this creates `.next/types/` if `.next` already exists). Or accept that the subagent will hit this and fix it in the integration check.

### Admin components hardcode `/en/` prefixes

The existing pattern in this project (acme-website) uses hardcoded `/en/admin/...` paths in admin sidebar links and redirects, not dynamic locale routing. When creating new admin pages and components, match this pattern — do not pass `locale` to admin components. The existing `AdminSidebar` hrefs all start with `'/en/admin/...'`.

### React 19 / Next.js 15 / shadcn-ui Build Error Patterns

When parallel subagents create frontend files independently, the integrated build often hits type mismatches and framework-specific errors. Common patterns and fixes:

#### Zod version incompatibility with @hookform/resolvers

**Error:** `Type 'unknown' is not assignable to type 'number | undefined'` when using `z.coerce.number().int().optional()` in a schema passed to `zodResolver`.

**Root cause:** Zod v4 has breaking type changes. `z.coerce.number()` (and other coerce/union/transform chains) infers as `unknown` in certain contexts when used with `@hookform/resolvers` v5.

**Fix:** Pin zod v3 + @hookform/resolvers v4:
```bash
pnpm add zod@3 @hookform/resolvers@4
```
Then use `z.coerce.number().int().min(1).max(86400).optional()` directly (no `z.union` with `z.literal('')` and `.transform`).

#### React 19 useRef requires initial value

**Error:** `Expected 1 arguments, but got 0` on `useRef<ReturnType<typeof setTimeout>>()`.

**Root cause:** React 19 makes the initial value argument required for `useRef` when a type parameter is provided.

**Fix:** `useRef<ReturnType<typeof setTimeout>>(undefined)` — pass explicit `undefined` as initial value.

Scan the codebase for other `useRef<Type>()` patterns before rebuilding (`search_files` for `useRef<`).

#### shadcn/ui Toast ToasterToast type mismatch

**Error:** `Type 'ReactNode' is not assignable to type 'string | undefined'` at the `ADD_TOAST` dispatch in `toast.tsx`.

**Root cause:** The auto-generated shadcn `ToasterToast` type extends `ToastProps` (from `@radix-ui/react-toast`), where `title` is `string | undefined`. But the `toast()` options interface defines `title` as `ReactNode`. Spreading `options` (with `ReactNode` title) into an object typed as extending `ToastProps` (with `string` title) causes the type error.

**Fix:** Define `ToasterToast` independently instead of extending `ToastProps`:
```typescript
type ToasterToast = {
  id: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: ToastActionElement;
  variant?: 'default' | 'destructive' | 'success';
};
```

#### React Hook Form defaultValues type mismatch

**Error:** `Type 'string' is not assignable to type 'number'` on a form default value when the schema has `z.coerce.number()`.

**Root cause:** `z.coerce.number()` produces `number | undefined` in the inferred type. Setting defaultValues with `String(work.duration)` or empty string `''` conflicts.

**Fix:** Pass `number | undefined` default values for coerce-number fields:
```typescript
duration: work?.duration || undefined,
```
Use `valueAsNumber: true` in `register('duration', { valueAsNumber: true })` for type="number" inputs.

#### Verifying the integrated build

After parallel subagent frontend work, run these checks in order:
1. `npx tsc --noEmit` — catch type errors fast (may have false positives from stale `.next/types`)
2. `npx next build` — full compilation + type check + page generation
3. If all routes return 404: clear `.next` cache and rebuild
4. Check for import path mismatches between subagents (one agent's output vs another's imports)

### i18n key drift between parallel agents

When backend and frontend subagents run in parallel, the i18n keys specified in the shared context may not match what the frontend agent actually uses. **Mitigation:** specify the exact key names in both agents' context upfront. After both complete, diff `messages/en.json` and `messages/ko.json` between the start and end of the session to catch orphans.

### Duplicate foundation files in parallel frontend-only splits

When splitting frontend work into parallel subagents (e.g. Agent A = foundation layer, Agent B = feature pages), both agents can independently create **the same foundation files** (api-types.ts, api.ts, auth.tsx, UI components, layout components) if each context includes the full API contract and UI component list. This wastes tokens and produces conflicts.

**Root cause:** each agent interprets "here are the API types and UI components" as a specification to implement, not just a contract to reference.

**Mitigation — contract vs. implementation boundary:**

1. **Define one agent as the foundation owner.** Only Agent A creates api-types.ts, api.ts, auth.tsx, UI components, layout files.
2. **Agent B's context must say explicitly:** "These files already exist in `src/lib/api-types.ts`, `src/lib/api.ts`, `src/components/ui/*` — import from them, do NOT recreate them." Include the exact import paths Agent B should use.
3. **List the import surface explicitly** in Agent B's context so it never needs to guess what's available:

   ```
   Types are in @/lib/api-types (WorkRead, WorkListRead, WorkCreate, WorkUpdate, PaginatedResponse)
   API functions are in @/lib/api (listWorks, getWork, createWork, updateWork, deleteWork)
   UI components are in @/components/ui (Button, Input, Badge, Table, Dialog, Select, Tabs, Toast, Skeleton, Separator)
   Layout is in @/components/layout (AppLayout, Sidebar)
   Auth is in @/lib/auth (useAuth hook returning { user, login, logout, isLoading })
   Utility is in @/lib/utils (cn)
   ```

4. **Verify integration after both complete.** Check that Agent B's imports resolve to the actual files Agent A created. Fix any mismatches in a follow-up pass.

## Verification Checklist

Before marking a story complete:
1. [ ] API tests pass: `.venv/bin/python -m pytest tests/test_<name>.py -xvs`
2. [ ] Web tests pass: `pnpm vitest run --reporter=verbose src/app/\\[locale\\]/<feature>/`
3. [ ] Full API suite passes: `.venv/bin/python -m pytest tests/ -q`
4. [ ] Full web suite passes: `pnpm vitest run`
5. [ ] No new linter warnings
6. [ ] i18n keys match between EN and KO files
7. [ ] Build verified — run `pnpm build` (or `pnpm typecheck`) after patches. The TypeScript Language Server (LSP) shows stale diagnostics after rapid patch operations. Editor squiggles are not the source of truth — the actual build is.
