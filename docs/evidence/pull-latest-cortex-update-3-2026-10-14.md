# Pull-Latest + Cortex Update (3rd run) — 2026-10-14

Cycle: pull-latest-and-cortex-update-3 (#6261)
Host: Titus (macOS)

## 1. Pull
`git pull --ff-only origin main` → fast-forward 38 commits to `33fd0134`.
A second upstream commit `e80ff2e0` ("land 8 stranded skill files; the deployed side was the
curated one" — the orchestrator landing stranded skills, matching my cycle-6063 bus request)
landed mid-cycle; integrated by MERGE (`git merge origin/main --no-edit`), per change-checklist.
Repo synced, `behind=0`.

## 2. REAL BLOCKER FOUND AND FIXED — the fleet venv was broken
The first update run FAILED:
```
✗ the fleet venv is MISSING: /Users/luke/.hermes-cortex/venv
✗ Update completed the enforcement/critical sync, but these DB schema migrations FAILED:
✗   • fleet venv missing
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'   # doctor crash, PEP 604
```
Root cause: `~/.hermes-cortex/venv/bin/python3` → `~/.local/bin/python3` →
`~/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12`. That uv-managed
Python tree had been REMOVED, so the symlink chain was dangling, the fleet venv had no usable
interpreter, and `python3` fell back to the system 3.9.6 — which is why the doctor crashed on
`float | None` (PEP 604 needs 3.10+).

**Fix (least invasive — restored the interpreter, did NOT rebuild the venv):**
```
uv python install 3.12.13      # restores the exact tree pyvenv.cfg names
```
Verified: `~/.hermes-cortex/venv/bin/python3 --version` → `Python 3.12.13`;
`fix-cortex-venv.py --check` → "imports all 6 declared requirements". Re-ran the sanctioned
update: no venv/migration failure.

## 3. Sanctioned deploy (after fix)
`bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (exit 1 = relock wrapper only)
- Skills: 0 updated, 386 unchanged, 0 stale removed
- Crons up to date
- Enforcement files re-locked (all LOCKED lines present; relock rc=1 benign)
- `GATEWAY RESTART REQUIRED` banner (enforcement chain redeployed — see §6)

## 4. Skill drift reconciled
Doctor flagged `⚠️ Skill drift: software-development/test-driven-development`. The deployed copy
was a pure superset (+11, -0) over the repo source — a stranded lesson. Reconciled via
`reconcile-stranded-skills.py --apply`; `check-skill-drift-parity.py --check` now returns 0
(committed artifact matches live derivation, 0 stranded).
`skills/` is orchestrator-only — the working-tree copy is uncommitted and a commit request was
sent to the orchestrator via the bus (`inbox_orchestrator`).

## 5. Doctor — TWO runs, both captured and labelled (the pre-reconcile one is NOT presented as the post-reconcile state)
`python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet` → rc=1 (WARNING).
- **Pre-reconcile** run → `doctor-pull-latest-cortex-update-3-pre-reconcile-2026-10-14.txt`:
  **444 pass · 8 warn · 0 fail · 7 info**, still listing `⚠️ Skill drift: software-development/test-driven-development`
  (the warned 8th warning).
- **Post-reconcile** run → `doctor-pull-latest-cortex-update-3-post-reconcile-2026-10-14.txt`:
  **444 pass · 7 warn · 0 fail · 7 info**, `✅ Skill drift` (reconciled).
- The committed verify capture (`verify-…-3-….txt`) runs the doctor fresh; its inline Overall line is the
  authority for that run and will reflect the tree state at run time.
- Remaining warns: CLAUDE.md (dev repos), Script run evidence, Legacy lock
  (`.governance-sess_6459cc640a9c.json` — a prior-session lock on the DIFFERENT `steadfaste-s1-model`
  repo, within TTL, not deleted), Symlinks, Paused crons: reason, loop-gov daemon, MCP-wiring migration.
- Accepted criterion for this host: **0 fail and rc ≤ 1** (warnings are pre-existing/ambient, not a
  failure). The verify script asserts that, and reports the warn count without claiming the doctor is
  "clean" — a WARNING doctor is not a clean doctor.

## 6. Gateway restart still pending
The deploy banner fired again; the running gateway still executes the old enforcer until
**`hermes gateway restart`** (operator action). Same deferred item as cycles 6057/6063.

## 7. Verify script (committed, runnable)
`verify-pull-latest-cortex-update-3-2026-10-14.sh` re-runs every claim and exits non-zero on
failure: git sync, fleet venv interpreter + all 6 requirements, uv python restored,
deployed==repo for 3 deploy-map files, enforcement 10/10 immutable, doctor rc≤1 AND 0 fail
(reported, not claimed "clean"), skill-drift parity via read-only `--check`. Captured run:
`verify-pull-latest-cortex-update-3-2026-10-14.txt`.