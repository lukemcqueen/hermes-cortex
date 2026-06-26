# ACME Works Domain Conventions

Domain model conventions and architectural decisions for acme-works (Next.js 15 + FastAPI + Rust + PostgreSQL 17 + Docker).

## Role Hierarchy (Story-Authoring Shape)

```
superadmin → admin → manager → publisher → member
```

- **superadmin**: system config, user mgmt, API keys, batch ops, audit, health
- **admin**: day-to-day work/creator/member/publisher/contract CRUD, CWR import/export, review queue
- **manager**: dashboard KPIs, approve/reject review, reports, publisher relations
- **publisher**: own catalog view, contract mgmt, work submission, royalty dashboard
- **member**: own works/shares/contracts (read-only)

## 5 Rights Types (CISAC Standard)

```
perf    — Performance right
mech    — Mechanical reproduction
broad   — Broadcasting
webcast — Webcasting
digital — Digital distribution
```

## Share Allocation Pattern

**Each creator gets 5 rows per work** (one per rights type):
- `perf` uses the PR (performance right) share value
- `mech`/`broad`/`webcast`/`digital` all use MR (mechanical + other rights) share value

**ShareType enum:**
```
normal     — Standard creator/member allocation
parent     — Publisher share that wraps child publisher shares
child      — Sub-publisher downstream share
zero_child — Blocking zero-parent (IP owner uses this to zero out a publisher line)
```

**Validation rule:** Sum per rights_type must be 10000 ± 6 basis points (100% ± 0.06%).
- TOLERANCE_BP = 6
- TARGET_BP = 10000

**Copy shares pattern:** Shares can be copied from a source work to a target work when a derivative work (e.g., broadcast version) uses the same allocation structure. The copy clones all non-deleted share rows.

## Contract Status State Machine

```
draft → active → modified → archived
       ↑         ↓
       └── modified can reactivate
```

Transition map:
```python
VALID_STATUS_TRANSITIONS = {
    "draft": ["active"],
    "active": ["modified", "archived"],
    "modified": ["active", "archived"],
    "archived": [],  # Terminal state
}
```

## Contract Types

```
op_and_specific      — Original publisher + specific sub-publisher
op_and_general       — Original publisher + general sub-publisher
sp_and_specific      — Sub-publisher + specific sub-publisher
sp_and_general       — Sub-publisher + general sub-publisher
```

## Territory Presets (CISAC TIS Codes)

```
worldwide  — +0100 (aggregate code for all territories)
korea      — +82
apac       — +81, +82, +86, +852, +886, +65, +91, +61, +64, +60, +66, +63
eu         — 27 EU/EEA member codes
```

Applying a preset creates territory×rights_type rows for all 5 rights types per territory code, each with 100% share_percentage and collection_share.

## Contract Code Format

Auto-generated: `CTR-YYYY-NNNNNN` (incrementing sequence per year).

## Contract Territory×Rights Matrix

Replaces MWI's single `rights_type` on Contract with a `contract_territories` table:

```sql
contract_territories (
  contract_id      UUID REFERENCES contracts(id) ON DELETE CASCADE,
  territory_code   VARCHAR(4),  -- CISAC TIS code
  rights_type      VARCHAR(16), -- perf/mech/broad/webcast/digital
  share_percentage DECIMAL(8,4),
  collection_share DECIMAL(8,4),
  is_exclusive     BOOLEAN,
  UNIQUE(contract_id, territory_code, rights_type)
)
```

Territory presets: "Worldwide" (+0100, all 5 types), "Korea" (KR), "APAC", "EU".
Specific territory overrides Worldwide.

## Multiple Identifiers (ISWC/ISRC per Work)

Replace MWI's single `iswc`/`isrc` columns on Song with a `work_identifiers` table:

```sql
work_identifiers (
  work_id          UUID REFERENCES works(id) ON DELETE CASCADE,
  identifier_type  VARCHAR(16),  -- iswc, isrc, upi, proprietary
  identifier_value VARCHAR(64),
  is_primary       BOOLEAN,
  UNIQUE(work_id, identifier_type, identifier_value)
)
```

Primary ISWC/ISRC values denormalized onto `works.iswc`/`works.isrc` for fast search.

## Member↔Publisher Association

M:N relationship via `member_publishers` join table:

```sql
member_publishers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id       UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  publisher_id    UUID NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
  relationship    VARCHAR(32) DEFAULT 'associated',
  valid_from      DATE,
  valid_to        DATE,
  UNIQUE(member_id, publisher_id)
)
```

Used to model which publishers represent which members, including date ranges for historical publisher switches.

## Slice Naming Convention (Parallel Execution)

Individual story files follow `slice-{phase}{subphase}-{area}.md`:

```
slice-1a-db.md              — Phase 1A: DB schema + Docker foundation
slice-1a-design.md          — Phase 1A: Next.js app shell + design system
slice-1b-admin-api.md       — Phase 1B: Admin CRUD API
slice-1b-auth.md            — Phase 1B: Authentication + RBAC
slice-1b-audit.md           — Phase 1B: Audit log
slice-1c-contract-api.md    — Phase 1C: Contract + territory matrix API
slice-1c-shares-api.md      — Phase 1C: Share allocation + validation
slice-1d-works-ui.md        — Phase 1D: Work list/detail/create pages
slice-1d-contract-ui.md     — Phase 1D: Contract pages + territory matrix
slice-1d-dashboard-ui.md    — Phase 1D: Manager dashboard
slice-2a-cwr-import.md      — Phase 2A: CWR import pipeline
slice-2b-batch-rust.md      — Phase 2B: Rust batch processor
slice-3-publisher-portal.md — Phase 3: Publisher portal
slice-3-member-portal.md    — Phase 3: Member portal
```

## Story Structure Template

```markdown
## {STORY-ID}: {Short Name}

As a **{role}**, I want **{goal}** so that **{benefit}**.

### Acceptance Criteria
- [ ] AC-1

### Edge Cases
- EC-1 → outcome

### Backend (FastAPI)
- endpoint, model touches

### Frontend (Next.js)
- route, components

### Dependencies
- blocks-on: {dependency}
```

## Domain-Specific Validation Rules

| Rule | Tolerance | Scope |
|------|-----------|-------|
| Share total per rights_type | 10000 ± 6 bp (0.06%) | per-work, per-rights_type |
| ISWC format | `T-\d{9}-\d` or `T\d{9}\d` | per identifier |
| ISRC format | `CC-XXX-00-00000` or `CCXXX0000000` | per identifier |
| IPI checksum | ISO 7064 | per creator/member |
| Contract dates | valid_from ≥ today, valid_to ≥ valid_from | per contract |
| Parent share ≥ child share | — | per publisher chain |

## ID Strategy

- **UUID v4** primary keys on all tables (not serial/auto-increment)
- **Code** columns for human-readable identifiers: `CW-YYYY-NNNNNN` (works), `CTR-YYYY-NNNNNN` (contracts), auto-generated
- **Soft delete** via `deleted_at` timestamps, not hard deletes
- **Audit** via dedicated `audit.log` schema with JSONB old/new diffs

## Key Tables

| Table | Purpose | Key Relationship |
|-------|---------|-----------------|
| `works` | Musical works | → WorkIdentifier, WorkTitle, WorkRecording |
| `creators` | Writers/composers | → WorksContractShare |
| `members` | Rightsholders | → Contract, WorksContractShare, MemberPublisher |
| `publishers` | Publishing companies | → Contract, WorksContractShare, MemberPublisher |
| `member_publishers` | Member↔Publisher M:N association | → Member, Publisher |
| `contracts` | Member↔Publisher agreements | → ContractTerritory, WorksContractShare |
| `contract_territories` | Territory×Rights matrix | ← Contract |
| `works_contract_shares` | Linchpin: links work+creator+member+publisher+contract | ← all 5 entities |
| `work_identifiers` | Multiple ISWCs/ISRCs | ← Work |
| `work_titles` | Alternative titles (EN/KO/original) | ← Work |
| `users` | System users | → role enum |
| `api_keys` | Scoped keys for external integrations | ← User |

## API Service-Layer Pattern

Phase 1C introduced a dedicated service layer separating business logic from router/HTTP concerns:

```
router (HTTP concerns) → service (business logic) → CRUDBase (db operations)
```

**ContractService** business logic:
- Code generation (auto-incrementing per year)
- Status transitions with VALID_STATUS_TRANSITIONS map
- Territory preset application (worldwide/korea/apac/eu)
- Batch territory replacement (delete-all + re-create)

**ShareService** business logic:
- Auto-create 5 CISAC-standard rows per creator (one per rights type)
- Per-rights-type share validation with ±6 bp tolerance
- Copy shares from source work (clones all non-deleted rows)
- Soft delete (sets deleted_at, removes from validation)
