# Domain Calculation Engine Patterns

Recurring pattern for building domain calculation engines in acme-royalty.

## Pattern

```
domain/<name>.py       # Pure calculation functions, dataclass results
tests/test_domain_<name>.py  # 20-30 tests, no DB dependency
services/<name>.py     # Optional: service layer wrapping domain + DB lookups
routers/<name>.py      # Optional: API endpoint
```

## Rules

1. **Pure functions only** — no DB calls, no I/O, no side effects. The domain module is a collection of pure functions with dataclass results. DB lookups happen in the service layer.
2. **BIGINT-safe** — all monetary amounts stored as `int` (KRW). No floats, no Decimal, no Numeric.
3. **Basis points for percentages** — rates stored as BPS (1 bps = 0.01%). 10000 = 100%. Conversion: `amount * bps // 10000`.
4. **Line-item metadata** — every calculation result includes per-step details with labels, descriptions, and running totals for the deduction narrative.
5. **Versioned** — every result carries a `pipeline_version` or `rule_version` string for audit reproducibility.
6. **Deterministic** — same inputs always produce same outputs. Largest-remainder method with deterministic tiebreakers.
7. **Dataclass results** — use `@dataclass` for all result types. No Pydantic, no SQLAlchemy models in domain code.
8. **Comprehensive tests** — 20-30 tests covering: standard cases, edge cases (zero, negative), boundary values, determinism, large amounts, custom rate overrides, line item structure.

## Examples

### Split Rules (Story 2.1)
- `domain/split_rules.py`: `calculate_split(work_id, pool_total, creators) -> SplitResult`
- Role fractions hardcoded: composer 12/20 (60%), lyricist 6/20 (30%), arranger 2/20 (10%)
- Within-role split: equal share with largest-remainder allocation
- Validates roles, rejects unknown roles

### Deduction Pipeline (Story 2.2)
- `domain/deduction.py`: `calculate_deductions(gross_amount, *) -> DeductionResult`
- Steps: commission → management fee (tiered) → withholding tax → net
- Custom rate overrides: `commission_bps`, `withholding_bps`, `treaty_bps`
- Non-resident vs domestic tax treatment

## Service-Layer Wrapper (Distribution Engine Pattern)

When a calculation engine has two distinct execution modes (pure calculation vs DB-backed run), factor them as separate entrypoints in a single service module.

### Two-Path Pattern

| Path | Endpoint | Split Method | Persistence | Use Case |
|------|----------|-------------|-------------|---------|
| **Calculate** (dry-run) | `POST /calculate` | Role-based (KOMCA fractions) | None | Verify amounts before run |
| **Run** (DB-backed) | `POST /run` | Ownership-based (share_percentage BPS) | Creates Run + Statements + Audit log | Full distribution run |

### When to use which path

- **Calculate** — requires explicit role input from the caller (composer/lyricist/arranger). The domain's KOMCA split function is called directly. Used for verification and what-if analysis.
- **Run** — queries `OwnershipSplit` table for `share_percentage` (basis points). Applies proportional split: `pool_total * share_percentage // 10000`. Last owner gets remainder to prevent integer rounding drift. Stores results in DB.

### Rationale for separate paths

The KOMCA split engine requires role information (composer 12/20, lyricist 6/20, arranger 2/20), which is not available from the DB since the Work model was moved to acme-metadata (ADR-011). The `OwnershipSplit` table only has `share_percentage` — no role column. Until role metadata is integrated via acme-metadata, the DB-backed run path uses ownership-based proportional splits.

### Deduction Pipeline Clone Pattern

The service layer should NOT import domain-layer dataclass types for internal use. Instead, define a lightweight internal class that mirrors the deduction pipeline:

```python
class _DeductionItem:
    __slots__ = ("step", "label", "rate_description", "amount", "running_total")
    def __init__(self, step, label, rate_description, amount, running_total):
        ...

def _apply_deductions(gross: int, *, commission_bps, withholding_bps, ...) -> list[_DeductionItem]:
    """Matches domain.deduction.calculate_deductions() logic."""
    running = gross
    # Step 1: Commission
    # Step 2: Management fee (tiered)
    # Step 3: Withholding tax / non-resident tax
    return items
```

This avoids coupling the DB-backed run path to the domain module's import tree while keeping the same calculation logic.

### Deduction Pipeline Steps

| Step | Default Rate | Notes |
|------|-------------|-------|
| 1. Society Commission | 8% (800 bps) | On gross |
| 2. Management Fee | 0% (<1M), 2% (1M-10M), 3% (>10M) | On gross |
| 3. Withholding Tax | 3.3% domestic, 22% non-resident | On gross; treaty override for non-resident |

### Ownership-Based Proportional Split

```python
for i, owner in enumerate(owners):
    if i == len(owners) - 1:
        gross = pool_total - allocated_gross  # remainder avoids rounding drift
    else:
        gross = pool_total * owner["share_percentage"] // 10000
    allocated_gross += gross
```

The last-owner-gets-remainder pattern is essential. Without it, integer division (`// 10000`) on each share can leave 1-3 KRW unallocated due to truncation.

## Test File Naming

Domain test files use `test_domain_<name>.py` prefix (NOT `test_<name>.py`) to avoid confusion with DB-backed tests. The conftest's `@pytest.fixture(autouse=True)` for `setup_db()` only applies to filenames starting with `test_` — `test_domain_*` files don't need a DB connection.

## Service-Layer Test Fixtures

When creating seed data for service-layer integration tests (DB-backed), watch for these recurring pitfalls:

- **Enum-backed columns.** If a model column uses a `TypeDecorator` backed by an enum (e.g. `OwnershipSplit.split_type` uses `RightTypeColumn`), pass only valid enum string values like `"performance"` or `"mechanical"`. Invalid values (like `"original"`) raise `ValueError`.
- **FK chains.** Models with `ForeignKey` constraints (e.g. `DistributionAmount → ingestion_jobs.id`) require the referenced record to exist first. Seed the parent table (`IngestionJob`) before child records.
- **VARCHAR length.** Check column definitions for max length. `DistributionStatement.period` is `VARCHAR(20)` — use `"2026-Q1"` format, not full ISO dates like `"2026-01-01/2026-03-31"`.
- **No run_id FK.** `DistributionStatement` has no `run_id` foreign key. Queries cannot be scoped by distribution run. For test assertions, filter by `rights_holder_id` or accept multi-run results. A single creator appearing in multiple works produces multiple statements (e.g. Alice in work 100 and work 200 = 2 statements).
