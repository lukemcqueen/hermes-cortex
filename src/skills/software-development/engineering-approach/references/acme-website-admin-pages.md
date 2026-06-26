# ACME Website: Admin Page Pattern

The admin panel in `acme-website` follows a **server component → client component** split pattern distinct from acme-royalty's client-only `'use client'` pages.

## Architecture

```
apps/web/src/app/[locale]/admin/<feature>/page.tsx    ← Server component (auth + shell)
apps/web/src/components/admin/<feature>/<Feature>.tsx  ← Client component (interactivity)
```

## Server Component (page.tsx)

```typescript
import { getSessionAdmin } from '../../login/actions';
import { redirect } from 'next/navigation';
import { AdminPageShell } from '@/components/admin/AdminPageShell';
import { FeatureList } from '@/components/admin/feature/FeatureList';

type Props = { params: Promise<{ locale: string }> };

export default async function AdminFeaturePage({ params }: Props) {
  const { locale } = await params;
  const admin = await getSessionAdmin();
  if (!admin) redirect(`/${locale}/login`);

  return (
    <AdminPageShell title="Feature" description="Do something with feature">
      <FeatureList />
    </AdminPageShell>
  );
}
```

Key rules:
- `getSessionAdmin()` returns the admin object or null — redirect to login if null
- `AdminPageShell` provides consistent title bar + description + page structure
- No data fetching in the server component — the client component manages its own API calls
- `params` is a `Promise` — must `await` in Next.js 15 App Router

## Client Component (components/admin/<feature>/<Feature>.tsx)

```typescript
'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiFunction } from '@/lib/api';
import { Loader2 } from 'lucide-react';

export function FeatureList() {
  const [data, setData] = useState<DataType | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiFunction();
      setData(result);
    } catch {
      // Keep existing data on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ... render
}
```

Key rules:
- `'use client'` directive at top
- `useCallback` + `useEffect` pattern for data fetching (stable reference, no stale closures)
- No i18n translation calls — admin pages use hardcoded English text
- API functions from `@/lib/api`, not direct `fetch()` calls
- Client-side filtering (e.g. search, action filter) can be done on the fetched data or by re-fetching with query params
- Use the same icon/style patterns as other admin components (lucide-react icons, neutral/primary color scheme, rounded-xl borders, bg-white shadow-sm cards)

## API Functions (lib/api.ts)

Add to `apps/web/src/lib/api.ts` under a section comment:

```typescript
// ── Feature Name ──────────────────────────────

export interface FeatureItem {
  id: number;
  // snake_case fields matching FastAPI response
}

export async function listFeatureItems(params: { page?: number } = {}) {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set('page', String(params.page));
  return apiFetch<FeatureResponse>(`/api/admin/feature?${searchParams}`, { method: 'GET' });
}
```

- Use `apiFetch<T>()` from the same file — it handles auth headers and error handling
- Always define response types (interfaces) alongside the function
- Query params via `URLSearchParams` — only pass non-empty values

## Sidebar Nav Items

Add to the `navItems` array in `AdminSidebar.tsx`:

```typescript
import { ScrollText, Bell, Palette } from 'lucide-react';

// In navItems array:
{ label: 'Feature', href: '/en/admin/feature', icon: <IconName className="h-5 w-5" /> },
```

- Hardcode `/en/admin/...` paths (matching the existing pattern — admin sidebar does not use dynamic locale routing)
- Import the lucide-react icon

## Notification Bell (AdminHeader)

Add to `AdminHeader.tsx`:

```typescript
import { Bell } from 'lucide-react';
import { getUnreadNotificationCount } from '@/lib/api';

const [unreadCount, setUnreadCount] = useState(0);

useEffect(() => {
  const fetchUnread = async () => {
    try {
      const { count } = await getUnreadNotificationCount();
      setUnreadCount(count);
    } catch { /* silent */ }
  };
  fetchUnread();
  const interval = setInterval(fetchUnread, 60_000);
  return () => clearInterval(interval);
}, []);
```

The bell icon links to `/en/admin/notifications`.

## Tables

Admin tables follow this template:
- Overflow-x-auto wrapper div with `rounded-xl border border-neutral-200 bg-white shadow-sm`
- Sortable column headers as `<button>` elements with `ArrowUpDown` icon
- Action column with `Edit` (Link) and `Trash2` (delete button) icons
- Empty state with centered icon + message
- `<Pagination>` component from `@/components/shared/Pagination` for multi-page results

## Build & Verify

```bash
./run rebuild     # clean + install + build
./run ps          # verify all 6 services healthy (api, web, postgres, pgbouncer, redis, minio)
```
