# Bus Scale — User Stories

> **Vertical-sliced user stories for all P0/P1/P2 bus scaling gaps.**
> Each story follows the INVEST criteria and includes Given/When/Then acceptance criteria.

---

## Phase 0: Foundation (P0 — Before Agent #7)

### Story BUS-P0-1: Credential Provisioning API

**As** a fleet operator (Moses),  
**I want** to add a new agent to the bus with a single CLI command,  
**So that** onboarding takes 30 seconds instead of 30 minutes.

```gherkin
Feature: Agent Credential Provisioning

  Scenario: Add a new agent with all credentials created
    Given the fleet operator runs `hermes cortex agent add gisu --role worker`
    Then a Bearer token is generated and stored in `bus.tokens`
    And a permissions row is created in `bus.permissions` for `inbox_gisu`
    And an nginx htpasswd entry is created for `gisu`
    And the agent's queue `inbox_gisu` is created
    And the agent's DLQ `inbox_gisu_dlq` is created
    And a config snippet is printed that the agent can use verbatim
    And the credentials are stored in a secrets file for recovery

  Scenario: Add an orchestrator agent
    Given the fleet operator runs `hermes cortex agent add esther --role orchestrator`
    Then all worker-role setup is performed
    And the agent can also send to all inboxes (orch privilege)
    And the agent can also create queues
    And a note is printed about additional orchestrator cron setup

  Scenario: Agent name already exists
    Given agent `gisu` already exists
    When the operator runs `hermes cortex agent add gisu --role worker`
    Then the command fails with "Agent gisu already exists"
    And no credentials are modified
    And the exit code is non-zero

  Scenario: Revoke an agent
    Given agent `titus` exists with active credentials
    When the operator runs `hermes cortex agent remove titus`
    Then the Bearer token is removed from `bus.tokens`
    And the permissions row is removed from `bus.permissions`
    And the nginx htpasswd entry is removed
    And confirmation is printed: "Agent titus revoked"
```

**Acceptance criteria:**
- [ ] `hermes cortex agent add <name> --role worker|orchestrator` completes in < 2 seconds
- [ ] All bus artifacts created (token, permissions, htpasswd, queues)
- [ ] Output includes copy-pasteable config snippet
- [ ] `hermes cortex agent list` shows all agents with their roles and status
- [ ] `hermes cortex agent remove <name>` fully decommissions an agent
- [ ] All operations are logged in `bus.audit_log`

---

### Story BUS-P0-2: Inner Body JSON Auto-Parse

**As** a bus consumer (any agent),  
**I want** the inner message `body` to be auto-parsed,  
**So that** I don't have to remember to call `json.loads()` and risk silent data loss.

```gherkin
Feature: Inner Body JSON Auto-Parse

  Scenario: Send with dict inner body
    Given a consumer calls `bus_send('inbox_moses', {'from': 'test', 'body': {'key': 'val'}})`
    When another consumer calls `bus_read('inbox_moses')`
    Then `msg['body']['body']['key']` returns `'val'` (not a JSON string)

  Scenario: Send with string inner body (backward compat)
    Given a consumer calls `bus_send('inbox_moses', {'from': 'test', 'body': json.dumps({'key': 'val'})})`
    When another consumer calls `bus_read('inbox_moses')`
    Then `msg['body']['body']` is auto-parsed to dict `{'key': 'val'}`

  Scenario: Inner body is not valid JSON
    Given a consumer calls `bus_send('inbox_moses', {'from': 'test', 'body': 'not-json'})`
    When another consumer calls `bus_read('inbox_moses')`
    Then `msg['body']['body']` remains the raw string `'not-json'`
    And no exception is raised
```

**Acceptance criteria:**
- [ ] `bus_read()` auto-parses inner body if it's a valid JSON string
- [ ] `bus_read()` leaves inner body as-is if it's already a dict
- [ ] `bus_read()` leaves inner body as-is if it's not valid JSON (no crash)
- [ ] All existing consumers continue to work without changes
- [ ] No data loss from the double-encoding

---

### Story BUS-P0-3: Agent Labels + Targeted Fleet Updates

**As** Moses (fleet orchestrator),  
**I want** to target fleet updates to specific agent groups,  
**So that** I can run canary deployments (update canary → verify → update rest).

```gherkin
Feature: Targeted Fleet Updates via Agent Labels

  Scenario: Update agents matching a label
    Given agent `gisu` has labels `{group: canary, region: us-east-1}`
    And agent `joseph` has labels `{group: general, region: us-east-1}`
    When Moses sends UPDATE_REQUEST with `target_labels: {group: canary}`
    Then gisu processes the update
    And joseph ignores the update
    And joseph's UPDATE_RESULT is "label_mismatch" (skipped)

  Scenario: Update a specific agent by name
    Given agent `gisu` has labels `{group: canary}`
    When Moses sends UPDATE_REQUEST with `target_agents: ['gisu']`
    Then gisu processes the update
    And no other agents process it

  Scenario: No label filter = all agents
    Given Moses sends UPDATE_REQUEST without `target_labels` or `target_agents`
    Then every agent processes the update (current behavior preserved)

  Scenario: Agent labels managed via CLI
    Given agent `gisu` exists
    When the operator runs `hermes cortex agent label set gisu group=general`
    Then gisu's labels are updated in `bus.permissions`
    And the change is logged in `bus.audit_log`
```

**Acceptance criteria:**
- [ ] Labels attached to agents via `bus.permissions` table extension
- [ ] `agent-message-handler.py` checks `target_labels` before processing
- [ ] `target_agents` field supports name-based targeting
- [ ] No label filter = all agents process (backward compatible)
- [ ] CLI for setting/removing agent labels

---

## Phase 1: Scale (P1 — Before 50 Agents)

### Story BUS-P1-1: Queue Sharding by Agent Hash

**As** the bus server,  
**I want** messages distributed across 8 Postgres schemas by agent name hash,  
**So that** no single schema becomes a contention bottleneck at scale.

```gherkin
Feature: Queue Sharding

  Scenario: Messages routed by hash
    Given the bus has 8 shards (`bus_0` through `bus_7`)
    When `bus_send('inbox_moses', msg)` is called
    Then the message is stored in `bus_{hash('moses') % 8}.messages`
    When `bus_read('inbox_moses')` is called
    Then only the hash-determined shard is queried

  Scenario: All shards have the same schema
    Given shard `bus_0` has schema `(msg_id uuid, queue text, ...)`
    Then shard `bus_7` has the exact same schema
    And the migration tool applies DDL to all shards

  Scenario: Agent migration between shards
    Given an agent's messages are in shard `bus_3`
    When the shard count changes (e.g., 8→16)
    Then old messages in `bus_3` remain readable
    And new messages are routed by the new hash
    And reads check both old and new shards until old queue is empty

  Scenario: No agent-side changes
    Given an agent calls `bus_send` and `bus_read` via `cortex_bus.py`
    Then the agent does not know about shards
    And the agent's code does not change
```

**Acceptance criteria:**
- [ ] Hash routing implemented in bus server (not in `cortex_bus.py`)
- [ ] 8 shards created automatically on deploy
- [ ] Read/write operations hit only the correct shard
- [ ] Zero changes to agent-side code
- [ ] Schema migrations apply to all shards atomically
- [ ] Re-sharding is documented (add shards, migrate queues)

---

### Story BUS-P1-2: Prometheus Bus Metrics

**As** an SRE operating the bus at scale,  
**I want** Prometheus metrics for bus latency, queue depth, and error rates,  
**So that** I can detect problems before agents report them.

```gherkin
Feature: Prometheus Bus Metrics

  Scenario: Basic bus metrics exposed
    Given the bus server is running
    When I query `/metrics`
    Then I see `bus_send_total{queue="inbox_moses"} N`
    And I see `bus_read_total{queue="inbox_moses"} N`
    And I see `bus_archive_total{queue="inbox_moses"} N`
    And I see `bus_send_duration_seconds_bucket{le="0.01"} N`
    And I see `bus_queue_depth{queue="inbox_moses"} N`

  Scenario: Error metrics
    When a send request fails with HTTP 403
    Then `bus_send_errors_total{queue="inbox_moses", reason="forbidden"} 1`

  Scenario: Queue depth histogram
    When I query `/metrics`
    Then I see `bus_queue_depth{queue="inbox_moses"} N`
    And I see `bus_queue_depth{queue="inbox_moses_dlq"} N`
    And I see `bus_queue_depth{queue="workflow_dispatch"} N`

  Scenario: Health endpoint unchanged
    Given I query `/health`
    Then the response is still `{"status":"ok","backend":"pgmq","queues":N}`
    (metrics endpoint is separate from health)
```

**Acceptance criteria:**
- [ ] `/metrics` endpoint returns Prometheus-format text
- [ ] Counters: send, read, archive, requeue, archive_total (per queue)
- [ ] Histograms: operation duration (send, read, archive)
- [ ] Gauges: queue depth per queue, DLQ depth per queue
- [ ] Error breakdowns: per error type and queue
- [ ] No significant perf impact (< 1µs per operation)

---

### Story BUS-P1-3: Long-Poll Read Support

**As** the bus server,  
**I want** `bus_read()` to hold the connection briefly when no message is available,  
**So that** agents don't hammer Postgres with empty reads.

```gherkin
Feature: Long-Poll Read

  Scenario: Read returns immediately when message available
    Given `inbox_moses` has a pending message
    When a consumer calls `bus_read('inbox_moses', vt=60, poll_timeout=30)`
    Then the message is returned immediately (< 100ms)

  Scenario: Read holds when no message
    Given `inbox_moses` has no pending messages
    When a consumer calls `bus_read('inbox_moses', vt=60, poll_timeout=30)`
    Then the connection is held (server does not respond immediately)
    And Postgres is NOT queried again until a new message arrives or timeout

  Scenario: New message arrives during poll
    Given `inbox_moses` has no pending messages
    And a consumer has an active long-poll read
    When a new message is sent to `inbox_moses` within 30 seconds
    Then the poll returns the new message immediately

  Scenario: Timeout returns empty
    Given `inbox_moses` has no pending messages for 30 seconds
    When a consumer calls `bus_read('inbox_moses', vt=60, poll_timeout=30)`
    Then the poll returns `null` after 30 seconds
    And the consumer can retry

  Scenario: Compatibility with existing consumers
    Given an existing MCP tool calls `bus_read()` without `poll_timeout`
    Then the behavior is identical to today (poll once, return immediately)
```

**Acceptance criteria:**
- [ ] Long-poll parameter added to `bus_read()` API (server side)
- [ ] Default behavior unchanged (no poll_timeout = poll once)
- [ ] Server-side polling loop in asyncio (not blocking threads)
- [ ] Postgres load reduced by ~90% at 1000 agents
- [ ] Works with existing `cortex_bus.py` library (opt-in)

---

### Story BUS-P1-4: Per-Queue Circuit Breaker + Backpressure

**As** the bus server,  
**I want** to automatically reject sends to inboxes that are growing too fast,  
**So that** one slow consumer doesn't tank Postgres for everyone.

```gherkin
Feature: Per-Queue Circuit Breaker

  Scenario: Queue exceeds depth threshold
    Given `inbox_gisu` has 5000 pending messages
    When any agent attempts `bus_send('inbox_gisu', msg)`
    Then the server returns HTTP 429 "Too Many Requests — inbox_gisu at capacity"
    And the message is NOT stored

  Scenario: Queue recovers after consumption
    Given `inbox_gisu` was at capacity (HTTP 429 being returned)
    When gisu consumes messages and depth drops to 1000
    Then `bus_send('inbox_gisu', msg)` succeeds again

  Scenario: DLQ emergency cutoff
    Given `inbox_gisu_dlq` has 1000 messages
    When Moses sends a new message to `inbox_gisu`
    Then a WARN is logged (but send succeeds — DLQ cutoff is advisory)
    And the message is stored normally

  Scenario: Configuration per agent
    Given the operator runs `hermes cortex agent config set gisu max_inbox_depth=10000`
    Then only gisu's threshold changes
    And the default is 5000 for all other agents

  Scenario: Backpressure notification
    When a send is rejected with HTTP 429
    Then a metric is incremented: `bus_backpressure_activations_total{agent="gisu"} 1`
    And an event is logged to `bus.audit_log`
```

**Acceptance criteria:**
- [ ] Default inbox depth limit: 5000 messages
- [ ] HTTP 429 when limit exceeded
- [ ] Auto-recovery when depth drops below 80% of limit
- [ ] Per-agent configurable limit
- [ ] DLQ depth is advisory (warn but don't block)
- [ ] Metrics and audit log on every backpressure event

---

## Phase 2: Enterprise (P2 — 100-500 Agents)

### Story BUS-P2-1: Bus Audit Log

**As** a security auditor,  
**I want** every bus operation logged with agent identity and timestamp,  
**So that** I can trace who did what and when for compliance.

```gherkin
Feature: Bus Audit Log

  Scenario: Every operation logged
    Given agent `moses` sends a message to `inbox_gisu`
    Then `bus.audit_log` has an entry:
    - agent: moses
    - action: send
    - queue: inbox_gisu
    - msg_id: <uuid>
    - timestamp: <utc>

  Scenario: Read operations logged
    Given agent `gisu` reads from `inbox_gisu`
    Then `bus.audit_log` has an entry for the read

  Scenario: Archive operations logged
    Given agent `gisu` archives a message
    Then `bus.audit_log` has an entry for the archive

  Scenario: Permission changes logged
    Given the operator runs `hermes cortex agent remove titus`
    Then `bus.audit_log` has entries for:
    - token removal
    - permission removal
    - htpasswd removal

  Scenario: Query audit log by agent
    Given I run `hermes cortex audit agent gisu --since 2026-07-27`
    Then all operations by gisu since that date are returned
```

**Acceptance criteria:**
- [ ] `bus.audit_log` table in Postgres
- [ ] Every send, read, archive, requeue, permission change logged
- [ ] Entry includes: agent, action, queue, msg_id, timestamp, client_ip
- [ ] Log is append-only (no deletes or updates)
- [ ] CLI tool for querying the audit log
- [ ] Retention configurable (default: 90 days)

---

### Story BUS-P2-2: Integration Test Harness

**As** a developer modifying the bus,  
**I want** a multi-agent integration test that exercises the full message lifecycle,  
**So that** I can verify changes don't break existing agent interactions.

```gherkin
Feature: Integration Test Harness

  Scenario: Multi-agent message cycle
    Given the test harness spawns 10 virtual agents
    When Moses sends a unique message to each agent
    Then each agent reads its message
    And each agent archives its message
    And each agent sends a reply to inbox_moses
    And Moses reads all 10 replies
    And the test reports: "10/10 messages completed, 0/10 timed out, 0 errors"

  Scenario: Queues are torn down after test
    Given the test ran with 10 virtual agents
    Then all test queues (`test_inbox_agent_*`) are removed
    And no test messages remain in `bus.messages`
    And no test rows remain in `bus.archives`

  Scenario: Stressed with 200 agents
    Given the test harness spawns 200 virtual agents
    When each agent sends 100 messages (20,000 total)
    Then all messages are delivered and archived within 5 minutes
    And no messages go to DLQ
    And average latency < 100ms

  Scenario: Failure simulation
    Given a virtual agent crashes mid-read (vt expires)
    Then the message is re-queued automatically
    And the test reports the failure
    And the message is eventually archived after retry
```

**Acceptance criteria:**
- [ ] `python3 -m pytest tests/integration/bus/ -v` runs the full suite
- [ ] 10-agent happy path test completes in < 30 seconds
- [ ] 200-agent stress test completes in < 10 minutes
- [ ] Cleanup guaranteed even on test failure
- [ ] Failure scenarios: crashed consumer, nginx down, PG down, token invalid
- [ ] Runs as part of CI (or as a pre-merge check)

---

## Story Dependency Graph

```
BUS-P0-1 (Credential API)
  └── no deps

BUS-P0-2 (Inner body fix)
  └── no deps

BUS-P0-3 (Agent labels)
  └── BUS-P0-1 (needs bus.permissions)

BUS-P1-1 (Queue sharding)
  └── BUS-P0-1 (needs agent enumeration for shard placement)

BUS-P1-2 (Prometheus metrics)
  └── no deps

BUS-P1-3 (Long-poll read)
  └── no deps

BUS-P1-4 (Circuit breaker)
  └── BUS-P0-1 (needs agent config store)

BUS-P2-1 (Audit log)
  └── BUS-P1-2 (needs agent identity in operations)

BUS-P2-2 (Integration tests)
  └── BUS-P0-2 + BUS-P1-1 + BUS-P1-2 + BUS-P1-3 + BUS-P1-4
```

## Story Points Estimation

| Story | Points | Days | Parallelizable |
|-------|--------|------|----------------|
| BUS-P0-1 | 5 | 2 | ✅ Yes (standalone) |
| BUS-P0-2 | 1 | 0.25 | ✅ Yes (standalone) |
| BUS-P0-3 | 2 | 0.5 | ❌ After P0-1 |
| BUS-P1-1 | 8 | 3-4 | ❌ After P0-1 |
| BUS-P1-2 | 5 | 2 | ✅ Yes (standalone) |
| BUS-P1-3 | 5 | 2 | ✅ Yes (standalone) |
| BUS-P1-4 | 5 | 2 | ❌ After P0-1 |
| BUS-P2-1 | 3 | 1 | ✅ Yes (after P1-2) |
| BUS-P2-2 | 8 | 3-5 | ❌ After all P0 + P1 |
| **Total** | **42** | **~16-20 days** | **~10-12 days with parallelism** |
