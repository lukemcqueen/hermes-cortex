#!/usr/bin/env python3
"""Auto-snapshot echokorean session state.
Updates .hermes-cortex/sessions/current.md when git state changes.
Silent exit (0) when nothing changed — no output = no notification."""

import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta

REPO = "/Users/luke/Developer/PERSONAL/echokorean"
SESSION_FILE = os.path.join(REPO, ".hermes-cortex", "sessions", "current.md")
KST = timezone(timedelta(hours=9))

os.chdir(REPO)

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)

def kst_now():
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S%z")

def get_git_state():
    head = run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0:
        return None
    head_sha = head.stdout.strip()

    msg = run(["git", "log", "-1", "--format=%s"])
    msg_text = msg.stdout.strip()

    short = run(["git", "rev-parse", "--short", "HEAD"])
    short_sha = short.stdout.strip()

    status = run(["git", "status", "--short"])
    dirty = status.stdout.strip() != ""
    dirty_count = len([l for l in status.stdout.split("\n") if l.strip()]) if dirty else 0

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch_name = branch.stdout.strip()

    return {
        "head": head_sha,
        "head_short": short_sha,
        "message": msg_text,
        "branch": branch_name,
        "dirty": dirty,
        "dirty_count": dirty_count,
    }

def read_recorded_head():
    """Read the HEAD hash from the existing session file, if present."""
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE) as f:
        for line in f:
            line = line.strip()
            # Look for "HEAD: <sha>" or grab from commit hash lines
            if line.startswith("|") and "dd2aed5" in line:
                # Try to extract the commit hash from the commit history table
                pass
    return None

def write_snapshot(state):
    ts = kst_now()
    dirty_info = f"Yes ({state['dirty_count']} files)" if state['dirty'] else "No"
    content = f"""# Session State — {datetime.now(KST).strftime("%Y-%m-%d")}

## Current State
- **Branch:** `{state['branch']}`
- **HEAD:** `{state['head_short']}` — {state['message']}
- **Dirty:** {dirty_info}
- **Snapshot:** {ts}

## Last Commit
```
{state['head_short']}  {state['message']}
```

## Remaining Items
_Update from agent conversation: what was accomplished in this session._

## Test Status
_Run tests to get current status._

---
_This snapshot was auto-generated at {ts}._
"""
    with open(SESSION_FILE, "w") as f:
        f.write(content)
    return True

current = get_git_state()
if not current:
    sys.exit(0)  # can't determine state — silent

# Read old state
old_head = None
if os.path.exists(SESSION_FILE):
    with open(SESSION_FILE) as f:
        for line in f:
            if "HEAD:" in line and "`" in line:
                import re
                m = re.search(r'`([a-f0-9]+)`', line)
                if m:
                    old_head = m.group(1)
                    break

if old_head == current["head_short"]:
    sys.exit(0)  # nothing changed — silent

write_snapshot(current)