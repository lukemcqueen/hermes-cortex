# Admin Review Queue + Super Admin Pattern

Reusable pattern for any ACME app needing a human-in-the-loop review workflow
and/or configuration management dashboards. First implemented in acme-license
(S-03 Admin Queue, S-04 Super Admin).

## Architecture

```
                        ┌──────────────────────┐
                        │   Admin Router        │
                        │   /api/v1/admin/      │
                        │   admin_auth_middleware│
                        └──────┬───────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                                     ▼
┌─────────────────────┐             ┌────────────────────────┐
│ admin queue          │             │ super admin config      │
│ (approve/reject/     │             │ (products, rules,       │
│  assign/override/    │             │  discount codes,        │
│  notes)              │             │  financial dashboard,   │
│                      │             │  audit log)            │
└─────────────────────┘             └────────────────────────┘
```

## Admin Review Queue (S-03)

### State Machine

```
┌─────────┐    ┌───────────┐    ┌──────────┐
│ Pending │───▶│ In Review │───▶│ Approved │
└─────────┘    └───────────┘    └──────────┘
     │               │                │
     │               │                │
     ▼               ▼                ▼
  (assign)       (reject)        (reject)
                     │                │
                     ▼                ▼
                ┌──────────┐
                │ Rejected │
                └──────────┘
```

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/queue` | List items with `?status=`, `?q=`, `?page=`, `?page_size=` |
| `GET` | `/licenses/{id}` | Full detail for side panel |
| `POST` | `/licenses/{id}/assign` | Assign reviewer `{reviewer_id}` |
| `POST` | `/licenses/{id}/approve` | Approve `{review_note, override_amount?}` |
| `POST` | `/licenses/{id}/reject` | Reject `{reason, review_note}` |
| `POST` | `/licenses/{id}/pricing` | Override pricing `{line_items[]}` |
| `GET` | `/licenses/{id}/notes` | Get internal notes |
| `POST` | `/licenses/{id}/notes` | Add internal note `{content}` |

### Admin Auth

```python
# Middleware approach — validates X-Admin-Key header against env var
async def admin_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/admin/"):
        key = request.headers.get("X-Admin-Key", "")
        if key != settings.ADMIN_API_KEY:
            return JSONResponse({"detail": "Unauthorized"}, 403)
    return await call_next(request)
```

Or use a dependency injection guard:

```python
async def require_admin(request: Request):
    key = request.headers.get("X-Admin-Key", "")
    if key != settings.ADMIN_API_KEY:
        raise HTTPException(403, "Unauthorized")
```

`ADMIN_API_KEY` comes from `.env` with a safe dev default (e.g. `dev-admin-key`).
In production, set a strong random value.

### Frontend Pattern

```
/admin/
  page.tsx          ← Tabbed queue (All | Pending | In Review | Approved | Rejected)
  components/
    QueueTable.tsx   ← Filterable table with status badge, date, applicant
    DetailPanel.tsx  ← Side panel with license info + action buttons
    ActionBar.tsx    ← Approve / Reject / Assign / Override buttons
    NoteThread.tsx   ← Note list + add form
```

### State Management

- **No external state library.** Use React `useState` + `useCallback` for tabs,
  filter state, and the selected item for the detail panel.
- **Refetch after mutation.** After approve/reject/assign, re-fetch the queue
  list and clear the detail panel selection.
- **Loading states.** Show skeleton/spinner during fetch, disable action buttons
  during mutation.

## Super Admin Configuration (S-04)

### Tabbed Layout

```
/admin/super/
  page.tsx              ← 5-tab container with sidebar/strip nav
  components/
    ProductsTab.tsx      ← CRUD table: name, type, active toggle
    PricingRulesTab.tsx  ← CRUD: priority, territory, rule expressions, dates
    DiscountCodesTab.tsx ← CRUD: code, type (pct/flat), max_uses, valid_through
    FinancialTab.tsx     ← Dashboard: revenue by period/product/territory
    AuditLogTab.tsx      ← Searchable paginated log with expandable details
```

### CRUD Operations Pattern

Each tab follows this rhythm:

1. **Initial load:** `GET /api/v1/admin/{resource}` → populate table
2. **Create:** Modal form → `POST /api/v1/admin/{resource}` → re-fetch
3. **Edit:** Inline or modal → `PUT /api/v1/admin/{resource}/{id}` → re-fetch
4. **Delete:** Confirm modal → `DELETE /api/v1/admin/{resource}/{id}` → re-fetch
5. **Toggle active:** Optimistic UI update → `PATCH /api/v1/admin/{resource}/{id}/toggle` → re-fetch

### Financial Dashboard Data

Fetched from a single endpoint:

```
GET /api/v1/admin/dashboard?period=monthly&from=2026-01&to=2026-06
```

Response shape:

```json
{
  "revenue_by_period": [{"period": "2026-01", "revenue": 1500000}, ...],
  "revenue_by_product": [{"product": "YouTube", "revenue": 3200000}, ...],
  "revenue_by_territory": [{"territory": "KR", "revenue": 2100000}, ...],
  "discount_stats": {"total_discounts": 45, "total_discounted_amount": 230000, "top_discount_code": "WELCOME10"}
}
```

For MVP, seed realistic mock data. Connect to real billing aggregation later.

### Audit Log

```python
# model.py
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID, primary_key=True, default=uuid4)
    actor_id = Column(String(255), nullable=False)     # admin user ID or API key name
    action = Column(String(100), nullable=False)         # "license.approve", "product.create", etc.
    resource_type = Column(String(100), nullable=False)  # "license", "product", "discount_code"
    resource_id = Column(String(255), nullable=False)
    details = Column(JSON, nullable=True)                # diff, before/after, reason
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def log(cls, db_session, actor_id, action, resource_type, resource_id, details=None):
        entry = cls(actor_id=actor_id, action=action, resource_type=resource_type,
                    resource_id=resource_id, details=details)
        db_session.add(entry)
        # no flush — caller commits as part of their transaction
```

Every admin mutation logs to `audit_log` within the same transaction.
The audit log tab exposes search, pagination, and expandable detail rows.

## Seed Data Pattern

Idempotent seed via lifecycle hook (FastAPI `lifespan` or Alembic migration):

```python
# main.py — lifespan
async def seed_admin_data(db: AsyncSession):
    """Insert seed data if tables are empty. Idempotent."""
    # Check if already seeded
    existing = await db.execute(select(Product).limit(1))
    if existing.scalar_one_or_none():
        return

    # Create products
    products = [Product(name="YouTube", type="per_stream", ...), ...]
    db.add_all(products)

    # Create pricing rules
    rules = [PricingRule(priority=1, territory="ALL", ...), ...]
    db.add_all(rules)

    # Create discount codes
    codes = [
        DiscountCode(code="WELCOME10", discount_type="percentage", discount_value=10, ...),
        DiscountCode(code="FLAT5000", discount_type="fixed", discount_value=5000, ...),
        DiscountCode(code="SUMMER20", discount_type="percentage", discount_value=20, ...),
    ]
    db.add_all(codes)
    await db.commit()
```

## Cross-Service Integration Points

Admin features may need to query other ACME services:

| Integration | Pattern |
|---|---|
| **Works** (acme-works) | Search works by title/CIS code via proxy endpoint |
| **Royalty** (acme-royalty) | Read-only: aggregate earnings per work/period |
| **AV** (acme-av) | Lookup fingerprint matches for compliance checks |
| **Metadata** (acme-metadata) | Enrich license with ISRC/IPI codes |
| **Matching** (acme-matching) | Display match confidence scores |
| **Platform** (acme-platform) | Auth, notification, email dispatch |

For each cross-service call, use a `ServiceClient` class with configurable endpoint,
timeout, and auth token:

```python
class WorksServiceClient:
    def __init__(self, base_url: str, api_key: str):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=10.0,
        )

    async def search_works(self, query: str) -> list[dict]:
        resp = await self.client.get("/api/works", params={"q": query})
        resp.raise_for_status()
        return resp.json()["items"]
```

## Parallel Development Strategy

S-03 and S-04 can be developed in parallel because they share no files:

```
Backend:   models/review.py + models/review_note.py + models/discount_code.py
           + models/audit_log.py + routers/admin.py + schemas/admin.py
           + services/review.py + services/admin.py

Frontend:  /admin/page.tsx            ← S-03
           /admin/super/page.tsx      ← S-04
           i18n/*.json                ← both appends (no key collisions)
           tests/admin-queue.test.tsx
           tests/admin-super.test.tsx
```

They **do** share the i18n files, but adding keys to separate top-level namespaces
(`admin.queue.*`, `admin.super.*`) prevents collisions. Verify with a manual
check after the parallel write.

## Pitfalls

1. **Admin auth at middleware level blocks all admin routes.** Ensure health checks
   and public routes are excluded from the middleware path check.
2. **Audit log grows fast.** Add a retention policy (e.g. 90 days) or archive to
   cold storage. Without it, the audit_log table becomes the largest table in the DB.
3. **Mock vs real financial data.** The dashboard seed data is a placeholder. When
   connecting to real billing, the endpoint shape may differ. Plan an adapter layer.
4. **Action buttons must disable during mutation.** Without loading states, a user
   can double-click Approve and trigger two approval events. The state machine should
   handle this gracefully (idempotent transition), but the UI should prevent it.
5. **Tab state lost on navigation.** Each tab fetches independently. If a user fills
   a form in one tab and navigates away, the form state is lost. Consider `useRef`
   or URL search params for draft persistence if this is a UX concern.
6. **Permission model.** MVP uses a single `ADMIN_API_KEY`. Production needs
   role-based auth (admin vs super_admin) with per-action granularity.

## Verification Checklist

- [ ] Queue list filters by status, searches by applicant/license number
- [ ] Approve transitions status, creates agreement record, logs audit entry
- [ ] Reject with reason logs denial, notifies applicant
- [ ] Assign sets reviewer_id, changes status to in_review
- [ ] Pricing override recalculates total, stores audit trail
- [ ] All tabs in super admin load independently
- [ ] CRUD operations on each tab create/update/delete correctly
- [ ] Financial dashboard loads with seed data
- [ ] Audit log searchable by actor, action, date range
- [ ] Admin auth middleware rejects requests without X-Admin-Key
