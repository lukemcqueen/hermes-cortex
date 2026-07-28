#!/usr/bin/env python3
"""no-verify-audit — silent watchdog for --no-verify events.

Watchdog pattern: empty stdout = silent (nothing to report).
Prints only when new --no-verify events appear since last check.

State tracked in: ~/.hermes-cortex/state/no-verify-audit-state.json
"""

import json
import os
import sys

LOG_FILE = os.path.expanduser("~/.hermes-cortex/state/no-verify-log.json")
STATE_FILE = os.path.expanduser("~/.hermes-cortex/state/no-verify-audit-state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_timestamp": None, "last_index": -1}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_events():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []


def main():
    state = load_state()
    events = load_events()

    if not events:
        sys.exit(0)  # No log file or empty — silent

    # Find new events since last check
    new_events = []
    for i, evt in enumerate(events):
        if i > state["last_index"]:
            new_events.append(evt)

    if not new_events:
        sys.exit(0)  # Nothing new — silent

    # Print new events (this gets delivered)
    print(f"⚠️  {len(new_events)} new --no-verify event(s) detected:")
    for evt in new_events:
        ts = evt.get("timestamp", "?")
        commit = evt.get("commit", "?")[:10]
        msg = evt.get("message", "?")
        print(f"  • {ts}  {commit}  {msg}")

    # Update state
    state["last_index"] = len(events) - 1
    if new_events:
        state["last_timestamp"] = new_events[-1].get("timestamp", state["last_timestamp"])
    save_state(state)


if __name__ == "__main__":
    main()
