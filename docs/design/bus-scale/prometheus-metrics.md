# VictoriaMetrics Bus Metrics — Design Document

> **BUS-P1-2:** Observable bus: latency, depth, error rates.
> Priority: 🟡 P1 (needed for operations at 25+ agents). Effort: 2-3 days.
>
> **Replaces Prometheus with VictoriaMetrics single-node + push model.**

## Problem

The bus has no metrics. Queue depth is checked via `GET /api/pgmq/queues`,
but there's no latency tracking, no error rate monitoring, no per-queue historical
depth. At scale, operators need to detect "bus is slow" vs "bus is dying" without
guessing.

## Solution

Add a `/metrics` endpoint to the bus server exposing Prometheus-format metrics
for all bus operations. Metrics are **pushed** to VictoriaMetrics via its
`/api/v1/import/prometheus` endpoint, which accepts the exact Prometheus
text/plain exposition format (same output as `prometheus_client.generate_latest()`).

### Architecture

```
  Agent Server                          Central Hermes Server
┌─────────────────────┐          ┌──────────────────────────────────┐
│ Bus Server          │          │  VictoriaMetrics (single-node)  │
│  ┌───────────────┐  │          │  ┌────────────────────────────┐ │
│  │ prometheus_   │──┼─POST─────┼─▶│  /api/v1/import/prometheus │ │
│  │ client        │  │ /metrics │  │  Port 8428                 │ │
│  │ (counters,    │  │ every 30s│  └────────────┬───────────────┘ │
│  │  histograms,  │  │          │               │                  │
│  │  gauges)      │  │          │  ┌────────────▼───────────────┐ │
│  └───────────────┘  │          │  │  Grafana :3030             │ │
│                     │          │  │  PromQL queries via        │ │
│ Agent N             │          │  │  Prometheus datasource     │ │
│  ┌───────────────┐  │          │  └────────────────────────────┘ │
│  │ push-metrics  │──┼─POST─────┼─▶  same endpoint               │
│  │ script        │  │ /metrics │                                 │
│  └───────────────┘  │          └──────────────────────────────────┘
└─────────────────────┘
```

**Push model benefits for 1000+ agents:**
- No inbound firewall rules needed on agent servers
- Agents behind NAT/VPN can report metrics
- VictoriaMetrics handles burst traffic via internal buffering
- Single central endpoint to secure, not N agent endpoints
- Prometheus-compatible alerting (vmalert) can be added later

### Metrics Endpoint (local debug / bus server)

The bus server exposes a `/metrics` endpoint for local inspection.
When Push Mode is enabled, this endpoint is also POSTed to VictoriaMetrics
on a configurable interval.

```
GET /metrics
Content-Type: text/plain; version=0.4.0

# HELP bus_send_total Total messages sent per queue
# TYPE bus_send_total counter
bus_send_total{queue="inbox_moses"} 1423
bus_send_total{queue="inbox_gisu"} 89

# HELP bus_read_total Total messages read per queue
# TYPE bus_read_total counter
bus_read_total{queue="inbox_moses"} 1401

# HELP bus_send_duration_seconds Send operation latency
# TYPE bus_send_duration_seconds histogram
bus_send_duration_seconds_bucket{le="0.001"} 1200
bus_send_duration_seconds_bucket{le="0.01"} 1410
bus_send_duration_seconds_bucket{le="0.1"} 1423
bus_send_duration_seconds_sum 4.2
bus_send_duration_seconds_count 1423

# HELP bus_queue_depth Current queue depth
# TYPE bus_queue_depth gauge
bus_queue_depth{queue="inbox_moses"} 3
bus_queue_depth{queue="inbox_gisu"} 0
bus_queue_depth{queue="inbox_gisu_dlq"} 0
```

### Push Mode

Each agent (bus server, cron jobs, watcher scripts) pushes metrics to the
central VictoriaMetrics endpoint:

```
POST http://<victoria-host>:8428/api/v1/import/prometheus
Content-Type: text/plain; version=0.4.0

<prometheus_client.generate_latest() output>
```

Agents push on a configurable interval (default: 60s). The push is:
- **Fire-and-forget** — if VictoriaMetrics is briefly down, the agent retries
  with exponential backoff (3 attempts, 1s/2s/4s delay)
- **Self-contained** — no state on the agent, no persistence needed
- **Idempotent** — VictoriaMetrics deduplicates identical series within a
  single POST (overwrites by timestamp + labels)

### Implementation

#### Metric Definitions

Using `prometheus_client` library (identical to the original Prometheus design):

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Counters
bus_send_total = Counter(
    'bus_send_total', 'Messages sent',
    ['queue']
)
bus_read_total = Counter(
    'bus_read_total', 'Messages read',
    ['queue']
)
bus_archive_total = Counter(
    'bus_archive_total', 'Messages archived',
    ['queue']
)
bus_requeue_total = Counter(
    'bus_requeue_total', 'Messages requeued',
    ['queue']
)
bus_errors_total = Counter(
    'bus_errors_total', 'Bus operation errors',
    ['queue', 'operation', 'error_type']
)

# Histograms — only for agent-facing operations
bus_send_duration = Histogram(
    'bus_send_duration_seconds', 'Send latency',
    ['queue'],
    buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0)
)
bus_read_duration = Histogram(
    'bus_read_duration_seconds', 'Read latency',
    ['queue'],
    buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0)
)
bus_archive_duration = Histogram(
    'bus_archive_duration_seconds', 'Archive latency',
    ['queue'],
    buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1.0)
)

# Gauges
bus_queue_depth = Gauge(
    'bus_queue_depth', 'Current queue depth',
    ['queue']
)
bus_dlq_depth = Gauge(
    'bus_dlq_depth', 'Current DLQ depth',
    ['queue']
)
bus_connection_count = Gauge(
    'bus_connection_count', 'Active connections'
)
```

#### Metrics Endpoint Handler (local / debug)

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def metrics():
    # Refresh queue depths before serving
    await _refresh_queue_depth_gauges()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

#### Push to VictoriaMetrics

```python
import httpx
from prometheus_client import generate_latest

VICTORIA_METRICS_URL = "http://localhost:8428/api/v1/import/prometheus"

async def push_metrics():
    """Push current metrics to VictoriaMetrics."""
    await _refresh_queue_depth_gauges()
    payload = generate_latest()

    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            try:
                resp = await client.post(
                    VICTORIA_METRICS_URL,
                    content=payload,
                    headers={"Content-Type": "text/plain; version=0.4.0"},
                    timeout=10.0,
                )
                if resp.status_code == 204:
                    return  # success
                logger.warning("push_metrics_failed", status=resp.status_code)
            except httpx.RequestError as exc:
                logger.warning("push_metrics_retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(2 ** attempt)

# Called on a timer in the bus server lifespan
async def metrics_push_loop(interval: int = 60):
    while True:
        await push_metrics()
        await asyncio.sleep(interval)
```

#### Per-Queue Depth Refresh

```python
async def _refresh_queue_depth_gauges():
    queues = await _list_queues()
    for q in queues:
        name = q["name"]
        depth = q["depth"]
        is_dlq = name.endswith("_dlq")
        
        if is_dlq:
            bus_dlq_depth.labels(queue=name).set(depth)
        else:
            bus_queue_depth.labels(queue=name).set(depth)
```

### Agent Push Script (for non-bus agents)

For agents that aren't the bus server but still need to report metrics
(e.g., cron job run times, health check status), use the reference script:

```bash
# ~/.hermes-cortex/scripts/push-metrics.sh
# Collects system metrics and pushes to central VictoriaMetrics.
# Called by cron or systemd timer or the agent itself.
#
# Usage: bash push-metrics.sh
#   Pushes system-level metrics (cpu, memory, disk, uptime)

VICTORIA_URL="${VICTORIA_METRICS_URL:-http://your-server:8428/api/v1/import/prometheus}"

# Generate Prometheus-format metrics
METRICS=$(cat <<EOF
# HELP node_cpu_usage_percent CPU usage percentage
# TYPE node_cpu_usage_percent gauge
node_cpu_usage_percent $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d. -f1)
# HELP node_memory_used_percent Memory usage percentage
# TYPE node_memory_used_percent gauge
node_memory_used_percent $(free | grep Mem | awk '{print $3/$2 * 100.0}')
# HELP node_disk_used_percent Disk usage percentage
# TYPE node_disk_used_percent gauge
node_disk_used_percent $(df / | tail -1 | awk '{print $5}' | tr -d '%')
EOF
)

curl -s -X POST "$VICTORIA_URL" \
  -H "Content-Type: text/plain; version=0.4.0" \
  --data-binary "$METRICS" \
  -w "%{http_code}" -o /dev/null
```

### Cost

- `prometheus_client` adds ~100KB to the deployment
- Metric instrumentation adds < 1µs per operation (counter inc, histogram obs)
- **No Prometheus server to run** — VictoriaMetrics handles storage
- VictoriaMetrics storage: ~1 byte per sample for integer metrics,
  ~3 bytes per sample for histograms (10x better than Prometheus)

### What NOT to Measure

- Don't expose `bus.*` internal token/permissions table metrics (security)
- Don't expose per-agent metrics by agent name in public endpoints
  (agent names are already visible in queue names, which are required for
  debugging — but don't expose PII via additional labels)

### Files Changed

| File | Action |
|------|--------|
| `core/cortex_bus/server.py` | Add `/metrics` endpoint |
| `core/cortex_bus/metrics.py` | Create — metric definitions + push loop |
| `core/cortex_bus/push-metrics.sh` | Create — standalone push script for agents |
| `requirements.txt` | Add `prometheus-client` |
| `ops/install/deploy/docker-compose.victoria-metrics.yml` | Create — VictoriaMetrics + Grafana stack |
| `ops/install/deploy/config/grafana-datasources.yml` | Create — auto-provisioned Grafana datasource |
