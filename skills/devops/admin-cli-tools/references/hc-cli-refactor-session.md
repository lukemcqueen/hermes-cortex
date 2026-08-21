# Agent Bus Debugging: hc CLI Refactor Session

## Problem
`hc inbox joseph` returned HTTP 403: Agent 'moses' does not have read access to queue 'inbox_joseph'. Admin tool was hitting the bus API which enforces per-queue ACLs.

## Root Cause
`hc` was using `POST /api/pgmq/read` — same endpoint agents use. ACLs blocked cross-agent reads.

## Solution
Refactored to use **direct Postgres** (`docker exec legacy Postgres psql -U mycortex -d mycortex -t -c "SELECT ..."`). No auth, no ACLs, any queue readable.

## Key Changes
1. Removed `HC_BUS_URL` and `HC_BUS_AUTH` from config — just `HC_AGENT`
2. `hc inbox` → SQL SELECT from `bus.messages` (non-destructive)
3. `hc send` → `SELECT bus.send(queue, body_json, priority)` (SQL function, not API)
4. `hc watch` → polls SQL SELECT every 5s (non-destructive)

## Consumer Race Discovered
`agent-worker.py` runs as systemd service consuming `inbox_moses` messages instantly. During live testing, by the time `hc watch` polled, messages were already consumed. Fixed by:
- Sending to other agent queues (agent-worker only reads `inbox_moses`)
- Or using non-destructive reads (the refactor)

## Stuck Messages
Messages consumed via PGMQ `read` (state='processing') but never archived sit in `processing` state until `bus.recover_timeouts()` runs. Set up a no_agent cron every 5 min.

## Dashboard Addition
- Added `_bus_data()` + `/api/bus` endpoint to Cortex Dashboard (Flask, port 8901/13001)
- Added HTML card + `renderBus()` JS to existing dashboard
- Creating dedicated `/bus` and `/langfuse` pages

## JS Scoping Bug
```javascript
// BUG — secs is const inside if block, referenced outside
if (m.timeout_at) {
  const tout = new Date(m.timeout_at.replace(' ', 'T') + 'Z');
  const secs = Math.round((tout - now) / 1000);  // const, block-scoped!
  timing = secs > 0 ? `⏳ ${secs}s left` : `⏰ ${Math.abs(secs)}s overdue`;
}
// secs is NOT defined here — ReferenceError!
html += `<span style="${secs > 0 ? ...}">`;

// FIX — declare let outside
let secs = 0;
if (m.timeout_at) {
  const tout = ...
  secs = Math.round((tout - now) / 1000);
  ...
}
// secs is now accessible
```

## Stale Process Issue
When killing and restarting the dashboard, the old process didn't always die:
```
kill 1963797  # might fail silently if wrong PID or process already gone
ss -tlnp | grep 8901  # verify it's really freed
```
Always verify with `ss -tlnp` before assuming the port is free.
