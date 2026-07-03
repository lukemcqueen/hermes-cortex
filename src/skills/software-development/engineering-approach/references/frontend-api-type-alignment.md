# Frontend-Backend Field Name Alignment

Frontend TypeScript types and backend Pydantic schemas must use the **exact same field names**. When they diverge, data silently disappears — no errors on either side.

## The Pattern

```
Frontend                  Backend
api-types.ts              schemas/admin_user.py

interface UserCreate {    class UserAdminCreate(BaseModel):
  name: string              display_name: str | None = None
  email: string             email: str
  role: string              role: str
}
```

**Bug: `name` vs `display_name`**

1. Frontend sends `POST /admin/users { name: "John", email: "...", role: "admin" }`
2. Pydantic receives the body. `name` is not a field of `UserAdminCreate`. It gets **silently dropped** (no 422 error — unknown fields are ignored by default).
3. `display_name` was not sent, so it stays `None`.
4. User's name is stored as `NULL`.
5. On read, frontend does `user.name` on the response. Backend returned `display_name: null` — frontend reads `undefined`. Table shows nothing.

**Both directions are silent:** no 400, no 422, no error log, no console warning. Data just vanishes.

## Prevention

### 1. Single source of truth for field names

When adding a new backend schema field, **simultaneously** update the frontend TypeScript type. Do not rely on memory or separate PRs.

Checklist when adding a field:
- [ ] Backend model column added
- [ ] Backend Pydantic schema updated (Create, Update, Read)
- [ ] Frontend API type updated (`api-types.ts`)
- [ ] Frontend API function payload/response typed
- [ ] Frontend page uses the correct field name in form state and display
- [ ] i18n label keys match (if displayed)

### 2. Verify field names match — don't trust TypeScript

TypeScript types defined in `api-types.ts` are **not enforced at runtime**. The `fetchJSON` call passes JSON directly — no runtime validation against the declared type. TypeScript's structural typing means `{ name: string }` and `{ display_name: string }` are just different labels, not different types.

Manual check: compare Pydantic schema field names vs frontend API type field names side by side.

### 3. Test at the integration level

A unit test of the frontend component that mocks the API response with `display_name` won't catch the problem if the mock uses `name` too. The gap only surfaces when:
- The POST goes to a real backend and Pydantic validates it
- The GET response is mapped to the frontend's `UserAdminRead` type

E2E tests or integration tests that exercise the real API surface catch this. Unit tests with permissive mocks don't.

### 4. Common mismatch pairs

| Frontend uses | Backend expects | Where it appears |
|---|---|---|
| `name` | `display_name` | User admin, member/publisher models |
| `description` | `notes` or `comment` | Various entity schemas |
| `type` | `entity_type` or `kind` | Polymorphic models |
| `code` | `soc_code` | CISAC society code — frontend used `society.code`, API returns `soc_code` |
| `territory_code` | `territory` | Society territory — frontend used `society.territory_code`, API expects `territory` |
| `created` | `created_at` | Timestamp fields |
| `updated` | `updated_at` | Timestamp fields |
| `items` | `results` or `data` | Paginated/list responses |

### Societies page specific checklist (from real incident)

When the societies page showed blank code and territory columns despite data in the DB, the root cause chain was:

1. `api-types.ts` defined `SocietyRead.code` and `SocietyRead.territory_code`
2. Backend Pydantic schema `SocietyRead` had `soc_code` and `territory`
3. Page rendered `society.code` and `society.territory_code` → both `undefined`
4. TypeScript didn't catch it because the type system trusts the .d.ts file
5. Form state `useState<SocietyCreate>({ code: '', territory_code: '' })` sent wrong field names to POST/PATCH, so creates/updates also failed silently

**Fix steps for any entity with display/CRUD issues:**
1. Check `api-types.ts` — `SocietyRead`, `SocietyCreate`, `SocietyUpdate`
2. Check backend `schemas/{entity}.py` — `{Entity}Read`, `{Entity}Create`, `{Entity}Update`
3. Align every field name between them
4. Check form state initial values in the page component
5. Check `openEditDialog()` — it reads the read model and sets form state
6. Check delete confirmation dialog — `society.code` → `society.soc_code`
7. Run `npx tsc --noEmit` to catch any remaining references to old field names
8. Rebuild Docker and verify in browser

## Root cause

Frontend teams often define API types independently (or copy from a mock/spec) rather than generating them from the backend schema. The result: drift between what the frontend declares it expects and what the backend actually sends/accepts.

**Long-term fix:** Generate TypeScript types from Pydantic schemas (e.g. `datamodel-code-generator` or `openapi-typescript`). Short-term: manual triple-check on every PR that touches both layers.

### Societies page specific checklist (from real incident)

When the societies page showed blank code and territory columns despite data in the DB, the root cause chain was:

1. `api-types.ts` defined `SocietyRead.code` and `SocietyRead.territory_code`
2. Backend Pydantic schema `SocietyRead` had `soc_code` and `territory`
3. Page rendered `society.code` and `society.territory_code` → both `undefined`
4. TypeScript didn't catch it because the type system trusts the .d.ts file
5. Form state `useState<SocietyCreate>({ code: '', territory_code: '' })` sent wrong field names to POST/PATCH, so creates/updates also failed silently

**Fix steps for any entity with display/CRUD issues:**
1. Check `api-types.ts` — `SocietyRead`, `SocietyCreate`, `SocietyUpdate`
2. Check backend `schemas/{entity}.py` — `{Entity}Read`, `{Entity}Create`, `{Entity}Update`
3. Align every field name between them
4. Check form state initial values in the page component
5. Check `openEditDialog()` — it reads the read model and sets form state
6. Check delete confirmation dialog — `society.code` → `society.soc_code`
7. Run `npx tsc --noEmit` to catch any remaining references to old field names
8. Rebuild Docker and verify in browser
