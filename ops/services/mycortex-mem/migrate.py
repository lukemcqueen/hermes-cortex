#!/usr/bin/env python3
"""
mycortex-mem migrate.py — schema_version-gated migration runner for mycortex_mem.

Applies SQL migrations from the sibling schema/ directory to the shared
mycortex-postgres database. Idempotent: re-running when current is a no-op.

Invoked by cortex-update.sh AFTER file sync (cortex-update itself has no DDL
path — this runner is the DDL path). New hosts: install.sh runs it once.

Usage:
    migrate.py [--db-name mycortex] [--schema-dir DIR] [--dry-run] [--verbose]

Migration discovery:
    - schema/v001__mem.sql        → version 1  (v001, canonical)
    - schema/vNNN__*.sql          → version NNN (future migrations)

Role creation (mycortex_mem_admin / mycortex_mem_writer / mycortex_mem_reader)
lives at the top of v001__mem.sql with DO $$ guards — PG has no CREATE ROLE
IF NOT EXISTS. The runner executes as the `mycortex` superuser (container
trust auth) so the DO blocks can create roles on first apply; the schema's
GRANT section then establishes the role split for the plugin's runtime use.
"""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

DEFAULT_DB = "mycortex"


def _psql_base(db_name: str) -> list[str]:
    """Platform-appropriate psql invocation (mycortex migrate.py pattern).

    Both OSes → docker exec into mycortex-postgres: trust auth inside the
    container, no ~/.pgpass dependency. macOS Docker Desktop needs no
    `sg docker` group — same exec form as Linux minus the wrapper.
    """
    if platform.system() == "Darwin":
        return [
            "docker", "exec", "-i", "mycortex-postgres",
            "psql", "-U", "mycortex", "-d", db_name,
            "-v", "ON_ERROR_STOP=1", "-t", "-A",
        ]
    # Linux — container exec via sg docker group
    return [
        "sg", "docker", "-c",
        f"docker exec -i mycortex-postgres psql -U mycortex -d {db_name} -v ON_ERROR_STOP=1 -t -A",
    ]


def psql_script(sql: str, db_name: str) -> tuple[int, str, str]:
    """Run a SQL script via psql, return (returncode, stdout, stderr)."""
    cmd = _psql_base(db_name)
    proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def psql_query(sql: str, db_name: str) -> str:
    """Run a query and return trimmed stdout; raises on non-zero exit."""
    rc, out, err = psql_script(sql, db_name)
    if rc != 0:
        raise RuntimeError(f"psql failed (rc={rc}): {err.strip() or out.strip()}")
    return out.strip()


# ── Migration discovery ───────────────────────────────────────

def discover_migrations(schema_dir: Path) -> list[tuple[int, Path]]:
    """Return [(version, path)] sorted ascending.

    v001__mem.sql = version 1; vNNN__*.sql = version NNN.
    """
    migrations: list[tuple[int, Path]] = []
    for p in sorted(schema_dir.glob("*.sql")):
        m = re.match(r"v(\d+)__", p.name)
        if m:
            migrations.append((int(m.group(1)), p))
        else:
            print(f"  ⚠ skipping unrecognized schema file: {p.name}", file=sys.stderr)
    migrations.sort(key=lambda t: t[0])
    return migrations


def current_version(db_name: str) -> int:
    """Max applied version; 0 when the schema doesn't exist yet."""
    try:
        out = psql_query(
            "SELECT COALESCE(MAX(version), 0) FROM mycortex_mem.schema_version;", db_name
        )
        return int(out.splitlines()[0] if out else 0)
    except RuntimeError as e:
        # Schema not present yet → version 0 (fresh DB / first apply)
        if "does not exist" in str(e) or "schema" in str(e).lower():
            return 0
        raise


# ── Main ─────────────────────────────────────────────────────

def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-name", default=DEFAULT_DB, help=f"target database (default: {DEFAULT_DB})")
    parser.add_argument("--schema-dir", type=Path, default=here / "schema",
                        help="directory containing migration SQL files")
    parser.add_argument("--dry-run", action="store_true", help="print what would run, change nothing")
    parser.add_argument("--verbose", action="store_true", help="show psql stdout")
    args = parser.parse_args()

    schema_dir = args.schema_dir.resolve()
    if not schema_dir.is_dir():
        print(f"ERROR: schema dir not found: {schema_dir}", file=sys.stderr)
        return 1

    migrations = discover_migrations(schema_dir)
    if not migrations:
        print(f"ERROR: no migration files found in {schema_dir}", file=sys.stderr)
        return 1

    current = current_version(args.db_name)
    pending = [(v, p) for v, p in migrations if v > current]

    if not pending:
        print(f"mycortex_mem schema up to date (version {current}) — no-op")
        return 0

    print(f"mycortex_mem schema: current={current}, applying {len(pending)} migration(s) to DB '{args.db_name}'")
    applied_max = current
    for version, path in pending:
        label = f"v{version:03d} ({path.name})"
        sql = path.read_text()
        if args.dry_run:
            print(f"  [dry-run] would apply {label}")
            continue
        print(f"  applying {label} …")
        rc, out, err = psql_script(sql, args.db_name)
        if rc != 0:
            print(f"  ❌ {label} FAILED (rc={rc}):", file=sys.stderr)
            print(err.strip()[-2000:] or out.strip()[-2000:], file=sys.stderr)
            return 1
        # Record the applied version (same DB, same schema)
        rec_rc, rec_out, rec_err = psql_script(
            f"INSERT INTO mycortex_mem.schema_version (version) VALUES ({version}) "
            f"ON CONFLICT (version) DO NOTHING;",
            args.db_name,
        )
        if rec_rc != 0:
            print(f"  ❌ failed to record schema_version={version}: {rec_err.strip()}", file=sys.stderr)
            return 1
        if args.verbose and out:
            print(out.strip()[-2000:])
        applied_max = version

    if args.dry_run:
        print(f"  [dry-run] no changes made — schema stays at version {current}")
    else:
        print(f"mycortex_mem schema at version {applied_max} — done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
