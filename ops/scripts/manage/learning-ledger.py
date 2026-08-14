#!/usr/bin/env python3
"""
learning-ledger.py — orchestrator-only lifecycle client for the fleet
learning ledger (F-006).

The lifecycle (orch-skill-lifecycle cron on Moses/Esther) is the ONLY UPDATE
path for learnings (party L-1). This CLI gives it a safe, tested surface:

    learning-ledger.py list [--status pending] [--route remediation] [--limit 25]
    learning-ledger.py set-status <uuid> <status> [--impact N]
    learning-ledger.py stats

- list     — read ledger rows (SELECT, granted only to orchestrator profile
             roles mycortex_reader_esther/moses; RLS fail-closed elsewhere).
             Default: pending learnings (the lifecycle intake queue).
- set-status — call learnings.set_status(id, status [, impact]) — the single
             gated transition function. Impact (-3..3) optionally revises
             impact_score during evaluation (v002).
- stats    — status + route counts for the run report.

Connects as mycortex_reader_<profile> (NEVER superuser), same psql plumbing
as task-db.py: docker exec on Linux, direct psql on macOS, queries via STDIN
(no shell embedding — B-1), ON_ERROR_STOP so errors exit non-zero.

Design: docs/design/learning-ledger.md (party L-1..L-6, F-006 wiring).
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

MYCORTEX_CONFIG = os.path.expanduser("~/.hermes-cortex/mycortex.conf")
DEFAULT_DB = "mycortex"
CONTAINER = "mycortex-postgres"
PG_OPTS = ["-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "||"]

STATUSES = ("pending", "evaluated", "applied", "verified", "retired")
ROUTES = (
    "brain_pending", "brain_lessons", "session_corrections",
    "governance_cycles", "llm_judge", "remediation",
    "user_feedback", "cron_outputs",
)

# ── Profile resolution (same order as task-db.py / install script) ──

def _env_or_file_agent() -> str:
    """AGENT_NAME env → agent.env → .env. Never hostname (Luke directive
    2026-08-14): a machine name is not a tenant identity."""
    val = os.environ.get("AGENT_NAME", "").strip()
    if val and val != "unknown":
        return val
    for _p in (Path.home() / ".hermes-cortex" / "agent.env",
               Path.home() / "hermes-cortex" / ".env"):
        try:
            if _p.is_file():
                for _l in _p.read_text().splitlines():
                    _l = _l.strip()
                    if _l.startswith("AGENT_NAME="):
                        _v = _l.split("=", 1)[1].strip().strip("\"'")
                        if _v and _v != "unknown":
                            return _v
        except OSError:
            continue
    return ""


def resolve_profile() -> str:
    """HERMES_PROFILE → AGENT_NAME (env → agent.env → .env). FAIL loudly on
    none — never hostname (Luke directive 2026-08-14). Never scans profiles/*/."""
    return (os.environ.get("HERMES_PROFILE")
            or _env_or_file_agent()
            or sys.exit("❌ AGENT_NAME not configured — set AGENT_NAME= in "
                        "~/.hermes-cortex/agent.env / ~/hermes-cortex/.env "
                        "or export AGENT_NAME"))


PROFILE = resolve_profile()
# LEARNING_DB_ROLE env override: hermetic tests connect as a scratch role.
CRUD_ROLE = os.environ.get("LEARNING_DB_ROLE", f"mycortex_reader_{PROFILE}")
# LEARNING_DB env override: hermetic tests target a scratch database.
DB_NAME = os.environ.get("LEARNING_DB", DEFAULT_DB)


# ── psql plumbing (stdin-only, no shell embedding — B-1) ─────

@functools.lru_cache(maxsize=4)
def _get_db_query(role: str) -> list[str]:
    """Platform-appropriate psql invocation (query via STDIN)."""
    if platform.system() == "Darwin":
        if os.path.exists(MYCORTEX_CONFIG):
            with open(MYCORTEX_CONFIG) as f:
                cfg = json.load(f)
            url = cfg.get("database_url",
                          f"postgresql://{role}:@127.0.0.1:15432/{DB_NAME}")
        else:
            url = f"postgresql://{role}:@127.0.0.1:15432/{DB_NAME}"
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return [
            shutil.which("psql") or "/opt/homebrew/bin/psql",
            "-h", parsed.hostname or "127.0.0.1",
            "-p", str(parsed.port or 15432),
            "-U", parsed.username or role,
            "-d", DB_NAME,
            *PG_OPTS,
        ]
    # Linux — direct docker exec (docker group)
    try:
        subprocess.run(["docker", "exec", CONTAINER, "true"],
                       capture_output=True, timeout=5, check=True)
        return ["docker", "exec", "-i", CONTAINER, "psql",
                "-U", role, "-d", DB_NAME, *PG_OPTS]
    except Exception:
        # sg fallback — NO user data in the command string (stdin carries SQL).
        return ["sg", "docker", "-c",
                f"docker exec -i {CONTAINER} psql -U {role} -d {DB_NAME} "
                "-v ON_ERROR_STOP=1 -t -A -F '||'"]


def _sql_literal(value: str) -> str:
    """Quote-double a value into a SQL string literal (B-1)."""
    return "'" + value.replace("'", "''") + "'"


def build_query(sql: str, params: list | None = None) -> str:
    """Interpolate ? params into a SQL template (single-quote doubling)."""
    if not params:
        return sql
    out = sql
    for p in params:
        idx = out.find("?")
        if idx < 0:
            raise ValueError(f"too many params for query: {sql[:80]}...")
        if p is None:
            repl = "NULL"
        elif isinstance(p, bool):
            repl = "TRUE" if p else "FALSE"
        elif isinstance(p, (int, float)):
            repl = str(p)
        else:
            repl = _sql_literal(str(p))
        out = out[:idx] + repl + out[idx + 1:]
    if "?" in out:
        raise ValueError(f"missing params for query: {sql[:80]}...")
    return out


def psql(query: str, params: list | None = None, role: str | None = None,
         timeout: int = 15) -> str:
    """Run a SQL query via psql stdin; return trimmed stdout. Exits 1 on error."""
    full_query = build_query(query, params)
    cmd = _get_db_query(role or CRUD_ROLE)
    try:
        result = subprocess.run(cmd, input=full_query, capture_output=True,
                                text=True, timeout=timeout)
    except FileNotFoundError as e:
        print(f"ERROR: {e.filename} not found — is psql/docker installed?",
              file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0 or "ERROR:" in result.stderr:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"ERROR: {detail[:500]}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


# ── Validation ───────────────────────────────────────────────

def _check_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        print(f"ERROR: '{value}' is not a valid learning UUID", file=sys.stderr)
        sys.exit(2)


def _check_enum(flag: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        print(f"ERROR: {flag} '{value}' not in {', '.join(allowed)}",
              file=sys.stderr)
        sys.exit(2)


def _check_impact(flag: str, value: int) -> None:
    if not -3 <= value <= 3:
        print(f"ERROR: {flag} must be between -3 and 3, got {value}",
              file=sys.stderr)
        sys.exit(2)


# ── Commands ─────────────────────────────────────────────────

SELECT_COLS = (
    "id, route, agent, type, status, impact_score, source_ref, "
    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI') AS created, "
    "left(content, 90) AS preview"
)


def cmd_list(status: str | None, route: str | None, limit: int,
             json_out: bool):
    """List ledger rows (default: pending — the lifecycle intake queue)."""
    if status:
        _check_enum("--status", status, STATUSES)
    if route:
        _check_enum("--route", route, ROUTES)
    if limit < 1 or limit > 500:
        print("ERROR: --limit must be 1..500", file=sys.stderr)
        sys.exit(2)

    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    if route:
        where.append("route = ?")
        params.append(route)
    sql = f"SELECT {SELECT_COLS} FROM learnings.learning"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    raw = psql(sql, params)
    if not raw:
        print("No learnings found.")
        return

    rows = []
    for line in raw.split("\n"):
        parts = [p.strip() for p in line.split("||")]
        if len(parts) < 9:
            continue
        rows.append({
            "id": parts[0], "route": parts[1], "agent": parts[2],
            "type": parts[3], "status": parts[4],
            "impact": parts[5] or "0", "source_ref": parts[6] or "",
            "created": parts[7], "content": parts[8],
        })

    if json_out:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    header = (f"{'ID':<38} {'Route':<18} {'Type':<11} {'St':<9} "
              f"{'Imp':<4} {'Created(UTC)':<17} Content")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['id']:<38} {r['route']:<18} {r['type']:<11} "
              f"{r['status']:<9} {r['impact']:<4} {r['created']:<17} "
              f"{r['content']}")


def cmd_set_status(learning_id: str, new_status: str, impact: int | None):
    """Transition a learning's status (optionally revising impact, v002)."""
    learning_id = _check_uuid(learning_id)
    _check_enum("status", new_status, STATUSES)
    if impact is not None:
        _check_impact("--impact", impact)

    if impact is None:
        ok = psql("SELECT learnings.set_status(?::uuid, ?);",
                  [learning_id, new_status])
    else:
        ok = psql("SELECT learnings.set_status(?::uuid, ?, ?::int);",
                  [learning_id, new_status, impact])

    if ok.strip() != "t":
        print(f"ERROR: set_status returned '{ok.strip() or 'nothing'}' — "
              f"no such learning id?", file=sys.stderr)
        sys.exit(1)
    tail = f", impact={impact}" if impact is not None else ""
    print(f"✅ learning {learning_id} → {new_status}{tail}")


def cmd_stats():
    """Status + route counts for the run report."""
    raw = psql(
        "SELECT status, count(*) FROM learnings.learning "
        "GROUP BY status ORDER BY status;"
    )
    print("By status:")
    total = 0
    for line in raw.split("\n"):
        parts = [p.strip() for p in line.split("||")]
        if len(parts) == 2:
            print(f"  {parts[0]:<11} {parts[1]}")
            try:
                total += int(parts[1])
            except ValueError:
                pass
    raw_r = psql(
        "SELECT route, count(*) FROM learnings.learning "
        "GROUP BY route ORDER BY route;"
    )
    print("By route:")
    for line in raw_r.split("\n"):
        parts = [p.strip() for p in line.split("||")]
        if len(parts) == 2:
            print(f"  {parts[0]:<18} {parts[1]}")
    print(f"Total: {total}")


# ── Main ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Orchestrator-only lifecycle client for the fleet learning "
                    "ledger (F-006). Connects as mycortex_reader_<profile>.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list ledger rows (default: pending)")
    p_list.add_argument("--status", default="pending",
                        help=f"filter by status ({', '.join(STATUSES)})")
    p_list.add_argument("--route", default=None,
                        help=f"filter by route ({', '.join(ROUTES)})")
    p_list.add_argument("--limit", type=int, default=25, help="max rows (1..500)")
    p_list.add_argument("--json", action="store_true", help="JSON output")
    p_list.set_defaults(func=cmd_list)

    p_set = sub.add_parser("set-status",
                           help="transition a learning's status (+ optional impact)")
    p_set.add_argument("learning_id", help="learning UUID")
    p_set.add_argument("status", help=f"target status ({', '.join(STATUSES)})")
    p_set.add_argument("--impact", type=int, default=None,
                       help="revise impact_score (-3..3); omit to keep current")
    p_set.set_defaults(func=cmd_set_status)

    p_stats = sub.add_parser("stats", help="status + route counts")
    p_stats.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    if args.command == "list":
        args.func(args.status, args.route, args.limit, args.json)
    elif args.command == "set-status":
        args.func(args.learning_id, args.status, args.impact)
    else:
        args.func()
    return 0


if __name__ == "__main__":
    sys.exit(main())
