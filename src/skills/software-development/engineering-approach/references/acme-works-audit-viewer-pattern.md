# acme-works Audit / Read-Only Viewer Pattern

A read-only data viewer page with filters, pagination, inline detail expansion, and a stats sidebar. Used for audit logs, event history, import records, or any page where the user inspects rather than edits.

## When to use this pattern

- The page displays data the user should not edit (audit trail, system logs, activity history)
- The main view is a flat list that needs filtering by multiple dimensions (type, status, resource)
- Each row may have expandable detail (JSON diff, nested info)
- A stats summary helps orient the user (counts per category)

## Golden Sequence

```
API types (api-types.ts) → API functions (api.ts) → Hooks (hooks/use-*.ts)
→ i18n keys (messages/{lang}.json) → Page (app/<path>/page.tsx)
```

No form, no sidebar link, no detail/edit/create pages — single page only.

## File-by-file

### 1. Types (`lib/api-types.ts`)

Add a section comment and the response types:

```typescript
// ── Audit Log ──
export interface AuditEntry {
  id: number;
  table_name: string;
  operation: 'INSERT' | 'UPDATE' | 'DELETE';
  record_id: string;
  changes: Record<string, { old: unknown; new: unknown }> | null;
  performed_by: string | null;
  created_at: string;
}

export interface AuditListResponse {
  items: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditStatsItem {
  table_name: string;
  entry_count: number;
}

export interface AuditTablesResponse {
  tables: string[];
}
```

### 2. API functions (`lib/api.ts`)

Filter params are passed as query string. No mutation functions needed:

```typescript
import type { AuditEntry, AuditListResponse, AuditStatsItem, AuditTablesResponse } from '@/lib/api-types';

export function listAuditEntries(params?: {
  page?: number;
  page_size?: number;
  table_name?: string;
  operation?: string;
  record_id?: string;
}): Promise<AuditListResponse> {
  const usp = new URLSearchParams();
  if (params?.page) usp.set('page', String(params.page));
  if (params?.page_size) usp.set('page_size', String(params.page_size));
  if (params?.table_name) usp.set('table_name', params.table_name);
  if (params?.operation) usp.set('operation', params.operation);
  if (params?.record_id) usp.set('record_id', params.record_id);
  return fetchJSON(`/audit?${usp}`);
}

export function getAuditTables(): Promise<AuditTablesResponse> {
  return fetchJSON('/audit/tables');
}

export function getAuditStats(): Promise<AuditStatsItem[]> {
  return fetchJSON('/audit/stats');
}
```

### 3. Hooks (`hooks/use-<topic>.ts`)

Query-only — no mutations:

```typescript
import { useQuery } from '@tanstack/react-query';
import { listAuditEntries, getAuditTables, getAuditStats } from '@/lib/api';
import type { AuditListResponse, AuditTablesResponse, AuditStatsItem } from '@/lib/api-types';

export function useAuditEntries(params?: {
  page?: number;
  page_size?: number;
  table_name?: string;
  operation?: string;
  record_id?: string;
}) {
  return useQuery<AuditListResponse>({
    queryKey: ['audit', 'entries', params],
    queryFn: () => listAuditEntries(params),
  });
}

export function useAuditTables() {
  return useQuery<AuditTablesResponse>({
    queryKey: ['audit', 'tables'],
    queryFn: () => getAuditTables(),
  });
}

export function useAuditStats() {
  return useQuery<AuditStatsItem[]>({
    queryKey: ['audit', 'stats'],
    queryFn: () => getAuditStats(),
  });
}
```

Query key convention: `['audit', 'entries', params]`, `['audit', 'tables']`, `['audit', 'stats']` — namespaced under `'audit'` to group related queries.

### 4. Page (`app/<path>/page.tsx`)

Structure: `'use client'` → `AppLayout` → header (title + back link if applicable) → filter row → main content grid (stats sidebar | table).

**States:**

| State | UI |
|---|---|
| **Loading** | `<Skeleton>` cards for stats, `<Skeleton>` rows for table |
| **Error** | Centered `<AlertCircle>` + error message + retry button (calls `refetch()`) |
| **Empty** | Centered icon + "No entries" message |
| **Data** | Stats cards in sidebar, paginated table with expandable rows |

**Filter row** — horizontal layout:

```tsx
<div className="flex flex-wrap gap-2 mb-4">
  {/* Table name: <Select> populated from useAuditTables() */}
  {/* Operation: <Select> with static INSERT/UPDATE/DELETE + "All" */}
  {/* Record ID: <Input> search field */}
</div>
```

**Stats sidebar** — `<Card>` per item:

```tsx
<div className="space-y-2">
  {stats?.map(stat => (
    <Card key={stat.table_name} className="p-3">
      <div className="text-sm text-muted-foreground">{stat.table_name}</div>
      <div className="text-2xl font-bold">{Number(stat.entry_count).toLocaleString()}</div>
    </Card>
  ))}
</div>
```

**Table** — standard `<Table>` from shadcn/ui with:

| Column | Content |
|---|---|
| Timestamp | `created_at` formatted |
| Table | `<Badge variant="outline">{table_name}</Badge>` |
| Operation | Colored `<Badge>` — Update/Insert/Delete |
| Record ID | Monospace `<code>` |
| Performed by | Name or "—" |
| Changes | Toggle button (only for UPDATE entries with non-null `changes`) |

**Inline diff** — expandable `<Collapsible>` for update changes:

```tsx
<Collapsible>
  <CollapsibleTrigger>Show changes</CollapsibleTrigger>
  <CollapsibleContent>
    <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-40">
      {JSON.stringify(changes, null, 2)}
    </pre>
  </CollapsibleContent>
</Collapsible>
```

### 5. i18n keys (`messages/{lang}.json`)

Minimal — the page is mostly data-driven with no forms:

```json
{
  "audit": {
    "title": "Audit Log",
    "description": "Track all changes made across the system",
    "filter_table": "Table",
    "filter_operation": "Operation",
    "filter_record_id": "Record ID",
    "all_tables": "All Tables",
    "all_operations": "All Operations",
    "no_entries": "No audit entries found",
    "error_loading": "Failed to load audit log",
    "retry": "Retry",
    "columns": {
      "timestamp": "Timestamp",
      "table": "Table",
      "operation": "Operation",
      "record_id": "Record ID",
      "performed_by": "Performed By",
      "changes": "Changes"
    },
    "operations": {
      "INSERT": "Insert",
      "UPDATE": "Update",
      "DELETE": "Delete"
    },
    "show_changes": "Show changes",
    "hide_changes": "Hide changes",
    "stats_title": "Entries by Table"
  }
}
```

## Pitfalls

- **Stats sidebar API may return no data on empty DB** — fall back to empty array, don't crash. The stats section should gracefully show nothing when `stats.length === 0`.
- **Inline changes can be large** — cap the `<pre>` height with `max-h-40` (or a custom value) and `overflow-auto`. Don't render giant raw diffs inline.
- **Pagination resets on filter change** — when the user changes a filter dropdown, reset `page` to 1. The cleanest way: use a `key` derived from filters on the query so it auto-refetches from page 1.
- **No `useSearchParams()` here unless search-in-URL** — audit filters are often local state (`useState`), not URL params. If you use `useSearchParams()`, wrap in `<Suspense>`.
- **Operation filter is static** — INSERT/UPDATE/DELETE are universal for this pattern. Don't fetch operations from the API; hardcode the three values.
- **Table name filter fetches from API** — use `useAuditTables()` to populate the dropdown. This is dynamic because table names are domain-specific.
- **Audit data is append-only** — never invalidate audit queries on mutations. Audits never change once written. Set `staleTime: 5 * 60 * 1000` or higher for these queries.
- **fetchJSON auto-attaches JWT + `/api/v1` prefix** — same as CRUD pages. No manual auth or URL prefix needed.
