#!/usr/bin/env python3
"""
Purge stale governance lock files from crashed sessions.

Scans ~/.hermes-cortex/state/ for .governance-*.json files whose
heartbeat has exceeded their TTL and removes them. Also cleans
orphan symlinks pointing to deleted targets.

Designed as a no_agent cron (silent when clean, reports only
when locks were removed).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path.home() / ".hermes-cortex" / "state"
DEFAULT_TTL = 3600  # 1 hour


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
    """Remove stale lock files. Returns count removed."""
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
        try:
            # Remove markers older than 24 hours
            mtime = os.path.getmtime(marker)
            age = (datetime.now().timestamp() - mtime)
            if age > 86400:  # 24 hours
                marker.unlink()
                removed += 1
        except OSError:
            print("expected — silently handled", file=sys.stderr)
    count = purge()
    if count > 0:
        print(f"🧹 Purged {count} stale governance lock file(s)")
    else:
        # Silent — no_agent cron with empty stdout = no delivery
        pass
    sys.exit(0)
