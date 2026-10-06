#!/usr/bin/env python3
"""
fleet-hygiene — unified fleet hygiene verification CLI.

Merged verifiers behind one umbrella with consistent conventions
(PASS/FAIL/UNVERIFIABLE, --json, exit codes 0/1/2):

  fleet-hygiene langfuse     — Langfuse reachability: traces + API keys.

Former script (removed 2026-08-27):
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
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()


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
        description="Fleet hygiene verification CLI (langfuse)"
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_lf = sub.add_parser("langfuse", help="Langfuse reachability probe")
    p_lf.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.subcommand == "langfuse":
        return cmd_langfuse(args)
    parser.error(f"unknown subcommand: {args.subcommand}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
