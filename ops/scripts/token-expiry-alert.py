#!/usr/bin/env python3
"""token-expiry-alert.py — warn BEFORE bus tokens expire (party finding).

Security role (party 2026-08-24): bus tokens auto-expire after 90 days;
nothing alerts before expiry, so bridges hard-fail silently at T+90d.
This checker queries the bus tokens table and warns (exit 1, human-readable
output) for any agent whose token expires within the warning window
(default 7 days) — wire as a daily cron.

Usage:
    python3 token-expiry-alert.py [--warn-days 7] [--alert-days 3]

Exit codes:
    0 = all tokens healthy (or no tokens)
    1 = at least one token expiring soon (or expired) — alert
    2 = could not check (bus unreachable) — alert (fail-open check)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _bus_conn():
    """Connect to the bus Postgres (same seam as cortex-agent-manager)."""
    import importlib.util
    here = Path(__file__).resolve().parent
    mgr = here / "cortex-agent-manager.py"
    spec = importlib.util.spec_from_file_location("cam", mgr)
    cam = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cam)
    return cam._pg_execute


def check_expiry(pg_execute, warn_days: int, now=None) -> list[dict]:
    """Return agents whose tokens expire within warn_days (or already did)."""
    now = now or datetime.now(timezone.utc)
    horizon = (now + timedelta(days=warn_days)).isoformat()
    rows = pg_execute(
        "SELECT agent_name, expires_at::text, is_active "
        "FROM bus.tokens WHERE is_active = true "
        "AND expires_at IS NOT NULL AND expires_at <= %s "
        "ORDER BY expires_at",
        (horizon,),
    )
    out = []
    for r in rows or []:
        name, exp, active = r[0], r[1], r[2]
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        except ValueError:
            exp_dt = None
        days_left = (exp_dt - now).days if exp_dt else None
        out.append({"agent": name, "expires": exp, "days_left": days_left,
                    "active": active})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-days", type=int, default=7)
    args = ap.parse_args()

    try:
        _pg = _bus_conn()
        expiring = check_expiry(_pg, args.warn_days)
    except Exception as e:  # noqa: BLE001 — fail-open check
        print(f"⚠️  token-expiry-alert: could not query bus tokens ({e}) — "
              f"alerting (check failed open)", file=sys.stderr)
        return 2

    if not expiring:
        print("✅ All bus tokens healthy (none expiring within "
              f"{args.warn_days} days).")
        return 0

    print(f"⚠️  {len(expiring)} bus token(s) expiring within "
          f"{args.warn_days} days:")
    for e in expiring:
        state = "EXPIRED" if (e["days_left"] is not None and e["days_left"] < 0) else "expiring"
        print(f"  - {e['agent']}: expires {e['expires']} "
              f"({e['days_left']} days left) [{state}]")
    print("  → Rotate now: cortex-agent-manager.py rotate <agent>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
