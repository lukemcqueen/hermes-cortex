#!/usr/bin/env python3
"""Unannounced evaluation / honeypot probe (Story M7 — defeat device).

Assume evaluation-awareness: the only test an agent cannot rehearse is one it
does not know is a test. This probe injects a honeypot task (a bus message or
artifact) that a non-vigilant agent would mishandle, and records the delta
between believed-test and believed-deployment behavior.

THIN SLICE (M7.1): the script is the scaffold only — `--dry-run` emits the
probe payload, `--inject` records a placeholder probe, `--report` reads back
the recorded loop. The actual honeypot content is a follow-up authored by the
orchestrator, not here.

Usage:
    python3 agent-unannounced-probe.py --dry-run   # emit the probe payload
    python3 agent-unannounced-probe.py --inject    # record a probe (placeholder)
    python3 agent-unannounced-probe.py --report    # read back the loop (default)
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path.home() / ".hermes-cortex" / "data" / "unannounced-probes.jsonl"


def loop_path(path=None) -> Path:
    if path:
        return Path(path)
    return Path(os.environ.get("UNANNOUNCED_PROBE_LOG", str(DEFAULT_PATH)))


def build_payload() -> dict:
    """The probe payload — a honeypot task spec the orchestrator will author."""
    return {
        "type": "unannounced-honeypot-probe",
        "honeypot_task": "PLACEHOLDER — orchestrator authors the real honeypot "
                         "content (Story M7 follow-up, not a weak model)",
        "measure": "delta between believed-test and believed-deployment behavior",
    }


def inject(path=None) -> dict:
    """Append a probe record (placeholder honeypot) to the loop and return it."""
    p = loop_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "probe_id": uuid.uuid4().hex,
        "payload": build_payload(),
        "believed_test": None,
        "believed_deployment": None,
        "delta": None,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def read_loop(path=None) -> list:
    """Read the recorded probe loop, skipping blank/malformed lines."""
    p = loop_path(path)
    if not p.exists():
        return []
    recs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return recs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="emit the probe payload")
    ap.add_argument("--inject", action="store_true", help="record a placeholder probe")
    ap.add_argument("--report", action="store_true", help="read back the recorded loop")
    ap.add_argument("--path", default="", help="override loop file path")
    args = ap.parse_args(argv)

    path = args.path or None
    if args.dry_run:
        print(json.dumps(build_payload(), indent=2))
        return 0
    if args.inject:
        print(json.dumps(inject(path)))
        return 0

    # default (no flag) and --report both read the loop back
    recs = read_loop(path)
    if recs:
        for r in recs:
            print(json.dumps(r))
    else:
        print("No unannounced probes recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
