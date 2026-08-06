---
name: pgmq-consumer-patterns
description: "Use when fixing bus consumers or false-unreachable agents."
version: 1.0.0
author: Hermes Cortex
metadata:
  hermes:
    tags: [bus, pgmq, consumers, migration, health]
    related_skills: [cortex-bus, cortex-bus-automation, agent-health-monitoring]
---

# PGMQ Consumer Patterns

Class-level patterns for building and debugging PGMQ bus consumers, learned from
the inbox→PGMQ migration (2026-08). Applies to any queue where one process
drains and others need the data.

## Pattern 1: The Drainer Must Persist — Consumers Read State, Not the Live Queue

**Rule:** Any queue that one cron drains is invisible to other consumers. PGMQ
`read` pops only `pending` messages; a consumer that runs *after* the drainer
will find the queue empty every time. Never have a second consumer race the
drainer on the live queue — especially an hourly consumer vs a 10-minute
drainer.

**Correct design:**
```
producer ──send──> queue ──drainer (every 10m)──> archive
                            └── persist latest per key ──> state.json
consumer (hourly) ──reads state.json──> data
consumer fallback: bus_read(queue, vt=60) peek for not-yet-drained pings
```

**Example (health pings, fixed 2026-08-04, commit 87df0c73):**
- `orch-clean-health-queue.py` drains `inbox_health_check` every 10m; while
  archiving it persists each agent's latest vector+ts to
  `~/.hermes-cortex/state/inbox-health-state.json` and updates `last-seen.json`.
- `orch-health-report.py` reads that state file; live `bus_read` is only a
  fallback for pings the drainer hasn't caught yet.

**Symptoms of violating this rule:** "agent 🔴 unreachable despite healthy
pushes", stale `last-seen.json` for days/weeks, queue depth near 0 at consumer
time.

## Pattern 2: Transport-Migration Sweep — Silent-404 Consumers

**Rule:** When a transport migrates (file inbox → PGMQ bus, HTTP → gRPC, etc.),
the old endpoint often disappears with no error to callers. Any consumer still
hitting the retired surface gets a silent 404 → returns None → downstream
false alarms. Docs and skills lag too.

**Sweep checklist (grep the whole repo, not just the obvious dirs):**
```
grep -rn "api/inbox\|api/delete\|MOSES_INBOX_URL\|moses-inbox.conf" ops/ scripts/ skills/ docs/
```
Also grep for removed script names (e.g. `orch-team-health`) — docs reference
them long after deletion.

**Verify claims against LIVE code before fixing:** the proposal said a skill was
stale; confirmation required checking (a) the deployed bus server's route table
(no `/api/inbox`), (b) the actual push script's endpoint, (c) which consumer
still called the old API, (d) whether the referenced poller was removed from the
repo (`git log --diff-filter=D`).

## Pattern 3: Verify End-to-End, Not Just Unit

After a consumer fix, prove the full path with real messages:
1. Seed: `bus_send("inbox_health_check", {"from": "<agent>", "subject": "health", "body": "{...}"})`
2. Drain: run the drainer exactly as cron does (set `CORTEX_REPO` and
   `PYTHONPATH=ops/scripts` — direct `python3 path/to/script.py` from another
   cwd fails the `hermes_paths` import).
3. Consume: run the report script; confirm the agent shows ✅.

## Pitfalls

- **Direct script runs mislead.** A no_agent cron gets `PYTHONPATH` from
  `build_subprocess_env()`; a bare `python3 script.py` from a random cwd will
  `ModuleNotFoundError: hermes_paths`. Reproduce the cron env
  (`CORTEX_REPO=~/hermes-cortex PYTHONPATH=~/hermes-cortex/ops/scripts`).
- **A queue drained before the consumer runs is NOT proof of a dead producer.**
  Check the drainer's persistence file before blaming the push side.
- **Deployed copies of scripts/skills are copies.** Fix the repo source, deploy
  via `cortex-update.sh`, then verify the deployed file (SOURCE header differs
  from repo raw MD5 — hash comparison must strip the header).
