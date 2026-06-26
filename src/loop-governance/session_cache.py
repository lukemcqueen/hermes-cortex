#!/usr/bin/env python3
"""
Session Embedding Cache — builds a local vector index from session data.

Takes session files, loop DB cycles, and skill content, embeds them
with nomic-embed-text, stores in SQLite for fast similarity search.

This improves progress detection: score_progress() can compare
current code against similar past sessions, not just the immediate
previous cycle.

Usage:
    python3 session_cache.py build     # embed all available data
    python3 session_cache.py search    # interactive search
    python3 session_cache.py status    # show cache stats
"""

import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CACHE_DB = HOME / ".hermes" / "data" / "session-embeddings.db"
LOOP_DB = HOME / ".hermes" / "data" / "loop-governance.db"
SESSION_DIR = HOME / ".hermes-cortex" / "sessions"
SKILLS_DIR = HOME / ".hermes-cortex" / "skills" / "software-development"
INBOX_DIR = HOME / "agent-inbox-private" / "inbox"

OLLAMA_URL = "http://localhost:11434/api/embeddings"
NOMIC_MODEL = "nomic-embed-text"


def embed(text: str) -> list[float] | None:
    try:
        payload = json.dumps({"model": NOMIC_MODEL, "prompt": text[:2000]}).encode()
        req = urllib.request.Request(OLLAMA_URL, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


# ── Schema ─────────────────────────────────────────────────────

def init_db():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            source_id TEXT,
            text TEXT NOT NULL,
            embedding TEXT NOT NULL,
            agent TEXT DEFAULT 'moses',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_source
        ON embeddings(source)
    """)
    conn.commit()
    return conn


# ── Data Sources ───────────────────────────────────────────────

def embed_sessions(conn):
    """Embed session files from .hermes-cortex/sessions/"""
    count = 0
    if not SESSION_DIR.exists():
        return count

    for f in sorted(SESSION_DIR.glob("*.md"))[-30:]:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")[:3000]
            if len(text.strip()) < 100:
                continue
            # Skip if already cached
            existing = conn.execute(
                "SELECT id FROM embeddings WHERE source='session' AND source_id=?",
                (f.name,)
            ).fetchone()
            if existing:
                continue

            emb = embed(text)
            if not emb:
                continue

            conn.execute(
                "INSERT INTO embeddings (source, source_id, text, embedding, agent) VALUES (?, ?, ?, ?, ?)",
                ("session", f.name, text[:500], json.dumps(emb), "moses")
            )
            count += 1
        except Exception:
            continue
    conn.commit()
    return count


def embed_loop_db(conn):
    """Embed high-scoring cycles from the loop governance DB."""
    count = 0
    if not LOOP_DB.exists():
        return count

    try:
        src = sqlite3.connect(str(LOOP_DB))
        rows = src.execute(
            "SELECT id, task_id, code_or_spec, output_text FROM loop_cycles WHERE composite >= 6.0 ORDER BY composite DESC LIMIT 50"
        ).fetchall()
        src.close()

        for row in rows:
            cycle_id, task_id, code, output = row
            text = f"{task_id}: {code[:1000]} -> {output[:500]}"
            if len(text.strip()) < 50:
                continue

            existing = conn.execute(
                "SELECT id FROM embeddings WHERE source='loop_db' AND source_id=?",
                (str(cycle_id),)
            ).fetchone()
            if existing:
                continue

            emb = embed(text)
            if not emb:
                continue

            conn.execute(
                "INSERT INTO embeddings (source, source_id, text, embedding, agent) VALUES (?, ?, ?, ?, ?)",
                ("loop_db", str(cycle_id), text[:500], json.dumps(emb), "moses")
            )
            count += 1
    except Exception:
        pass
    conn.commit()
    return count


def embed_skills(conn):
    """Embed SKILL.md content from installed skills."""
    count = 0
    if not SKILLS_DIR.exists():
        return count

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")[:3000]
            if len(text.strip()) < 50:
                continue

            existing = conn.execute(
                "SELECT id FROM embeddings WHERE source='skill' AND source_id=?",
                (skill_dir.name,)
            ).fetchone()
            if existing:
                continue

            emb = embed(text)
            if not emb:
                continue

            conn.execute(
                "INSERT INTO embeddings (source, source_id, text, embedding, agent) VALUES (?, ?, ?, ?, ?)",
                ("skill", skill_dir.name, text[:500], json.dumps(emb), "moses")
            )
            count += 1
        except Exception:
            continue
    conn.commit()
    return count


# ── Search ──────────────────────────────────────────────────────

def search(query: str, top_k: int = 5) -> list[dict]:
    """Search the cache for the most similar entries."""
    query_emb = embed(query)
    if not query_emb:
        print("  ⚠  Embedding unavailable — can't search")
        return []

    conn = sqlite3.connect(str(CACHE_DB))
    rows = conn.execute(
        "SELECT id, source, source_id, text, embedding, agent FROM embeddings"
    ).fetchall()
    conn.close()

    scored = []
    for row in rows:
        stored = json.loads(row[4])
        sim = cosine_similarity(query_emb, stored)
        scored.append((sim, {
            "id": row[0],
            "source": row[1],
            "source_id": row[2],
            "text": row[3],
            "agent": row[5],
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:top_k]]


# ── CLI ─────────────────────────────────────────────────────────

def cmd_build():
    conn = init_db()
    total = 0

    print("  Embedding sessions…")
    n = embed_sessions(conn)
    print(f"    {n} new session embeddings")
    total += n

    print("  Embedding loop DB cycles…")
    n = embed_loop_db(conn)
    print(f"    {n} new cycle embeddings")
    total += n

    print("  Embedding skills…")
    n = embed_skills(conn)
    print(f"    {n} new skill embeddings")
    total += n

    print(f"\n  Total new embeddings: {total}")
    cmd_status(conn)
    conn.close()


def cmd_status(conn=None):
    close = conn is None
    if close:
        conn = sqlite3.connect(str(CACHE_DB))
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM embeddings GROUP BY source"
    ).fetchall()
    if close:
        conn.close()

    if not rows:
        print("  Cache is empty. Run 'build' first.")
        return

    print("  Embedding cache:")
    for source, count in rows:
        print(f"    {source}: {count} embeddings")
    print(f"    Total: {sum(c for _, c in rows)}")


def cmd_search():
    query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else input("  Search: ")
    if not query:
        return
    results = search(query)
    if not results:
        print("  No results.")
        return
    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] {r['source']}/{r['source_id']} (from {r['agent']})")
        print(f"      {r['text'][:150]}…")


def main():
    print(f"\n═ Session Embedding Cache — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ═\n")

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("  Usage:")
        print("    session-cache build    Embed all available data")
        print("    session-cache search   Similarity search")
        print("    session-cache status   Show cache stats")
        print()
        return

    cmd = sys.argv[1]
    if cmd == "build":
        cmd_build()
    elif cmd == "status":
        cmd_status()
    elif cmd == "search":
        cmd_search()
    else:
        print(f"  Unknown command: {cmd}")


if __name__ == "__main__":
    main()