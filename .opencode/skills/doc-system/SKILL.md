---
name: doc-system
description: |
  Discover, create, link, and maintain project documentation.
  Prevents orphan docs, duplication, and fragmentation.
  Triggers: "find docs", "existing documentation", "doc discovery", "doc linking", "link docs", "documentation structure"
---

# Doc System

## Core Rule

Always search before creating. Prefer updating over creating. Link all important docs.

## Workflow

1. List existing docs (`find docs -maxdepth 3 -type f`, also check `memory/`, `.agentkore/`)
2. Search by keywords (feature name, domain term, model, capability, service, abbreviations)
3. Classify matches: strong → update | partial → extend | none → create new
4. Link related docs + ensure bidirectional links
5. Add status block for major docs (draft | active | superseded)
6. Preserve history — never delete replaced docs; mark superseded with `## Status: superseded`

## Related Docs Section (REQUIRED)

```md
## Related docs
- [PRD](../prd/<file>.md)
- [Architecture](../architecture/<file>.md)
- [ADR](../decisions/<file>.md)
- [Task plan](../tasks/<file>.md)
- [Research](../research/<file>.md)
- [Memory](../../memory/<file>.md)
```

## Naming

Stable meaningful names, not `prd-v2.md` or `new-doc.md`. Dates only for ADRs and research.

```
docs/prd/<feature>.md
docs/decisions/YYYY-MM-DD-<decision>.md
docs/tasks/<feature>.md
docs/research/<topic>.md
docs/architecture/<system>.md
```

## Verification

All links resolve. No duplicate docs. Doc graph navigable in 1–2 hops.

## Anti-Patterns

Creating without search | duplicate content | ignoring existing docs | renaming instead of updating | copying instead of linking | deleting without superseding | orphan docs | inconsistent naming | linking everything indiscriminately | broken relative paths
