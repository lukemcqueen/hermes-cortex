# Real Example: `orch-team-messages.sh` Stale Entry

**Date:** 2026-07-21
**Commit:** 3f56914

## Symptom

The `remediation-sensor.py` reported every 5 minutes:

```json
{"type": "script_missing", "severity": "high", "detail": "Missing script: orch-team-messages.sh"}
```

## Investigation

1. **File search:** `search_files("orch-team-messages")` — found only in:
   - `remediation-sensor.py` (the required_scripts list)
   - `moses-inbox-remediation/SKILL.md` (architecture section)
   - `brain/lessons/` (lessons confirming it was never deployed)

2. **Path check:** The script didn't exist anywhere — not in `ops/scripts/`,
   `~/.hermes/scripts/`, or `~/.hermes-cortex/scripts/`.

3. **Install script check:** No `create_cron` block referenced it in
   `install-crons.sh` or `install-orch-crons.sh`. It only appeared in uninstall
   arrays — placed there during the bare-name→agent-* rename cleanup as a
   safe way to remove old entries.

4. **Lesson confirmation:** `session_search("orch-team-messages")` returned
   lessons stating "never actively created — only in uninstall arrays for cleanup."

## Fix

Removed `orch-team-messages.sh` from the `required_scripts` array in
`remediation-sensor.py` (line 72). The array went from:

```python
"orch-team-messages.sh", "cron-auto-remediate.sh", ...
```

to:

```python
"cron-auto-remediate.sh", ...
```

## Verification

```bash
python3 ~/hermes-cortex/ops/scripts/manage/remediation-sensor.py
# Output: only git_issue (uncommitted changes from the fix itself)
# No more script_missing
```

## Deployment

```bash
cp ~/hermes-cortex/ops/scripts/manage/remediation-sensor.py ~/.hermes-cortex/scripts/
cp ~/hermes-cortex/ops/scripts/manage/remediation-sensor.py ~/.hermes/scripts/
```

## Lesson

The `required_scripts` array in the sensor is a **manually maintained list** that
drifts from the install scripts. Every time a cron script is renamed or
removed from an install script, the sensor's list should be checked too.
This is currently a manual step — there's no automated sync between the
cron install scripts and the sensor's hardcoded list.
