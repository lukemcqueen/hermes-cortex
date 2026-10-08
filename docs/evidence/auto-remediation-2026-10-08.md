# Auto-remediation scan — 2026-10-08 22:33 KST

Result: **nothing to fix** — sensor returned empty, all spot-checks healthy.

## Re-executable evidence

Raw capture of the actual sensor run (2026-10-08 22:33 KST), committed verbatim:
`docs/evidence/auto-remediation-sensor-2026-10-08.raw.txt`
```
[] 
sensor_exit=0
```

A runnable regression test (asserts sensor → `[]` + exit 0) lives in the
uncommitted working tree (`tests/check-remediation-health.py`), because the
`tests/` path is orchestrator-only on this host and a non-orchestrator cannot
commit there. The raw capture above is the committed, verifiable artifact.

Reproduce the capture directly:
```bash
python3 ops/scripts/health/agent-remediation-sensor.py
```

## Repo skill fence balance (no UNBALANCED lines = balanced)
```bash
cd "$HOME/hermes-cortex"
for f in $(find skills -name 'SKILL.md'); do
  n=$(grep -c '^```' "$f")
  if [ $((n % 2)) -ne 0 ]; then echo "UNBALANCED: $f ($n fences)"; fi
done
# output: (none)
```

## System resources
- Disk: root volume 926Gi, 18% used
- Ollama: `curl -s http://127.0.0.1:11434/api/tags` → HTTP 200
- Agent Bus health endpoint (`CORTEX_BUS_URL`): reachable (401 = auth-gated, expected)

## Host context
- `IS_SERVER=false` in `~/hermes-cortex/.env` → non-server host, sensor expected empty
- No fixes applied; read-only audit.