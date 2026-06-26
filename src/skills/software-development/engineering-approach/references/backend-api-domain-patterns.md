# Backend API Domain Patterns

Repeatable API design patterns for ACME FastAPI projects — status transitions,
auto-versioning, batch operations, draft-guards, and entity-level audit logging.

These patterns emerged from the acme-av cue sheet workflow and apply broadly
to any domain entity with lifecycle states, versioned snapshots, or guarded
child mutations.

---

## 1. Status Transition State Machine

**Use when:** An entity has a lifecycle (draft → pending_validation → validated →
approved → archived) and only certain transitions are valid at each step.

### Pattern

```python
from enum import Enum

VALID_STATUSES = [
    "draft",
    "pending_validation",
    "validated",
    "approved",
    "archived",
]

STATUS_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["pending_validation"],
    "pending_validation": ["validated", "draft"],  # allow rejection: send back to draft
    "validated": ["approved", "pending_validation"],
    "approved": ["archived"],
    "archived": [],               # terminal state — no transitions out
}
```

### Validation Helper

```python
class StatusUpdateSchema(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(VALID_STATUSES)}"
            )
        return v

def _validate_transition(current_status: str, new_status: str, entity_name: str = "entity"):
    """Raise 422 with explicit allowed-to list on invalid transitions."""
    allowed = STATUS_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        detail = (
            f"Cannot transition {entity_name} from '{current_status}' to '{new_status}'. "
            f"Allowed transitions from '{current_status}': "
            f"{', '.join(allowed) if allowed else 'none (terminal state)'}."
        )
        raise HTTPException(status_code=422, detail=detail)
```

### Status-Only Patch Endpoint

```python
@router.patch("/{entity_id}/status")
async def update_status(
    entity_id: str,
    body: StatusUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("editor", "admin")),
):
    obj = await service.get(db, entity_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"{entity_name} not found")

    if obj.status == body.status:
        raise HTTPException(
            status_code=422,
            detail=f"{entity_name} is already in '{body.status}' status.",
        )

    _validate_transition(obj.status, body.status, entity_name)

    old_status = obj.status
    obj.status = body.status
    await db.flush()

    await create_audit_log(
        db=db,
        entity_type=entity_name,
        entity_id=str(obj.id),
        action="status_changed",
        old_values={"status": old_status},
        new_values={"status": body.status},
        actor_id=current_user.id,
    )
    await db.commit()
    await db.refresh(obj)
    return obj
```

### What makes this pattern good

- **Single source of truth** for all valid transitions — the dict
- **Helpful errors** — the error tells the caller exactly which transitions are available
- **Zero SQL gymnastics** — just compare and assign
- **Terminal states are explicit** — empty transition list means "no changes allowed"
- **Validation at the field level** (Pydantic validator) catches invalid status values before the transition check

---

## 2. Auto-Versioning

**Use when:** Each change to an entity should increment a version number and
preserve a snapshot of the previous state.

### Pattern

```python
async def _with_version_increment(
    db: AsyncSession,
    obj,
    service,
    actor_id: str,
):
    """Increment version and snapshot before mutation.

    Snapshots the current state BEFORE changes, so the version history
    records what was changed away from.
    """
    old_version = obj.version_number
    obj.version_number = (obj.version_number or 0) + 1

    # Snapshot the state BEFORE mutation
    snapshot = CueSheetVersion(
        cue_sheet_id=obj.id,
        version_number=old_version,
        status=obj.status,
        data=obj.model_dump() if hasattr(obj, "model_dump") else _serialize(obj),
    )
    db.add(snapshot)
    await db.flush()

    await create_audit_log(
        db=db,
        entity_type="cue_sheet",
        entity_id=str(obj.id),
        action="version_incremented",
        old_values={"version": old_version},
        new_values={"version": obj.version_number},
        actor_id=actor_id,
    )
    return obj
```

### Rules

- **Snapshot before mutation** — the version captures what WAS, not what WILL BE
- **One version per mutation** — do not version for internal field updates (e.g. sort_order changes happen in the background)
- **Version number is user-visible** — what an auditor expects to see on a report

### Version Tracking Table

```python
class CueSheetVersion(Base):
    __tablename__ = "cue_sheet_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cue_sheet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cue_sheets.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

---

## 3. Batch Create

**Use when:** Clients need to create multiple child entities under one parent in
a single request, with a single version increment.

### Pattern

```python
class BatchCreateSchema(BaseModel):
    items: list[CueEntryCreate]

@router.post("/{parent_id}/entries/batch", status_code=201)
async def batch_create(
    parent_id: str,
    body: BatchCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("editor", "admin")),
):
    parent = await parent_service.get(db, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")

    # Draft guard (see pattern 5)
    if parent.status != "draft":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot add entries when parent is '{parent.status}'. Must be in 'draft' status.",
        )

    new_entries = []
    last_order = await _get_max_sort_order(db, parent_id)
    for item in body.items:
        entry = CueEntry(
            cue_sheet_id=parent.id,
            sort_order=last_order + 1,
            **item.model_dump(),
        )
        last_order += 1
        new_entries.append(entry)
        db.add(entry)

    # Single version increment for the batch (not per-item)
    parent.version_number = (parent.version_number or 0) + 1

    await db.flush()

    # One audit log entry for the batch
    await create_audit_log(
        db=db,
        entity_type="cue_entry",
        entity_id=str(parent.id),
        action="batch_created",
        new_values={"count": len(new_entries), "ids": [str(e.id) for e in new_entries]},
        actor_id=current_user.id,
    )

    await db.commit()
    for e in new_entries:
        await db.refresh(e)
    return new_entries
```

### Rules

- **One version increment per batch** — not per item
- **One audit log entry per batch** — the count and IDs suffice
- **Auto-increment sort_order** — start from the current max + 1
- **Draft guard** — child entities should not be modifiable in non-draft states

---

## 4. Reorder

**Use when:** Clients need to reposition child entities (entries, items, steps)
within a parent.

### Pattern

```python
class ReorderSchema(BaseModel):
    entry_ids: list[str]  # ordered list of IDs — first item gets sort_order 0

@router.patch("/{parent_id}/entries/reorder")
async def reorder_entries(
    parent_id: str,
    body: ReorderSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("editor", "admin")),
):
    parent = await parent_service.get(db, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")

    if parent.status != "draft":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot reorder entries when parent is '{parent.status}'. Must be in 'draft' status.",
        )

    # Fetch all entries for this parent in one query
    stmt = select(CueEntry).where(CueEntry.cue_sheet_id == parent.id)
    result = await db.execute(stmt)
    existing_entries = {str(e.id): e for e in result.scalars().all()}

    # Validate all IDs exist
    for eid in body.entry_ids:
        if eid not in existing_entries:
            raise HTTPException(
                status_code=422,
                detail=f"Entry '{eid}' not found in this parent.",
            )

    # Reassign sort_order in provided order
    for i, eid in enumerate(body.entry_ids):
        existing_entries[eid].sort_order = i

    # Single version increment for the reorder
    parent.version_number = (parent.version_number or 0) + 1

    await create_audit_log(
        db=db,
        entity_type="cue_entry",
        entity_id=str(parent.id),
        action="reordered",
        actor_id=current_user.id,
    )

    await db.commit()
    return {"message": "Reordered", "count": len(body.entry_ids)}
```

### Rules

- **Must include ALL child IDs** — partial reorder is a different operation
- **One version increment** — not per-item
- **Bulk-fetch** — don't N+1 by fetching each entry individually
- **Draft guard** — reordering is a content operation, not valid in finalized states

---

## 5. Draft-Guard

**Use when:** Child entities (entries, items, line items) should only be
modifiable when the parent is in a draft or editable state.

### Pattern

```python
async def _require_draft(parent, action: str = "modify"):
    """Raise 422 if parent is not in draft status."""
    if parent.status != "draft":
        detail = (
            f"Cannot {action} entries when parent is '{parent.status}'. "
            f"Set parent status back to 'draft' before making changes."
        )
        raise HTTPException(status_code=422, detail=detail)
```

### Application

```python
@router.delete("/{parent_id}/entries/{entry_id}")
async def delete_entry(
    parent_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("editor", "admin")),
):
    parent = await parent_service.get(db, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found")
    await _require_draft(parent, "delete")
    # ... proceed with deletion
```

### Extension: Draft-or-Revert

If your workflow allows reverting a finalized entity back to draft
(transition: validated → draft, approved → draft), the draft-guard
automatically unblocks when the status changes.

---

## 6. Entity-Level Audit Logging

**Use when:** Every mutation (create, update, delete, status change, batch
operation) must be logged for compliance.

### Pattern

```python
async def create_audit_log(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    actor_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values=old_values or {},
        new_values=new_values or {},
        actor_id=actor_id,
        metadata=metadata or {},
    )
    db.add(entry)
    return entry
```

### Call sites

```python
# Create
await create_audit_log(
    db=db, entity_type="cue_sheet", entity_id=str(obj.id),
    action="created", new_values={"title": body.title},
    actor_id=current_user.id,
)

# Update
await create_audit_log(
    db=db, entity_type="cue_sheet", entity_id=str(obj.id),
    action="updated", old_values=old_dict, new_values=changed_fields,
    actor_id=current_user.id,
)

# Delete (soft)
await create_audit_log(
    db=db, entity_type="cue_sheet", entity_id=str(obj.id),
    action="deleted", old_values={"status": obj.status},
    actor_id=current_user.id,
)
```

### Rules

- **Log BEFORE commit** — `db.add(entry)` + `await db.flush()` so the audit
  entry participates in the same transaction. If the mutation is rolled back,
  the audit entry rolls back too.
- **One audit entry per semantic action** — a batch create of 10 items gets one
  "batch_created" entry with a count, not 10 individual entries.
- **Actor always included** — `current_user.id` or `actor_id` field. For
  system-initiated operations, use a system user ID.
- **`old_values` always before mutation** — snapshot the old state before
  applying changes. For creates, `old_values` is empty.

### AuditLog Model

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
```

---

## When to Use Which Pattern

| Pattern | Trigger | Alternative |
|---|---|---|
| Status Transition | Entity has a lifecycle with named states and guard rails | Freeform `status` field (no validation) — only for simple 2-state entities |
| Auto-Versioning | Auditors need a snapshot trail | Just a `version_number` column without snapshot table — cheaper but less audit-proof |
| Batch Create | Client sends multiple items at once (wizard step, bulk import) | Single-item POST loop — simpler but 10x the network round-trips |
| Reorder | User drags items or submits an ordered list | `sort_order = ID` in the update endpoint — simpler but no validation |
| Draft-Guard | Child entities only modifiable in parent draft state | Let users edit any time — simpler but data integrity risk |
| Entity Audit Log | Compliance requirement (CISAC, KOMCA) | ORM event listeners — automatic but harder to understand and test |

## Related

- `backend-api-feature-workflow.md` — the general model→router→tests sequence
- `backend-api-test-patterns.md` — async test infrastructure for these patterns
- `sqlalchemy-patterns` — model patterns including `metadata` column alias
