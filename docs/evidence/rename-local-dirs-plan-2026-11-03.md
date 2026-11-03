# Local-Directory Rename Plan — esther dogfood (cycle 14077)

**Decision (Luke, 2026-11-03):** rename the two local dirs, hard-rename +
short-lived transition symlink (1 week), esther-first then fleet.

## 1. Path mapping (and what is deliberately NOT renamed)

| Now | After esther dogfood | Transition (week 1) |
|---|---|---|
| `~/hermes-cortex` (repo checkout) | `~/steadfaste-fleet` | `~/hermes-cortex` -> symlink |
| `~/.hermes-cortex` (deployed home = `CORTEX_DEPLOY_HOME`) | `~/.steadfaste-fleet` | `~/.hermes-cortex` -> symlink |
| `~/.hermes-cortex/brain` (kb + memories) | `~/.steadfaste-fleet/brain` | moved with dir |
| `~/.hermes-cortex/scripts/hc` | `~/.steadfaste-fleet/scripts/hc` | same |

**NOT renamed (compat/identity contracts):** the framework brand `Hermes Cortex`,
the `hermes-cortex` package/agent identity string, skill names
`hermes-cortex`/`hermes-cortex-setup`, import paths, service *names* (unit
filenames stay `cortex-*`, `hermes-cortex-dashboard.service`). Only
**filesystem-path** references move.

**Verified preflight facts (this host):**
- Deployed home default is parameterized: `cortex-update.sh:183`
  `CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"`.
- ~65 systemd **user** units under `~/.config/systemd/user` carry the path
  (gateway, cortex-bus, ~20 `cortex-bridge-*` services + their `.timer` files,
  dashboard, health-vector). No /etc/systemd units reference it.
- `hc` is at `~/.hermes-cortex/scripts/hc` — **no** `/usr/local/bin` symlink.
- Shell rc (`.bashrc/.zshrc/.profile`) have **0** path refs.
- `~/.hermes/cron/jobs.json` has 9 path refs.
- SOUL.md + MEMORY.md carry the path (2). Repo-wide `.hermes-cortex` path refs:
  **944** across 702 files — 53 are `CORTEX_DEPLOY_HOME`-default-driven, **891
  are hardcoded** (compose, service plists, prep/offline scripts, docs).
  `CORTEX_DEPLOY_HOME` is NOT globally set. Authoritative inventory:
  `docs/evidence/rename-local-dirs-preflight.md`. Brand strings (`Hermes Cortex` /
  bare `hermes-cortex`) are separate and NOT part of this count.
- Brain/mycortex: `~/.hermes-cortex/brain` + `docker-compose.mycortex.yml`.
- Same filesystem (mv is renames, no copy).

## 2. Mechanism — guarded rename script + transition symlink

Run `ops/scripts/manage/migrate-home-dirs.sh` (shipped in this commit) for BOTH
dirs. The script is `set -euo pipefail`; it preflights (new-target absent, and
the source is not already inside a target), uses `mv -T` (no nesting), creates
the `ln -s` immediately afterward, and a `trap` RESTORES any failed rename back
to the old path — so a failed `ln` never leaves the old path missing. Idempotent
and re-runnable; on esther it renames `~/hermes-cortex` and `~/.hermes-cortex` →
their `steadfaste-fleet` analogues and lays both transition symlinks.

Accepted interruption: the rename has a short `mv`→`ln` gap while services
resolve the old path via the symlink, and at most one `cortex-bus` restart may be
needed under failover. Nothing is copied or deleted.

## 3. Re-point real references (progressively remove symlink dependence)

1. **Regenerate systemd user units to the new path** (this writes ~65 unit
   files with `~/.steadfaste-fleet`):
   ```
   export CORTEX_DEPLOY_HOME=~/.steadfaste-fleet
   bash ~/.steadfaste-fleet/scripts/install-crons.sh
   bash ~/.steadfaste-fleet/scripts/install-orch-crons.sh
   systemctl --user daemon-reload
   ```
2. **hc**: no global symlink; update any PATH/export + shell helper that names
   the old scripts dir (rc shows 0; confirm nothing else). It ships to
   `~/.steadfaste-fleet/scripts/hc` via deploy.
3. **Hermes crons** (`~/.hermes/cron/jobs.json`, 9 refs): rewrite command
   paths to `~/.steadfaste-fleet/...`; reload scheduler.
4. **brain/mycortex**: update compose/env refs from `~/.hermes-cortex/brain` to
   `~/.steadfaste-fleet/brain`; symlink covers until done.
5. **SOUL/MEMORY/skills/docs**: rewrite the path-bearing refs to
   `~/.steadfaste-fleet` / `~/steadfaste-fleet` (leave brand-identity strings).
6. **Framework default** `cortex-update.sh:183` → `${HOME}/.steadfaste-fleet`:
   repo commit, but its **push is gated to the fleet-rollout follow-up cycle**
   (so the 4 agents' next deploy targets stay consistent until they're migrated).
   Esthers own host uses the env override from (1).

## 4. Verification — esther golden path (live, not mocks)

```bash
systemctl --user is-active cortex-bus.service cortex-gateway.service hermes-cortex-dashboard.service
systemctl --user list-timers | grep -c cortex-bridge      # ~20 remain scheduled
curl -sS 127.0.0.1:8903/health                             # bus 200
ls ~/.steadfaste-fleet/brain/kb ~/.steadfaste-fleet/brain/memories
[ -x ~/.steadfaste-fleet/scripts/hc ]                      # new-path hc present
readlink ~/hermes-cortex && readlink ~/.hermes-cortex      # -> new dirs
# live self-test: send a TEST msg via new-path hc, run handler once, confirm consumed
```
Plus — no residual old path in generated units: `grep -Rl '\.hermes-cortex'
~/.config/systemd/user` must return **zero** matches across `.service`/
`.timer`/`.socket`/`.target`; then restart all affected units and confirm
active. Health uses `curl -fsS -o /dev/null -w '%{http_code}'
127.0.0.1:8903/health` and asserts literal `200`.

## 5. Rollout (follow-up cycles, only after esther green)
- Same rename across moses/titus/joseph/kustos (via bus).
- Then push the code-default commit + remove transition symlinks week+1.

## 6. Addressing deepseek-pro review (ADV-14077, verdict FINDINGS)

**ADV-14077-1 (high) — 944 path refs, not one line.** `CORTEX_DEPLOY_HOME` is
NOT globally set; 53 refs are `CORTEX_DEPLOY_HOME`-default-driven and 891 are
hardcoded `.hermes-cortex` path refs across the repo. Remedy: a **repo-wide path
sweep** converts filesystem-path tokens `~/.hermes-cortex` / `${HOME}/.hermes-cortex`
/ `.hermes-cortex/` → `~/.steadfaste-fleet` / `.steadfaste-fleet/` (brand strings
`Hermes Cortex` / bare `hermes-cortex`, and historical `docs/older` +
`docs/evidence` transcripts stay), updating the 53 defaults AND the 891
hardcoded refs (compose, plists, prep scripts, docs). A **repo-wide grep gate**
`grep -Rl '\.hermes-cortex'` (whitelist historical/evidence/brand only) is
enforced before symlink removal.

**ADV-14077-2 (high) — verification grep.** Replace `grep -L` with
`grep -Rl '\.hermes-cortex' ~/.config/systemd/user` expecting **zero** matches,
covering `.service`/`.timer`/`.socket`/`.target`, then restart all affected
units and confirm active.

**ADV-14077-3 (medium) — health check.** Use `curl -fsS -o /dev/null
-w '%{http_code}' 127.0.0.1:8903/health` and assert literal `200`; checks are
committed as a runnable script `ops/scripts/manage/verify-rename-esther.sh`.

**ADV-14077-4 (medium) — downtime claim.** Drop "zero-downtime". A rename has a
trap-rolled-back `mv`→`ln` gap; a single `cortex-bus` restart during the
transition is an accepted, failover-covered service interruption.

**ADV-14077-5 (medium) — runnable migration.** Ship
`ops/scripts/manage/migrate-home-dirs.sh`: `set -euo pipefail`, preflight
(new-target absence + not-inside-target), `mv -T` (no nesting), immediate `ln
-s`, and a `trap` that restores a failed rename to the old path (so a failed
`ln` never leaves the old path missing). idempotent + re-runnable.

**ADV-14077-6 (medium) — preflight evidence.** Commit
`docs/evidence/rename-local-dirs-preflight.md` carrying the host-specific
counts (65 units, 9 jobs.json refs, 944 repo path refs, brain/compose paths,
hc location, no `/usr/local/bin` symlink, same-fs).

