---
name: pipeline-debugging
description: Check the data store and service logs before changing code.
version: 1.0.0
category: devops
author: Gisu
license: MIT
platforms: [linux]
aliases: [iswc-debugging, cisnet-debugging]
---

# Pipeline Debugging — Data + Service + Code

## The Core Insight

Pipeline bugs have three layers of truth:
- **Code** — what the developer intended to happen
- **Database** — what actually happened (committed state)
- **Service logs** — what the runtime environment actually did

These three are often different. The most common debugging mistake is
changing code based on assumptions that the database and logs would
contradict in seconds.

## Method: Data-First Pipeline Debugging

### Step 1: Check the data store

Before any code change, query the database tables that hold the entity's
processing state. This reveals:
- Was the entity processed? (status, timestamps)
- Was it rejected or did it succeed? (status code, rejection reason)
- What was the actual output? (ISWC assigned, error message)

For the MWI ISWC/CIS-Net pipeline:
```sql
SELECT w.socworkcde, i.iswc, s.status, s.rejection_reason
FROM tblworkinfo w
LEFT JOIN tbliswc i ON i.dbkey = w.dbkey
LEFT JOIN tbliswcsync s ON s.dbkey = w.dbkey
WHERE w.socworkcde = '<work-code>';
```

### Step 2: Check the service logs

Find the service-agent that processes the pipeline stage and grep for
the entity's identifier:

```bash
# Find the logs
find /service/root -name "*.log" | head -20

# Grep for the entity
grep -ri '<entity-id>' /service/root/ 2>/dev/null
```

Key signals:
- **404/401 on API calls** — the service can't authenticate or reach its upstream
- **NullPointerException / crash on startup** — service never processes anything
- **"Processed successfully"** — service did work, no error on its side
- **Empty results** — entity didn't reach this service stage

### Step 3: Connect the findings

Map what the DB, logs, and code each say. If they disagree, the data
store and logs are more reliable than the code — they show what actually
happened.

Example from a real session: The code said "work exists in CIS-Net with
no ISWC → send UPDATE." The DB said "status=REJECTED, no ISWC." The
Tomcat ISWC Agent logs said "401 Unauthorized on updateAgentRun — agent
crashing before processing." The actual root cause was an expired API
key, not a code bug.

### Step 4: Fix the actual blocker

Only make code changes when the code is demonstrably wrong (DB + logs
confirm the code path is incorrect). If the DB shows "service never
processed the entity" and the logs show "service crashed on startup,"
fix the service — not the pipeline code.

### Step 5: Verify

After the fix, re-query the DB and re-check the logs to confirm the
entity was processed. Don't claim the fix works until you can cite:
- DB query showing the updated status
- Log line showing successful processing

## Pitfalls

- **Making code changes without checking the DB** — wastes cycles on
  hypotheses the DB disproves instantly
- **Assuming the code route is the problem** — the pipeline might never
  reach the code you're fixing
- **Claiming "done" without verification** — a stated claim without tool
  output is a promise, not evidence
- **Ignoring service logs** — a crashed service silently drops all
  entities; no code change can fix that
- **Overcomplicating the fix** — the `iswc_or_error` nil fix was 2 lines
  and fixed the "unknown error" cascade. Most pipeline fixes are small
  when you identify the right break point.

## Reference

- `references/iswc-cisnet-pipeline-debugging-2026-07-29.md` — full session
  narrative for the MWI ISWC/CIS-Net pipeline debugging session
