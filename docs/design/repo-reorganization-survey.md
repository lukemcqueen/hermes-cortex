# Repo Re-Organization — Survey (2026-11-06)

> Current state of `steadfaste-fleet`, captured before any move. Goal: make the
> repo EASY for other agents to see the separation, organization, and where things
> live — then update all references/folders/names/docs.

## Scale

~3,600 tracked files.

## Top-level layout (tracked, by first path segment)

| Segment | Files | Notes |
|---|---|---|
| `ops/` | 1053 | The operational catch-all (see below) |
| `skills/` | 999 | Canonical skill library |
| `docs/` | 975 | Docs + 759 evidence + 69 `docs/older` |
| `tests/` | 391 | Test suite |
| `core/` | 44 | `cortex_bus` 24, `governance` 19 |
| `tools/` | 19 | `fleet-search` 18 + one script |
| `plugins/` | 11 | governance-enforcer, mycortex-mem/-command, prompt-guard, hc-lean-index |
| `mcp-servers/` | 6 | cortex-bus/context/sandbox, executor, loop-gov, task |
| `evals/` | 2 | regression golden + suite |
| misc root | several | see "root stray files" |

## `ops/` breakdown (second level)

| Subdir | Files |
|---|---|
| `ops/offline` | 561 (the offline corpus — largest single dir) |
| `ops/scripts` | 358 |
| `ops/install` | 64 |
| `ops/services` | 42 |
| `ops/evidence` | 17 |
| `ops/deploy` | 6 |
| `ops/web-cache` | 3 |

## Root stray files / near-empty dirs

- `poll-bus-inbox_titus.sh` — a launcher script sitting in the repo root.
- `evidence-bus-poll-titus-20261009.md`, `evidence-agent-fixer-evening-repetition-loop-20261009.md` — evidence captures at root.
- `CLAUDE.md` — a second agent-guide beside `AGENTS.md`.
- `config/`, `laptop/`, `profiles/` — top-level dirs each holding ~1 tracked file.

## Divergence from the canonical standard (`repo-organization` skill)

The canonical standard defines `src/` (scripts, agent-inbox, dashboard,
loop-governance, mcp-servers, agent-registry.json, project-map) + `deploy/`.
The actual repo instead uses **`ops/` + `core/` + `tools/` + `plugins/` +
`mcp-servers/`**. Either the standard is aspirational and reality settled on
`ops/`, or the repo drifted off-standard. That is the ONE decision that shapes
the whole re-org (see below).

## Other findings

- `docs/evidence` (759 files) is the dominant docs subtree — committed evidence
  captures, likely archive/prune candidates.
- `docs/older` (69) is a legacy-docs pile.
- `hc-session2/` is a SIBLING directory at `~/hc-session2/` (outside this repo),
  apparently a stale copy of the repo — needs a duplicate-vs-unique hash audit
  before any removal (rename-sweep pitfall: a copy can hold the only copy of
  real content).

## The decision fork

1. **Literal canonical migration** — move `ops/`+`core/`+`tools/` → `src/`
   (scripts/install/services/offline/web-cache under `src/`), per the standard.
   Massive: rewrites every `ops/...` reference — `cortex-update.sh` register
   lines, every script path, deploy maps, cron jobs, tests, docs — plus the
   fleet-side migration + doctor checks + runbook (rename-sweep §6).
2. **Navigability-first** — keep the existing `ops/` layout, achieve the same
   "easy to see the separation" goal by: partitioning/renaming the catch-all
   clearly, moving root strays, archiving `docs/evidence`+`docs/older`,
   reconciling `core/`/`tools/`/`evals/`, auditing `hc-session2/`, and writing a
   single repo map + AGENTS.md/DOCS-INDEX that makes every subtree obvious.
   Far less risky; same navigability outcome.

## Implementation shape (either path)

Governed by slice (each slice its own cycle): root-stray cleanup → docs
evidence/older archive → ops/core/tools/evals reconciliation → (optional src/
migration) → repo map + AGENTS.md/DOCS-INDEX rewrite → reference sweep +
verification battery → fleet migration + doctor check + runbook.