# Backend API Feature Workflow (acme-royalty)

Workflow for adding new backend features to the acme-royalty FastAPI project — from doc discovery through implementation and verification.

## Golden Path: Doc-First Feature Discovery

When the user asks "check docs/ for X" or "see where we are on Y":

1. **Search docs/** for relevant story/slice/docs files — `search_files(pattern, path="docs/")` for names and content
2. **Read the spec** — understand the data model, endpoints, and required behavior
3. **Check existing state** — run tests, check if models/routers already exist before building
4. **Summarize findings** — what exists, what's missing, what needs building

Then implement the feature.

## Feature Implementation Sequence

For each backend feature, follow this order:

```
Spec (docs/) → DB Model (db/models.py) → Alembic Migration → Router (routers/) → app registration (main.py) → Tests → Seed Script (scripts/)
```

### 1. DB Model (`db/models.py`)

- Use SQLAlchemy 2.x MappedAsDataclass style with `Mapped[type] = mapped_column(...)`
- Add new models at the bottom of the file
- Common column patterns:
  - `id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)`
  - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())`
  - `status` fields as strings with sensible defaults
- NOT NULL columns must handle test seeding (SQLite enforces them strictly)

### 2. Alembic Migration

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"
```

- Check the generated migration in `db/versions/` — verify column types and constraints match the model
- SQLite in tests ignores things like `TIMEZONE` on DateTime, but PostgreSQL in prod will enforce it

### 3. Router (`apps/api/routers/<name>.py`)

- Create a new router file with `prefix="/api/v1/<name>"`, `tags=[...]`, `dependencies=[Depends(require_s2s_auth)]`
- Reusable patterns:

**Normalized resource IDs** — when the frontend uses "dist-XXX" formatted IDs but the DB uses integers:
```python
def _normalize_id(raw_id: str) -> int:
    if raw_id.startswith("dist-"):
        return int(raw_id.replace("dist-", ""))
    return int(raw_id)
```
Use in path params: `distribution_id: str` (not `int`), then normalize.

**Default/demo creator resolver** — for dev endpoints that default to a demo user:
```python
DEMO_CREATOR_ID = 1

def _resolve_creator_id(creator_id: int | None) -> int:
    return creator_id if creator_id else DEMO_CREATOR_ID
```

**Deduction chain** — gross → deductions → net, returned as a structured list with type/label/amount:
```python
deductions = [
    {"type": "commission", "label": "Society Commission (8%)", "amount": str(stmt.commission)},
    {"type": "management_fee", ...},
    {"type": "withholding_tax", ...},
]
# Add optional items conditionally
if stmt.treaty_adjustment:
    deductions.append({"type": "treaty", ...})
```

Return amounts as `str` (not int) to avoid JS number precision issues for large KRW values.

**Export endpoint with SHA-256 tamper evidence** — For audit/certification downloads, append the hash as a comment outside the JSON payload:

```python
import hashlib

@router.get("/export")
def export_audit_trail(format: str = Query("json", pattern="^(json|csv)$")):
    events = query.order_by(AuditEvent.timestamp).all()
    records = [_serialize(ev) for ev in events]
    
    cover = {
        "title": "Audit Trail Export",
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_events": len(records),
        "event_type_breakdown": dict(Counter(ev["event_type"] for ev in records)),
        "certifying_officer": "system_auditor@client-domain.com",
        "contact": "audit@client-domain.com",
    }
    
    if format == "csv":
        csv_buf = io.StringIO()
        writer = csv.DictWriter(csv_buf, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
        body = csv_buf.getvalue().rstrip()
        body += f"\n# SHA-256: {hashlib.sha256(body.encode()).hexdigest()}\n"
        return Response(content=body, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=..."})
    
    body = json.dumps({"cover": cover, "events": records}, indent=2, default=str)
    body += f"\n/* SHA-256: {hashlib.sha256(body.encode()).hexdigest()} */\n"
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=..."})
```

The hash comment is stripped client-side. The auditor independently hashes the body to verify integrity.

**Admin CRUD audit logging** — every admin mutation (create, update roles, etc.) must log the actor for compliance:

```python
from db.models import User
from middleware.auth import require_auth, require_roles
from services.audit import append_audit_event

@router.patch("/users/{user_id}/roles")
def update_roles(
    user_id: int,
    req: UpdateRolesRequest,
    actor: User = Depends(require_auth),    # captures who did it
    _: None = Depends(require_roles("super_admin")),  # gates access
    db: Session = Depends(get_db),
):
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    old_roles = _user_to_roles(user)            # snapshot before mutation

    user.roles = ",".join(req.roles)
    db.commit()

    append_audit_event(
        db=db,
        event_type="rbac",                      # event category
        entity="user",
        entity_id=user.id,
        action="roles_updated",
        actor=actor.email,                      # the human who did it
        previous_value={"roles": old_roles},
        new_value={"roles": req.roles},
    )
```

Key points:
- `actor: User = Depends(require_auth)` before `require_roles` — FastAPI caches duped deps
- Always snapshot `previous_value` **before** the mutation
- Use `actor.email` not `actor.id` — the audit log records human-readable identity
- `event_type="rbac"` separates access-control events from financial/distribution audit events
- `append_audit_event()` writes to `AuditEventOld` table (the legacy but actively-used audit log — DO NOT use `AuditEvent`/`audit_service.py` for this; the rest of the codebase uses `services.audit`)

**Test gotcha**: The conftest overrides `require_auth` globally to return `test@client-domain.com` with all roles. Even if the test logs in as `admin@client-domain.com` and passes a JWT, `Depends(require_auth)` inside the endpoint resolves to the overridden user. Assert `actor == "test@client-domain.com"` in data-access-layer audit tests, not the JWT's email.

### 4. Register Router (`apps/api/main.py`)

```python
from routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)
```

### 5. Tests (`apps/api/tests/test_<name>.py`)

**Option A — Manual session** (for tests that need explicit control):
```python
from sqlalchemy.orm import Session
from tests.conftest import test_engine

def test_name(self, client):
    session = Session(test_engine)
    try:
        session.add(Model(...))
        session.commit()
        
        res = client.get("/api/v1/...")
        assert res.status_code == 200
        # ... assertions
    finally:
        session.close()
```

**Option B — Autouse fixture** (for tests where all methods need seed data):
```python
@pytest.fixture(autouse=True)
def seed_data(db_session: Session):
    """Seed events so every test method has data to query."""
    events = [
        AuditEvent(event_type="distribution", entity="work", entity_id="42", action="calculated", actor="system"),
        AuditEvent(event_type="approval", entity="work", entity_id="42", action="approved", actor="admin@client-domain.com"),
    ]
    for ev in events:
        db_session.add(ev)
    db_session.commit()
    yield  # cleanup is handled by setup_db fixture's drop_all
```

The `autouse` fixture runs before every test in the module. Because all sessions share the same SQLite in-memory engine, commits from the fixture's session are immediately visible to the endpoint's session. This avoids repeating seed logic across test methods.

Key points:
- Always use `try/finally` with `session.close()` — test sessions don't auto-close
- Use `test_engine` (imported from conftest) — not `get_engine()` or `get_db`
- Include `rights_holder_name` when creating `DistributionStatement` — it's NOT NULL
- For date fields: use `date(2026, 4, 15)` from `datetime` module
- Test both the ID normalization ("dist-001" and "1") and the raw data path

### 6. Seed Script (`apps/api/scripts/seed_<name>.py`)

For standalone data seeding:
```python
"""Docstring.

Usage: cd apps/api && uv run python -m scripts.seed_dashboard
"""
from db.session import get_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

engine = get_engine()

def _seed():
    with Session(engine) as session:
        # ... create objects
        session.commit()

if __name__ == "__main__":
    _seed()
    print("Done.")
```

- Include `__init__.py` in `scripts/` so `python -m scripts.seed_*` works
- Use `with Session(engine) as session:` pattern — context manager auto-closes
- Support idempotent re-runs (clear existing data first if needed)
- Print summary at the end

## Verification

- Run the specific test file: `uv run pytest tests/test_<name>.py -v`
- Run the full suite: `uv run pytest tests/ -q` — **zero regressions required**
- Quick reg-check: `uv run pytest --tb=short -q` (shorter output, pass/fail only)

## Common Pitfalls

- **NOT NULL on new models**: SQLite enforces NOT NULL strictly. If a column has no default, every test insert must provide a value.
- **`rights_holder_name`**: Required on `DistributionStatement` (NOT NULL, no default).
- **SQLite vs PostgreSQL**: Timezone-aware columns, enum types, and RETURNING clause work differently. Tests use SQLite (`sqlite:///:memory:`) — what passes there may not cover prod Postgres constraints.
- **Import changes break existing tests**: If you add a new import to `routers/dashboard.py` or `db/models.py`, existing tests that depend on those modules will need the updated import path.
`BigInt` or `parseInt`.
- **Avoid `format` as a query parameter name**: `format` is a Python built-in function. While FastAPI handles it, it can cause confusing scoping issues. Use `output_format` or `fmt` instead.
- **`Query(regex=...)` is deprecated in FastAPI 0.136+**: Use `Query(pattern=...)` instead.
