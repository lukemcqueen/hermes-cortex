#!/usr/bin/env python3
"""
learning-collect.py — F-001 collector write path (no_agent, zero LLM).

Any of the 8 capture routes calls this to record a learning in the fleet
ledger. It POSTs to the bus server's /api/learnings endpoint via the shared
lib.cortex_bus.learning_capture() — the server inserts as DB owner through
learnings.capture(); collectors never touch Postgres directly (party L-1,
L-5: server-side write, existing bus auth, INSERT-only).

Watchdog semantics (cron-safe):
  - exit 0 + empty stdout on success (including dedup) → silent
  - exit 1 + stderr message on failure → the cron/agent sees the error
  - --dry-run prints the payload and exits 0 without sending

Usage:
    learning-collect.py --route remediation --content "fix pattern: ..."
    learning-collect.py --route governance_cycles --type insight \
        --impact 2 --source-ref "cycle 2642" --content "..."
    learning-collect.py --route brain_lessons --content-file ~/brain/lessons/x.md
    learning-collect.py --list-routes

Design: docs/design/learning-ledger.md (party-reviewed 2026-08-08).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Shared bus lib (repo + deployed layout) ──────────────────
_LIB_CANDIDATES = [
    Path(__file__).resolve().parent.parent,          # repo: ops/scripts
    Path.home() / ".hermes-cortex" / "scripts",      # deployed: scripts
    Path.home() / "hermes-cortex" / "ops" / "scripts",
]
for _lib in _LIB_CANDIDATES:
    if _lib.is_dir() and str(_lib) not in sys.path:
        sys.path.insert(0, str(_lib))
        break

try:
    from lib.cortex_bus import learning_capture  # type: ignore
    _HAS_LIB = True
except Exception:
    learning_capture = None  # type: ignore
    _HAS_LIB = False

ROUTES = [
    "brain_pending",        # 1: ~/brain/learnings/pending/*.md
    "brain_lessons",        # 2: ~/brain/lessons/
    "session_corrections",  # 3: session transcripts
    "governance_cycles",    # 4: loop-governance feedback
    "llm_judge",            # 5: trace scoring
    "remediation",          # 6: sensor/fixer novel success (F-002)
    "user_feedback",        # 7: in-session feedback (F-003)
    "cron_outputs",         # 8: watchdog findings (F-004)
]
TYPES = ["lesson", "fix", "correction", "insight",
         "feedback", "watchdog", "skill", "other"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Record a learning in the fleet ledger (F-001).")
    ap.add_argument("--route", choices=ROUTES,
                    help="capture route (see --list-routes)")
    ap.add_argument("--content", help="learning content (mutually exclusive with --content-file)")
    ap.add_argument("--content-file", type=Path,
                    help="read content from file (e.g. ~/brain/learnings/pending/x.md)")
    ap.add_argument("--type", choices=TYPES, default="lesson")
    ap.add_argument("--impact", type=int, default=0,
                    help="impact score in [-3, 3] (0=unknown)")
    ap.add_argument("--source-ref", default=None,
                    help="provenance: file/cycle/msg the learning came from")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload and exit 0 without sending")
    ap.add_argument("--list-routes", action="store_true",
                    help="print the 8 canonical capture routes and exit")
    args = ap.parse_args()

    if args.list_routes:
        print("\n".join(f"{i+1}. {r}" for i, r in enumerate(ROUTES)))
        return 0

    if not args.route:
        print("ERROR: --route is required (use --list-routes)", file=sys.stderr)
        return 1

    if (args.content and args.content_file) or (not args.content and not args.content_file):
        print("ERROR: provide exactly one of --content or --content-file", file=sys.stderr)
        return 1

    content = args.content
    if args.content_file:
        try:
            content = args.content_file.read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"ERROR: cannot read {args.content_file}: {e}", file=sys.stderr)
            return 1
    if not content:
        print("ERROR: content is empty", file=sys.stderr)
        return 1
    if len(content) > 4000:
        content = content[:4000]
        print("WARNING: content truncated to 4000 chars", file=sys.stderr)

    if not _HAS_LIB or learning_capture is None:
        print("ERROR: lib.cortex_bus unavailable (is cortex-bus.conf configured?)",
              file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps({
            "route": args.route, "type": args.type,
            "impact_score": args.impact, "source_ref": args.source_ref,
            "content": content,
        }, ensure_ascii=False))
        return 0

    result = learning_capture(
        route=args.route,
        content=content,
        ltype=args.type,
        impact_score=args.impact,
        source_ref=args.source_ref,
    )
    if result is None:
        print("ERROR: learning_capture returned None (bus unreachable or rejected)",
              file=sys.stderr)
        return 1

    # Success (incl. dedup) → silent, exit 0 (watchdog pattern)
    return 0


if __name__ == "__main__":
    sys.exit(main())
