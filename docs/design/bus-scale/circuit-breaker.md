# Per-Queue Circuit Breaker + Backpressure — Design Document

> **BUS-P1-4:** Backpressure, inbox limits, per-agent isolation.
> Priority: 🟡 P1 (prevents cascading failure). Effort: 2 days.

## Problem

A single slow or crashed consumer can accumulate thousands of messages in its inbox.
These messages occupy Postgres rows, consume index space, and slow down SKIP LOCKED
queries on the shared `bus.messages` table. Without per-queue limits, one bad agent
can degrade the bus for everyone.

## Solution

Add per-queue inbox depth limits. When a queue exceeds its limit, `bus_send()` returns
HTTP 429 (Too Many Requests). The sender must back off and retry.

### Configuration

Default limits:

| Queue Type | Default Limit | Rationale |
|------------|---------------|-----------|
| Standard inbox | 5000 messages | ~50 MB at 10KB/msg |
| DLQ | 500 messages (advisory) | Don't block, but warn |
| Workflow queues | 10000 messages | Higher throughput expected |

Per-agent overrides via `bus.permissions`:

```sql
ALTER TABLE bus.permissions 
    ADD COLUMN IF NOT EXISTS config jsonb DEFAULT '{
        "max_inbox_depth": 5000,
        "max_dlq_warn": 500
    }';
```

### Server-Side Implementation

```python
# Configuration
DEFAULT_MAX_INBOX_DEPTH = 5000
DEFAULT_DLQ_WARN = 500
RECOVERY_THRESHOLD = 0.8  # Reject sends until depth drops to 80% of limit

# Per-queue cache (refreshed every 30s or on demand)
_queue_config: dict[str, QueueConfig] = {}

class QueueConfig:
    max_depth: int
    breached: bool  # Currently rejecting sends

async def get_queue_config(queue: str) -> QueueConfig:
    if queue not in _queue_config:
        # Look up permissions for this queue's agent
        agent = _agent_from_queue(queue)
        row = await db.fetchrow(
            "SELECT config FROM bus.permissions WHERE agent_name = $1", agent
        )
        config = row["config"] if row else {}
        max_depth = config.get("max_inbox_depth", DEFAULT_MAX_INBOX_DEPTH)
        _queue_config[queue] = QueueConfig(max_depth=max_depth, breached=False)
    return _queue_config[queue]

async def check_backpressure(queue: str) -> bool:
    """Check if a queue is under backpressure. Returns True if send should be blocked."""
    config = await get_queue_config(queue)
    
    depth = await pgmq_depth(queue)
    
    if config.breached:
        # In recovery — allow sends when depth drops below 80% of limit
        if depth < config.max_depth * RECOVERY_THRESHOLD:
            config.breached = False
            return False
        return True
    
    if depth > config.max_depth:
        config.breached = True
        _record_backpressure(queue, depth, config.max_depth)
        return True
    
    return False

@app.post("/api/pgmq/send")
async def api_send(request: SendRequest):
    # Check backpressure before processing
    if request.queue.startswith("inbox_") and not request.queue.endswith("_dlq"):
        blocked = await check_backpressure(request.queue)
        if blocked:
            raise HTTPException(
                status_code=429,
                detail=f"Queue {request.queue} at capacity. "
                       f"Max depth: {config.max_depth}. "
                       f"Current depth: {depth}. Retry after consumption."
            )
    
    # ... normal send logic ...
```

### Backpressure Lifecycle

```
Depth grows:    0 → 1000 → 3000 → 5000 → 5001 (BREACH!)
                  ↓
Send rejected:   HTTP 429 ← agent_moses
                  HTTP 429 ← agent_gisu  
                  HTTP 429 ← workflow_dispatcher
                  ↓
Agent consumes:  5001 → 4000 → 3500 → 3000 (still blocked — above 4000)
                  ↓
Recovery:        3000 → 2999 (BELOW 4000 = 80% of 5000 → UNBLOCKED)
                  ↓
Sends accepted:  HTTP 200 again
```

### DLQ Advisory Warning

DLQs don't block sends — they warn. This prevents cascading failures where
a blocked send prevents the consumer from processing pending messages
(which would clear the DLQ).

```python
if queue.endswith("_dlq"):
    depth = await pgmq_depth(queue)
    if depth > DEFAULT_DLQ_WARN:
        logger.warning(f"DLQ {queue} has {depth} messages — investigate")
        bus_dlq_warnings_total.labels(queue=queue).inc()
    # Never block DLQ sends
```

### Metrics

```
# HELP bus_backpressure_activations_total Times per-queue backpressure activated
# TYPE bus_backpressure_activations_total counter
bus_backpressure_activations_total{agent="gisu"} 3

# HELP bus_backpressure_depth Queue depth at backpressure activation
# TYPE bus_backpressure_depth gauge
bus_backpressure_depth{agent="gisu"} 5001
```

### Notification on Activation

When a queue enters backpressure:
1. Metric incremented
2. Event logged to `bus.audit_log` (when available)
3. Optionally: Moses receives a fleet alert (via existing cron framework)

### Rationale for 80% Recovery

Using 80% of the limit as the recovery threshold prevents rapid
breach → recover → breach cycling (thrashing). An agent that rises to 5001,
consumes down to 4999, and has sends re-enabled will immediately re-breach
on the next small send.

### Files Changed

| File | Action |
|------|--------|
| `ops/services/agent-bus/server.py` | Add backpressure check to send handler |
| `ops/services/agent-bus/config.py` | Create — per-queue config cache |
| `ops/services/agent-bus/schema/auth.sql` | Add `config` column to permissions |
