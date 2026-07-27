#!/usr/bin/env python3
"""
agent-session-mine-cron.py — Overnight session mining for Hermes Cortex agents.

Runs session-mine to extract lessons from recent sessions and dump them
into ~/brain/lessons/ where the agent-learning-collector picks them up.

Runs as a no_agent cron (overnight, every 24h).

Bootstrap: on first run, mines ALL past sessions (up to 365 days).
Subsequent: incremental — only the last 1 day.

Usage:
    python3 agent-session-mine-cron.py              # mine and dump
    python3 agent-session-mine-cron.py --dry-run    # preview only
    python3 agent-session-mine-cron.py --force      # full bootstrap regardless
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "agent-session-mine-state.json"
TIMEOUT = 120  # 2 minutes — bootstrap finished in 82s on this server


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"bootstrap_done": False, "last_run": 0}


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    state = load_state()

    # Bootstrap: mine all past sessions on first run, incremental after
    bootstrap_done = state.get("bootstrap_done", False)
    days = 365 if (not bootstrap_done or force) else 1

    # Locate session-mine CLI
    session_mine = None
    for candidate in [
        os.environ.get("SESSION_MINE_PATH"),
        str(HOME / ".hermes" / "bin" / "session-mine"),
    ]:
        if candidate and Path(candidate).is_file():
            session_mine = candidate
            break

    if not session_mine:
        # Try PATH
        import shutil
        session_mine = shutil.which("session-mine")

    if not session_mine:
        print("WARN: session-mine not found — skipping run.", flush=True)
        return  # Silent — session-mine not installed on this machine

    cmd = [session_mine, "mine", "--days", str(days), "--auto"]
    if dry_run:
        cmd.append("--dry-run")
        print(f"[DRY RUN] Would run: {' '.join(cmd)}", flush=True)
        return

    print(f"Running: {' '.join(cmd)} (up to {TIMEOUT}s)", flush=True)

    try:
        t0 = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.time() - t0

        if result.returncode != 0:
            print(f"WARN: session-mine exited {result.returncode} after {elapsed:.0f}s", flush=True)
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", flush=True)
        else:
            print(f"OK: session-mine completed in {elapsed:.0f}s", flush=True)
            if result.stdout:
                print(f"  output: {result.stdout[:500]}", flush=True)

        # Mark bootstrap done after a successful full run
        if not bootstrap_done and result.returncode == 0:
            state["bootstrap_done"] = True

    except subprocess.TimeoutExpired:
        print(f"ERR: session-mine timed out after {TIMEOUT}s", flush=True)
    except (FileNotFoundError, OSError) as e:
        print(f"ERR: session-mine failed: {e}", flush=True)

    state["last_run"] = time.time()
    save_state(state)


if __name__ == "__main__":
    main()
