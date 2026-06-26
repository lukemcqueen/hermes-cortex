# Echo Korean Test Patterns

## FakeUser must match _user_to_response

The auth router's `_user_to_response()` function manually maps `User` model fields to `UserResponse` schema fields:

```python
def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        native_language=user.native_language,
        target_language=user.target_language,
        level=user.level,
        is_verified=user.is_verified,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
```

When writing HTTP integration tests with `httpx.AsyncClient` + `app.dependency_overrides`, the FakeUser class passed as `get_current_user` must implement EVERY field accessed by `_user_to_response`. If you add a field to the schema and mapper, all FakeUser classes across all test files break.

### Correct FakeUser template

```python
class FakeUser:
    id = user_id
    email = "test@test.com"
    display_name = "Test User"
    native_language = "en"
    target_language = "ko"
    level = "beginner"
    is_verified = False
    is_active = True
    is_admin = False
    created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    updated_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
```

Note: `created_at` and `updated_at` must be `datetime` objects, not `None` — Pydantic validates them.

### Affected test files

When adding a new field to `_user_to_response`:
1. Update `app/schemas/auth.py` — `UserResponse` schema
2. Update `app/routers/auth.py` — `_user_to_response()` mapper
3. Update ALL FakeUser classes in `app/tests/test_*.py` files
4. Update frontend `UserResponse` interface in `apps/web/src/lib/auth-context.tsx`

### Detective work when tests fail

If a test fails with `AttributeError: 'FakeUser' object has no attribute 'X'` or `ValidationError` about a missing field, the field was added to `_user_to_response` but not all FakeUser classes were updated. Run:

```bash
grep -rn "class FakeUser" apps/api/app/tests/
```

to find all locations that need updating.
