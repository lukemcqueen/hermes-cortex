# Works/Shares/Contracts ↔ Royalty Distribution — Bounded Contexts

## The Landscape

Three repos that form the ACME application suite:

| Repo | Stack | Domain | Role |
|---|---|---|---|
| **acme-alpha** | Rails (Ruby/PostgreSQL) | Works, shares, contracts, creators, CWR import | Source of truth for catalog |
| **acme-royalty** | FastAPI/Next.js (Python/TS/PostgreSQL) | Distribution calculation, matching, approval, audit | Read projection from client |
| **acme-metadata** | (PRD phase) | 3-store metadata reconciliation | Integration layer (planned) |

## The Architectural Decision

**Works/shares/contracts SHOULD remain in acme-alpha (Rails) as the source of truth.** acme-royalty's Work/OwnershipSplit models are **read-only projections** — they exist only to support matching and distribution, not to manage the work lifecycle.

### Why Keep Them Separate

1. **acme-alpha has 10+ years of edge cases.** `client_share` uses char-column fixed-width storage. `contract` has complex state machines. Duplicating this in Python/TS is high-risk, low-value.

2. **Different bounded contexts, different lifecycles.**
   - Works/shares/contracts: created once, edited rarely, long-lived
   - Distribution: computed monthly, heavy calculation, batch-oriented
   - Matching: runs on ingest, fuzzy, needs fast reads of static catalog

3. **Technology mismatch.** Rails monolith vs Next.js/FastAPI. Sharing a DB is coupling them; an API layer is the right boundary.

### The Sync Layer

Keep acme-royalty's Work model as a thin projection. Sync from client via the sync service:

| File | Purpose |
|---|---|
| `apps/api/services/work_sync.py` | `sync_works()`, `sync_shares()`, `sync_all()` — paginated httpx pulls from `acme-alpha/api/songs` and `api/song_creators` |
| `apps/api/routers/work_sync.py` | `POST /api/v1/sync/works` (manual trigger), `GET /api/v1/sync/status` |
| Cron job | Hermes cron `client-sync`, every 6h, calls `/api/v1/sync/works` |

Env config:
- `CLIENT_API_URL` — defaults to `http://host.docker.internal:3000` (Docker → host)
- `CLIENT_API_KEY` — Bearer token for auth
- `CLIENT_SYNC_SCHEDULE` — default `every 6h`

Sync service pulls fields: `id, code, title, title_ko, iswc, isrc, status, genre, library_id` from songs, maps to `Work`. Song creators → `OwnershipSplit` with share in basis points.

**Rules going forward:**
- Work/OwnershipSplit are read-only projections — no CRUD routes in acme-royalty
- CWR import → acme-alpha, not acme-royalty (client has mature contract/creator linking)
- No new fields on Work model without a corresponding field in acme-alpha
- REC/PER/IPA enrichments from CWR-2.1 are valid (support matching) but use WorkRecording/WorkPerformer/WorkAlternatePartyId, not Work itself

The projection model in acme-royalty should be **frozen** — no CRUD routes for works/shares in acme-royalty. CWR import routes to acme-alpha, not acme-royalty.

### Boundaries

| Operation | Handled By |
|---|---|
| Work registration (CWR import) | acme-alpha |
| Work editing (title, ISWC, shares) | acme-alpha |
| Contract management | acme-alpha |
| Reading works for matching | acme-royalty (projection) |
| Usage matching | acme-royalty |
| Distribution calculation | acme-royalty |
| Approval/Audit | acme-royalty |

### acme-metadata (the 3-store PRD)

If built, acme-metadata should be an evolution of acme-alpha's catalog layer — not a third silo. It would become the canonical metadata source that both client and royalty read from. Until then, acme-alpha remains the source of truth.
