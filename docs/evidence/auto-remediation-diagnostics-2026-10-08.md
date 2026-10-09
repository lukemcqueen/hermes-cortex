# Auto-Remediation Diagnostic Evidence — 2026-10-08 23:52:45 KST

## Phase 0: Repo skill fence balance
```
(no UNBALANCED lines = balanced)
```

## Sensor output (agent-remediation-sensor.py)
```
[]
```

## cron-auto-remediate.sh diagnose
```
ISSUES:1
  GIT:dirty-scripts:/Users/luke/hermes-cortex
```

## git status (dirty-scripts source)
```
A  docs/evidence/cortex-bus-inbox-check.py
M  docs/evidence/cron-bus-inbox-check-overnight-2026-10-08.md
 M ops/scripts/install/install-pi-mcp.sh
 M ops/scripts/manage/audit-pi-integration.sh
 M tests/test_pi_integration_audit.py
?? .hermes-cortex/
?? adapters/
?? docs/evidence/auto-remediation-diagnostics-2026-10-08.md
?? docs/evidence/mycortex-mem-password-resolution.md
?? docs/evidence/pi-mycortex-memory-wiring-audit-2026-10-08.md
```

## Service health (2026-10-08)
```
Host is NON-SERVER (IS_SERVER=false) — per skill host-gating, sensor [] expected here.
git branch: main | detached: no
docker: 15 containers running
ollama: 200
Fleet context: CORTEX_BUS_URL is a remote URL (ported :13004), not local :8903 — this host
is not a server agent, so no local fleet bus/nginx service to remediate.
```
## Conclusion
One issue reported (GIT:dirty-scripts) = peer Pi-MCP work-in-progress (install/audit
scripts + evidence docs) on a clean main branch, no detached HEAD, no merge conflict,
no service failure. Per peer-update/do-no-harm rules, do NOT commit/stash/revert a
peer's uncommitted work. No remediation required.
