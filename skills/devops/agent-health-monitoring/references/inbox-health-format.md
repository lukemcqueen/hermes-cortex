# Inbox Health Data Format — Client-Only Agents (PGMQ Bus)

Agents with no inbound network access (Titus on macOS, local dev machines) push
their health data to Moses via the **PGMQ Agent Bus** instead of serving an HTTP
endpoint. The retired file-inbox API (`api/inbox`, `api/delete`, `MOSES_INBOX_URL`)
was removed in the inbox→PGMQ migration (commit `0f01556d`) — do not use it.

## Push Format — Compact Vector (recommended)

The client agent sends a JSON body via `health-vector-push.sh` to queue
`inbox_health_check` (`POST /api/pgmq/send`, subject `health`):

```json
{"from": "titus", "subject": "health", "body": "{\"v\": [1,1,1,1,1,1,1,1,1], \"h\": \"t\", \"t\": 1782882578}"}
```

| Field | Type | Meaning |
|-------|------|---------|
| `from` | `str` | Agent name (e.g. "titus") |
| `subject` | `str` | MUST be `health` |
| `body` | `str` (JSON) | The health payload: `{"v": [...], "h": "<host>", "t": <unix-ts>}` |
| `v` | `list[int]` (9 elements) | Standard health vector: 1=up, -1=down, 0=n/a |
| `h` | `str` | Hostname (agent name, e.g. "titus") |
| `t` | `int` | Unix timestamp |

Config: `health-vector-push.sh` reads `CORTEX_BUS_URL` + `CORTEX_BASIC_AUTH`
(or Bearer `CORTEX_BUS_TOKEN`) from `~/.hermes-cortex/cortex-bus.conf`.

## Push Format — Rich Health-Report (optional)

See `references/rich-health-report-format.md` for the full schema. Includes
services, issues, resources, and uptime metadata.

## Fetch Pattern (Consumer Side — Drain + Persist)

The retired anchor-keep pattern (keep oldest ping, DELETE newer ones) is **gone**.
Today the pipeline is:

```
Every 10 min:
  1. orch-clean-health-queue.py drains inbox_health_check (bus_read + archive)
  2. For each ping it persists the agent's LATEST vector to
     ~/.hermes-cortex/state/inbox-health-state.json  →  {"<agent>": {"vector": [...], "ts": "<iso>"}}
  3. It also updates ~/.hermes-cortex/state/last-seen.json (laptop grace)
```

Consumers (`orch-health-report.py`, dashboard) read `inbox-health-state.json`
instead of polling the queue — the queue is transient (drained every 10 min),
the state file always holds the latest vector per agent.

```python
state_file = Path.home() / ".hermes-cortex" / "state" / "inbox-health-state.json"
entry = json.loads(state_file.read_text()).get("titus")
vec = entry["vector"] if entry else None
```

**Key properties of the drain-and-persist pattern:**

- The queue never grows — drained every 10 min
- The state file holds at most one entry per agent (always the latest)
- `last-seen.json` records the drain timestamp for alert suppression during
  laptop sleep (grace period, no artificial anchors)
- If the drain cron stops, the queue backlogs AND the state file goes stale —
  both are visible in the health report

## Multi-Topic Search (REMOVED)

The old implementation searched both `health` and `general` topics via
`api/inbox`. That API is gone; all pings go to the single `inbox_health_check`
queue.

## API Endpoint Details (current)

| Aspect | Detail |
|--------|--------|
| Send | `POST /api/pgmq/send` with `{"queue": "inbox_health_check", "message": "<json string>"}` |
| Read | `POST /api/pgmq/read` with `{"queue": "inbox_health_check", "vt": 60}` |
| Archive | `POST /api/pgmq/archive` with `{"queue": ..., "msg_id": ...}` |
| Depth | `GET /api/pgmq/depth/inbox_health_check` |
| Auth | Basic Auth with `CORTEX_BASIC_AUTH` or Bearer `CORTEX_BUS_TOKEN` from `~/.hermes-cortex/cortex-bus.conf` |
| Timeout | 5 seconds per request |
| Retired | `GET /api/inbox`, `DELETE /api/delete/{filename}` — 404 on the PGMQ bus |
