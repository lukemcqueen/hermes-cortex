#!/usr/bin/env python3
"""state_tracker.py — State fingerprinting for no_agent cron scripts.

Prevents duplicate error alerts by tracking the last-reported state.
Usage:
    from state_tracker import StateTracker
    st = StateTracker("service-recovery")
    fp = "ollama=DOWN|nginx=UP"  # fingerprint of current state
    action = st.evaluate(fp)
    # action: "silent" (same as before), "alert" (new error), "resolve" (error cleared)

State files stored in ~/.hermes/state/<cron-name>.state
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path.home() / ".hermes" / "state"


class StateTracker:
    """Track state transitions for a named cron job.

    Stores the last-reported fingerprint and status.
    On each check, compares current fingerprint to last:
      - same fingerprint, last was OK         → "silent" (no change)
      - same fingerprint, last was ERROR      → "silent" (duplicate error)
      - different fingerprint, last was ERROR → "resolve" (error state changed)
      - different fingerprint, new has issues → "alert" (new or changed error)
    """

    def __init__(self, name: str):
        self.name = name
        self.state_file = STATE_DIR / f"{name}.state"

    def _fingerprint(self, data: str) -> str:
        """Stable hash of the state data."""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def evaluate(self, current_state: str, has_issues: bool = True) -> str:
        """Compare current state to last reported state.

        Args:
            current_state: A string fingerprint of the current situation
                          (e.g. "ollama=DOWN|disk=85%")
            has_issues: Whether the current state represents a problem.
                        True = this is an error/alert state.
                        False = this is a healthy/all-clear state.

        Returns:
            "silent"  — no change or duplicate error — produce no output
            "alert"   — new/changed error — produce alert output
            "resolve" — error cleared — produce resolution output
        """
        fprint = self._fingerprint(current_state)

        prev = self._read()
        self._write(fprint, has_issues)

        if prev is None:
            # First run ever: alert if issues, silent if healthy
            return "alert" if has_issues else "silent"

        prev_fprint, prev_had_issues = prev

        if not has_issues and not prev_had_issues:
            # Was healthy, still healthy
            return "silent"

        if has_issues and prev_had_issues and fprint == prev_fprint:
            # Same error as last time — duplicate, suppress
            return "silent"

        if not has_issues and prev_had_issues:
            # Was error, now healthy — resolution!
            return "resolve"

        if has_issues and not prev_had_issues:
            # Was healthy, now error — alert!
            return "alert"

        if has_issues and prev_had_issues and fprint != prev_fprint:
            # Error changed (different fingerprint) — re-alert
            return "alert"

        return "silent"

    def _read(self):
        """Read previous state. Returns (fingerprint, had_issues) or None."""
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text())
            return data.get("fingerprint"), data.get("had_issues", False)
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, fingerprint: str, had_issues: bool):
        """Write current state."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "fingerprint": fingerprint,
            "had_issues": had_issues,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }))