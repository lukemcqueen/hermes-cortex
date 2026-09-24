#!/usr/bin/env python3
"""Record an independent adversarial review into the loop-governance DB.

Story M6.2 — the review sink. The reviewer (a separate context) writes its
verdict here; the worker cannot write to this table (it is written only by the
reviewer script, which runs orchestrator-side).

Usage:
    record-review.py --db <path> --cycle-id N --reviewer-id <session>
        --reviewer-model <model> --verdict CLEAN|FINDINGS
        --findings-json '<json array>' --summary '<text>'
"""
import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--cycle-id", type=int, required=True)
    p.add_argument("--reviewer-id", required=True)
    p.add_argument("--reviewer-model", required=True)
    p.add_argument("--verdict", required=True, choices=["CLEAN", "FINDINGS"])
    p.add_argument("--findings-json", required=True)
    p.add_argument("--summary", required=True)
    args = p.parse_args()

    try:
        findings = json.loads(args.findings_json)
    except json.JSONDecodeError as e:
        print(f"Error: --findings-json is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(findings, list):
        print("Error: --findings-json must be a JSON array", file=sys.stderr)
        return 2
    if args.verdict == "FINDINGS" and not findings:
        print(
            "Error: verdict FINDINGS requires at least one finding "
            "(use CLEAN with an empty array)",
            file=sys.stderr,
        )
        return 2

    conn = sqlite3.connect(args.db)
    try:
        conn.execute(
            "INSERT INTO adversarial_reviews (review_id, cycle_id, reviewer_id,"
            " reviewer_model, verdict, findings_json, summary, ts)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                args.cycle_id,
                args.reviewer_id,
                args.reviewer_model,
                args.verdict,
                json.dumps(findings),
                args.summary,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f"Error: cannot record review for cycle {args.cycle_id}: {e}",
              file=sys.stderr)
        return 3
    finally:
        conn.close()
    print(f"OK: review recorded for cycle {args.cycle_id} ({args.verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
