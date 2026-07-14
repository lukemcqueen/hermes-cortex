"""
Hermes Cortex Agent Bus — Postgres Native Message Queue.

A lightweight message queue built on Postgres using SKIP LOCKED.
No external extensions required. Each agent has its own queue + DLQ.

Usage:
    from hermes_bus.queue import get_queue
    
    bus = get_queue()
    msg_id = bus.send("inbox_moses", {"from": "test", "body": "hello"})
    msg = bus.read("inbox_moses", vt=60)
    bus.archive("inbox_moses", msg["msg_id"])
"""

from .queue import get_queue, NotAvailableError, BusClient

__all__ = ["get_queue", "NotAvailableError", "BusClient"]
