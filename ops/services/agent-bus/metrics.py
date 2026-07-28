"""
VictoriaMetrics Bus Metrics — Metric Definitions + Push Client
==============================================================

Defines all bus metrics (counters, histograms, gauges) using the
Prometheus-compatible `prometheus_client` library.

Metrics are pushed to VictoriaMetrics via POST /api/v1/import/prometheus
using the standard Prometheus text exposition format (v0.4.0).

Usage (bus server):
    from metrics import (
        bus_send_total, bus_read_total, bus_queue_depth,
        push_metrics, metrics_push_loop
    )

    # Instrument an operation:
    bus_send_total.labels(queue="inbox_moses").inc()
    bus_queue_depth.labels(queue="inbox_moses").set(3)

    # Push to central VictoriaMetrics:
    await push_metrics()

    # Or run continuous push loop:
    import asyncio
    asyncio.create_task(metrics_push_loop(interval=60))

Standalone usage (any agent / cron job):
    # Define custom metrics with prometheus_client, then:
    python3 -c "
    from metrics import push_metrics
    # ... your custom metrics ...
    import asyncio
    asyncio.run(push_metrics(url='http://central:8428'))
    "
"""

import asyncio
import logging
import os

import httpx
from prometheus_client import Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)

# ── Counters ────────────────────────────────────────────────

bus_send_total = Counter(
    "bus_send_total",
    "Total messages sent per queue",
    ["queue"],
)

bus_read_total = Counter(
    "bus_read_total",
    "Total messages read per queue",
    ["queue"],
)

bus_archive_total = Counter(
    "bus_archive_total",
    "Total messages archived per queue",
    ["queue"],
)

bus_requeue_total = Counter(
    "bus_requeue_total",
    "Total messages requeued per queue",
    ["queue"],
)

bus_errors_total = Counter(
    "bus_errors_total",
    "Bus operation errors",
    ["queue", "operation", "error_type"],
)

# ── Histograms ──────────────────────────────────────────────

BUS_LATENCY_BUCKETS = (.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0)

bus_send_duration = Histogram(
    "bus_send_duration_seconds",
    "Send operation latency",
    ["queue"],
    buckets=BUS_LATENCY_BUCKETS,
)

bus_read_duration = Histogram(
    "bus_read_duration_seconds",
    "Read operation latency",
    ["queue"],
    buckets=BUS_LATENCY_BUCKETS,
)

bus_archive_duration = Histogram(
    "bus_archive_duration_seconds",
    "Archive operation latency",
    ["queue"],
    buckets=(.001, .005, .01, .025, .05, .1, .25, .5, 1.0),
)

# ── Gauges ──────────────────────────────────────────────────

bus_queue_depth = Gauge(
    "bus_queue_depth",
    "Current queue depth per queue",
    ["queue"],
)

bus_dlq_depth = Gauge(
    "bus_dlq_depth",
    "Current dead-letter queue depth per queue",
    ["queue"],
)

bus_connection_count = Gauge(
    "bus_connection_count",
    "Active bus connections",
)


# ── Refresh Helpers ─────────────────────────────────────────

async def refresh_queue_depth_gauges(list_queues_fn=None):
    """
    Query queue depths and update gauge metrics.

    Args:
        list_queues_fn: Async callable returning [{"name": str, "depth": int}, ...]
                        If None, gauges are not auto-refreshed (use .set() manually).
    """
    if list_queues_fn is None:
        return
    queues = await list_queues_fn()
    for q in queues:
        name = q["name"]
        depth = q["depth"]
        is_dlq = name.endswith("_dlq")
        if is_dlq:
            bus_dlq_depth.labels(queue=name).set(depth)
        else:
            bus_queue_depth.labels(queue=name).set(depth)


# ── Push Client ─────────────────────────────────────────────

DEFAULT_VICTORIA_URL = os.getenv(
    "VICTORIA_METRICS_URL",
    "http://localhost:8428/api/v1/import/prometheus",
)
DEFAULT_PUSH_INTERVAL = int(os.getenv("VICTORIA_PUSH_INTERVAL", "60"))
MAX_RETRIES = 3


async def push_metrics(
    url: str | None = None,
    refresh_gauges_fn=None,
) -> bool:
    """
    Push current Prometheus-format metrics to VictoriaMetrics.

    Args:
        url: VictoriaMetrics push endpoint.
             Defaults to VICTORIA_METRICS_URL env var, then localhost:8428.
        refresh_gauges_fn: Optional async callable to refresh gauge values
                           before serializing.

    Returns:
        True on success, False after all retries exhausted.
    """
    url = url or DEFAULT_VICTORIA_URL

    # Refresh gauges before serializing
    if refresh_gauges_fn:
        await refresh_gauges_fn()

    # Serialize all metrics to Prometheus text format
    payload = generate_latest()

    async with httpx.AsyncClient() as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    url,
                    content=payload,
                    headers={"Content-Type": "text/plain; version=0.4.0"},
                    timeout=10.0,
                )
                if resp.status_code == 204:
                    logger.debug("push_metrics_ok", url=url)
                    return True

                logger.warning(
                    "push_metrics_failed",
                    url=url,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "push_metrics_retry",
                    url=url,
                    attempt=attempt,
                    error=str(exc),
                )

            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    logger.error("push_metrics_exhausted", url=url)
    return False


async def metrics_push_loop(
    interval: int | None = None,
    url: str | None = None,
    refresh_gauges_fn=None,
):
    """
    Continuous loop: push metrics every `interval` seconds.

    Runs forever. Intended for asyncio.create_task() in the
    bus server's lifespan.

    Args:
        interval: Seconds between pushes (default: 60).
        url: VictoriaMetrics push endpoint.
        refresh_gauges_fn: Async callable to refresh gauge values.
    """
    interval = interval or DEFAULT_PUSH_INTERVAL
    url = url or DEFAULT_VICTORIA_URL

    logger.info(
        "metrics_push_loop_start",
        url=url,
        interval=interval,
    )

    while True:
        try:
            await push_metrics(url=url, refresh_gauges_fn=refresh_gauges_fn)
        except Exception as exc:
            logger.error("metrics_push_loop_error", error=str(exc))
        await asyncio.sleep(interval)


# ── Synchronous convenience (for cron / scripts) ──────────

def push_metrics_sync(url: str | None = None):
    """
    Synchronous wrapper for push_metrics().

    Use this in cron jobs or standalone scripts that don't
    have an asyncio event loop.

    Usage:
        python3 -c "
        from metrics import push_metrics_sync
        # ... instrument metrics ...
        push_metrics_sync('http://central:8428/api/v1/import/prometheus')
        "
    """
    payload = generate_latest()

    import urllib.request

    req = urllib.request.Request(
        url or DEFAULT_VICTORIA_URL,
        data=payload,
        headers={"Content-Type": "text/plain; version=0.4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                return True
    except Exception as exc:
        logger.error("push_metrics_sync_error", error=str(exc))
    return False
