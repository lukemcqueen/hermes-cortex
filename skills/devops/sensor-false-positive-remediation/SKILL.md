---
name: sensor-false-positive-remediation
version: 1.0.0
category: devops
description: >-
  Handle false positives from the auto-remediation sensor pipeline.
  Covers the trace-before-create workflow for sensor-reported missing
  scripts and distinguishing stale sensor entries from genuine issues.
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [remediation, sensor, false-positive, cron, maintenance]
---

# Sensor False Positive Remediation

## When this applies

The `agent-remediation-sensor.py` (every 5m, no_agent) reports issues via JSON.
Not all reports indicate real problems — some are **stale entries** in the
sensor's hardcoded check lists.

## Known false positive patterns

| Sensor report | Likely cause | Action |
|---|---|---|
| `script_missing` for a script | Stale entry in `required_scripts` array | Trace references; remove if never deployed |
| `mycortex_health_check_failed` | Skills missing resolver triggers (content/marketing skills) | Pre-existing; no action unless service-level failure |
| `git_issue` — uncommitted changes | Sensor's own fix not committed yet | Commit and push the sensor fix |
| `nginx config invalid` (from `nginx -t` as non-root) | `open() "/run/nginx.pid" failed (13: Permission denied)` — pid-file permission artifact, NOT a config error | Validate with `sudo nginx -t`; don't report/revert anything (2026-08-05) |
| `Authorization: Basic ***` literal in a script (auth header "computed but never used") | **Tool-output redaction, NOT a bug.** Hermes masks any `Authorization: Basic <token>` pattern to `Authorization: Basic ***` in displayed output (canary-verified 2026-08-13). The file usually contains `f'-H "Authorization: Basic {encoded}"'` — the var IS used. | Byte-check before reporting: `python3 -c "print(open('<file>').read().count('*'))"` — 0 asterisks in the line = redacted display, code is fine. Don't re-report (Gisu FP 2026-08-13) |

## Reading the sensor's own output

The sensor cron's output lives at `~/.hermes/cron/output/922670b04cba/*.md`
(job id for `agent-remediation-sensor`). An empty issue array prints as `[]`
in the file — that is the healthy state, not an error. On hosts with
`IS_SERVER=false` in `~/hermes-cortex/.env` the sensor always prints `[]` by
design (host gating); don't expect sensor issues from them.

## Workflow: Handling `script_missing` from the sensor

### 1. Trace references

```bash
search_files(pattern="<script-name>", path="~/hermes-cortex")
```

Check: does the script exist in any `ops/scripts/` directory?
```bash
ls ~/hermes-cortex/ops/scripts/*<script-name>* 2>/dev/null
```

### 2. Check session lessons

```bash
session_search(query="<script-name>")
```

Lessons may confirm the script was deliberately never deployed — e.g. "only
appeared in uninstall arrays for cleanup, never a create_cron block".

### 3. Check install scripts

Search for the script name in:
- `ops/scripts/install-crons.sh` (create_cron blocks and uninstall arrays)
- `ops/scripts/install/install-orch-crons.sh` (orchestration crons)

If it only appears in the **uninstall** array (cleanup legacy) and never in a
`create_cron` block, the entry is stale.

### 4. Fix

**If stale:** Remove the entry from `required_scripts` in
`ops/scripts/health/agent-remediation-sensor.py`, commit, push, deploy.

**If genuinely missing:** Copy from repo source to both runtime paths.

### 5. Deploy

```bash
cp ~/hermes-cortex/ops/scripts/health/agent-remediation-sensor.py ~/.hermes-cortex/scripts/
cp ~/hermes-cortex/ops/scripts/health/agent-remediation-sensor.py ~/.hermes/scripts/
```

### 6. Verify

```bash
python3 ~/.hermes-cortex/scripts/agent-remediation-sensor.py
```

Confirm the `script_missing` issue no longer appears in output.

## Workflow: Handling `mycortex_health_check_failed`

The sensor runs `mycortex doctor --fast`. Exit code != 0 triggers this report.

**Expected non-critical issues:**
- `resolver_health` — skills without trigger rows in RESOLVER.md (content/
  marketing skills not relevant to brain ops). This is pre-existing and
  non-actionable.
- `skill_conformance` — manifest.json not found. Known/expected warning.
- `connection` — Skipping DB checks in --fast mode. Not a real failure.

**Only escalate if:** Postgres is unreachable, the autopilot service is down,
or the health score drops below 50 without a known pattern.

## Real example (2026-07-21)

`orch-team-messages.sh` appeared in sensor's `required_scripts` but:
- Never existed in any `ops/scripts/` directory
- Only appeared in uninstall arrays as cleanup legacy (from bare-name rename)
- Lesson search confirmed: "never actively created"
- Fix: removed from sensor list → commit `3f56914` → push → deploy
