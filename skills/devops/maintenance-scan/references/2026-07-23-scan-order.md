# 2026-07-23 — Scan Order Correction

## What happened

User said "look for work that needs to be done." I ran doctor → crons → git → system, missing two critical first steps:

1. **Inbox** — 5 messages were sitting in inbox_moses from fleet agents. I queried the bus with `WHERE state = 'pending'` and got 0 because I guessed the wrong column name (`state` was correct, but `status` was wrong). The schema was in memory and in the `agent-bus` skill — I didn't check either first.
2. **Memory/session** — I had the bus schema in memory (`bus.messages has msg_id, queue_name, state`) but went straight to PSQL with wrong column names, wasting turns.

## Correct order (codified in maintenance-scan)

1. **Inbox** — check agent bus pending messages first
2. **Memory & session** — check what you already know before querying external systems
3. **Doctor** — system health
4. **Crons** — failing jobs
5. **Git** — pending changes
6. **System** — disk, RAM, load
7. **Analyze** — cross-reference findings
8. **Fix** — without asking
9. **Re-verify** — doctor must be clean

## Skills updated

- `agent-fundamentals` — added #9 (check own knowledge first) and #10 (knowledge lifecycle at start/end)
- `maintenance-scan` — inbox and memory/session are now steps 1-2 (was missing)
