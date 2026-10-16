#!/usr/bin/env python3
"""Advisory diagnostic: how long ONE reviewer call takes, control vs a real blob.

WHY THIS IS COMMITTED: the close machinery's bounds are argued from a measured number —
"one blob review runs 180-250s against the 240s wall-clock ceiling, so the heaviest blob of
a range was never judged". A number a reviewer cannot re-run is an unverified claim, so the
measurement ships as this script plus the transcript it produced
(docs/evidence/review-bounded/reviewer-latency.txt).

WHAT IT IS NOT: not a review, not verification, and it authorises nothing. The governed
close pass (`end_change`) is the review of record; this prints TIMINGS ONLY and deliberately
does not print the model's reply — a helper that emitted verdicts would be a second, unaudited
review path, which is exactly what governance refuses. It resolves its credential through the
component's own config helper and never names or prints a key.

Run:  python3 docs/evidence/review-bounded/measure-reviewer-latency.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SERVER = Path(os.environ.get(
    "CORTEX_LOOP_GOV_SERVER",
    Path.home() / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py"))


def load():
    spec = importlib.util.spec_from_file_location("loopgov_latency_probe", SERVER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {SERVER}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)      # import-time write is its own log file, nothing else
    return mod


def timed(label: str, fn) -> None:
    started = time.monotonic()
    try:
        text = fn()
        note = f"{len(text)} chars back"
        try:
            json.loads(text[text.index("{"):text.rindex("}") + 1])
            note += ", parses as a findings object (contents NOT printed)"
        except (ValueError, json.JSONDecodeError):
            note += ", not a findings object (contents NOT printed)"
    except Exception as exc:  # noqa: BLE001 — a failure here is a measurement too
        text, note = "", f"{type(exc).__name__}: {str(exc)[:160]}"
    print(f"{label:<28} {time.monotonic() - started:8.1f}s   {note}")


def main() -> int:
    mod = load()
    ceiling = mod._reviewer_timeout_ceiling()
    print(f"module      : {SERVER}  (the DEPLOYED copy the close loads)")
    print(f"model       : {mod._reviewer_model()}")
    print(f"effort      : {mod._reviewer_reasoning_effort()}")
    print(f"ceiling     : {ceiling}s for this caller "
          f"({'cli' if ceiling == mod.REVIEWER_TIMEOUT_CEILING_CLI else 'mcp'})")
    print()

    timed("control (trivial prompt)", lambda: mod._call_reviewer(
        "Reply with exactly: OK", author="latency-probe", cx={}))

    base = mod._push_base(REPO)
    blobs = mod._push_range_blobs(REPO) or {}
    clean = mod._blobs_with_clean_verdict(blobs)
    uncovered = sorted(p for p, sha in blobs.items() if sha not in clean)
    print(f"range       : {base[:12]}..HEAD, {len(blobs)} blob(s), "
          f"{len(uncovered)} without a verdict")
    if not uncovered:
        print("no uncovered blob — nothing to time (the close is what would review it)")
        return 0

    path = uncovered[0]
    ctx = {"sid": "latency-probe", "author": "latency-probe", "branch": "main",
           "head_sha": mod._git_capture(REPO, "rev-parse", "--short", "HEAD").strip(),
           "cycle_id": 0, "task_id": "latency-probe",
           "description": "advisory latency probe — see the script docstring"}
    prompt = (f"{mod._review_template_text(REPO)}\n"
              f"{mod._blob_material(REPO, base, path, ctx)}\n")
    print(f"blob        : {path}  (prompt {len(prompt)} chars)")
    timed("one real blob review", lambda: mod._call_reviewer(
        prompt, author="latency-probe", cx=mod._complexity(REPO, None, None)))
    print()
    print("Advisory: timings only. No verdict is recorded here and no receipt depends on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
