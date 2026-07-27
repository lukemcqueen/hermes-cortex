# Inbox Health Data Format — Client-Only Agents

Agents with no inbound network access (Titus on macOS, local dev machines) push
their health data to Moses via the agent inbox API instead of serving an HTTP
endpoint.

## Push Format — Compact Vector (recommended)

The client agent sends a JSON body via `inbox_send` to topic `#health`:

```json
{"v": [1, 1, 1, 1, 1, 1, 1, 1, 1], "h": "titus", "t": 1782882578}
```

| Field | Type | Meaning |
|-------|------|---------|
| `v` | `list[int]` (9 elements) | Standard health vector: 1=up, -1=down, 0=n/a |
| `h` | `str` | Hostname (agent name, e.g. "titus") |
| `t` | `int` | Unix timestamp |

**Topic MUST be `health`** — `orch-team-health` only polls the `health` topic.

## Push Format — Rich Health-Report (optional)

See `references/rich-health-report-format.md` for the full schema. Includes
services, issues, resources, and uptime metadata.

## Fetch Pattern (Consumer Side — Anchor Keep)

The orchestrator (`orch-team-health.py`) polls the inbox using an **anchor-keep**
pattern:

```
Each tick (every 10 min):
  1. GET api/inbox?topic=health&limit=20
  2. Filter to messages from the target agent (client-side from-filter)
  3. Sort oldest-first by timestamp
  4. Keep the OLDEST message (the anchor) — this is proof of liveness
  5. DELETE all newer messages — redundant once consumed
  6. Parse the anchor's body and return (health_data, anchor_timestamp)
```

```python
resp = _inbox_request("api/inbox?topic=health&limit=20")
messages = resp.get("messages", [])
agent_msgs = [m for m in messages if m.get("from","").lower() == agent_key.lower()]
agent_msgs.sort(key=lambda m: m.get("timestamp", ""))  # oldest first

anchor = agent_msgs[0]
for msg in agent_msgs[1:]:  # delete newer ones
    _inbox_request(f"api/delete/{msg['filename']}", method="DELETE")

result = _parse_vector_body(anchor.get("body", ""))
```

**Key properties of the anchor-keep pattern:**

- The anchor stays in the inbox permanently — it's the "first ping ever seen"
- Newer pings are deleted on each tick — inbox stays at max 1 message per agent
- The anchor naturally persists during laptop sleep — dashboard stays green
- No artificial grace period needed — the anchor IS the grace mechanism
- `last-seen.json` records the anchor timestamp for alert suppression

## Multi-Topic Search (DEPRECATED)

The old implementation searched both `health` and `general` topics. As of
July 2026, `_fetch_inbox` only searches `health`. Client agents are instructed
(via `docs/agent-onboarding.md`) to push to `#health` topic.

## API Endpoint Details

| Aspect | Detail |
|--------|--------|
| Correct endpoint | `GET /api/inbox` (NOT `/api/messages` — that returns 404) |
| Response shape | `{"count": int, "unread": int, "messages": [...]}`, each msg has `filename`, `from`, `timestamp`, `body`, `topic` |
| Query params | `topic=health`, `limit=20` — no `from` filter server-side |
| `from` filter | NOT supported server-side — filter by `msg.get("from")` client-side |
| Auth | Basic Auth with `CORTEX_INBOX_AUTH` from `~/.hermes-cortex/.env` |
| Timeout | 5 seconds per request |
| Delete | `DELETE /api/delete/{filename}` — returns `{"status":"deleted"}` |
