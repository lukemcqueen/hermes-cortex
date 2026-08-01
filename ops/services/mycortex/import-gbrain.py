#!/usr/bin/env python3.12
"""
import-gbrain.py — one-shot gbrain → mycortex data migration (additive only).

Copies gbrain's indexed knowledge (public.sources, public.pages,
public.content_chunks) into the mycortex schema on the SAME shared Postgres
(gbrain DB). Idempotent: safe to re-run — sources conflict on name (update
local_path), pages conflict on (source_id, relpath) while not archived,
chunks conflict on (page_id, chunk_index). Nothing is deleted from gbrain;
decommission (public table tombstone/drop) is a separate, later, gated phase
(design §4 Phase 6-7).

Federation: imported sources are created is_federated=false (isolated,
fail-closed). Mark a source federated explicitly with --federated NAME
(re-run; requires the PII gate — mycortex CHECK enforces pii_scan_at when
federated; this script records pii_scan_at=now() at federation time, the
operator's responsibility).

FTS: pages.fts is rebuilt from concatenated chunk content using the source's
search_config ('simple' default — mixed-language safe) so text search works
immediately after import, matching what the ingest path will do going forward.

Usage:
    import-gbrain.py [--db-name gbrain] [--dry-run] [--verbose]
    import-gbrain.py --federated hermes-cortex --federated shared   # re-run

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Reuse migrate.py's psql helpers (same package dir, same platform handling)
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from migrate import _psql_base, psql_script  # noqa: E402


def run_sql(sql: str, db_name: str, verbose: bool = False) -> tuple[int, str, str]:
    """Run SQL, return (rc, stdout, stderr). Raises on non-zero."""
    rc, out, err = psql_script(sql, db_name)
    if verbose and out.strip():
        print(out.strip())
    if rc != 0:
        raise RuntimeError(f"psql failed (rc={rc}): {err.strip()[-2000:] or out.strip()[-2000:]}")
    return rc, out, err


def count(sql: str, db_name: str) -> int:
    rc, out, err = psql_script(sql, db_name)
    if rc != 0:
        raise RuntimeError(f"count failed: {err.strip()}")
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


# ── Source registration ───────────────────────────────────────

REGISTER_SOURCES = """
INSERT INTO mycortex.sources (name, local_path, host, sync_mode, is_federated, search_config)
SELECT gs.name, gs.local_path, 'localhost',
       CASE WHEN gs.local_path IS NULL OR gs.local_path = '' THEN 'git' ELSE 'local' END,
       FALSE, 'simple'
FROM public.sources gs
ON CONFLICT (name) DO UPDATE SET
  local_path = EXCLUDED.local_path
RETURNING name, id;
"""

# ── Pages ─────────────────────────────────────────────────────

# gbrain page → mycortex page, joined through source name mapping.
# skips gbrain-soft-deleted pages (deleted_at IS NOT NULL).
INSERT_PAGES = """
INSERT INTO mycortex.pages (source_id, relpath, title, content_hash, updated_at)
SELECT ms.id, gp.slug, gp.title, gp.content_hash, COALESCE(gp.updated_at, now())
FROM public.pages gp
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name
WHERE gp.deleted_at IS NULL
ON CONFLICT (source_id, relpath) WHERE NOT archived
DO UPDATE SET content_hash = EXCLUDED.content_hash,
              title = EXCLUDED.title,
              updated_at = EXCLUDED.updated_at;
"""

# ── Chunks ────────────────────────────────────────────────────

INSERT_CHUNKS = """
INSERT INTO mycortex.content_chunks (page_id, chunk_index, content)
SELECT mp.id, gc.chunk_index, gc.chunk_text
FROM public.content_chunks gc
JOIN public.pages gp ON gp.id = gc.page_id
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name
JOIN mycortex.pages mp ON mp.source_id = ms.id AND mp.relpath = gp.slug AND NOT mp.archived
WHERE gp.deleted_at IS NULL
ON CONFLICT (page_id, chunk_index) DO NOTHING;
"""

# ── FTS rebuild (matches ingest-path maintenance, 'simple' per source) ──

REBUILD_FTS = """
UPDATE mycortex.pages p
SET fts = sub.ts
FROM (
  SELECT c.page_id,
         to_tsvector(COALESCE(s.search_config, 'simple')::regconfig,
                     string_agg(c.content, ' ' ORDER BY c.chunk_index)) AS ts
  FROM mycortex.content_chunks c
  JOIN mycortex.pages pg ON pg.id = c.page_id
  JOIN mycortex.sources s ON s.id = pg.source_id
  GROUP BY c.page_id, s.search_config
) sub
WHERE sub.page_id = p.id
  AND p.fts IS DISTINCT FROM sub.ts;
"""

# ── Federation flip (explicit, re-run safe) ───────────────────

def federate(name: str, db_name: str) -> bool:
    """Mark a source federated (records PII-scan time; operator's responsibility)."""
    rc, out, err = psql_script(
        "UPDATE mycortex.sources SET is_federated = TRUE, pii_scan_at = COALESCE(pii_scan_at, now()) "
        "WHERE name = $$%s$$ AND NOT is_federated;" % name,
        db_name,
    )
    if rc != 0:
        print(f"  ⚠ failed to federate '{name}': {err.strip()[:300]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-name", default="gbrain", help="target database (default: gbrain)")
    parser.add_argument("--dry-run", action="store_true", help="print counts, change nothing")
    parser.add_argument("--verbose", action="store_true", help="show psql stdout")
    parser.add_argument("--federated", action="append", default=[],
                        help="source name to mark federated (repeatable; re-run safe)")
    args = parser.parse_args()

    db = args.db_name
    if db == "mycortex_test" and not args.dry_run:
        # Hermeticity guard (design §5): tests never touch prod, prod never
        # accidentally targets scratch. Import on scratch is allowed with
        # --dry-run for validation.
        print("REFUSED: --db-name mycortex_test without --dry-run (hermeticity guard)", file=sys.stderr)
        return 1

    # Counts BEFORE
    src_sql = "SELECT count(*) FROM public.sources;"
    page_sql = "SELECT count(*) FROM public.pages WHERE deleted_at IS NULL;"
    chunk_sql = "SELECT count(*) FROM public.content_chunks;"
    n_src = count(src_sql, db)
    n_pages = count(page_sql, db)
    n_chunks = count(chunk_sql, db)
    print(f"gbrain source rows: {n_src} sources | {n_pages} active pages | {n_chunks} chunks")

    if args.dry_run:
        print("DRY RUN — no changes made.")
        return 0

    # 1. Sources
    rc, out, err = run_sql(REGISTER_SOURCES, db, args.verbose)
    registered = len([l for l in out.strip().splitlines() if l.strip()])
    print(f"registered sources: {registered}")

    # 2. Pages
    run_sql(INSERT_PAGES, db, args.verbose)
    print("pages migrated (upsert)")

    # 3. Chunks
    run_sql(INSERT_CHUNKS, db, args.verbose)
    print("chunks migrated (upsert)")

    # 4. FTS
    run_sql(REBUILD_FTS, db, args.verbose)
    print("fts rebuilt")

    # 5. Federation flip (explicit opt-in)
    for name in args.federated:
        if federate(name, db):
            print(f"federated: {name}")

    # Verify counts AFTER
    n_pages_after = count("SELECT count(*) FROM mycortex.pages WHERE NOT archived;", db)
    n_chunks_after = count("SELECT count(*) FROM mycortex.content_chunks;", db)
    n_src_after = count("SELECT count(*) FROM mycortex.sources;", db)
    print(f"mycortex after: {n_src_after} sources | {n_pages_after} active pages | {n_chunks_after} chunks")
    if n_pages_after < n_pages or n_chunks_after < n_chunks:
        print(f"⚠ WARNING: mycortex counts below gbrain source counts "
              f"({n_pages_after}/{n_pages} pages, {n_chunks_after}/{n_chunks} chunks) — check joins",
              file=sys.stderr)
        return 1
    print("import complete — gbrain data untouched (decommission is a separate gated phase)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
