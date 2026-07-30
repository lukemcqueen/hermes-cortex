#!/usr/bin/env python3
"""No-agent no-verify-audit: reads ~/.hermes-cortex/state/no-verify-log.json and reports."""
import json, sys
from pathlib import Path

log_path = Path.home() / ".hermes-cortex" / "state" / "no-verify-log.json"
if not log_path.exists():
    print("✅ no-verify-log.json: not found — no audit events")
    sys.exit(0)

data = json.loads(log_path.read_text())
events = data if isinstance(data, list) else data.get("events", [])
if not events:
    print("✅ no-verify-log.json: empty — no audit events")
    sys.exit(0)

print(f"⚠️  {len(events)} no-verify audit event(s):")
for e in events[-5:]:
    ts = e.get("timestamp", "?")
    branch = e.get("branch", "?")
    files = e.get("files_count", "?")
    print(f"  • {ts} | branch={branch} | {files} files")
if len(events) > 5:
    print(f"  ... and {len(events) - 5} older events")
