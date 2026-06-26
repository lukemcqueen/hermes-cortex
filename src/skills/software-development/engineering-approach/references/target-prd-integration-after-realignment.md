# Target PRD Integration After Cross-Service Realignment

Once a cross-service scope realignment is resolved (ADR written, source-repo PRD
stubbed with a cross-reference — see `cross-service-scope-realignment.md` steps 1-5),
the epic's requirements must be integrated into the **target repo's** PRD. This is
not a copy-paste — it requires surgical insertion that respects the existing document
structure and FR numbering.

## Integration Checklist

| # | Action | Details |
|---|--------|---------|
| 1 | Map each epic story to target FR numbers | Match against existing FRs. Overlap? Expand the existing FR. No overlap? Create a new section with new FR numbers. |
| 2 | Expand overlapping FRs | Where the epic story describes functionality the target repo already covers (e.g., "usage submission" matches an existing FR), expand that FR's acceptance criteria with the new detail. |
| 3 | Insert new sections | For stories that don't map to existing FRs, add a new subsection at the correct structural position. |
| 4 | Renumber subsequent FRs + sections | Every FR and section header after the insertion point increments by `n` (where `n` = number of new FRs). Update all internal cross-references. |
| 5 | Update data model tables | Add tables for new entities with columns, types, and FK relationships. |
| 6 | Update core services table | If the epic expands a service's scope, update its description. |
| 7 | Update story slices | Expand existing slices where personas overlap; add new slices for entirely new personas. Include full acceptance flows and edge cases. |
| 8 | Update build priority / roadmap | Add new roadmap items with dependencies and effort estimates. |
| 9 | Add epic cross-reference table | A table mapping each epic story to its target FRs and sections for traceability. |
| 10 | Verify no dangling FR refs | Search the full PRD for old FR numbers that should have been renumbered. Also check NFRs for collisions (NFR-XX and FR-XX are independent prefixes). |

## Example — Epic 9 → acme-license Integration

| Story | Target FR | Action |
|:-----:|:---------:|:------|
| 9.1 — Usage Data Submission | FR-LIC-33 | Expanded existing §4.7 with encoding detection, partial submission, error reports |
| 9.2 — Compliance Reporting | FR-LIC-36, FR-LIC-37 | New §4.8 (renumbered old §4.8→4.10, old §4.9→4.11) |
| 9.3 — Dispute Resolution | FR-LIC-38, FR-LIC-39, FR-LIC-40 | New §4.9 with 3 FRs, SLA triggers, evidence rules |

## Common Pitfalls

- **FR/NFR collision** — NFR-LIC-XX and FR-LIC-XX are independent prefixes. Adding
  new FR-LIC-36 doesn't conflict with NFR-LIC-36. Verify with a prefix-aware search.
- **Section numbering drift** — When you insert a new section in the middle, every
  section after it renumbers. Update ALL internal references across the document.
- **Story slice dependency chains** — New slices may depend on existing ones
  (e.g., S-07 depends on S-05 for usage data). Document these in the build sequence.
- **Dual-side realignment + integration** — The source-repo PRD gets a cross-reference
  stub AND the target-repo PRD gets the full content. Both changes happen together.
  Do one side, then the other — don't leave the source side stub as the only trace.

## Related

- `cross-service-scope-realignment.md` — the upstream pipeline that precedes this step
- `prd-integration-from-migration-docs.md` — similar pattern for integration from migration analysis
