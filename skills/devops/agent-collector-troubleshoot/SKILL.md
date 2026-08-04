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
| `--dry-run` shows content, `--force` silent | No bus creds | Step 2 |
| Lesson count 0 | session_mine.py path | Step 4 |
| `session-mine: not found` | Not deployed | `cortex-update.sh` |
| Collector silent | Already sent | Delete state, re-run |
| ModuleNotFoundError | PYTHONPATH | Export `~/.hermes-cortex/scripts` |
