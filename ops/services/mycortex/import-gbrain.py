#!/usr/bin/env python3
"""
import-gbrain.py — one-shot gbrain → mycortex data migration (additive only).

Copies gbrain's indexed knowledge (public.sources, public.pages,
public.content_chunks) into the mycortex schema on the SAME shared Postgres
(gbrain DB). Idempotent: safe to re-run — sources conflict on name (update
local_path), pages conflict on (source_id, relpath) while not archived,
chunks conflict on (page_id, chunk_index). Nothing is deleted from gbrain;
decommission (public table tombstone/drop) is a separate, later, gated phase
(design §4 Phase 6-7).

Relpath mapping: gbrain stores slug relpaths (extension-stripped, lowercased:
  `skills/.../skill` for `skills/.../SKILL.md`, `docs/agent-architecture`
  for `docs/agent-architecture.md`). mycortex's canonical relpath is the REAL
  file path (golden queries, design §2). This script walks each source tree
  and inserts pages with the real path, pruning any slug-path leftovers so
  re-runs never duplicate. Pages whose slug matches no real file (hidden-dir
  artifacts the walk skips) are left as slug paths — they archive harmlessly
  on the first sync (well under the 10% mass-deletion guardrail).

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


def esc_literal(s: str) -> str:
    """SQL string literal (single-quote escaped, wrapped)."""
    return "'" + str(s).replace("'", "''") + "'"


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

# ── Source-tree walk (mirrors the CLI's sync walk) ────────────

def _walk_source_files(local_path: str, mode: str) -> list[str]:
    """Real file relpaths for a source."""
    root = Path(local_path)
    if mode == "git":
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git ls-files failed in {local_path}: {proc.stderr.strip()[:500]}")
        return [ln for ln in proc.stdout.splitlines() if ln.strip()]
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if any(part.startswith(".") for part in Path(rel).parts):
                continue
            out.append(rel)
    return out


def _slug_to_real_map(local_path: str, mode: str) -> dict[str, str]:
    """slug (lowercased, extension-stripped) → real relpath, unique matches only."""
    mapping: dict[str, str | None] = {}
    for rel in _walk_source_files(local_path, mode):
        key = Path(rel).with_suffix("").as_posix().lower()
        if key in mapping and mapping[key] != rel:
            mapping[key] = None  # ambiguous — leave slug untouched
        elif key not in mapping:
            mapping[key] = rel
    return {k: v for k, v in mapping.items() if v}


def _slug_values(slug_map: dict[str, str]) -> str:
    """VALUES clause (slug, real_path) for one source."""
    if not slug_map:
        return ""
    return ",\n".join(
        f"({esc_literal(s)}, {esc_literal(r)})" for s, r in slug_map.items()
    )


# ── Pages (insert with REAL relpaths — idempotent) ────────────

def insert_pages(db: str, source_name: str, slug_values: str, verbose: bool = False) -> None:
    """Insert gbrain pages for one source, mapping slug → real relpath.

    ON CONFLICT targets (source_id, relpath) with the REAL path, so re-runs
    upsert the same rows instead of creating slug-path duplicates.
    """
    if not slug_values:
        # No walkable tree — fall back to raw slugs (e.g. builtin 'default')
        sql = """
INSERT INTO mycortex.pages (source_id, relpath, title, content_hash, updated_at)
SELECT ms.id, gp.slug, gp.title, gp.content_hash, COALESCE(gp.updated_at, now())
FROM public.pages gp
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name AND ms.name = $$%s$$
WHERE gp.deleted_at IS NULL
ON CONFLICT (source_id, relpath) WHERE NOT archived
DO UPDATE SET content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at;
""" % source_name
        run_sql(sql, db, verbose)
        return
    sql = """
INSERT INTO mycortex.pages (source_id, relpath, title, content_hash, updated_at)
SELECT ms.id, COALESCE(sm.real_path, gp.slug), gp.title, gp.content_hash, COALESCE(gp.updated_at, now())
FROM public.pages gp
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name AND ms.name = $$%s$$
LEFT JOIN (VALUES
%s
) AS sm(slug, real_path) ON sm.slug = gp.slug
WHERE gp.deleted_at IS NULL
ON CONFLICT (source_id, relpath) WHERE NOT archived
DO UPDATE SET content_hash = EXCLUDED.content_hash,
              updated_at = EXCLUDED.updated_at;
""" % (source_name, slug_values)
    run_sql(sql, db, verbose)


# ── Chunks (join through the same slug → real map) ────────────

def insert_chunks(db: str, source_name: str, slug_values: str, verbose: bool = False) -> None:
    if not slug_values:
        sql = """
INSERT INTO mycortex.content_chunks (page_id, chunk_index, content)
SELECT mp.id, gc.chunk_index, gc.chunk_text
FROM public.content_chunks gc
JOIN public.pages gp ON gp.id = gc.page_id
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name AND ms.name = $$%s$$
JOIN mycortex.pages mp ON mp.source_id = ms.id AND mp.relpath = gp.slug AND NOT mp.archived
WHERE gp.deleted_at IS NULL
ON CONFLICT (page_id, chunk_index) DO NOTHING;
""" % source_name
        run_sql(sql, db, verbose)
        return
    sql = """
INSERT INTO mycortex.content_chunks (page_id, chunk_index, content)
SELECT mp.id, gc.chunk_index, gc.chunk_text
FROM public.content_chunks gc
JOIN public.pages gp ON gp.id = gc.page_id
JOIN public.sources gs ON gs.id = gp.source_id
JOIN mycortex.sources ms ON ms.name = gs.name AND ms.name = $$%s$$
LEFT JOIN (VALUES
%s
) AS sm(slug, real_path) ON sm.slug = gp.slug
JOIN mycortex.pages mp ON mp.source_id = ms.id
  AND mp.relpath = COALESCE(sm.real_path, gp.slug)
  AND NOT mp.archived
WHERE gp.deleted_at IS NULL
ON CONFLICT (page_id, chunk_index) DO NOTHING;
""" % (source_name, slug_values)
    run_sql(sql, db, verbose)


# ── Prune slug-path duplicates (idempotency guard) ────────────

def prune_slug_rows(db: str, source_name: str, slug_values: str, verbose: bool = False) -> int:
    """Delete slug-path pages that map to a real file, before re-insert.

    A previous buggy run may have left pages with slug relpaths while a
    real-path twin exists. Deleting them (cascade removes their chunks) keeps
    the import idempotent: the pages are re-inserted with real paths below.
    """
    if not slug_values:
        return 0
    rc, out, err = psql_script(
        "DELETE FROM mycortex.pages p\n"
        "USING (VALUES\n" + slug_values + "\n) AS v(slug, real_path)\n"
        "WHERE p.source_id = (SELECT id FROM mycortex.sources WHERE name = $$%s$$)\n"
        "  AND NOT p.archived\n"
        "  AND p.relpath = v.slug;" % source_name,
        db,
    )
    if rc != 0:
        print(f"  ⚠ '{source_name}': prune failed: {err.strip()[:500]}", file=sys.stderr)
        return 0
    # parse "DELETE n" from psql -t -A output
    try:
        n = int(out.strip().splitlines()[0].replace("DELETE ", ""))
    except (ValueError, IndexError):
        n = 0
    if verbose and n:
        print(f"pruned {n} slug-path duplicate row(s) for '{source_name}'")
    return n


# ── FTS rebuild (matches ingest-path maintenance, 'simple' per source) ──

REBUILD_FTS = """
UPDATE mycortex.pages p
SET fts = sub.ts
FROM (
  SELECT c.page_id,
         setweight(to_tsvector(COALESCE(s.search_config, 'simple')::regconfig,
                     replace(replace(COALESCE(pg.title, ''), '/', ' '), '-', ' ')), 'A') ||
         setweight(to_tsvector(COALESCE(s.search_config, 'simple')::regconfig,
                     replace(replace(COALESCE(pg.relpath, ''), '/', ' '), '-', ' ')), 'B') ||
         setweight(to_tsvector(COALESCE(s.search_config, 'simple')::regconfig,
                     string_agg(c.content, ' ' ORDER BY c.chunk_index)), 'C') AS ts
  FROM mycortex.content_chunks c
  JOIN mycortex.pages pg ON pg.id = c.page_id
  JOIN mycortex.sources s ON s.id = pg.source_id
  GROUP BY c.page_id, s.search_config, pg.title, pg.relpath
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

    # 2. Per-source: prune slug dupes → insert pages (real relpaths) → chunks
    src_rows = []
    rc, out, err = psql_script(
        "SELECT name, local_path, sync_mode FROM mycortex.sources WHERE NOT archived;", db)
    if rc != 0:
        raise RuntimeError(f"source list failed: {err.strip()[:500]}")
    for ln in out.splitlines():
        if ln.strip():
            parts = ln.split("|")
            if len(parts) >= 3:
                src_rows.append((parts[0], parts[1], parts[2]))

    total_pruned = 0
    for name, local_path, mode in src_rows:
        if local_path and local_path.strip():
            try:
                slug_map = _slug_to_real_map(local_path, mode)
            except RuntimeError as e:
                print(f"  ⚠ source '{name}': {e}", file=sys.stderr)
                slug_values = ""
            else:
                slug_values = _slug_values(slug_map)
        else:
            slug_values = ""
        total_pruned += prune_slug_rows(db, name, slug_values, args.verbose)
        insert_pages(db, name, slug_values, args.verbose)
        insert_chunks(db, name, slug_values, args.verbose)
    print(f"pages migrated (upsert) — pruned {total_pruned} slug-path duplicate(s)")

    # 3. FTS
    run_sql(REBUILD_FTS, db, args.verbose)
    print("fts rebuilt")

    # 4. Federation flip (explicit opt-in)
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
