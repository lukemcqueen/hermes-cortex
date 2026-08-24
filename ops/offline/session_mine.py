#!/usr/bin/env python3
"""
Hermes Cortex — Session Mining for Lesson Database
───────────────────────────────────────────────────
Sifts past Hermes sessions for bug fixes and distills them into
structured lessons. Bootstraps the lesson database from history.

Usage:
  session-mine                          # Interactive: review suggestions
  session-mine --auto --days 30         # Auto-save with confidence threshold
  session-mine --dry-run --days 7       # Preview only
  session-mine review                   # Review pending suggestions

Pipeline:
  1. Search session history for error/fix patterns
  2. For each candidate, extract error → cause → solution
  3. Check for duplicate lessons (semantic similarity ≥ 0.65)
  4. Save new lessons or present for review
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from hermes_paths import ensure_scripts_path
ensure_scripts_path()
from hermes_models import get_model

EMBEDDING_MODEL = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")

# ── Config ──────────────────────────────────────────────────
HOME = Path.home()
CORTEX_HOME = HOME / ".hermes-cortex"
LESSONS = HOME / "brain" / "lessons"
INDEX_FILE = HOME / "offline" / "lessons-index.json"

SESSION_DB = CORTEX_HOME / "sessions.db"  # Hermes session store

# Error/fix patterns to search for in session history
SEARCH_QUERIES = [
    # Original FTS patterns
    "error exception traceback failed",
    "bug fix root cause solution resolved",
    "fixed by changing OR fixed by adding OR fixed by removing",
    "error was caused by OR root cause was",
    "debugging OR debugged OR debug",
    "traceback OR stacktrace OR stack trace",
    "422 OR 500 OR 400 OR 403 OR 404 error",
    "database locked OR connection refused OR timeout",
    "import error OR module not found OR no module named",
    "key error OR attribute error OR type error OR value error",
    "permission denied OR access denied OR unauthorized",
    # Agent reasoning style patterns (matches reasoning column content)
    "i found a issue OR i found a problem OR the issue is",
    "two issues OR a few issues OR several issues",
    "the problem was OR the problem is OR this fails because",
    "wait OR hmm OR actually OR let me check",
    "need to fix OR needs to be OR should be OR instead of",
    "it turns out OR the reason is OR turns out that",
    "wasn't working OR didn't work OR not working OR wasn't correct",
    "let me fix OR let me update OR let me change OR fixed the",
    "i noticed OR i see the OR found that OR realized that",
    "we need to OR we should OR we have to",
    # Additional agent reasoning patterns
    "issue was that OR problem was that OR bug was that",
    "missing OR forgot OR forgotten OR hadn't",
    "failed because OR fails because OR failing because",
    "the fix was OR solution was OR resolved by",
]

# Minimum confidence for auto-save
AUTO_THRESHOLD = 0.7

# Max sessions to scan per run
MAX_SESSIONS = 200
MAX_PER_QUERY = 20


# ── Session History Access ──────────────────────────────────

def _get_session_db_path() -> Optional[Path]:
    """Find the Hermes session database."""
    candidates = [
        SESSION_DB,
        CORTEX_HOME / "state.db",
        CORTEX_HOME / "hermes-agent" / "sessions.db",
        HOME / ".hermes-agent" / "sessions.db",
        HOME / ".hermes" / "state.db",                # primary Hermes session store
        HOME / ".hermes" / "data" / "sessions.db",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def search_sessions(query: str, limit: int = 10) -> list:
    """Search session history using Hermes session_search (FTS5) CLI."""
    try:
        # Try using hermes session-search CLI
        result = subprocess.run(
            ["session_search", query, "--limit", str(limit), "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data

        # Fallback: direct SQLite query if DB is accessible
        db_path = _get_session_db_path()
        if db_path:
            return _query_sessions_sqlite(query, limit)

    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Fallback to SQLite
    db_path = _get_session_db_path()
    if db_path:
        return _query_sessions_sqlite(query, limit)

    return []


def _query_sessions_sqlite(query: str, limit: int = 10) -> list:
    """Direct SQLite FTS5 query on Hermes session DB."""
    db_path = _get_session_db_path()
    if not db_path:
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check for trigram FTS (best for partial-word matching)
        tables = {t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        if "messages_fts_trigram" in tables:
            # Trigram FTS — handles partial words, no stemming
            sql = """
                SELECT m.id, m.session_id, m.role,
                       COALESCE(NULLIF(m.content, ''), m.reasoning, m.reasoning_content, '') as text,
                       m.content, m.reasoning, m.reasoning_content,
                       s.id as session_title
                FROM messages m
                JOIN messages_fts_trigram f ON m.id = f.rowid
                LEFT JOIN sessions s ON m.session_id = s.id
                WHERE m.role IN ('user', 'assistant')
                  AND (s.id IS NULL OR (
                       s.id NOT LIKE 'auto-save%'
                   AND s.id NOT LIKE 'client-sync%'
                   AND s.id NOT LIKE 'cron_%'))
                  AND messages_fts_trigram MATCH ?
                ORDER BY RANDOM()
                LIMIT ?
            """
            try:
                # Convert query to trigram FTS syntax
                # Trigram FTS5 needs quoted phrases for multi-word terms
                if " OR " in query:
                    # Split on OR, quote multi-word phrases
                    parts = []
                    for part in query.split(" OR "):
                        part = part.strip()
                        if " " in part:
                            parts.append(f'"{part}"')
                        else:
                            parts.append(part)
                    fts_query = " OR ".join(parts)
                else:
                    # Space-separated words — OR them individually
                    fts_query = " OR ".join(query.split()[:5])
                rows = cur.execute(sql, (fts_query, limit)).fetchall()
            except sqlite3.OperationalError:
                rows = []
        else:
            rows = []

        # If FTS returns nothing, fallback to LIKE on user messages
        if not rows:
            terms = query.split()[:3]
            conditions = " AND ".join([f"m.content LIKE ?" for _ in terms])
            sql = f"""
                SELECT m.id, m.session_id, m.role, m.content, s.id as session_title
                FROM messages m
                LEFT JOIN sessions s ON m.session_id = s.id
                WHERE m.role IN ('user', 'assistant')
                  AND ({conditions})
                ORDER BY m.id DESC
                LIMIT ?
            """
            params = [f"%{t}%" for t in terms] + [limit]
            rows = cur.execute(sql, params).fetchall()

        results = []
        for row in rows:
            text = str(row[3] or "")
            content = str(row[4] or "")
            reasoning = str(row[5] or "")
            reasoning_content = str(row[6] or "")
            results.append({
                "id": row[0],
                "session_id": row[1],
                "role": row[2],
                "text": text,
                "content": content,
                "reasoning": reasoning,
                "reasoning_content": reasoning_content,
                "session_title": str(row[7] or ""),
            })

        conn.close()
        return results

    except (sqlite3.Error, Exception) as e:
        return [{"error": str(e)}]


# ── Candidate Extraction ────────────────────────────────────

def _extract_fix_pattern(text: str) -> Optional[dict]:
    """Extract problem → cause → solution from a text segment.
    
    Uses simple heuristics and pattern matching rather than LLM calls
    (keeping this free and fast for bulk mining).
    """
    if not text or len(text) < 60:
        return None

    # Skip context compaction blocks (no useful fix info)
    if "[CONTEXT COMPACTION" in text or "Earlier turns were compacted" in text:
        return None

    # Skip tool output blocks
    if text.strip().startswith("{") and '"success"' in text[:200]:
        return None

    result = {"problem": "", "cause": "", "solution": ""}

    # Look for error messages (highest signal)
    error_match = re.search(
        r'(?:(?:Error|Exception|Traceback|Failed|fatal):?\s*([^\n]+))'
        r'|(?:(?:sqlite3|psycopg2|requests|docker)\.\w+Error:\s*([^\n]+))'
        r'|(?:(?:HTTP|status)\s+\d{3}\s+[^\n]+)',
        text, re.IGNORECASE
    )
    if error_match:
        result["problem"] = (error_match.group(1) or error_match.group(2) or error_match.group(0)).strip()[:200]

    # If no explicit error found, look for broader problem descriptions
    if not result["problem"]:
        problem_patterns = [
            # Numbered issue lists (agent reasoning style)
            (r"(?:\d+\.\s*)([^\n]{15,200}?)(?=\n\d+\.|\n\n|\Z)", 1),
            (r"(?:Two|A few|Several) issues?:\s*\n?((?:.+\n?)*?(?=\n\n|\Z))", "block"),
            # Natural language problem statements
            (r"(?:the |an |a )?(?:issue|problem|bug|error)[:\s]+(.{10,200}?)(?:\.|$)", 1),
            (r"(?:the issue|the problem|the bug)\s+is\s+that\s+(.{10,200}?)(?:\.|$)", 1),
            (r"(?:the issue|the problem|the bug)\s+was\s+that\s+(.{10,200}?)(?:\.|$)", 1),
            (r"(?:wasn't|weren't|isn't|aren't)\s+(?:working|correct|right|valid)\s*(.{10,200}?)(?:\.,|$)", 1),
            (r"(?:didn't work|not working|failed to)\s+(.{10,200}?)(?:\.|$)", 1),
            (r"wait[,.]+(?:\s+this|\s+the|\s+it)?\s+(.{15,200}?)(?:\.|$)(?=(?:\n|$))", 1),
            # Verb-based problem detection
            (r"(?:returning|returned|getting|throws?)\s+(.{10,200}?(?:error|exception|fail))", 1),
            (r"(?:failed to|unable to|couldn't|cannot)\s+(.{10,200}?)(?:\.|$)", 1),
            # I noticed / found patterns
            (r"(?:i found|i noticed|i see)\s+that\s+(.{15,200}?)(?:\.|$)", 1),
            (r"(?:found|noticed)\s+(?:a|an|the|that)\s+(.{10,200}?)(?:issue|problem|bug)(?:\s|\.|$)", 1),
            (r"(\w+Error|Exception):\s*(.{10,200}?)(?:\.|$)", 2),
        ]
        for pat, group in problem_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(group).strip() if isinstance(group, int) else m.group(0).strip()
                if len(val) > 10:
                    result["problem"] = val[:200]
                    break

    # Look for cause indicators
    cause_patterns = [
        # Explicit reasoning cause patterns
        (r"(?:the reason|the root cause)\s+is\s+that\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:the reason|the root cause)\s+was\s+that\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:root cause|caused by|because|due to|reason)[:\s]+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:this is|it is|that is)\s+because\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:this was|it was|that was)\s+because\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:it turns out|turns out that)\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:the issue was|the problem was|the bug was)\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:what happened was|the thing was)\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:missing|forgot|forgotten|wasn't|weren't|didn't|hadn't)\s+(.{10,200}?)(?:\.|$)", 1),
    ]
    for pat, group in cause_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(group) if isinstance(group, int) else group(m)
            if len(val) > 10:
                result["cause"] = val[:200]
                break

    # Look for solution indicators
    solution_patterns = [
        (r"(?:the fix|the solution|the workaround)\s+is\s+to\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:the fix|the solution|the workaround)\s+was\s+to\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:fixed|fix|solution|resolved|solved)\s+(?:by|with|using):?\s*(.+?)(?:\.|$)", 1),
        (r"(?:i need to|we need to|we should|i should)\s+(.{10,200}?)(?:\.|$)", 1),
        (r"(?:added|changed|updated|modified|replaced|removed|set|enabled|disabled)\s+(.+?)(?:\.|$)", 1),
        (r"(?:let me fix|let me update|let me change|let me add)\s+(.+?)(?:\.|$)", 1),
        (r"(?:instead of|rather than)\s+(.+?)(?:\.,|$)", 1),
        (r"(?:solution|fix|workaround):?\s*(.+?)(?:\.|$)", 1),
        (r"(?:fixed the|fix the|fixing the)\s+(.+?)(?:\.|$)", 1),
    ]
    for pat, group in solution_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(group) if isinstance(group, int) else group(m)
            if len(val) > 10:
                result["solution"] = val[:200]
                break

    # Only return if we have at least problem + something
    if result["problem"] and (result["cause"] or result["solution"]):
        return result
    return None


def _detect_language(text: str) -> str:
    """Detect programming language from code snippets in text."""
    patterns = {
        "python": [r"import\s+\w+", r"from\s+\w+\s+import", r"def\s+\w+\s*\(", r"class\s+\w+.*:"],
        "javascript": [r"const\s+\w+\s*=", r"let\s+\w+\s*=", r"function\s+\w+\s*\(", r"=>\s*{"],
        "typescript": [r"interface\s+\w+", r"type\s+\w+\s*=", r":\s*(string|number|boolean)\b"],
        "go": [r"func\s+\w+\s*\(", r"package\s+\w+", r"import\s+\("],
        "rust": [r"fn\s+\w+\s*\(", r"let\s+mut\s+\w+", r"impl\s+\w+"],
        "yaml": [r"^\s*\w+:", r"^\s*-\s+\w+:"],
        "shell": [r"#!/bin/", r"^\w+=.*`", r"\$\(.*\)"],
        "sql": [r"SELECT\s+.*\s+FROM", r"CREATE\s+TABLE", r"ALTER\s+TABLE"],
        "docker": [r"FROM\s+\w+", r"RUN\s+", r"COPY\s+", r"CMD\s+\["],
        "javascript": [r"app\.(get|post|put|delete)\(", r"<script"],
    }
    scores = {}
    for lang, pats in patterns.items():
        count = sum(1 for p in pats if re.search(p, text, re.MULTILINE))
        if count > 0:
            scores[lang] = count
    return max(scores, key=scores.get) if scores else ""


def _detect_framework(text: str) -> str:
    """Detect framework from text."""
    patterns = {
        "fastapi": [r"FastAPI", r"fastapi"],
        "flask": [r"Flask\b", r"flask"],
        "django": [r"django", r"DJANGO"],
        "react": [r"React", r"react", r"jsx"],
        "docker": [r"Docker|docker compose|dockerfile"],
        "sqlite": [r"sqlite3|sqlite"],
        "pydantic": [r"pydantic|BaseModel", r"ConfigDict"],
    }
    for fw, pats in patterns.items():
        if any(re.search(p, text, re.IGNORECASE) for p in pats):
            return fw
    return ""


def _extract_tags(text: str) -> list:
    """Extract relevant tags from text."""
    tag_keywords = {
        "validation", "authentication", "authorization", "database",
        "deployment", "networking", "performance", "security",
        "migration", "testing", "docker", "configuration",
        "serialization", "concurrency", "error-handling",
        "api", "frontend", "backend", "cli", "monitoring",
    }
    found = set()
    text_lower = text.lower()
    for tag in tag_keywords:
        if tag in text_lower:
            found.add(tag)
    return sorted(found) if found else ["bug-fix"]


# ── Dedup ────────────────────────────────────────────────────

def _check_duplicate(title: str, problem: str, threshold: float = 0.65) -> Optional[str]:
    """Check if a lesson with similar content already exists. Returns path or None."""
    import urllib.request

    # Build search text
    search_text = f"{title}\n{problem}"[:500]

    # Embed the search text
    try:
        body = json.dumps({"model": EMBEDDING_MODEL, "input": search_text}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            qvec = data.get("embeddings", [None])[0]
            if not qvec:
                return None
    except Exception:
        return None

    # Load index
    if not INDEX_FILE.exists():
        return None

    try:
        index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return None

    if not index.get("entries"):
        return None

    # Compute similarity against all entries
    best_sim = 0
    best_path = None
    for entry in index["entries"]:
        evec = entry["embedding"]
        dot = sum(x * y for x, y in zip(qvec, evec))
        nq = sum(x * x for x in qvec) ** 0.5
        ne = sum(x * x for x in evec) ** 0.5
        sim = dot / (nq * ne) if nq and ne else 0
        if sim > best_sim:
            best_sim = sim
            best_path = entry.get("path")

    if best_sim >= threshold and best_path:
        return best_path
    return None


# ── Lesson Creation ──────────────────────────────────────────

def _save_lesson(title: str, problem: str, cause: str, solution: str,
                 evidence: str = "", language: str = "", framework: str = "",
                 tags: list = None, source: str = "session-mine") -> dict:
    """Save a new lesson file."""
    LESSONS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:80]
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_prefix}_{slug}.md"
    filepath = LESSONS / filename

    tags_str = ", ".join(tags) if tags else ""

    content = f"""---
title: "{title}"
created: "{timestamp}"
updated: "{timestamp}"
language: {language}
framework: {framework}
tags: [{tags_str}]
project: ""
success_count: 1
source: {source}
---

## Problem

{problem}

## Root Cause

{cause}

## Solution

{solution}

## Evidence

{evidence}
"""

    filepath.write_text(content.strip() + "\n", encoding="utf-8")
    return {"path": str(filepath), "filename": filename}


# ── Mining Pipeline ─────────────────────────────────────────

def mine_sessions(days: int = 30, auto: bool = False, dry_run: bool = False,
                  interactive: bool = False) -> dict:
    """Main mining pipeline: search → extract → dedup → save."""
    print(f"🔍 Mining session history (last {days} days)...")
    print()

    all_candidates = []
    seen_texts = set()

    for query in SEARCH_QUERIES:
        results = search_sessions(query, limit=MAX_PER_QUERY)
        for r in results:
            text = r.get("text", "")
            content = r.get("content", "")
            reasoning = r.get("reasoning", "")

            # text is already COALESCE'd from SQL — content/reasoning/reasoning_content fallback
            if not text or len(text) < 100:
                continue

            # Use reasoning content for extraction when available (has the fix narrative)
            extraction_text = reasoning if len(reasoning) >= 200 else text

            # Simple dedup on content text
            content_hash = hash(text[:200])
            if content_hash in seen_texts:
                continue
            seen_texts.add(content_hash)

            fix = _extract_fix_pattern(extraction_text)
            if fix:
                all_candidates.append({
                    **fix,
                    "session_id": r.get("session_id", ""),
                    "session_title": r.get("session_title", ""),
                    "created_at": r.get("created_at", ""),
                    "full_text": extraction_text[:2000],
                })

        if len(all_candidates) >= MAX_SESSIONS:
            break

    if not all_candidates:
        print("📭 No fix patterns found in recent session history.")
        return {"found": 0, "saved": 0}

    print(f"📋 Found {len(all_candidates)} potential fix patterns\n")

    saved = 0
    skipped_duplicate = 0
    skipped_low_confidence = 0

    for i, candidate in enumerate(all_candidates):
        title = candidate.get("session_title", "") or candidate["problem"][:60]
        language = _detect_language(candidate["full_text"])
        framework = _detect_framework(candidate["full_text"])
        tags = _extract_tags(candidate["full_text"])

        # Confidence score (simple heuristic)
        has_problem = len(candidate["problem"]) > 15
        has_cause = len(candidate["cause"]) > 10
        has_solution = len(candidate["solution"]) > 10
        confidence = (has_problem * 0.3 + has_cause * 0.3 + has_solution * 0.4)
        candidate["confidence"] = round(confidence, 2)

        # Check duplicate
        dup = _check_duplicate(title, candidate["problem"])
        if dup:
            skipped_duplicate += 1
            if not auto and interactive:
                print(f"  ⏭️  [{i+1}/{len(all_candidates)}] Duplicate → {Path(dup).name}")
            continue

        # Auto-save or review
        if auto:
            if confidence >= AUTO_THRESHOLD:
                _save_lesson(
                    title=title,
                    problem=candidate["problem"],
                    cause=candidate["cause"] or "Not explicitly stated",
                    solution=candidate["solution"] or "See evidence",
                    evidence=candidate["full_text"][:500],
                    language=language,
                    framework=framework,
                    tags=tags,
                    source="session-mine",
                )
                saved += 1
                print(f"  ✅ [{i+1}/{len(all_candidates)}] Saved: {title[:60]}")
            else:
                skipped_low_confidence += 1
                if dry_run:
                    print(f"  📄 [{i+1}/{len(all_candidates)}] Low confidence ({confidence}): {title[:60]}")

        elif dry_run:
            print(f"\n  📄 [{i+1}/{len(all_candidates)}] Candidate (confidence: {confidence})")
            print(f"     Title: {title[:60]}")
            print(f"     Problem: {candidate['problem'][:80]}")
            print(f"     Cause:   {candidate['cause'][:80] or '(not found)'}")
            print(f"     Solution: {candidate['solution'][:80] or '(not found)'}")
            print(f"     Lang: {language or '?'}  Framework: {framework or '?'}")
            if tags:
                print(f"     Tags: {', '.join(tags)}")
            print()

        elif interactive:
            print(f"\n  📄 [{i+1}/{len(all_candidates)}] Candidate (confidence: {confidence})")
            print(f"     Session: {candidate.get('session_title', '?')}")
            print(f"     Problem: {candidate['problem'][:120]}")
            print(f"     Cause:   {candidate['cause'][:120] or '(not found)'}")
            print(f"     Solution: {candidate['solution'][:120] or '(not found)'}")
            print()

    print()
    print(f"📊 Results:")
    print(f"   Found:     {len(all_candidates)} candidates")
    print(f"   Saved:     {saved}")
    if skipped_duplicate:
        print(f"   Duplicate: {skipped_duplicate} (skipped)")
    if skipped_low_confidence and auto:
        print(f"   Low conf:  {skipped_low_confidence} (below {AUTO_THRESHOLD})")

    return {
        "found": len(all_candidates),
        "saved": saved,
        "skipped_duplicate": skipped_duplicate,
        "skipped_low_confidence": skipped_low_confidence,
    }


# ── Export / Import / Sync ─────────────────────────────────

def export_lessons(output_path: str = None) -> dict:
    """Export all lessons to a single JSON file for syncing."""
    LESSONS.mkdir(parents=True, exist_ok=True)
    lesson_files = sorted(LESSONS.glob("*.md"))

    if not lesson_files:
        return {"status": "empty", "message": "No lessons to export"}

    lessons = []
    for f in lesson_files:
        try:
            text = f.read_text(encoding="utf-8")
            lessons.append({
                "filename": f.name,
                "content": text,
                "size": len(text),
            })
        except Exception as e:
            lessons.append({"filename": f.name, "error": str(e)})

    out = output_path or str(HOME / "offline" / "lessons-export.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(lessons),
        "lessons": lessons,
    }

    Path(out).write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "ok",
        "path": out,
        "count": len(lessons),
        "size_kb": round(len(json.dumps(export_data)) / 1024, 1),
    }


def import_lessons(input_path: str, merge: bool = True) -> dict:
    """Import lessons from an export file, with dedup."""
    path = Path(input_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {path}"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    imported = data.get("lessons", [])
    if not imported:
        return {"status": "empty", "count": 0}

    LESSONS.mkdir(parents=True, exist_ok=True)
    existing_files = {f.name for f in LESSONS.glob("*.md")}

    added = 0
    skipped = 0
    errors = 0

    for lesson in imported:
        filename = lesson.get("filename", "")
        content = lesson.get("content", "")

        if not filename or not content:
            errors += 1
            continue

        if merge and filename in existing_files:
            # Check if the local version is different
            local_path = LESSONS / filename
            local_content = local_path.read_text(encoding="utf-8")
            if local_content == content:
                skipped += 1
                continue
            # Merge: keep the longer version, sum success counts
            # Parse both
            import re as _re
            local_sc = int(_re.search(r'success_count:\s*(\d+)', local_content).group(1)) if _re.search(r'success_count:\s*(\d+)', local_content) else 1
            import_sc = int(_re.search(r'success_count:\s*(\d+)', content).group(1)) if _re.search(r'success_count:\s*(\d+)', content) else 1
            merged_count = local_sc + import_sc

            # Keep whichever has more detail (longer body)
            local_body_len = len(local_content)
            import_body_len = len(content)
            best = content if import_body_len > local_body_len else local_content

            # Update success count
            best = _re.sub(r'success_count:\s*\d+', f'success_count: {merged_count}', best)
            local_path.write_text(best, encoding="utf-8")
            added += 1
        else:
            # New file
            filepath = LESSONS / filename
            if not filepath.exists():
                filepath.write_text(content, encoding="utf-8")
                added += 1
            else:
                skipped += 1

    result = {
        "status": "ok",
        "imported": len(imported),
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }

    # Rebuild index after import
    import subprocess as _sp
    try:
        _sp.run(["offline_knowledge", "lesson", "index"], capture_output=True, timeout=60)
        result["indexed"] = True
    except Exception:
        result["indexed"] = False

    return result


# ── CLI ─────────────────────────────────────────────────────

def main(args: Optional[list] = None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="session-mine",
        description="Mine session history for bug-fix patterns → lesson database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # mine
    mp = sub.add_parser("mine", help="Mine sessions for bug fixes")
    mp.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    mp.add_argument("--auto", action="store_true", help="Auto-save (no review)")
    mp.add_argument("--dry-run", action="store_true", help="Preview only, don't save")

    # export
    ep = sub.add_parser("export", help="Export all lessons to JSON")
    ep.add_argument("--output", "-o", help="Output path (default: ~/offline/lessons-export.json)")

    # import
    ip = sub.add_parser("import", help="Import lessons from JSON export")
    ip.add_argument("path", help="Path to import file")
    ip.add_argument("--no-merge", action="store_true", help="Skip merged duplicates, just add new")
    ip.add_argument("--rebuild-index", action="store_true", help="Rebuild index after import")

    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        return

    if parsed.command == "mine":
        mine_sessions(
            days=parsed.days,
            auto=parsed.auto,
            dry_run=parsed.dry_run,
            interactive=not parsed.auto and not parsed.dry_run,
        )

    elif parsed.command == "export":
        result = export_lessons(parsed.output)
        if result["status"] == "ok":
            print(f"✅ Exported {result['count']} lessons to {result['path']}")
            print(f"   Size: {result['size_kb']} KB")
        elif result["status"] == "empty":
            print("📭 No lessons to export. Create some first with offline_knowledge lesson create")
        else:
            print(f"❌ {result['message']}")

    elif parsed.command == "import":
        result = import_lessons(parsed.path, merge=not parsed.no_merge)
        if result["status"] == "error":
            print(f"❌ {result['message']}")
            sys.exit(1)
        print(f"✅ Import complete: {result['added']} added, {result['skipped']} skipped, {result['errors']} errors")
        if result.get("indexed"):
            print("   Index rebuilt automatically")


if __name__ == "__main__":
    main()
