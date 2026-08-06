#!/usr/bin/env python3
"""
tasks migrate.py — schema_version-gated migration runner for the tasks schema.

Applies SQL migrations from the sibling schema/ directory to the shared
mycortex-postgres database. Idempotent: re-running when current is a no-op.
Connects as the DB owner (mycortex) for DDL — same trust level as the mycortex
migrate.py; task-db.py CRUD never touches superuser (party fix B-2).

Invoked by cortex-update.sh AFTER file sync (cortex-update itself has no DDL
path — this runner is the DDL path, same as ops/services/mycortex/migrate.py).

Usage:
    migrate.py [--db-name mycortex] [--schema-dir DIR] [--dry-run] [--verbose]

Migration discovery:
    - schema/vNNN__*.sql       → version NNN (v001__tasks.sql = version 1)

Design: docs/design/task-workflow.md §3 (party B-9: version-gated, fail loudly).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

MYCORTEX_CONFIG = os.path.expanduser("~/.hermes-cortex/mycortex.conf")
DEFAULT_DB = "mycortex"
# DDL runs as the DB owner (mycortex) via the version-gated runner — the
# same trust level as mycortex migrate.py (house precedent). CRUD in
# task-db.py connects as mycortex_reader_<profile> — the CRUD path NEVER
# touches superuser (party fix B-2). Role creation inside v001__tasks.sql
# requires CREATEROLE, which only the owner has on every host.
DDL_ROLE = "mycortex"


def _psql_base(db_name: str, role: str = DDL_ROLE) -> list[str]:
    """Platform-appropriate psql invocation as mycortex_admin.

    Linux  → sg docker (container is the DB host)
    macOS  → direct psql reading mycortex.conf (or defaults)
    """
    if platform.system() == "Darwin":
        url = None
        if os.path.exists(MYCORTEX_CONFIG):
            with open(MYCORTEX_CONFIG) as f:
                cfg = json.load(f)
            url = cfg.get("database_url")
        if not url:
            url = f"postgresql://{role}:@127.0.0.1:15432/{db_name}"
        from urllib.parse import urlparse
        parsed = urlparse(url)
        psql = shutil.which("psql") or "/opt/homebrew/bin/psql"
        return [
            psql,
            "-h", parsed.hostname or "127.0.0.1",
            "-p", str(parsed.port or 15432),
            "-U", parsed.username or role,
            "-d", db_name,
            "-v", "ON_ERROR_STOP=1",
            "-t", "-A",
        ]
    # Linux — container exec as DDL role. SQL flows via stdin (never embedded
    # in the command string) so there is no shell-injection surface (B-1).
    return [
        "sg", "docker", "-c",
        f"docker exec -i mycortex-postgres psql -U {role} -d {db_name} "
        f"-v ON_ERROR_STOP=1 -t -A",
    ]


def psql_script(sql: str, db_name: str) -> tuple[int, str, str]:
    """Run a SQL script via psql stdin (ON_ERROR_STOP makes rc meaningful),
    return (returncode, stdout, stderr)."""
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
    """Return [(version, path)] sorted ascending. vNNN__*.sql → version NNN."""
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
            "SELECT COALESCE(MAX(version), 0) FROM tasks.schema_version;", db_name
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
        print(f"tasks schema up to date (version {current}) — no-op")
        return 0

    print(f"tasks schema: current={current}, applying {len(pending)} migration(s) to DB '{args.db_name}'")
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
            print((err or out).strip(), file=sys.stderr)
            return rc
        if args.verbose and out.strip():
            print(f"  {out.strip()}")
        # Record version (after successful apply; idempotent re-run skips)
        ver_rc, ver_out, ver_err = psql_script(
            f"INSERT INTO tasks.schema_version (version) VALUES ({version}) "
            f"ON CONFLICT (version) DO NOTHING;",
            args.db_name,
        )
        if ver_rc != 0:
            print(f"  ❌ version record failed (rc={ver_rc}): {ver_err.strip()}", file=sys.stderr)
            return ver_rc
        applied_max = version
        print(f"  ✓ {label} applied (version {version})")

    print(f"tasks schema now at version {applied_max}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
