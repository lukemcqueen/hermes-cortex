#!/usr/bin/env python3
"""
Purge stale governance lock files from crashed sessions.

Scans ~/.hermes-cortex/state/ for .governance-*.json files whose
heartbeat has exceeded their TTL and removes them. Also cleans
orphan symlinks pointing to deleted targets.

Designed as a no_agent cron (silent when clean, reports only
when locks were removed).

FIXED 2026-07-31: the main block (count = purge(), output, exit) was
inadvertently indented inside the def, so the script only defined the
function and exited 0 — the purge cron was a silent no-op. The loop
also referenced an undefined `marker` variable (NameError) in what was
meant to be a separate 24h marker cleanup. Both are corrected here.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path.home() / ".hermes-cortex" / "state"
DEFAULT_TTL = 3600  # 1 hour
MARKER_MAX_AGE = 86400  # 24 hours


def _is_lock_stale(state: dict) -> bool:
    """Check if a lock's heartbeat has exceeded its TTL."""
    ttl = state.get("ttl_seconds", DEFAULT_TTL)
    heartbeat_str = state.get("heartbeat_at", state.get("started_at", ""))
    if not heartbeat_str:
        return False
    try:
        hb_str = heartbeat_str.replace("Z", "+00:00").replace("+00:00", "+00:00")
        heartbeat = datetime.fromisoformat(hb_str)
        now = datetime.now(timezone.utc)
        elapsed = (now - heartbeat).total_seconds()
        return elapsed > ttl
    except (ValueError, TypeError):
        return False


def purge() -> int:
    """Remove stale lock files and old session markers. Returns count removed."""
    removed = 0
    if not STATE_DIR.exists():
        return 0

    # Phase 1: Remove stale real files
    for lock_file in sorted(STATE_DIR.glob(".governance-*.json")):
        try:
            if lock_file.is_symlink():
                continue  # Process real file separately
            state = json.loads(lock_file.read_text())
            if _is_lock_stale(state):
                lock_file.unlink()
                removed += 1
        except (json.JSONDecodeError, OSError, ValueError):
            try:
                lock_file.unlink(missing_ok=True)
                removed += 1
            except OSError:
                print("expected — silently handled", file=sys.stderr)
        try:
            if lock_file.is_symlink() and not lock_file.exists():
                lock_file.unlink()
                removed += 1
        except OSError:
            print("expected — silently handled", file=sys.stderr)

    # Phase 2: Remove stale session marker files (.hermes-session-*.id) older than 24h.
    # NOTE: previously inlined in the lock loop with an undefined `marker`
    # variable, which crashed the loop. Moved to its own loop here.
    for marker in sorted(STATE_DIR.glob(".hermes-session-*.id")):
        try:
            mtime = os.path.getmtime(marker)
            age = (datetime.now().timestamp() - mtime)
            if age > MARKER_MAX_AGE:  # 24 hours
                marker.unlink()
                removed += 1
        except OSError:
            print("expected — silently handled", file=sys.stderr)

    return removed


count = purge()
if count > 0:
    print(f"🧹 Purged {count} stale governance lock file(s)")
else:
    # Silent — no_agent cron with empty stdout = no delivery
    pass
sys.exit(0)
