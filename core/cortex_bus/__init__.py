"""
Hermes Cortex Agent Bus — Postgres Native Message Queue.

A lightweight message queue built on Postgres using SKIP LOCKED.
No external extensions required. Each agent has its own queue + DLQ.

This package is Hermes-independent (component-hermes-separation, scope 1): it
imports only its own ``.queue`` module and resolves with ZERO Hermes runtime
import. The bus server and queue client are standalone — they talk to the
mycortex Postgres via SKIP LOCKED, not through the Hermes process.

Usage:
    from cortex_bus import get_queue       # Hermes-independent
    from cortex_bus.queue import get_queue # or import the module directly

    bus = get_queue()
    msg_id = bus.send("inbox_moses", {"from": "test", "body": "hello"})
    msg = bus.read("inbox_moses", vt=60)
    bus.archive("inbox_moses", msg["msg_id"])
"""

from .queue import get_queue, NotAvailableError, BusClient

__all__ = ["get_queue", "NotAvailableError", "BusClient"]
