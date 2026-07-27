# Long-Poll Read Support — Design Document

> **BUS-P1-3:** Reduce Postgres load with HTTP long-poll reads.
> Priority: 🟡 P1 (needed at 50+ agents). Effort: 2 days.

## Problem

Every agent polls its inbox every 5 minutes. At 1000 agents, that's 200 queries/min
on `bus.messages` just for the handler. LLM-driven inbox reads add more. Most reads
return empty — the ratio of productive reads to wasted reads approaches 1:1000+.

## Solution

Add HTTP long-poll (also called "comet" or "hanging GET") to the `bus_read()` API.
When no message is available, the server holds the connection for up to `poll_timeout`
seconds instead of returning immediately. When a new message arrives for that queue,
the poll returns it instantly.

### API Change

Add an optional `poll_timeout` parameter to `POST /api/pgmq/read`:

```json
{
  "queue": "inbox_moses",
  "vt": 60,
  "poll_timeout": 30
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vt` | 60 | Visibility timeout in seconds (unchanged) |
| `poll_timeout` | 0 | Max seconds to hold the connection when no message. 0 = poll once (current behavior) |

### Server-Side Implementation

```python
@app.post("/api/pgmq/read")
async def api_read(request: ReadRequest):
    queue = request.queue
    vt = request.vt or 60
    poll_timeout = request.poll_timeout or 0
    
    # Try immediate read
    msg = await pgmq_read(queue, vt)
    if msg:
        return msg
    
    # If no message and poll_timeout > 0, long-poll
    if poll_timeout > 0:
        # Poll with backoff — check every 2 seconds up to poll_timeout
        deadline = time.monotonic() + poll_timeout
        while time.monotonic() < deadline:
            # Wait a short interval to avoid busy-looping
            await asyncio.sleep(2)
            msg = await pgmq_read(queue, vt)
            if msg:
                return msg
    
    # Still no message after poll
    return None
```

### Agent-Side Adoption

Since this is a **server-side change**, no agent code changes are needed immediately.
Existing consumers without `poll_timeout` get the current behavior.

When agents opt in, the `cortex_bus.py` library gets a new function:

```python
def bus_read_longpoll(queue, vt=60, poll_timeout=30):
    """Read with long-poll. Holds connection up to poll_timeout seconds."""
    return _api_request("POST", f"{BUS_URL}/api/pgmq/read", {
        "queue": queue,
        "vt": vt,
        "poll_timeout": poll_timeout
    })
```

### Why asyncio.sleep (not Postgres LISTEN/NOTIFY)

Postgres `LISTEN/NOTIFY` is tempting but has limitations:
- NOTIFY payload max is 8000 bytes (messages can be larger)
- NOTIFY is transactional — rolled back notifications never fire
- Requires persistent Postgres connection per consumer
- ASYNC notifications are per-session, not per-queue

A simple polling loop with `asyncio.sleep(2)` is:
- Simpler (no Postgres-level coordination)
- More reliable (no lost notifications)
- Easy to tune (change sleep interval per agent)
- Only hits Postgres every 2 seconds when idle (vs every 300 seconds)

### Postgres Load Calculation

**Before (poll every 5 min):**
- 1000 agents × 1 read / 300s = 3.3 reads/s on Postgres
- Plus 1000 archive sends
- Plus agent-message-handler reads every 5 min

**After (long-poll every 2s):**
- 1000 agents × 1 read / 2s = 0.5 reads/s (one every 2s, but most return no new message)
- Actually: each agent gets one PG read every 2s while idle. That's 500 reads/s. **WORSE!**

Wait — let me recalculate more carefully.

**Before:** Each handler agent (1000) polls every 5 min = 300 seconds. That's 1000/300 = 3.3 reads/sec.

**After with 2s polling:** Each agent polls every 2 seconds. That's 1000/2 = 500 reads/sec. That's WORSE.

The issue is that `asyncio.sleep(2)` with a PG read every 2s is MORE reads, not fewer. The real savings come from:
1. Reducing the absolute number of PG reads per agent (check less often)
2. Eliminating the LLM-driven inbox read crons (they also poll)

Actually the correct approach is:

**Long-poll with 30s timeout and 2s sleep between PG checks:**
- Each check does 1 PG read
- Over 30s of idle time: 15 PG reads
- But the agent is idle 99% of the time...

No, the real point of long-poll is:
- The agent makes ONE HTTP request. That request is held open for 30s.
- During those 30s, the server checks PG every 2s → 15 PG reads per agent per 30s
- If a message arrives within the 30s, the agent gets it instantly (no longer waiting 5 min)

Without long-poll:
- Agent makes an HTTP request, gets empty, immediately retries
- Or: agent makes an HTTP request every 5 min → 1 PG read per 5 min = very low load
- But: agent takes up to 5 min to notice a message

The trade-off is: responsiveness vs PG load. Long-poll trades 15 reads/30s for instant delivery.

**Actually, the smarter design for the agent:**

The agent keeps the HTTP connection held open on the server side for 30s. During those 30s, the server checks PG every 5 seconds (not 2). That's 6 PG reads per 30s per agent.

If all 1000 agents are long-polling: 6000 PG reads per 30s = 200 PG reads/sec.

Without any long-poll: 1000/300 = 3.3 PG reads/sec.

So yes, long-poll with sleep-2s-check actually INCREASES PG reads. The benefit is NOT PG savings — it's instant delivery.

Let me redesign this. The real PG savings strategy is:
1. The server only needs to check PG once when a message arrives for a queue that has an active poll
2. Use a memory-based notification system: when `bus_send()` delivers a message to a queue, check if there's an active poll for that queue, and wake it up

This way: PG is hit once when idle (no message), and once when a message arrives. Net: minimal PG reads regardless of agent count.

Let me rewrite this design properly.

Actually wait. Let me re-read my original design in the architecture review. I said:

> Keep the current bus_read() API but change the server behavior: if no message, hold the connection open for up to 30 seconds (HTTP long-poll). If a message arrives in that window, return it immediately.

The key is the "if a message arrives in that window" part. The server waits until a message arrives OR 30s passes. NOT polling every 2s.

But how does the server know when a message arrives without polling PG?

Option A: In-memory event system. When `bus_send()` is called for queue X, check if there's an active long-poll waiting on queue X and wake it up.
Option B: PG NOTIFY. Bus sends `NOTIFY queue_message, 'inbox_moses'` after every `bus_send()`. Long-poll does `LISTEN inbox_moses` and waits for the notification.

Let me go with Option A (in-memory, simpler) but also document Option B as the future path.

Actually, let me use a hybrid: 
- The server maintains an in-memory dict `active_polls: dict[str, list[asyncio.Event]]`
- When `bus_read(..., poll_timeout=30)` finds no message, it registers an event for that queue and waits
- When `bus_send()` succeeds, it fires the event for that queue
- The waiting polls are woken up, re-read PG, and return the message

This way PG is read:
1. Once when `bus_read()` is called (finds nothing)
2. Once after `bus_send()` fires the event (finds the message)
3. If no message arrives in 30s, the wait times out (no PG read)

Net: 1-2 PG reads per agent per message, regardless of poll frequency. That's the savings.

Let me rewrite the design with this approach.<｜end▁of▁thinking｜>That design needed a rethink — let me rewrite the long-poll with the right approach (in-memory event system, not periodic PG polling).

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write_file">
<｜｜DSML｜｜parameter name="content" string="true"># Long-Poll Read Support — Design Document

> **BUS-P1-3:** Reduce Postgres load with HTTP long-poll reads.
> Priority: 🟡 P1 (needed at 50+ agents). Effort: 2 days.

## Problem

Every agent polls its inbox periodically. At 1000 agents polling every 5 minutes,
that's ~200 reads/min. Most return empty. The ratio of productive to wasted reads
approaches 1:100. This is wasteful and doesn't scale.

But more importantly: **responsiveness**. An agent with a 5-minute poll interval
takes up to 5 minutes to notice an incoming message. Long-poll enables near-instant
delivery.

## Solution

Add HTTP long-poll to `bus_read()`. When no message is available, the server
holds the connection until a message arrives or a timeout expires — using an
**in-memory event system** so Postgres is ONLY queried when a message might exist.

### Core Insight

The wrong approach is "poll Postgres every N seconds while waiting." That
_increases_ Postgres load. The right approach:

1. Agent calls `bus_read(..., poll_timeout=30)` → server queries PG once → empty
2. Server registers the agent's queue in an **in-memory wait list**
3. Server holds the HTTP response, waiting on an `asyncio.Event`
4. When `bus_send()` delivers a message to that queue, it fires the event
5. The waiting handler queries PG once more → finds the message → returns it
6. If `poll_timeout` expires first → returns null (no PG query on timeout)

**Net: 2 PG reads per delivered message, regardless of poll interval.**

### API Change

```json
// POST /api/pgmq/read
{
  "queue": "inbox_moses",
  "vt": 60,
  "poll_timeout": 30
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `poll_timeout` | 0 | Max seconds to hold connection. 0 = return immediately (current behavior) |

### Server-Side Implementation

```python
# In-memory wait list
_active_polls: dict[str, list[asyncio.Event]] = {}
_lock = asyncio.Lock()

async def _register_poll(queue: str) -> asyncio.Event:
    """Register a waiting poll for a queue. Returns an event to wait on."""
    event = asyncio.Event()
    async with _lock:
        if queue not in _active_polls:
            _active_polls[queue] = []
        _active_polls[queue].append(event)
    return event

async def _wake_polls(queue: str):
    """Wake all polls waiting for a queue."""
    async with _lock:
        polls = _active_polls.pop(queue, [])
    for event in polls:
        event.set()

async def _unregister_poll(queue: str, event: asyncio.Event):
    """Remove a specific poll registration (on timeout or early return)."""
    async with _lock:
        polls = _active_polls.get(queue, [])
        if event in polls:
            polls.remove(event)
        if not polls:
            _active_polls.pop(queue, None)

@app.post("/api/pgmq/read")
async def api_read(request: ReadRequest):
    queue = request.queue
    vt = request.vt or 60
    poll_timeout = request.poll_timeout or 0
    
    # Try immediate read
    msg = await pgmq_read(queue, vt)
    if msg:
        return msg
    
    # No message and no poll requested → return empty
    if poll_timeout <= 0:
        return None
    
    # Register for long-poll
    event = await _register_poll(queue)
    
    try:
        # Wait for message signal or timeout
        await asyncio.wait_for(event.wait(), timeout=poll_timeout)
    except asyncio.TimeoutError:
        await _unregister_poll(queue, event)
        return None
    
    # Woken up — try reading again
    msg = await pgmq_read(queue, vt)
    return msg
```

### Send-Side Integration

When a message is sent to a queue, wake any waiting polls:

```python
@app.post("/api/pgmq/send")
async def api_send(request: SendRequest):
    # ... existing send logic ...
    result = await pgmq_send(request.queue, ...)
    
    # Wake any long-poll waiting on this queue (fire-and-forget)
    asyncio.ensure_future(_wake_polls(request.queue))
    
    return result
```

### Memory Bounds

- Each active poll holds ~200 bytes (event + dict entry + task reference)
- 1000 agents long-polling = ~200KB — negligible
- Events are removed on timeout or wake, so no memory leak

### Timeout Guarantees

- `poll_timeout` is a hard deadline. If no message arrives, the poll returns `null`
- The agent can immediately retry with a new long-poll call
- If the event fires but the message was already consumed by another poll
  (competing consumer scenario), the woken poll reads `null` and returns it.
  The agent can retry.

### Edge Cases

| Case | Behavior |
|------|----------|
| Message arrives during registration race | First PG query catches it — poll never registered |
| Two agents waiting on same queue (DLQ scan) | Event fires → both wake → one gets message, one gets null |
| Send is rolled back (PG transaction fails) | Event fires but PG query returns nothing → client gets null |
| Server crashes during poll | Agent sees connection drop → retries → new poll |
| Poll timeout and message arrive simultaneously | `wait_for` returns successfully → PG query finds message |

### Agent-Side Adoption

Since this is server-side, no agent changes are needed for compatibility.
Existing consumers without `poll_timeout` get the current behavior.

For consumers that want responsiveness, update the `cortex_bus.py` library:

```python
def bus_read_longpoll(queue, vt=60, poll_timeout=30):
    """Read with long-poll. Holds connection up to poll_timeout seconds.
    When a message arrives for this queue, returns immediately.
    """
    return _api_request("POST", f"{BUS_URL}/api/pgmq/read", {
        "queue": queue,
        "vt": vt,
        "poll_timeout": poll_timeout
    })
```

And the `agent-message-handler.py` can switch from 5-minute polling to
long-poll with immediate wake:

```python
# Old: poll every 5 min
msg = bus_read("inbox_moses", vt=60)
time.sleep(300)

# New: long-poll, wake immediately on message
msg = bus_read_longpoll("inbox_moses", vt=120, poll_timeout=60)
# If no message in 60s, PG was NOT queried during that time
```

### Future: PG NOTIFY (If In-Memory is Insufficient)

If the bus server runs in a multi-process or multi-instance setup, the in-memory
event system won't cross process boundaries. In that case:

1. `bus_send()` calls `NOTIFY queue_message, 'inbox_moses'` after writing
2. The read handler calls `LISTEN queue_message_{queue}` and `SELECT pg_notification_wait()`
3. When a notification arrives, it queries PG

This is documented but NOT implemented in this round — the in-memory approach
handles the current single-process FastAPI architecture.

### Files Changed

| File | Action |
|------|--------|
| `ops/services/agent-bus/server.py` | Add long-poll logic to read handler, send wake to send handler |
