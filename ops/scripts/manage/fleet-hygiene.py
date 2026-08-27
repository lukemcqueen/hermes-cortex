#!/usr/bin/env python3
"""
fleet-hygiene — unified fleet hygiene verification CLI.

Merges the former standalone verifiers into one umbrella with consistent
conventions (PASS/FAIL/UNVERIFIABLE, --json, exit codes 0/1/2):

  fleet-hygiene cost-store   — O1-S3 cron-cost fix propagation probe:
                               deployed cost_store.py markers + latest-row
                               spot-check at local rates.
  fleet-hygiene langfuse     — Langfuse reachability: traces + API keys.

Former scripts (removed 2026-08-27):
  verify-cost-store-fix.py   → fleet-hygiene cost-store
  verify-langfuse.py         → fleet-hygiene langfuse

Usage:
    fleet-hygiene <subcommand> [--json]

Exit codes (all subcommands):
    0 — PASS (all checks green)
    1 — FAIL (any check failed)
    2 — UNVERIFIABLE (dependency missing: DB/rows/env/endpoint)
"""

import argparse
import base64
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()


# ────────────────────────────────────────────────────────────────────
# cost-store — O1-S3 fleet propagation probe (from verify-cost-store-fix.py)
# ────────────────────────────────────────────────────────────────────
DEPLOYED_COST_STORE = HOME / ".hermes" / "hermes-agent" / "cron" / "cost_store.py"
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"

RATE_VERSION = "2026-08-16"
PRICE_HIT, PRICE_MISS, PRICE_OUT, PEAK_MULT = 0.007, 0.22, 0.66, 2.0

# O1-S3 fix markers in cost_store.py source (commit 8bbee471, 2026-08-26)
COST_STORE_MARKERS = [
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


def check_deployed_cost_store() -> tuple:
    """Return (ok, detail) for the deployed cost_store.py. ok None = no file."""
    if not DEPLOYED_COST_STORE.exists():
        return None, f"no deployed cost_store.py at {DEPLOYED_COST_STORE}"
    try:
        src = DEPLOYED_COST_STORE.read_text(errors="replace")
    except OSError as e:
        return False, f"UNREADABLE {DEPLOYED_COST_STORE}: {e}"
    missing = [label for label, marker in COST_STORE_MARKERS if marker not in src]
    if missing:
        return False, f"STALE (missing O1-S3 markers: {', '.join(missing)})"
    return True, "O1-S3 markers present (record_run recompute + consistency guard)"


def check_cost_row() -> tuple:
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


def cmd_cost_store(args) -> int:
    dep_ok, dep_detail = check_deployed_cost_store()
    row_ok, row_detail = check_cost_row()
    checks = [
        ("deployed_cost_store", dep_ok, dep_detail),
        ("row_spot_check", row_ok, row_detail),
    ]
    return _report(args, "cost-store", checks)


# ────────────────────────────────────────────────────────────────────
# langfuse — reachability probe (from verify-langfuse.py)
# ────────────────────────────────────────────────────────────────────
LANGFUSE_BASE = "http://localhost:3000"


def _langfuse_auth() -> str | None:
    """Return Basic auth header value, or None if env keys are missing."""
    env_path = HOME / ".hermes" / ".env"
    if not env_path.exists():
        return None
    pub = secret = ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("HERMES_LANGFUSE_PUBLIC_KEY="):
                pub = line.strip().split("=", 1)[1]
            elif line.startswith("HERMES_LANGFUSE_SECRET_KEY="):
                secret = line.strip().split("=", 1)[1]
    except OSError:
        return None
    if not pub or not secret:
        return None
    return base64.b64encode(f"{pub}:{secret}".encode()).decode()


def _langfuse_api(path: str, auth: str) -> dict:
    req = urllib.request.Request(f"{LANGFUSE_BASE}{path}")
    req.add_header("Authorization", f"Basic {auth}")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:  # noqa: BLE001 — probe surfaces any failure
        body = e.read().decode() if hasattr(e, "read") else str(e)
        return {"error": str(e), "body": body[:300]}


def check_langfuse() -> list:
    """Return a list of (name, ok, detail) checks. ok None = unverifiable.

    Langfuse v3 public API: /api/public/traces REQUIRES fromTimestamp
    (verified 3.225.1, 2026-08-27); /api/public/keys does not exist in
    this version (404). A 200 on traces with valid auth proves the keys
    are good, so the second check reports auth status instead of a dead
    endpoint.
    """
    auth = _langfuse_auth()
    if auth is None:
        return [
            ("langfuse_auth", None, "HERMES_LANGFUSE_PUBLIC_KEY/SECRET_KEY missing in ~/.hermes/.env"),
            ("traces", None, "skipped (no auth)"),
        ]
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    traces = _langfuse_api(f"/api/public/traces?limit=10&fromTimestamp={since}", auth)
    if "data" in traces:
        n = len(traces["data"])
        traces_detail = f"{n} traces (7d); newest: " + (
            f"{traces['data'][0]['name']} ({traces['data'][0].get('timestamp', '?')[:19]})"
            if n else "none"
        )
        traces_ok = True
        # 200 on the authed endpoint == keys valid
        auth_ok, auth_detail = True, "Basic auth accepted (traces 200)"
    elif traces.get("error"):
        traces_detail = f"API unreachable: {traces['body'][:200] or traces['error'][:200]}"
        traces_ok = False
        auth_ok, auth_detail = False, "traces endpoint rejected the request"
    else:
        traces_detail = "unexpected response shape"
        traces_ok = False
        auth_ok, auth_detail = False, "traces endpoint returned an unexpected shape"

    return [
        ("traces", traces_ok, traces_detail),
        ("langfuse_auth", auth_ok, auth_detail),
    ]


def cmd_langfuse(args) -> int:
    return _report(args, "langfuse", check_langfuse())


# ────────────────────────────────────────────────────────────────────
# shared reporting
# ────────────────────────────────────────────────────────────────────
def _report(args, subcommand: str, checks: list) -> int:
    """checks: list of (name, ok, detail); ok True/False/None (unverifiable)."""
    unverifiable = any(v is None for _, v, _ in checks)
    fail = any(v is False for _, v, _ in checks)
    overall = "PASS" if not fail and not unverifiable else (
        "UNVERIFIABLE" if unverifiable and not fail else "FAIL"
    )

    if getattr(args, "json", False):
        print(json.dumps({
            "subcommand": subcommand,
            "overall": overall,
            "checks": [{"name": n, "ok": v, "detail": d} for n, v, d in checks],
        }, indent=2))
    else:
        for name, ok, detail in checks:
            tag = "INFO" if ok is None else ("OK" if ok else "FAIL")
            print(f"{tag:<4} {name}: {detail}")
        print(f"OVERALL: {overall}")
    return 1 if fail else (2 if unverifiable else 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fleet hygiene verification CLI (cost-store, langfuse)"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_cost = sub.add_parser("cost-store", help="O1-S3 cost fix propagation probe")
    p_cost.add_argument("--json", action="store_true")

    p_lf = sub.add_parser("langfuse", help="Langfuse reachability probe")
    p_lf.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.subcommand == "cost-store":
        return cmd_cost_store(args)
    if args.subcommand == "langfuse":
        return cmd_langfuse(args)
    parser.error(f"unknown subcommand: {args.subcommand}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
