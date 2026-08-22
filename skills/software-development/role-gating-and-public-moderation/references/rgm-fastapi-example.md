# Example FastAPI reference implementation

Concrete shapes from the Example build (Next.js web + FastAPI/uv + Postgres) that
instantiate the patterns in SKILL.md. Reuse the shapes, adapt names.

## Public register forces seeker
`example_api/v1/auth.py`
```python
class RegisterRequest(BaseModel):
    # NOTE: no `role` field ON PURPOSE. Public registration can never request a
    # privileged role; a client-supplied role is silently dropped by pydantic.
    email: str
    password: str
    pseudonym: str | None = None
...
role = "seeker"  # always — privileged roles come from the seed.
```

## Role gates (FastAPI dependencies)
Fully gated surface = one dependency per privilege tier; each calls
`get_current_user` (401 if anon) then raises 403 for the wrong role.
```python
async def get_current_evangelist(request, db=Depends(get_db)) -> User:
    user = await get_current_user(request, db)
    allowed = {r.strip() for r in settings.evangelist_allowed_roles.split(",")}  # "evangelist,admin"
    if user.role not in allowed:
        raise HTTPException(403, "Evangelist or admin role required")
    return user  # <-- MUST be present (see SKILL.md pitfall #6)

async def get_current_warrior(request, db=Depends(get_db)) -> User:
    user = await get_current_user(request, db)
    if user.role not in ("warrior", "admin"):
        raise HTTPException(403, "Prayer warrior or admin role required")
    return user
```
Admin-only endpoints use role == "admin" strictly (an evangelist is 403).

## Seed / test bootstrap helper (the sanctioned path)
`example_api/seed.py`
```python
def ensure_user(session, email, password, role, *, force_role=False):
    user = session.query(User).filter(User.email == email).first()
    if user is None:
        return User(email=..., password_hash=bcrypt.hashpw(...), role=role), True
    if force_role:  # demo / tests only — never in prod-safe default
        user.role = role
        user.password_hash = bcrypt.hashpw(...)
    return user, False
```
- `seed_default()` creates the FIRST admin from `Example_ADMIN_EMAIL`/`Example_ADMIN_PASSWORD`,
  idempotent, fails closed (exit 1) when creds absent. Never demotes/alters
  existing rows (force_role=False).
- `seed_demo()` refuses on prod unless `Example_ALLOW_DEMO_ON_PROD=1`; idempotent;
  only writes sample rows on a FRESH seed (probe a `created_evangelist` flag).
- Tests import the same helper: `ensure_user(db, email, pw, "evangelist", force_role=True)` + commit, then login via HTTP. Do NOT create privileged test accounts through the public register.
- CLI: `python -m example_api.seed --mode default|demo`. Wire to `./run seed <mode>`.

## PII-tiered community read
Peer endpoint returns ONLY non-PII:
```python
@router.get("/community")
async def warrior_community(current_user=Depends(get_current_warrior), db=Depends(get_db)):
    warriors = db.query(User).filter(User.role == "warrior", User.id != current_user.id).all()
    return [{"id": w.id, "pseudonym": w.pseudonym, "country": w.country} for w in warriors]
```
Admin endpoint returns full PII (email etc.) gated by `get_current_admin`.
Own-profile returns the caller's own full PII.

## UGC moderation lifecycle
A user-submitted public entry (`evangelist_churches`) carries: `status`
(pending|approved|rejected|needs_info), `source` (submitted|scraped|manual),
submitter email, `is_cult`, `image_approval_status`. Rules:
- Public browse filters `status == approved AND is_cult == False`. Cult-flagged
  rows stay hidden even if later approved.
- Anonymous POST creates `status = pending` (hidden); owner review endpoint
  `POST /admin/churches/{id}/review {decision: approve|reject|needs_info,
  mark_cult, note}` moves the state.
- Editor (evangelist/admin) POST creates `status = approved` directly.
- Blocklist: `CULT_BLOCKLIST` set; `_is_cult(name, denomination)` lower-matches;
  on match auto-reject + flag + return `{"awareness": True, "help_url": "/cults"}`.
- Public serializer (`_public_fields`) excludes submitter/status/cult/source/review.
- Separate readonly awareness endpoint `GET /cults/awareness` serves an editable
  notice + resources + an anonymous questionnaire; NOT expected to be stored.

## Mechanics that mattered
- **Alembic on a moved/venv'd repo**: the `alembic` bin shebang went stale.
  Run migrations via `uv run python -m alembic upgrade head` (module form
  avoids the bad interpreter), and for a dockerized Postgres pass the host
  URL: `DATABASE_URL='postgresql://user:pass@localhost:<HOST_PORT>/db'`.
- **Pyright false positives**: with the codebase venv active elsewhere, Pyright
  reports every third-party import (bcrypt/sqlalchemy/pytest/alembic) as
  unresolvable. Lint status is still "ok"; ignore when the venv has them.
- **`__fields_map__` vs `model_fields`**: pydantic v2's public field-map is
  `Model.model_fields` (`.keys()`), not `__fields_map__`.
