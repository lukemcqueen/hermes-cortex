---
name: test-seed-uniqueness
version: 1.0.0
category: software-development
description: "Ensure test seed data never causes unique constraint violations — UUID-based, timestamp-based, counter-based, or Faker patterns for any field with a UNIQUE index, primary key, or slug constraint."
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, seed-data, factories, fixtures, database, uniqueness, pytest, factory-boy]
    related_skills: [change-test-loop, subagent-driven-development, systematic-debugging]
---

# Test Seed Data — Uniqueness Discipline

## The Problem

Every test needs seed data. Agents instinctively write:

```python
user = User.objects.create(email="alice@example.com", username="alice")
```

This works *once*. On the next test run, or when tests run in parallel, or when a second test also creates an alice:

```
django.db.utils.IntegrityError: duplicate key value violates unique constraint
```

The agent didn't do anything wrong — it just picked a *natural-looking* value for a field that happens to have a `UNIQUE` constraint. The database doesn't care how pretty the data is; it cares about uniqueness.

## The Rule

**Every value inserted into a uniquely-constrained field MUST be dynamically unique at runtime.**

Hardcoded strings in seed data are only safe for:
- Non-unique fields (e.g., `display_name`, `bio`, `age`)
- Enum-like fields (e.g., `status="active"`, `role="admin"`)
- Reference data that's de-duplicated by the test setup (e.g., loaded once from JSON)

Everything else — emails, usernames, slugs, external IDs, phone numbers, API keys, invite codes, profile handles — gets the dynamic treatment.

## Failure Detection

When you see any of these in test output, stop and fix the seed data:

| Error Pattern | Likely Source |
|---|---|
| `duplicate key value violates unique constraint` | PostgreSQL |
| `UNIQUE constraint failed` | SQLite |
| `E11000 duplicate key error` | MongoDB |
| `Duplicate entry '...' for key` | MySQL |
| `unique constraint "..." violated` | Generic ORM |
| `already exists.` | Rails / Active Record |
| `IntegrityError: (1062, "Duplicate entry` | MySQL via ORM |

**First debugging step when seeing these:** Look at the test's seed data or fixtures. Find the field whose value is hardcoded. Make it dynamic.

## Dynamic Uniqueness Patterns

### Pattern 1 — UUID (Best for Primary Keys & External IDs)

```python
import uuid

def test_create_user():
    user = User.objects.create(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4()}@example.com",
    )
```

**Use when:** The value is never shown to a human in tests. IDs, tokens, API keys.

### Pattern 2 — Timestamp (Best for Ordered, Human-Readable Slugs)

```python
from datetime import datetime

slug = f"test-project-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
```

**Use when:** You want roughly ordered test data, or the field appears in logs/output.

### Pattern 3 — Counter (Best for Sequential Batch Tests)

```python
from itertools import count

_user_counter = count(1)

def make_user(email=None):
    n = next(_user_counter)
    return User.objects.create(
        email=email or f"user{n}@example.com",
        username=f"user{n}",
    )
```

**Use when:** Creating multiple objects in a loop or parameterized test.

### Pattern 4 — Random Hex Suffix (Best for Short, Readable Values)

```python
import secrets

suffix = secrets.token_hex(4)  # 8-char hex, e.g. "a3f1b2c8"
email = f"alice-{suffix}@example.com"
```

**Use when:** You want something shorter than a full UUID but still practically unique.

### Pattern 5 — Faker (Best for Realistic, Human-Readable Data)

```python
from faker import Faker
fake = Faker()

email = fake.unique.email()
name = fake.unique.name()
```

**Use when:** Tests need realistic-looking data, or you're already using Faker. The `.unique` property ensures no collisions within the generator session.

### Pattern 6 — factory_boy Sequences (Best for Complex Fixtures)

```python
import factory

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")

# Usage — each call gets a unique email/username
user1 = UserFactory()
user2 = UserFactory()
```

**Use when:** You have many fields and many tests. factory_boy Sequences are the gold standard — zero boilerplate, fully automatic, works with `SubFactory`.

### Pattern 7 — pytest Fixture with Scope

```python
import pytest

@pytest.fixture
def unique_user():
    suffix = secrets.token_hex(4)
    user = User.objects.create(
        email=f"test-{suffix}@example.com",
        username=f"test-{suffix}",
    )
    yield user
    user.delete()
```

**Use when:** Many tests need a user and you want DRY setup with guaranteed cleanup.

## Complementary Anti-Patterns (What NOT to Do)

| ❌ Anti-Pattern | Why It Fails | ✅ Fix |
|---|---|---|
| `email="alice@example.com"` | Second test or re-run collision | `f"alice-{uuid.uuid4()}@example.com"` |
| `User.objects.create()` without cleanup in non-transactional tests | Data leaks between tests | Use `@pytest.mark.django_db(transaction=True)` or fixture with teardown |
| `User.objects.all().delete()` at start of test | Race condition in parallel tests | Use `secrets.token_hex()` or factory |
| Copy-pasting seed data across test files | Same hardcoded values in multiple files | Extract a shared factory or fixture |
| Using `datetime.now()` at second precision | Collision when tests run in same second | Use microsecond precision (`%f`) or UUID |
| `UserFactory()` without unique guarantees on special fields | Factory inherits hardcoded defaults | Override with `Sequence` or pass unique values |

## Model-Specific Ref Detection

Before writing seed data, identify the model's unique constraints:

```python
# Django
class Meta:
    unique_together = [["organization", "slug"]]
    constraints = [
        models.UniqueConstraint(fields=["tenant", "external_id"], name="unique_tenant_external")
    ]

# SQLAlchemy
__table_args__ = (
    UniqueConstraint("tenant_id", "external_id", name="uq_tenant_external"),
)

# Prisma / Rails / etc. — check schema.rb, schema.prisma, or migrations
```

**Fields to always make unique:**
- `id` / `pk` (unless using auto-increment — then let the DB handle it)
- `email`
- `username`
- `slug`
- `external_id` / `stripe_id` / `github_id` — any third-party ID
- `api_key` / `token` / `secret`
- `invite_code` / `referral_code`
- `phone_number`
- `handle` / `display_handle` / `profile_url`
- Any field with `unique=True`, `unique_together`, or `UniqueConstraint`

## Integration with change-test-loop

When the RED phase fails not because the test logic is wrong but because of a unique constraint violation:

1. Don't change the test logic — the test is correct
2. Fix the **seed data** to use a dynamic uniqueness pattern
3. Re-score RED: the test should now fail for the intended reason (feature missing)

When GREEN phase passes but seed data has hardcoded unique fields: this is a REFACTOR concern — dynamize the seed data while keeping tests green.

## Verification

Before declaring seed data done:

```
✅ Every uniquely-constrained field uses a dynamic pattern (UUID, timestamp, counter, or Faker)
✅ No hardcoded alice@example.com, testuser, demo-slug, or similar in seed data
✅ Tests pass on re-run without cleanup
✅ Tests pass in parallel (xdist or similar)
✅ factory_boy fixtures use Sequence() for all unique fields
✅ Non-unique fields are still readable/human-friendly (don't over-randomize)
```
