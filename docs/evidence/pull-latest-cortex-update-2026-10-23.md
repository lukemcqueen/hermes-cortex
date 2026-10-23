# Pull Latest + Cortex Update — 2026-10-23 (Titus, macOS LAM2.local)

## Provenance

- Produced by: Titus session `hc-pull-update` (governance cycle 7433, lock `20261023_172042_b4605c`).
- Commands run, output captured into this file + `doctor-pull-latest-2026-10-23.txt`.
- Host paths normalised (`/Users/luke` → `~`) in the committed copies; the live logs
  are at `~/.hermes/cache/scratch/hc-pull-update-20261023_172206.log` and
  `~/.hermes/cache/scratch/hc-doctor-20261023.log`.
- Tip revision at capture: `2a1517c6` (HEAD == origin/main).

## 1. Pull

```bash
git fetch origin && git pull --rebase origin main   # PULL_EXIT=0
```

- Fast-forward `7230c79c..2a1517c6` — 21 files, +1505/−52: loop-governance wrong-repo
  guard evidence + v014 tasks schema (orchestrator-only verify arc), briefing-gate
  evidence, governance-closeout / subagent-delegation skill copies, cortex-update.sh +
  verify_briefing.py tweaks, updated tests.
- Tree clean before pull (`git status --porcelain` empty); HEAD == origin/main after.

## 2. Deploy (post-merge hook ran cortex-update.sh)

From `hc-pull-update-20261023_172206.log`:

- `✓ Updated: 2a1517c6 → 2a1517c6` (force mode)
- `✓ 315 file(s) updated`; enforcement files UNLOCKED → deployed → LOCKED (all 9
  listed, including `governance-enforcer/__init__.py`, `loop-gov-mcp.py`,
  `hermes-plugin-lock`)
- Plugins re-enabled: governance-enforcer, mycortex-command, mycortex-mem,
  prompt-guard, hc-lean-index — gateway reloaded plugins
- Crons: 8 new, 35 skipped; LLM crons drifted prompts refreshed (agent-fixer ×3,
  cortex-bus ×3, agent-memory-pruning, agent-agents-md-prune-apply)
- SOUL.md sync: up to date with template
- `✓ State saved: 2a1517c6` — Deploy sync holds
- Warnings (accepted): `GATEWAY RESTART REQUIRED` banner (enforcement chain
  redeployed — operator action, see §4), `cost keys not dropped` (ruamel.yaml
  missing in that interpreter, pre-existing), skill drift ×2 (see §5), name-collision
  shadows ×2 (Hermes defaults, pre-existing), nginx zone-defs needs manual `sudo cp`
  (operator action, §4). Deploy exited rc=1 because of the doctor FAIL in §3 — the
  only ❌ is the out-of-scope steadfaste check; relock fail-safe re-secured all
  enforcement files afterwards (`LOCKED:` ×9 all present).

## 3. Doctor (fleet venv — ALWAYS the venv interpreter)

```bash
~/.hermes-cortex/venv/bin/python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```

`Overall: FAILING (471 pass · 12 warn · 1 fail · 7 info)` — exit 2.

- **Only ❌: `AGENTS.md (steadfaste)`** — staleness check on a DIFFERENT repo
  (`~/steadfaste`, ahead 47/behind 1, its AGENTS.md mtime predates HEAD). Pre-existing,
  out of scope for this hermes-cortex update cycle — accepted by the fleet's own
  verify script (`docs/evidence/verify-pull-latest-cortex-update-2026-10-13.sh`:
  "only out-of-scope fail is steadfaste (different project)"). Recovery is its own
  governed change in that repo.
- All 12 ⚠️ carry recorded dispositions (deferred/deliberate, titus): CLAUDE.md dev
  repos, USER.md template, Cron status ×4, Legacy lock, Skills loadable (published),
  Skill drift ×2, loop-gov daemon. No undisposed items.
- ✅ on every governance/deploy check: AGENTS.md sync, SOUL.md sync, hooks, plugin
  content, Task schema deployed, Deploy sync, Cron runtime scripts.

## 4. Operator actions required (not agent-run)

1. **Gateway restart** — enforcement chain redeployed; the RUNNING gateway still
   executes the old enforcer in memory. Until restarted, `end_change` may read a
   cycle as PENDING right after scoring (retry after `cycle_query` is a workaround,
   not the fix). Run from a separate shell outside the gateway: the lifecycle guard
   prints the exact command if attempted inside.
2. **nginx zone-defs** — `sudo cp ~/hermes-cortex/ops/install/deploy/nginx/hermes-zone-defs.conf /opt/homebrew/etc/nginx/hermes-zone-defs.conf` (template updated by deploy; live copy not applied — printed by the deploy log).

## 5. Known deferrals (unchanged by this pull)

- Stranded skills `devops/docker-management` + `devops/cortex-deployment-sync`
  (deployed copies newer than repo source) — already recorded deferred (titus,
  2026-10-21/22). Recovery is its own governed change per `reconcile-stranded-skills.py`.
- PENDING cycle #7435 (`member-edit-ipi-validated-update`, session `sess_cb06267f73e5`)
  belongs to the morning koscap-mwi session, covered by the legacy-lock deferral; not
  this session's to score.

## Result

Pull ✅ → deploy ✅ (315 files, enforcement re-locked, Deploy sync) → doctor 471 pass /
1 fail, where the single fail is the same pre-existing out-of-scope steadfaste check
this fleet has accepted on every prior update cycle.
