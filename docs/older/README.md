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
   Two exempt classes: **dated records** (a filename with a date — they record
   what was true then) and the two **machine-managed areas below**.
3. Prepend the one-line archive banner (see any file below for its wording) so a
   reader who lands here directly knows the doc is not current instruction.
4. Fix the moved doc's own relative links (they shift one directory down) and add
   it to the **Contents** list below.
5. Update `docs/DOCS-INDEX.md` — remove it from the current tables; the archive
   itself is described there by one row pointing at this file.
6. One governance cycle for the batch; do not leave cycles PENDING.

## Machine-managed areas — do NOT archive these

- `docs/evidence/` — the run-evidence store. It is an enforced surface (the
  doctor's `Review provenance` check FAILs on an undeclared review artifact there)
  and it is browsed by directory, not indexed row by row. See
  `docs/evidence/README.md`.
- `docs/reference/` and the `*-reference.md` files in `docs/` — written by
  `ops/scripts/agent/agents-doc-audit.py --prune --apply` (cron
  `agents-md-prune-apply`), which relocates sections out of `AGENTS.md` and
  rewrites them. Anything moved to the archive would simply be recreated.

## Contents

**Archived 2026-10-20** (the consolidation sweep — each carries the archive banner)
- `cron-jobs-reference.md` — the pre-2026-08 cron table; superseded by `docs/cron-schedules.md` (canonical)
- `cron-format-standard.md` — a partial summary; superseded by the `cron-format-standard` skill
- `cost-baseline-2026-10.md` — the October fleet-cost measurement (a dated record, not instruction)
- `review-queue-diagnosis-2026-10.md` — the October review-queue diagnosis (diagnose-only bound)
- `continuous-skill-suggestion.md` — 2026-07-29 design that was never implemented
- `external/pi-skill-bridge.md` — the hand-built Pi skill bridge, superseded 2026-10-13
- `pre-task-sequence-mandatory-before-every-task.md` — superseded by the `task-start` skill
- `reference/session-todo-protocol.md` — pointed at `~/.hermes-cortex/data/TODO.md`, which no longer exists
- `reports/` — the three dated 2026-10-06 reports + their raw captures
- `design/client-av-alembic-hook-handoff.md` — a completed task handoff (delivered 2026-08-24)

**Merged away 2026-10-20** (content preserved in the surviving doc, listed here for provenance)
- `repo-vs-deployed-paths.md` → `docs/deploy-registry-pattern.md`
- `agent-learning-submissions.md` → `docs/pipeline-reference.md`
- `pinned-repo-hooks.md`, `pre-commit-scoring.md` → `docs/git-enforcement.md`

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
