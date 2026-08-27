# Client-Side Durable Outbox (Bus Retry) — Design Document

> **BUS-P1-7 (client half):** When the bus is unreachable, `bus_send()`
> must not lose the message. Queued locally with backoff; the sweep cron
> re-sends when the bus recovers.
> Priority: 🟡 P1 · Effort: 1 day · Status: **Implemented 2026-08-27**

## Problem

`bus_send()` returns `None` when the bus is unreachable (3 attempts + optional
fallback URL, then `ConnectionError`). For fleet dispatch — `UPDATE_REQUEST`,
`ROLLBACK_REQUEST`, advisories — a lost message means an agent never receives
the instruction. The server-side circuit breaker (gap #7) makes the bus return
429 under pressure; the client must handle that gracefully too.

## Solution

A **durable outbox** on the sending side: `bus_send()` falls back to writing
the message to `~/.hermes-cortex/bus-retry/` (atomic file) instead of dropping
it. A no_agent cron (`agent-bus-retry-sweep`, every 15 min) re-sends queued
messages with exponential backoff, dedup, and poison-pill quarantine.

```
bus_send(queue, msg)
  ├─ bus reachable ──→ delivered (server queue)
  └─ bus unreachable ──→ ~/.hermes-cortex/bus-retry/<queue>-<hash>.json
                          └─ agent-bus-retry-sweep (*/15, no_agent)
                              ├─ backoff due? ──→ wait (2^attempts min ±20%)
                              ├─ duplicate already pending? ──→ delete file
                              ├─ send OK ──→ delete file
                              ├─ send fails ──→ attempts++; wait
                              └─ attempts >= 12 / corrupt ──→ quarantine/
```

## Design

### Files

| Asset | Location |
|-------|----------|
| Outbox library | `ops/scripts/lib/bus_outbox.py` (enqueue + sweep + CLI) |
| Fallback hook | `ops/scripts/lib/cortex_bus.py` → `bus_send()` |
| Canonical dedup | `cortex_bus.bus_find_duplicate()` / `bus_norm_body()` |
| Cron | `agent-bus-retry-sweep` (`*/15 * * * *`, no_agent) in `install-crons.sh` |
| Tests | `tests/test_bus_outbox.py` (17 tests) |

### Retry file

```json
{
  "version": 1,
  "queue": "inbox_moses",
  "message_body": {"from": "...", "subject": "UPDATE_REQUEST", "...": "..."},
  "created_at": "2026-08-27T07:30:00+00:00",
  "attempts": 0,
  "last_error": ""
}
```

Filename `<queue>-<sha1(queue+corr_id+body)[:12]>.json` is **content-derived**:
re-enqueueing the same message deterministically overwrites (write-time dedup),
immune to wall-clock races.

### Enterprise properties

- **Atomicity** — tmp file + `fsync` + `os.replace` + dir fsync. A crash
  never leaves a torn retry file; a crash between write and rename leaves
  only a harmless `.tmp` (ignored by the sweep, which globs `*.json`).
- **No caller mutation** — `bus_send` serializes into a local copy; the
  caller's dict is never modified. The pristine message is what gets
  hashed and queued, so dedup is stable across attempts.
- **Backoff + jitter** — `min(2^attempts, 1024)` minutes ±20%. Attempts
  counts failed sweeps; a fresh file retries on the first sweep (≥1 min
  old). Jitter prevents a thundering herd when the bus recovers.
- **Resend dedup** — before re-sending, `bus_peek` the target queue; if an
  identical message (same correlation_id, OR same subject+body — the
  canonical `bus_find_duplicate` rule shared with `hc.py`) is already
  pending, delete the file. Closes the at-least-once hazard where a send
  landed but its response was lost.
- **Poison-pill quarantine** — corrupt JSON or `attempts >= 12` moves the
  file to `bus-retry/quarantine/`; it stops retrying forever and the cron
  alerts (exit 1 + message). A malformed file can't wedge the sweep.
- **Concurrency** — the sweep holds an `flock` on `.sweep.lock`; cron and
  manual sweeps can't race. A second sweep exits immediately.
- **Watchdog pattern** — empty stdout + exit 0 when the outbox is clean;
  the cron delivers only on quarantine or persistent (≥3) failures.

### Config

| Env | Default | Purpose |
|-----|---------|---------|
| `CORTEX_BUS_RETRY_DIR` | `~/.hermes-cortex/bus-retry/` | Outbox location (tests override) |
| `CORTEX_BUS_NO_OUTBOX` | unset | `1` = hard-fail to `None` (no queueing) |

## Why files, not a DB or daemon

- **Files are crash-safe** — one message = one durable file; `os.replace`
  is atomic. No schema, no lock tables, no daemon to supervise.
- **Inspectable** — `ls ~/.hermes-cortex/bus-retry/` shows exactly what is
  undelivered; `cat` any file to see the message.
- **Zero server changes** — this is purely client-side; the bus server is
  untouched, satisfying the "zero agent-side changes" principle from the
  server side and "no server work" from the client side.

## Alternatives considered

| Option | Rejected because |
|--------|------------------|
| Retry inside `bus_send` (blocking loop) | Holds the caller hostage to the outage; a long outage blocks the calling cron's whole tick. |
| In-memory queue | Lost on process restart — the exact failure mode we're removing. |
| SQLite outbox | A whole DB for a directory of JSON files; files are simpler and grep-able. |
| Full daemon / background worker | Overkill for ~20 lines of sweep logic; the existing cron infrastructure already runs every 15 min. |

## Verification

- **Unit** — 17 tests: atomic enqueue, deterministic overwrite, backoff
  growth/cap, resend-success deletion, dedup-on-resend, corrupt quarantine,
  max-attempts quarantine, flock contention, `bus_send` fallback wiring,
  watchdog CLI silence/alert.
- **Live** — dead primary + dead fallback → message queued (caller dict
  unmutated) → bus recovered → sweep delivers → file removed → message
  confirmed in `inbox_esther` via `bus_peek`.
- **Regression** — `hc.py` dedup delegates to the canonical
  `bus_find_duplicate` (verified); 33 tests pass across the suite.

## Related

- [Per-Queue Circuit Breaker](circuit-breaker.md) — the server-side half
  (429 under pressure); this doc is the client's response to that signal.
- [Inner Body JSON Fix](inner-body-json-fix.md) — the `body` auto-parse the
  outbox relies on for stable hashing.
- `skills/devops/cortex-bus*` — bus diagnostics and operations.
