#!/usr/bin/env python3
"""
Agent Bus end-to-end health check — no_agent cron pattern.

Sends a test message, reads it back, archives it. Reports round-trip latency.
Exits non-zero if any step fails (triggers system-alert-watchdog).

Usage as no_agent cron:
    hermes cron create name=bus-health-check schedule="*/5 * * * *" \\
      script=bus-health-check.py no_agent=true deliver=origin
"""

import os
import sys
import time
from datetime import datetime, timezone

# Add repo core dir to path (agent_bus package lives in <repo>/core).
# Works from repo layout (ops/scripts/orch-bus/) and deployed layout
# (~/.hermes-cortex/scripts/) since the repo is at ~/hermes-cortex.
_REPO_CORE = os.path.expanduser("~/hermes-cortex/core")
if os.path.isdir(_REPO_CORE):
    sys.path.insert(0, _REPO_CORE)
else:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "core"))

from agent_bus.queue import get_queue, NotAvailableError
from agent_bus.circuit_breaker import get_circuit_breaker


def main():
    # Check circuit breaker first
    cb = get_circuit_breaker()

    if cb.get_backend() != "pgmq":
        # In degraded mode — try to restore first (Postgres may have recovered)
        cb.check_and_restore()
        if cb.get_backend() != "pgmq":
            print(f"[bus-health] DEGRADED: backend={cb.get_backend()}, "
                  f"last_failure={cb._state.last_failure}")
            sys.exit(0)
    
    try:
        bus = get_queue()
    except NotAvailableError:
        print("[bus-health] SKIP: not on server machine")
        sys.exit(0)
    
    start = time.time()
    
    try:
        # Step 1: Send a test message
        test_id = f"health-{int(start)}"
        msg_id = bus.send("inbox_health_check", {
            "_test": True,
            "id": test_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if not msg_id:
            raise RuntimeError("send returned no msg_id")
        
        # Step 2: Read it back
        vt = 10
        msg = bus.read("inbox_health_check", vt)
        if not msg or not msg.get("msg_id"):
            raise RuntimeError("read returned no message")
        
        # Step 3: Archive it
        archived = bus.archive("inbox_health_check", msg["msg_id"], "health-check")
        if not archived:
            raise RuntimeError("archive failed")
        
        elapsed_ms = int((time.time() - start) * 1000)
        
        # Record success in circuit breaker
        cb.record_success()
        
        # Get queue depth for reporting
        depth = bus.depth("inbox_health_check")
        
        # Summary
        print(f"[bus-health] OK | rtt={elapsed_ms}ms | queue_depth={depth}")
        
        # Alert if slow
        if elapsed_ms > 1000:
            print(f"[bus-health] WARN: round-trip time > 1s ({elapsed_ms}ms)")
        
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        print(f"[bus-health] FAIL | error={str(e)[:200]} | elapsed={elapsed_ms}ms")
        cb.record_failure(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
