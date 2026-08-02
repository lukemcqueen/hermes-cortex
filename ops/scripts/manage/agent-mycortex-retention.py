#!/usr/bin/env python3
"""
agent-mycortex-retention.py — prune stale mycortex audit/archived data (S-016).

Runs as a no_agent cron (daily). Silent (empty stdout) when nothing pruned or
pruning succeeds with nothing to do. Emits a one-line summary when rows ARE
pruned so the cron delivery path confirms the cleanup happened.

Prunes:
  1. mycortex.ingest_log rows older than 90 days (started_at < now() - 90d)
  2. mycortex.pages hard-purge where archived AND updated_at < now() - 7d
     (soft-delete window from the mass-deletion guardrail design)

Role: mycortex_ingest (DML on pages/content_chunks/ingest_log per schema design;
admin is SELECT/audit only). Verified live: ingest can DELETE both tables.

Exit codes: 0 = ok (even when nothing to prune), 1 = error.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

DB_DEFAULT = "gbrain"
INGEST_LOG_DAYS = 90
ARCHIVED_PURGE_DAYS = 7


def _psql_base(role: str, db_name: str) -> list[str]:
    """Platform-appropriate psql invocation (same pattern as mycortex CLI)."""
    if platform.system() == "Darwin":
        url = None
        cfg_path = Path.home() / ".hermes-cortex" / "mycortex.conf"
        if cfg_path.exists():
            try:
                cfg = __import__("json").loads(cfg_path.read_text())
                url = cfg.get("database_url")
            except (OSError, ValueError):
                url = None
        if not url:
            url = os.environ.get("MYCORTEX_DB_URL", "")
        if not url:
            url = f"postgresql://{role}@127.0.0.1:15432/{db_name}"
        from urllib.parse import urlparse

        parsed = urlparse(url)
        psql = shutil.which("psql") or "/opt/homebrew/bin/psql"
        return [
            psql,
            "-h", parsed.hostname or "127.0.0.1",
            "-p", str(parsed.port or 15432),
            "-U", role,
            "-d", db_name,
            "-v", "ON_ERROR_STOP=1",
            "-t", "-A",
        ]
    # Linux — container exec as the role (trust auth inside container)
    return [
        "sg", "docker", "-c",
        f"docker exec -i gbrain-postgres psql -U {role} -d {db_name} -v ON_ERROR_STOP=1 -t -A",
    ]


def psql_script(sql: str, role: str = "mycortex_ingest", db_name: str = DB_DEFAULT) -> tuple[int, str, str]:
    cmd = _psql_base(role, db_name)
    proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


def run_retention(dry_run: bool = False) -> tuple[int, int]:
    """Prune ingest_log + archived pages. Returns (ingest_pruned, pages_purged).

    Counts eligible rows BEFORE deleting (in the same txn) so the reported
    numbers are rows removed, not rows remaining.
    """
    sql = f"""
BEGIN;
SELECT count(*) FROM mycortex.ingest_log
 WHERE started_at < now() - interval '{INGEST_LOG_DAYS} days'
   AND status IN ('ok', 'error');
DELETE FROM mycortex.ingest_log
 WHERE started_at < now() - interval '{INGEST_LOG_DAYS} days'
   AND status IN ('ok', 'error');
SELECT count(*) FROM mycortex.pages
 WHERE archived = TRUE
   AND updated_at < now() - interval '{ARCHIVED_PURGE_DAYS} days';
DELETE FROM mycortex.pages
 WHERE archived = TRUE
   AND updated_at < now() - interval '{ARCHIVED_PURGE_DAYS} days';
COMMIT;
"""
    if dry_run:
        sql = f"""
SELECT count(*) FROM mycortex.ingest_log
 WHERE started_at < now() - interval '{INGEST_LOG_DAYS} days'
   AND status IN ('ok', 'error');
SELECT count(*) FROM mycortex.pages
 WHERE archived = TRUE
   AND updated_at < now() - interval '{ARCHIVED_PURGE_DAYS} days';
"""
    rc, out, err = psql_script(sql)
    if rc != 0:
        raise RuntimeError(f"retention psql failed (rc={rc}): {err.strip()[-2000:] or out.strip()[-2000:]}")

    # Output: two scalar rows (counts) in -t -A mode
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    ingest_pruned = int(lines[0]) if lines and lines[0].lstrip("-").isdigit() else 0
    pages_purged = int(lines[1]) if len(lines) > 1 and lines[1].lstrip("-").isdigit() else 0
    return ingest_pruned, pages_purged


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    ingest_pruned, pages_purged = run_retention(dry_run=dry_run)
    if dry_run:
        print(f"[dry-run] would prune {ingest_pruned} ingest_log row(s), {pages_purged} archived page(s)")
    elif ingest_pruned or pages_purged:
        print(f"[mycortex-retention] pruned {ingest_pruned} ingest_log row(s), {pages_purged} archived page(s)")
    # else: silent — watchdog pattern, nothing to report
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — cron watchdog: emit error, exit non-zero
        print(f"❌ mycortex-retention error: {e}", file=sys.stderr)
        sys.exit(1)
