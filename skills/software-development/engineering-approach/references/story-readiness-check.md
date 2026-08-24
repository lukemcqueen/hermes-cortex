# Story Readiness Check Methodology

Systematic pre-build verification that a story/phase is ready to implement.
Run before starting any new slice or phase.

## The 5-Axis Check

### 1. PRD & Domain Alignment (hc-elicit lens)

Verify the PRD is current and the story aligns with it:

| Check | What to look for |
|-------|-----------------|
| PRD version | Is the PRD the current version? Revision history visible? |
| hc-party review | Does the PRD explicitly say it went through architecture review? |
| Story ↔ PRD mapping | Does every story requirement trace to a PRD section? |
| Cross-codebase audit | Was client/Rails codebase reviewed to validate the model? |
| Story spec completeness | Does the slice spec have endpoints, schemas, validation rules, edge cases? |

### 2. Architecture Review (hc-party lens)

Verify architectural decisions are documented:

| Check | What to look for |
|-------|-----------------|
| ADRs | Are there ADRs covering the domain (contracts, shares, matching, etc.)? |
| Trade-off records | Are risks documented with tier ratings (🔴/🟡/🟢)? |
| Consistency | Do the ADRs agree with each other and with the PRD? |

### 3. Data Model Readiness

Verify the DB schema and SQLAlchemy models exist and are consistent:

| Check | What to do |
|-------|-----------|
| Tables exist | Search both `01-schema.sql` and `app/models/` for each table |
| FK constraints | Verify foreign keys point to existing tables |
| Unique constraints | Check UNIQUE clauses match story spec |
| Model relationships | Verify `back_populates` pairs exist on both sides |
| Seed data | If the story needs reference data (territories, societies, lookups), verify seeds exist |
| Migration | Check `alembic/versions/` includes the table |

### 4. Auth & API Infrastructure

Verify the plumbing the story needs is already wired:

| Check | What to look for |
|-------|-----------------|
| CRUD base | Does `CRUDBase` support pagination, filtering, search? |
| Auth deps | Are `require_permission`, `require_min_role`, `get_current_user` available? |
| Router pattern | Is the existing router pattern importable and proven? |
| Pydantic schema pattern | Are there established schema patterns (Base/Create/Update/Response)? |
| Router registration | Is `app/routers/` directory structure in place? |
| Main.py wiring | Is the router import/include pattern established? |
| Permissions | Does `rbac.py` define the permission strings the story needs? |
| Versioning | Is the `/api/v1/` prefix used consistently? |

### 5. Gap Analysis

Compile a gap matrix and categorize each gap:

| Severity | Label | Impact |
|----------|-------|--------|
| 🚫 BLOCKER | Missing table or model | Cannot implement without pre-work |
| ⚠️ GAP | Missing relationship | Reduced functionality but not blocked |
| 💡 NICE | Missing migration | Tables exist in SQL but not tracked by Alembic |
| ℹ️ NOTE | Missing service/endpoint | This IS the work to be done in the phase |

**Gap resolution:**
- 🚫 BLOCKER → Fix immediately before starting the phase
- ⚠️ GAP → Fix as pre-work or document as scoped out
- 💡 NICE → Include in the build
- ℹ️ NOTE → This is the build scope (not a gap)

## Example

For Phase 1C (Contracts + Shares), the gap analysis was:

| Table/Feature | DB Schema | SQLAlchemy Model | Alembic | Status |
|---------------|-----------|------------------|---------|--------|
| contracts | ✅ | ✅ | ✅ | Ready |
| contract_territories | ✅ | ✅ | ✅ | Ready |
| works_contract_shares | ✅ | ✅ | ✅ | Ready |
| societies | ✅ | ✅ | ✅ | Ready |
| territories | ✅ | ✅ (via `__init__`) | ✅ | Ready |
| member_publishers | ❌ | ❌ | ❌ | ⚠️ GAP — added as pre-work |
| Contract service | N/A | N/A | N/A | ℹ️ NOTE — this is the build |
| Share service | N/A | N/A | N/A | ℹ️ NOTE — this is the build |

## Reference

Used in this session before Phase 1C of acme-works. The check confirmed:
- PRD v2.0 → ✅ (revised after hc-party + hc-elicit)
- 8 ADRs → ✅
- All Phase 1C tables in schema → ✅ (except member_publishers, added as pre-work)
- Auth/RBAC infrastructure → ✅
- CRUD patterns established → ✅

**Verdict:** READY (with one pre-work fix: MemberPublisher association).
