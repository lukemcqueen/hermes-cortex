#!/usr/bin/env python3
"""
web_cache.py — Local Semantic Web Cache for AI Agents

Transparently caches web_search and web_extract results using
SQLite + sqlite-vec for vector storage and Ollama for local embeddings.

Cache = your agent's "local internet" — answer queries offline,
reduce API costs, and carry knowledge across sessions.

Usage:
  web_cache search <query>              Semantic search cached queries
  web_cache store <query> [results.json] Store web_search results
  web_cache extract <url>               Check URL cache
  web_cache store-extract <url> [file]  Store web_extract results  
  web_cache prune                        LRU eviction over limit
  web_cache stats                        Cache statistics
  web_cache backup [path]               Backup DB to file
  web_cache export [path]               Export cache (portable tar.gz)
  web_cache import <file>               Import from export
  web_cache clear                        Wipe all cached data
  web_cache auto <query>                Search + store (for agent use)
  web_cache auto-extract <url> [file]   Check URL + store (for agent use)
"""

import argparse
import hashlib
import json
import math
import os
import sqlite3
import struct
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────

CACHE_DIR = Path(os.environ.get(
    "WEB_CACHE_DIR",
    Path.home() / ".hermes" / "web-cache"
))
DB_PATH = CACHE_DIR / "cache.db"
DEFAULT_LIMIT_MB = 200          # Max cache size before LRU eviction
SIMILARITY_THRESHOLD = 0.82     # Minimum cosine similarity for cache hit
DEFAULT_SEARCH_LIMIT = 5        # Default number of search results to return

OLLAMA_EMBED_URL = os.environ.get(
    "OLLAMA_EMBED_URL",
    "http://127.0.0.1:11434/api/embed"
)
OLLAMA_MODEL = os.environ.get(
    "OLLAMA_EMBED_MODEL",
    "nomic-embed-text"
)

# ── Embedded Model Dimensions ──────────────────────────────────
# nomic-embed-text = 768 dimensions
# all-MiniLM-L6-v2 = 384 dimensions
EMBED_DIMS = int(os.environ.get("WEB_CACHE_EMBED_DIMS", "768"))

# ── Local Venv Python ──────────────────────────────────────────
VENV_PYTHON = Path.home() / ".hermes" / "web-cache" / ".venv" / "bin" / "python3"

# ── SQLite Schema ──────────────────────────────────────────────

SCHEMA_SQL = """
-- Core search cache table
CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash  TEXT    UNIQUE NOT NULL,
    query_text  TEXT    NOT NULL,
    result_json TEXT    NOT NULL,
    result_summary TEXT,
    source_urls TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access TEXT    NOT NULL DEFAULT (datetime('now')),
    access_count INTEGER NOT NULL DEFAULT 1,
    result_size INTEGER
);

-- Per-URL extract cache table
CREATE TABLE IF NOT EXISTS extracts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash    TEXT    UNIQUE NOT NULL,
    url         TEXT    NOT NULL,
    title       TEXT,
    content     TEXT    NOT NULL,
    content_summary TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    last_access TEXT    NOT NULL DEFAULT (datetime('now')),
    access_count INTEGER NOT NULL DEFAULT 1,
    content_size INTEGER
);

-- Metadata table for tracking
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# ── Helpers ────────────────────────────────────────────────────


def get_connection():
    """Get SQLite connection with sqlite-vec loaded."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Enable extension loading (required by sqlite-vec)
    conn.enable_load_extension(True)

    # Load sqlite-vec extension via venv Python
    loaded = False
    if VENV_PYTHON.exists():
        import subprocess
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", "import sqlite_vec; print(sqlite_vec.extension_path())"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            ext_path = result.stdout.strip()
            try:
                conn.load_extension(ext_path)
                loaded = True
            except sqlite3.OperationalError:
                pass

    if not loaded:
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
            loaded = True
        except (ImportError, sqlite3.OperationalError):
            print("Warning: sqlite-vec not available, using Python fallback", file=sys.stderr)

    # Create tables
    conn.executescript(SCHEMA_SQL)

    # Create vec virtual tables if sqlite-vec is loaded
    if loaded:
        try:
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_searches USING vec0(
                    embedding float[{EMBED_DIMS}] distance_metric=cosine
                )
            """)
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_extracts USING vec0(
                    embedding float[{EMBED_DIMS}] distance_metric=cosine
                )
            """)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    return conn


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_embedding(text):
    """Get embedding vector from Ollama."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "input": text[:8192]  # Truncate to safe length
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, OSError) as e:
        print(f"Warning: Ollama embedding failed: {e}", file=sys.stderr)
    return None


def cosine_similarity(a, b):
    """Pure Python cosine similarity (fallback when sqlite-vec not available)."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb > 0 else 0.0


def pack_embedding(vec):
    """Pack float list into BLOB for storage."""
    return struct.pack(f"{len(vec)}f", *vec)


def unpack_embedding(blob):
    """Unpack BLOB into float list."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def db_size():
    """Get current DB file size in MB."""
    if DB_PATH.exists():
        return DB_PATH.stat().st_size / (1024 * 1024)
    return 0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def truncate(text, max_len=500):
    """Truncate text for summary storage."""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ── Core Operations ────────────────────────────────────────────


def cmd_search(query, limit=DEFAULT_SEARCH_LIMIT):
    """
    Semantic search cached queries. Returns list of matching results
    ordered by similarity (highest first).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get embedding for query
    query_embed = get_embedding(query)
    if query_embed is None:
        print("No embedding available (Ollama offline?). Returning empty.", file=sys.stderr)
        return []

    results = []

    # Try sqlite-vec search first
    try:
        # Pack query embedding for vec0 MATCH
        vec_blob = pack_embedding(query_embed)
        vec_cursor = conn.execute(
            "SELECT rowid, distance FROM vec_searches WHERE embedding MATCH ? AND k = ?",
            (vec_blob, limit * 2)  # Get more for post-filtering
        )
        vec_rows = vec_cursor.fetchall()

        for row in vec_rows:
            rowid = row["rowid"]
            distance = row["distance"]
            similarity = 1.0 - distance  # cosine distance → similarity

            if similarity >= SIMILARITY_THRESHOLD:
                detail = conn.execute(
                    "SELECT query_text, result_summary, source_urls, "
                    "last_access, access_count, created_at FROM searches WHERE id = ?",
                    (rowid,)
                ).fetchone()

                if detail:
                    # Update access tracking
                    conn.execute(
                        "UPDATE searches SET last_access = ?, access_count = access_count + 1 WHERE id = ?",
                        (now_iso(), rowid)
                    )
                    conn.commit()

                    results.append({
                        "id": rowid,
                        "query": detail["query_text"],
                        "summary": detail["result_summary"],
                        "urls": detail["source_urls"],
                        "similarity": round(similarity, 4),
                        "last_access": detail["last_access"],
                        "access_count": detail["access_count"],
                        "created_at": detail["created_at"],
                        "source": "vec_cache"
                    })
    except sqlite3.OperationalError:
        # sqlite-vec not available, fall back to Python comparison
        pass

    # Fallback: Python-side similarity for exact text matches
    if not results:
        all_rows = conn.execute(
            "SELECT id, query_text, result_summary, source_urls, "
            "last_access, access_count, created_at FROM searches"
        ).fetchall()

        for row in all_rows:
            # Exact/partial text match as simple fallback
            q = row["query_text"].lower()
            qry = query.lower()
            if qry in q or q in qry:
                sim = 0.9  # High similarity for text overlap
                results.append({
                    "id": row["id"],
                    "query": row["query_text"],
                    "summary": row["result_summary"],
                    "urls": row["source_urls"],
                    "similarity": sim,
                    "last_access": row["last_access"],
                    "access_count": row["access_count"],
                    "created_at": row["created_at"],
                    "source": "text_fallback"
                })

    # Sort by similarity desc, take top N
    results.sort(key=lambda r: r["similarity"], reverse=True)
    results = results[:limit]

    # Print results
    if results:
        print(json.dumps({"hits": results, "count": len(results), "cached": True}, indent=2))
    else:
        print(json.dumps({"hits": [], "count": 0, "cached": False}))

    conn.close()
    return results


def cmd_store(query, result_file=None):
    """Store web_search results in cache."""
    conn = get_connection()

    # Load results
    if result_file and result_file != "-":
        with open(result_file, "r") as f:
            result_data = f.read()
    else:
        result_data = sys.stdin.read()

    try:
        result_json = json.loads(result_data)
        result_str = json.dumps(result_json)
    except json.JSONDecodeError:
        result_json = {}
        result_str = result_data

    # Generate summary
    summary = truncate(result_str)
    source_urls = ""
    if isinstance(result_json, dict):
        data = result_json.get("data", result_json)
        if isinstance(data, dict):
            web_results = data.get("web") or data.get("results") or []
            urls = [r.get("url", "") for r in web_results if isinstance(r, dict)]
            source_urls = ", ".join(filter(None, urls[:5]))

    query_hash = sha256(query)
    now = now_iso()
    result_size = len(result_str.encode("utf-8"))

    # Get embedding
    embed = get_embedding(query)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO searches
               (query_hash, query_text, result_json, result_summary,
                source_urls, created_at, last_access, access_count, result_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (query_hash, query, result_str, summary, source_urls, now, now, result_size)
        )
        row_id = cursor.lastrowid

        # Store embedding in vec table
        if embed:
            vec_blob = pack_embedding(embed)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO vec_searches(rowid, embedding) VALUES (?, ?)",
                    (row_id, vec_blob)
                )
            except sqlite3.OperationalError:
                # Store as BLOB in main table (fallback)
                conn.execute(
                    "UPDATE searches SET embedding = ? WHERE id = ?",
                    (vec_blob, row_id)
                )

        conn.commit()
        print(json.dumps({"status": "stored", "id": row_id, "query": query}))
    except sqlite3.IntegrityError as e:
        print(json.dumps({"status": "exists", "error": str(e)}))

    conn.close()


def cmd_extract(url):
    """Check if a URL is cached. Returns cached content if found."""
    conn = get_connection()
    url_hash = sha256(url)

    row = conn.execute(
        "SELECT id, url, title, content, content_summary, "
        "last_access, access_count, created_at FROM extracts WHERE url_hash = ?",
        (url_hash,)
    ).fetchone()

    if row:
        # Update access tracking
        conn.execute(
            "UPDATE extracts SET last_access = ?, access_count = access_count + 1 WHERE id = ?",
            (now_iso(), row["id"])
        )
        conn.commit()

        result = {
            "id": row["id"],
            "url": row["url"],
            "title": row["title"],
            "content": row["content"],
            "summary": row["content_summary"],
            "last_access": row["last_access"],
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "cached": True
        }
        print(json.dumps(result, indent=2))
        conn.close()
        return result

    print(json.dumps({"url": url, "cached": False}))
    conn.close()
    return None


def cmd_store_extract(url, content_file=None):
    """Store web_extract results by URL."""
    conn = get_connection()
    url_hash = sha256(url)

    # Load content
    if content_file and content_file != "-":
        with open(content_file, "r") as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    # Try to extract title
    title = ""
    summary = truncate(content)

    now = now_iso()
    content_size = len(content.encode("utf-8"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO extracts
               (url_hash, url, title, content, content_summary,
                created_at, last_access, access_count, content_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (url_hash, url, title, content, summary, now, now, content_size)
        )
        row_id = cursor.lastrowid
        conn.commit()
        print(json.dumps({"status": "stored", "id": row_id, "url": url}))
    except sqlite3.IntegrityError as e:
        print(json.dumps({"status": "exists", "error": str(e)}))

    conn.close()


def cmd_prune(limit_mb=None):
    """
    LRU eviction: remove oldest entries when cache exceeds limit.
    Removes oldest-accessed entries first.
    """
    if limit_mb is None:
        limit_mb = DEFAULT_LIMIT_MB

    conn = get_connection()
    current_mb = db_size()

    if current_mb <= limit_mb:
        print(json.dumps({"status": "ok", "size_mb": round(current_mb, 1), "limit_mb": limit_mb, "pruned": 0}))
        conn.close()
        return

    # Remove oldest searches (by last_access) until under limit
    target_mb = limit_mb * 0.8  # Prune down to 80% of limit
    pruned = 0

    while db_size() > target_mb:
        # Find the oldest entry
        oldest = conn.execute(
            "SELECT id, query_text FROM searches ORDER BY last_access ASC LIMIT 1"
        ).fetchone()
        if not oldest:
            break

        # Remove from vec table
        try:
            conn.execute("DELETE FROM vec_searches WHERE rowid = ?", (oldest["id"],))
        except sqlite3.OperationalError:
            pass

        conn.execute("DELETE FROM searches WHERE id = ?", (oldest["id"],))
        conn.commit()
        pruned += 1

        # Also prune extracts if still over
        if db_size() > target_mb:
            oldest_ext = conn.execute(
                "SELECT id FROM extracts ORDER BY last_access ASC LIMIT 1"
            ).fetchone()
            if oldest_ext:
                conn.execute("DELETE FROM extracts WHERE id = ?", (oldest_ext["id"],))
                conn.commit()
                pruned += 1

    final_mb = db_size()
    print(json.dumps({
        "status": "pruned",
        "size_mb_before": round(current_mb, 1),
        "size_mb_after": round(final_mb, 1),
        "limit_mb": limit_mb,
        "pruned": pruned
    }))
    conn.close()


def cmd_stats():
    """Print cache statistics."""
    conn = get_connection()
    size_mb = round(db_size(), 1)

    search_count = conn.execute("SELECT COUNT(*) as c FROM searches").fetchone()["c"]
    extract_count = conn.execute("SELECT COUNT(*) as c FROM extracts").fetchone()["c"]

    # Calculate hit rate (based on access counts)
    total_accesses = conn.execute(
        "SELECT COALESCE(SUM(access_count), 0) as c FROM searches"
    ).fetchone()["c"]
    total_accesses += conn.execute(
        "SELECT COALESCE(SUM(access_count), 0) as c FROM extracts"
    ).fetchone()["c"]

    # Most accessed
    top_searches = conn.execute(
        "SELECT query_text, access_count, last_access FROM searches ORDER BY access_count DESC LIMIT 5"
    ).fetchall()

    top_extracts = conn.execute(
        "SELECT url, access_count, last_access FROM extracts ORDER BY access_count DESC LIMIT 5"
    ).fetchall()

    # DB path
    db_path_str = str(DB_PATH.resolve())

    stats = {
        "size_mb": size_mb,
        "search_entries": search_count,
        "extract_entries": extract_count,
        "total_entries": search_count + extract_count,
        "total_accesses": total_accesses,
        "top_searches": [
            {"query": r["query_text"], "accesses": r["access_count"], "last": r["last_access"]}
            for r in top_searches
        ],
        "top_extracts": [
            {"url": r["url"], "accesses": r["access_count"], "last": r["last_access"]}
            for r in top_extracts
        ],
        "db_path": db_path_str,
        "embed_model": OLLAMA_MODEL,
        "embed_dims": EMBED_DIMS,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "limit_mb": DEFAULT_LIMIT_MB
    }
    print(json.dumps(stats, indent=2))
    conn.close()


def cmd_backup(output_path=None):
    """Backup the SQLite DB file."""
    if output_path:
        dest = Path(output_path)
    else:
        backup_dir = CACHE_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / f"web-cache-{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    if DB_PATH.exists():
        import shutil
        shutil.copy2(str(DB_PATH), str(dest))
        print(json.dumps({"status": "backed_up", "path": str(dest), "size_mb": round(dest.stat().st_size / (1024*1024), 1)}))
    else:
        print(json.dumps({"status": "error", "message": "Cache DB does not exist"}))


def cmd_export(output_path=None):
    """Export cache to portable tar.gz (content + embeddings)."""
    if output_path:
        dest = Path(output_path)
    else:
        dest = CACHE_DIR / f"web-cache-export-{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"

    conn = get_connection()

    # Export data as JSONL
    export_data = {"searches": [], "extracts": [], "meta": {}}

    # Get all searches
    for row in conn.execute("SELECT * FROM searches").fetchall():
        entry = dict(row)
        entry.pop("embedding", None)  # Don't include raw BLOB in JSON
        export_data["searches"].append(entry)

    # Get all extracts
    for row in conn.execute("SELECT * FROM extracts").fetchall():
        export_data["extracts"].append(dict(row))

    # Get meta
    for row in conn.execute("SELECT * FROM meta").fetchall():
        export_data["meta"][row["key"]] = row["value"]

    # Add export metadata
    export_data["meta"]["exported_at"] = now_iso()
    export_data["meta"]["embed_model"] = OLLAMA_MODEL
    export_data["meta"]["embed_dims"] = str(EMBED_DIMS)
    export_data["meta"]["search_count"] = str(len(export_data["searches"]))
    export_data["meta"]["extract_count"] = str(len(export_data["extracts"]))

    # Write tar.gz
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(export_data, f, indent=2)
        json_path = f.name

    with tarfile.open(str(dest), "w:gz") as tar:
        tar.add(json_path, arcname="web-cache-export.json")

    os.unlink(json_path)

    size_mb = round(dest.stat().st_size / (1024 * 1024), 2)
    print(json.dumps({
        "status": "exported",
        "path": str(dest),
        "size_mb": size_mb,
        "searches": len(export_data["searches"]),
        "extracts": len(export_data["extracts"])
    }))

    conn.close()
    return str(dest)


def cmd_import(import_path):
    """Import cache entries from an export tar.gz."""
    source = Path(import_path)
    if not source.exists():
        print(json.dumps({"status": "error", "message": f"File not found: {import_path}"}))
        return

    conn = get_connection()

    # Extract
    with tarfile.open(str(source), "r:gz") as tar:
        json_file = tar.extractfile("web-cache-export.json")
        if not json_file:
            print(json.dumps({"status": "error", "message": "Invalid export file"}))
            return
        export_data = json.loads(json_file.read())

    imported = {"searches": 0, "extracts": 0}

    # Import searches
    for entry in export_data.get("searches", []):
        try:
            conn.execute(
                """INSERT OR IGNORE INTO searches
                   (query_hash, query_text, result_json, result_summary,
                    source_urls, created_at, last_access, access_count, result_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["query_hash"], entry["query_text"], entry["result_json"],
                 entry.get("result_summary"), entry.get("source_urls"),
                 entry.get("created_at", now_iso()), entry.get("last_access", now_iso()),
                 entry.get("access_count", 1), entry.get("result_size"))
            )
            if conn.total_changes > 0:
                imported["searches"] += 1
        except sqlite3.IntegrityError:
            pass

    # Import extracts
    for entry in export_data.get("extracts", []):
        try:
            conn.execute(
                """INSERT OR IGNORE INTO extracts
                   (url_hash, url, title, content, content_summary,
                    created_at, last_access, access_count, content_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["url_hash"], entry["url"], entry.get("title", ""),
                 entry["content"], entry.get("content_summary"),
                 entry.get("created_at", now_iso()), entry.get("last_access", now_iso()),
                 entry.get("access_count", 1), entry.get("content_size"))
            )
            if conn.total_changes > 0:
                imported["extracts"] += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    print(json.dumps({
        "status": "imported",
        "source": str(source),
        "imported_searches": imported["searches"],
        "imported_extracts": imported["extracts"],
        "total_entries": imported["searches"] + imported["extracts"]
    }))
    conn.close()


def cmd_clear():
    """Wipe all cached data."""
    conn = get_connection()
    conn.execute("DELETE FROM searches")
    conn.execute("DELETE FROM extracts")
    try:
        conn.execute("DELETE FROM vec_searches")
        conn.execute("DELETE FROM vec_extracts")
    except sqlite3.OperationalError:
        pass
    conn.execute("DELETE FROM meta")
    conn.commit()
    print(json.dumps({"status": "cleared"}))
    conn.close()


def cmd_auto(query):
    """
    For agent use: search cache first, if miss return empty.
    Agent calls this before web_search, then calls store after.
    """
    return cmd_search(query)


def cmd_auto_extract(url):
    """For agent use: check URL cache first."""
    return cmd_extract(url)


# ── CLI Dispatch ───────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Local semantic web cache for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  web_cache search "Python async patterns"
  web_cache store "Python async patterns" results.json
  web_cache extract https://docs.python.org/3/asyncio.html
  web_cache prune
  web_cache stats
  web_cache export ~/backups/web-cache.tar.gz
  web_cache import ~/backups/web-cache.tar.gz
  web_cache backup ~/backups/
  echo '{"results": [...]}' | web_cache store "my query" -
        """
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # search
    p = subparsers.add_parser("search", help="Semantic search cached queries")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="Max results")

    # store
    p = subparsers.add_parser("store", help="Store web_search results")
    p.add_argument("query", help="Original search query")
    p.add_argument("file", nargs="?", default=None, help="JSON file with results (default: stdin)")

    # extract
    p = subparsers.add_parser("extract", help="Check URL cache")
    p.add_argument("url", help="URL to check")

    # store-extract
    p = subparsers.add_parser("store-extract", help="Store web_extract results")
    p.add_argument("url", help="Original URL")
    p.add_argument("file", nargs="?", default=None, help="Content file (default: stdin)")

    # auto
    p = subparsers.add_parser("auto", help="Search + cache check (for agent use)")
    p.add_argument("query", help="Search query")

    # auto-extract
    p = subparsers.add_parser("auto-extract", help="URL cache check (for agent use)")
    p.add_argument("url", help="URL to check")

    # prune
    subparsers.add_parser("prune", help="LRU eviction over limit")

    # stats
    subparsers.add_parser("stats", help="Cache statistics")

    # backup
    p = subparsers.add_parser("backup", help="Backup DB file")
    p.add_argument("path", nargs="?", default=None, help="Output path")

    # export
    p = subparsers.add_parser("export", help="Export cache to portable tar.gz")
    p.add_argument("path", nargs="?", default=None, help="Output path")

    # import
    p = subparsers.add_parser("import", help="Import from export")
    p.add_argument("file", help="Import file path")

    # clear
    subparsers.add_parser("clear", help="Wipe all cached data")

    args = parser.parse_args()

    try:
        if args.command == "search":
            cmd_search(args.query, args.limit)
        elif args.command == "store":
            cmd_store(args.query, args.file)
        elif args.command == "extract":
            cmd_extract(args.url)
        elif args.command == "store-extract":
            cmd_store_extract(args.url, args.file)
        elif args.command == "auto":
            cmd_auto(args.query)
        elif args.command == "auto-extract":
            cmd_auto_extract(args.url)
        elif args.command == "prune":
            cmd_prune()
        elif args.command == "stats":
            cmd_stats()
        elif args.command == "backup":
            cmd_backup(args.path)
        elif args.command == "export":
            cmd_export(args.path)
        elif args.command == "import":
            cmd_import(args.file)
        elif args.command == "clear":
            cmd_clear()
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
