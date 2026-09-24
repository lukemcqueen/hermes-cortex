#!/usr/bin/env python3
"""Refusal log + separate metrics (Story M3 — Balaam's donkey).

Tracks refusal precision/recall SEPARATELY from task satisfaction, so a
single satisfaction metric can never breed the refusal out of the agent.

`record` appends a JSONL record:
    {ts, session_id, context, challenged, override_outcome}
  - challenged=false → the agent did not push back (baseline); outcome is
    forced to "none".
  - challenged=true  → pushback happened; override_outcome is
    "upheld" | "overridden".

The log lives at ~/.hermes-cortex/data/refusals.jsonl (override with the
REFUSALS_LOG env var or --path).

Usage:
    python3 ops/scripts/manage/refusal-log.py record --challenged --outcome overridden
    python3 ops/scripts/manage/refusal-log.py record [--context ...] [--session-id ...] [--path ...]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path.home() / ".hermes-cortex" / "data" / "refusals.jsonl"


def log_path() -> Path:
    return Path(os.environ.get("REFUSALS_LOG", str(DEFAULT_PATH)))


def record(challenged, outcome, context="", session_id="", path=None) -> dict:
    """Append one refusal record and return it."""
    p = Path(path) if path else log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "",
        "context": context or "",
        "challenged": bool(challenged),
        "override_outcome": outcome if bool(challenged) else "none",
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="append a refusal record")
    rec.add_argument("--challenged", action="store_true", help="agent pushed back")
    rec.add_argument("--outcome", choices=("upheld", "overridden", "none"),
                     default="none", help="override outcome when challenged")
    rec.add_argument("--context", default="", help="free-text context")
    rec.add_argument("--session-id", default="", help="session identifier")
    rec.add_argument("--path", default="", help="override log file path")

    args = ap.parse_args(argv)

    if args.command == "record":
        if args.challenged and args.outcome not in ("upheld", "overridden"):
            print("ERROR: --challenged requires --outcome upheld|overridden", file=sys.stderr)
            return 2
        r = record(args.challenged, args.outcome, args.context, args.session_id, args.path or None)
        print(json.dumps(r))
        return 0

    ap.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
