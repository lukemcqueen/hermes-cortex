# Integration Test Harness — Design Document

> **BUS-P2-2:** Multi-agent bus testing for CI/CD.
> Priority: 🟢 P2 (needed for quality assurance at 100+). Effort: 3-5 days.

## Problem

There is no multi-agent integration test for the bus. The doctor's E2E test
tests one agent against itself. Nothing verifies multi-agent scenarios:
concurrent reads, competing consumers, message routing, backpressure, sharding.

## Solution

A Python test suite using `pytest-asyncio` that spawns virtual agents and exercises
the full message lifecycle across multiple agents simultaneously.

### Architecture

```python
# tests/integration/bus/conftest.py

@pytest_asyncio.fixture
async def bus_connection():
    """Fixture providing a raw bus connection (not through cortex_bus.py) for testing."""
    # Use direct HTTP to the bus server (avoid cortex_bus.py caching)
    async with httpx.AsyncClient(base_url=BUS_URL) as client:
        yield client

@pytest_asyncio.fixture
async def virtual_agents(bus_connection):
    """Fixture creating N virtual agents with their own credentials and inboxes."""
    agents = []
    for i in range(10):
        agent = VirtualAgent(f"test-agent-{i}")
        await agent.register(bus_connection)
        agents.append(agent)
    
    yield agents
    
    # Cleanup: delete test queues
    for agent in agents:
        await agent.cleanup(bus_connection)

class VirtualAgent:
    """Simulates a bus agent — sends, reads, archives, responds."""
    
    def __init__(self, name):
        self.name = name
        self.inbox = f"inbox_{name}"
        self.dlq = f"inbox_{name}_dlq"
    
    async def register(self, client):
        """Register this agent on the bus (create queues, set up permissions)."""
        # Create inbox + DLQ via API
        await client.post("/api/pgmq/queue", json={"queue": self.inbox})
        await client.post("/api/pgmq/queue", json={"queue": self.dlq})
    
    async def send(self, client, to, body):
        return await client.post("/api/pgmq/send", json={
            "queue": to,
            "message": body
        })
    
    async def read(self, client, vt=5):
        return await client.post("/api/pgmq/read", json={
            "queue": self.inbox,
            "vt": vt
        })
    
    async def archive(self, client, msg_id):
        return await client.post("/api/pgmq/archive", json={
            "queue": self.inbox,
            "msg_id": msg_id
        })
    
    async def cleanup(self, client):
        """Remove all queues."""
        # Delete via API (or mark for cleanup)
```

### Test Scenarios

```python
# tests/integration/bus/test_basic_cycle.py

@pytest.mark.asyncio
async def test_single_message_cycle(bus_connection, virtual_agents):
    """Basic: send → read → archive → confirm archived."""
    agent_a = virtual_agents[0]
    agent_b = virtual_agents[1]
    
    # Send
    resp = await agent_a.send(bus_connection, agent_b.inbox, {
        "from": agent_a.name, "subject": "TEST", "body": "hello"
    })
    assert resp.status_code == 200
    msg_id = resp.json()["msg_id"]
    
    # Read
    resp = await agent_b.read(bus_connection)
    assert resp.status_code == 200
    msg = resp.json()
    assert msg["body"]["from"] == agent_a.name
    assert msg["msg_id"] == msg_id
    
    # Archive
    resp = await agent_b.archive(bus_connection, msg_id)
    assert resp.status_code == 200
    
    # Confirm archived (read returns empty)
    resp = await agent_b.read(bus_connection)
    assert resp.status_code == 200
    assert resp.json() is None  # No messages left
```

```python
# tests/integration/bus/test_backpressure.py

@pytest.mark.asyncio
async def test_backpressure_rejects_over_limit(bus_connection):
    """Backpressure: sending > limit returns 429."""
    # Create an agent with 5-msg limit
    agent = VirtualAgent("test-limit")
    await agent.register(bus_connection)
    
    # Send 6 messages (5 is default limit for test)
    for i in range(6):
        resp = await agent.send(bus_connection, agent.inbox, {
            "from": "test", "subject": f"MSG-{i}"
        })
    
    # 6th should be blocked
    assert resp.status_code == 429
    
    # Consume one
    msg = await agent.read(bus_connection)
    await agent.archive(bus_connection, msg.json()["msg_id"])
    
    # Retry — should still fail (depth 5 > 80% of 5 = 4)
    resp = await agent.send(bus_connection, agent.inbox, {"from": "test", "subject": "RETRY"})
    assert resp.status_code == 429
    
    # Consume one more (depth 4 → below recovery threshold)
    msg = await agent.read(bus_connection)
    await agent.archive(bus_connection, msg.json()["msg_id"])
    
    # Now send should work
    resp = await agent.send(bus_connection, agent.inbox, {"from": "test", "subject": "OK"})
    assert resp.status_code == 200
```

```python
# tests/integration/bus/test_competing_consumers.py

@pytest.mark.asyncio
async def test_no_message_loss_with_two_consumers(bus_connection):
    """Competing consumers: two readers on same queue don't lose messages."""
    queue = "test-multi-reader"
    await bus_connection.post("/api/pgmq/queue", json={"queue": queue})
    
    # Send 5 messages
    for i in range(5):
        await bus_connection.post("/api/pgmq/send", json={
            "queue": queue, "message": {"seq": i}
        })
    
    # Two consumers read aggressively
    read_ids = set()
    for _ in range(10):  # 10 reads with vt=2
        r1 = await bus_connection.post("/api/pgmq/read", json={"queue": queue, "vt": 2})
        r2 = await bus_connection.post("/api/pgmq/read", json={"queue": queue, "vt": 2})
        if r1.status_code == 200 and r1.json():
            read_ids.add(r1.json()["msg_id"])
            await bus_connection.post("/api/pgmq/archive", json={"queue": queue, "msg_id": r1.json()["msg_id"]})
        if r2.status_code == 200 and r2.json():
            read_ids.add(r2.json()["msg_id"])
            await bus_connection.post("/api/pgmq/archive", json={"queue": queue, "msg_id": r2.json()["msg_id"]})
    
    # Exactly 5 unique messages were read and archived
    assert len(read_ids) == 5, f"Expected 5 unique messages, got {len(read_ids)}"
```

```python
# tests/integration/bus/test_long_poll.py

@pytest.mark.asyncio
async def test_long_poll_wakes_on_new_message(bus_connection):
    """Long-poll: waiting read wakes when a new message arrives."""
    agent = VirtualAgent("test-poll")
    await agent.register(bus_connection)
    
    # Start a long-poll read in background
    async def long_poll():
        return await bus_connection.post("/api/pgmq/read", json={
            "queue": agent.inbox, "vt": 30, "poll_timeout": 10
        })
    
    # Fire long-poll
    task = asyncio.create_task(long_poll())
    
    # Give it time to register
    await asyncio.sleep(0.5)
    
    # Send a message
    await agent.send(bus_connection, agent.inbox, {"from": "test", "subject": "WAKE"})
    
    # Long-poll should return within 2 seconds
    resp = await asyncio.wait_for(task, timeout=5)
    assert resp.status_code == 200
    msg = resp.json()
    assert msg["body"]["subject"] == "WAKE"
    
    # Clean up
    await agent.archive(bus_connection, msg["msg_id"])
```

```python
# tests/integration/bus/test_stress_200_agents.py

@pytest.mark.asyncio
@pytest.mark.slow
async def test_200_agents_100_messages_each(bus_connection):
    """Stress: 200 agents, 100 messages each = 20K messages in 5 minutes."""
    agents = []
    for i in range(200):
        agent = VirtualAgent(f"stress-{i}")
        await agent.register(bus_connection)
        agents.append(agent)
    
    # Moses sends 100 messages to each agent
    send_count = 0
    for agent in agents:
        for j in range(100):
            resp = await bus_connection.post("/api/pgmq/send", json={
                "queue": agent.inbox,
                "message": {"from": "moses", "subject": f"STRESS-{j}", "seq": send_count}
            })
            assert resp.status_code == 200
            send_count += 1
    
    # Each agent reads and archives
    total_read = 0
    for agent in agents:
        for _ in range(100):
            resp = await agent.read(bus_connection, vt=5)
            if resp.status_code == 200 and resp.json():
                await agent.archive(bus_connection, resp.json()["msg_id"])
                total_read += 1
    
    assert total_read == 20000, f"Expected 20000, got {total_read}"
    
    # Clean up
    for agent in agents:
        await agent.cleanup(bus_connection)
```

### Running the Tests

```bash
# All tests
python3 -m pytest tests/integration/bus/ -v

# Fast subset
python3 -m pytest tests/integration/bus/ -v -m "not slow"

# Slow tests (200-agent stress)
python3 -m pytest tests/integration/bus/ -v -m slow
```

### Test Infrastructure Requirements

- A running bus server (or one started by the test suite)
- PostgreSQL with bus schema
- Clean database state (test schemas `bus_test_*` that are dropped after)
- No external dependencies beyond `pytest`, `pytest-asyncio`, `httpx`

### Cleanup Guarantee

Every test must clean up after itself, even on failure:

```python
@pytest_asyncio.fixture(autouse=True)
async def cleanup_bus_state(bus_connection):
    """After every test, remove any test queues and messages."""
    yield
    # Remove all test queues
    resp = await bus_connection.get("/api/pgmq/queues")
    if resp.status_code == 200:
        for q in resp.json():
            if q["name"].startswith("test-"):
                await bus_connection.delete(f"/api/pgmq/queue/{q['name']}")
```

### CI Integration

Add to CI pipeline:
```yaml
- name: Bus integration tests
  run: |
    python3 -m pytest tests/integration/bus/ -v --timeout=120
```

### Files Changed

| File | Action |
|------|--------|
| `tests/integration/bus/conftest.py` | Create |
| `tests/integration/bus/test_basic_cycle.py` | Create |
| `tests/integration/bus/test_backpressure.py` | Create |
| `tests/integration/bus/test_competing_consumers.py` | Create |
| `tests/integration/bus/test_long_poll.py` | Create |
| `tests/integration/bus/test_stress_200_agents.py` | Create |
| `tests/integration/bus/test_sharding.py` | Create |
| `tests/integration/bus/test_audit_log.py` | Create |
