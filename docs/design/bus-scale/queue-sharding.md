# Queue Sharding — Design Document

> **BUS-P1-1:** Horizontal scale via Postgres hash sharding.
> Priority: 🟡 P1 (needed before 50 agents). Effort: 3-4 days.

## Problem

All PGMQ queues live in a single Postgres schema (`bus.messages`).
At 1000 agents with 2000 queues, `SKIP LOCKED` reads contend on the same table.
Write contention, read latency, and index pressure grow linearly with agent count.

## Solution

Distribute queues across 8 Postgres schemas (`bus_0` through `bus_7`) using
a hash of the agent name. The bus server routes reads/writes to the correct shard.

### Architecture

```python
def _shard_for_queue(queue_name: str) -> int:
    """Determine which shard owns a queue by hashing the queue name."""
    # Extract agent name from queue name
    # "inbox_moses" → "moses"
    # "inbox_moses_dlq" → "moses"
    # "workflow_dispatch" → use consistent hash on queue name
    
    agent_name = _extract_agent(queue_name)
    shard = int(hashlib.sha256(agent_name.encode()).hexdigest(), 16) % NUM_SHARDS
    return shard
```

### Server-Side Routing

The bus server wraps every PGMQ operation with shard routing:

```python
class ShardedPGMQBackend:
    """PGMQ backend that routes to the correct shard schema."""
    
    def __init__(self, num_shards=8):
        self.num_shards = num_shards
        self.connections = {}  # shard_index → async connection
    
    async def _get_conn(self, queue_name):
        shard = self._shard(queue_name)
        if shard not in self.connections:
            self.connections[shard] = await create_pool(f"dbname=gbrain options=-csearch_path=bus_{shard},public")
        return self.connections[shard]
    
    async def send(self, queue, body, **kwargs):
        conn = await self._get_conn(queue)
        # Execute PGMQ send on the correct shard schema
        
    async def read(self, queue, vt=60, **kwargs):
        conn = await self._get_conn(queue)
        # Execute PGMQ read with SKIP LOCKED on the correct shard
        
    async def archive(self, queue, msg_id):
        conn = await self._get_conn(queue)
        # Execute PGMQ archive on the correct shard
```

### Shard Schema

Each shard has an identical copy of the PGMQ tables:

```sql
-- Schema: bus_0, bus_1, ..., bus_7
CREATE SCHEMA IF NOT EXISTS bus_0;
CREATE SCHEMA IF NOT EXISTS bus_1;
-- ...

-- Create all PGMQ tables in each schema
-- queues, messages, archives, (no tokens/permissions — those stay global)
```

The `bus.tokens` and `bus.permissions` tables remain in the global `bus` schema
(they're metadata, not queue data, and don't need sharding).

### AGENT_NAME for Non-Agent Queues

For system queues (`workflow_dispatch`, `workflow_step_result`, `inbox_health_check`),
use a consistent hash based on the queue name:

```python
SPECIAL_QUEUES = {
    "workflow_dispatch": 0,      # pinned to shard 0
    "workflow_step_result": 0,   # pinned to shard 0
    "workflow_timeout": 0,       # pinned to shard 0
    "inbox_health_check": 0,     # pinned to shard 0
    "inbox_bus_health": 0,       # pinned to shard 0
}
```

Since these queues handle workflow infra (high-frequency polling), pinning them
to one shard simplifies the router while isolating them from agent inboxes.

### Read-Only Agent Operations

Operations that span all queues (admin queries) need scatter-gather:

```python
async def list_all_queues():
    """List queues across ALL shards (admin only)."""
    results = []
    for shard in range(NUM_SHARDS):
        conn = await _get_shard_conn(shard)
        rows = await conn.fetch("SELECT name, depth FROM bus_0.queues")
        # Note: each shard's tables are in its own schema,
        # accessed via search_path or schema-qualified
        results.extend(rows)
    return results
```

This is only used by admin/health endpoints, not by agent operations.

### Migration Path

1. Create 8 shard schemas with identical table definitions
2. Add shard routing to the bus server (behind a feature flag)
3. Run a backfill: copy existing messages to the correct shard
4. Switch reads/writes to sharded mode
5. Drop the old `bus.messages` table (after verification window)

During migration, both the old `bus.messages` and the new `bus_*.messages` tables
are checked. Once all queues are confirmed correctly routed, the old table is dropped.

### Resharding

To increase the shard count (e.g., 8→16):

1. Update `NUM_SHARDS` config
2. Run `reshard.py` that re-hashes all queues and moves messages
3. During resharding, reads check both old and new shard

This is a rare operation (~once per order-of-magnitude scale).

### Shard Health

Each shard's connectivity and depth are exposed via VictoriaMetrics metrics (pushed
from the bus server):

```
bus_shard_depth{shard="3", queue="inbox_moses"} 42
bus_shard_errors{shard="7"} 0
```

### Files Changed

| File | Action |
|------|--------|
| `core/cortex_bus/server.py` | Add shard routing to PGMQ backend |
| `core/cortex_bus/shard.py` | Create — shard management module |
| `core/cortex_bus/reshard.py` | Create — resharding utility |
| `core/cortex_bus/schema/shard.sql` | Create — shard schema DDL |
| `ops/scripts/install/install-bus.sh` | Update — create shard schemas |
