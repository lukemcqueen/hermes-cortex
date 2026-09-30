# Component↔Hermes Separation — Scope 1 + 2

> **Status:** DESIGN (approved scope 1+2, builds tracked in build-tasks). **Audience:** builder, orchestrator, owner.
> **Pairs with:** `steadfaste-design` (north-star replacement) · `messaging-gateway.md` (bus already standalone) · `bus-scale/` (bus internals) · `env-vars.md` · `operations-reference.md`.

**The one-line goal:** make every fleet component *resolvable and schedulable without requiring the Hermes Agent runtime*, so nothing is load-bearing on Hermes — the migration rule "nothing the target does requires the incumbent" applied to the present fleet.

**Scope locked (Luke, 2026-09-30):**
- **Scope 1 — sever the import seam.** Rename/vendor the `hermes_*` client modules (`hermes_tz`, `hermes_paths`, `hermes_models`, `hermes_tools`, `hermes_bus`, `hermes_models.get_model`) behind a neutral namespace so scripts stop resolving against the Hermes runtime. Scripts keep working on this host; they no longer *require* Hermes to import.
- **Scope 2 — standalone runtime/hostage.** Move cron scheduling, the MCP/plugin layer (governance-enforcer, mycortex-mem, prompt-guard), and the Telegram gateway out of the Hermes process into daemoned/systemd services (bus + gateway already standalone). Agents keep talking *to* Hermes, but nothing requires its process to stay alive for a component to run.

**Explicitly out (north star, not this workstream):** full replacement of the harness with steadfaste-core. Tracked separately.

---

## 1. The seam map (surveyed 2026-09-30)

Most infra is **already Hermes-independent**: Postgres/PGMQ bus server (`core/cortex_bus/server.py` — standalone), governance DB, mycortex, task DB all run under systemd/docker with zero Hermes import. The coupling is a *thin, named seam*, enumerated below.

### 1.1 Genuine runtime imports (the real coupling)

| Where | Import | What it is |
|---|---|---|
| `core/cortex_bus/__init__.py:8` | `from hermes_bus.queue import get_queue` | **The only true `hermes_bus` dependency.** Self-referential: bus's own module exports the Hermes-runtime bus client. Guarded (a bare `import hermes_bus` already fails when Hermes runtime absent → the seam is leaky-but-not-load-bearing). |
| `mcp-servers/loop-gov-mcp.py:91` + `manage/*.py` (9 files) | `hermes_models.get_model` `load_models_env` | Model resolution — needed for governance scoring. |
| `manage/*.py`, `health/*.py` (18+ files) | `hermes_tz.format_timestamp` / `get_timezone` | Timestamping. |
| `ops/scripts/*` (9 files) | `hermes_paths.ensure_scripts_path` | sys.path bootstrap. |
| `offline/*`, `web-cache/*`, `manage/*` (few) | `hermes_tools.read_file` `write_file` `search_files` `web_search` `execute_code` | Agent tool shims used by offline code / session cache / analysis. |

### 1.2 Our-own-but-`hermes_*`-named (NOT Hermes-owned — rename only)

`ops/scripts/hermes_tz.py`, `ops/scripts/hermes_paths.py`, `ops/scripts/hermes_models.py` are **our** modules, just carrying the `hermes_*` prefix. These are a rename, not a vendoring problem.

### 1.3 Runtime-hosted but already-standalone-underneath

`mcp-servers/cortex-bus-mcp.py`, `cortex-sandbox-mcp.py`, `executor-mcp.py`, `task-mcp.py` — **standalone** (no Hermes import). Only `loop-gov-mcp.py` couples (via `hermes_models`). Cron jobs (81) run under the Hermes `cronjob` MCP; gateway (`msg-gateway.py`) + plugins (governance-enforcer, mycortex-mem, mycortex-command, prompt-guard) are plugin/MCP servers inside the Hermes process.

---

## 2. Scope 1 — sever the import seam

**Principle:** components must `import` against a neutral namespace that resolves to *our* modules, with Hermes-runtime modules vendored where truly needed. After this scope, deleting the Hermes runtime does not break a single `import`.

**Slices (one per module, in dependency order):**

| Slice | What | Where |
|---|---|---|
| **S1a** | Introduce neutral package `cortex_lib/` (`cortex_lib/tz.py`, `cortex_lib/paths.py`, `cortex_lib/models.py`) as the canonical home; keep `hermes_tz/paths/models` as thin re-export shims that `from cortex_lib import …` (back-compat: existing callers unchanged) | `ops/scripts/cortex_lib/` |
| **S1b** | Vendor the small Hermes-runtime stateless helpers (`_format_timestamp`, `_get_timezone` logic) into `cortex_lib/tz.py` so timecode works with zero Hermes import | `cortex_lib/tz.py` |
| **S1c** | `hermes_models.get_model` → `cortex_lib/models.py` reading the same env/`model` config sources, no `hermes_models` requirement. Update 8 MCP/`manage` callers | `cortex_lib/models.py` + mcp-servers/loop-gov-mcp.py + manage/*.py |
| **S1d** | `hermes_tools` runtime imports → either `cortex_lib/tools.py` wrapping the same underlying callable, or (where mechanical) inline the tool; used by offline/session-cache/analysis | `cortex_lib/tools.py` |
| **S1e** | Bus `__init__.py`: import `get_queue` from its own `server`/`queue` module path, not via `hermes_bus` (remove seam #1.1 row 1) | `core/cortex_bus/__init__.py` |

**Done-proof for S1:** for each sha sl, `python3 -I -c "import cortex_lib.tz"` (isolated mode, no Hermes on path) succeeds; full `cargo`-equivalent test suite + doctor + a live cron run still green; `grep -rl "import hermes" ops/ mcp-servers/ core/` returns **zero**.

## 3. Scope 2 — standalone runtime/hostage

**Principle:** scheduling and plugin services run as first-class daemons that *use* Hermes when present and degrade/hold-queue when not — never depend on the Hermes process being freshly alive.

| Slice | What | Where |
|---|---|---|
| **S2a** | Cron: move the 81-job schedule to a standalone scheduler (systemd-timer / a small daemon) that invokes each job script directly; Hermes `cronjob` MCP becomes one of several consumers of the same cron table, not the owner | `ops/scripts/` + install-crons.sh + a new scheduler unit |
| **S2b** | Gateway: `msg-gateway.py` already standalone — ensure systemd/docker hosting independent of the Hermes process/restart (confirm the "gateway restart kills cron" coupling is gone — the O1-S3 lesson) | gateway unit |
| **S2c** | Plugin/MCP layer: governance-enforcer, mycortex-mem/command, prompt-guard, and the MCP servers run as standalone MCP servers (loop-gov, task, bus, executor already are filesystem+MCP; remove their in-process Hermes plugin coupling) | `plugins/`, `mcp-servers/` |
| **S2d** | Verify "route around Hermes": with the Hermes process stopped (maintenance window), each component's scheduled job + core service still runs and its output still lands (local/telegram) | runbook + a gated test |

**S2 sequencing rule:** do **not** stage a fleet-wide cut. S2a builds and proves the standalone scheduler on *one* low-risk cron first (e.g. a no_agent local reporter), then widens. S2d is the acceptance gate, run only in an announced window.

## 4. Anti-bloat & safety

- **No new component** unless one already planned: a scheduler daemon is new (S2a) and is justified as the thing that removes the `cronjob`-MCP / process-restart coupling — name it, scope it, approve it in S2a before build.
- **Back-compat by default:** S1 keeps `hermes_*` shims re-exporting `cortex_lib`, so nothing breaks mid-stream; shims are removed only after the fleet is verified on `cortex_lib`.
- **Docs:** register `cortex_lib/` in `docs/DOCS-INDEX.md` + skills doc-freshness pass when S1 lands.
- **rollback:** every S1 slice is a rename+vendor commit with shims — revert = restore shims. S2 keeps the old in-process path until S2d passes.

## 5. Build-track reference

Each slice above → a BUILD/CHECK row in `build-tasks.md` (one test owned once), following the established CR/MN discipline. CHECK slices (S1e bus seam, S2d route-around gate) are strong-model; BUILD slices may be delegated.