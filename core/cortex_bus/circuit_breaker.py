"""
Circuit breaker for Hermes Cortex Agent Bus.

Auto-degrades from PGMQ to file backend when Postgres is unavailable.
Auto-restores when Postgres comes back.

State is persisted to ~/.hermes-cortex/bus-circuit-breaker.json
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

STATE_FILE = Path.home() / ".hermes-cortex" / "bus-circuit-breaker.json"


class CircuitBreakerState:
    """Persistent state for the bus circuit breaker."""
    
    def __init__(self):
        self.state: str = "pgmq"          # "pgmq" or "file"
        self.failures: int = 0
        self.last_failure: str = ""
        self.last_success: str = ""
        self.last_check: str = ""
        self.threshold: int = 3            # failures before degrading
        self.check_interval: int = 30      # seconds between health checks

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "failures": self.failures,
            "last_failure": self.last_failure,
            "last_success": self.last_success,
            "last_check": self.last_check,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CircuitBreakerState":
        s = cls()
        s.state = d.get("state", "pgmq")
        s.failures = d.get("failures", 0)
        s.last_failure = d.get("last_failure", "")
        s.last_success = d.get("last_success", "")
        s.last_check = d.get("last_check", "")
        return s


class CircuitBreaker:
    """Circuit breaker that manages PGMQ → file fallback."""

    def __init__(self):
        self._state = self._load()

    def _load(self) -> CircuitBreakerState:
        try:
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text())
                return CircuitBreakerState.from_dict(data)
        except (json.JSONDecodeError, OSError):
            pass
        return CircuitBreakerState()

    def _save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._state.to_dict(), indent=2))

    def get_backend(self) -> str:
        """Return the current active backend: 'pgmq' or 'file'."""
        return self._state.state

    def record_failure(self, error: str = ""):
        """Record a PGMQ failure."""
        self._state.failures += 1
        self._state.last_failure = datetime.now(timezone.utc).isoformat()
        self._state.last_check = datetime.now(timezone.utc).isoformat()

        if self._state.failures >= self._state.threshold:
            old_state = self._state.state
            self._state.state = "file"
            if old_state != "file":
                print(f"[circuit-breaker] DEGRADED: PGMQ failed {self._state.failures}x, "
                      f"falling back to file backend. Last error: {error[:200]}")
                self._state.failures = 0  # Reset counter for next cycle

        self._save()

    def record_success(self):
        """Record a PGMQ success (resets failure count)."""
        self._state.failures = 0
        self._state.last_success = datetime.now(timezone.utc).isoformat()
        self._state.last_check = datetime.now(timezone.utc).isoformat()

        if self._state.state == "file":
            self._state.state = "pgmq"
            print("[circuit-breaker] RESTORED: Postgres is back, switching to PGMQ backend.")

        self._save()

    def check_and_restore(self):
        """Check if Postgres is available and restore PGMQ if so.
        
        Called periodically (every health check) when in 'file' mode.
        """
        if self._state.state != "file":
            return

        try:
            from cortex_bus.queue import get_queue
            bus = get_queue()
            # Quick health check — list queues
            _ = bus.list_queues()
            self.record_success()
        except Exception as e:
            self.record_failure(str(e))

    def is_available(self) -> bool:
        """Quick check: is the bus available right now?"""
        if self._state.state != "pgmq":
            return False
        try:
            from cortex_bus.queue import get_queue
            bus = get_queue()
            bus.list_queues()
            self.record_success()
            return True
        except Exception as e:
            self.record_failure(str(e))
            return False


# Global singleton
_breaker: CircuitBreaker | None = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance."""
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker()
    return _breaker
