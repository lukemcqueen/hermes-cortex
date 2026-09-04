---
name: agent-collector-troubleshoot
version: 1.0.0
category: devops
description: "Use when collectors can't send. Diagnoses bus, paths, crons."
platforms: [linux, macos]
---

# Agent Collector Troubleshoot — Diagnostic & Repair

Run this checklist when `agent-learning-collector --force` produces no output,
no report appears in `inbox_orchestrator`, or the agent can't reach the orchestrator.

## Step 1 — Script Deployment

```bash
# Collector script
ls -la ~/.hermes-cortex/scripts/agent-learning-collector.py
python3 -m py_compile ~/.hermes-cortex/scripts/agent-learning-collector.py

# Session-mine
ls -la ~/.hermes/bin/session-mine
ls -la ~/.hermes-cortex/offline/session_mine.py
python3 -m py_compile ~/.hermes-cortex/offline/session_mine.py
```

**If missing:** `bash ~/.hermes-cortex/scripts/cortex-update.sh`

## Step 2 — Bus Connectivity

```bash
# Bus URL
grep -r "CORTEX_BUS_URL" ~/.hermes-cortex/cortex-bus.conf ~/hermes-cortex/.env 2>/dev/null

# Auth
grep -r "CORTEX_BUS_AUTH\|CORTEX_BASIC_AUTH" ~/.hermes-cortex/cortex-bus.conf 2>/dev/null

# Test
curl -sI "$(grep CORTEX_BUS_URL ~/.hermes-cortex/cortex-bus.conf 2>/dev/null | head -1 | cut -d= -f2)" | head -3
```

**Required:** HTTP 200 + auth creds. Missing = contact Moses.

**Known 401 trap (2026-09-04):** the collector's `_build_auth_headers` prefers
`CORTEX_BASIC_AUTH` and gives up on 401, whereas `lib/cortex_bus.py` prefers the
Bearer `CORTEX_BUS_TOKEN` and falls back to Basic on 401/403. A stale Basic cred
STILL in `cortex-bus.conf` alongside a valid token makes the collector 401 while
`bus_send` (moses/esther handlers) succeeds on the same host. Collector-and-lib
must agree: prefer the token, add the Basic fallback.

## Step 3 — Cron Status

```bash
hermes cron list | grep -E "agent-learning-collector|agent-session-mine"
```

**Expected:** Both exist, `enabled: true`. If missing, `bash ~/.hermes-cortex/scripts/install-crons.sh`.

## Step 4 — Path Alignment

Collector scans `~/brain/lessons/`. Session-mine must write there.

```bash
grep "LESSONS" ~/.hermes-cortex/offline/session_mine.py
# Correct: HOME / "brain" / "lessons"
# Wrong:   HOME / "brain" / "<hostname>" / "lessons"
```

**If wrong:** run `cortex-update.sh` to get the Jul 27 fix.

Make dirs:
```bash
mkdir -p ~/brain/lessons ~/brain/learnings/pending ~/brain/learnings/sent
```

## Step 5 — Send Test Report

```bash
python3 ~/.hermes-cortex/scripts/agent-learning-collector.py --dry-run   # preview
python3 ~/.hermes-cortex/scripts/agent-learning-collector.py --force     # send
```

**Output:** `Sent: Learning Report: ... (msg_id=...)`. Silent = bus issue (Step 2).

**Silent-but-OK does NOT mean delivered (2026-09-04):** the collector swallows send
failures (prints `ERR: ...` then exits 0, so `last_status=ok`). The bus `strict input
formatting` envelope contract (repo commit 9cec8b8e, 2026-09-02) rejects the
collector's legacy payload with HTTP 400 `Invalid message: unknown envelope
field(s): topic; subject: required UPPER_CASE protocol name; priority: optional
integer` — no report is staged and the collector still reports `ok`. A 400/`ERR`
line in the run means conformance, not connectivity: drop the `topic` field, UPPER_CASE
the subject (and keep every `LIKE 'Learning Report%'` consumer in sync), integer
priority 0-100. Verify by watching `~/.hermes-cortex/state/learning-reports/` for
a newly staged file, not by trusting `last_status`.

## Step 6 — Submit Ad-Hoc Learning

```bash
mkdir -p ~/brain/learnings/pending
cat > ~/brain/learnings/pending/$(date +%Y%m%d)-test.md << 'EOF'
---
title: Pipeline test
type: discovery
---
Testing end-to-end. If received, pipeline is healthy.
EOF
python3 ~/.hermes-cortex/scripts/agent-learning-collector.py --force
```

Moves to `~/brain/learnings/sent/` after success.

## Step 7 — State Files

```bash
cat ~/.hermes-cortex/state/agent-learning-collector-state.json
cat ~/.hermes-cortex/state/agent-session-mine-state.json
```

**Expected:** Valid JSON. If corrupt, delete and re-run.

## Step 8 — Bootstrap Session Mining

```bash
python3 ~/.hermes-cortex/scripts/agent-session-mine-cron.py
cat ~/.hermes-cortex/state/agent-session-mine-state.json
# Should show: bootstrap_done: true
```

## Error Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| `--dry-run` shows content, `--force` prints none | No bus creds | Step 2 |
| `ERR: Send failed: 400 ... unknown envelope field(s): topic` | Envelope not conformant to strict bus contract (9cec8b8e) | Drop `topic`, UPPER_CASE subject, int priority; sync consumers |
| Send 401 (collector) while `bus_send` works on same host | Collector prefers stale Basic cred, no token/Basic fallback | Retire stale Basic, add fallback (Step 2 note) |
| `last_status=ok` but no staged report | 400 swallowed; collector exits 0 on failure | Watch state/learning-reports/ not `last_status` |
| Lesson count 0 | session_mine.py path | Step 4 |
| `session-mine: not found` | Not deployed | `cortex-update.sh` |
| Collector silent | Already sent | Delete state, re-run |
| ModuleNotFoundError | PYTHONPATH | Export `~/.hermes-cortex/scripts` |
