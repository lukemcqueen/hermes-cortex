# P3 step 3 — hyphen sweep cortex-* -> fleet-* — evidence record (2026-11-06)

Cycle 14307 (task p3-hyphen-sweep-step3). The remaining hyphenated
cortex-* names are gone: 35 file renames + repo-wide content sweep.

## What changed

- **35 git mv file renames** (list in the commit message): mcp-servers trio
  (fleet-bus-mcp / fleet-context-mcp / fleet-sandbox-mcp), the doctor
  entrypoint fleet-doctor.py, bus scripts (bridge-run/generate,
  processor, remediate, failover-watchdog), fleet-context.py,
  fleet-dogfood.sh, install scripts (fleet-profile, fleet-setup-langfuse,
  install-fleet-update-cron, setup-fleet-bus), fleet-update-mutex.py,
  fleet-agent-manager.py, fleet-health.sh, fix-fleet-venv.py,
  fleet-sandbox.py, pi extensions (fleet-context.ts / fleet-governance.ts),
  fleet-config.yaml, fleet-bus.service template, fleet-gateway.service +
  both plist templates, 4 doc files, 3 test files.
- **ONE-RELEASE shim** ops/scripts/manage/cortex-doctor.py (registered +
  deployed; verified live below) keeps every legacy doctor invocation
  working.
- **Content sweep, 27 token families, longest-first, word-boundary** across
  339 non-record files (1084/1084 lines): mcp__cortex_bus__* MCP tool
  strings -> mcp__fleet_bus__*, every file/command reference. Excluded by
  design: docs/evidence|older|reviews, tests/artifacts (records), the plan
  doc (historical), the enforcer (dual-accept), fleet-update.sh
  (functional legacy refs — registers edited separately), the shim, restore
  and migrate-orch-bus-names scripts (functional legacy).
- **Register map 394 -> 395** (353 register + 42 register_orch; 390
  ${CORTEX_DEPLOY_HOME}/ visible; 136 derivable; 254 no-rule + 5
  ${HOME}/ = 259). docs/deploy-registry-pattern.md + plan synced with
  computed numbers; test_repo_resource_paths asserts them (26 green).
- **Live bridge-unit repair**: the deploy's orphan-sweep deleted the
  old-named deployed scripts while the 26 cortex-bridge-*.service units
  still ExecStart'd `cortex-bus-bridge-run.py` (renamed) -> all failed.
  Patched the live unit files (bridge-run path + renamed --script names),
  daemon-reload, reset-failed -> 0 failed; 53 bridge timers active.

## Verification (run on this host, outputs cited)

- bash -n / py_compile: 0 failures across the changed set (live files).
- test battery: **113 passed** (register map 26, sanction 3, guard 2, shim
  2, mutex, never-overwrites-config, fix-fleet-venv, mcp-servers-deployed,
  gateway modules, fleet_lib 11, bus import graph 18, gateway backend +
  systemd, doctor gate smoke, doctor jev layer, doctor mcp review name).
- fix-fleet-venv.py pre-existing test drift corrected: the expected-missing
  set lacked `requests>=2.31` + `certifi>=2023.5.7` added to
  requirements.txt on 2026-11-04 (proven pre-existing at HEAD in a stash
  run, same 1 failure).
- Deploy: `bash ops/scripts/fleet-update.sh` -> **DEPLOY_RC=0**
  (502 pass - 31 warn - 0 fail - 3 info; the 25 undisposed are standing
  deferred dispositions dated 10-21..10-30).
- Deployed doctor both names: `scripts/fleet-doctor.py --quick --quiet`
  rc=0 AND legacy `scripts/cortex-doctor.py --quick --quiet` rc=0 (shim
  execs the sibling; both deployed).

## Register map (post-commentary)

395 entries (353 register + 42 register_orch), 390 ${CORTEX_DEPLOY_HOME}/
test-visible, 136 strip-ops derivable, 254 no-rule (253 + the flat-deployed
fleet-doctor.py entry; +5 ${HOME}/ = 259).
