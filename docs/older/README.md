# docs/older/ — Historical Documentation Archive

**Rule: `docs/` holds what is CURRENT. This directory holds what is HISTORICAL.**

Nothing is deleted — a doc that stops being current is *moved here*, because a
reader may still need the reasoning, and git history alone is hard to browse.
If you are an agent trying to learn how something works **today**, read
`docs/` and `docs/DOCS-INDEX.md`; come here only when a current doc points
you at a predecessor, or when you need the provenance of a decision.

## What belongs here

| Kind | Signal |
|---|---|
| Dated records | a date in the filename (`2026-09-28-…`) — a plan, incident, or session record |
| Deprecated designs | the doc (or its own header) says deprecated / superseded / replaced by X |
| Completed plans | the work shipped; the plan is now provenance, not instruction |
| Migration records | "we moved from A to B" — read once, then historical |
| Foreign-project design | design material for a *different* project kept for reference |
| Stale troubleshooting | the failure mode no longer exists in current code |

## What does NOT belong here

- Anything a current doc links to as *the* source of truth — fix the current
  doc instead (or keep the target current).
- Operational runbooks, references, ADRs, PRDs, templates, and design docs
  that still describe live behaviour. Those stay in `docs/`.
- Skills (`skills/`) — they have their own lifecycle, not this archive.

## Moving a doc here (procedure)

1. `git mv docs/<path> docs/older/<path>` — **preserve the relative path** so
   the origin of the doc stays obvious.
2. Sweep references: `grep -rn 'docs/<path>' --include=*.md --include=*.py .`
   and repoint each hit at `docs/older/<path>`. Never leave a dangling link.
3. Update `docs/DOCS-INDEX.md` — remove it from the current tables, and add it
   to the archive list if it is worth a reader's attention.
4. One governance cycle for the batch; do not leave cycles PENDING.

## Contents

**Records & plans**
- `plans/2026-09-28-build-jev-style-decision-model.md` — Jev-style decision model build plan
- `plans/2026-09-28-build-specialized-model-research.md` — specialised-model research plan
- `design/fleet-git-reset-2026-08-24.md` — the fleet-wide git reset of 2026-08-24
- `elicit/2026-09-09_bus-resilience.md` — bus-resilience elicitation session

**Superseded / deprecated**
- `deprecated-profile-model.md` — the multi-profile model, replaced by single-profile + isolation
- `troubleshooting-stale-inbox-api.md` — inbox-API failure mode that no longer exists
- `reference/mcp-sdk-v2-migration.md` — the MCP SDK 1.0 → 2.0 migration record
- `design/titusclaude-hookup.md` — a prepared hookup that was never completed

**Foreign-project design archive**
- `steadfaste/coding_agent/codeharness-design-docs/` — the **steadfaste
  code-harness design docs** (spec, party, research, architecture, story).
  Steadfaste is a separate project; this is kept here as reference material,
  not as current hermes-cortex documentation. Its internal `docs/new/`
  duplicate subtree was merged up and removed (2026-10-01) — the unique files
  were kept, the 15 duplicate copies dropped.
