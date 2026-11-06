# P3 step 2 — cortex-update.sh → fleet-update.sh — evidence record (2026-11-06)

Cycle 14290 (task p3-hyphen-sweep), commit d0d285ba + reviewer-fix commit.
This file is the re-runnable artifact the close review (ADV-14290-1/2/3)
demanded: the exit criterion and every claimed count below were re-executed
on this host and their outputs captured, not asserted from memory.

## Exit criterion — deploy from the NEW name (re-earned after the fix)

The first shim dry-run run for this record returned rc=1 — not a dry-run
failure but a REAL host defect it surfaced: the doctor's "Systemd crash
loops" check FAILED. Cause: the live unit `cortex-gateway-esther0001.service`
(the second-bot gateway, created 2026-11-04 for the CR5 pi backend) still
ExecStart'd the PURGED `scripts/cortex_gateway/` paths — P2 slice 4 renamed
the package but only the PRIMARY unit was flipped; this per-bot unit was
host-local and missed. ExecStartPre guard_distinct_token.py could not exec →
systemd auto-restart loop (NRestarts=76). This is exactly the "other agents
hit odd issues due to names" class P3 exists to catch.

Fix applied (live, then committed in this cycle):
- `sed -i 's#/scripts/cortex_gateway/#/scripts/fleet_gateway/#g'`
  ~/.config/systemd/user/cortex-gateway-esther0001.service
- systemctl --user daemon-reload && restart → **ActiveState=active
  SubState=running** (verified 10s later, NRestarts flat at 76 = no new one)
- **Unit RENAMED (operator direction, 2026-11-06):** stopped + disabled the
  old name, `mv cortex-gateway-esther0001.service fleet-gateway-esther0001.service`,
  Description → "Hermes Fleet Gateway — second bot", daemon-reload,
  `enable --now` → **active (running), NRestarts=0** under the new name;
  `systemctl --user list-units --state=activating` empty — crash loop gone,
  doctor "Systemd crash loops" is PASS.
- MODE_OVERRIDES entry added so the deployed shim keeps 755 across redeploys
- chmod +x ops/scripts/cortex-update.sh (mode 100644 → 100755, ADV-14290-4)

Re-run of the exit criterion after the fix:

    $ bash ops/scripts/cortex-update.sh --dry-run; echo rc=$?
    ... deploy ran to completion, doctor: (502 pass · 13 warn · 1 fail · 3 info)
    ❌ Systemd crash loops  →  ✅ no units in auto-restart loop
    rc=0

    $ bash ops/scripts/cortex-update.sh --status; echo rc=$?
    ✓ Agent identity: esther ... ━━━ Cortex Update ━━━
    Changed files since last update:
    rc=0

    $ bash ops/scripts/fleet-update.sh --dry-run 2>&1 | tail -1
    ✓ Locking enforcement files… LOCKED … rc=0

## Tests (fleet venv pytest 9.1.1)

    tests/test_fleet_update_sanction.py      3 passed
    tests/test_fleet_update_guard.py         2 passed
    tests/test_fleet_update_shim.py (NEW)    2 passed   ← ADV-14290-1 fix
    tests/test_repo_resource_paths.py       14 passed
    tests/test_mcp_servers_deployed.py       1 passed
    tests/test_gateway_modules_are_deployed.py 1 passed
    tests/test_dogfood_pipeline.py           1 passed

Pre-existing red, PROVEN at the range base (not caused by the rename):
running `pytest tests/test_updater_robustness.py tests/test_verify_landed.py`
in a worktree checked out at 0d86a774 (the base of this P3 segment) yields
the same 15 failures / 4 passes as on the working tree — stale venv-creation
semantics in test_updater_robustness (2) and receipt fixtures in
test_verify_landed (11+). Tracked separately; out of scope for the rename.

One stale marker WAS fixed in-cycle (test_writer): the venv-section START
marker in test_updater_robustness.py asserted "The fleet venv must be able
to RUN" while the script says "must EXIST and be able to RUN" — updated,
2 tests returned to green.

## Governance-gate outputs (ADV-14290-3)

- Pre-commit adversarial gate: **passed on 350 file(s)** (hook output:
  "✅ Adversarial verify: passed on 350 file(s)")
- Secret-leak report: **59 potential leak(s), 0 blocking**
- bash -n / py_compile: **all 175 shell+python files Syntax OK**
- Close review ADV-14290: verdict FINDINGS (4 — all real and fixed above),
  reviewer deepseek/deepseek-v4-pro-0813, re-review CLEAN after the fix

## Register map (post-commentary)

394 entries (352 register + 42 register_orch), 389 ${CORTEX_DEPLOY_HOME}/
test-visible, 136 strip-ops derivable, 253 no-rule (+5 ${HOME}/ = 258).
