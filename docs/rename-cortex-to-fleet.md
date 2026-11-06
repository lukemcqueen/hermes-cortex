# Rename boundary — `cortex` → `fleet` short-name family

> **What this is.** The implementer quick-reference for the second naming sweep (2026-11-06): the
> `cortex` short-name family (`cortex-`, `cortex_`, `Cortex`, `\bcortex\b`) renames to `fleet`,
> staged in P0–P7. The full specification is
> [`docs/plans/cortex-to-fleet-rename-plan.md`](plans/cortex-to-fleet-rename-plan.md) — including
> measured scope, the risk register, phases, verification and rollback. Read that plan before
> executing; this file is the boundary you must not cross while you do.

## Operator decisions (2026-11-06) — these override any earlier note

- **Q1** Staged, not a bang (the 2026-11-04 attempt was reverted for being too big a single change).
- **Q2** Dashboard JOINS the rename → `fleet-dashboard.service` (+ plist). The earlier
  "hermes-cortex-dashboard keeps its name" note in `docs/rename-followups-steadfaste-fleet.md` is
  superseded for this artifact.
- **Q3** Names-only. `CORTEX_*` env vars are DEFERRED to a follow-on release (§5 P4 spec).
- **Q4** The four `hermes-cortex*` skills stay for a third sweep — do not touch their `name:` or dirs.

## Guard rule (first rule in any replacement pass)

Every replacement regex on the token must carry **`(?<!my)(?<!hermes-)cortex`** —
never a bare catch-all.

- `my` protects the knowledge brain: database `mycortex`, roles `mycortex`/`mycortex_admin`,
  schema `mycortex.*`, `plugins/mycortex-*`, `ops/services/mycortex*`, the `mycortex` CLI,
  `mycortex-parity.py`, `agent-mycortex-*`, `agent-mycortex-dream-*` crons.
- `hermes-` protects the four deferred skills and the enforcer's
  `(hermes-cortex|steadfaste-fleet)` accept list. **Without it a bare replace makes
  `hermes-cortex` → `hermes-fleet`.**

Post-condition: `git grep -c mycortex` and `git grep -c hermes-cortex` are **unchanged per file**
except the deliberately-repointed artifacts below.

## Deliberately-repointed `hermes-cortex` consumers (mapping rules, never the catch-all)

| from | to | phase |
|---|---|---|
| `hermes-cortex-dashboard.service` (host unit) | `fleet-dashboard.service` | P5 |
| `ops/install/deploy/hermes-cortex.env.example` | `ops/install/deploy/fleet.env.example` | P3 |
| `docs/templates/com.hermes.cortex-dashboard.plist`, `ops/services/dashboard/com.hermes.cortex-dashboard.plist` | `com.steadfaste.fleet-dashboard.plist` | P3 |

## Deliberate keeps (do NOT touch)

- **Records:** `docs/older/`, `docs/evidence/`, `tests/artifacts/`, `docs/reviews/`, any dated
  filename — they record what WAS there; rewriting falsifies the record.
- **The documents that describe THIS change**: this file, the plan, and the four
  `docs/evidence/cortex-to-fleet-scope-2026-11-06.*` / `-worktree-2026-11-06.*` artifacts — a
  blanket replace inverts their `old → new` mapping lines to `new → new`.
- **One-release shims**: the `cortex_<pkg>/__init__.py` re-export shims (P2) and the
  `fleet-update.sh` forwarding shim (P3) must keep the old token while their release window is
  open — that is their job.
- **Detection/report messages** whose subject is the old name (doctor "stray …", enforcer brand
  allow-list entry).
- **The migration tool itself** (`migrate-cortex-to-fleet.sh`): its idempotency check depends on
  the old literal.

## Two counters, never mixed

| counter | regex | use it for |
|---|---|---|
| family | `CORTEX_` | later (P4) replacement pass — also rewrites prose wildcards |
| identifier | `CORTEX_[A-Z0-9_]+` | later (P4) env-var inventory — real names only |

Not part of P0–P7 (Q3). Both come from ONE run of the scope evidence script.

## Environment surfaces — repoint them in the same change that renames their target

The repo sweep renames files; the host references them by name (Hermes `config.yaml` MCP args,
the Pi manifest `~/.pi/agent/mcp.json` + `settings.json`, macOS LaunchAgents, Linux systemd units,
`/usr/local/{bin,sbin}` root copies, `gateway.yaml`). Miss one and the next agent spawn 404s on a
moved path. Full inventory with per-surface repoint commands: **plan §4.9**; the P7 doctor FAIL
check enforces it. The harness **generator** (`ops/install/harnesses/generate-harnesses.py`) must
be swept too, or every future host regenerates the old names.

## Verify a phase is converged

- Residue grep of the active families (`cortex-`, `cortex_`, `Cortex`, `\bcortex\b`) == 0 in
  scope; `CORTEX_` is NOT in this list for P0–P7.
- `git grep -c mycortex` / `hermes-cortex` unchanged per file (except the mapped renames).
- `cortex-doctor.py --quiet` → 0 fail; doctor green after every deploy. Deploy, then push.