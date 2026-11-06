# Repo Organization — Decision Material for Pro Review (2026-11-06)

Goal (operator): make the `steadfaste-fleet` repo EASY for other agents to see
the separation, organization, and where things live; update all
references/folders/names/docs. Multi-agent fleet (Hermes, Pi, Claude, custom) on
one server.

## Current architecture (the ACTUAL operative standard)

The repo follows a **layer-separation model** established by commits
P0a (`b416ed5c` "layer separation scaffold — core/, runtime/, ops/ dirs") and
P0d (`0e5be574` "move all operational assets to ops/ + skills to runtime/").
`src/` was retired and physically removed (`f51df21a`, `7e8a8eac`), references
swept (`05f6ff68`). Today:

| Top level | Files | Purpose |
|---|---|---|
| `ops/` | 1053 | offline 561, scripts 358, install 64, services 42, evidence 17, deploy 6, web-cache 3, skills 1, README 1 — sum 1053 |
| `skills/` | 999 | canonical skill library (by domain) |
| `docs/` | 975 | docs (evidence 759, design 46, older 69, templates, runbooks, reviews, adr, prd) |
| `tests/` | 391 | test suite |
| `core/` | 44 | cortex_bus 24, governance 19, README 1 — sum 44 |
| `tools/` | 19 | fleet-search 18 + one script |
| `plugins/` | 11 | Hermes plugins (governance-enforcer, mycortex-mem/-command, prompt-guard, hc-lean-index) |
| `mcp-servers/` | 6 | cortex-bus/context/sandbox, executor, loop-gov, task |
| `evals/` | 2 | regression golden + suite |

## The stale reference point

The `repo-organization` skill (`skills/software-development/repo-organization/`,
v1.1.0) still prescribes a `src/`-based tree (`src/scripts`, `src/agent-inbox`,
`src/dashboard`, `src/loop-governance`, `src/mcp-servers`, `deploy/nginx`). That
layout predates P0a/P0d and was never updated after `src/`→`ops/`. Its §7
audit checklist and §3 naming conventions remain useful; its §2 directory tree
is obsolete.

## Pain points to resolve (any plan)

1. Root strays: `poll-bus-inbox_titus.sh`, `evidence-*-20261009.md` ×2,
   `CLAUDE.md` beside `AGENTS.md`, near-empty `config/`/`laptop/`/`profiles/`.
2. `docs/evidence` = 759 files (dominant subtree) — archive/prune candidate.
3. `docs/older` = 69 — legacy pile (mostly correctly-preserved history; some
   non-`older` stale content may be mixed in).
4. Scatter of small top-levels: `core/` (44), `tools/` (19), `evals/` (2) sit
   outside `ops/` — is that the right separation, or should they consolidate?
5. `ops/` is a catch-all: `offline/` (a 561-file corpus) vs `scripts/` vs
   `services/` vs `install/` — mostly clear by name, but nothing documents it.
6. `hc-session2/` is a SIBLING dir at `~/hc-session2/` (outside the repo),
   apparently a stale copy — needs duplicate-vs-unique hash audit.
7. No single repo map: navigation relies on AGENTS.md + DOCS-INDEX, neither of
   which lists the actual top-level separation as it stands.

## The question for review

Given the layer model is already established and `src/` is long retired:

1. Is the current `ops/` + `core/` + `tools/` + `plugins/` + `mcp-servers/` +
   `skills/` + `docs/` + `tests/` separation the right one to KEEP, or does it
   need structural consolidation (e.g. fold `core/`+`tools/`+`evals/` under
   `ops/`, or promote `plugins/`/`mcp-servers/`)?
2. Should the `repo-organization` skill be REWRITTEN to codify the actual model
   (retire the `src/` tree from it), rather than the repo migrated to match the
   stale skill?
3. What is the minimal, highest-leverage set of moves + a single repo-map
   artifact that makes the separation obvious to a fresh agent?
4. Any naming/structure pitfalls (e.g. `ops/` vs `src/`, `core/governance` vs
   `loop-governance`, plugins under repo vs deploy-home) worth fixing now vs
   deferring?

## Evidence pointers

- Operator directive: this session (Telegram DM, 2026-11-06, UTC+09) — *"organize
  the fleet repo so it's EASY for other agents to see the separation... this is
  a full re-organization"*; recorded in `docs/design/repo-reorganization-survey.md`
  (commit `9cb85f27`).
- File counts + top-level table: `git ls-files | cut -d/ -f1 | sort | uniq -c`
  and `git ls-files | cut -d/ -f1-2 | sort | uniq -c`, run 2026-11-06 in this
  session; tabulated in `docs/design/repo-reorganization-survey.md`.
- Commit hashes (P0a/P0d layer separation, src/ retirement): `git log --oneline
  --diff-filter=D -- 'src/*'` and `git log --follow --oneline --
  skills/software-development/repo-organization/SKILL.md` → `b416ed5c`,
  `0e5be574`, `f51df21a`, `7e8a8eac`, `05f6ff68`, `63fed304`.
- Root strays: `git ls-files | grep -v '/'` → `poll-bus-inbox_titus.sh`,
  `evidence-bus-poll-titus-20261009.md`, `evidence-agent-fixer-evening-repetition-loop-20261009.md`,
  `CLAUDE.md`, `config/`, `laptop/`, `profiles/` (each 1 file).
- `docs/evidence`/`docs/older` counts: same `git ls-files` breakdown.
- `hc-session2/`: SIBLING at `~/hc-session2/` (outside this repo) — surfaces in
  `search_files` of `~`; a duplicate-vs-unique hash audit is REQUIRED before any
  removal and has NOT yet been run.