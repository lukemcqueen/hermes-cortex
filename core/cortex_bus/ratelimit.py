"""cortex_bus.ratelimit — per-agent send rate limiting (anti-spam).

In-memory sliding window keyed by authenticated agent name. A single
bus-server process can serve thousands of agents; each gets an independent
quota so one noisy or malicious agent cannot flood a queue.

Defaults: 600 sends/hour per agent (10/min sustained) — generous for
legitimate protocol traffic (crons, health pings, EXECs), decisive against
spam floods. Tune via constructor args or env overrides.
"""

from __future__ import annotations

import os
import threading
import time


class RateLimiter:
    """Sliding-window per-agent rate limiter (thread-safe)."""

    def __init__(
        self,
        max_per_window: int | None = None,
        window_seconds: int | None = None,
    ):
        self.max_per_window = max_per_window or int(
            os.environ.get("CORTEX_BUS_RATE_LIMIT_PER_HOUR", "600")
        )
        self.window_seconds = window_seconds or int(
            os.environ.get("CORTEX_BUS_RATE_WINDOW_SECONDS", "3600")
        )
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, agent: str) -> bool:
        """Record a send for ``agent``; True if within quota, False if over."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._events.setdefault(agent, [])
            # Prune expired events (sliding window).
            while q and q[0] < cutoff:
                q.pop(0)
            if len(q) >= self.max_per_window:
                return False
            q.append(now)
            return True

    def remaining(self, agent: str) -> int:
        """How many sends remain in the current window for ``agent``."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._events.get(agent, [])
            while q and q[0] < cutoff:
                q.pop(0)
            return max(0, self.max_per_window - len(q))
