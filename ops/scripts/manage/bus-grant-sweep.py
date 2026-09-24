#!/usr/bin/env python3
"""Bus grant expiry sweep (Story M5 — Jubilee, Lev 25).

Lists grants whose `expires_at` is in the past — power expires by default,
and an expired grant is either re-granted (a fresh expiry) or removed.

Grants with `expires_at IS NULL` are indefinite and are NOT listed here; the
doctor's M5.2 check flags indefinite grants that lack a named justifier.

Production path queries `bus.permissions` via the orchestrator's Postgres
container (docker exec mycortex-postgres). For offline/testing, pass a JSON
array of grants with --grants-file.

Usage:
    python3 ops/scripts/manage/bus-grant-sweep.py [--grants-file grants.json] [--json]
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_ts(value):
    if value is None or value == "":
        return None
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def sweep_expired(grants, now=None) -> list:
    """Return the grants whose expires_at is strictly in the past.

    `now` is a timezone-aware datetime (defaults to now, UTC). Grants with no
    parseable expires_at (NULL/empty) are indefinite and omitted.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    expired = []
    for g in grants:
        if not isinstance(g, dict):
            continue
        exp = parse_ts(g.get("expires_at"))
        if exp is not None and exp < now:
            expired.append(g)
    return expired


def _db_grants():
    """Query bus.permissions (agent_name, expires_at) from the Postgres bus."""
    sql = (
        "SELECT agent_name, expires_at FROM bus.permissions "
        "WHERE expires_at IS NOT NULL"
    )
    cmd = [
        "docker", "exec", "-i", "mycortex-postgres",
        "psql", "-U", "mycortex", "-d", "mycortex",
        "-t", "-A", "-F", "|", "-c", sql,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    grants = []
    for line in r.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            grants.append({"agent_name": parts[0].strip(), "expires_at": parts[1].strip()})
    return grants


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grants-file", default="", help="JSON array of grants (offline/test)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    if args.grants_file:
        try:
            grants = json.loads(Path(args.grants_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot load grants file: {e}", file=sys.stderr)
            return 2
    else:
        grants = _db_grants()
        if grants is None:
            print("ERROR: cannot query bus.permissions (orchestrator host only?)", file=sys.stderr)
            return 2

    expired = sweep_expired(grants)
    if args.json:
        print(json.dumps(expired, indent=2))
    else:
        for g in expired:
            print(f"EXPIRED: {g.get('agent_name')} expires_at={g.get('expires_at')}")
        if not expired:
            print("No expired grants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
