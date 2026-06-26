# ACME Works — Fullstack Page Build Workflow

Specific patterns for building new pages in the **acme-works** project (FastAPI + Next.js 15 App Router).

This is distinct from the general `fullstack-feature-workflow.md` which documents acme-royalty patterns. ACME Works has its own i18n, auth, layout, and router conventions.

## i18n Layer

ACME Works uses React Context i18n, not next-intl:

```typescript
import { useI18n } from '@/lib/i18n';
const { t } = useI18n();
// t('admin.api_keys.title')  — dot-notation, no namespaces
```

Files:
- `apps/web/messages/en.json`
- `apps/web/messages/ko.json`

Both must have matching keys. Add new keys before the `shortcuts` section (end of file). Use `\u2026` for ellipsis chars in JSON.

Sidebar nav keys go under `nav`:
```json
"nav": {
  "api_keys": "API Keys",
  ...
}
```

## API Client

All calls go through `fetchJSON()` in `apps/web/src/lib/api.ts`.

**Path convention differs by route group:**
- Admin routes: `/admin/api-keys`, `/admin/users` (no `/api/v1` prefix)
- Publisher routes: `/api/v1/publisher/me/dashboard` (has `/api/v1` prefix)
- Search: `/search?q=...` (no prefix)

## Backend Router Registration (admin pages)

1. Create schema in `apps/api/app/schemas/admin_<name>.py`
2. Create router in `apps/api/app/routers/admin/<name>.py`
   - Router prefix: `/admin/<name>`
   - Admin endpoints must NOT use `/api/v1` prefix — the router sets its own
3. Register in `apps/api/app/main.py`:
   ```python
   from app.routers.admin.<name> import router as admin_<name>_router
   app.include_router(admin_<name>_router, prefix="/api")
   ```

## Admin Page Build Sequence (e.g. api-keys)

```
1. Schema:     apps/api/app/schemas/admin_api_key.py
2. Router:     apps/api/app/routers/admin/api_keys.py
3. Register:   apps/api/app/main.py (import + include_router)
4. API client: apps/web/src/lib/api.ts (section comment + functions + types)
5. i18n:       apps/web/messages/{en,ko}.json (sidebar nav key + page keys)
6. Sidebar:    apps/web/src/components/layout/sidebar.tsx (NAV_GROUPS)
7. Page:       apps/web/src/app/[locale]/admin/api-keys/page.tsx
```

### Partial-build scenario: steps 1-6 already done, only page missing

In larger feature batches, steps 1-6 (backend + API client + i18n + sidebar) are often completed in one session, then the frontend page component (step 7) is deferred.

**How to detect:** The import `from app.routers.admin.<name> import router` exists in `main.py`, the API functions exist in `api.ts`, the i18n keys exist under `admin.<name>.*`, and the sidebar has a nav entry — but `apps/web/src/app/[locale]/admin/<name>/page.tsx` is either empty or doesn't exist (the directory might exist but only `page.tsx` is missing).

**Build pattern when only the page is missing:**
1. Read the API types (`api.ts`) — types are inlined in the section, not imported from `api-types.ts`
2. Read the i18n keys (`en.json` under `admin.<name>.*`) — all labels are already defined
3. Copy the admin/users page pattern — same `AppLayout`, `useQuery`, `useI18n`, pagination pattern
4. Verify the <Select> user filter works with `listAdminUsers` (queried inline, not a dedicated hook)
5. Prune unused imports (see Import Cleanup above)
```

## Publisher Portal Page Build Sequence (e.g. royalties)

1. Backend endpoint: `apps/api/app/routers/publisher_portal.py`
   - Publisher identity via `current_user.publisher_id` — always check with `cast(uuid.UUID | None, ...)`
   - Share data comes from `WorksContractShare` (not `Contract` — Contract has no `work_id` column)
   - The model `WorksContractShare` has `publisher_id`, `work_id`, `contract_id`, `rights_type`, `share`
2. API client: `apps/web/src/lib/api.ts`
3. i18n: `apps/web/messages/{en,ko}.json` under `publisher.royalties.*`
4. Sidebar: `apps/web/src/components/layout/sidebar.tsx` — add to publisher group
5. Page: `apps/web/src/app/[locale]/publisher/royalties/page.tsx`

## Search Page Pattern

The global search (`Cmd+K`) palette lives in `apps/web/src/components/layout/global-search.tsx`. The dedicated search results page is at `/search`.

To add "View all results" navigation from Cmd+K to the full page:

1. Update `apps/web/src/hooks/use-search.ts` — expose `query` from the hook
2. Update `global-search.tsx`:
   - Add `handleViewAll` callback → `router.push(\`/search?q=${encodeURIComponent(q)}\`)`
   - Add `handleKeyDown` to input (Enter when no inline results = navigate to search page)
   - Add "View all results" `Command.Item` at bottom of `Command.List`
3. Create page at `apps/web/src/app/[locale]/search/page.tsx`

## shadcn/ui Component Availability

Not all shadcn/ui components are installed. Check `apps/web/src/components/ui/` before importing:

| Available | Not available (use alternatives) |
|---|---|
| `badge`, `button`, `card`, `command`, `dialog`, `export-button`, `input`, `label`, `popover`, `progress`, `select`, `separator`, `skeleton`, `table`, `tabs`, `toast`, `tooltip`, `bulk-actions-bar`, `locale-link` | **checkbox** — use `<Button variant={selected ? 'default' : 'outline'} size="sm">` instead as toggle buttons |

When building a new page, list the directory first:
```bash
ls apps/web/src/components/ui/
```
Match imports against what's actually available. Do NOT import components that don't exist.

## Import Cleanup

After copying a page skeleton from an existing admin page (e.g. `admin/users/page.tsx`), prune unused imports:

- Remove `Checkbox`, `Input`, `Tabs`, `TabsContent`, `TabsList`, `TabsTrigger` from the import block if not used
- Remove unused lucide-react icons (`Search` if using Select for filtering, etc.)
- If you only need a search filter, prefer `<Select>` over `<Input>` + `<Search>` icon pattern — fewer imports, matches the user filter UX

**Why:** The admin/users page has a search <Input> + <form> + <Search> icon. API keys uses a user <Select> filter instead. Copying the full import block from users brings in dead imports that fail CI.

## Page Component Pattern

Every page follows this structure:

```typescript
'use client';

import { useQuery } from '@tanstack/react-query';
import { useI18n } from '@/lib/i18n';
import { AppLayout } from '@/components/layout/app-layout';
// Only import shadcn/ui components that exist in apps/web/src/components/ui/

function LoadingSkeleton() { /* AppLayout-wrapped skeleton */ }
function ErrorState({ onRetry }) { /* centered error card */ }
function PageContent() {
  const { t } = useI18n();
  const { data, isLoading, isError, refetch } = useQuery({...});
  if (isLoading) return <AppLayout><LoadingSkeleton /></AppLayout>;
  if (isError) return <AppLayout>... <ErrorState /> ...</AppLayout>;
  return <AppLayout>...</AppLayout>;
}
export default function Page() { return <PageContent />; }
```

## Verification (hard mandate)

After every page batch:
1. TypeScript: `npx tsc --noEmit` in `apps/web/` — filter to check only new/modified files
2. Docker rebuild: `./run build`
3. E2E: `npx playwright test e2e/`
4. Verify all containers up
