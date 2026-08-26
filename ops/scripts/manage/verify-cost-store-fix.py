#!/usr/bin/env python3
"""
verify-cost-store-fix — fleet propagation check for the O1-S3 cost fix.

Checks a host's deployed cron-cost tracking state:
  1. Deployed ~/.hermes/hermes-agent/cron/cost_store.py exists AND contains the
     O1-S3 fix (2026-08-26, commit 8bbee471): record_run recomputes cost from
     token columns at the local RATE_VERSION schedule ("provider estimate is
     intentionally ignored"), and reprice_runs self-heals with a consistency
     guard (abs diff < 1e-4) instead of the old version-only check.
  2. Spot-check: the latest LLM run row in ~/.hermes/cron/cron-costs.db is
     re-computed at local rates (0.007 hit / 0.22 miss / 0.66 out per 1M,
     peak 01-04 & 06-10 UTC x2) and compared against the stored cost.

Usage:
    verify-cost-store-fix.py [--json]
Exit codes: 0 = PASS, 1 = FAIL (any check), 2 = missing DB/rows (unverifiable)
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
DEPLOYED = HOME / ".hermes" / "hermes-agent" / "cron" / "cost_store.py"
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"

RATE_VERSION = "2026-08-16"
PRICE_HIT, PRICE_MISS, PRICE_OUT, PEAK_MULT = 0.007, 0.22, 0.66, 2.0

# O1-S3 fix markers in cost_store.py source (commit 8bbee471, 2026-08-26)
MARKERS = [
    ("record_run recompute", "provider number is intentionally ignored"),
    ("reprice consistency guard", "< 1e-4"),
]


def is_peak(dt: datetime) -> bool:
    h = dt.hour
    return (1 <= h < 4) or (6 <= h < 10)


def compute_cost(in_tok, out_tok, cr_tok, cw_tok, run_dt: datetime) -> float:
    hit = cr_tok or 0
    miss = (in_tok or 0) + (cw_tok or 0)
    mult = PEAK_MULT if is_peak(run_dt) else 1.0
    return (hit * PRICE_HIT + miss * PRICE_MISS + (out_tok or 0) * PRICE_OUT) * mult / 1e6


def check_deployed() -> tuple:
    """Return (ok, details) for the deployed cost_store.py."""
    if not DEPLOYED.exists():
        return False, f"MISSING {DEPLOYED}"
    try:
        src = DEPLOYED.read_text(errors="replace")
    except OSError as e:
        return False, f"UNREADABLE {DEPLOYED}: {e}"
    missing = [label for label, marker in MARKERS if marker not in src]
    if missing:
        return False, f"STALE (missing O1-S3 markers: {', '.join(missing)})"
    return True, "O1-S3 markers present (record_run recompute + consistency guard)"


def check_row() -> tuple:
    """Spot-check latest LLM row: stored cost vs local-rate recompute."""
    if not COST_DB.exists():
        return None, f"no cost DB at {COST_DB}"
    con = sqlite3.connect(f"file:{COST_DB}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT id, job_id, run_time, input_tokens, output_tokens,
                      cache_read_tokens, cache_write_tokens, estimated_cost_usd,
                      rate_version
               FROM cron_runs
               WHERE no_agent = 0 AND status = 'ok'
                 AND (input_tokens > 0 OR output_tokens > 0)
               ORDER BY run_time DESC LIMIT 1"""
        )
        row = cur.fetchone()
        if not row:
            return None, "no LLM run rows in cron-costs.db"
        (rid, job_id, run_time, in_tok, out_tok, cr_tok, cw_tok, stored, rate_ver) = row
        run_dt = datetime.fromisoformat(run_time.replace("Z", "+00:00"))
        recomputed = compute_cost(in_tok, out_tok, cr_tok, cw_tok, run_dt)
        diff = abs(float(stored or 0.0) - recomputed)
        ok = diff < 1e-4
        detail = (
            f"row#{rid} {job_id[:12]} stored=${float(stored or 0):.6f} "
            f"recomputed=${recomputed:.6f} diff={diff:.2e} rv={rate_ver} "
            f"({'MATCH' if ok else 'MISMATCH'})"
        )
        return ok, detail
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dep_ok, dep_detail = check_deployed()
    row_ok, row_detail = check_row()

    checks = [
        ("deployed_cost_store", dep_ok, dep_detail),
        ("row_spot_check", row_ok, row_detail),
    ]
    unverifiable = any(v is None for _, v, _ in checks)
    fail = any(v is False for _, v, _ in checks)
    overall = "PASS" if not fail and not unverifiable else ("UNVERIFIABLE" if unverifiable and not fail else "FAIL")

    if args.json:
        print(json.dumps({"overall": overall, "checks": [
            {"name": n, "ok": v, "detail": d} for n, v, d in checks
        ]}, indent=2))
    else:
        for name, ok, detail in checks:
            tag = "INFO" if ok is None else ("OK" if ok else "FAIL")
            print(f"{tag:<4} {name}: {detail}")
        print(f"OVERALL: {overall}")
    return 1 if fail else (2 if unverifiable else 0)


if __name__ == "__main__":
    sys.exit(main())
