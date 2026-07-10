# Next.js Dashboard KPI Patterns (acme-works)

Dashboard pattern for Next.js apps: aggregation API endpoint + trend cards + chart + alerts + recent activity.

## Backend: Aggregation Endpoint

```python
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
```

**Aggregation queries** — count current month vs previous month for growth %:

SQL approach: use `func.date_trunc('month', ...)` for month boundaries. Use `func.count()` with `filter()` for multiple counts in one query when efficient.

**Import trend** — daily counts over 30 days with `func.date_trunc('day', ...)`, group by day, order by day. Fill zero-count days from a Python-generated date range.

**Growth percentage calculation:**

```
if prev == 0 and current > 0:  growth = 100
elif prev == 0:                 growth = 0
else:                           growth = round((current - prev) / prev * 100)
```

## Frontend Components

### TrendCard
- Icon + label + large value + growth % with ▲/▼/— indicator
- Uses TrendingUp/TrendingDown/Minus from lucide-react
- Entire card is a Link to the entity's list page
- Shows Skeleton during loading

### Recharts Line Chart
- ResponsiveContainer + LineChart + XAxis + YAxis + Tooltip + Line
- `stroke="hsl(var(--border))"` / `"hsl(var(--primary))"` for theme-aware colors
- `dot={{ r: 3 }}` / `activeDot={{ r: 5 }}` for clean dots
- **Pitfall:** `Tooltip` `labelFormatter` and `formatter` props have strict generic types that make custom formatters difficult to type in TypeScript. If `as any` casting doesn't resolve, simply omit custom formatters — the default Tooltip display is functional.
- Empty state: `"No import activity yet"` centered text
- Loading state: `<Skeleton className="h-64 w-full" />`

### Alerts Panel
- Cards for: share errors (red), pending reviews (amber), failed imports (green)
- Each item is a Link to the relevant filtered list page (`/works?status=error`, etc.)
- Shows change/delta text from the API

### Recent Imports Table
- Uses Badge variants: completed=default, failed=destructive, processing=secondary, pending=outline
- Rows are clickable → `/import/{id}`
- Responsive: hides date column on small screens (`hidden sm:table-cell`)
- Empty state shows Upload icon + descriptive text

## Types (api-types.ts)

```
DashboardSummary: entity_total + entity_growth pairs + pending + share_errors + import_trend + recent_imports
ImportTrendPoint: { date: string, count: number }
RecentImport: { id, status, file_path, transactions_processed, transactions_failed, records_imported, error_count, creation_date, created_at }
```

## Hook

```tsx
function useDashboardSummary() {
  return useQuery<DashboardSummary>({
    queryKey: ['dashboard', 'summary'],
    queryFn: getDashboardSummary,
    staleTime: 30_000,
  });
}
```

## Page Layout

4 TrendCards → Quick Actions → [Chart | Alerts] → Recent Imports → Recent Activity (last 5 works)

## Registration

1. Create router at `apps/api/app/routers/dashboard.py`
2. Register: `app.include_router(dashboard.router, prefix="/api")`
3. `pnpm add recharts`
4. Add types, API function, hook
5. Create components under `components/dashboard/`
6. Rewrite `app/page.tsx`
