---
name: detached-worker-pattern
description: "Cron tick budget kill: detached worker + result sweep."
version: 1.0.0
category: devops
metadata:
  hermes:
    tags: [cron, background, worker, timeout, at-least-once, result-receipt, deadlock, decouple]
    related_skills: [cron-job-management, fleet-commands]
---

# Detached Worker Pattern — Surviving the Execution Budget

## When to use

Any **budgeted, at-least-once consumer** (a cron tick, a message handler tick,
a job queue worker) that must run work whose worst-case runtime can exceed the
consumer's execution budget:

- Cron ticks with an execution timeout (`HERMES_CRON_TIMEOUT`, no_agent script
  limits) running subprocess chains (pull + deploy + doctor ≈ 390s worst case
  inside a 300s budget)
- Handlers that early-archive the request message then process it — a kill
  mid-processing loses the receipt forever (the message never re-processes)
- Any "send a result back" flow where silence is indistinguishable from success

## The failure it prevents (verified 2026-08-18)

Fleet `UPDATE_REQUEST` dispatch: 5 hosts consumed the request and the updates
LANDED (verified via direct probes: repo + deploy sync at the target SHA), but
**0/5 returned UPDATE_RESULTs**. Root cause: the handler ran
pull+cortex-update+doctor synchronously (~390s worst case) inside a cron tick
budgeted at ~300s. The tick was killed mid-processing — after the early-archive
— so the request was never re-processed and the receipt was silently lost.
"Consumed but no result" looked like a bus failure; it was an execution-budget
kill.

## The pattern (four pieces)

### 1. Detached worker

```python
subprocess.Popen(
    [sys.executable, "-c", WORKER_CODE, handler_path, json.dumps(msg_body), corr],
    start_new_session=True,          # survives the parent's budget kill
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
```
- `start_new_session=True` detaches from the parent's process group so the
  cron's kill (which targets the tick's group) cannot take the worker down.
- The worker does the LONG work and writes its result to a state file:
  `state/pending-results/<corr>.json` — never sends over the bus itself.

### 2. State-file result + in-flight marker

- Worker writes `<corr>.json` when done (success OR crash — wrap in try/except
  so a crash still yields a structured error result).
- Handler writes `<corr>.running` when spawning; worker deletes it on finish.
  The marker also tells concurrent readers "a deploy is mid-flight" — see #4.

### 3. Per-tick sweep (runs EVERY tick, even with no new work)

```python
for f in sorted(PENDING_DIR.glob("*.json")):
    result = json.loads(f.read_text())
    send_result(corr, result)          # bus / webhook / queue
    f.unlink(missing_ok=True)
for m in sorted(PENDING_DIR.glob("*.running")):
    if now - m.stat().st_mtime > TIMEOUT:
        send_result(corr, {"success": False, "error": "worker died"})
        m.unlink(missing_ok=True)
```
- A worker that finished while the spawning tick was killed is still delivered
  by the next tick — the guarantee that makes the pattern correct.
- Stale `.running` markers (worker died without writing) become explicit
  timeout error results — never permanent silence.
- Duplicates on re-sweep are possible (kill between send and delete); make
  consumers idempotent by correlation id, not by hoping for exactly-once.

### 4. In-flight guard for concurrent health checks

A tick that ALSO runs its own health doctor will catch the worker's mid-deploy
state (checksum mismatches, files half-rewritten) and fire false FAIL alerts.
Skip the health check while any `.running` marker exists.

## Key implementation notes

- The worker must insert its own `sys.path` before importing the parent module
  (`sys.path.insert(0, str(Path(handler_path).parent))`) — cron children don't
  inherit PYTHONPATH.
- Load the parent module by file path (`importlib.util.spec_from_file_location`)
  and call its existing process function — don't duplicate the logic.
- Spawn-failure fallback: if `Popen` raises, fall through to the legacy
  synchronous path rather than dropping the request.
- The tick itself now returns in seconds instead of minutes — a side benefit
  that also frees the tick budget for other work.

## Verified reference implementation

`agent-message-handler.py` UPDATE_REQUEST branch (commit `282045ec`,
2026-08-18): `_spawn_update_worker()` / `_send_pending_update_results()` /
`_update_worker_code()` in `ops/scripts/agent/agent-message-handler.py`,
`state/pending-update-results/` under `CORTEX_DEPLOY_HOME`. Tested end-to-end:
worker → sweep → result received; worker-death (stale marker) → timeout result;
mid-deploy health-doctor skip (killed a false 9-fail alert).

## Pitfalls

- **Don't keep the result send inside the worker** — if the worker itself is
  killed (OOM, host restart) the result file never appears and the sweep's
  timeout path covers it; if the send were inside the worker, both die together.
- **Budget math**: sum ALL synchronous subprocess timeouts (pull 60s + update
  300s + doctor 30s = 390s worst case) against the ACTUAL tick budget
  (HERMES_CRON_TIMEOUT, default 300s, fleet-wide env — not per-job). If
  worst-case > budget, this pattern is required, not optional.
- **Early-archive makes kills fatal**: if the consumer archives the request
  before processing, a kill mid-processing is unrecoverable without a
  pending-result file. The pattern is the recovery mechanism.
- **Sweep must run before the "no work → return early" shortcut** in the tick,
  or completed results wait for the next message to arrive.
