# Territory Matrix — Society Splits Design

**Source:** hc-party review, 2026-06-23
**Approach:** Option B — Separate `society_splits` table

## Problem

The territory matrix needs to support multiple societies per (territory, rights_type) cell. Example: KOMCA has perf/mech/broad in Korea, ACME has webcast/digital — same territory, different societies with different rights.

## Data Model

```
contract_territories (modified)
├── id (PK)
├── contract_id (FK -> contracts)
├── territory_code (FK -> territories)
├── rights_type (string, extensible — not Literal)
├── total_share (Decimal, nullable — denormalized sum)
├── collection_share (Decimal)
├── is_exclusive (bool)
└── created_at

society_splits (new table)           UNIQUE(contract_territory_id, society)
├── id (PK)
├── contract_territory_id (FK -> contract_territories, CASCADE)
├── society (FK -> societies.soc_code, nullable for "unknown")
├── share_percentage (Decimal, 0-100, 4dp)
└── created_at
```

## Key Design Decisions

1. **RightsType -> str** — Make extensible (currently Literal["perf","mech","broad","webcast","digital"]). Future types: lyrics, sync, etc.
2. **100% validation** — `SELECT SUM(share_percentage) FROM society_splits WHERE contract_territory_id = X` must equal 100 per (territory, rights)
3. **"Unknown Society"** — null `society` in splits covers unmatched percentages
4. **Migration** — Existing rows' `society` + `share_percentage` become a single split entry
5. **IPI integration** — `society` from IPI lookup pre-fills the default society on the contract

## UI Pattern

- Territory row collapsed: shows `total_share` per rights type
- Expand/collapse icon reveals society sub-rows
- Each sub-row: `[Society dropdown] [Share % input]`
- Add society button appends a new sub-row
- Inline validation warning when shares don't total 100%
- Default: one society with 100% of all rights for most contracts

## Rejected Alternatives

- **Option A (expand uniqueness)**: Cheaper but mixes (territory, rights) data across society rows
- **Option C (JSONB)**: No referential integrity, opaque to audit, hard to validate

## IPI `getAgreements` Data Model (validated 2026-06-23)

The CISAC IPI SOAP `getAgreements` operation returns data matching our `society_splits` design:

| IPI field | Example | Maps to |
|---|---|---|
| `society` | `021` (numeric PRO code) | `society_splits.society` |
| `right` | `MW-LY-PE` (suffix: PE=perf, ME=mech, BT=broad, OB=webcast, OD=digital, PC=sync) | `contract_territories.rights_type` (2-letter suffix) |
| `share` | `10000` (basis points) | `society_splits.share_percentage` (÷ 100) |
| `territories` | `+2136` (World), `+410` (Korea) | `contract_territories.territory_code` |
| `valid_from` / `valid_to` | `19961201000000` / `99991231235959` | Contract dates |

client (acme-alpha) only uses this for the **member's default society** (`soc_code`), with comment
`# future accommodate multiple societies/territories`. client contracts have a single `rights_type`
per contract — per-territory rights is a new capability.

**Numeric vs string society codes:** IPI returns numeric codes (336=KOMCA, 021=international).
ACME Works uses string codes (KOMCA, ACME). A mapping layer may be needed for IPI auto-fill.

See `app/helpers/ipi_api_helper.rb` (`ipi_get_agreements`, `ipi_get_society_from_agr_hash`) and
`app/jobs/update_from_ipi_member_mna_worker_job.rb` in acme-alpha.
