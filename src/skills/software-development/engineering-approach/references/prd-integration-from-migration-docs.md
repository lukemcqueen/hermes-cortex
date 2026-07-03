# PRD Integration from Cross-Codebase Migration Docs

When a migration analysis document from another ACME system (e.g. acme-royalty) identifies services that belong in acme-works, integrate them into the PRD surgically rather than rewriting the whole document.

## Sequence

### 1. Read the source document

Identify each service being migrated, its current behavior, and the target behavior expected in this codebase. Note any open questions the source doc flags.

### 2. Map each service to the right PRD section

| Service type | Likely PRD section |
|---|---|
| Import format (CSV, Excel) | Section 4.5 Import/Export |
| Search enhancement (Meilisearch) | Section 4.2 Admin API (search row) |
| Export format (CSV, CWR) | Section 4.5 Import/Export |
| New CRUD endpoint | Section 4.2 or 4.3 Admin/Domain API |

### 3. Patch each section surgically

- **Existing rows:** update status (✅ for already-built, ⏳ for pending, 📋 for scoped)
- **New rows:** add between existing rows, keeping priority/status columns consistent
- **Section expansion:** if the scope grows significantly, rename the section header (e.g. "CWR Import" → "Work Import/Export") and add subsection headers

### 4. Update peripheral metadata

- **Status line** at the top of the PRD — append new scope with appropriate emoji
- **Phases table** (Section 5) — update duration, scope description, and status for the affected phase
- **ADR table** — add any new ADR referenced or implied by the migration
- **SLICES-INDEX.md** — expand the relevant phase table with new rows

### 5. Close open questions in the source doc

When the user makes a decision (e.g. "yes, support CSV + Excel too"), record it in both:
- The source migration doc (under the Open Questions section, with **Decision:** prefix and date)
- The PRD import format strategy note

### 6. Circle back

After all patches, re-read the PRD sections you modified to verify consistency. The document should read as if the new scope was always part of the original plan — not as a grafted appendix.

## When to use this

- A system boundary decision (ADR-011 style) moves service ownership between ACME projects
- A migration analysis from another codebase identifies capabilities that belong here
- The PRD needs to absorb new requirements without a full rewrite

## When NOT to use this

- Starting a brand new project with no PRD → use `prd-creation-methodology.md`
- Auditing existing implementation against the PRD → use `prd-gap-analysis-methodology.md`
- Adding a small feature to an aligned architecture → just add rows directly
