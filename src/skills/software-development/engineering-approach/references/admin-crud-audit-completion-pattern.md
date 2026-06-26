# Admin CRUD Audit & Completion Pattern

Comprehensive workflow for auditing and completing admin CRUD pages in ACME projects. Used when the user asks to "review all admin pages," "fix gaps," "build out detail pages," or "make all administrative functions work."

## Trigger Conditions

- User says "comprehensive audit," "review all pages," "fix everything and proceed"
- Multiple admin pages show raw keys, missing data, or broken flows
- Need to systematically complete CRUD for multiple entities (creators, members, publishers, contracts, works, etc.)

## Workflow: 5-Phase Batch Approach

### Phase 1: Systematic Audit (S1)
```bash
# 1. Enumerate all admin pages
find apps/web/src/app/[locale] -name "page.tsx" | grep -E "(creators|members|publishers|contracts|works|admin)" | sort

# 2. For each entity, check 4 pages: list, new, edit, [id] detail
# 3. Verify each page has:
#    - List: search, filter, sort, pagination, delete, bulk actions, export, create button
#    - Create/Edit: zod validation, i18n, proper form pre-fill on edit
#    - Detail: all fields displayed, related data sections
```

### Phase 2: P0 Bug Fixes (S1)
Fix immediately blocking issues:
- Wrong data in dropdowns (e.g., Members instead of Creators)
- Edit forms losing data (empty defaults instead of pre-fill)
- Missing fields on detail pages
- Missing Create buttons on list pages

### Phase 3: Filters, Validation, Table Fixes (S2)
- Add filter dropdowns matching backend query params (role, member_type, etc.)
- Fix skeleton vs data table column mismatches
- Add Zod validation to all create/edit forms
- Show entity names instead of truncated UUIDs in list tables

### Phase 4: Page Improvements (S3)
- Wire stubbed pages to real APIs (forgot password, reports)
- Add read-only notices for non-editable fields
- Add export buttons to admin pages

### Phase 5: Backend Endpoints + Detail Pages (S4)
- Add filtering query params to API routers (creator_id, publisher_id, member_id)
- Update CRUD layer to support joins/filters
- Update frontend API functions and hooks
- Build related data sections on detail pages:
  - Creator → Works by creator, Contracts via works
  - Member → Contracts by member
  - Publisher → Works by publisher, Contracts by publisher

## Key Patterns

### Backend Filter Endpoint Pattern
```python
# apps/api/app/routers/works.py
@router.get("", response_model=PaginatedResponse[WorkListRead])
async def list_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    creator_id: uuid.UUID | None = Query(None),  # NEW
    publisher_id: uuid.UUID | None = Query(None),  # NEW
    ...
):
    items, total = await crud_work.search_works(
        db, creator_id=creator_id, publisher_id=publisher_id, ...
    )
```

```python
# apps/api/app/crud/work.py
async def search_works(self, db, *, creator_id: uuid.UUID | None = None, ...):
    query = select(Work).where(Work.deleted_at.is_(None))
    if creator_id:
        from app.models.work import WorkCreator
        query = query.join(WorkCreator).where(WorkCreator.creator_id == creator_id)
    ...
```

### Frontend Hook Update Pattern
```typescript
// apps/web/src/hooks/use-works.ts
export function useWorks(params?: { 
  page?: number; 
  creator_id?: string; 
  publisher_id?: string; 
  page_size?: number;  // NEW
  ...
}) {
  return useQuery<PaginatedResponse<WorkListRead>>({
    queryKey: ['works', params],
    queryFn: () => listWorks(params),
  });
}
```

### Detail Page Related Data Pattern
```tsx
// apps/web/src/app/[locale]/creators/[id]/page.tsx
const { data: worksData } = useWorks({ creator_id: id, page_size: 10 });
const { data: contractsData } = useContracts({ q: '', page_size: 10 }); // or custom filter

// Render as table with Link to detail pages
{worksData?.items?.map((work) => (
  <tr key={work.id}>
    <td><Link href={`/works/${work.id}`}>{work.title}</Link></td>
    <td>{work.code}</td>
    <td><Badge>{work.status}</Badge></td>
  </tr>
))}
```

## E2E Verification Cycle (After Each Batch)

```bash
# 1. TypeScript check (no new errors)
cd apps/web && npx tsc --noEmit

# 2. Docker rebuild
cd /project/root && docker build -t acme-works-web apps/web -f apps/web/Dockerfile

# 3. Deploy
docker compose up -d --no-deps --force-recreate web

# 4. Wait for healthy, then run E2E
sleep 15 && npx playwright test --reporter=dot

# 5. Verify 100% pass rate before next batch
```

## Gap Classification Schema

| Priority | Type | Examples |
|---|---|---|
| P0 | Bug | Wrong data, lost data on edit, broken flows |
| P1 | Missing feature | Filters, validation, export, related data |
| P2 | Polish | Column sorting, empty states, tooltips |

## Common Pitfalls

1. **Link import** — Next.js 15 requires `import Link from 'next/link'` (not `{ Link }`)
2. **page_size param** — Must add to hook type AND API function AND backend router
3. **i18n keys** — Use `t('entity.field')` pattern; verify keys exist in messages/en.json
4. **Rate limiting** — Login endpoint has 10 req/15min per IP; clear Redis keys during testing
5. **CORS** — New API params need CORS preflight to include them (already configured for /works and /contracts)

## Session Artifacts

This session produced:
- 4 P0 bug fixes across 6 files
- 5 filter/table/validation fixes across 8 files  
- 4 page improvements across 6 files
- 3 backend endpoints + 3 detail pages with related data across 12 files
- 108/108 E2E tests passing after each batch