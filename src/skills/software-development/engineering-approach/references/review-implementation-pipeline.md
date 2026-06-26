# Post-Review Implementation Pipeline

## Purpose

Bridge the gap between architecture review output (hc-party) and delivered, tested code. The hc-party produces a list of "Implementation Slices" with summaries and estimates. This reference documents how to convert those slices into actual story slices, implement each one, add tests, and verify.

## When to Use

After running `hc-party` or any structured architecture review that produces a list of recommended implementation slices. Use this to turn recommendations into real code.

## Pipeline Stages

```
hc-party → story-slicing → implement → test → verify → report
```

### Stage 1: Slice Conversion

The hc-party "First 5 Implementation Slices" section lists items like:
```
| Slice | Work | Estimate |
|-------|------|----------|
| S1 | Fix health color logic (elapsed time vs P95) | 0.5 days |
| S2 | Add date range filter to page + backend | 1 day |
| S3 | Add drill-down navigation from stage cards | 0.5 days |
```

Each slice must be converted into a proper **story slice** with:

| Element | What to define |
|---------|----------------|
| Title | The slice's work description (user-visible outcome) |
| Scope | What's included AND what's explicitly excluded |
| Acceptance criteria | Success, failure, edge case, test/verification |
| Files affected | Backend router, frontend page, API types, i18n files, test files |
| Risk | low/medium/high |
| Verification | Exact command to run + expected result |

**Example conversion:**

```
S1: Fix Health Color Logic

Scope:
- Backend: Add stalled_pct field to StageInfo model
- Backend: Implement _get_stage_entry_time() helper
- Frontend: Replace anomaly-based proxy with real stalled_pct
- Test: Existing backend tests must still pass

AC:
- [ ] stalled_pct appears in dashboard endpoint response
- [ ] stalled_pct = null when no P95 data or no runs
- [ ] Frontend health color uses stalled_pct, not anomaly proxy
- [ ] All 7 operations backend tests pass

Files: routers/operations.py, operations/page.tsx, api.ts
Risk: low
Verification: pytest tests/test_operations.py -v → 7/7 PASS
```

### Stage 2: Prioritization & Ordering

Order slices by:

1. **Foundation first** — backend changes before frontend (the frontend needs the backend to be deployed first)
2. **Smallest risk first** — low-risk slices before medium-risk
3. **Dependency chain** — if S2 depends on S1, do S1 first
4. **Test completion** — always add the test slice last (it's the final verification)

Within each slice, the implementation order is:
```
backend → frontend API types → frontend page → i18n → tests → verify
```

### Stage 3: Implementation Per Slice

Each slice follows the same implementation pattern:

#### Backend changes
```python
# 1. Update the Pydantic/response model
class StageInfo(BaseModel):
    status: str
    run_count: int
    p95_hours: float | None = None
    anomaly_count: int = 0
    stalled_pct: float | None = None  # NEW FIELD

# 2. Add helper function if needed
def _get_stage_entry_time(run: DistributionRun, status: str) -> datetime | None:
    ...

# 3. Add computation logic in the endpoint
for r in stage_runs:
    entered_at = _get_stage_entry_time(r, status)
    if entered_at:
        elapsed = (now - entered_at).total_seconds() / 3600
        # Compare to P95 for health color

# 4. Add query params for filters
@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
):
    query = db.query(DistributionRun)
    if period_start:
        query = query.filter(DistributionRun.period_end >= period_start)
    if period_end:
        query = query.filter(DistributionRun.period_start <= period_end)
```

#### Frontend API types
```typescript
// 1. Add new field to frontend type
export interface StageInfo {
  status: string;
  run_count: number;
  p95_hours: number | null;
  anomaly_count: number;
  stalled_pct: number | null;  // NEW
}

// 2. Update API function signature if params added
export function getOperationsDashboard(params?: {
  period_start?: string;
  period_end?: string;
}): Promise<DashboardResponse> {
  const qs = new URLSearchParams();
  if (params?.period_start) qs.set('period_start', params.period_start);
  if (params?.period_end) qs.set('period_end', params.period_end);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return fetchJSON(`/operations/dashboard${suffix}`);
}
```

#### Frontend page changes
```tsx
// 1. Use the new field instead of proxy logic
const stalledPct = info?.stalled_pct ?? null;

// 2. Add drill-down navigation
{count > 0 ? (
  <Link href={`/distributions?status=${stage}`}>
    {cardBody}
  </Link>
) : (
  <div>{cardBody}</div>
)}

// 3. Add filter state and pass to API
const [periodStart, setPeriodStart] = useState('');
const [periodEnd, setPeriodEnd] = useState('');

const fetchData = useCallback(() => {
  getOperationsDashboard({
    period_start: periodStart || undefined,
    period_end: periodEnd || undefined,
  })
}, [periodStart, periodEnd]);
```

#### i18n changes
```json
{
  "periodStart": "Period start",
  "periodEnd": "Period end"
}
```
Always add both English (`en.json`) and Korean (`ko.json`) translations.

### Stage 4: Testing Per Slice

Each slice must include tests:

#### Backend tests
- Run the existing test suite AFTER changes: `pytest tests/test_operations.py -v`
- Verify 7/7 pass (or whatever the count is)
- No new backend tests needed unless the slice adds new behavior (filters, new endpoint)

#### Frontend component tests
Create a test file at `apps/web/src/app/[locale]/operations/__tests__/page.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import OperationsPage from '../page';

// Mock data
const mockData = { stages: [...], pending_amounts: {...}, ... };

// Mocks needed:
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    // Must support {count} style interpolation
    const val = translations[key] ?? key;
    if (params) {
      return Object.entries(params).reduce(
        (s, [k, v]) => s.replace(`{${k}}`, String(v)), val
      );
    }
    return val;
  },
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: any) => <a href={href}>{children}</a>,
}));

vi.mock('../../../../lib/api', () => ({
  getOperationsDashboard: vi.fn(),
}));

// Test cases to cover:
describe('OperationsPage', () => {
  it('renders title and subtitle', ...)
  it('renders all pipeline stages', ...)
  it('renders failed stage when failed runs exist', ...)
  it('renders run counts per stage', ...)
  it('renders pending amounts section', ...)
  it('renders recent activity', ...)
  it('shows loading state initially', ...)
  it('shows error state on API failure', ...)
  it('renders total runs count', ...)
  it('renders refresh button', ...)
  it('renders date range filter inputs', ...)
  it('calls API on mount with no date filters', ...)
});
```

**Common pitfalls when writing these tests:**

| Pitfall | Fix |
|---------|-----|
| `getByText('string')` fails when text appears in multiple elements | Use `getAllByText('string')` + `expect(length).toBeGreaterThanOrEqual(1)` |
| i18n mockT fails on `t('key', { count: N })` | The mock `t` function must accept a second `params` argument |
| Link component renders as `<a>` without href | Mock `next/link` to render an `<a>` tag with `href` |
| Date input elements not found | Check for `input[type="date"]` via `document.querySelectorAll` |
| API mock receives wrong params | Verify the mock's call signature: `expect(getOperationsDashboard).toHaveBeenCalledWith({period_start: '...'})` |

### Stage 5: Final Verification

After all slices are complete:

| Check | Command | Expected |
|-------|---------|----------|
| Backend tests | `pytest tests/test_operations.py -v` | 7/7 PASS |
| Frontend component tests | `pnpm vitest run .../operations/__tests__/page.test.tsx` | 12/12 PASS |
| Full web suite | `./run test:web` | 310 PASS, only pre-existing test failures |
| Page loads | `curl -s -o /dev/null -w "%{http_code}" http://localhost:13101/en/operations` | 200 |
| API healthy | `curl -s http://localhost:13102/health` | `{"status":"ok"}` |

## Anti-Patterns

- **Skipping the slice conversion**: Taking hc-party recommendations directly as code directives without converting to proper story slices. Each slice needs scope (included/excluded), AC, files affected, and verification. Without this, slices bleed into each other or miss edge cases.
- **Implementing all slices before running any tests**: Test each slice before moving to the next. A bug in S1 will cascade through S2-S5.
- **Skipping i18n**: Even for Korean-first projects, add both en.json and ko.json keys in the same commit. Missing translations are a common gap.
- **Forgetting to add `stalled_pct` to the frontend type**: If the backend returns a new field but the frontend `StageInfo` interface doesn't declare it, TypeScript will error. Update types and mocks in the same change as the backend field.
- **Deep import paths**: The test file is in `[locale]/operations/__tests__/page.test.tsx`, which is 4 levels deep. The import path to `api.ts` is `../../../../lib/api`. Count `../` entries carefully.
