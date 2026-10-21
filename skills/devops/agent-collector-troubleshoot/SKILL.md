---
name: agent-collector-troubleshoot
version: 1.0.0
category: devops
description: "Use when a report is missing or a collector can't send."
platforms: [linux, macos]
---

# Agent Collector Troubleshoot — Diagnostic & Repair

Run this checklist when `agent-learning-collector --force` produces no output,
no report appears in `inbox_orchestrator`, or the agent can't reach the orchestrator.

## Step 0 — Prove it is MISSING before touching the collector

A report can be absent from what YOU read while the agent sent it perfectly. Rule these
out first — every one of them costs an hour if skipped, and none of them is a collector bug:

- **Two staging dirs, two report kinds.** `agent-learning-collector` reports stage to
  `~/.hermes-cortex/state/learning-reports/<agent>-<ts>.md`; the older chunked
  `Skill Report:` messages stage to `state/skill-reports/`. Look at the dir named for the
  SUBJECT you are chasing, and read the newest file per agent instead of counting files.
- **Which host staged it is a race, not a property.** BOTH orchestrators poll the shared
  `inbox_orchestrator`, so whichever ticks first consumes the report and stages it on ITS OWN
  host — a report consumed by the peer is invisible locally with no error anywhere. Before
  concluding an agent stopped reporting, compare BOTH hosts' staged dirs
  (`ssh <peer> "ls -1t ~/.hermes-cortex/state/learning-reports | grep '^<agent>-' | head"`).
- **"Received" and "digested" are different facts — check the CONSUMER's scope.** The pipeline
  that turns reports into a digest reads the staged dir on the host IT runs on, while staging
  happens on whichever host won the race. So an agent can be reporting every 6h, its files sitting
  on the peer, and the digest never mentioning it — a scope mismatch, not a send failure. Read the
  consumer's own record before blaming the agent: where its input path points, and its REAL
  schedule from the cron entry/timer rather than the schedule its documentation claims (a skill
  saying "daily 04:00" against a live `1,3,5 04:34` job sends the next reader down the wrong path).
- **Size the window to the queue's churn.** `?limit=N` caps the archive page, and a queue
  carrying health-probe traffic burns through N fast: the newest N messages can span only a
  couple of hours, so "no reports from <agent>" often just means "older than the page I
  fetched". Widen `since_minutes` AND `limit`, then aggregate per sender.
- **Never call a consumer dead from one peek.** The handler is a periodic tick (minutes).
  A message enqueued after the last tick is PENDING by design — compare its `enqueued_at`
  against the consumer's last and next run (`systemctl --user list-timers`) BEFORE reporting
  a stalled consumer. To separate "consumer is dead" from "the API cannot remove messages",
  hand-archive ONE test message and watch the depth drop (`{"success":true}`, depth N→N-1).

Who last reported, from the archive (the authoritative record of what was consumed — the
live peek sees only what is still pending):

```bash
set -a; . ~/.hermes-cortex/.env; set +a   # never echo the token value
curl -s -H "Authorization: Bearer $CORTEX_BUS_TOKEN" \
  "http://127.0.0.1:8903/api/pgmq/archives/inbox_orchestrator?limit=2000&since_minutes=300000" \
| python3 -c "import json,sys,collections; d=json.load(sys.stdin); m=d if isinstance(d,list) else d.get('messages',[]); c=collections.Counter(((x.get('body') or {}).get('subject'),(x.get('body') or {}).get('from')) for x in m); [print(n,s,f) for (s,f),n in c.most_common(20)]"
```

Also weigh the agent KIND: a laptop agent is offline much of the day, and the collector is
silent when its delta is empty, so an irregular cadence from an offline-capable host is
expected — not evidence of breakage. Compare against a server agent before calling it a fault.

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
grep -r "CORTEX_BUS_URL" ~/hermes-cortex/.env ~/hermes-cortex/.env 2>/dev/null

# Auth
grep -r "CORTEX_BUS_AUTH\|CORTEX_BASIC_AUTH" ~/hermes-cortex/.env 2>/dev/null

# Test
curl -sI "$(grep CORTEX_BUS_URL ~/hermes-cortex/.env 2>/dev/null | head -1 | cut -d= -f2)" | head -3
```

**Required:** HTTP 200 + auth creds. Missing = contact Moses.

**Known 401 trap (2026-09-04):** the collector's `_build_auth_headers` prefers
`CORTEX_BASIC_AUTH` and gives up on 401, whereas `lib/cortex_bus.py` prefers the
Bearer `CORTEX_BUS_TOKEN` and falls back to Basic on 401/403. A stale Basic cred
STILL in `.env` alongside a valid token makes the collector 401 while
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
