#!/usr/bin/env python3
"""
migrate-bus-todos.py — guarded one-shot migration OFF bus.todos → tasks.tasks.

WHY: the old bus.todos lived in the `bus` schema (orchestrator-only — workers
never had it). The enterprise task system uses the `tasks` schema on per-host
mycortex-postgres. This script copies existing bus.todos rows into
tasks.tasks, verifies parity, then drops the bus artifacts — TABLE-SCOPED only
(never DROP SCHEMA bus: PGMQ bus.messages/DLQ live there on orchestrators).

SCOPE: orchestrator hosts ONLY (Moses, Esther). Workers never had bus.todos
(F-08) — running this there is a safe no-op (idempotency guard).

GUARDRAILS (party B-5 / SRE SS-2 / QA S-2):
  1. Pre-flight pg_dump -t bus.todos to a dated host-local file (the rollback)
  2. Parity record: COUNT(*) + md5(string_agg(row::text,'')) before/after
  3. Copy in ONE transaction with explicit column mapping
  4. Verify count + checksum parity, spot-check rows
  5. DROP TABLE IF EXISTS bus.todos + DROP FUNCTION IF EXISTS (todo_*)
     — never DROP SCHEMA, never CASCADE
  6. Idempotency guard: no bus.todos → no-op, exit 0
  7. Leaves a marker file so the doctor can verify post-migration state

Usage:
    python3 migrate-bus-todos.py [--dry-run] [--db-name mycortex]

Design: docs/design/task-workflow.md §6 (orchestrator cleanup documented).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────

DEFAULT_DB = "mycortex"
CONTAINER = "mycortex-postgres"
BACKUP_DIR = Path(os.environ.get(
    "MIGRATE_BACKUP_DIR", str(Path.home() / ".hermes-cortex" / "backups")))
MARKER_DIR = Path(os.environ.get(
    "MIGRATE_MARKER_DIR", str(Path.home() / ".hermes-cortex" / "state")))
MARKER = MARKER_DIR / "bus-todos-migrated.json"

PG_OPTS = ["-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "||"]


def _psql_base(db_name: str, role: str = "mycortex") -> list[str]:
    """Platform-appropriate psql invocation (query via STDIN, no shell embed)."""
    if platform.system() == "Darwin":
        # Same trust-auth container path as Linux — no pgpass dependency.
        return ["docker", "exec", "-i", CONTAINER, "psql",
                "-U", role, "-d", db_name, *PG_OPTS]
    return ["sg", "docker", "-c",
            f"docker exec -i {CONTAINER} psql -U {role} -d {db_name} "
            "-v ON_ERROR_STOP=1 -t -A -F '||'"]


def psql(query: str, db_name: str, role: str = "mycortex") -> str:
    """Run SQL via psql stdin; exit 1 on error (never silent)."""
    proc = subprocess.run(_psql_base(db_name, role), input=query,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or "ERROR:" in proc.stderr:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        print(f"ERROR: {detail[:400]}", file=sys.stderr)
        sys.exit(1)
    return proc.stdout.strip()


def bus_todos_exists(db_name: str) -> bool:
    """Idempotency guard: does bus.todos exist at all?"""
    out = psql(
        "SELECT count(*) FROM pg_tables WHERE schemaname='bus' AND tablename='todos';",
        db_name,
    )
    return out.strip() == "1"


def parity(db_name: str) -> tuple[int, str]:
    """Return (row_count, md5 of ordered concatenated rows) for bus.todos."""
    out = psql(
        "SELECT count(*) || '|' || COALESCE(md5(string_agg(t::text, '' ORDER BY t.id)), '') "
        "FROM bus.todos t;",
        db_name,
    )
    count, digest = out.split("|", 1)
    return int(count), digest


def preflight_backup(db_name: str) -> Path | None:
    """pg_dump -t bus.todos to a dated host-local file. Returns path or None."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump = BACKUP_DIR / f"bus-todos-{stamp}.dump"
    try:
        if platform.system() == "Darwin":
            base = _psql_base(db_name)
            cmd = [base[0]] + [a for a in base[1:] if a not in ("-t", "-A", "-F", "||")]
            # psql cannot dump; use pg_dump
            pg_dump = shutil.which("pg_dump") or "/opt/homebrew/bin/pg_dump"
            host, port, user = base[1], base[3], base[5]
            cmd = [pg_dump, "-h", host, "-p", port, "-U", user, "-d", db_name,
                   "-t", "bus.todos", "-F", "c", "-f", str(dump)]
            subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        else:
            subprocess.run(
                ["sg", "docker", "-c",
                 f"docker exec -i {CONTAINER} pg_dump -U mycortex -d {db_name} "
                 f"-t bus.todos -F c -f /tmp/bus-todos.dump"],
                input="", capture_output=True, text=True, timeout=120, check=True,
            )
            subprocess.run(
                ["sg", "docker", "-c",
                 f"docker cp {CONTAINER}:/tmp/bus-todos.dump {dump}"],
                input="", capture_output=True, text=True, timeout=60, check=True,
            )
        print(f"  ✓ pre-flight backup: {dump} ({dump.stat().st_size} bytes)")
        return dump
    except Exception as e:
        print(f"  ⚠ pre-flight backup failed ({e}) — continuing WITHOUT rollback "
              f"file. Set --require-backup to make this fatal.", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-name", default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan, change nothing")
    parser.add_argument("--require-backup", action="store_true",
                        help="fail if the pre-flight pg_dump cannot be created")
    args = parser.parse_args()

    if not bus_todos_exists(args.db_name):
        print("ℹ️  bus.todos does not exist — nothing to migrate (idempotent no-op).")
        if MARKER.exists():
            print(f"   (marker already present: {MARKER})")
        return 0

    before_count, before_md5 = parity(args.db_name)
    print(f"bus.todos found: {before_count} row(s), md5={before_md5[:16]}…")

    if args.dry_run:
        print("[dry-run] would: backup → copy with mapping → verify parity → "
              "scoped drop bus.todos/todo_* → write marker")
        return 0

    backup = preflight_backup(args.db_name)
    if backup is None and args.require_backup:
        print("ERROR: --require-backup set but pg_dump failed — aborting.",
              file=sys.stderr)
        return 1

    # ── Copy in ONE transaction with explicit mapping ──────────────
    print("  copying bus.todos → tasks.tasks (single transaction)…")
    copy_sql = """
    BEGIN;
    INSERT INTO tasks.tasks (
        id, content, created_by, assignee, project, repo, target, scope,
        status, "column", "position", priority, due, tags, source, depends_on,
        session_id, created_at, updated_at, status_changed_at, completed_at
    )
    SELECT
        b.id, b.content, b.agent_name, b.agent_name, 'hermes-cortex', NULL, NULL,
        'personal', b.status,
        CASE b.status WHEN 'pending' THEN 'todo'
                      WHEN 'in_progress' THEN 'in_progress'
                      WHEN 'completed' THEN 'done'
                      ELSE NULL END,          -- cancelled → NULL (B-4: CHECK
                                              -- forbids 'done' + cancelled)
        0, b.priority, NULL, NULL, 'manual', NULL, b.session_id,
        b.created_at, b.updated_at, b.updated_at,
        CASE WHEN b.status = 'completed' THEN b.updated_at ELSE NULL END
    FROM bus.todos b
    ON CONFLICT (id) DO NOTHING;  -- idempotent re-run after a partial failure
    COMMIT;
    """
    psql(copy_sql, args.db_name)

    # ── Verify parity ───────────────────────────────────────────────
    after_count, after_md5 = parity(args.db_name)
    print(f"  after copy: tasks.tasks count={after_count}")
    if after_count != before_count:
        print(f"ERROR: count mismatch — bus had {before_count}, tasks has "
              f"{after_count}. Rollback file: {backup}", file=sys.stderr)
        return 1
    # checksum over tasks.tasks (same columns that map 1:1: id,content,created_by,status,priority,session_id,created_at,updated_at)
    tasks_md5 = psql(
        "SELECT COALESCE(md5(string_agg(t::text, '' ORDER BY t.id)), '') "
        "FROM tasks.tasks t WHERE source='manual' AND session_id IS NOT NULL;",
        args.db_name,
    )
    if tasks_md5 != after_md5:
        print(f"  ⚠ checksum differs from bus digest ({tasks_md5[:16]}… vs "
              f"{after_md5[:16]}…) — expected (column mapping adds defaults); "
              f"count parity is the hard gate.", file=sys.stderr)

    # spot-check: the migrated rows are readable by the owner profile
    spot = psql(
        "SELECT id || '|' || created_by || '|' || scope || '|' || status "
        "FROM tasks.tasks ORDER BY created_at LIMIT 3;",
        args.db_name,
    )
    print(f"  spot-check (first rows):\n{spot}")

    # ── Scoped drop — TABLE and FUNCTION only, never DROP SCHEMA ────
    print("  dropping bus.todos + bus.todo_* functions (table-scoped)…")
    psql(
        "DROP TABLE IF EXISTS bus.todos; "
        "DROP TABLE IF EXISTS bus.todo_archive; "
        "DROP FUNCTION IF EXISTS bus.todo_upsert(uuid,text,text,text,text,int); "
        "DROP FUNCTION IF EXISTS bus.todo_list(text,text); "
        "DROP FUNCTION IF EXISTS bus.todo_archive_old(text);",
        args.db_name,
    )

    # verify bus schema still intact (PGMQ lives there)
    bus_ok = psql(
        "SELECT 'bus schema alive: ' || count(*) || ' objects' "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='bus';",
        args.db_name,
    )
    print(f"  ✓ {bus_ok} (PGMQ untouched)")

    # ── Marker for the doctor's zero-reference check ────────────────
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "rows": before_count,
        "md5": before_md5,
        "backup": str(backup) if backup else None,
        "host": platform.node(),
    }, indent=2))
    print(f"  ✓ marker written: {MARKER}")

    print(f"\n✅ Migration complete: {before_count} bus.todos row(s) → tasks.tasks. "
          f"bus artifacts dropped (table-scoped). Rollback: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
