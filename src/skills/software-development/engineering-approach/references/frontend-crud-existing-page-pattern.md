# Adding CRUD to an Existing Page (acme-royalty)

When an existing page renders a saved/list view but lacks edit/delete, follow this pattern for the full stack.

## Backend

### PUT endpoint — regenerate and update

```python
@router.put("/{entity_id}")
def update_entity(
    entity_id: int,
    body: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Regenerate and update with new parameters."""
    entity = db.query(E entity).filter(E entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Not found")

    # Recompute result with new params
    params = InputClass(
        name=body.get("name", entity.name),
        field1=body.get("field1", 0.0),
        field2=body.get("field2", 0.0),
    )
    result = compute_fn(db, params)

    # Update entity fields
    entity.field1 = result.field1
    entity.field2 = result.field2
    entity.result_json = json.dumps(result.some_field)
    db.commit()
    db.refresh(entity)

    return {"id": entity.id, **result_to_dict(result)}
```

### DELETE endpoint

```python
@router.delete("/{entity_id}")
def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
):
    entity = db.query(E entity).filter(E entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(entity)
    db.commit()
    return {"status": "deleted", "id": entity_id}
```

## Frontend API Client (`lib/api.ts`)

Add update and delete functions with the same shape as existing CRUD functions:

```typescript
export function updateXxx(id: number, body: Record<string, unknown>): Promise<XxxProjection & { id: number }> {
  return fetchJSON(`/xxx/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export function deleteXxx(id: number): Promise<{ status: string; id: number }> {
  return fetchJSON(`/xxx/${id}`, {
    method: 'DELETE',
  });
}
```

Also import and export `getXxx(id)` if not already available — used by the edit handler to load existing assumptions.

## Page Component State

Add these pieces to the existing page:

```typescript
const [editingId, setEditingId] = useState<number | null>(null);
```

### Edit handler — loads detail, populates form

```typescript
const handleEdit = async (item: XxxSummary) => {
  setError(null);
  setProjection(null);  // clear current result
  setSavedId(null);
  setEditingId(item.id);
  try {
    const detail = await getXxx(item.id);
    const a = detail.assumptions;
    if (a) {
      if (a.field1 !== undefined) setField1(a.field1);
      if (a.field2 !== undefined) setField2(a.field2);
    }
  } catch {
    setError('Failed to load');
    setEditingId(null);
  }
};
```

### Save/Update handler — dispatches to create or update

```typescript
const handleSave = async () => {
  setSaving(true);
  try {
    const body = { field1, field2, ... };
    let result;
    if (editingId !== null) {
      result = await updateXxx(editingId, body);
    } else {
      result = await saveXxx(body);
    }
    setSavedId(result.id);
    setEditingId(null);
    // Refresh the list
    listXxx().then(setSavedList).catch(() => {});
  } catch (e: any) {
    setError(e.message);
  } finally {
    setSaving(false);
  }
};
```

### Delete handler — confirm + remove from list

```typescript
const handleDelete = async (id: number) => {
  if (!window.confirm(t('deleteConfirm'))) return;
  try {
    await deleteXxx(id);
    setSavedList(prev => prev.filter(item => item.id !== id));
    if (editingId === id) {
      setEditingId(null);
      setProjection(null);
      setSavedId(null);
    }
  } catch (e: any) {
    setError(e.message);
  }
};
```

### Save button — conditional label

```tsx
<button onClick={handleSave} disabled={saving}>
  {saving ? t('saving') : editingId !== null ? t('update') : t('save')}
</button>
{editingId !== null && (
  <button onClick={() => { setEditingId(null); setProjection(null); setSavedId(null); setError(null); }}>
    {t('cancel')}
  </button>
)}
```

### Actions column — Edit + Delete buttons

```tsx
<td className="...">
  <div className="flex items-center justify-end gap-1.5">
    <button onClick={() => handleEdit(item)} className="px-2 py-0.5 rounded border border-gray-300 text-[10px] ...">
      {t('edit')}
    </button>
    <button onClick={() => handleDelete(item.id)} className="px-2 py-0.5 rounded border border-red-200 text-[10px] text-red-500 ...">
      {t('delete')}
    </button>
  </div>
</td>
```

## i18n Keys

Both `en.json` and `ko.json` under the same namespace:

```json
{
  "edit": "Edit",
  "delete": "Delete",
  "update": "Update",
  "cancel": "Cancel",
  "deleteConfirm": "Are you sure you want to delete this?"
}
```

Korean:
```json
{
  "edit": "편집",
  "delete": "삭제",
  "update": "업데이트",
  "cancel": "취소",
  "deleteConfirm": "이 항목을 삭제하시겠습니까?"
}
```

## Test Mock Expansion

When adding these functions to an existing page, the existing test mocks need three additions:

### 1. API function mocks

Add to the `vi.mock('@/lib/api', ...)` block:

```typescript
updateXxx: vi.fn(() => Promise.resolve({ ...mockProjection, id: 1 })),
deleteXxx: vi.fn(() => Promise.resolve({ status: 'deleted', id: 1 })),
getXxx: vi.fn(() => Promise.resolve({ ...mockProjection, id: 1, status: 'active', assumptions: {} })),
```

### 2. i18n key mocks

Add to the mockT key map:

```typescript
'edit': 'Edit',
'delete': 'Delete',
'update': 'Update',
'cancel': 'Cancel',
'deleteConfirm': 'Are you sure?',
```

### 3. Verify

All existing tests must still pass — the new mocks should only add coverage, never break existing assertions:
```bash
pnpm vitest run --reporter=verbose src/app/\[locale\]/xxx/__tests__/
```
