# acme-works Frontend CRUD Pattern

Full CRUD frontend for a business entity (works, creators, contracts, members, publishers) in the acme-works Next.js app.

## Stack

| Concern | Choice |
|---|---|
| Framework | Next.js 15 App Router (no `[locale]` prefix) |
| i18n | React Context (`useI18n()`, `messages/{lang}.json`) |
| Forms | `react-hook-form` (no zod for simple forms; zod + `@hookform/resolvers` for validated forms) |
| Data fetching | `@tanstack/react-query` hooks in `hooks/` |
| UI | shadcn/ui New York (Button, Input, Table, Badge, Dialog, Select, Separator, Skeleton, Toast) |
| API client | `lib/api.ts` with `fetchJSON()` wrapper |

## Golden Sequence

```
Types (api-types.ts) → API functions (api.ts) → Hooks (hooks/use-<entity>.ts)
→ i18n keys (messages/en.json + messages/ko.json) → Sidebar link
→ Form component (components/<entity>/<entity>-form.tsx) → Pages
```

One entity typically produces **10 files** (types + api + hooks + form + 4 pages + sidebar + 2 i18n files).

## File-by-file

### 1. Types (`lib/api-types.ts`)

Add under a `── <Entity> ──` section comment at the bottom of the file.

```typescript
export interface EntityCreate {
  name: string;
  // All fields in snake_case matching API request body
}

export interface EntityRead extends EntityCreate {
  id: string;
  code: string;
  created_at: string;
  updated_at: string;
}

export interface EntityListRead extends EntityCreate {
  id: string;
  code: string;
  // Trimmed — fewer fields than EntityRead (no created_at, no nested relations)
}

export interface EntityUpdate {
  // Same shape as EntityCreate, all fields optional
  name?: string;
}
```

**Key rule:** `EntityListRead` is separate from `EntityRead` — the list endpoint returns fewer fields (no `created_at`, no nested relations). The frontend types must match *both* schemas exactly. Check the API's `response_model` decorator on each endpoint.

### 2. API functions (`lib/api.ts`)

Add under a `── <Entity> ──` section comment and import the types at the top:

```typescript
export function listEntities(params?: {
  page?: number;
  page_size?: number;
  q?: string;
}): Promise<PaginatedResponse<EntityListRead>> {
  const usp = new URLSearchParams();
  if (params?.page) usp.set('page', String(params.page));
  if (params?.q) usp.set('q', params.q);
  return fetchJSON(`/entities?${usp}`);
}

export function getEntity(id: string): Promise<EntityRead> {
  return fetchJSON(`/entities/${id}`);
}

export function createEntity(data: EntityCreate): Promise<EntityRead> {
  return fetchJSON('/entities', { method: 'POST', body: JSON.stringify(data) });
}

export function updateEntity(id: string, data: EntityUpdate): Promise<EntityRead> {
  return fetchJSON(`/entities/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteEntity(id: string): Promise<void> {
  return fetchJSON(`/entities/${id}`, { method: 'DELETE' });
}
```

Query parameter naming: use `q` (search), `page`, `page_size` — matching acme-works API convention.

### 3. Hooks (`hooks/use-<entity>.ts`)

Five hooks following the existing pattern:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listEntities, getEntity, createEntity, updateEntity, deleteEntity } from '@/lib/api';
import type { EntityCreate, EntityListRead, EntityRead, PaginatedResponse } from '@/lib/api-types';

export function useEntities(params?: { page?: number; q?: string }) {
  return useQuery<PaginatedResponse<EntityListRead>>({
    queryKey: ['entities', params],
    queryFn: () => listEntities(params),
  });
}

export function useEntity(id: string) {
  return useQuery<EntityRead>({
    queryKey: ['entity', id],
    queryFn: () => getEntity(id),
    enabled: !!id,
  });
}

export function useCreateEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityCreate) => createEntity(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities'] }); },
  });
}

export function useUpdateEntity(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: EntityUpdate) => updateEntity(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entity', id] }); qc.invalidateQueries({ queryKey: ['entities'] }); },
  });
}

export function useDeleteEntity(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => deleteEntity(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities'] }); },
  });
}
```

Query key convention: plural (`entities`) for list queries, singular (`entity`, `id`) for detail queries.

### 4. i18n messages (`messages/en.json` + `messages/ko.json`)

Add a top-level key for the entity in both files. Structure:

```json
{
  "<entity>": {
    "title": "...",
    "description": "...",
    "search_placeholder": "...",
    "no_entities": "...",
    "create": "...",
    "edit": "...",
    "delete": "...",
    "saved": "...",
    "deleted": "...",
    "confirm_delete": "...",
    "error_loading": "...",
    "fields": {
      "name": "...",
      "field2": "..."
    },
    "detail": {
      "title": "...",
      "back_to_list": "...",
      "not_found": "..."
    },
    "create_page": {
      "title": "...",
      "subtitle": "..."
    },
    "edit_page": {
      "title": "...",
      "subtitle": "..."
    },
    "form": {
      "basic_info": "...",
      "identifiers": "...",
      "submit_create": "...",
      "submit_update": "...",
      "placeholders": {
        "name": "..."
      }
    }
  }
}
```

Also add the nav link key under `nav` in both files.

### 5. Sidebar (`components/layout/sidebar.tsx`)

Add a nav item in the `navItems` array. Position matters — match domain ordering:

```typescript
const navItems = [
  { href: '/works', label: t('nav.works'), icon: Music },
  { href: '/creators', label: t('nav.creators'), icon: Users },   // after works
  { href: '/contracts', label: t('nav.contracts'), icon: FileSignature },
  { href: '/members', label: t('nav.members'), icon: Users },
  { href: '/publishers', label: t('nav.publishers'), icon: Building2 },
];
```

Both icon and href must match. Import the icon from `lucide-react`.

### 6. Form component (`components/<entity>/<entity>-form.tsx`)

Reusable form for both create and edit pages. Props:

```typescript
interface EntityFormProps {
  onSubmit: (data: EntityCreate) => Promise<void>;
  isSubmitting: boolean;
  initialData?: EntityRead;  // provided for edit, undefined for create
}
```

Pattern:
- `useForm<EntityCreate>` with `defaultValues` initialized from `initialData ?? defaultValues`
- Sectioned layout using `rounded-lg border bg-card` with `border-b` heading
- `Select` components from shadcn/ui for enum fields
- Separate fields into logical sections (Basic Info, Personal Info, Identifiers) separated by `<Separator />`
- Submit button at the bottom-right using `Loader2` spinner + i18n label

### 7. List page (`app/<entity>/page.tsx`)

Structure: `'use client'` → wrapper component inside `<Suspense>` (for `useSearchParams()`) →
`AppLayout` → header (title + create button) → search bar → table/empty state → pagination.

States to handle:
- **Loading**: skeleton UI matching table row structure (use `<Skeleton>` for each cell)
- **Error**: centered `AlertCircle` icon + error message + retry button
- **Empty**: centered `Music` (or entity-relevant icon) + "no items" message
- **Data**: table with clickable rows (onClick navigates to detail page)

Pagination: `page` from `useSearchParams()`, previous/next buttons, "N–M of Total" text.

### 8. Detail page (`app/<entity>/[id]/page.tsx`)

Header with back button + title + edit/delete buttons. Delete uses a `<Dialog>` confirm pattern.

Detail body: `<dl>` with `<DetailRow>` components in a `border bg-card` card. Each row is a grid with label + value.

Loading state: `<Skeleton>` rows matching the same grid layout.
Not-found state: text message from i18n `detail.not_found`.

### 9. Create page (`app/<entity>/new/page.tsx`)

Simple wrapper:
- Header with back button + page title
- `<EntityForm onSubmit={handleSubmit} isSubmitting={isPending} />`
- `handleSubmit` calls `useCreateEntity()`, shows toast on success, navigates to `/<entity>/${created.id}`
- Error handling in catch block → destructive toast

### 10. Edit page (`app/<entity>/[id]/edit/page.tsx`)

Same as create but:
- Fetches entity with `useEntity(id)` for `initialData`
- Uses `useUpdateEntity(id)` mutation
- Navigates back to `/<entity>/${id}` on success
- Loading state: Skeleton form
- Not-found guard: entity not loaded → show error text

## Common pitfalls

- **`CreatorListRead` lacks `created_at`** — the list API schema is intentionally trimmed. Do NOT add a "Created" column to the list table. The field exists only on `EntityRead`.
- **`useSearchParams()` requires `<Suspense>`** — Next.js 15 throws if `useSearchParams()` is used outside a `<Suspense>` boundary. Always wrap the main page component in `<Suspense>` in the default export.
- **`useForm<CreatorCreate>` not `useForm<CreatorFormValues>`** — for simple forms without zod validation, use the API type directly as the form type. No intermediary schema needed.
- **`fetchJSON` auto-attaches JWT and the `/api/v1` prefix via Next.js rewrite proxy** — no manual `Authorization` header and no `/api/v1` in the URL path. The rewrite proxy in `next.config.ts` maps `/works` -> `/api/v1/works` and adds the auth cookie.
- **i18n keys must match between en.json and ko.json** — every key in en.json must exist in ko.json. Missing keys show the key path as fallback text.
- **Route paths have no `[locale]` prefix** — unlike acme-royalty, acme-works uses flat routes (`/creators`, not `/[locale]/creators`).
- **API endpoints may exist in the backend with no frontend API client functions** — this is a common half-built state in acme-works. Always check the API router (`apps/api/app/routers/<entity>.py`) for `@router.post`, `@router.patch`, `@router.delete` endpoints, then compare against `apps/web/src/lib/api.ts`. If the backend has CRUD but `api.ts` only has `list*` and `get*` functions, you need to add `create*`, `update*`, `delete*` functions and the corresponding types. The hooks file may also be incomplete (missing single-entity query or mutation hooks).
