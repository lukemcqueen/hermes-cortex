# Cross-Service Scope Realignment (hc-elicit → hc-party)

When a PRD story or epic overlaps with another ACME microservice, follow this
pipeline to realign scope and document the integration contract.

## Trigger Conditions

Any of these signal a cross-service overlap that needs realignment:

- User asks "does this overlap with repo-X?"
- PRD story describes functionality that another ACME repo plausibly owns
- Discovery finds similar routers, services, or models in sibling repos
- The feature involves data flowing between two services

## Pipeline

### 1. Discovery — what does the other repo already have?

Build a mapping table of PRD stories ↔ existing implementation by checking
the sibling repo's PRDs, routers, and services.

### 2. hc-elicit (Requirements Gap Analysis)

| # | Question | How to answer |
|---|---|---|
| 1 | Does the sibling repo implement all of the PRD stories? | Map each story to a router/service. If uncovered stories exist, mark as gap. |
| 2 | Is the implementation complete or partial? | Read the actual service code. Check for stubs, TODOs, skipped tests. |
| 3 | What integration does the current repo need? | What data flows in each direction? Check the sibling PRD's "Integration" or "Bounded Context" section. |
| 4 | What infrastructure is missing? | Check for NATS consumers, API clients, proxy endpoints, or event handlers. |

### 3. hc-party (Architecture Review & Integration Contract)

Document in an ADR (`docs/decisions/ADR-NNN-<topic>.md`):

- **Scope Decision:** Which repo owns the feature
- **Data Flow Diagram:** Direction + protocol
- **Event/API Contract Table:** Endpoint name, direction, payload, auth, status (🔴🟡🟢)
- **Gap Table:** Missing consumers, emitters, or infrastructure

### 4. Update the PRD

Replace the detailed Epic/Story section with a cross-reference to the
owning repo's PRD:

```markdown
### Epic N: Feature Name

**Owned by:** `<sibling-repo>` application
**Scope in acme-royalty:** None. This feature is a bounded context
implemented in the dedicated microservice.

**[ALL STORIES BELONG TO `<sibling-repo>`.]**
```

### 5. Write the ADR

See `docs/decisions/ADR-013-epic-9-scope-realignment.md` for a completed
realignment of Epic 9 (Licensee Portal) → `acme-license`.

## Example

| Item | Value |
|---|---|
| Discovered | acme-license has 6 routers covering all Epic 9 stories |
| Gap | acme-royalty has zero NATS infrastructure for integration |
| ADR | `ADR-013-epic-9-scope-realignment.md` |
| PRD update | Epic 9 in `epics.md` replaced with cross-reference |
| Integration | `license.revenue.recorded` NATS event (not built yet) |

## Related

- `engineering-approach/references/prd-gap-analysis-methodology.md` — PRD-level gap analysis
- `engineering-approach/references/target-prd-integration-after-realignment.md` — **target repo** integration (step 6: surgically add the realigned epic into the target PRD)
- `acme-project-structure` — Companion repo layout, which service owns what
