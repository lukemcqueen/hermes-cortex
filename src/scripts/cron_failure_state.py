#!/usr/bin/env python3
"""Failure state helpers for no_agent crons — Python equivalent of cron-failure-state.sh.

Usage:
    from cron_failure_state import FailureState

    fs = FailureState("my-script")
    error_hash = fs.compute_hash("HTTP 403 to ...")

    if not fs.should_report(error_hash, cooldown_minutes=30):
        sys.exit(0)  # silent — already reported recently

    # ... do work, fail ...
    fs.record_failure(error_hash)
    sys.exit(1)

    # On success:
    fs.record_success()

State file: ~/.hermes-cortex/state/<script-name>.json
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

DEFAULT_STATE_DIR = Path.home() / ".hermes-cortex" / "state"
DEFAULT_COOLDOWN = 30  # minutes


class FailureState:
    """Per-script failure state with cooldown-based dedup."""

    def __init__(self, script_name: str, state_dir: Optional[Union[Path, str]] = None):
        self.script_name = script_name
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self.state_file = self.state_dir / f"{script_name}.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────

    @staticmethod
    def compute_hash(error_msg: str) -> str:
        """Deterministic hash from an error message (SHA-256 first 16 chars)."""
        return hashlib.sha256(error_msg.encode()).hexdigest()[:16]

    def should_report(self, error_hash: str, cooldown_minutes: int = DEFAULT_COOLDOWN) -> bool:
        """Return True if this failure should be reported, False if still in cooldown."""
        state = self._read()

        # No prior failure → always report
        if not state.get("last_error_hash") or not state.get("last_report_at"):
            return True

        # Different error → report
        if state.get("last_error_hash") != error_hash:
            return True

        # Same error — check cooldown
        try:
            last_report = datetime.fromisoformat(state["last_report_at"])
            now = datetime.now(timezone.utc)
            elapsed = (now - last_report).total_seconds() / 60
            return elapsed >= cooldown_minutes
        except (ValueError, TypeError):
            return True  # Can't parse time → report to be safe

    def record_failure(self, error_hash: str, cooldown_minutes: int = DEFAULT_COOLDOWN) -> None:
        """Record a failure and update the state file.

        Call this AFTER should_report() returned True — just before
        exiting non-zero.
        """
        state = self._read()
        state["script"] = self.script_name
        state["version"] = 1
        state["last_error_hash"] = error_hash
        state["last_error_at"] = self._now_iso()
        state["error_count"] = state.get("error_count", 0) + 1
        state["last_report_at"] = self._now_iso()
        state["report_cooldown_minutes"] = cooldown_minutes
        self._write(state)

    def record_success(self) -> None:
        """Record a successful run, clearing error state."""
        state = self._read()
        state["script"] = self.script_name
        state["version"] = 1
        state["last_error_hash"] = ""
        state["last_error_at"] = ""
        state["error_count"] = 0
        state["last_success_at"] = self._now_iso()
        self._write(state)

    def get_state(self) -> dict:
        """Return the full state dict (for debugging/inspection)."""
        return self._read()

    # ── Internal ────────────────────────────────────────────────────

    def _read(self) -> dict:
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _write(self, state: dict) -> None:
        self.state_file.write_text(
            json.dumps(state, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
