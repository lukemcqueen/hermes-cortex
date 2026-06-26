# Next.js Build & Dev Server Debugging

Gotchas encountered building/running the acme-works Next.js 15 frontend (App Router, `src/` dir, shadcn/ui).

## Empty root `app/` dir shadows `src/app/`

**Symptom:** `next build` compiles successfully with zero errors, but `next start` / `next dev` returns 404 on every route except `/_not-found`. Build output shows only `/404` under "Route (pages)" — no App Router routes listed.

**Cause:** An empty `app/` directory at the project root causes Next.js to ignore `src/app/`. This happens even though Next.js officially prefers `src/` when it exists — the empty dir triggers a resolution quirk.

**Fix:** `rmdir apps/web/app` (or wherever the empty root `app/` lives).

## `useSearchParams()` needs Suspense boundary for static generation

**Symptom:** `next build` fails during "Generating static pages" with:
```
useSearchParams() should be wrapped in a suspense boundary at page "/works".
```

**Cause:** Next.js 15 App Router requires any component using `useSearchParams()` to be wrapped in `<Suspense>` when the page is statically generated.

**Fix:** Split the page into two components:
```tsx
function PageContent() {
  const searchParams = useSearchParams();
  // ... rest of the page
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <PageContent />
    </Suspense>
  );
}
```

## React 19 `useRef()` requires initial value

**Symptom:** TypeScript build error:
```
Expected 1 arguments, but got 0.
```
on `useRef<ReturnType<typeof setTimeout>>()`.

**Cause:** React 19 removed the no-arg overload of `useRef`. An initial value is always required (pass `undefined` explicitly).

**Fix:** `useRef<ReturnType<typeof setTimeout>>(undefined)`

## Zod v4 + `@hookform/resolvers` incompatibility

**Symptom:** Type error when using `zodResolver(workSchema)` with `useForm<WorkFormValues>`:
```
Type 'Resolver<{ ... duration?: unknown; ... }>' is not assignable to type
'Resolver<{ ... duration?: number | undefined; ... }>'.
```

**Cause:** `@hookform/resolvers` v5 ships zod v4 support, but zod v4's type inference differs from v3. `z.coerce.number().optional()` infers as `unknown` in certain contexts when combined with `z.union()` and `.transform()`.

**Fix:** Pin to known-compatible versions:
```
pnpm add zod@3 @hookform/resolvers@4
```

Avoid `z.union([z.coerce.number(), z.literal('')]).optional().transform(...)` — use `z.coerce.number().optional()` directly.

## Works page `listWorks` import check

The works page imports `useWorks` from `@/hooks/use-works`. This hook uses `@tanstack/react-query`'s `useQuery`. The dependency was added via `pnpm add @tanstack/react-query` — verify the import path matches the exported member name.
