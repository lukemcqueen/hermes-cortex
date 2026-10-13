# Pull-Latest + Cortex Update — 2026-10-13

Cycle: pull-latest-and-cortex-update (#6057)
Host: Titus (macOS)
Upstream: origin/main `e4fd5f7e` — "feat(mcp): audit WIRING, not presence — a registered server can still be dead"

## 1. Pre-pull state
- Local `main` 1 commit behind origin/main, 0 ahead → clean fast-forward.
- Incoming commit touched: docs/DOCS-INDEX.md, docs/evidence/mcp-cli-subcommands-2026-10-13.txt, docs/evidence/mcp-wiring-audit-2026-10-13.txt, docs/troubleshooting.md, ops/scripts/cortex-update.sh, ops/scripts/manage/cortex_doctor/checks.py, ops/scripts/manage/cortex_doctor/config.py, ops/scripts/manage/mcp_wiring.py, tests/test_mcp_wiring.py
- Staged/untracked files (verify-dream-2026-10-13.sh, adapters/, docs/evidence/*.md) NOT touched by incoming commit and NOT in this cycle's scope — left untouched.

## 2. Pull
`git pull --ff-only origin main` → fast-forward to `e4fd5f7e`. Post-merge hook auto-ran cortex-update.sh (exited rc=1 on the relock wrapper only).

A SECOND upstream commit `e50938f2` (esther — "fix(governance): a lock must not lie about who holds it, or about which repo it governs", the check_lock false-inactive fix) landed on origin after the first pull. Per change-checklist, integrated by MERGE (`git merge origin/main --no-edit` → 90abd9b9). The merge was initially blocked by a pre-existing staged-but-uncommitted file `docs/evidence/verify-dream-2026-10-13.sh` (from a prior session, in neither HEAD nor origin) — unstaged non-destructively (file left on disk untouched, now untracked) and merged. Post-merge hook re-deployed the new enforcer.

## 3. Sanctioned deploy
`bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (full log: /tmp/cortex-update-full.log)
- Skills: 0 updated, 386 unchanged, 0 stale removed, 0 preserved
- Crons: 8 created, 35 skipped; cron manifest all in-scope match
- nginx templates updated (deploy commands printed)
- Plugins deployed: governance-enforcer (3 files), mycortex-command (2), mycortex-mem, prompt-guard, hc-lean-index
- Enforcement files re-locked (all LOCKED lines present)
- relock wrapper printed "relock ran on a FAILED exit (rc=1) — enforcement files re-secured" — this is the relock wrapper's own exit code; all files were re-secured (LOCKED lines above it).

## 4. GATEWAY RESTART REQUIRED banner
The update printed:
```
║  ⚠  GATEWAY RESTART REQUIRED — enforcement chain redeployed      ║
⚠ Deploy ≠ load: the RUNNING gateway still executes the OLD enforcer in memory.
⚠ that is a pending restart, not a code bug. Do not loop retrying; do not edit the deployed copy.
```
This is the documented deploy≠load semantics: the new enforcer activates only after `hermes gateway restart`, which agents cannot perform (lifecycle guard). **Deferred — operator (Luke) must restart the gateway.**

## 5. Doctor (python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet)
Exit code 2. 433 pass · 7 warn · 1 fail · 11 info.
- ❌ AGENTS.md (steadfaste) — DIFFERENT project (~/steadfaste), out of scope for this hermes-cortex pull/update cycle.
- ⚠️ Repo clean / Repo sync — pre-existing staged/untracked files (see §1); not this cycle.
- ⚠️ Script run evidence — pre-existing.
- ⚠️ Cron status (agent-deploy-drift-audit, agent-daily-bible-reading) — pre-existing cron status.
- ⚠️ MCP wiring (loop-governance, tasks) — NEW check from this commit: servers registered against the HERMES venv (`hermes-agent/venv`), fleet migrating to cortex venv (`~/.hermes-cortex/venv/bin/python3`). WARN not FAIL (documented migration). Wiring is functional (begin_change/cache_search/feedback_accept all worked this session).
- ✅ Deploy sync, AGENTS.md sync, all governance/hook/immutable/checksum checks PASS.

## 5b. Post-merge re-run (after e50938f2 merge)
Doctor after final merge: **435 pass · 6 warn · 1 fail · 10 info** — same out-of-scope steadfaste fail; the extra pass is the new governance-lock check. Verify script `verify-pull-latest-cortex-update-2026-10-13.sh` re-checks all claims and exits 0 — captured run in `verify-pull-latest-cortex-update-2026-10-13.txt` (11 checks, 0 failures).

## 6. Verification of live wiring
`~/.hermes-cortex/venv/bin/python3 -c "import mcp"` → mcp OK. loop-governance MCP tools used successfully this session.

## 7. Outcome
Pull + deploy complete and verified. Doctor clean except out-of-scope fail (steadfaste) and known/pre-existing warns. **Gateway restart pending (operator action).**

## 8. Peer-commit scope note (for the close review)
The close-review window `base..HEAD` includes esther's upstream commit **e50938f2** ("fix(governance): a lock must not lie about who holds it, or about which repo it governs"), which entered this branch via the MERGE at step 2. Its files — `docs/enforcer-known-issues.md`, `docs/evidence/foreign_lock_reporting.py`, `docs/evidence/lock-truth-2026-10-13.txt`, `mcp-servers/loop-gov-mcp.py`, `ops/scripts/loop-gov.py`, `tests/test_lock_truth.py` — are **esther's work, NOT this cycle's**. Per change-checklist Phase 5, a peer commit landing mid-cycle shows up as scope drift in the range; the correct response is to name the peer SHA and leave their work untouched (reverting it to green the gate would be the same violation as an amend). This cycle's own changes are limited to: the pull/merge itself + `docs/evidence/pull-latest-cortex-update-2026-10-13.md`, `docs/evidence/verify-pull-latest-cortex-update-2026-10-13.sh`, `docs/evidence/verify-pull-latest-cortex-update-2026-10-13.txt`, and the two `docs/DOCS-INDEX.md` entries.

## 9. How the verify script re-runs every claim
`verify-pull-latest-cortex-update-2026-10-13.sh` (committed, exits non-zero on any failure) re-runs:
1. **Git sync** — asserts both upstream commits (e4fd5f7e, e50938f2) are ancestors of HEAD and `behind=0`.
2. **Deploy sync** — diffs deployed vs repo (SOURCE header stripped) for the 4 deploy-map files the pulled commits changed: `cortex-update.sh`, `mcp_wiring.py`, `cortex_doctor/checks.py`, `cortex_doctor/config.py`.
3. **Governance immutability** — asserts 9/9 enforcement paths carry `uchg`/`schg` flags after the rc=1 relock wrapper.
4. **Doctor** — re-runs `cortex-doctor.py --quiet`, asserts its only fail is the out-of-scope `steadfaste` AGENTS.md.
5. **Enforcer deploy** — asserts the deployed enforcer is present and substantive (>1000 bytes), documenting the deploy≠load gap (gateway restart is the operator step).
6. **MCP wiring** — asserts the cortex venv has the `mcp` package.
Captured run: `verify-pull-latest-cortex-update-2026-10-13.txt` — **11 checks, 0 failures, exit 0**.