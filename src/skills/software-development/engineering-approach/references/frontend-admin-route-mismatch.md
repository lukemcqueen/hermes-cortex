# Frontend-Backend Route Mismatch for Admin Pages

When an admin page links to `/admin/{entity}s` but the backend has no router
at that path, users see either a blank error state or a 404.

## The Pattern

| Layer | What breaks | Symptom |
|-------|-------------|---------|
| Frontend page | `[locale]/admin/{entity}s/page.tsx` loads but API calls fail | Error state shown (AlertCircle, retry button) |
| Frontend API | `lib/api/admin.ts` calls `fetchJSON('/admin/{entity}s')` | 404 from the proxy |
| Backend admin router | Missing at `app/routers/admin/{entity}s.py` | Route never registered |
| Backend registry | Missing from `_ROUTERS` in `app/routers/registry.py` | Router not mounted |
| SCIM/Types | `api-types.ts` has wrong field names | Data renders blank |

## Prevention Checklist

When adding a new admin CRUD page:

- [ ] Frontend page exists at `app/[locale]/admin/{entity}s/page.tsx` — verify the file was actually created (not just the sidebar route), check for compile errors like missing hook imports
- [ ] Sidebar nav has `{ path: '/admin/{entity}s', labelKey: 'nav.{entity}s', icon: ... }` — verify file exists BEFORE adding nav entry, otherwise clicking creates a blank error page
- [ ] Backend admin router exists at `app/routers/admin/{entity}s.py` — full CRUD with `prefix="/admin/{entity}s"`
- [ ] Backend router registered in `app/routers/registry.py` with `_RouterEntry(admin_{entity}s_router, prefix="/api")`
- [ ] Backend CRUD module exists at `app/crud/{entity}.py` — the admin router imports from `app.crud`
- [ ] Frontend API functions in `lib/api/admin.ts` or `lib/api/{entity}s.ts` — use correct path (`/admin/{entity}s` or `/{entity}s`)
- [ ] Frontend types in `api-types.ts` — `SocietyRead`, `SocietyCreate`, `SocietyUpdate` field names match Pydantic schemas exactly
- [ ] Form state initial values use correct field names (e.g. `soc_code` not `code`, `territory` not `territory_code`)
- [ ] ALL references in the page use the correct field names — not just the display, but onChange handlers, reset states, and delete confirmations
- [ ] Run `npx tsc --noEmit` to catch stale property references — TypeScript catches mismatches between API types and actual usage
- [ ] Rebuild Docker and verify in browser — the page should load without error

### Quick diagnostic for a blank admin page

If clicking a sidebar link shows an error page:

1. `curl http://localhost:{API_PORT}/api/admin/{entity}s` — if 404, the backend router is missing or not registered
2. If 200 but page shows blank data, check `api-types.ts` field names vs backend Pydantic schema
3. If data loads but table shows empty cells for some columns, that field name is wrong in the render or in the type
4. If the page component can't be found (sidebar link → client error), the page file at `app/[locale]/admin/{entity}s/page.tsx` may not exist

### Societies page case study

The societies page at `/admin/societies` failed on multiple layers simultaneously:

```
Layer 1: Backend router missing     → 404 on /api/admin/societies
Layer 2: Frontend types wrong       → code→soc_code, territory_code→territory
Layer 3: Form state used old names  → useState<SocietyCreate>({ code: '' })
Layer 4: Delete dialog used .code   → deletingSociety.code
```

Each layer was fixed independently. The prevention checklist above would have caught all four.
