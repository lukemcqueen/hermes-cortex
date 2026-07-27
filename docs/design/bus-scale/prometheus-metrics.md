# Prometheus Bus Metrics — Design Document

> **BUS-P1-2:** Observable bus: latency, depth, error rates.
> Priority: 🟡 P1 (needed for operations at 25+ agents). Effort: 2-3 days.

## Problem

The bus has no metrics. Queue depth is checked via `GET /api/pgmq/queues`,
but there's no latency tracking, no error rate monitoring, no per-queue historical
depth. At scale, operators need to detect "bus is slow" vs "bus is dying" without
guessing.

## Solution

Add a `/metrics` endpoint to the bus server exposing Prometheus-format metrics
for all bus operations.

### Metrics Endpoint

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

### Implementation

Using `prometheus_client` library (lightweight, no external dependencies
beyond the pip package):

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

### Metrics Endpoint Handler

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

### Per-Queue Depth Refresh

The `_refresh_queue_depth_gauges()` function queries queue depth and DLQ depth
for all known queues and updates the gauges. This is done on-demand (not cached)
since `/metrics` is typically scraped every 15-30 seconds by Prometheus.

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

### Cost

- `prometheus_client` adds ~100KB to the deployment
- Metric instrumentation adds < 1µs per operation (counter inc, histogram obs)
- No persistent storage needed (Prometheus scrapes and stores)

### What NOT to Measure

- Don't expose `bus.*` internal token/permissions table metrics (security)
- Don't expose per-agent metrics by agent name in public endpoints
  (agent names are already visible in queue names, which are required for
  debugging — but don't expose PII via additional labels)

### Files Changed

| File | Action |
|------|--------|
| `ops/services/agent-bus/server.py` | Add `/metrics` endpoint |
| `ops/services/agent-bus/metrics.py` | Create — metric definitions |
| `requirements.txt` | Add `prometheus-client` |
